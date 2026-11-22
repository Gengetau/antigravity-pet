/**
 * Token Meter sidecar backend for Antigravity Desktop.
 *
 * Read-only telemetry aggregator:
 * - Queries LanguageServerService Connect JSON RPCs (GetUserStatus,
 *   GetAllCascadeTrajectories, GetCascadeTrajectory) with incremental caching.
 * - Falls back to local <appData>/brain/<conv>/.system_generated/logs/transcript.jsonl
 *   when cold trajectories cannot be fetched over RPC.
 * - Computes per-model and per-step token breakdowns (input, cache read,
 *   thinking output, response output), dual speed metrics (streaming decode
 *   tok/s, end-to-end tok/s, and TTFT ms), model quota remaining, and context
 *   window occupancy.
 * - Writes a compact live snapshot to <ANTIGRAVITY_EXECUTABLE_DATA_DIR>/hud_live.json
 *   every 2.5s so the standalone desktop Always-On-Top HUD bar stays updated
 *   across Antigravity restarts.
 */

import { existsSync, mkdirSync, readFileSync, readdirSync, renameSync, statSync, writeFileSync } from 'node:fs';
import { homedir } from 'node:os';
import { basename, dirname, join } from 'node:path';
import { fileURLToPath, pathToFileURL } from 'node:url';

const __dirname = dirname(fileURLToPath(import.meta.url));
const UUID_RE = /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i;

function findAppDataDirs() {
  const execDataDir = process.env.ANTIGRAVITY_EXECUTABLE_DATA_DIR;
  if (execDataDir) {
    for (let d = execDataDir; d !== dirname(d); d = dirname(d)) {
      if (basename(d) === 'sidecar_data') {
        const appData = dirname(d);
        if (existsSync(appData)) return [appData];
      }
    }
  }
  const geminiRoot = join(homedir(), '.gemini');
  const out = [];
  try {
    for (const entry of readdirSync(geminiRoot)) {
      const candidate = join(geminiRoot, entry);
      if (existsSync(join(candidate, 'brain'))) out.push(candidate);
    }
  } catch {
    // Ignore unreadable root.
  }
  return out;
}

function resolveHudDataDir() {
  if (process.env.ANTIGRAVITY_EXECUTABLE_DATA_DIR) {
    return process.env.ANTIGRAVITY_EXECUTABLE_DATA_DIR;
  }
  const appDirs = findAppDataDirs();
  const base = appDirs[0] || join(homedir(), '.gemini', 'antigravity');
  return join(base, 'sidecar_data', 'token-meter', 'dashboard', 'data');
}

async function loadSidecarSdk() {
  try {
    return await import('sidecar_sdk');
  } catch {
    for (const appData of findAppDataDirs()) {
      const sdkPath = join(appData, 'lib', 'node_modules', 'sidecar_sdk', 'index.mjs');
      if (existsSync(sdkPath)) {
        return await import(pathToFileURL(sdkPath).href);
      }
    }
    const fallback = join(homedir(), '.gemini', 'antigravity', 'lib', 'node_modules', 'sidecar_sdk', 'index.mjs');
    if (existsSync(fallback)) {
      return await import(pathToFileURL(fallback).href);
    }
    throw new Error('Unable to locate sidecar_sdk');
  }
}

if (!process.env.ANTIGRAVITY_SIDECAR_WEB_PORT) {
  process.env.ANTIGRAVITY_SIDECAR_WEB_PORT = process.env.PORT || '18920';
}
if (!process.env.ANTIGRAVITY_LS_ADDRESS) {
  process.env.ANTIGRAVITY_LS_ADDRESS = '127.0.0.1:5387';
}
if (!process.env.ANTIGRAVITY_CSRF_TOKEN) {
  process.env.ANTIGRAVITY_CSRF_TOKEN = 'standalone';
}

const { SidecarApp, Response } = await loadSidecarSdk();
const app = new SidecarApp();

const LS_ADDRESS = process.env.ANTIGRAVITY_LS_ADDRESS;
const CSRF_TOKEN = process.env.ANTIGRAVITY_CSRF_TOKEN;

async function lsRpc(method, body = {}, timeoutMs = 6000) {
  const res = await fetch(
    `http://${LS_ADDRESS}/exa.language_server_pb.LanguageServerService/${method}`,
    {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
        'x-codeium-csrf-token': CSRF_TOKEN,
      },
      body: JSON.stringify(body),
      signal: AbortSignal.timeout(timeoutMs),
    }
  );
  if (!res.ok) {
    throw new Error(`LS ${method} HTTP ${res.status}`);
  }
  return await res.json();
}

// ---------------------------------------------------------------------------
// Model metadata & quota cache (refreshed every 15s from GetUserStatus)
// ---------------------------------------------------------------------------

let userModelStateCache = {
  fetchedAt: 0,
  labelMap: new Map(),
  quotaMap: new Map(),
  limitMap: new Map(),
  selectedModelId: '',
};

function prettifyModelEnum(raw) {
  if (!raw || typeof raw !== 'string') return 'Unknown Model';
  if (!raw.startsWith('MODEL_')) return raw;
  return raw
    .replace(/^MODEL_PLACEHOLDER_/, 'Model ')
    .replace(/^MODEL_/, '')
    .split('_')
    .map((w) => (w.length <= 3 && /\d/.test(w) ? w : w.charAt(0) + w.slice(1).toLowerCase()))
    .join(' ');
}

function prettifyProvider(raw) {
  if (!raw || typeof raw !== 'string') return '';
  return raw
    .replace(/^API_PROVIDER_/, '')
    .split('_')
    .map((w) => w.charAt(0) + w.slice(1).toLowerCase())
    .join(' ');
}

const DEFAULT_CONTEXT_LIMIT = 524_288; // 512k: Antigravity's default window
const UNKNOWN_MODEL_LABELS = new Set(['', '未知模型', '未选择模型', 'unknown model', 'UNKNOWN_MODEL']);

function inferContextWindowLimit(modelId, label, limitMap) {
  const reported = limitMap?.get?.(modelId);
  if (Number.isFinite(reported) && reported > 0) return reported;
  const cleanId = UNKNOWN_MODEL_LABELS.has(String(modelId || '').trim()) ? '' : String(modelId || '');
  const cleanLabel = UNKNOWN_MODEL_LABELS.has(String(label || '').trim()) ? '' : String(label || '');
  const s = `${cleanId} ${cleanLabel}`.toLowerCase();
  if (s.includes('claude')) return 200_000;
  if (s.includes('gpt-oss') || s.includes('120b')) return 131_072;
  return DEFAULT_CONTEXT_LIMIT;
}

// A model config may report its context window; field names differ between
// LS versions, so look for any plausible numeric field.
const CONTEXT_KEY = /context.*(window|length|limit|size|tokens)|max_?input_?tokens|input_?token_?limit|max_?prompt_?tokens/i;

function findContextLimit(value, depth = 0) {
  if (!value || typeof value !== 'object' || depth > 4) return null;
  for (const [key, field] of Object.entries(value)) {
    const n = Number(field);
    if (CONTEXT_KEY.test(key) && Number.isFinite(n) && n >= 8_000 && n <= 20_000_000) return n;
  }
  for (const field of Object.values(value)) {
    const found = findContextLimit(field, depth + 1);
    if (found) return found;
  }
  return null;
}

function keyPaths(value, prefix = '', depth = 0, out = []) {
  if (!value || typeof value !== 'object' || depth > 4) return out;
  for (const [key, field] of Object.entries(value)) {
    const path = prefix ? `${prefix}.${key}` : key;
    if (field && typeof field === 'object' && !Array.isArray(field)) keyPaths(field, path, depth + 1, out);
    else out.push(typeof field === 'number' ? `${path}=${field}` : path);
  }
  return out;
}

async function getUserModelState(maxAgeMs = 15_000) {
  const now = Date.now();
  if (now - userModelStateCache.fetchedAt < maxAgeMs && userModelStateCache.labelMap.size > 0) {
    return userModelStateCache;
  }
  try {
    const data = await lsRpc('GetUserStatus', {});
    const cfgData = data?.userStatus?.cascadeModelConfigData || {};
    const configs = cfgData?.clientModelConfigs;
    const selectedModelId =
      cfgData?.defaultOverrideModelConfig?.modelOrAlias?.model ||
      cfgData?.defaultOverrideModelConfig?.modelOrAlias?.alias ||
      '';

    if (Array.isArray(configs)) {
      const nextLabels = new Map(userModelStateCache.labelMap);
      const nextQuotas = new Map();
      const nextLimits = new Map();
      const schema = {};
      for (const cfg of configs) {
        const key = cfg?.modelOrAlias?.model || cfg?.modelOrAlias?.alias;
        const label = cfg?.label || cfg?.displayName;
        if (key && label) nextLabels.set(key, label);
        const limit = findContextLimit(cfg);
        if (key && limit) nextLimits.set(key, limit);
        // Field names (and numbers) only, to confirm where the window lives.
        if (key) schema[key] = { label: label || '', contextLimit: limit, fields: keyPaths(cfg) };
        if (key && cfg?.quotaInfo) {
          const frac = Number(cfg.quotaInfo.remainingFraction);
          nextQuotas.set(key, {
            remainingPct: Number.isFinite(frac) ? Math.max(0, Math.min(100, frac * 100)) : null,
            resetTime: cfg.quotaInfo.resetTime || null,
          });
        }
      }
      userModelStateCache = {
        fetchedAt: now,
        labelMap: nextLabels,
        quotaMap: nextQuotas,
        limitMap: nextLimits,
        selectedModelId: selectedModelId || userModelStateCache.selectedModelId,
      };
      try {
        const outDir = resolveHudDataDir();
        mkdirSync(outDir, { recursive: true });
        writeFileSync(join(outDir, 'model_configs.json'), JSON.stringify(schema, null, 2), 'utf-8');
      } catch {
        // diagnostics only
      }
    }
  } catch {
    // Keep last known state on transient failure.
  }
  return userModelStateCache;
}

// ---------------------------------------------------------------------------
// Quota windows (RetrieveUserQuotaSummary): e.g. a 5-hour and a weekly bucket.
// Only the bucket fields below are kept; nothing else from the reply is written.
// ---------------------------------------------------------------------------

let quotaSummaryCache = { fetchedAt: 0, buckets: [], status: 'pending', method: '' };

// The language server exposes RetrieveUserQuotaSummary (GetUserQuotaSummary is
// the name on Google's backend and 404s here); keep the old name as fallback.
const QUOTA_SUMMARY_METHODS = ['RetrieveUserQuotaSummary', 'GetUserQuotaSummary'];

// Text that may say which window a bucket is (5 hours / weekly ...).
const WINDOW_KEY = /window|period|duration|interval|cadence|reset|refresh|type|name|title|description|label/i;

function describeWindow(value) {
  if (value == null) return '';
  if (typeof value === 'string' || typeof value === 'number') return String(value);
  if (typeof value === 'object' && ('seconds' in value || 'nanos' in value)) return `${Number(value.seconds || 0)}s`;
  return '';
}

function normalizeBucket(bucket, groupName) {
  if (!bucket || typeof bucket !== 'object') return null;
  const frac = Number(bucket.remainingFraction);
  // Field names differ between versions: gather every short descriptive field.
  const hints = [];
  for (const [key, value] of Object.entries(bucket)) {
    if (key === 'remainingFraction' || key === 'resetTime') continue;
    if (WINDOW_KEY.test(key)) {
      const text = describeWindow(value);
      if (text && text.length <= 120) hints.push(text);
    }
  }
  return {
    id: String(bucket.bucketId || bucket.id || bucket.quotaBucketKey || ''),
    name: String(bucket.displayName || bucket.name || bucket.title || ''),
    description: hints.join(' '),
    group: groupName || '',
    window: describeWindow(bucket.window ?? bucket.windowDuration ?? bucket.period ?? bucket.resetPeriod ?? ''),
    remainingPct: Number.isFinite(frac) ? Math.max(0, Math.min(100, frac * 100)) : null,
    remainingAmount: bucket.remainingAmount ?? null,
    resetTime: bucket.resetTime || null,
    disabled: Boolean(bucket.disabled),
  };
}

// Every object carrying a remainingFraction is a bucket, wherever it sits.
function collectBuckets(value, groupName, out, depth = 0) {
  if (!value || typeof value !== 'object' || depth > 8) return out;
  if (Array.isArray(value)) {
    for (const item of value) collectBuckets(item, groupName, out, depth + 1);
    return out;
  }
  if ('remainingFraction' in value) {
    const bucket = normalizeBucket(value, groupName);
    if (bucket) out.push(bucket);
  }
  const name = String(value.displayName || value.name || groupName || '');
  for (const [key, field] of Object.entries(value)) {
    if (field && typeof field === 'object') collectBuckets(field, key === 'quotaSubBuckets' ? groupName : name, out, depth + 1);
  }
  return out;
}

async function getQuotaSummary(maxAgeMs = 60_000) {
  const now = Date.now();
  if (now - quotaSummaryCache.fetchedAt < maxAgeMs) return quotaSummaryCache;
  const errors = [];
  for (const method of QUOTA_SUMMARY_METHODS) {
    try {
      const data = await lsRpc(method, {});
      const buckets = collectBuckets(data, '', []);
      try {
        // Quota numbers and bucket names only; kept for checking the shape.
        const outDir = resolveHudDataDir();
        mkdirSync(outDir, { recursive: true });
        writeFileSync(join(outDir, 'quota_summary_raw.json'), JSON.stringify({ method, data }, null, 2), 'utf-8');
      } catch {
        // diagnostics only
      }
      quotaSummaryCache = { fetchedAt: now, buckets, status: buckets.length ? 'ok' : 'empty', method };
      return quotaSummaryCache;
    } catch (err) {
      errors.push(`${method}: ${String(err?.message || 'error').slice(0, 60)}`);
    }
  }
  quotaSummaryCache = { fetchedAt: now, buckets: quotaSummaryCache.buckets, status: errors.join(' | ').slice(0, 200), method: '' };
  return quotaSummaryCache;
}

// ---------------------------------------------------------------------------
// Parsing timestamps, durations, and trajectories
// ---------------------------------------------------------------------------

function parseIsoMs(iso) {
  if (!iso || typeof iso !== 'string') return null;
  const ms = Date.parse(iso);
  return Number.isFinite(ms) ? ms : null;
}

function parseProtoDurationMs(dur) {
  if (!dur) return null;
  if (typeof dur === 'string') {
    const m = /^(-?\d+(?:\.\d+)?)s$/.exec(dur.trim());
    return m ? Math.max(0, parseFloat(m[1]) * 1000) : null;
  }
  if (typeof dur === 'object') {
    const sec = Number(dur.seconds || 0);
    const nanos = Number(dur.nanos || 0);
    return Math.max(0, sec * 1000 + nanos / 1e6);
  }
  return null;
}

function toInt(v) {
  const n = Number(v || 0);
  return Number.isFinite(n) && n > 0 ? Math.round(n) : 0;
}

function extractCleanUserTitle(text) {
  if (!text || typeof text !== 'string') return '';
  const reqMatch = /<USER_REQUEST>([\s\S]*?)<\/USER_REQUEST>/i.exec(text);
  const body = (reqMatch ? reqMatch[1] : text)
    .replace(/<[^>]+>/g, ' ')
    .replace(/\s+/g, ' ')
    .trim();
  if (!body) return '';
  return body.length > 48 ? `${body.slice(0, 48)}…` : body;
}

function readTranscriptTitleAndStat(convId) {
  for (const appData of findAppDataDirs()) {
    const p = join(appData, 'brain', convId, '.system_generated', 'logs', 'transcript.jsonl');
    try {
      const st = statSync(p);
      const raw = readFileSync(p, 'utf-8');
      const nl = raw.indexOf('\n');
      const firstLine = nl >= 0 ? raw.slice(0, nl) : raw;
      let title = '';
      if (firstLine.trim()) {
        try {
          const obj = JSON.parse(firstLine);
          title = extractCleanUserTitle(obj?.content || '');
        } catch {
          // Ignore malformed first line.
        }
      }
      return { path: p, mtimeMs: st.mtimeMs, size: st.size, title };
    } catch {
      // Try next dir.
    }
  }
  return { path: null, mtimeMs: 0, size: -1, title: '' };
}

function parseRpcTrajectory(convId, traj, summary, transcriptInfo) {
  const stepsRaw = Array.isArray(traj?.steps) ? traj.steps : [];
  let derivedTitle = transcriptInfo?.title || '';
  const steps = [];

  const meta = summary?.trajectoryMetadata || traj?.metadata || {};
  const parentConversationId = meta?.parentConversationId || '';
  const rootConversationId = meta?.rootConversationId || convId;
  const subagentRole = meta?.subagentSpec?.role || meta?.subagentSpec?.typeName || '';
  const isSubagent = Boolean(parentConversationId);
  const projectId = String(meta?.projectId || '');

  let workspaceName = '';
  const wsList = summary?.workspaces || meta?.workspaces || [];
  const workspaceUriSet = new Set();
  if (Array.isArray(meta?.workspaceUris)) {
    for (const u of meta.workspaceUris) {
      if (typeof u === 'string' && u) workspaceUriSet.add(u);
    }
  }
  if (Array.isArray(wsList)) {
    for (const w of wsList) {
      const u = w?.workspaceFolderAbsoluteUri;
      if (typeof u === 'string' && u) workspaceUriSet.add(u);
    }
  }
  if (Array.isArray(wsList) && wsList.length > 0) {
    workspaceName =
      wsList[0]?.repository?.computedName ||
      basename(String(wsList[0]?.workspaceFolderAbsoluteUri || '').replace(/\/+$/, '')) ||
      '';
  }
  if (!derivedTitle) {
    derivedTitle = extractCleanUserTitle(summary?.annotations?.title || summary?.summary || '');
  }

  for (let idx = 0; idx < stepsRaw.length; idx++) {
    const s = stepsRaw[idx];
    if (!derivedTitle && s?.type === 'CORTEX_STEP_TYPE_USER_INPUT') {
      const items = s?.userInput?.items;
      if (Array.isArray(items)) {
        const joined = items.map((it) => it?.text || '').join(' ');
        derivedTitle = extractCleanUserTitle(joined);
      }
      if (!derivedTitle && typeof s?.userInput?.userResponse === 'string') {
        derivedTitle = extractCleanUserTitle(s.userInput.userResponse);
      }
    }

    const usage = s?.metadata?.modelUsage;
    if (!usage && s?.type !== 'CORTEX_STEP_TYPE_PLANNER_RESPONSE') continue;
    if (!usage) continue;

    const inputTokens = toInt(usage.inputTokens);
    const cacheReadTokens = toInt(usage.cacheReadTokens || usage.cacheReadInputTokens);
    const outputTokens = toInt(usage.outputTokens);
    const thinkingTokens = toInt(usage.thinkingOutputTokens);
    const responseTokens =
      usage.responseOutputTokens !== undefined
        ? toInt(usage.responseOutputTokens)
        : Math.max(0, outputTokens - thinkingTokens);
    const totalTokens = inputTokens + cacheReadTokens + outputTokens;

    if (totalTokens === 0) continue;

    const modelId = usage.model || s?.metadata?.generatorModel || 'UNKNOWN_MODEL';
    const provider = prettifyProvider(usage.apiProvider || '');

    const createdMs = parseIsoMs(s?.metadata?.createdAt);
    let firstGenMs = parseIsoMs(s?.metadata?.viewableAt);
    const transitions = s?.metadata?.internalMetadata?.statusTransitions;
    if (!firstGenMs && Array.isArray(transitions)) {
      const genTr = transitions.find((t) => t?.updatedStatus === 'CORTEX_STEP_STATUS_GENERATING');
      if (genTr) firstGenMs = parseIsoMs(genTr.timestamp);
    }
    let finishedMs =
      parseIsoMs(s?.metadata?.finishedGeneratingAt) || parseIsoMs(s?.metadata?.completedAt);
    if (!finishedMs && Array.isArray(transitions)) {
      const doneTr = transitions.find((t) => t?.updatedStatus === 'CORTEX_STEP_STATUS_DONE');
      if (doneTr) finishedMs = parseIsoMs(doneTr.timestamp);
    }

    const thinkingMs = parseProtoDurationMs(s?.plannerResponse?.thinkingDuration);

    const e2eMs =
      createdMs !== null && finishedMs !== null && finishedMs > createdMs
        ? finishedMs - createdMs
        : null;
    const ttftMs =
      createdMs !== null && firstGenMs !== null && firstGenMs >= createdMs
        ? firstGenMs - createdMs
        : null;
    const rawDecodeMs =
      firstGenMs !== null && finishedMs !== null && finishedMs > firstGenMs
        ? finishedMs - firstGenMs
        : null;

    const bufferedDecode = rawDecodeMs !== null && rawDecodeMs < 80;
    const decodeMs = rawDecodeMs !== null && rawDecodeMs >= 80 ? rawDecodeMs : null;

    const e2eTokPerSec =
      outputTokens > 0 && e2eMs !== null && e2eMs >= 80
        ? outputTokens / (e2eMs / 1000)
        : null;
    const decodeTokPerSec =
      outputTokens > 0 && decodeMs !== null
        ? outputTokens / (decodeMs / 1000)
        : e2eTokPerSec;

    const toolCalls = Array.isArray(s?.plannerResponse?.toolCalls)
      ? s.plannerResponse.toolCalls.map((tc) => tc?.name).filter(Boolean)
      : [];

    steps.push({
      stepIndex: s?.metadata?.sourceTrajectoryStepInfo?.stepIndex ?? idx,
      createdAt: s?.metadata?.createdAt || null,
      createdMs: createdMs || 0,
      modelId,
      provider,
      inputTokens,
      cacheReadTokens,
      outputTokens,
      thinkingTokens,
      responseTokens,
      totalTokens,
      contextTokens: inputTokens + cacheReadTokens + responseTokens,
      ttftMs,
      e2eMs,
      decodeMs,
      thinkingMs,
      bufferedDecode,
      decodeTokPerSec,
      e2eTokPerSec,
      toolCalls,
    });
  }

  const createdTime = summary?.createdTime || meta?.createdAt || steps[0]?.createdAt || null;
  const lastModifiedTime =
    summary?.lastModifiedTime ||
    steps[steps.length - 1]?.createdAt ||
    (transcriptInfo?.mtimeMs ? new Date(transcriptInfo.mtimeMs).toISOString() : null);

  return {
    conversationId: convId,
    title: derivedTitle || (subagentRole ? `[子代理] ${subagentRole}` : `会话 ${convId.slice(0, 8)}`),
    status: summary?.status || 'CASCADE_RUN_STATUS_IDLE',
    createdTime,
    lastModifiedTime,
    lastModifiedMs: parseIsoMs(lastModifiedTime) || transcriptInfo?.mtimeMs || 0,
    isSubagent,
    parentConversationId,
    rootConversationId,
    subagentRole,
    workspaceName,
    projectId,
    workspaceUris: [...workspaceUriSet],
    lastUserViewTime: summary?.annotations?.lastUserViewTime || null,
    lastUserInputTime: summary?.lastUserInputTime || null,
    steps,
  };
}

function parseTranscriptFallback(convId, transcriptInfo) {
  if (!transcriptInfo?.path) return null;
  let raw = '';
  try {
    raw = readFileSync(transcriptInfo.path, 'utf-8');
  } catch {
    return null;
  }
  const lines = raw.split('\n');
  let currentModel = 'UNKNOWN_MODEL';
  let derivedTitle = transcriptInfo.title || '';
  const steps = [];
  const parsedLines = [];

  for (const line of lines) {
    if (!line.trim()) continue;
    try {
      parsedLines.push(JSON.parse(line));
    } catch {
      // Ignore partial line.
    }
  }

  for (let i = 0; i < parsedLines.length; i++) {
    const row = parsedLines[i];
    if (row?.type === 'USER_INPUT' && typeof row?.content === 'string') {
      if (!derivedTitle) derivedTitle = extractCleanUserTitle(row.content);
      const m = /changed setting `Model Selection` from [^\n]+? to ([^\n.]+)\./.exec(row.content);
      if (m) currentModel = m[1].trim();
    }
    if (row?.type !== 'PLANNER_RESPONSE') continue;

    const inputTokens = toInt(row.input_tokens);
    const cacheReadTokens = toInt(row.cache_read_tokens);
    const outputTokens = toInt(row.output_tokens);
    const thinkingTokens = toInt(row.thinking_tokens || row.thinkingOutputTokens);
    const responseTokens =
      row.response_tokens !== undefined
        ? toInt(row.response_tokens)
        : row.responseOutputTokens !== undefined
          ? toInt(row.responseOutputTokens)
          : Math.max(0, outputTokens - thinkingTokens);
    const totalTokens = inputTokens + cacheReadTokens + outputTokens;
    if (totalTokens === 0) continue;

    const createdMs = parseIsoMs(row.created_at);
    const nextMs = i + 1 < parsedLines.length ? parseIsoMs(parsedLines[i + 1]?.created_at) : null;
    const e2eMs =
      createdMs !== null && nextMs !== null && nextMs > createdMs && nextMs - createdMs < 300_000
        ? nextMs - createdMs
        : null;
    const e2eTokPerSec =
      outputTokens > 0 && e2eMs !== null && e2eMs >= 500 ? outputTokens / (e2eMs / 1000) : null;

    const toolCalls = Array.isArray(row.tool_calls)
      ? row.tool_calls.map((tc) => tc?.name).filter(Boolean)
      : [];

    steps.push({
      stepIndex: row.step_index ?? i,
      createdAt: row.created_at || null,
      createdMs: createdMs || 0,
      modelId: currentModel,
      provider: '',
      inputTokens,
      cacheReadTokens,
      outputTokens,
      thinkingTokens,
      responseTokens,
      totalTokens,
      contextTokens: inputTokens + cacheReadTokens + responseTokens,
      ttftMs: null,
      e2eMs,
      decodeMs: null,
      thinkingMs: null,
      bufferedDecode: false,
      decodeTokPerSec: e2eTokPerSec,
      e2eTokPerSec,
      toolCalls,
    });
  }

  return {
    conversationId: convId,
    title: derivedTitle || `会话 ${convId.slice(0, 8)}`,
    status: 'CASCADE_RUN_STATUS_IDLE',
    createdTime: steps[0]?.createdAt || null,
    lastModifiedTime: transcriptInfo.mtimeMs ? new Date(transcriptInfo.mtimeMs).toISOString() : null,
    lastModifiedMs: transcriptInfo.mtimeMs || 0,
    isSubagent: false,
    parentConversationId: '',
    rootConversationId: convId,
    subagentRole: '',
    workspaceName: '',
    steps,
  };
}

// ---------------------------------------------------------------------------
// Incremental trajectory store
// ---------------------------------------------------------------------------

const convCache = new Map(); // convId -> { key, record }
let hydrating = false;

function discoverBrainIds() {
  const ids = new Set();
  for (const appData of findAppDataDirs()) {
    const brainDir = join(appData, 'brain');
    try {
      for (const name of readdirSync(brainDir)) {
        if (UUID_RE.test(name)) ids.add(name);
      }
    } catch {
      // Ignore missing brain dir.
    }
  }
  return ids;
}

async function fetchAndCacheConversation(convId, summary) {
  const tInfo = readTranscriptTitleAndStat(convId);
  const cacheKey = summary
    ? `ls:${summary.stepCount || 0}:${summary.lastModifiedTime || ''}:${summary.status || ''}:${tInfo.size}`
    : `disk:${tInfo.mtimeMs}:${tInfo.size}`;

  const hit = convCache.get(convId);
  if (hit && hit.key === cacheKey) {
    return hit.record;
  }

  try {
    const res = await lsRpc('GetCascadeTrajectory', { cascadeId: convId }, 8000);
    if (res?.trajectory) {
      const record = parseRpcTrajectory(convId, res.trajectory, summary, tInfo);
      convCache.set(convId, { key: cacheKey, record });
      return record;
    }
  } catch {
    // Fallback to local transcript if RPC unavailable.
  }

  const fallback = parseTranscriptFallback(convId, tInfo);
  if (fallback) {
    convCache.set(convId, { key: cacheKey, record: fallback });
    return fallback;
  }
  return hit?.record || null;
}

async function hydrateRemainingInBackground(entries) {
  if (hydrating || entries.length === 0) return;
  hydrating = true;
  try {
    const BATCH = 4;
    for (let i = 0; i < entries.length; i += BATCH) {
      const slice = entries.slice(i, i + BATCH);
      await Promise.all(slice.map(([cid, sum]) => fetchAndCacheConversation(cid, sum)));
    }
  } finally {
    hydrating = false;
  }
}

// ---------------------------------------------------------------------------
// Aggregation math
// ---------------------------------------------------------------------------

function createBucket(modelId, label, provider = '') {
  return {
    modelId,
    label,
    provider,
    steps: 0,
    conversationSet: new Set(),
    inputTokens: 0,
    cacheReadTokens: 0,
    outputTokens: 0,
    thinkingTokens: 0,
    responseTokens: 0,
    totalTokens: 0,
    decodeWeightedOut: 0,
    decodeWeightedMs: 0,
    e2eWeightedOut: 0,
    e2eWeightedMs: 0,
    peakDecodeTokPerSec: 0,
    ttftSumMs: 0,
    ttftCount: 0,
  };
}

function addStepToBucket(bucket, step, convId) {
  bucket.steps += 1;
  if (convId) bucket.conversationSet.add(convId);
  if (!bucket.provider && step.provider) bucket.provider = step.provider;

  bucket.inputTokens += step.inputTokens;
  bucket.cacheReadTokens += step.cacheReadTokens;
  bucket.outputTokens += step.outputTokens;
  bucket.thinkingTokens += step.thinkingTokens;
  bucket.responseTokens += step.responseTokens;
  bucket.totalTokens += step.totalTokens;

  const effDecodeMs = step.decodeMs ?? (step.e2eMs !== null && step.e2eMs >= 80 ? step.e2eMs : null);
  if (step.outputTokens > 0 && effDecodeMs !== null && effDecodeMs >= 80) {
    bucket.decodeWeightedOut += step.outputTokens;
    bucket.decodeWeightedMs += effDecodeMs;
    if (step.outputTokens >= 20 && effDecodeMs >= 150) {
      const rate = step.outputTokens / (effDecodeMs / 1000);
      if (rate > bucket.peakDecodeTokPerSec) bucket.peakDecodeTokPerSec = rate;
    }
  }

  if (step.outputTokens > 0 && step.e2eMs !== null && step.e2eMs >= 80) {
    bucket.e2eWeightedOut += step.outputTokens;
    bucket.e2eWeightedMs += step.e2eMs;
  }

  if (step.ttftMs !== null && step.ttftMs >= 0 && step.ttftMs < 180_000) {
    bucket.ttftSumMs += step.ttftMs;
    bucket.ttftCount += 1;
  }
}

function finalizeBucket(bucket, grandTotalTokens) {
  const promptTotal = bucket.inputTokens + bucket.cacheReadTokens;
  const avgDecodeTokPerSec =
    bucket.decodeWeightedMs > 0
      ? bucket.decodeWeightedOut / (bucket.decodeWeightedMs / 1000)
      : null;
  const avgE2eTokPerSec =
    bucket.e2eWeightedMs > 0
      ? bucket.e2eWeightedOut / (bucket.e2eWeightedMs / 1000)
      : null;
  return {
    modelId: bucket.modelId,
    label: bucket.label,
    provider: bucket.provider,
    steps: bucket.steps,
    conversations: bucket.conversationSet.size,
    inputTokens: bucket.inputTokens,
    cacheReadTokens: bucket.cacheReadTokens,
    outputTokens: bucket.outputTokens,
    thinkingTokens: bucket.thinkingTokens,
    responseTokens: bucket.responseTokens,
    totalTokens: bucket.totalTokens,
    sharePct: grandTotalTokens > 0 ? (bucket.totalTokens / grandTotalTokens) * 100 : 0,
    cacheHitRate: promptTotal > 0 ? (bucket.cacheReadTokens / promptTotal) * 100 : 0,
    avgDecodeTokPerSec,
    peakDecodeTokPerSec: bucket.peakDecodeTokPerSec > 0 ? bucket.peakDecodeTokPerSec : avgDecodeTokPerSec,
    avgE2eTokPerSec,
    avgTtftMs: bucket.ttftCount > 0 ? bucket.ttftSumMs / bucket.ttftCount : null,
  };
}

function resolveModelLabel(modelId, labelMap) {
  return labelMap.get(modelId) || prettifyModelEnum(modelId);
}

function aggregateRecords(records, labelMap) {
  const overall = createBucket('ALL', 'All Models');
  const byModel = new Map();

  for (const rec of records) {
    for (const step of rec.steps) {
      const label = resolveModelLabel(step.modelId, labelMap);
      addStepToBucket(overall, step, rec.conversationId);
      let mb = byModel.get(step.modelId);
      if (!mb) {
        mb = createBucket(step.modelId, label, step.provider);
        byModel.set(step.modelId, mb);
      }
      addStepToBucket(mb, step, rec.conversationId);
    }
  }

  const totals = finalizeBucket(overall, overall.totalTokens);
  const models = [...byModel.values()]
    .map((b) => finalizeBucket(b, overall.totalTokens))
    .sort((a, b) => b.totalTokens - a.totalTokens);

  return { totals, models };
}

async function buildMetricsSnapshot(requestedConvId, includeSubagents) {
  const [modelState, allTrajRes] = await Promise.all([
    getUserModelState(),
    lsRpc('GetAllCascadeTrajectories', {}).catch(() => ({ trajectorySummaries: {} })),
  ]);

  const { labelMap } = modelState;
  const summaries = allTrajRes?.trajectorySummaries || {};
  const allIds = new Set([...Object.keys(summaries), ...discoverBrainIds()]);

  const priorityIds = [];
  const deferredEntries = [];

  const targetId =
    (requestedConvId && UUID_RE.test(requestedConvId) ? requestedConvId : '') ||
    (app.config.conversationId && UUID_RE.test(app.config.conversationId)
      ? app.config.conversationId
      : '');

  for (const cid of allIds) {
    const sum = summaries[cid] || null;
    const parentId = sum?.trajectoryMetadata?.parentConversationId || '';
    const rootId = sum?.trajectoryMetadata?.rootConversationId || '';
    const isPriority =
      cid === targetId ||
      (targetId && (parentId === targetId || rootId === targetId)) ||
      convCache.has(cid);

    if (isPriority) {
      priorityIds.push([cid, sum]);
    } else {
      deferredEntries.push([cid, sum]);
    }
  }

  const immediateUncached = deferredEntries.slice(0, 8);
  const backgroundUncached = deferredEntries.slice(8);

  await Promise.all([
    ...priorityIds.map(([cid, sum]) => fetchAndCacheConversation(cid, sum)),
    ...immediateUncached.map(([cid, sum]) => fetchAndCacheConversation(cid, sum)),
  ]);

  if (backgroundUncached.length > 0) {
    hydrateRemainingInBackground(backgroundUncached);
  }

  const allRecords = [...convCache.values()]
    .map((entry) => entry.record)
    .filter((r) => r && (r.steps.length > 0 || r.conversationId === targetId));

  allRecords.sort((a, b) => (b.lastModifiedMs || 0) - (a.lastModifiedMs || 0));

  const effectiveConvId =
    (targetId && allRecords.some((r) => r.conversationId === targetId) ? targetId : '') ||
    targetId ||
    allRecords.find((r) => !r.isSubagent && r.status === 'CASCADE_RUN_STATUS_RUNNING')?.conversationId ||
    allRecords.find((r) => !r.isSubagent)?.conversationId ||
    allRecords[0]?.conversationId ||
    '';

  const globalAgg = aggregateRecords(allRecords, labelMap);

  const currentRecords = allRecords.filter((r) => {
    if (!effectiveConvId) return false;
    if (r.conversationId === effectiveConvId) return true;
    if (!includeSubagents) return false;
    return (
      r.parentConversationId === effectiveConvId ||
      r.rootConversationId === effectiveConvId
    );
  });

  const primaryConv = allRecords.find((r) => r.conversationId === effectiveConvId) || null;
  const subagentCount = allRecords.filter(
    (r) =>
      effectiveConvId &&
      r.conversationId !== effectiveConvId &&
      (r.parentConversationId === effectiveConvId || r.rootConversationId === effectiveConvId)
  ).length;

  const currentAgg = aggregateRecords(currentRecords, labelMap);

  const currentSteps = [];
  for (const rec of currentRecords) {
    for (const s of rec.steps) {
      const promptTotal = s.inputTokens + s.cacheReadTokens;
      currentSteps.push({
        conversationId: rec.conversationId,
        isSubagent: rec.conversationId !== effectiveConvId,
        subagentRole: rec.subagentRole || '',
        stepIndex: s.stepIndex,
        createdAt: s.createdAt,
        createdMs: s.createdMs,
        modelId: s.modelId,
        label: resolveModelLabel(s.modelId, labelMap),
        provider: s.provider,
        inputTokens: s.inputTokens,
        cacheReadTokens: s.cacheReadTokens,
        cacheHitRate: promptTotal > 0 ? (s.cacheReadTokens / promptTotal) * 100 : 0,
        outputTokens: s.outputTokens,
        thinkingTokens: s.thinkingTokens,
        responseTokens: s.responseTokens,
        totalTokens: s.totalTokens,
        ttftMs: s.ttftMs,
        e2eMs: s.e2eMs,
        decodeMs: s.decodeMs,
        thinkingMs: s.thinkingMs,
        bufferedDecode: s.bufferedDecode,
        decodeTokPerSec: s.decodeTokPerSec,
        e2eTokPerSec: s.e2eTokPerSec,
        toolCalls: s.toolCalls,
      });
    }
  }
  currentSteps.sort((a, b) => (b.createdMs || 0) - (a.createdMs || 0) || b.stepIndex - a.stepIndex);

  const conversations = allRecords.map((r) => {
    const totalTokens = r.steps.reduce((acc, s) => acc + s.totalTokens, 0);
    const lastStep = r.steps[r.steps.length - 1];
    return {
      conversationId: r.conversationId,
      title: r.title,
      isSubagent: r.isSubagent,
      subagentRole: r.subagentRole,
      status: r.status,
      steps: r.steps.length,
      totalTokens,
      lastModifiedTime: r.lastModifiedTime,
      primaryModel: lastStep ? resolveModelLabel(lastStep.modelId, labelMap) : '—',
    };
  });

  const etag = [
    effectiveConvId,
    includeSubagents ? '1' : '0',
    backgroundUncached.length,
    allRecords.length,
    globalAgg.totals.totalTokens,
    globalAgg.totals.steps,
    currentSteps.length,
  ].join('|');

  return {
    etag,
    hydratingCount: backgroundUncached.length,
    hostConversationId: app.config.conversationId || '',
    activeConversationId: effectiveConvId,
    includeSubagents,
    conversations,
    global: globalAgg,
    current: {
      conversationId: effectiveConvId,
      title: primaryConv?.title || (effectiveConvId ? `会话 ${effectiveConvId.slice(0, 8)}` : '暂无活跃会话'),
      status: primaryConv?.status || 'CASCADE_RUN_STATUS_IDLE',
      workspaceName: primaryConv?.workspaceName || '',
      subagentCount,
      ...currentAgg,
      steps: currentSteps.slice(0, 200),
    },
  };
}

// ---------------------------------------------------------------------------
// Live Desktop HUD Snapshot Writer (updates every 2.5s for agy-hud-bar)
// ---------------------------------------------------------------------------

let hudTickBusy = false;
let lastHostFocus = { conversationId: '', updatedMs: 0 };

function readActiveSessionHook(maxAgeMs = 7_200_000) {
  for (const appData of findAppDataDirs()) {
    const p = join(appData, 'sidecar_data', 'agy-pet', 'active_session.json');
    try {
      const st = statSync(p);
      const parsed = JSON.parse(readFileSync(p, 'utf-8'));
      const cid = String(parsed?.conversationId || '').trim();
      if (!cid) continue;
      const updatedMs = Number(parsed?.updatedMs) || st.mtimeMs;
      if (Date.now() - updatedMs > maxAgeMs) continue;
      return {
        conversationId: cid,
        lastUserInput: String(parsed?.lastUserInput || ''),
        title: String(parsed?.title || ''),
        updatedMs,
      };
    } catch {
      // Ignore missing or invalid hook file.
    }
  }
  return null;
}

function focusMsForSummary(cid, summary, hook) {
  const viewMs = parseIsoMs(summary?.annotations?.lastUserViewTime) || 0;
  const inputMs = parseIsoMs(summary?.lastUserInputTime) || 0;
  const hookMs = hook && hook.conversationId === cid ? hook.updatedMs : 0;
  const hostMs = lastHostFocus.conversationId === cid ? lastHostFocus.updatedMs : 0;
  return Math.max(viewMs, inputMs, hookMs, hostMs);
}

async function updateHudLiveFile() {
  if (hudTickBusy) return;
  hudTickBusy = true;
  try {
    const [modelState, allTrajRes] = await Promise.all([
      getUserModelState(10_000),
      lsRpc('GetAllCascadeTrajectories', {}, 4000).catch(() => ({ trajectorySummaries: {} })),
    ]);

    const { labelMap, quotaMap, limitMap, selectedModelId } = modelState;
    const summaries = allTrajRes?.trajectorySummaries || {};
    const hook = readActiveSessionHook();

    // Rank main (non-subagent) conversations by focusMs desc, running status, then lastModifiedTime desc.
    const mainAll = Object.entries(summaries)
      .filter(([, s]) => !s?.trajectoryMetadata?.parentConversationId)
      .map(([cid, sum]) => ({
        cid,
        sum,
        focusMs: focusMsForSummary(cid, sum, hook),
        running: sum?.status === 'CASCADE_RUN_STATUS_RUNNING' ? 1 : 0,
        modMs: parseIsoMs(sum?.lastModifiedTime) || 0,
      }));
    const hasFocus = mainAll.some((item) => item.focusMs > 0);
    mainAll.sort((a, b) => {
      if (hasFocus && a.focusMs !== b.focusMs) return b.focusMs - a.focusMs;
      if (a.running !== b.running) return b.running - a.running;
      return b.modMs - a.modMs;
    });
    const mainCandidates = mainAll.slice(0, 8).map((item) => [item.cid, item.sum]);

    const records = (
      await Promise.all(mainCandidates.map(([cid, sum]) => fetchAndCacheConversation(cid, sum)))
    ).filter(Boolean);

    const buildConvHud = (rec) => {
      const agg = aggregateRecords([rec], labelMap).totals;
      const latest = rec.steps.length > 0 ? rec.steps[rec.steps.length - 1] : null;
      const effectiveModelId = selectedModelId || latest?.modelId || '';
      const effectiveModelLabel = effectiveModelId
        ? resolveModelLabel(effectiveModelId, labelMap)
        : '未选择模型';
      const quota = quotaMap.get(effectiveModelId) || (latest ? quotaMap.get(latest.modelId) : null) || null;

      const contextUsedTokens = latest ? (latest.contextTokens ?? latest.totalTokens) : 0;
      const isRunning = rec.status === 'CASCADE_RUN_STATUS_RUNNING';
      const contextModelId = (isRunning && latest ? latest.modelId : effectiveModelId) || '';
      const contextModelLabel = contextModelId ? resolveModelLabel(contextModelId, labelMap) : '';
      const contextLimitTokens = inferContextWindowLimit(
        contextModelId,
        contextModelLabel,
        limitMap
      );
      const contextLimitSource = limitMap?.has?.(contextModelId) ? 'ls' : 'default';
      const contextUsedPct =
        contextLimitTokens > 0 ? (contextUsedTokens / contextLimitTokens) * 100 : 0;

      const latestPromptTotal = latest ? latest.inputTokens + latest.cacheReadTokens : 0;
      const latestCacheHitPct =
        latestPromptTotal > 0 ? (latest.cacheReadTokens / latestPromptTotal) * 100 : null;

      return {
        conversationId: rec.conversationId,
        title: rec.title,
        status: rec.status,
        steps: rec.steps.length,
        lastModifiedTime: rec.lastModifiedTime,
        lastUserViewTime: rec.lastUserViewTime || null,
        lastUserInputTime: rec.lastUserInputTime || null,
        projectId: rec.projectId || '',
        workspaceUris: rec.workspaceUris || [],
        selectedModelId: effectiveModelId,
        selectedModelLabel: effectiveModelLabel,
        lastStepModelLabel: latest ? resolveModelLabel(latest.modelId, labelMap) : '',
        latestDecodeTokPerSec: latest?.decodeTokPerSec ?? null,
        latestE2eTokPerSec: latest?.e2eTokPerSec ?? null,
        latestTtftMs: latest?.ttftMs ?? null,
        avgDecodeTokPerSec: agg.avgDecodeTokPerSec,
        avgE2eTokPerSec: agg.avgE2eTokPerSec,
        quotaRemainingPct: quota?.remainingPct ?? null,
        quotaResetTime: quota?.resetTime ?? null,
        cacheHitRatePct: agg.cacheHitRate,
        latestCacheHitRatePct: latestCacheHitPct,
        contextUsedTokens,
        contextTokensExcludesThinking: true,
        contextLimitTokens,
        contextLimitSource,
        contextUsedPct,
        cumulativeTotalTokens: agg.totalTokens,
      };
    };

    const convSnapList = records.map(buildConvHud);
    const maxFocusMs = mainAll.reduce((m, item) => Math.max(m, item.focusMs), 0);
    const selectedQuota = quotaMap.get(selectedModelId) || null;
    const selectedModelLabel = selectedModelId ? resolveModelLabel(selectedModelId, labelMap) : '';
    let active = convSnapList[0] || null;
    if (hook && !mainAll.some((item) => item.cid === hook.conversationId) && hook.updatedMs > maxFocusMs) {
      const hookLimit = inferContextWindowLimit(selectedModelId, selectedModelLabel, limitMap);
      active = {
        conversationId: hook.conversationId,
        title: extractCleanUserTitle(hook.lastUserInput || hook.title || '') || '新对话',
        status: 'CASCADE_RUN_STATUS_IDLE',
        steps: 0,
        lastModifiedTime: new Date(hook.updatedMs).toISOString(),
        selectedModelId,
        selectedModelLabel: selectedModelLabel || '未选择模型',
        lastStepModelLabel: '',
        latestDecodeTokPerSec: null,
        latestE2eTokPerSec: null,
        latestTtftMs: null,
        avgDecodeTokPerSec: null,
        avgE2eTokPerSec: null,
        quotaRemainingPct: selectedQuota?.remainingPct ?? null,
        quotaResetTime: selectedQuota?.resetTime ?? null,
        cacheHitRatePct: 0,
        latestCacheHitRatePct: null,
        contextUsedTokens: 0,
        contextTokensExcludesThinking: true,
        contextLimitTokens: hookLimit,
        contextLimitSource: limitMap?.has?.(selectedModelId) ? 'ls' : 'default',
        contextUsedPct: 0,
        cumulativeTotalTokens: 0,
      };
    }
    const quotaSummary = await getQuotaSummary();

    const payload = {
      updatedAt: new Date().toISOString(),
      updatedMs: Date.now(),
      selectedModelId,
      selectedModelLabel,
      selectedQuotaRemainingPct: selectedQuota?.remainingPct ?? null,
      selectedQuotaResetTime: selectedQuota?.resetTime ?? null,
      quotaBuckets: quotaSummary.buckets,
      quotaSummaryStatus: quotaSummary.status,
      activeConversationId: active?.conversationId || '',
      active,
      conversations: convSnapList,
    };

    const dataDir = resolveHudDataDir();
    mkdirSync(dataDir, { recursive: true });
    const tmpFile = join(dataDir, 'hud_live.json.tmp');
    const dstFile = join(dataDir, 'hud_live.json');
    writeFileSync(tmpFile, JSON.stringify(payload), 'utf-8');
    renameSync(tmpFile, dstFile);
  } catch {
    // Non-fatal background snapshot error.
  } finally {
    hudTickBusy = false;
  }
}

updateHudLiveFile();
setInterval(updateHudLiveFile, 2500).unref();

// ---------------------------------------------------------------------------
// Static & JSON Routes
// ---------------------------------------------------------------------------

app.page('/', () => readFileSync(join(__dirname, 'index.html'), 'utf-8'));
app.page('/styles.css', () =>
  new Response(readFileSync(join(__dirname, 'styles.css'), 'utf-8'), {
    contentType: 'text/css; charset=utf-8',
  })
);
app.page('/app.js', () =>
  new Response(readFileSync(join(__dirname, 'app.js'), 'utf-8'), {
    contentType: 'application/javascript; charset=utf-8',
  })
);

app.api(
  '/api/metrics',
  async (data) => {
    const convId = typeof data.conversationId === 'string' ? data.conversationId : '';
    const hostConvId = typeof data.hostConvId === 'string' ? data.hostConvId : '';
    if (hostConvId && UUID_RE.test(hostConvId) && hostConvId !== lastHostFocus.conversationId) {
      lastHostFocus = { conversationId: hostConvId, updatedMs: Date.now() };
    }
    const includeSubagents = data.includeSubagents !== '0' && data.includeSubagents !== 'false';
    const snap = await buildMetricsSnapshot(convId, includeSubagents);
    if (data.etag && data.etag === snap.etag) {
      return { unchanged: true, etag: snap.etag, hydratingCount: snap.hydratingCount };
    }
    return snap;
  },
  'GET'
);

await app.run();
