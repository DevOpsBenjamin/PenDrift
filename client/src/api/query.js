/**
 * Ask the Narrator — analytical Q&A about the story, streamed as SSE.
 * The model has full session context (chars, facts, masked intents, recent
 * chunks) but answers in plain analytical prose, not narrative.
 *
 * History is loaded server-side from the `session_queries` table — clients
 * no longer pass it in the body. This way closing the modal mid-call doesn't
 * lose the question; the next reopen sees the persisted result.
 */
export async function streamQuery(sessionId, { question }, onEvent, signal) {
  const resp = await fetch(`/api/sessions/${sessionId}/query/stream`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ question }),
    signal,
  });
  if (!resp.ok) {
    const text = await resp.text().catch(() => '');
    throw new Error(`Query failed: ${resp.status} ${text}`);
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
        try { onEvent(JSON.parse(payload)); } catch { /* skip malformed */ }
      }
    }
  }
}

/**
 * Fetch every persisted Q&A for a session. Used by the modal on mount so the
 * history survives close/reopen, page reloads, and cross-device access.
 */
export async function getQueries(sessionId) {
  const resp = await fetch(`/api/sessions/${sessionId}/queries`);
  if (!resp.ok) {
    const text = await resp.text().catch(() => '');
    throw new Error(`Failed to load queries: ${resp.status} ${text}`);
  }
  return resp.json();
}
