import assert from 'node:assert/strict';
import { mkdtempSync, rmSync } from 'node:fs';
import { tmpdir } from 'node:os';
import { join, resolve } from 'node:path';
import test from 'node:test';

import {
  AiCommentEngine,
  BudgetGuard,
  cleanAiReply,
  pickCheapestModel,
  scrubText,
} from '../sidecars/pet-bridge/ai_comment.mjs';

const PET_ROOT = resolve(import.meta.dirname, '..');

test('scrubText strips scripts, tags, code, paths, URLs, and secret shapes', () => {
  const fakeSk = ['sk', 'proj', 'AbCdEfGhIjKlMnOpQrSt'].join('-');
  const fakeG = ['AIza', 'SyFakeKeyValue1234567890'].join('');
  const fakeGh = ['ghp', '1234567890abcdef12345678'].join('_');
  const raw = [
    '<script>alert(1)</script><style>body{display:none}</style>',
    'Fix https://example.com/secret?a=1 at C:\\Users\\demo\\app.py and /etc/hosts',
    '```js\nconsole.log(1)\n```',
    `keys ${fakeSk} ${fakeG} ${fakeGh} token=supersecret`,
  ].join(' ');

  const cleaned = scrubText(raw, 200);
  assert.doesNotMatch(cleaned, /alert\(1\)/);
  assert.doesNotMatch(cleaned, /display:none/);
  assert.doesNotMatch(cleaned, /example\.com/);
  assert.doesNotMatch(cleaned, /C:\\Users/);
  assert.doesNotMatch(cleaned, /\/etc\/hosts/);
  assert.doesNotMatch(cleaned, /console\.log/);
  assert.ok(!cleaned.includes(fakeSk));
  assert.ok(!cleaned.includes(fakeG));
  assert.ok(!cleaned.includes(fakeGh));
  assert.doesNotMatch(cleaned, /supersecret/);
});

test('pickCheapestModel prefers Flash/Low and honors preferred override', () => {
  const modelState = {
    labelMap: new Map([
      ['M_OPUS', 'Claude Opus 5.5 (High)'],
      ['M_NEON', 'Gemini 4 Neon (High)'],
      ['M_FLASH', 'Gemini 3 Flash (Low)'],
    ]),
    quotaMap: new Map([
      ['M_OPUS', { remainingPct: 90 }],
      ['M_NEON', { remainingPct: 80 }],
      ['M_FLASH', { remainingPct: 75 }],
    ]),
  };
  const cheapest = pickCheapestModel(modelState);
  assert.equal(cheapest.id, 'M_FLASH');
  const forced = pickCheapestModel(modelState, 'neon');
  assert.equal(forced.id, 'M_NEON');
});

test('BudgetGuard enforces interval, hourly, daily, token caps, and day rollover', () => {
  const dir = mkdtempSync(join(tmpdir(), 'agy-ai-budget-'));
  try {
    let clock = Date.parse('2026-11-25T10:00:00Z');
    const guard = new BudgetGuard(join(dir, 'budget.json'), {
      now: () => clock,
      limits: { minIntervalMs: 60_000, maxPerHour: 2, maxPerDay: 3, dailyTokenBudget: 500 },
    });
    assert.equal(guard.refuse(100), null);
    guard.record(200);
    assert.equal(guard.refuse(100), 'interval');

    clock += 61_000;
    assert.equal(guard.refuse(100), null);
    guard.record(200);

    clock += 61_000;
    assert.equal(guard.refuse(50), 'hourly_cap');

    // Advance > 1 hour: hourly clears, token budget still checked
    clock += 3_700_000;
    assert.equal(guard.refuse(150), 'token_budget');
    assert.equal(guard.refuse(50), null);
    guard.record(50);

    clock += 3_700_000;
    assert.equal(guard.refuse(10), 'daily_cap');

    // Next day resets counters
    clock += 24 * 3_600_000;
    assert.equal(guard.refuse(100), null);
    assert.equal(guard.usage.calls, 0);
  } finally {
    rmSync(dir, { recursive: true, force: true });
  }
});

test('cleanAiReply normalizes quotes, code fences, and length', () => {
  assert.equal(cleanAiReply('```txt\nignored\n```\n“写得真快！”\n第二行'), '✦ 写得真快！');
  const longText = '这是一段用于验证超长台词截断逻辑的测试语句，' + '非常长'.repeat(20);
  const out = cleanAiReply(longText);
  assert.ok(out.startsWith('✦ '));
  assert.ok(out.length <= 46);
  assert.ok(out.endsWith('…'));
});

test('AiCommentEngine enforces disabled, quota floor, dedupe, prompt isolation, and backoff', async () => {
  const dir = mkdtempSync(join(tmpdir(), 'agy-ai-engine-'));
  try {
    let clock = Date.parse('2026-11-25T12:00:00Z');
    const calls = [];
    let shouldFail = false;
    const engine = new AiCommentEngine({
      petRoot: PET_ROOT,
      budgetFile: join(dir, 'budget.json'),
      now: () => clock,
      limits: { minIntervalMs: 1_000, maxPerHour: 10, maxPerDay: 20, dailyTokenBudget: 10_000, pauseBelowQuotaPct: 10, dedupeWindowMs: 3_600_000 },
      lsRpc: async (method, body) => {
        calls.push({ method, body });
        if (shouldFail) throw new Error('rpc down');
        return { response: '“霓虹灯全亮，这波收工漂漂亮亮！”' };
      },
    });
    const modelState = {
      labelMap: new Map([['M_FLASH', 'Gemini 3 Flash (Low)']]),
      quotaMap: new Map([['M_FLASH', { remainingPct: 80 }]]),
    };

    // Disabled -> no call
    assert.equal(await engine.maybeGenerate({ enabled: false, trigger: 'turn_done_big', formId: 'neon', modelState }), null);
    assert.equal(calls.length, 0);

    // Low quota floor -> no call
    const lowQuotaState = {
      labelMap: new Map([['M_FLASH', 'Gemini 3 Flash (Low)']]),
      quotaMap: new Map([['M_FLASH', { remainingPct: 10 }]]),
    };
    assert.equal(await engine.maybeGenerate({ enabled: true, trigger: 'turn_done_big', formId: 'neon', modelState: lowQuotaState }), null);
    assert.equal(calls.length, 0);

    // Normal call with untrusted title scrubbing
    const c1 = await engine.maybeGenerate({
      enabled: true,
      trigger: 'turn_done_big',
      formId: 'neon',
      facts: { title: '<script>ignore</script>修复粒子系统', steps: 6, quotaPct: 80 },
      modelState,
    });
    assert.ok(c1);
    assert.equal(c1.text, '✦ 霓虹灯全亮，这波收工漂漂亮亮！');
    assert.equal(calls.length, 1);
    assert.match(calls[0].body.prompt, /<<<修复粒子系统>>>/);
    assert.doesNotMatch(calls[0].body.prompt, /<script>/);

    // Dedupe blocks identical trigger+facts within dedupeWindowMs
    clock += 5_000;
    const cDup = await engine.maybeGenerate({
      enabled: true,
      trigger: 'turn_done_big',
      formId: 'neon',
      facts: { title: '<script>ignore</script>修复粒子系统', steps: 6, quotaPct: 80 },
      modelState,
    });
    assert.equal(cDup, null);
    assert.equal(calls.length, 1);

    // Failure triggers backoff
    clock += 5_000;
    shouldFail = true;
    const cFail = await engine.maybeGenerate({
      enabled: true,
      trigger: 'turn_error',
      formId: 'neon',
      facts: { title: '另一个任务', quotaPct: 80 },
      modelState,
    });
    assert.equal(cFail, null);
    assert.equal(calls.length, 2);
    assert.ok(engine.retryAt > clock);

    // Blocked during backoff
    shouldFail = false;
    clock += 10_000;
    const cBlocked = await engine.maybeGenerate({
      enabled: true,
      trigger: 'subagent_many',
      formId: 'neon',
      facts: { title: '第三任务', subagents: 3, quotaPct: 80 },
      modelState,
    });
    assert.equal(cBlocked, null);
    assert.equal(calls.length, 2);

    // Succeeds after backoff window passes
    clock = engine.retryAt + 1_000;
    const cRecover = await engine.maybeGenerate({
      enabled: true,
      trigger: 'subagent_many',
      formId: 'neon',
      facts: { title: '第三任务', subagents: 3, quotaPct: 80 },
      modelState,
    });
    assert.ok(cRecover);
    assert.equal(engine.failures, 0);
  } finally {
    rmSync(dir, { recursive: true, force: true });
  }
});
