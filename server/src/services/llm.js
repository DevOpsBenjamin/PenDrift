import http from 'node:http';
import https from 'node:https';
import { stripThinkBlocks } from '../utils/think-parser.js';
import { logApiRequest, logApiResult } from './api-logger.js';
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

  // Log request BEFORE the call — survives server crashes
  let logIndex = -1;
  if (sessionId) {
    logIndex = await logApiRequest(sessionId, {
      type: callType || 'unknown',
      model,
      messages,
      params: { ...samplerParams, ...providerOptions },
    }).catch(() => -1);
  }

  const startTime = Date.now();
  let data;
  try {
    // Use native fetch with AbortController for reliable long timeouts
    // ky/node http agent may have hidden TCP timeouts at ~300s
    const controller = new AbortController();
    const timeoutId = setTimeout(() => controller.abort(), 600000);

    const requestBody = JSON.stringify({
      model,
      messages,
      stream: false,
      ...samplerParams,
      ...providerOptions,
    });

    // Use node:http directly to bypass undici/fetch 300s default timeout
    const url = new URL(apiEndpoint);
    const httpModule = url.protocol === 'https:' ? https : http;

    const response = await new Promise((resolve, reject) => {
      const req = httpModule.request({
        hostname: url.hostname,
        port: url.port,
        path: url.pathname,
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          'Content-Length': Buffer.byteLength(requestBody),
        },
        timeout: 600000,
      }, (res) => {
        let body = '';
        res.on('data', chunk => body += chunk);
        res.on('end', () => resolve({ ok: res.statusCode >= 200 && res.statusCode < 300, status: res.statusCode, body }));
      });

      req.on('timeout', () => { req.destroy(); reject(new Error('Request timed out')); });
      req.on('error', reject);
      controller.signal.addEventListener('abort', () => req.destroy());
      req.write(requestBody);
      req.end();
    });

    clearTimeout(timeoutId);

    if (!response.ok) {
      throw new Error(`Request failed with status code ${response.status}: POST ${apiEndpoint}`);
    }

    data = JSON.parse(response.body);
  } catch (err) {
    const durationMs = Date.now() - startTime;
    const endpoint = apiEndpoint || 'unknown';
    const errorMsg = err.name === 'TimeoutError'
      ? `LLM request timed out after 5 minutes`
      : `Could not connect to LLM at ${endpoint}. Is Ollama/KoboldCpp running? (${err.message})`;

    // Update log with failure
    if (sessionId && logIndex >= 0) {
      logApiResult(sessionId, logIndex, { error: errorMsg, durationMs }).catch(() => {});
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

  // Model name from response (actual model used)
  const modelName = data.model || model;

  // Extract usage stats if available
  const usage = data.usage || {};
  const stats = {
    durationMs,
    promptTokens: usage.prompt_tokens || null,
    completionTokens: usage.completion_tokens || null,
    reasoningTokens: usage.completion_tokens_details?.reasoning_tokens || null,
    totalTokens: usage.total_tokens || null,
  };

  const result = { narrative, thinking, raw: rawContent, stats, modelName };

  // Update log with success
  if (sessionId && logIndex >= 0) {
    logApiResult(sessionId, logIndex, { response: result, durationMs }).catch(() => {});
  }

  return result;
}
