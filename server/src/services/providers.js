import ky from 'ky';

/**
 * Fetches the list of available models from the configured LLM provider.
 * Returns an array of { id, name } objects.
 */
export async function listModels(apiEndpoint, provider) {
  const baseUrl = extractBaseUrl(apiEndpoint);

  try {
    switch (provider) {
      case 'ollama':
        return await listOllamaModels(baseUrl);
      case 'lmstudio':
        return await listOpenAIModels(baseUrl);
      case 'koboldcpp':
        return await listKoboldModel(baseUrl);
      case 'generic':
      default:
        // Try OpenAI-compatible endpoint first, fall back to empty
        try {
          return await listOpenAIModels(baseUrl);
        } catch {
          return [];
        }
    }
  } catch (err) {
    console.error(`Failed to list models from ${provider} at ${baseUrl}:`, err.message);
    return [];
  }
}

/**
 * Extracts the base URL from the full API endpoint.
 * e.g. "http://localhost:11434/v1/chat/completions" → "http://localhost:11434"
 */
function extractBaseUrl(endpoint) {
  try {
    const url = new URL(endpoint);
    return `${url.protocol}//${url.host}`;
  } catch {
    return endpoint;
  }
}

/**
 * Ollama: GET /api/tags → { models: [{ name, size, ... }] }
 */
async function listOllamaModels(baseUrl) {
  const data = await ky.get(`${baseUrl}/api/tags`, { timeout: 5000 }).json();
  return (data.models || []).map(m => ({
    id: m.name,
    name: m.name,
    size: m.size,
    modified: m.modified_at,
  }));
}

/**
 * OpenAI-compatible (LM Studio, vLLM, etc.): GET /v1/models → { data: [{ id, ... }] }
 */
async function listOpenAIModels(baseUrl) {
  const data = await ky.get(`${baseUrl}/v1/models`, { timeout: 5000 }).json();
  return (data.data || []).map(m => ({
    id: m.id,
    name: m.id,
    owned_by: m.owned_by,
  }));
}

/**
 * KoboldCpp: GET /api/v1/model → { result: "model name" }
 * Only returns the currently loaded model.
 */
async function listKoboldModel(baseUrl) {
  const data = await ky.get(`${baseUrl}/api/v1/model`, { timeout: 5000 }).json();
  if (data.result) {
    return [{ id: data.result, name: data.result }];
  }
  return [];
}
