import path from 'node:path';
import { SESSIONS_DIR } from '../utils/paths.js';
import { readJSON, writeJSON, ensureDir } from './storage.js';

function getLogsFile(sessionId) {
  return path.join(SESSIONS_DIR, sessionId, 'api-logs.json');
}

/**
 * Log the request BEFORE the API call. Returns the log index for updating later.
 */
export async function logApiRequest(sessionId, { type, model, messages, params }) {
  const logsFile = getLogsFile(sessionId);
  await ensureDir(path.join(SESSIONS_DIR, sessionId));
  const logs = await readJSON(logsFile) || [];

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

  logs.push(entry);

  if (logs.length > 100) {
    logs.splice(0, logs.length - 100);
  }

  await writeJSON(logsFile, logs);
  return logs.length - 1;
}

/**
 * Update an existing log entry with the response or error.
 */
export async function logApiResult(sessionId, logIndex, { response, error, durationMs }) {
  const logsFile = getLogsFile(sessionId);
  const logs = await readJSON(logsFile) || [];

  if (logIndex >= 0 && logIndex < logs.length) {
    logs[logIndex].status = error ? 'failed' : 'success';
    logs[logIndex].response = response ? {
      narrative: response.narrative?.slice(0, 500),
      thinking: response.thinking?.slice(0, 500),
      raw: response.raw?.slice(0, 1000),
    } : null;
    logs[logIndex].error = error || null;
    logs[logIndex].durationMs = durationMs || null;

    await writeJSON(logsFile, logs);
  }
}

// Keep backward compat
export async function logApiCall(sessionId, { type, model, messages, params, response, error, durationMs }) {
  const logsFile = getLogsFile(sessionId);
  await ensureDir(path.join(SESSIONS_DIR, sessionId));
  const logs = await readJSON(logsFile) || [];

  logs.push({
    timestamp: new Date().toISOString(),
    type,
    model,
    messages,
    params,
    status: error ? 'failed' : 'success',
    response: response ? {
      narrative: response.narrative?.slice(0, 500),
      thinking: response.thinking?.slice(0, 500),
      raw: response.raw?.slice(0, 1000),
    } : null,
    error: error || null,
    durationMs: durationMs || null,
  });

  if (logs.length > 100) {
    logs.splice(0, logs.length - 100);
  }

  await writeJSON(logsFile, logs);
}
