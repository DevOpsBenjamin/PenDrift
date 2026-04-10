import ky from 'ky';
import { stripThinkBlocks } from '../utils/think-parser.js';
import { logApiCall } from './api-logger.js';
import { enqueueLLMCall, getQueueLength } from './llm-queue.js';

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
 * Logs request and response to the session's api-logs.json.
 *
 * @param {Array} messages - The messages array
 * @param {Object} settings - Full settings preset
 * @param {string} modelOverride - Which model to use (overrides default)
 * @param {string} sessionId - For logging (optional)
 * @param {string} callType - Label for the log entry (e.g. 'narrative', 'meta', 'format-fixer')
 */
export function generateCompletion(messages, settings, modelOverride, sessionId, callType) {
  const label = `${callType || 'unknown'}${sessionId ? ` [${sessionId.slice(0, 8)}]` : ''}`;
  return enqueueLLMCall(() => _generateCompletion(messages, settings, modelOverride, sessionId, callType), label);
}

async function _generateCompletion(messages, settings, modelOverride, sessionId, callType) {
  const { apiEndpoint, thinkBlockStart, thinkBlockEnd } = settings;
  const model = modelOverride || settings.narrativeModel || settings.model;

  const samplerParams = buildSamplerParams(settings);

  // Provider-specific options
  const providerOptions = {};
  if (settings.provider === 'ollama' && settings.contextSize) {
    providerOptions.options = { num_ctx: settings.contextSize };
  }

  const startTime = Date.now();
  let data;
  try {
    data = await ky.post(apiEndpoint, {
      json: {
        model,
        messages,
        stream: false,
        ...samplerParams,
        ...providerOptions,
      },
      timeout: 300000,
    }).json();
  } catch (err) {
    const durationMs = Date.now() - startTime;
    const endpoint = apiEndpoint || 'unknown';
    const errorMsg = err.name === 'TimeoutError'
      ? `LLM request timed out after 5 minutes`
      : `Could not connect to LLM at ${endpoint}. Is Ollama/KoboldCpp running? (${err.message})`;

    // Log the failed call
    if (sessionId) {
      logApiCall(sessionId, {
        type: callType || 'unknown',
        model,
        messages,
        params: { ...samplerParams, ...providerOptions },
        error: errorMsg,
        durationMs,
      }).catch(() => {});
    }

    throw Object.assign(new Error(errorMsg), {
      status: err.name === 'TimeoutError' ? 504 : 502,
    });
  }

  const durationMs = Date.now() - startTime;
  const message = data.choices?.[0]?.message || {};
  const rawContent = message.content || '';

  // Some providers (LM Studio) return reasoning in a separate field
  // Others embed <think> blocks in the content
  let narrative, thinking;
  if (message.reasoning_content) {
    narrative = rawContent.trim();
    thinking = message.reasoning_content;
  } else {
    ({ narrative, thinking } = stripThinkBlocks(rawContent, thinkBlockStart, thinkBlockEnd));
  }

  // Extract usage stats if available
  const usage = data.usage || {};
  const stats = {
    durationMs,
    promptTokens: usage.prompt_tokens || null,
    completionTokens: usage.completion_tokens || null,
    reasoningTokens: usage.completion_tokens_details?.reasoning_tokens || null,
    totalTokens: usage.total_tokens || null,
  };

  const result = { narrative, thinking, raw: rawContent, stats };

  // Log the successful call
  if (sessionId) {
    logApiCall(sessionId, {
      type: callType || 'unknown',
      model,
      messages,
      params: { ...samplerParams, ...providerOptions },
      response: result,
      durationMs,
    }).catch(() => {});
  }

  return result;
}
