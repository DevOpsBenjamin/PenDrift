import api from './client.js';

export const getLlmStatus = () => api.get('llm/status').json();
export const getProviderStatus = () => api.get('llm/providers/status').json();
export const getProviderModels = (provider, baseUrl) => 
  api.get(`llm/providers/${encodeURIComponent(provider)}/models`, { searchParams: { base_url: baseUrl } }).json();

export const loadModel = ({ modelPath, gpuLayers, contextSize, port }) =>
  api.post('llm/load', {
    json: { modelPath, gpuLayers, contextSize, port },
    timeout: 120000,
  }).json();

export const unloadModel = () => api.post('llm/unload').json();

export const configureExe = (executablePath) =>
  api.post('llm/configure', { json: { executablePath } }).json();

export const getVersion = () => api.get('llm/version').json();

export const downloadLlamaServer = (variant = 'cuda13') =>
  api.post('llm/download', {
    json: { variant },
    timeout: 300000, // downloads can take a while
  }).json();

export const browsePath = (path) =>
  api.get('llm/browse', { searchParams: path ? { path } : {} }).json();

export const getActivity = () => api.get('llm/activity').json();

export const getLogs = (lines = 200) =>
  api.get('llm/logs', { searchParams: { lines } }).json();

export const getResponseDump = (filename) =>
  api.get(`llm/response/${encodeURIComponent(filename)}`).json();

export const getRequestDump = (filename) =>
  api.get(`llm/request/${encodeURIComponent(filename)}`).json();

export const cancelCall = (id) =>
  api.post(`llm/cancel/${encodeURIComponent(id)}`).json();

export const getXaiBudget = () => api.get('xai/budget').json();
export const refreshXaiBudget = () => api.post('xai/budget/refresh').json();
