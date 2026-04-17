import api from './client.js';

export const getLlmStatus = () => api.get('llm/status').json();

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
