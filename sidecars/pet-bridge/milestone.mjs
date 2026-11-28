/**
 * Extract and sanitize Antigravity agent milestone progress updates for AGY Pet.
 *
 * Mirrors `agy/milestone.py` so both the Antigravity sidecar (`pet_live.json`)
 * and standalone Python mode produce identical, secret-scrubbed milestone events
 * with zero extra LLM calls or token usage.
 */

import { createHash } from 'node:crypto';
import { closeSync, openSync, readSync, statSync } from 'node:fs';

const SCRIPT_STYLE_RE = /<(script|style)[^>]*>[\s\S]*?<\/\1\s*>/gi;
const SCRIPT_OPEN_RE = /<(script|style)[^>]*>[\s\S]*$/gi;
const CODE_FENCE_RE = /```[\s\S]*?```/g;
const CODE_FENCE_OPEN_RE = /```[\s\S]*$/g;
const MD_IMAGE_RE = /!\[[^\]]*\]\([^)]+\)/g;
const MD_LINK_RE = /\[([^\]]+)\]\(([^)]+)\)/g;
const URL_RE = /(?:https?|wss?|file|postgres(?:ql)?|mysql|mongodb(?:\+srv)?|redis|amqp):\/\/\S+/gi;
const AUTH_BEARER_RE = /\bAuthorization\s*:\s*Bearer\s+\S+/gi;
const BEARER_RE = /\bBearer\s+[A-Za-z0-9._\-+/=]{8,}/gi;
const KNOWN_SECRET_RE =
  /\b(?:sk-[A-Za-z0-9_\-]{12,}|AIza[0-9A-Za-z_\-]{16,}|gh[pousr]_[A-Za-z0-9_]{16,}|ya29\.[A-Za-z0-9_\-.]{12,}|AKIA[0-9A-Z]{16}|eyJ[A-Za-z0-9_-]{8,}\.eyJ[A-Za-z0-9_-]{8,}\.[A-Za-z0-9_-]{8,})\b/g;
const KV_SECRET_RE =
  /[A-Za-z0-9_-]*(?:api[_-]?key|token|secret|password|passwd|cookie)\s*[:=]\s*(?:"[^"]*"|'[^']*'|\S+)/gi;
const OPAQUE_BLOB_RE = /[A-Za-z0-9+/=_-]{44,}/g;
const HTML_TAG_RE = /<\/?[a-zA-Z][^>]*>/g;
const INLINE_CODE_RE = /`([^`\n]+)`/g;
const BOLD_STAR_RE = /\*\*([^*]+)\*\*/g;
const BOLD_UNDER_RE = /__([^_]+)__/g;
const HR_LINE_RE = /^\s*[-*_]{3,}\s*$/;
const TABLE_SEP_RE = /^\s*\|?(?:\s*:?-{2,}:?\s*\|)+\s*:?-{2,}:?\s*\|?\s*$/;
const HEADING_RE = /^\s*#{1,6}\s+/;
const QUOTE_RE = /^\s*>\s*/;
const BULLET_RE = /^\s*(?:[-*•]|\d+[.)])\s+/;
const TRIVIAL_RE = /^(?:ok|okay|done|yes|no|sure|好的|收到|完成|可以|はい|了解)[.。!！~～]*$/i;

function hasCjk(text) {
  for (let i = 0; i < text.length; i++) {
    const code = text.charCodeAt(i);
    if ((code >= 0x3400 && code <= 0x9fff) || (code >= 0x3040 && code <= 0x30ff)) {
      return true;
    }
  }
  return false;
}

export function scrubSensitive(input) {
  let s = String(input || '');
  s = s.replace(SCRIPT_STYLE_RE, ' ');
  s = s.replace(SCRIPT_OPEN_RE, ' ');
  s = s.replace(AUTH_BEARER_RE, '[redacted]');
  s = s.replace(BEARER_RE, '[redacted]');
  s = s.replace(KNOWN_SECRET_RE, '[redacted]');
  s = s.replace(KV_SECRET_RE, '[redacted]');
  s = s.replace(URL_RE, '');
  s = s.replace(OPAQUE_BLOB_RE, '[…]');
  return s;
}

export function cleanInlineTitle(input, maxChars = 64) {
  let s = String(input || '').replace(MD_IMAGE_RE, '');
  s = s.replace(MD_LINK_RE, '$1');
  s = scrubSensitive(s);
  s = s.replace(INLINE_CODE_RE, '$1');
  s = s.replace(BOLD_STAR_RE, '$1');
  s = s.replace(BOLD_UNDER_RE, '$1');
  s = s.replace(HTML_TAG_RE, ' ');
  s = s.replace(/\s+/g, ' ').trim();
  if (s.length > maxChars) {
    s = `${s.slice(0, Math.max(1, maxChars - 1)).trimEnd()}…`;
  }
  return s;
}

export function cleanMilestoneText(raw, { maxLines = 4, maxChars = null } = {}) {
  if (!raw || typeof raw !== 'string') return '';
  let s = raw.replace(SCRIPT_STYLE_RE, ' ');
  s = s.replace(SCRIPT_OPEN_RE, ' ');
  s = s.replace(CODE_FENCE_RE, '\n');
  s = s.replace(CODE_FENCE_OPEN_RE, '\n');
  s = s.replace(MD_IMAGE_RE, '');
  s = s.replace(MD_LINK_RE, '$1');
  s = scrubSensitive(s);

  const cleanedLines = [];
  for (const rawLine of s.split(/\r?\n/)) {
    let line = rawLine.trim();
    if (!line || HR_LINE_RE.test(line) || TABLE_SEP_RE.test(line)) continue;
    const isBullet = BULLET_RE.test(line);
    line = line.replace(HEADING_RE, '');
    line = line.replace(QUOTE_RE, '');
    if (isBullet) {
      line = `· ${line.replace(BULLET_RE, '')}`;
    }
    line = line.replace(INLINE_CODE_RE, '$1');
    line = line.replace(BOLD_STAR_RE, '$1');
    line = line.replace(BOLD_UNDER_RE, '$1');
    line = line.replace(HTML_TAG_RE, ' ');
    line = line.replace(/\s+/g, ' ').trim();
    if (!line || line === '·' || line === '-' || line === '|') continue;
    cleanedLines.push(line);
  }

  if (!cleanedLines.length) return '';
  const sample = cleanedLines.slice(0, maxLines).join(' ');
  const budget = maxChars ?? (hasCjk(sample) ? 155 : 210);

  const selected = [];
  let used = 0;
  for (const line of cleanedLines) {
    if (selected.length >= maxLines) break;
    const remaining = budget - used - (selected.length ? 1 : 0);
    if (remaining <= 12) break;
    if (line.length <= remaining) {
      selected.push(line);
      used += line.length + (selected.length > 1 ? 1 : 0);
    } else {
      const clipped = `${line.slice(0, Math.max(1, remaining - 1)).replace(/[\s,;·:：-]+$/, '')}…`;
      selected.push(clipped);
      used += clipped.length;
      break;
    }
  }

  const result = selected.join('\n').trim();
  if (result.length < 4 || TRIVIAL_RE.test(result)) return '';
  return result;
}

export function parseUpdateStepsItems(rawSteps) {
  let data = rawSteps;
  if (typeof data === 'string') {
    const trimmed = data.trim();
    if (!trimmed) return [];
    try {
      data = JSON.parse(trimmed);
    } catch {
      return [];
    }
  }
  if (data && typeof data === 'object' && !Array.isArray(data) && 'steps' in data) {
    return parseUpdateStepsItems(data.steps);
  }
  if (!Array.isArray(data)) return [];
  const items = [];
  for (const entry of data) {
    if (!entry || typeof entry !== 'object') continue;
    const title = cleanInlineTitle(entry.title || '', 64);
    const status = String(entry.status || '').trim().toLowerCase();
    if (title && status) {
      items.push({ title, status });
    }
  }
  return items;
}

function makeMilestoneId(cid, stepIndex, kind, title, body, stepDone, stepTotal) {
  const sig = `${kind}|${title}|${body}|${stepDone}/${stepTotal}`;
  const digest = createHash('sha1').update(sig, 'utf-8').digest('hex').slice(0, 8);
  const idxPart = Number.isInteger(stepIndex) && stepIndex >= 0 ? String(stepIndex) : 'x';
  return `${cid}:${idxPart}:${kind}:${digest}`;
}

function parseIsoMs(iso) {
  if (!iso || typeof iso !== 'string') return 0;
  const ms = Date.parse(iso);
  return Number.isFinite(ms) ? ms : 0;
}

function collectTurnMilestone(cid, turnEntries, isRunning) {
  let prevDone = new Set();
  let prevDoneCount = 0;
  let latest = null;
  const lastIdx = turnEntries.length - 1;

  for (let pos = 0; pos < turnEntries.length; pos++) {
    const entry = turnEntries[pos];
    const stepIndex = Number.isInteger(entry.stepIndex) ? entry.stepIndex : -1;
    const createdMs = Number(entry.createdMs || 0);
    const hasTools = Boolean(entry.hasTools);
    const stepItems = Array.isArray(entry.updateSteps) ? entry.updateSteps : [];

    let stepDoneCount = 0;
    let stepTotalCount = 0;
    let newlyDoneTitle = '';
    let nextStepTitle = '';

    if (stepItems.length > 0) {
      const doneTitles = stepItems.filter((it) => it.status === 'done').map((it) => it.title);
      const inProg = stepItems.filter((it) => it.status === 'in_progress').map((it) => it.title);
      stepTotalCount = stepItems.length;
      stepDoneCount = doneTitles.length;
      const newlyDone = doneTitles.filter((t) => !prevDone.has(t));
      if (newlyDone.length > 0 || (stepDoneCount > prevDoneCount && doneTitles.length > 0)) {
        newlyDoneTitle = newlyDone.length > 0 ? newlyDone[newlyDone.length - 1] : doneTitles[doneTitles.length - 1];
        nextStepTitle = inProg[0] || '';
      }
      prevDone = new Set(doneTitles);
      prevDoneCount = stepDoneCount;
    }

    const body = entry.text ? cleanMilestoneText(entry.text) : '';
    if (body) {
      const isInterim = hasTools || pos < lastIdx || Boolean(isRunning);
      const kind = isInterim ? 'progress' : 'summary';
      const title = newlyDoneTitle;
      const sd = newlyDoneTitle ? stepDoneCount : 0;
      const stTot = newlyDoneTitle ? stepTotalCount : 0;
      const nxt = newlyDoneTitle ? nextStepTitle : '';
      latest = {
        id: makeMilestoneId(cid, stepIndex, kind, title, body, sd, stTot),
        kind,
        title,
        body,
        createdMs,
        stepDone: sd,
        stepTotal: stTot,
        nextStep: nxt,
      };
    } else if (newlyDoneTitle) {
      latest = {
        id: makeMilestoneId(cid, stepIndex, 'step_done', newlyDoneTitle, newlyDoneTitle, stepDoneCount, stepTotalCount),
        kind: 'step_done',
        title: newlyDoneTitle,
        body: newlyDoneTitle,
        createdMs,
        stepDone: stepDoneCount,
        stepTotal: stepTotalCount,
        nextStep: nextStepTitle,
      };
    }
  }
  return latest;
}

export function extractMilestoneFromRpcSteps(cid, rawSteps, { isRunning = false, stepOffset = 0 } = {}) {
  if (!cid || !Array.isArray(rawSteps) || rawSteps.length === 0) return null;
  let start = 0;
  for (let i = rawSteps.length - 1; i >= 0; i--) {
    if (rawSteps[i]?.type === 'CORTEX_STEP_TYPE_USER_INPUT') {
      start = i + 1;
      break;
    }
  }
  const turnEntries = [];
  for (let i = start; i < rawSteps.length; i++) {
    const st = rawSteps[i];
    const pr = st?.plannerResponse;
    if (!pr || typeof pr !== 'object') continue;
    const meta = st?.metadata || {};
    const toolCalls = Array.isArray(pr.toolCalls) ? pr.toolCalls : [];
    let stepItems = [];
    for (const call of toolCalls) {
      if (call?.name === 'update_steps') {
        const parsed = parseUpdateStepsItems(call.argumentsJson ?? call.args);
        if (parsed.length > 0) stepItems = parsed;
      }
    }
    const text = String(pr.modifiedResponse || pr.response || '');
    if (!text && stepItems.length === 0) continue;
    turnEntries.push({
      stepIndex: stepOffset + i,
      createdMs: parseIsoMs(meta.finishedGeneratingAt || meta.completedAt || meta.createdAt),
      hasTools: toolCalls.length > 0,
      updateSteps: stepItems,
      text,
    });
  }
  return collectTurnMilestone(cid, turnEntries, isRunning);
}

export function extractMilestoneFromTranscriptRecords(cid, records, { isRunning = false } = {}) {
  if (!cid || !Array.isArray(records) || records.length === 0) return null;
  let start = 0;
  for (let i = records.length - 1; i >= 0; i--) {
    if (records[i]?.type === 'USER_INPUT') {
      start = i + 1;
      break;
    }
  }
  const turnEntries = [];
  for (let i = start; i < records.length; i++) {
    const rec = records[i];
    if (!rec || rec.type !== 'PLANNER_RESPONSE') continue;
    const toolCalls = Array.isArray(rec.tool_calls) ? rec.tool_calls : [];
    let stepItems = [];
    for (const call of toolCalls) {
      if (call?.name === 'update_steps') {
        const rawSteps = call.args && typeof call.args === 'object' ? call.args.steps : call.args;
        const parsed = parseUpdateStepsItems(rawSteps);
        if (parsed.length > 0) stepItems = parsed;
      }
    }
    const text = String(rec.content || '');
    if (!text && stepItems.length === 0) continue;
    const stepIndex = Number.isInteger(rec.step_index) ? rec.step_index : -1;
    turnEntries.push({
      stepIndex,
      createdMs: parseIsoMs(rec.created_at),
      hasTools: toolCalls.length > 0,
      updateSteps: stepItems,
      text,
    });
  }
  return collectTurnMilestone(cid, turnEntries, isRunning);
}

export function readLatestMilestoneFromTranscript(cid, transcriptPath, { isRunning = false, tailBytes = 196 * 1024 } = {}) {
  if (!cid || !transcriptPath) return null;
  let fd = null;
  try {
    const st = statSync(transcriptPath);
    if (st.size <= 0) return null;
    const readLen = Math.min(st.size, Math.max(8192, tailBytes));
    const buf = Buffer.alloc(readLen);
    fd = openSync(transcriptPath, 'r');
    readSync(fd, buf, 0, readLen, st.size - readLen);
    closeSync(fd);
    fd = null;
    let lines = buf.toString('utf-8').split(/\r?\n/);
    if (st.size > readLen && lines.length > 0) {
      lines = lines.slice(1);
    }
    const records = [];
    for (const line of lines) {
      const trimmed = line.trim();
      if (!trimmed) continue;
      try {
        const obj = JSON.parse(trimmed);
        if (obj && typeof obj === 'object') records.push(obj);
      } catch {
        // Ignore partial line.
      }
    }
    return extractMilestoneFromTranscriptRecords(cid, records, { isRunning });
  } catch {
    if (fd !== null) {
      try {
        closeSync(fd);
      } catch {
        // ignore
      }
    }
    return null;
  }
}
