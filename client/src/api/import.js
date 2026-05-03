import api from './client.js';

/**
 * Import a chub.ai character card. Returns immediately with `{jobId,
 * originalCard}` — the actual conversion runs as a background job.
 * Watch the JobsStore (fed by /api/jobs/stream) for live progress.
 */
export const importChub = ({ url, card, settingsPresetId = 'default' }) =>
  api.post('import/chub', {
    json: { url, card, settingsPresetId },
  }).json();
