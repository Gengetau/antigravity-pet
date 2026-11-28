import assert from 'node:assert/strict';
import { mkdtempSync, readFileSync, rmSync, writeFileSync } from 'node:fs';
import { tmpdir } from 'node:os';
import { join, resolve } from 'node:path';
import test from 'node:test';

import {
  cleanMilestoneText,
  extractMilestoneFromRpcSteps,
  extractMilestoneFromTranscriptRecords,
  readLatestMilestoneFromTranscript,
} from '../sidecars/pet-bridge/milestone.mjs';

const PET_ROOT = resolve(import.meta.dirname, '..');

test('cleanMilestoneText strips Markdown links, code fences, and secret patterns', () => {
  const fakeSk = ['sk', 'proj', 'AbCdEfGhIjKlMnOpQrSt'].join('-');
  const fakeGh = ['ghp', '1234567890abcdef12345678'].join('_');
  const raw = [
    '### 第 1 阶段完成',
    '已更新 [milestone.mjs](file:///d:/agy-pet/sidecars/pet-bridge/milestone.mjs) 并完成 **脱敏校验**。',
    '```js\nconst secret = 123;\n```',
    `- 验证通过，不包含 ${fakeSk} ${fakeGh} Bearer tok_abcdef123456 API_KEY=mysecret888 https://internal.invalid/x`,
  ].join('\n');

  const cleaned = cleanMilestoneText(raw);
  assert.match(cleaned, /milestone\.mjs/);
  assert.match(cleaned, /脱敏校验/);
  assert.doesNotMatch(cleaned, /file:\/\/\//);
  assert.doesNotMatch(cleaned, /const secret/);
  assert.ok(!cleaned.includes(fakeSk));
  assert.ok(!cleaned.includes(fakeGh));
  assert.doesNotMatch(cleaned, /tok_abcdef123456/);
  assert.doesNotMatch(cleaned, /mysecret888/);
  assert.doesNotMatch(cleaned, /internal\.invalid/);
  assert.equal(cleanMilestoneText('OK'), '');
  assert.equal(cleanMilestoneText('好的！'), '');
});

test('extractMilestoneFromTranscriptRecords merges same-step update_steps with prose and isolates turns', () => {
  const records = [
    { step_index: 1, type: 'USER_INPUT', content: 'old turn' },
    { step_index: 2, type: 'PLANNER_RESPONSE', content: '上一回合旧成果' },
    { step_index: 10, type: 'USER_INPUT', content: 'new turn' },
    {
      step_index: 11,
      type: 'PLANNER_RESPONSE',
      created_at: '2026-11-28T05:00:05Z',
      tool_calls: [
        {
          name: 'update_steps',
          args: {
            steps: JSON.stringify([
              { title: 'Step A', status: 'in_progress' },
              { title: 'Step B', status: 'pending' },
            ]),
          },
        },
      ],
    },
  ];
  assert.equal(extractMilestoneFromTranscriptRecords('c1', records, { isRunning: true }), null);

  records.push({
    step_index: 12,
    type: 'PLANNER_RESPONSE',
    created_at: '2026-11-28T05:00:20Z',
    content: '已完成 Step A，接下来实现 Step B。',
    tool_calls: [
      {
        name: 'update_steps',
        args: {
          steps: JSON.stringify([
            { title: 'Step A', status: 'done' },
            { title: 'Step B', status: 'in_progress' },
          ]),
        },
      },
    ],
  });
  const ev = extractMilestoneFromTranscriptRecords('c1', records, { isRunning: true });
  assert.ok(ev);
  assert.equal(ev.kind, 'progress');
  assert.equal(ev.title, 'Step A');
  assert.equal(ev.stepDone, 1);
  assert.equal(ev.stepTotal, 2);
  assert.equal(ev.nextStep, 'Step B');
  assert.match(ev.body, /已完成 Step A/);
});

test('extractMilestoneFromRpcSteps and tail transcript reader work reliably', () => {
  const rpcSteps = [
    { type: 'CORTEX_STEP_TYPE_USER_INPUT', userInput: { items: [{ text: 'hello' }] } },
    {
      type: 'CORTEX_STEP_TYPE_PLANNER_RESPONSE',
      metadata: { finishedGeneratingAt: '2026-11-28T05:05:00Z' },
      plannerResponse: {
        response: '全部测试通过，准备收尾汇总。',
        toolCalls: [],
      },
    },
  ];
  const rpcEv = extractMilestoneFromRpcSteps('c2', rpcSteps, { isRunning: false });
  assert.ok(rpcEv);
  assert.equal(rpcEv.kind, 'summary');
  assert.match(rpcEv.body, /全部测试通过/);

  const dir = mkdtempSync(join(tmpdir(), 'agy-ms-node-'));
  try {
    const p = join(dir, 'transcript.jsonl');
    const filler = JSON.stringify({ step_index: 0, type: 'GENERIC', content: 'z'.repeat(2000) });
    const tail = JSON.stringify({
      step_index: 88,
      type: 'PLANNER_RESPONSE',
      created_at: '2026-11-28T05:06:00Z',
      content: 'Node 尾读测试成功提取最新阶段播报。',
    });
    writeFileSync(p, `${Array(100).fill(filler).join('\n')}\n${tail}\n`, 'utf-8');
    const diskEv = readLatestMilestoneFromTranscript('c3', p, { isRunning: false, tailBytes: 16384 });
    assert.ok(diskEv);
    assert.equal(diskEv.kind, 'summary');
    assert.match(diskEv.body, /Node 尾读测试成功/);
  } finally {
    rmSync(dir, { recursive: true, force: true });
  }
});

test('sidecar index.html, app.js, and main.mjs wire progress_bubbles and auto-sync milestone.mjs', () => {
  const html = readFileSync(join(PET_ROOT, 'sidecars', 'pet-bridge', 'index.html'), 'utf-8');
  const js = readFileSync(join(PET_ROOT, 'sidecars', 'pet-bridge', 'app.js'), 'utf-8');
  const mainJs = readFileSync(join(PET_ROOT, 'sidecars', 'pet-bridge', 'main.mjs'), 'utf-8');
  assert.match(html, /id="chk-progress-bubbles"/);
  assert.match(html, /data-i18n="optProgressBubbles"/);
  const matches = js.match(/optProgressBubbles\s*:/g) || [];
  assert.equal(matches.length, 3, 'Expected optProgressBubbles in zh, en, and ja I18N tables');
  assert.match(js, /progress_bubbles/);
  assert.match(mainJs, /'sidecars\/pet-bridge\/milestone\.mjs'/);
});
