import api from './client.js';

export const getCharacters = (sessionId) =>
  api.get(`sessions/${sessionId}/characters`).json();

export const triggerCharacterUpdate = (sessionId, chapterId) =>
  api.post(`sessions/${sessionId}/characters/update`, {
    json: { chapterId },
    timeout: 300000,
  }).json();

export const getMetaHistory = (sessionId) =>
  api.get(`sessions/${sessionId}/characters/meta-history`).json();
