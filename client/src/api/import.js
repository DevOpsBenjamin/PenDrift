import api from './client.js';

/**
 * Import a chub.ai character card. Returns immediately with `{jobId,
 * originalCard}` — the actual conversion runs as a background job.
 * Subscribe to the job via `subscribeToJob(jobId, ...)` (or just watch
 * the JobsToastBar) to see live progress.
 */
export const importChub = ({ url, card, settingsPresetId = 'default' }) =>
  api.post('import/chub', {
    json: { url, card, settingsPresetId },
  }).json();
