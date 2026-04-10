import api from './client.js';

export const listSettingsPresets = () => api.get('presets/settings').json();

export const getSettingsPreset = (id) => api.get(`presets/settings/${id}`).json();

export const saveSettingsPreset = (preset) =>
  api.post('presets/settings', { json: preset }).json();

export const deleteSettingsPreset = (id) => api.delete(`presets/settings/${id}`).json();
