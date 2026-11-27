/**
 * AGY 桌宠 Antigravity 插件 Sidecar 后端 (pet-bridge)
 *
 * - 通过 LanguageServerService (GetUserStatus / RetrieveUserQuotaSummary /
 *   GetAllCascadeTrajectories / GetCascadeTrajectory) 与本地焦点信号
 *   (active_session.json / annotations/*.pbtxt / projects/*.json / hostFocus)
 *   实时判定当前正在看的会话与精确上下文占用（剔除单步 thinkingOutputTokens）。
 * - 每 2 秒原子写出 <appData>/sidecar_data/agy-pet/pet-bridge/data/pet_live.json
 *   供桌面宠物读取；同时与桌宠根目录 config.json 双向热同步形态与 HUD 配置。
 */

import { execFileSync, spawn } from 'node:child_process';
import { createHash } from 'node:crypto';
import { closeSync, copyFileSync, existsSync, mkdirSync, openSync, readFileSync, readSync, readdirSync, renameSync, statSync, writeFileSync } from 'node:fs';
import { homedir } from 'node:os';
import { basename, dirname, join } from 'node:path';
import { fileURLToPath, pathToFileURL } from 'node:url';
import { AiCommentEngine, normalizeLanguageSetting, resolveAiLang } from './ai_comment.mjs';

const __dirname = dirname(fileURLToPath(import.meta.url));
const UUID_RE = /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i;

function resolvePetRoot() {
  const envRoot = process.env.AGY_PET_ROOT;
  if (envRoot && existsSync(join(envRoot, 'main.py'))) {
    return envRoot;
  }
  const bundledRoot = dirname(dirname(__dirname));
  if (existsSync(join(bundledRoot, 'main.py'))) {
    return bundledRoot;
  }
  const linkFile = join(bundledRoot, '.pet_root');
  if (existsSync(linkFile)) {
    try {
      const target = readFileSync(linkFile, 'utf-8').trim();
      if (target && existsSync(join(target, 'main.py'))) {
        return target;
      }
    } catch {
      // Ignore unreadable link file.
    }
  }
  return bundledRoot;
}

const PET_ROOT = resolvePetRoot();

const PET_FORMS = [
  { id: 'carbon', name: 'Carbon', modelFamily: 'carbon', accent: '#7dd3fc' },
  { id: 'hydergon', name: 'Hydrogen', modelFamily: 'hydrogen', accent: '#a7f3d0' },
  { id: 'neon', name: 'Neon', modelFamily: 'neon', accent: '#f0abfc' },
  { id: 'argon', name: 'Argon', modelFamily: 'argon', accent: '#c4b5fd' },
  { id: 'claude', name: 'Claude', modelFamily: 'claude', accent: '#fdba74' },
];
const VALID_FORM_IDS = new Set(PET_FORMS.map((f) => f.id));
const VALID_HUD_MODES = new Set(['attached', 'floating']);
const VALID_HUD_APPEARANCES = new Set(['dialog', 'capsule', 'seamless', 'glass']);
const VALID_LANGUAGES = new Set(['auto', 'zh', 'en', 'ja']);

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

function resolveAppDataDir() {
  return findAppDataDirs()[0] || join(homedir(), '.gemini', 'antigravity');
}

function resolvePetDataDir() {
  if (process.env.ANTIGRAVITY_EXECUTABLE_DATA_DIR) {
    return process.env.ANTIGRAVITY_EXECUTABLE_DATA_DIR;
  }
  return join(resolveAppDataDir(), 'sidecar_data', 'agy-pet', 'pet-bridge', 'data');
}

function resolveActiveSessionPath() {
  return join(resolveAppDataDir(), 'sidecar_data', 'agy-pet', 'active_session.json');
}

function resolveProjectsDir() {
  return join(dirname(resolveAppDataDir()), 'config', 'projects');
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
  process.env.ANTIGRAVITY_SIDECAR_WEB_PORT = process.env.PORT || '18921';
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
// Atomic file write & bridge settings
// ---------------------------------------------------------------------------

function atomicWriteJson(filePath, data) {
  mkdirSync(dirname(filePath), { recursive: true });
  const tmp = `${filePath}.${process.pid}.tmp`;
  const text = JSON.stringify(data, null, 2);
  let lastErr = null;
  for (let attempt = 0; attempt < 4; attempt++) {
    try {
      writeFileSync(tmp, text, 'utf-8');
      renameSync(tmp, filePath);
      return;
    } catch (err) {
      lastErr = err;
    }
  }
  if (lastErr) throw lastErr;
}

function readBridgeSettings() {
  const p = join(resolvePetDataDir(), 'bridge_settings.json');
  try {
    const raw = JSON.parse(readFileSync(p, 'utf-8'));
    return {
      autoLaunchPet: Boolean(raw?.autoLaunchPet),
      checkUpdates: raw?.checkUpdates === undefined ? true : Boolean(raw.checkUpdates),
      aiComments: Boolean(raw?.aiComments),
      aiPrivacy: raw?.aiPrivacy === 'minimal' ? 'minimal' : 'title',
    };
  } catch {
    return { autoLaunchPet: false, checkUpdates: true, aiComments: false, aiPrivacy: 'title' };
  }
}

function writeBridgeSettings(patch) {
  const current = readBridgeSettings();
  const next = {
    autoLaunchPet: patch.autoLaunchPet !== undefined ? Boolean(patch.autoLaunchPet) : current.autoLaunchPet,
    checkUpdates: patch.checkUpdates !== undefined ? Boolean(patch.checkUpdates) : current.checkUpdates,
    aiComments: patch.aiComments !== undefined ? Boolean(patch.aiComments) : current.aiComments,
    aiPrivacy: patch.aiPrivacy === 'minimal' || patch.aiPrivacy === 'title' ? patch.aiPrivacy : current.aiPrivacy,
  };
  atomicWriteJson(join(resolvePetDataDir(), 'bridge_settings.json'), next);
  return next;
}

// ---------------------------------------------------------------------------
// GitHub Repo Link, 6h Update Check (Semver + Commit SHA) & Safe One-Click Update
// ---------------------------------------------------------------------------

const GITHUB_REPO_URL = 'https://github.com/Gengetau/antigravity-pet';
const GITHUB_RAW_PLUGIN_URL = 'https://raw.githubusercontent.com/Gengetau/antigravity-pet/main/plugin.json';
const GITHUB_RELEASES_API_URL = 'https://api.github.com/repos/Gengetau/antigravity-pet/releases/latest';
const GITHUB_COMMITS_API_URL = 'https://api.github.com/repos/Gengetau/antigravity-pet/commits/main';
const UPDATE_CHECK_INTERVAL_MS = 6 * 3600 * 1000;
const GIT_SHA_RE = /^[a-f0-9]{40}$/i;

function readLocalGitHead() {
  if (!existsSync(join(PET_ROOT, '.git'))) return { sha: '', branch: '' };
  try {
    const branch = execFileSync('git', ['rev-parse', '--abbrev-ref', 'HEAD'], {
      cwd: PET_ROOT,
      encoding: 'utf-8',
      timeout: 3000,
      windowsHide: true,
    }).trim();
    const sha = execFileSync('git', ['rev-parse', 'HEAD'], {
      cwd: PET_ROOT,
      encoding: 'utf-8',
      timeout: 3000,
      windowsHide: true,
    }).trim();
    return { sha: GIT_SHA_RE.test(sha) ? sha : '', branch };
  } catch {
    return { sha: '', branch: '' };
  }
}

function isLocalAncestor(commitSha) {
  if (!GIT_SHA_RE.test(commitSha || '') || !existsSync(join(PET_ROOT, '.git'))) return false;
  try {
    execFileSync('git', ['merge-base', '--is-ancestor', commitSha, 'HEAD'], {
      cwd: PET_ROOT,
      timeout: 3000,
      stdio: 'ignore',
      windowsHide: true,
    });
    return true;
  } catch {
    return false;
  }
}

function readLocalPluginVersion() {
  for (const root of [PET_ROOT, dirname(dirname(__dirname))]) {
    try {
      const raw = JSON.parse(readFileSync(join(root, 'plugin.json'), 'utf-8'));
      if (raw?.version) return String(raw.version).replace(/^v/i, '').trim();
    } catch {
      // Try next candidate.
    }
  }
  return '0.2.0';
}

function compareSemver(a, b) {
  const parse = (v) =>
    String(v || '0')
      .replace(/^v/i, '')
      .split('.')
      .slice(0, 3)
      .map((n) => Number.parseInt(n, 10) || 0);
  const pa = parse(a);
  const pb = parse(b);
  for (let i = 0; i < 3; i++) {
    if ((pa[i] || 0) !== (pb[i] || 0)) return (pa[i] || 0) > (pb[i] || 0) ? 1 : -1;
  }
  return 0;
}

function computeHasUpdate(localVersion, latestVersion, localGit, latestSha) {
  if (latestVersion && compareSemver(latestVersion, localVersion) > 0) return true;
  if (
    localGit?.branch === 'main' &&
    localGit?.sha &&
    GIT_SHA_RE.test(latestSha || '') &&
    latestSha.toLowerCase() !== localGit.sha.toLowerCase() &&
    !isLocalAncestor(latestSha)
  ) {
    return true;
  }
  return false;
}

function readUpdateCache() {
  const p = join(resolvePetDataDir(), 'update_check.json');
  const localVersion = readLocalPluginVersion();
  const localGit = readLocalGitHead();
  try {
    const raw = JSON.parse(readFileSync(p, 'utf-8'));
    const latestVersion = String(raw?.latestVersion || '').replace(/^v/i, '').trim();
    const latestSha = GIT_SHA_RE.test(String(raw?.latestSha || '')) ? String(raw.latestSha) : '';
    const checkedMs = Number(raw?.checkedMs) || 0;
    const hasUpdate = computeHasUpdate(localVersion, latestVersion, localGit, latestSha);
    return {
      localVersion,
      latestVersion,
      localSha: localGit.sha ? localGit.sha.slice(0, 7) : '',
      latestSha: latestSha ? latestSha.slice(0, 7) : '',
      checkedMs,
      hasUpdate,
      repoUrl: GITHUB_REPO_URL,
      error: String(raw?.error || ''),
    };
  } catch {
    return {
      localVersion,
      latestVersion: '',
      localSha: localGit.sha ? localGit.sha.slice(0, 7) : '',
      latestSha: '',
      checkedMs: 0,
      hasUpdate: false,
      repoUrl: GITHUB_REPO_URL,
      error: '',
    };
  }
}

let updateCheckPromise = null;

async function maybeCheckForUpdates({ force = false } = {}) {
  const settings = readBridgeSettings();
  const cached = readUpdateCache();
  if (!settings.checkUpdates && !force) {
    return { ...cached, hasUpdate: false, checkUpdates: false };
  }
  if (!force && cached.checkedMs > 0 && Date.now() - cached.checkedMs < UPDATE_CHECK_INTERVAL_MS) {
    return { ...cached, checkUpdates: settings.checkUpdates };
  }
  if (updateCheckPromise) return await updateCheckPromise;

  updateCheckPromise = (async () => {
    const localVersion = readLocalPluginVersion();
    const localGit = readLocalGitHead();
    let latestVersion = '';
    let latestSha = '';
    let error = '';
    try {
      const res = await fetch(GITHUB_RAW_PLUGIN_URL, { signal: AbortSignal.timeout(4000) });
      if (res.ok) {
        const data = await res.json();
        if (data?.version) latestVersion = String(data.version).replace(/^v/i, '').trim();
      }
    } catch (err) {
      error = String(err?.message || 'fetch failed').slice(0, 80);
    }
    try {
      const commitRes = await fetch(GITHUB_COMMITS_API_URL, {
        headers: { Accept: 'application/vnd.github+json', 'User-Agent': 'antigravity-pet-updater' },
        signal: AbortSignal.timeout(4000),
      });
      if (commitRes.ok) {
        const commitData = await commitRes.json();
        if (GIT_SHA_RE.test(String(commitData?.sha || ''))) {
          latestSha = String(commitData.sha);
          error = '';
        }
      }
    } catch {
      // Non-fatal: fall back to semver check.
    }
    if (!latestVersion) {
      try {
        const relRes = await fetch(GITHUB_RELEASES_API_URL, {
          headers: { Accept: 'application/vnd.github+json', 'User-Agent': 'antigravity-pet-updater' },
          signal: AbortSignal.timeout(4000),
        });
        if (relRes.ok) {
          const rel = await relRes.json();
          if (rel?.tag_name) latestVersion = String(rel.tag_name).replace(/^v/i, '').trim();
          error = '';
        }
      } catch (err) {
        if (!error) error = String(err?.message || 'release fetch failed').slice(0, 80);
      }
    }
    const resolvedVersion = latestVersion || cached.latestVersion || localVersion;
    const hasUpdate = computeHasUpdate(localVersion, latestVersion, localGit, latestSha);
    const next = {
      localVersion,
      latestVersion: resolvedVersion,
      localSha: localGit.sha ? localGit.sha.slice(0, 7) : '',
      latestSha,
      checkedMs: Date.now(),
      hasUpdate,
      repoUrl: GITHUB_REPO_URL,
      error: latestVersion || latestSha ? '' : error,
    };
    try {
      atomicWriteJson(join(resolvePetDataDir(), 'update_check.json'), next);
    } catch {
      // Non-fatal.
    }
    return {
      ...next,
      latestSha: latestSha ? latestSha.slice(0, 7) : '',
      checkUpdates: settings.checkUpdates,
    };
  })();

  try {
    return await updateCheckPromise;
  } finally {
    updateCheckPromise = null;
  }
}

function openExternalRepoUrl(subpath = '') {
  const safePath = subpath === '/releases' ? '/releases' : '';
  const target = `${GITHUB_REPO_URL}${safePath}`;
  try {
    if (process.platform === 'win32') {
      const child = spawn('cmd.exe', ['/c', 'start', '', target], {
        detached: true,
        stdio: 'ignore',
        windowsHide: true,
      });
      child.unref();
    } else if (process.platform === 'darwin') {
      const child = spawn('open', [target], { detached: true, stdio: 'ignore' });
      child.unref();
    } else {
      const child = spawn('xdg-open', [target], { detached: true, stdio: 'ignore' });
      child.unref();
    }
    return true;
  } catch {
    return false;
  }
}

function syncInstalledPluginFilesFromRepo() {
  const pluginRoot = dirname(dirname(__dirname));
  if (pluginRoot === PET_ROOT) return;
  const relFiles = [
    'plugin.json',
    'hooks.json',
    'hooks/track_session.mjs',
    'skills/agy-pet/SKILL.md',
    'sidecars/pet-bridge/main.mjs',
    'sidecars/pet-bridge/ai_comment.mjs',
    'sidecars/pet-bridge/index.html',
    'sidecars/pet-bridge/app.js',
    'sidecars/pet-bridge/styles.css',
  ];
  for (const rel of relFiles) {
    const src = join(PET_ROOT, rel);
    const dst = join(pluginRoot, rel);
    if (existsSync(src)) {
      mkdirSync(dirname(dst), { recursive: true });
      copyFileSync(src, dst);
    }
  }
}

// ---------------------------------------------------------------------------
// Model metadata & quota windows
// ---------------------------------------------------------------------------

let userModelStateCache = {
  fetchedAt: 0,
  labelMap: new Map(),
  quotaMap: new Map(),
  limitMap: new Map(),
  selectedModelId: '',
  userTierName: '',
  accountId: '',
};

function hashAccountId(rawIdentity) {
  const norm = String(rawIdentity || '').trim().toLowerCase();
  if (!norm) return '';
  return `acct_${createHash('sha256').update(`agy-pet:${norm}`).digest('hex').slice(0, 12)}`;
}

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

const DEFAULT_CONTEXT_LIMIT = 524_288;
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

async function getUserModelState(maxAgeMs = 15_000) {
  const now = Date.now();
  if (now - userModelStateCache.fetchedAt < maxAgeMs && userModelStateCache.labelMap.size > 0) {
    return userModelStateCache;
  }
  try {
    const data = await lsRpc('GetUserStatus', {});
    const userStatus = data?.userStatus || {};
    const cfgData = userStatus?.cascadeModelConfigData || {};
    const configs = cfgData?.clientModelConfigs;
    const selectedModelId =
      cfgData?.defaultOverrideModelConfig?.modelOrAlias?.model ||
      cfgData?.defaultOverrideModelConfig?.modelOrAlias?.alias ||
      '';
    const userTierName = String(
      userStatus?.userTier?.name || userStatus?.planStatus?.planInfo?.planName || ''
    ).trim();
    const accountId = hashAccountId(userStatus?.email || '');

    if (Array.isArray(configs)) {
      const nextLabels = new Map(userModelStateCache.labelMap);
      const nextQuotas = new Map();
      const nextLimits = new Map();
      for (const cfg of configs) {
        const key = cfg?.modelOrAlias?.model || cfg?.modelOrAlias?.alias;
        const label = cfg?.label || cfg?.displayName;
        if (key && label) nextLabels.set(key, label);
        const limit = findContextLimit(cfg);
        if (key && limit) nextLimits.set(key, limit);
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
        userTierName: userTierName || userModelStateCache.userTierName,
        accountId: accountId || userModelStateCache.accountId,
      };
    } else if (userTierName || accountId) {
      userModelStateCache = {
        ...userModelStateCache,
        fetchedAt: now,
        userTierName: userTierName || userModelStateCache.userTierName,
        accountId: accountId || userModelStateCache.accountId,
      };
    }
  } catch {
    // Keep last known state on transient failure.
  }
  return userModelStateCache;
}

let quotaSummaryCache = { fetchedAt: 0, buckets: [], status: 'pending', method: '' };
const QUOTA_SUMMARY_METHODS = ['RetrieveUserQuotaSummary', 'GetUserQuotaSummary'];
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
    if (field && typeof field === 'object') {
      collectBuckets(field, key === 'quotaSubBuckets' ? groupName : name, out, depth + 1);
    }
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
      quotaSummaryCache = { fetchedAt: now, buckets, status: buckets.length ? 'ok' : 'empty', method };
      return quotaSummaryCache;
    } catch (err) {
      errors.push(`${method}: ${String(err?.message || 'error').slice(0, 60)}`);
    }
  }
  quotaSummaryCache = {
    fetchedAt: now,
    buckets: quotaSummaryCache.buckets,
    status: errors.join(' | ').slice(0, 200),
    method: '',
  };
  return quotaSummaryCache;
}

// ---------------------------------------------------------------------------
// Annotations, Hooks, Projects & Workspace Normalization
// ---------------------------------------------------------------------------

function normalizeWorkspace(value) {
  if (!value || typeof value !== 'string') return '';
  let text = value.trim();
  try {
    text = decodeURIComponent(text);
  } catch {
    // Keep partially encoded paths.
  }
  if (/^file:\/\/\//i.test(text)) text = text.slice(8);
  else if (/^file:\/\//i.test(text)) text = text.slice(7);
  return text.replace(/\\/g, '/').replace(/\/+$/, '').toLowerCase();
}

function decodePbtxtString(raw) {
  const bytes = [];
  for (let i = 0; i < raw.length; i++) {
    const ch = raw[i];
    if (ch === '\\' && i + 1 < raw.length) {
      const nxt = raw[i + 1];
      if (nxt === 'n') { bytes.push(10); i++; continue; }
      if (nxt === 'r') { bytes.push(13); i++; continue; }
      if (nxt === 't') { bytes.push(9); i++; continue; }
      if (nxt === '"' || nxt === "'" || nxt === '\\') { bytes.push(nxt.charCodeAt(0)); i++; continue; }
      if (nxt >= '0' && nxt <= '7') {
        let j = i + 1;
        while (j < Math.min(raw.length, i + 4) && raw[j] >= '0' && raw[j] <= '7') j++;
        bytes.push(parseInt(raw.slice(i + 1, j), 8) & 0xff);
        i = j - 1;
        continue;
      }
      if ((nxt === 'x' || nxt === 'X') && i + 3 < raw.length) {
        const hex = parseInt(raw.slice(i + 2, i + 4), 16);
        if (Number.isFinite(hex)) {
          bytes.push(hex);
          i += 3;
          continue;
        }
      }
    }
    for (const b of Buffer.from(ch, 'utf-8')) bytes.push(b);
  }
  return Buffer.from(bytes).toString('utf-8').trim();
}

const annotationCache = new Map(); // cid -> { mtimeMs, viewMs, title }

function readAnnotationPbtxt(cid) {
  if (!cid) return { viewMs: 0, title: '' };
  const p = join(resolveAppDataDir(), 'annotations', `${cid}.pbtxt`);
  try {
    const st = statSync(p);
    const hit = annotationCache.get(cid);
    if (hit && hit.mtimeMs === st.mtimeMs) {
      return { viewMs: hit.viewMs, title: hit.title };
    }
    const text = readFileSync(p, 'utf-8');
    let viewMs = 0;
    const blockMatch = /last_user_view_time\s*:\s*\{([^}]*)\}/.exec(text);
    if (blockMatch) {
      const secMatch = /\bseconds\s*:\s*(\d+)/.exec(blockMatch[1]);
      const nanosMatch = /\bnanos\s*:\s*(\d+)/.exec(blockMatch[1]);
      if (secMatch) {
        const nanos = nanosMatch ? Number(nanosMatch[1]) : 0;
        viewMs = Number(secMatch[1]) * 1000 + Math.floor(nanos / 1_000_000);
      }
    }
    const titleMatch = /(?:^|\s)title\s*:\s*"((?:[^"\\]|\\.)*)"/.exec(text);
    const title = titleMatch ? decodePbtxtString(titleMatch[1]) : '';
    annotationCache.set(cid, { mtimeMs: st.mtimeMs, viewMs, title });
    return { viewMs, title };
  } catch {
    return { viewMs: 0, title: '' };
  }
}

function readActiveSessionHook(maxAgeMs = 7_200_000) {
  const p = resolveActiveSessionPath();
  try {
    const st = statSync(p);
    const parsed = JSON.parse(readFileSync(p, 'utf-8'));
    const cid = String(parsed?.conversationId || '').trim();
    if (!cid) return null;
    const updatedMs = Number(parsed?.updatedMs) || st.mtimeMs;
    if (Date.now() - updatedMs > maxAgeMs) return null;
    return {
      conversationId: cid,
      workspacePaths: Array.isArray(parsed?.workspacePaths) ? parsed.workspacePaths : [],
      lastUserInput: String(parsed?.lastUserInput || ''),
      title: String(parsed?.title || ''),
      source: String(parsed?.source || 'hook'),
      updatedMs,
    };
  } catch {
    return null;
  }
}

function latestProjectSwitch(maxAgeMs = 7_200_000) {
  const dir = resolveProjectsDir();
  try {
    const candidates = [];
    for (const name of readdirSync(dir)) {
      if (!name.endsWith('.json')) continue;
      const full = join(dir, name);
      try {
        const st = statSync(full);
        candidates.push({ mtimeMs: st.mtimeMs, path: full, stem: name.slice(0, -5) });
      } catch {
        // Skip unreadable project file.
      }
    }
    candidates.sort((a, b) => b.mtimeMs - a.mtimeMs);
    const now = Date.now();
    for (const item of candidates) {
      if (now - item.mtimeMs > maxAgeMs) break;
      try {
        const data = JSON.parse(readFileSync(item.path, 'utf-8'));
        if (!data || typeof data !== 'object' || data.sidecar) continue;
        const resources = data?.projectResources?.resources || [];
        const workspaces = new Set(
          resources
            .map((r) => normalizeWorkspace(r?.folderUri || ''))
            .filter(Boolean)
        );
        if (workspaces.size === 0) continue;
        return {
          mtimeMs: item.mtimeMs,
          id: String(data?.id || item.stem),
          name: String(data?.name || '').trim(),
          workspaces,
        };
      } catch {
        // Skip malformed project file.
      }
    }
    return null;
  } catch {
    return null;
  }
}

// ---------------------------------------------------------------------------
// Parsing trajectories & steps
// ---------------------------------------------------------------------------

function parseIsoMs(iso) {
  if (!iso || typeof iso !== 'string') return null;
  const ms = Date.parse(iso);
  return Number.isFinite(ms) ? ms : null;
}

function toInt(v) {
  const n = Number(v || 0);
  return Number.isFinite(n) && n > 0 ? Math.round(n) : 0;
}

function extractCleanUserTitle(text) {
  if (!text || typeof text !== 'string') return '';
  const reqMatch = /<USER_REQUEST>([\s\S]*?)<\/USER_REQUEST>/i.exec(text);
  const source = reqMatch ? reqMatch[1] : text.replace(/<SYSTEM_MESSAGE>[\s\S]*?<\/SYSTEM_MESSAGE>/gi, ' ');
  const body = source
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
          // Ignore malformed line.
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
  const isSubagent = Boolean(parentConversationId);
  const projectId = String(meta?.projectId || '');

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

  for (let idx = 0; idx < stepsRaw.length; idx++) {
    const s = stepsRaw[idx];
    if (!derivedTitle && s?.type === 'CORTEX_STEP_TYPE_USER_INPUT') {
      const items = s?.userInput?.items;
      if (Array.isArray(items)) {
        derivedTitle = extractCleanUserTitle(items.map((it) => it?.text || '').join(' '));
      }
      if (!derivedTitle && typeof s?.userInput?.userResponse === 'string') {
        derivedTitle = extractCleanUserTitle(s.userInput.userResponse);
      }
    }

    const usage = s?.metadata?.modelUsage;
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

    const e2eMs = createdMs !== null && finishedMs !== null && finishedMs > createdMs ? finishedMs - createdMs : null;
    const ttftMs = createdMs !== null && firstGenMs !== null && firstGenMs >= createdMs ? firstGenMs - createdMs : null;
    const rawDecodeMs =
      firstGenMs !== null && finishedMs !== null && finishedMs > firstGenMs ? finishedMs - firstGenMs : null;
    const decodeMs = rawDecodeMs !== null && rawDecodeMs >= 80 ? rawDecodeMs : null;

    const e2eTokPerSec =
      outputTokens > 0 && e2eMs !== null && e2eMs >= 80 ? outputTokens / (e2eMs / 1000) : null;
    const decodeTokPerSec =
      outputTokens > 0 && decodeMs !== null ? outputTokens / (decodeMs / 1000) : e2eTokPerSec;
    const toolCalls = Array.isArray(s?.plannerResponse?.toolCalls)
      ? s.plannerResponse.toolCalls.map((c) => String(c?.name || '')).filter(Boolean).slice(0, 4)
      : [];

    steps.push({
      modelId,
      inputTokens,
      cacheReadTokens,
      outputTokens,
      thinkingTokens,
      responseTokens,
      totalTokens,
      contextTokens: inputTokens + cacheReadTokens + responseTokens,
      createdAt: s?.metadata?.createdAt || null,
      ttftMs,
      e2eMs,
      decodeMs,
      decodeTokPerSec,
      e2eTokPerSec,
      toolCalls,
    });
  }

  const annPb = readAnnotationPbtxt(convId);
  if (!derivedTitle) {
    derivedTitle = extractCleanUserTitle(summary?.annotations?.title || summary?.summary || annPb.title || '');
  }

  const lastModifiedTime =
    summary?.lastModifiedTime ||
    steps[steps.length - 1]?.createdAt ||
    (transcriptInfo?.mtimeMs ? new Date(transcriptInfo.mtimeMs).toISOString() : null);

  return {
    conversationId: convId,
    title: derivedTitle || `会话 ${convId.slice(0, 8)}`,
    status: summary?.status || 'CASCADE_RUN_STATUS_IDLE',
    lastModifiedTime,
    lastModifiedMs: parseIsoMs(lastModifiedTime) || transcriptInfo?.mtimeMs || 0,
    lastUserViewTime: summary?.annotations?.lastUserViewTime || null,
    lastUserViewMs: Math.max(parseIsoMs(summary?.annotations?.lastUserViewTime) || 0, annPb.viewMs),
    lastUserInputTime: summary?.lastUserInputTime || null,
    lastUserInputMs: parseIsoMs(summary?.lastUserInputTime) || 0,
    projectId,
    workspaceUris: [...workspaceUriSet],
    isSubagent,
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
  let currentModel = 'UNKNOWN_MODEL';
  let derivedTitle = transcriptInfo.title || '';
  const parsedLines = [];
  for (const line of raw.split('\n')) {
    if (!line.trim()) continue;
    try {
      parsedLines.push(JSON.parse(line));
    } catch {
      // Ignore partial line.
    }
  }
  const steps = [];
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
    steps.push({
      modelId: currentModel,
      inputTokens,
      cacheReadTokens,
      outputTokens,
      thinkingTokens,
      responseTokens,
      totalTokens,
      contextTokens: inputTokens + cacheReadTokens + responseTokens,
      createdAt: row.created_at || null,
      ttftMs: null,
      e2eMs,
      decodeMs: null,
      decodeTokPerSec: e2eTokPerSec,
      e2eTokPerSec,
    });
  }
  const annPb = readAnnotationPbtxt(convId);
  return {
    conversationId: convId,
    title: derivedTitle || annPb.title || `会话 ${convId.slice(0, 8)}`,
    status: 'CASCADE_RUN_STATUS_IDLE',
    lastModifiedTime: transcriptInfo.mtimeMs ? new Date(transcriptInfo.mtimeMs).toISOString() : null,
    lastModifiedMs: transcriptInfo.mtimeMs || 0,
    lastUserViewTime: annPb.viewMs ? new Date(annPb.viewMs).toISOString() : null,
    lastUserViewMs: annPb.viewMs,
    lastUserInputTime: null,
    lastUserInputMs: 0,
    projectId: '',
    workspaceUris: [],
    isSubagent: false,
    steps,
  };
}

const convCache = new Map();

async function fetchAndCacheConversation(convId, summary) {
  const tInfo = readTranscriptTitleAndStat(convId);
  const cacheKey = summary
    ? `ls:${summary.stepCount || 0}:${summary.lastModifiedTime || ''}:${summary.status || ''}:${tInfo.size}`
    : `disk:${tInfo.mtimeMs}:${tInfo.size}`;

  const hit = convCache.get(convId);
  if (hit && hit.key === cacheKey) {
    // Refresh view timestamp even on step cache hit so sidebar clicks are instant.
    const annPb = readAnnotationPbtxt(convId);
    const lsViewMs = parseIsoMs(summary?.annotations?.lastUserViewTime) || 0;
    hit.record.lastUserViewMs = Math.max(lsViewMs, annPb.viewMs);
    if (summary?.annotations?.lastUserViewTime) {
      hit.record.lastUserViewTime = summary.annotations.lastUserViewTime;
    }
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
    // Fallback to local transcript.
  }

  const fallback = parseTranscriptFallback(convId, tInfo);
  if (fallback) {
    convCache.set(convId, { key: cacheKey, record: fallback });
    return fallback;
  }
  return hit?.record || null;
}

// ---------------------------------------------------------------------------
// Desktop Pet State, Launch & Config Sync
// ---------------------------------------------------------------------------

function isPetRunning() {
  const recoveryPath = join(PET_ROOT, 'session_recovery.json');
  try {
    const data = JSON.parse(readFileSync(recoveryPath, 'utf-8'));
    const hb = Number(data?.last_heartbeat || 0);
    const ageSec = Date.now() / 1000 - hb;
    return {
      running: Boolean(data?.active) && ageSec >= -5 && ageSec < 45,
      version: String(data?.version || ''),
      lastHeartbeat: hb,
    };
  } catch {
    return { running: false, version: '', lastHeartbeat: 0 };
  }
}

const DEFAULT_AGY_CONFIG = {
  form: 'carbon',
  follow_model: false,
  telemetry_enabled: true,
  use_language_server: true,
  reactions: true,
  autonomy: true,
  hop_to_window: true,
  explore_windows: true,
  subagent_clones: true,
  particles: true,
  edge_dock: true,
  hud_enabled: true,
  hud_hover_only: false,
  hud_mode: 'attached',
  hud_appearance: 'dialog',
  hud_locked: false,
  hud_x: null,
  hud_y: null,
  pinned_conversation: '',
  language: 'auto',
};

function readPetConfig() {
  const cfgPath = join(PET_ROOT, 'config.json');
  try {
    const raw = JSON.parse(readFileSync(cfgPath, 'utf-8'));
    const merged = { ...DEFAULT_AGY_CONFIG, ...(raw?.agy && typeof raw.agy === 'object' ? raw.agy : {}) };
    merged.language = normalizeLanguageSetting(merged.language);
    return merged;
  } catch {
    return { ...DEFAULT_AGY_CONFIG };
  }
}

function updatePetConfig(patch) {
  const cfgPath = join(PET_ROOT, 'config.json');
  let raw = {};
  try {
    const loaded = JSON.parse(readFileSync(cfgPath, 'utf-8'));
    if (loaded && typeof loaded === 'object' && !Array.isArray(loaded)) {
      raw = loaded;
    }
  } catch {
    raw = {};
  }
  const agy = raw.agy && typeof raw.agy === 'object' && !Array.isArray(raw.agy) ? { ...raw.agy } : { ...DEFAULT_AGY_CONFIG };

  if (typeof patch.form === 'string' && VALID_FORM_IDS.has(patch.form)) {
    agy.form = patch.form;
  }
  for (const boolKey of ['follow_model', 'hud_enabled', 'hud_hover_only', 'hud_locked', 'autonomy', 'reactions', 'subagent_clones', 'particles', 'edge_dock']) {
    if (typeof patch[boolKey] === 'boolean') {
      agy[boolKey] = patch[boolKey];
    }
  }
  if (patch.hud_hover_only === true) {
    agy.hud_enabled = true;
    if (agy.hud_mode === 'floating') {
      agy.hud_mode = 'attached';
    }
  }
  if (typeof patch.hud_mode === 'string' && VALID_HUD_MODES.has(patch.hud_mode)) {
    agy.hud_mode = patch.hud_mode;
  }
  if (typeof patch.hud_appearance === 'string' && VALID_HUD_APPEARANCES.has(patch.hud_appearance)) {
    agy.hud_appearance = patch.hud_appearance;
  }
  if (typeof patch.pinned_conversation === 'string') {
    agy.pinned_conversation = patch.pinned_conversation.slice(0, 128);
  }
  if (typeof patch.language === 'string') {
    const normLang = normalizeLanguageSetting(patch.language);
    if (VALID_LANGUAGES.has(normLang)) {
      agy.language = normLang;
    }
  }

  raw.agy = agy;
  atomicWriteJson(cfgPath, raw);
  return { ...DEFAULT_AGY_CONFIG, ...agy };
}

let lastAutoLaunchAttempt = 0;

function resolveLaunchCandidates() {
  const candidates = [];
  const venvPyw = join(PET_ROOT, '.venv', 'Scripts', 'pythonw.exe');
  const venvPy = join(PET_ROOT, '.venv', 'bin', 'python');
  if (existsSync(venvPyw)) candidates.push([venvPyw, ['main.py']]);
  if (existsSync(venvPy)) candidates.push([venvPy, ['main.py']]);
  try {
    execFileSync('py', ['-3.13', '-c', 'import PySide6'], {
      windowsHide: true,
      timeout: 2500,
      stdio: 'ignore',
    });
    candidates.push(['pyw', ['-3.13', 'main.py']]);
  } catch {
    // Fall back to generic launchers when py -3.13 is unavailable.
  }
  candidates.push(['pyw', ['main.py']], ['pythonw', ['main.py']], ['python3', ['main.py']]);
  return candidates;
}

function launchPet() {
  return new Promise((resolve) => {
    const mainPy = join(PET_ROOT, 'main.py');
    if (!existsSync(mainPy)) {
      resolve({ ok: false, errorKey: 'launchMissingMain', errorParams: { path: mainPy }, error: `未找到桌宠入口文件: ${mainPy}` });
      return;
    }
    const candidates = resolveLaunchCandidates();
    const attempt = (idx) => {
      if (idx >= candidates.length) {
        resolve({ ok: false, errorKey: 'launchMissingPython', error: '未找到可用的 Python 桌宠运行环境（需 Python 3.13+ 与 PySide6）' });
        return;
      }
      const [cmd, args] = candidates[idx];
      try {
        const child = spawn(cmd, args, {
          cwd: PET_ROOT,
          detached: true,
          stdio: 'ignore',
          windowsHide: true,
        });
        let settled = false;
        child.once('error', () => {
          if (settled) return;
          settled = true;
          attempt(idx + 1);
        });
        child.once('spawn', () => {
          if (settled) return;
          settled = true;
          child.unref();
          resolve({ ok: true, command: cmd });
        });
      } catch {
        attempt(idx + 1);
      }
    };
    attempt(0);
  });
}

// ---------------------------------------------------------------------------
// Live Focus Tracking & pet_live.json Writer (every 2.0s)
// ---------------------------------------------------------------------------

let tickBusy = false;
let lastPetPayload = null;
let hostFocus = { conversationId: '', workspaceUris: [], updatedMs: 0 };
let prevActiveSignal = null;

const aiEngine = new AiCommentEngine({
  lsRpc,
  petRoot: PET_ROOT,
  budgetFile: join(resolvePetDataDir(), 'ai_budget.json'),
});

const TOOL_CATEGORY_MAP = new Map([
  ['read_file', 'reading'],
  ['view_file', 'reading'],
  ['view_file_outline', 'reading'],
  ['list_dir', 'reading'],
  ['find_by_name', 'reading'],
  ['grep_search', 'reading'],
  ['mcp_agy-fast_fast_batch_search', 'reading'],
  ['mcp_agy-fast_fast_quick_outline', 'reading'],
  ['mcp_agy-fast_fast_read_slices', 'reading'],
  ['write_file', 'writing'],
  ['write_to_file', 'writing'],
  ['edit_file', 'writing'],
  ['replace_file_content', 'writing'],
  ['multi_replace_file_content', 'writing'],
  ['mcp_agy-fast_fast_apply_edits', 'writing'],
  ['run_command', 'running'],
  ['command_status', 'running'],
  ['send_command_input', 'running'],
  ['mcp_agy-fast_fast_run_checks', 'running'],
  ['search_web', 'searching'],
  ['read_url_content', 'searching'],
  ['search_marketplace', 'searching'],
  ['generate_image', 'drawing'],
  ['invoke_subagent', 'delegating'],
  ['define_subagent', 'delegating'],
  ['manage_subagents', 'delegating'],
  ['send_message', 'delegating'],
  ['ask_question', 'asking'],
]);
const QUIET_TOOL_NAMES = new Set(['update_focus', 'update_steps', 'manage_task', 'schedule', 'list_plugin_accounts']);

function classifyToolName(name) {
  const n = String(name || '').trim().toLowerCase();
  if (!n || QUIET_TOOL_NAMES.has(n)) return '';
  const hit = TOOL_CATEGORY_MAP.get(n);
  if (hit) return hit;
  if (/image|draw|paint/.test(n)) return 'drawing';
  if (/subagent|delegate|swarm/.test(n)) return 'delegating';
  if (/ask_/.test(n)) return 'asking';
  if (/browser|web|url|fetch/.test(n)) return 'searching';
  if (/write|edit|replace|patch|create/.test(n)) return 'writing';
  if (/read|view|list|grep|find|search|glob|outline/.test(n)) return 'reading';
  return 'running';
}

function formForModelLabel(label) {
  const s = String(label || '').toLowerCase();
  if (s.includes('neon')) return 'neon';
  if (s.includes('carbon')) return 'carbon';
  if (s.includes('hydrogen') || s.includes('hydergon')) return 'hydergon';
  if (s.includes('argon')) return 'argon';
  if (s.includes('claude') || s.includes('opus') || s.includes('sonnet')) return 'claude';
  return '';
}

function formForSubagentModel(label) {
  const exact = formForModelLabel(label);
  if (exact) return exact;
  const s = String(label || '').toLowerCase();
  if (s.includes('flash') || s.includes('lite') || s.includes('mini')) return 'argon';
  if (s.includes('gpt') || s.includes('oss')) return 'carbon';
  return '';
}

const discoveredPlaceholderLabels = new Map();

function prettifyTranscriptModel(raw) {
  const s = String(raw || '').trim();
  if (!s) return '';
  const m = /^gemini-(\d+(?:\.\d+)?)-([a-z]+)(?:-tiered)?-(xhigh|high|medium|low)$/i.exec(s);
  if (m) {
    const cap = (w) => (w.toLowerCase() === 'xhigh' ? 'XHigh' : w[0].toUpperCase() + w.slice(1).toLowerCase());
    return `Gemini ${m[1]} ${cap(m[2])} (${cap(m[3])})`;
  }
  return s
    .split(/[-_]+/)
    .filter(Boolean)
    .map((part) => {
      const low = part.toLowerCase();
      if (low === 'gpt' || low === 'oss') return low.toUpperCase();
      if (low === 'xhigh') return 'XHigh';
      return part[0].toUpperCase() + part.slice(1).toLowerCase();
    })
    .join(' ');
}

function readLatestModelFromTranscript(convId) {
  if (!convId) return '';
  for (const appData of findAppDataDirs()) {
    const p = join(appData, 'brain', convId, '.system_generated', 'logs', 'transcript.jsonl');
    let fd = null;
    try {
      const st = statSync(p);
      const readLen = Math.min(st.size, 24 * 1024);
      if (readLen <= 0) continue;
      const buf = Buffer.alloc(readLen);
      fd = openSync(p, 'r');
      readSync(fd, buf, 0, readLen, st.size - readLen);
      closeSync(fd);
      fd = null;
      const lines = buf.toString('utf-8').split(/\r?\n/).reverse();
      for (const line of lines) {
        if (!line.trim()) continue;
        try {
          const obj = JSON.parse(line);
          if (typeof obj?.model === 'string' && obj.model.trim()) {
            return obj.model.trim();
          }
        } catch {
          // ignore partial leading line
        }
      }
      return '';
    } catch {
      if (fd !== null) {
        try {
          closeSync(fd);
        } catch {}
      }
    }
  }
  return '';
}

function readLatestToolFromTranscript(convId) {
  if (!convId) return { name: '', category: '' };
  for (const appData of findAppDataDirs()) {
    const p = join(appData, 'brain', convId, '.system_generated', 'logs', 'transcript.jsonl');
    let fd = null;
    try {
      const st = statSync(p);
      const readLen = Math.min(st.size, 32 * 1024);
      if (readLen <= 0) continue;
      const buf = Buffer.alloc(readLen);
      fd = openSync(p, 'r');
      readSync(fd, buf, 0, readLen, st.size - readLen);
      closeSync(fd);
      fd = null;
      const text = buf.toString('utf-8');
      const lines = text.split(/\r?\n/).reverse();
      for (const line of lines) {
        if (!line.trim()) continue;
        let obj;
        try {
          obj = JSON.parse(line);
        } catch {
          continue;
        }
        const calls = Array.isArray(obj?.tool_calls) ? obj.tool_calls : [];
        for (let i = calls.length - 1; i >= 0; i--) {
          const toolName = String(calls[i]?.name || calls[i]?.tool || '').trim();
          const cat = classifyToolName(toolName);
          if (cat) return { name: toolName, category: cat };
        }
        if (obj?.type === 'USER_INPUT') break;
      }
      return { name: '', category: '' };
    } catch {
      if (fd !== null) {
        try {
          closeSync(fd);
        } catch {}
      }
    }
  }
  return { name: '', category: '' };
}

function resolveModelLabel(modelId, labelMap, convId = '') {
  if (labelMap.has(modelId)) return labelMap.get(modelId);
  if (discoveredPlaceholderLabels.has(modelId)) return discoveredPlaceholderLabels.get(modelId);
  if (convId && (!modelId || String(modelId).startsWith('MODEL_PLACEHOLDER_'))) {
    const raw = readLatestModelFromTranscript(convId);
    if (raw) {
      const friendly = prettifyTranscriptModel(raw);
      if (friendly) {
        if (modelId) discoveredPlaceholderLabels.set(modelId, friendly);
        return friendly;
      }
    }
  }
  return prettifyModelEnum(modelId);
}

function buildConvHud(rec, modelState) {
  const { labelMap, quotaMap, limitMap, selectedModelId } = modelState;
  let inputSum = 0;
  let cacheSum = 0;
  let outputSum = 0;
  let decodeOut = 0;
  let decodeMs = 0;

  for (const s of rec.steps) {
    inputSum += s.inputTokens;
    cacheSum += s.cacheReadTokens;
    outputSum += s.outputTokens;
    const effMs = s.decodeMs ?? (s.e2eMs !== null && s.e2eMs >= 80 ? s.e2eMs : null);
    if (s.outputTokens > 0 && effMs !== null && effMs >= 80) {
      decodeOut += s.outputTokens;
      decodeMs += effMs;
    }
  }

  const latest = rec.steps.length > 0 ? rec.steps[rec.steps.length - 1] : null;
  const effectiveModelId = selectedModelId || latest?.modelId || '';
  const effectiveModelLabel = effectiveModelId ? resolveModelLabel(effectiveModelId, labelMap) : '未选择模型';
  const quota = quotaMap.get(effectiveModelId) || (latest ? quotaMap.get(latest.modelId) : null) || null;

  const contextUsedTokens = latest ? latest.contextTokens : 0;
  const isRunning = rec.status === 'CASCADE_RUN_STATUS_RUNNING';
  const contextModelId = (isRunning && latest ? latest.modelId : effectiveModelId) || '';
  const contextModelLabel = contextModelId ? resolveModelLabel(contextModelId, labelMap) : '';
  const contextLimitTokens = inferContextWindowLimit(contextModelId, contextModelLabel, limitMap);
  const contextLimitSource = limitMap?.has?.(contextModelId) ? 'ls' : 'default';
  const contextUsedPct = contextLimitTokens > 0 ? (contextUsedTokens / contextLimitTokens) * 100 : 0;

  const promptSum = inputSum + cacheSum;
  const latestPromptTotal = latest ? latest.inputTokens + latest.cacheReadTokens : 0;

  return {
    conversationId: rec.conversationId,
    title: rec.title,
    status: rec.status,
    steps: rec.steps.length,
    lastModifiedTime: rec.lastModifiedTime,
    lastUserViewTime: rec.lastUserViewTime,
    lastUserInputTime: rec.lastUserInputTime,
    projectId: rec.projectId,
    workspaceUris: rec.workspaceUris,
    selectedModelId: effectiveModelId,
    selectedModelLabel: effectiveModelLabel,
    lastStepModelLabel: latest ? resolveModelLabel(latest.modelId, labelMap) : '',
    latestDecodeTokPerSec: latest?.decodeTokPerSec ?? null,
    latestE2eTokPerSec: latest?.e2eTokPerSec ?? null,
    latestTtftMs: latest?.ttftMs ?? null,
    avgDecodeTokPerSec: decodeMs > 0 ? decodeOut / (decodeMs / 1000) : null,
    quotaRemainingPct: quota?.remainingPct ?? null,
    quotaResetTime: quota?.resetTime ?? null,
    cacheHitRatePct: promptSum > 0 ? (cacheSum / promptSum) * 100 : 0,
    latestCacheHitRatePct: latestPromptTotal > 0 ? (latest.cacheReadTokens / latestPromptTotal) * 100 : null,
    contextUsedTokens,
    contextTokensExcludesThinking: true,
    contextLimitTokens,
    contextLimitSource,
    contextUsedPct,
    cumulativeTotalTokens: inputSum + cacheSum + outputSum,
  };
}

function emptyConvHud(cid, title, modelState, focusSource) {
  const { labelMap, quotaMap, limitMap, selectedModelId } = modelState;
  const selectedModelLabel = selectedModelId ? resolveModelLabel(selectedModelId, labelMap) : '未选择模型';
  const quota = quotaMap.get(selectedModelId) || null;
  const limit = inferContextWindowLimit(selectedModelId, selectedModelLabel, limitMap);
  return {
    conversationId: cid,
    title,
    status: 'CASCADE_RUN_STATUS_IDLE',
    steps: 0,
    lastModifiedTime: new Date().toISOString(),
    selectedModelId,
    selectedModelLabel,
    lastStepModelLabel: '',
    latestDecodeTokPerSec: null,
    latestE2eTokPerSec: null,
    latestTtftMs: null,
    avgDecodeTokPerSec: null,
    quotaRemainingPct: quota?.remainingPct ?? null,
    quotaResetTime: quota?.resetTime ?? null,
    cacheHitRatePct: 0,
    latestCacheHitRatePct: null,
    contextUsedTokens: 0,
    contextTokensExcludesThinking: true,
    contextLimitTokens: limit,
    contextLimitSource: limitMap?.has?.(selectedModelId) ? 'ls' : 'default',
    contextUsedPct: 0,
    cumulativeTotalTokens: 0,
    focusSource,
  };
}

async function updatePetLiveFile() {
  if (tickBusy) return lastPetPayload;
  tickBusy = true;
  try {
    const [modelState, allTrajRes, quotaSummary] = await Promise.all([
      getUserModelState(10_000),
      lsRpc('GetAllCascadeTrajectories', {}, 4000).catch(() => ({ trajectorySummaries: {} })),
      getQuotaSummary(60_000),
    ]);

    const { labelMap, quotaMap, selectedModelId, userTierName, accountId } = modelState;
    const summaries = allTrajRes?.trajectorySummaries || {};
    const rawHook = readActiveSessionHook();
    const proj = latestProjectSwitch();

    const subParentMap = new Map();
    for (const [cid, s] of Object.entries(summaries)) {
      const parent = String(s?.trajectoryMetadata?.parentConversationId || '').trim();
      if (parent) subParentMap.set(cid, parent);
    }
    const hook =
      rawHook?.conversationId && subParentMap.has(rawHook.conversationId)
        ? { ...rawHook, conversationId: subParentMap.get(rawHook.conversationId), lastUserInput: '' }
        : rawHook;
    const effectiveHostCid =
      hostFocus.conversationId && subParentMap.has(hostFocus.conversationId)
        ? subParentMap.get(hostFocus.conversationId)
        : hostFocus.conversationId;

    const mainEntries = Object.entries(summaries).filter(
      ([, s]) => !s?.trajectoryMetadata?.parentConversationId
    );

    const scored = mainEntries.map(([cid, sum]) => {
      const annPb = readAnnotationPbtxt(cid);
      const lsViewMs = parseIsoMs(sum?.annotations?.lastUserViewTime) || 0;
      const viewMs = Math.max(lsViewMs, annPb.viewMs);
      const inputMs = parseIsoMs(sum?.lastUserInputTime) || 0;
      const hookMs = hook && hook.conversationId === cid ? hook.updatedMs : 0;
      const hostMs = effectiveHostCid === cid ? hostFocus.updatedMs : 0;
      const focusMs = Math.max(viewMs, inputMs, hookMs, hostMs);
      let focusSource = 'recent';
      if (focusMs > 0) {
        if (focusMs === hookMs) focusSource = hook?.source || 'hook';
        else if (focusMs === hostMs) focusSource = 'host';
        else if (focusMs === viewMs) focusSource = 'view';
        else if (focusMs === inputMs) focusSource = 'input';
      } else if (sum?.status === 'CASCADE_RUN_STATUS_RUNNING') {
        focusSource = 'running';
      }

      const meta = sum?.trajectoryMetadata || {};
      const wsSet = new Set();
      for (const u of meta?.workspaceUris || []) {
        const n = normalizeWorkspace(u);
        if (n) wsSet.add(n);
      }
      for (const w of sum?.workspaces || meta?.workspaces || []) {
        const n = normalizeWorkspace(w?.workspaceFolderAbsoluteUri || '');
        if (n) wsSet.add(n);
      }

      return {
        cid,
        sum,
        focusMs,
        focusSource,
        running: sum?.status === 'CASCADE_RUN_STATUS_RUNNING' ? 1 : 0,
        modMs: parseIsoMs(sum?.lastModifiedTime) || 0,
        projectId: String(meta?.projectId || ''),
        wsSet,
      };
    });

    const maxFocusMs = scored.reduce((m, item) => Math.max(m, item.focusMs), 0);
    const projMs = proj ? proj.mtimeMs : 0;
    const activeCandidateId =
      hostFocus.updatedMs >= (hook?.updatedMs || 0) && effectiveHostCid
        ? { cid: effectiveHostCid, title: '', ms: hostFocus.updatedMs, source: 'host' }
        : hook
          ? {
              cid: hook.conversationId,
              title: extractCleanUserTitle(hook.lastUserInput || hook.title || '') || '新对话',
              ms: hook.updatedMs,
              source: hook.source || 'hook',
            }
          : null;

    let emptyActive = null;
    let pool = scored;
    if (
      activeCandidateId &&
      !scored.some((item) => item.cid === activeCandidateId.cid) &&
      activeCandidateId.ms > maxFocusMs &&
      activeCandidateId.ms >= projMs - 2000
    ) {
      emptyActive = emptyConvHud(
        activeCandidateId.cid,
        activeCandidateId.title || '新对话',
        modelState,
        activeCandidateId.source
      );
    } else if (proj && projMs > maxFocusMs + 2000) {
      const matched = scored.filter(
        (item) =>
          (item.projectId && item.projectId === proj.id) ||
          [...item.wsSet].some((ws) => proj.workspaces.has(ws))
      );
      if (matched.length > 0) {
        pool = matched;
      } else if (scored.some((item) => item.projectId || item.wsSet.size > 0)) {
        const title = proj.name ? `${proj.name} · 新对话` : '新对话';
        emptyActive = emptyConvHud(`project:${proj.id}`, title, modelState, 'project_empty');
      }
    }

    const hasFocus = pool.some((item) => item.focusMs > 0);
    pool.sort((a, b) => {
      if (hasFocus && a.focusMs !== b.focusMs) return b.focusMs - a.focusMs;
      if (a.running !== b.running) return b.running - a.running;
      return b.modMs - a.modMs;
    });

    const topPool = pool.slice(0, 10);
    const records = (
      await Promise.all(topPool.map((item) => fetchAndCacheConversation(item.cid, item.sum)))
    ).filter(Boolean);

    const focusSourceById = new Map(topPool.map((item) => [item.cid, item.focusSource]));
    const summaryById = new Map(Object.entries(summaries));
    const convSnapList = records.map((rec) => {
      const snap = buildConvHud(rec, modelState);
      snap.focusSource = focusSourceById.get(rec.conversationId) || 'recent';
      const sum = summaryById.get(rec.conversationId);
      const waitingSteps = Array.isArray(sum?.waitingSteps) ? sum.waitingSteps : [];
      snap.waitingForUser = waitingSteps.length > 0;
      snap.terminationReason = String(sum?.latestExecutorTerminationReason || '').replace(
        /^EXECUTOR_TERMINATION_REASON_/,
        ''
      );
      const lastTools = rec.steps.length > 0 ? rec.steps[rec.steps.length - 1].toolCalls || [] : [];
      let toolName = '';
      let toolCat = '';
      for (let i = lastTools.length - 1; i >= 0; i--) {
        const c = classifyToolName(lastTools[i]);
        if (c) {
          toolName = lastTools[i];
          toolCat = c;
          break;
        }
      }
      if (snap.status === 'CASCADE_RUN_STATUS_RUNNING' && (!toolCat || rec.conversationId === topPool[0]?.cid)) {
        const liveTool = readLatestToolFromTranscript(rec.conversationId);
        if (liveTool.category) {
          toolName = liveTool.name;
          toolCat = liveTool.category;
        }
      }
      snap.latestToolName = toolName;
      snap.latestToolCategory = toolCat;
      return snap;
    });

    const active = emptyActive || convSnapList[0] || null;
    const selectedQuota = quotaMap.get(selectedModelId) || null;
    const selectedModelLabel = selectedModelId ? resolveModelLabel(selectedModelId, labelMap) : '';

    const runningMainCount = mainEntries.filter(([, s]) => s?.status === 'CASCADE_RUN_STATUS_RUNNING').length;
    const runningSubEntries = Object.entries(summaries)
      .filter(([, s]) => Boolean(s?.trajectoryMetadata?.parentConversationId) && s?.status === 'CASCADE_RUN_STATUS_RUNNING')
      .slice(0, 6);
    const activeSubagents = await Promise.all(
      runningSubEntries.map(async ([cid, sum]) => {
        const rec = await fetchAndCacheConversation(cid, sum).catch(() => null);
        const latestStep = rec?.steps?.length ? rec.steps[rec.steps.length - 1] : null;
        let modelLabel = latestStep?.modelId ? resolveModelLabel(latestStep.modelId, labelMap, cid) : '';
        if (!modelLabel) {
          const rawTr = readLatestModelFromTranscript(cid);
          if (rawTr) modelLabel = prettifyTranscriptModel(rawTr);
        }
        const annPb = readAnnotationPbtxt(cid);
        const annTitle = extractCleanUserTitle(sum?.annotations?.title || sum?.summary || annPb.title || '');
        const recTitle = rec?.title && !/^The following is a\b/i.test(rec.title) ? rec.title : '';
        const title = annTitle || recTitle || `子代理 ${cid.slice(0, 6)}`;
        return {
          conversationId: cid,
          parentConversationId: String(sum?.trajectoryMetadata?.parentConversationId || ''),
          title,
          modelLabel,
          formId: formForSubagentModel(modelLabel),
        };
      })
    );

    const bridge = readBridgeSettings();
    const updCache = readUpdateCache();
    if (bridge.checkUpdates && (!updCache.checkedMs || Date.now() - updCache.checkedMs >= UPDATE_CHECK_INTERVAL_MS)) {
      maybeCheckForUpdates().catch(() => {});
    }

    // Trigger optional zero-API-key AI comment only on salient transitions.
    if (active) {
      const isRunning = active.status === 'CASCADE_RUN_STATUS_RUNNING';
      const activeQuota = active.quotaRemainingPct ?? selectedQuota?.remainingPct ?? null;
      const petCfg = readPetConfig();
      const activeForm = petCfg.follow_model
        ? formForModelLabel(active.lastStepModelLabel || active.selectedModelLabel) || petCfg.form
        : petCfg.form;
      let aiTrigger = '';
      if (prevActiveSignal && prevActiveSignal.cid === active.conversationId) {
        if (prevActiveSignal.running && !isRunning) {
          if (active.terminationReason === 'ERROR') aiTrigger = 'turn_error';
          else if ((active.steps || 0) - (prevActiveSignal.steps || 0) >= 4) aiTrigger = 'turn_done_big';
        } else if (!prevActiveSignal.waiting && active.waitingForUser) {
          aiTrigger = 'waiting_user';
        } else if (activeSubagents.length >= 2 && (prevActiveSignal.subagents || 0) < 2) {
          aiTrigger = 'subagent_many';
        } else if (activeQuota !== null && prevActiveSignal.quota !== null) {
          if (activeQuota <= 10 && prevActiveSignal.quota > 10) aiTrigger = 'quota_critical';
          else if (activeQuota - prevActiveSignal.quota >= 12) aiTrigger = 'quota_refilled';
        }
      }
      prevActiveSignal = {
        cid: active.conversationId,
        running: isRunning,
        steps: active.steps || 0,
        waiting: Boolean(active.waitingForUser),
        subagents: activeSubagents.length,
        quota: activeQuota,
      };
      if (aiTrigger && bridge.aiComments) {
        aiEngine
          .maybeGenerate({
            enabled: true,
            trigger: aiTrigger,
            formId: activeForm,
            facts: {
              title: active.title,
              modelLabel: active.lastStepModelLabel || active.selectedModelLabel,
              steps: active.steps || 0,
              subagents: activeSubagents.length,
              quotaPct: activeQuota,
              toolCategory: active.latestToolCategory || '',
            },
            modelState,
            privacyLevel: bridge.aiPrivacy,
            lang: resolveAiLang(petCfg.language),
          })
          .catch(() => {});
      }
    }

    const freshAiComment =
      aiEngine.latestComment && Date.now() - aiEngine.latestComment.createdAtMs < 60_000
        ? aiEngine.latestComment
        : null;

    const payload = {
      updatedAt: new Date().toISOString(),
      updatedMs: Date.now(),
      userTierName: userTierName || '',
      accountId: accountId || '',
      availableUpdateVersion: bridge.checkUpdates && updCache.hasUpdate ? updCache.latestVersion : '',
      availableUpdateSha: bridge.checkUpdates && updCache.hasUpdate ? updCache.latestSha || '' : '',
      modelLabels: Object.fromEntries(labelMap),
      selectedModelId,
      selectedModelLabel,
      selectedQuotaRemainingPct: selectedQuota?.remainingPct ?? null,
      selectedQuotaResetTime: selectedQuota?.resetTime ?? null,
      quotaBuckets: quotaSummary.buckets,
      quotaSummaryStatus: quotaSummary.status,
      activeConversationId: active?.conversationId || '',
      focusSource: active?.focusSource || '',
      runningSessionsCount: runningMainCount,
      waitingForUser: Boolean(active?.waitingForUser),
      terminationReason: String(active?.terminationReason || ''),
      latestToolName: String(active?.latestToolName || ''),
      latestToolCategory: String(active?.latestToolCategory || ''),
      activeSubagents,
      aiComment: freshAiComment,
      active,
      conversations: convSnapList,
    };

    atomicWriteJson(join(resolvePetDataDir(), 'pet_live.json'), payload);
    lastPetPayload = payload;

    try {
      await updatePetMeterFile(summaries, modelState);
    } catch {
      // Never let meter export failure break pet_live.json updates.
    }

    if (bridge.autoLaunchPet && !isPetRunning().running && Date.now() - lastAutoLaunchAttempt > 60_000) {
      lastAutoLaunchAttempt = Date.now();
      launchPet().catch(() => {});
    }
    return payload;
  } catch {
    return lastPetPayload;
  } finally {
    tickBusy = false;
  }
}

let lastMeterWriteMs = 0;

async function updatePetMeterFile(summaries, modelState) {
  const now = Date.now();
  if (lastMeterWriteMs > 0 && now - lastMeterWriteMs < 6000) {
    return;
  }
  const allEntries = Object.entries(summaries || {}).map(([cid, sum]) => ({
    cid,
    sum,
    running: sum?.status === 'CASCADE_RUN_STATUS_RUNNING' ? 1 : 0,
    modMs: parseIsoMs(sum?.lastModifiedTime) || 0,
  }));
  allEntries.sort((a, b) => {
    if (a.running !== b.running) return b.running - a.running;
    return b.modMs - a.modMs;
  });
  const targetEntries = allEntries.slice(0, 80);
  const fetched = [];
  let cursor = 0;
  const workerCount = Math.min(6, targetEntries.length);
  await Promise.all(
    Array.from({ length: workerCount }, async () => {
      while (cursor < targetEntries.length) {
        const idx = cursor++;
        const item = targetEntries[idx];
        const rec = await fetchAndCacheConversation(item.cid, item.sum);
        if (rec) fetched.push(rec);
      }
    })
  );

  const conversations = fetched.map((rec) => ({
    conversationId: rec.conversationId,
    title: rec.title,
    status: rec.status,
    lastModifiedMs: rec.lastModifiedMs || 0,
    isSubagent: Boolean(rec.isSubagent),
    steps: (rec.steps || []).map((st) => [
      parseIsoMs(st.createdAt) || 0,
      st.modelId,
      resolveModelLabel(st.modelId, modelState.labelMap, rec.conversationId),
      st.inputTokens,
      st.cacheReadTokens,
      st.outputTokens,
      st.thinkingTokens,
      st.responseTokens,
      st.ttftMs,
      st.decodeTokPerSec,
      st.e2eTokPerSec,
      st.e2eMs,
      st.toolCalls || [],
    ]),
  }));

  const meterPayload = {
    updatedAt: new Date().toISOString(),
    updatedMs: Date.now(),
    userTierName: modelState.userTierName || '',
    accountId: modelState.accountId || '',
    modelLabels: Object.fromEntries(modelState.labelMap),
    conversations,
  };
  atomicWriteJson(join(resolvePetDataDir(), 'pet_meter.json'), meterPayload);
  lastMeterWriteMs = Date.now();
}

updatePetLiveFile();
setInterval(updatePetLiveFile, 2000).unref();

// ---------------------------------------------------------------------------
// Web UI & API Routes
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
  '/api/state',
  async () => {
    if (!lastPetPayload || Date.now() - (lastPetPayload.updatedMs || 0) > 2500) {
      await updatePetLiveFile();
    }
    const petStatus = isPetRunning();
    const bridgeSettings = readBridgeSettings();
    const updCache = readUpdateCache();
    if (bridgeSettings.checkUpdates && (!updCache.checkedMs || Date.now() - updCache.checkedMs >= UPDATE_CHECK_INTERVAL_MS)) {
      maybeCheckForUpdates().catch(() => {});
    }
    return {
      version: readLocalPluginVersion(),
      petRunning: petStatus.running,
      petStatus,
      agyConfig: readPetConfig(),
      bridgeSettings,
      aiBudgetUsage: aiEngine.budget.usage,
      updateStatus: {
        ...updCache,
        hasUpdate: Boolean(bridgeSettings.checkUpdates && updCache.hasUpdate),
      },
      forms: PET_FORMS,
      hostConversationId: app.config.conversationId || '',
      live: lastPetPayload,
    };
  },
  'GET'
);

app.api(
  '/api/host-focus',
  async (data) => {
    const cid = typeof data?.conversationId === 'string' ? data.conversationId.trim() : '';
    const uris = Array.isArray(data?.workspaceUris) ? data.workspaceUris.filter((u) => typeof u === 'string') : [];
    const initial = Boolean(data?.initial);
    if (cid && UUID_RE.test(cid) && (initial || cid !== hostFocus.conversationId)) {
      const now = Date.now();
      hostFocus = { conversationId: cid, workspaceUris: uris, updatedMs: now };
      try {
        atomicWriteJson(resolveActiveSessionPath(), {
          conversationId: cid,
          workspacePaths: uris,
          hookEventName: 'SidecarHostFocus',
          source: 'host',
          updatedMs: now,
          updatedAt: new Date(now).toISOString(),
        });
      } catch {
        // Non-fatal.
      }
      await updatePetLiveFile();
    }
    return { ok: true, hostFocus };
  },
  'POST'
);

app.api(
  '/api/pet/launch',
  async () => {
    const res = await launchPet();
    return { ...res, petStatus: isPetRunning() };
  },
  'POST'
);

app.api(
  '/api/pet/config',
  async (data) => {
    const patch = data && typeof data === 'object' ? data : {};
    const agyConfig = updatePetConfig(patch);
    const bridgePatch = {};
    if (typeof patch.autoLaunchPet === 'boolean') bridgePatch.autoLaunchPet = patch.autoLaunchPet;
    if (typeof patch.checkUpdates === 'boolean') bridgePatch.checkUpdates = patch.checkUpdates;
    if (typeof patch.aiComments === 'boolean') bridgePatch.aiComments = patch.aiComments;
    if (patch.aiPrivacy === 'minimal' || patch.aiPrivacy === 'title') bridgePatch.aiPrivacy = patch.aiPrivacy;
    const bridgeSettings = Object.keys(bridgePatch).length > 0 ? writeBridgeSettings(bridgePatch) : readBridgeSettings();
    if (patch.checkUpdates === true) {
      maybeCheckForUpdates().catch(() => {});
    }
    return { ok: true, agyConfig, bridgeSettings };
  },
  'POST'
);

app.api(
  '/api/open-github',
  async () => {
    const ok = openExternalRepoUrl('');
    return { ok, url: GITHUB_REPO_URL };
  },
  'POST'
);

app.api(
  '/api/pet/check-update',
  async () => {
    const updateStatus = await maybeCheckForUpdates({ force: true });
    return { ok: true, updateStatus };
  },
  'POST'
);

app.api(
  '/api/pet/update',
  async () => {
    if (!existsSync(join(PET_ROOT, '.git'))) {
      openExternalRepoUrl('/releases');
      return { ok: false, openedBrowser: true, messageKey: 'updNotGit', message: '当前目录非 Git 仓库，已打开 GitHub 页面手动下载' };
    }
    try {
      const dirtyOut = execFileSync('git', ['status', '--porcelain', '--untracked-files=no'], {
        cwd: PET_ROOT,
        encoding: 'utf-8',
        timeout: 5000,
      }).trim();
      if (dirtyOut) {
        openExternalRepoUrl('');
        return { ok: false, dirty: true, openedBrowser: true, messageKey: 'updDirty', message: '本地有未提交改动，为保护代码未覆盖，已打开 GitHub 页面' };
      }
      const branch = execFileSync('git', ['rev-parse', '--abbrev-ref', 'HEAD'], {
        cwd: PET_ROOT,
        encoding: 'utf-8',
        timeout: 5000,
      }).trim();
      if (branch !== 'main') {
        return { ok: false, branch, messageKey: 'updWrongBranch', messageParams: { branch }, message: `当前处于分支 ${branch}，请切回 main 后再一键更新` };
      }
      execFileSync('git', ['pull', '--ff-only', 'origin', 'main'], {
        cwd: PET_ROOT,
        encoding: 'utf-8',
        timeout: 25000,
      });
      syncInstalledPluginFilesFromRepo();
      const newVer = readLocalPluginVersion();
      const newGit = readLocalGitHead();
      atomicWriteJson(join(resolvePetDataDir(), 'update_check.json'), {
        localVersion: newVer,
        latestVersion: newVer,
        localSha: newGit.sha ? newGit.sha.slice(0, 7) : '',
        latestSha: newGit.sha || '',
        checkedMs: Date.now(),
        hasUpdate: false,
        repoUrl: GITHUB_REPO_URL,
        error: '',
      });
      return { ok: true, version: newVer, messageKey: 'updSuccess', messageParams: { version: newVer }, message: `已拉取 v${newVer}，重开桌宠并开关一次插件即可生效` };
    } catch (err) {
      openExternalRepoUrl('/releases');
      const detail = String(err?.message || 'git error').slice(0, 60);
      return {
        ok: false,
        openedBrowser: true,
        messageKey: 'updFailed',
        messageParams: { detail },
        message: `自动更新失败（${detail}），已打开 GitHub 页面`,
      };
    }
  },
  'POST'
);

await app.run();
