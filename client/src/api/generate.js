import api from './client.js';

export const generate = (sessionId, { chapterId, directive, isKeyMoment }) =>
  api.post(`sessions/${sessionId}/generate`, {
    json: { chapterId, directive, isKeyMoment },
    timeout: 300000,
  }).json();

export const regenerate = (sessionId, { chapterId }) =>
  api.post(`sessions/${sessionId}/regenerate`, {
    json: { chapterId },
    timeout: 300000,
  }).json();

export const deleteLastChunk = (sessionId, chapterId) =>
  api.delete(`sessions/${sessionId}/chunks/last`, {
    searchParams: { chapterId },
  }).json();
