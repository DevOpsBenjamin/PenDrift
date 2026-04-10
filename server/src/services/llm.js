import ky from 'ky';
import { stripThinkBlocks } from '../utils/think-parser.js';

/**
 * Calls the OpenAI-compatible chat completions endpoint.
 */
export async function generateCompletion(messages, settings) {
  const { apiEndpoint, model, temperature, maxTokens, thinkBlockStart, thinkBlockEnd } = settings;

  let data;
  try {
    data = await ky.post(apiEndpoint, {
      json: {
        model,
        messages,
        temperature: temperature ?? 0.8,
        max_tokens: maxTokens ?? 2048,
      },
      timeout: 300000, // 5 min for slow local models
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
