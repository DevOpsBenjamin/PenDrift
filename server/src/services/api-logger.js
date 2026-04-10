import path from 'node:path';
import { SESSIONS_DIR } from '../utils/paths.js';
import { readJSON, writeJSON, ensureDir } from './storage.js';

/**
 * Logs an API call (request + response) to the session's api-logs.json
 */
export async function logApiCall(sessionId, { type, model, messages, params, response, error, durationMs }) {
  const logsDir = path.join(SESSIONS_DIR, sessionId);
  const logsFile = path.join(logsDir, 'api-logs.json');

  await ensureDir(logsDir);
  const logs = await readJSON(logsFile) || [];

  logs.push({
    timestamp: new Date().toISOString(),
    type,
    model,
    messages,
    params,
    response: response ? {
      narrative: response.narrative?.slice(0, 500),
      thinking: response.thinking?.slice(0, 500),
      raw: response.raw?.slice(0, 1000),
    } : null,
    error: error || null,
    durationMs: durationMs || null,
  });

  // Keep last 100 logs per session
  if (logs.length > 100) {
    logs.splice(0, logs.length - 100);
  }

  await writeJSON(logsFile, logs);
}
