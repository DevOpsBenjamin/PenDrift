import api from './client.js';

export const importChub = ({ url, card, settingsPresetId = 'default' }) =>
  api.post('import/chub', {
    json: { url, card, settingsPresetId },
    timeout: 600000, // LLM conversion can be slow
  }).json();
