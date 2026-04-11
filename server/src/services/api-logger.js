import path from 'node:path';
import { SESSIONS_DIR } from '../utils/paths.js';
import { readJSON, writeJSON, ensureDir, listFiles } from './storage.js';

function logsDir(sessionId) {
  return path.join(SESSIONS_DIR, sessionId, 'api-logs');
}

async function getNextIndex(sessionId) {
  const dir = logsDir(sessionId);
  await ensureDir(dir);
  const files = await listFiles(dir, '.json');
  if (files.length === 0) return 0;
  const nums = files.map(f => parseInt(f.replace('.json', ''), 10)).filter(n => !isNaN(n));
  return nums.length > 0 ? Math.max(...nums) + 1 : 0;
}

/**
 * Log the request BEFORE the API call. Returns the log index.
 */
export async function logApiRequest(sessionId, { type, model, messages, params }) {
  const idx = await getNextIndex(sessionId);

  const entry = {
    timestamp: new Date().toISOString(),
    type,
    model,
    messages,
    params,
    status: 'pending',
    response: null,
    error: null,
    durationMs: null,
  };

  await writeJSON(path.join(logsDir(sessionId), `${String(idx).padStart(4, '0')}.json`), entry);
  return idx;
}

/**
 * Update an existing log entry with the response or error.
 */
export async function logApiResult(sessionId, logIndex, { response, error, durationMs }) {
  const filePath = path.join(logsDir(sessionId), `${String(logIndex).padStart(4, '0')}.json`);
  const entry = await readJSON(filePath);
  if (!entry) return;

  entry.status = error ? 'failed' : 'success';
  entry.response = response ? {
    narrative: response.narrative?.slice(0, 500),
    thinking: response.thinking?.slice(0, 500),
    raw: response.raw?.slice(0, 1000),
  } : null;
  entry.error = error || null;
  entry.durationMs = durationMs || null;

  await writeJSON(filePath, entry);
}

/**
 * Get all API logs for a session (for the UI).
 */
export async function getApiLogs(sessionId) {
  const dir = logsDir(sessionId);
  const files = (await listFiles(dir, '.json')).sort();
  const logs = [];
  for (const file of files) {
    const entry = await readJSON(path.join(dir, file));
    if (entry) logs.push(entry);
  }
  return logs;
}
