import api from './client.js';

export const listSessions = () => api.get('sessions').json();

export const getSession = (id) => api.get(`sessions/${id}`).json();

export const createSession = ({ templateId, title, settingsPresetId }) =>
  api.post('sessions', { json: { templateId, title, settingsPresetId } }).json();

export const updateSession = (id, updates) =>
  api.put(`sessions/${id}`, { json: updates }).json();

export const deleteSession = (id) => api.delete(`sessions/${id}`).json();

export const setSessionTemplateVersion = (id, version) =>
  api.put(`sessions/${id}/template-version`, { json: { version } }).json();

export const validateFinish = (id) =>
  api.post(`sessions/${id}/finish/validate`).json();

export const reopenFinished = (id) =>
  api.post(`sessions/${id}/finish/reopen`).json();

/**
 * Stream epilogue generation via SSE. The backend renames the empty trailing
 * chapter to "Epilogue" (or creates a new one), generates a closing narrative
 * chunk, and saves it. The session is NOT marked finished — call
 * `validateFinish` separately once the user reviews/accepts the chunk.
 */
export async function streamFinish(sessionId, onEvent, signal) {
  const resp = await fetch(`/api/sessions/${sessionId}/finish`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    signal,
  });
  if (!resp.ok) {
    const text = await resp.text().catch(() => '');
    throw new Error(`Finish failed: ${resp.status} ${text}`);
  }
  const reader = resp.body.getReader();
  const decoder = new TextDecoder();
  let buffer = '';
  while (true) {
    const { value, done } = await reader.read();
    if (done) break;
    buffer += decoder.decode(value, { stream: true });
    let nl;
    while ((nl = buffer.indexOf('\n\n')) >= 0) {
      const block = buffer.slice(0, nl);
      buffer = buffer.slice(nl + 2);
      for (const line of block.split('\n')) {
        if (!line.startsWith('data:')) continue;
        const payload = line.slice(5).trim();
        if (!payload) continue;
        try { onEvent?.(JSON.parse(payload)); } catch { /* skip malformed */ }
      }
    }
  }
}
