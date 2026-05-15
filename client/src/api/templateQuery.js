/**
 * Ask the Template — meta-analytical Q&A about a template's structure, goals,
 * gaps, and encoded references. Streamed as SSE. Different audience from
 * Ask-the-Narrator: this one talks ABOUT the template, not about the story.
 *
 * History is loaded server-side from the `template_queries` table. Optionally
 * a session can be attached as evidence so the model cross-references what
 * the template ASKS for vs what it ACTUALLY produces.
 */
export async function streamTemplateQuery(templateId, { question, sessionId }, onEvent, signal) {
  const resp = await fetch(`/api/presets/templates/${templateId}/query/stream`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ question, sessionId: sessionId || null }),
    signal,
  });
  if (!resp.ok) {
    const text = await resp.text().catch(() => '');
    throw new Error(`Template query failed: ${resp.status} ${text}`);
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

/**
 * Rewrite the template via LLM, using the user's feedback and an optional
 * selection of past meta-analytical asks. The new version lands on disk
 * automatically — the SSE stream emits a `done` event with the new version
 * number when it's saved.
 */
export async function streamTemplateRewrite(templateId, { feedback, askIds }, onEvent, signal) {
  const resp = await fetch(`/api/presets/templates/${templateId}/rewrite`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ feedback, askIds: askIds || [] }),
    signal,
  });
  if (!resp.ok) {
    const text = await resp.text().catch(() => '');
    throw new Error(`Rewrite failed: ${resp.status} ${text}`);
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

export async function getTemplateQueries(templateId) {
  const resp = await fetch(`/api/presets/templates/${templateId}/queries`);
  if (!resp.ok) {
    const text = await resp.text().catch(() => '');
    throw new Error(`Failed to load template queries: ${resp.status} ${text}`);
  }
  return resp.json();
}
