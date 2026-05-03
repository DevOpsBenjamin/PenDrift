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

/**
 * Kick off a rerun or enrich. Returns immediately with `{jobId, kind, templateId}`.
 * The actual work runs as a background job — the JobsToastBar reflects its
 * progress via /api/jobs/stream, and the caller watches the jobs store for the
 * matching jobId to know when to refresh the template.
 */
export const rerunTemplateAnalysis = (id, sourceFilename, settingsPresetId = 'default') =>
  api.post(`presets/templates/${encodeURIComponent(id)}/rerun`, {
    json: { sourceFilename, settingsPresetId },
  }).json();

export const enrichTemplate = (id, sourceFilename, settingsPresetId = 'default') =>
  api.post(`presets/templates/${encodeURIComponent(id)}/enrich`, {
    json: { sourceFilename, settingsPresetId },
  }).json();
