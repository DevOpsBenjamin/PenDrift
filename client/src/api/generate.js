import api from './client.js';

export const startGeneration = (sessionId, { chapterId, directive, isKeyMoment }) =>
  api.post(`sessions/${sessionId}/generate`, {
    json: { chapterId, directive, isKeyMoment },
  }).json();

export const startRegeneration = (sessionId, { chapterId }) =>
  api.post(`sessions/${sessionId}/regenerate`, {
    json: { chapterId },
  }).json();

export const getJobStatus = (sessionId, jobId) =>
  api.get(`sessions/${sessionId}/jobs/${jobId}`).json();

export const deleteLastChunk = (sessionId, chapterId) =>
  api.delete(`sessions/${sessionId}/chunks/last`, {
    searchParams: { chapterId },
  }).json();
