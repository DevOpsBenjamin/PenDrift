import api from './client.js';

export const listSessions = () => api.get('sessions').json();

export const getSession = (id) => api.get(`sessions/${id}`).json();

export const createSession = ({ templateId, title, settingsPresetId }) =>
  api.post('sessions', { json: { templateId, title, settingsPresetId } }).json();

export const updateSession = (id, updates) =>
  api.put(`sessions/${id}`, { json: updates }).json();

export const deleteSession = (id) => api.delete(`sessions/${id}`).json();
