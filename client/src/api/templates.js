import api from './client.js';

export const listTemplates = () => api.get('presets/templates').json();

export const getTemplate = (id) => api.get(`presets/templates/${id}`).json();

export const saveTemplate = (template) =>
  api.post('presets/templates', { json: template }).json();

export const deleteTemplate = (id) => api.delete(`presets/templates/${id}`).json();

export const uploadTemplateImage = async (id, file) => {
  const fd = new FormData();
  fd.append('file', file);
  const resp = await fetch(`/api/presets/templates/${encodeURIComponent(id)}/image`, {
    method: 'POST',
    body: fd,
  });
  if (!resp.ok) {
    const err = await resp.json().catch(() => ({}));
    throw new Error(err.detail || `Upload failed: ${resp.status}`);
  }
  return resp.json();
};

export const deleteTemplateImage = (id) =>
  api.delete(`presets/templates/${encodeURIComponent(id)}/image`).json();

/** Return the URL to fetch a template's cover image, or null if none.
 * Pass the template object (we use `id` and `coverImage` as the presence
 * indicator). The query param busts the browser cache when the image is
 * replaced. */
export const templateImageUrl = (template) => {
  if (!template?.id || !template.coverImage) return null;
  return `/api/presets/templates/${encodeURIComponent(template.id)}/image?v=${encodeURIComponent(template.coverImage)}`;
};

// ── Versioning ───────────────────────────────────────────

export const listTemplateVersions = (id) =>
  api.get(`presets/templates/${encodeURIComponent(id)}/versions`).json();

export const getTemplateVersion = (id, version) =>
  api.get(`presets/templates/${encodeURIComponent(id)}/versions/${encodeURIComponent(version)}`).json();

export const checkpointTemplate = (id) =>
  api.post(`presets/templates/${encodeURIComponent(id)}/checkpoint`).json();

export const restoreTemplateVersion = (id, version) =>
  api.post(`presets/templates/${encodeURIComponent(id)}/restore/${encodeURIComponent(version)}`).json();

export const diffTemplateVersions = (id, from, to) =>
  api.get(`presets/templates/${encodeURIComponent(id)}/diff`, {
    searchParams: { from, to },
  }).json();

// ── Sources ──────────────────────────────────────────────

export const listTemplateSources = (id) =>
  api.get(`presets/templates/${encodeURIComponent(id)}/sources`).json();

export const attachTemplateSource = (id, card) =>
  api.post(`presets/templates/${encodeURIComponent(id)}/sources`, { json: { card } }).json();

export const deleteTemplateSource = (id, filename) =>
  api.delete(`presets/templates/${encodeURIComponent(id)}/sources/${encodeURIComponent(filename)}`).json();

async function _streamLlmOp(path, sourceFilename, settingsPresetId, onProgress) {
  // SSE-based long-running op. Returns a Promise that resolves with the
  // `done` event payload, rejects on `error`. Heartbeat events are passed to
  // onProgress so the UI can show elapsed time.
  const resp = await fetch(`/api/${path}`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ sourceFilename, settingsPresetId }),
  });
  if (!resp.ok) {
    let msg = `${resp.status} ${resp.statusText}`;
    try { const err = await resp.json(); msg = err.detail || msg; } catch { /* ignore */ }
    throw new Error(msg);
  }
  const reader = resp.body.getReader();
  const decoder = new TextDecoder();
  let buffer = '';
  while (true) {
    const { done, value } = await reader.read();
    if (done) throw new Error('Stream ended without a done event');
    buffer += decoder.decode(value, { stream: true });
    let idx;
    while ((idx = buffer.indexOf('\n\n')) !== -1) {
      const frame = buffer.slice(0, idx);
      buffer = buffer.slice(idx + 2);
      for (const line of frame.split('\n')) {
        if (!line.startsWith('data: ')) continue;
        let ev;
        try { ev = JSON.parse(line.slice(6)); } catch { continue; }
        if (ev.type === 'done') return ev;
        if (ev.type === 'error') throw new Error(ev.message);
        onProgress?.(ev);
      }
    }
  }
}

export const rerunTemplateAnalysis = (id, sourceFilename, settingsPresetId = 'default', onProgress) =>
  _streamLlmOp(`presets/templates/${encodeURIComponent(id)}/rerun`, sourceFilename, settingsPresetId, onProgress);

export const enrichTemplate = (id, sourceFilename, settingsPresetId = 'default', onProgress) =>
  _streamLlmOp(`presets/templates/${encodeURIComponent(id)}/enrich`, sourceFilename, settingsPresetId, onProgress);
