/**
 * Antigravity lifecycle hook handler (SessionStart / PreInvocation).
 *
 * Records the active conversationId and workspace paths into
 * <appData>/sidecar_data/agy-pet/active_session.json so the desktop pet
 * immediately tracks newly created or just-submitted conversations.
 * Always writes `{}` to stdout and exits 0 so it never blocks the agent loop.
 */

import { existsSync, mkdirSync, renameSync, writeFileSync } from 'node:fs';
import { homedir } from 'node:os';
import { basename, dirname, join } from 'node:path';

function readStdin() {
  return new Promise((resolve) => {
    let raw = '';
    process.stdin.setEncoding('utf8');
    process.stdin.on('data', (chunk) => {
      raw += chunk;
    });
    process.stdin.on('end', () => resolve(raw));
    process.stdin.on('error', () => resolve(raw));
  });
}

function walkUpToParent(startPath, markerDirName) {
  if (!startPath || typeof startPath !== 'string') return '';
  let cur = startPath;
  for (let i = 0; i < 10; i++) {
    const parent = dirname(cur);
    if (basename(cur) === markerDirName && existsSync(parent)) {
      return parent;
    }
    if (parent === cur) break;
    cur = parent;
  }
  return '';
}

function resolveAppDataDir(payload) {
  if (process.env.ANTIGRAVITY_APP_DATA_DIR) {
    return process.env.ANTIGRAVITY_APP_DATA_DIR;
  }
  const fromExec = walkUpToParent(process.env.ANTIGRAVITY_EXECUTABLE_DATA_DIR, 'sidecar_data');
  if (fromExec) return fromExec;
  const fromPlugin = walkUpToParent(process.env.PLUGIN_DATA, 'plugin_data');
  if (fromPlugin) return fromPlugin;
  const fromArtifact = walkUpToParent(payload?.artifactDirectoryPath, 'brain');
  if (fromArtifact) return fromArtifact;
  const fromTranscript = walkUpToParent(payload?.transcriptPath, 'brain');
  if (fromTranscript) return fromTranscript;
  return join(homedir(), '.gemini', 'antigravity');
}

async function main() {
  try {
    const raw = await readStdin();
    const payload = raw.trim() ? JSON.parse(raw) : {};
    const conversationId = String(payload?.conversationId || '').trim();
    if (conversationId) {
      const appData = resolveAppDataDir(payload);
      const outDir = join(appData, 'sidecar_data', 'agy-pet');
      mkdirSync(outDir, { recursive: true });
      const record = {
        conversationId,
        workspacePaths: Array.isArray(payload?.workspacePaths) ? payload.workspacePaths : [],
        modelName: String(payload?.modelName || ''),
        lastUserInput: String(payload?.lastUserInput || '').slice(0, 300),
        hookEventName: String(payload?.hookEventName || ''),
        source: 'hook',
        updatedMs: Date.now(),
        updatedAt: new Date().toISOString(),
      };
      const tmp = join(outDir, `active_session.${process.pid}.tmp`);
      const dst = join(outDir, 'active_session.json');
      writeFileSync(tmp, JSON.stringify(record), 'utf8');
      renameSync(tmp, dst);
    }
  } catch {
    // Hook must stay completely non-blocking on malformed stdin or disk issues.
  }
  process.stdout.write('{}\n');
}

await main();
