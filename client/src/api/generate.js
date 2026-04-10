import api from './client.js';

export const startGeneration = (sessionId, { chapterId, directive, isKeyMoment }) =>
  api.post(`sessions/${sessionId}/generate`, {
    json: { chapterId, directive, isKeyMoment },
  }).json();

export const startRegeneration = (sessionId, { chunkId, chapterId, directive }) =>
  api.post(`sessions/${sessionId}/regenerate`, {
    json: { chunkId, chapterId, directive },
  }).json();

export const setChunkVersion = (sessionId, chunkId, versionIndex) =>
  api.put(`sessions/${sessionId}/chunks/${chunkId}/version`, {
    json: { versionIndex },
  }).json();

export const getJobStatus = (sessionId, jobId) =>
  api.get(`sessions/${sessionId}/jobs/${jobId}`).json();

export const deleteLastChunk = (sessionId, chapterId) =>
  api.delete(`sessions/${sessionId}/chunks/last`, {
    searchParams: { chapterId },
  }).json();

export const deleteChunkVersion = (sessionId, chunkId, versionIndex) =>
  api.delete(`sessions/${sessionId}/chunks/${chunkId}/version`, {
    json: { versionIndex },
  }).json();
