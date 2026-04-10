import api from './client.js';

export const listTemplates = () => api.get('presets/templates').json();

export const getTemplate = (id) => api.get(`presets/templates/${id}`).json();

export const saveTemplate = (template) =>
  api.post('presets/templates', { json: template }).json();

export const deleteTemplate = (id) => api.delete(`presets/templates/${id}`).json();
