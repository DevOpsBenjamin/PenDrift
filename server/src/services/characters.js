import path from 'node:path';
import { SESSIONS_DIR } from '../utils/paths.js';
import { readJSON, writeJSON } from './storage.js';
import { generateCompletion } from './llm.js';
import { buildCharacterUpdateMessages } from './prompts.js';

function charactersFile(sessionId) {
  return path.join(SESSIONS_DIR, sessionId, 'characters.json');
}

export async function getCharacters(sessionId) {
  return await readJSON(charactersFile(sessionId)) || [];
}

export async function saveCharacters(sessionId, characters) {
  await writeJSON(charactersFile(sessionId), characters);
}

/**
 * Meta-call: asks the LLM to update character sheets based on recent narrative.
 */
export async function updateCharacterSheets(sessionId, recentChunks, settings) {
  const characters = await getCharacters(sessionId);
  if (characters.length === 0) return characters;

  const messages = buildCharacterUpdateMessages({ characters, recentChunks });

  try {
    const { narrative: responseText } = await generateCompletion(messages, settings);

    // Try to parse JSON from response (may be wrapped in markdown code blocks)
    let updated;
    try {
      updated = JSON.parse(responseText);
    } catch {
      // Try extracting JSON from markdown code block
      const jsonMatch = responseText.match(/```(?:json)?\s*([\s\S]*?)```/);
      if (jsonMatch) {
        updated = JSON.parse(jsonMatch[1]);
      } else {
        throw new Error('Could not parse character update response');
      }
    }

    if (!Array.isArray(updated)) {
      throw new Error('Character update response is not an array');
    }

    // Merge updates with existing characters, preserving names
    const now = new Date().toISOString();
    const merged = characters.map(existing => {
      const update = updated.find(u => u.name === existing.name);
      if (update) {
        return {
          ...existing,
          currentState: update.currentState || existing.currentState,
          traits: update.traits || existing.traits,
          keyEvents: update.keyEvents || existing.keyEvents,
          lastUpdated: now,
        };
      }
      return existing;
    });

    await saveCharacters(sessionId, merged);
    return merged;
  } catch (err) {
    console.error('Character sheet update failed:', err.message);
    return characters; // Return unchanged on failure
  }
}
