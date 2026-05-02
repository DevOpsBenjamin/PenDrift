import api from './client.js';

export const startGeneration = (sessionId, { chapterId, directive, isKeyMoment }) =>
  api.post(`sessions/${sessionId}/generate`, {
    json: { chapterId, directive, isKeyMoment },
  }).json();

export const startRegeneration = (sessionId, { chunkId, chapterId, directive }) =>
  api.post(`sessions/${sessionId}/regenerate`, {
    json: { chunkId, chapterId, directive },
  }).json();

export const setChunkVersion = (sessionId, chunkId, versionIndex) =>
  api.put(`sessions/${sessionId}/chunks/${chunkId}/version`, {
    json: { versionIndex },
  }).json();

export const getJobStatus = (sessionId, jobId) =>
  api.get(`sessions/${sessionId}/jobs/${jobId}`).json();

export const deleteLastChunk = (sessionId, chapterId) =>
  api.delete(`sessions/${sessionId}/chunks/last`, {
    searchParams: { chapterId },
  }).json();

export const deleteChunkVersion = (sessionId, chunkId, versionIndex) =>
  api.delete(`sessions/${sessionId}/chunks/${chunkId}/version`, {
    json: { versionIndex },
  }).json();

/**
 * Stream narrative generation via SSE. Calls `onEvent(event)` for each parsed
 * event from the backend, and resolves when the stream closes.
 *
 * Events the backend can emit:
 *  prep_done, started, thinking_start, thinking_chunk{text}, thinking_done,
 *  type_resolved{value}, narrative_start, narrative_chunk{text},
 *  narrative_done, suggestions{items}, done{...}, error{message}
 */
export async function streamGeneration(sessionId, { chapterId, directive, isKeyMoment }, onEvent, signal) {
  return _consumeSSE(`/api/sessions/${sessionId}/generate/stream`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ chapterId, directive, isKeyMoment }),
    signal,
  }, onEvent);
}

/**
 * Stream a regeneration (new version of an existing chunk) via SSE.
 * Same event contract as `streamGeneration`. On done event, the chunk
 * payload contains `id, versions, activeVersion` (chunk-shaped, not full).
 */
export async function streamRegeneration(sessionId, { chunkId, directive }, onEvent, signal) {
  return _consumeSSE(`/api/sessions/${sessionId}/regenerate/stream`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ chunkId, directive }),
    signal,
  }, onEvent);
}

/**
 * Check whether a generation is currently in progress for the given session.
 * Returns {running, eventCount, done} or {running: false}.
 */
export async function getActiveStreamStatus(sessionId) {
  const resp = await fetch(`/api/sessions/${sessionId}/generate/stream/active`);
  if (!resp.ok) return { running: false };
  return resp.json();
}

/**
 * Attach to an in-progress generation for this session. Replays buffered
 * events then forwards live ones. Throws if no gen is running (404).
 */
export async function attachGenerationStream(sessionId, onEvent, signal) {
  return _consumeSSE(`/api/sessions/${sessionId}/generate/stream`, {
    method: 'GET',
    signal,
  }, onEvent);
}

async function _consumeSSE(url, init, onEvent) {
  const resp = await fetch(url, init);
  if (!resp.ok) {
    const text = await resp.text().catch(() => '');
    throw new Error(`Stream failed: ${resp.status} ${text}`);
  }
  const reader = resp.body.getReader();
  const decoder = new TextDecoder();
  let buffer = '';
  let chunkCount = 0;
  let eventCount = 0;
  console.log('[stream] connected, content-type:', resp.headers.get('content-type'));
  while (true) {
    const { value, done } = await reader.read();
    if (done) {
      console.log('[stream] reader done. chunks=%d events=%d', chunkCount, eventCount);
      break;
    }
    chunkCount++;
    const chunkText = decoder.decode(value, { stream: true });
    buffer += chunkText;
    if (chunkCount <= 5 || chunkCount % 50 === 0) {
      console.log('[stream] reader chunk #%d size=%d bytes (buffer=%d)', chunkCount, chunkText.length, buffer.length);
    }
    // Parse SSE events: each event is `data: <json>\n\n`
    let nl;
    while ((nl = buffer.indexOf('\n\n')) >= 0) {
      const block = buffer.slice(0, nl);
      buffer = buffer.slice(nl + 2);
      for (const line of block.split('\n')) {
        if (!line.startsWith('data:')) continue;
        const payload = line.slice(5).trim();
        if (!payload) continue;
        try {
          const ev = JSON.parse(payload);
          eventCount++;
          if (eventCount <= 10 || eventCount % 100 === 0) {
            console.log('[stream] event #%d type=%s', eventCount, ev.type, ev.text ? `"${ev.text}"` : '');
          }
          onEvent(ev);
        } catch (e) { console.warn('[stream] bad payload:', payload.slice(0, 100), e); }
      }
    }
  }
}
