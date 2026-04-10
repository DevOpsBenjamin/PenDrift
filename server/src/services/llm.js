import ky from 'ky';
import { stripThinkBlocks } from '../utils/think-parser.js';

/**
 * Builds the sampler params object from settings, omitting unset values.
 */
function buildSamplerParams(settings) {
  const params = {};

  if (settings.temperature != null) params.temperature = settings.temperature;
  if (settings.maxTokens != null) params.max_tokens = settings.maxTokens;
  if (settings.topP != null) params.top_p = settings.topP;
  if (settings.topK != null) params.top_k = settings.topK;
  if (settings.minP != null) params.min_p = settings.minP;
  if (settings.presencePenalty != null) params.presence_penalty = settings.presencePenalty;
  if (settings.frequencyPenalty != null) params.frequency_penalty = settings.frequencyPenalty;
  if (settings.repeatPenalty != null) params.repeat_penalty = settings.repeatPenalty;
  if (settings.seed != null) params.seed = settings.seed;

  return params;
}

/**
 * Calls the OpenAI-compatible chat completions endpoint with a specific model.
 * @param {Array} messages - The messages array
 * @param {Object} settings - Full settings preset
 * @param {string} modelOverride - Which model to use (overrides default)
 */
export async function generateCompletion(messages, settings, modelOverride) {
  const { apiEndpoint, thinkBlockStart, thinkBlockEnd } = settings;
  const model = modelOverride || settings.narrativeModel || settings.model;

  const samplerParams = buildSamplerParams(settings);

  // Provider-specific options
  const providerOptions = {};
  if (settings.provider === 'ollama' && settings.contextSize) {
    providerOptions.options = { num_ctx: settings.contextSize };
  }

  let data;
  try {
    data = await ky.post(apiEndpoint, {
      json: {
        model,
        messages,
        ...samplerParams,
        ...providerOptions,
      },
      timeout: 300000,
    }).json();
  } catch (err) {
    const endpoint = apiEndpoint || 'unknown';
    if (err.name === 'TimeoutError') {
      throw Object.assign(new Error(`LLM request timed out after 5 minutes`), { status: 504 });
    }
    throw Object.assign(
      new Error(`Could not connect to LLM at ${endpoint}. Is Ollama/KoboldCpp running? (${err.message})`),
      { status: 502 },
    );
  }

  const rawContent = data.choices?.[0]?.message?.content || '';
  const { narrative, thinking } = stripThinkBlocks(rawContent, thinkBlockStart, thinkBlockEnd);

  return { narrative, thinking, raw: rawContent };
}
