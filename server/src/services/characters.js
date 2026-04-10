import path from 'node:path';
import { SESSIONS_DIR } from '../utils/paths.js';
import { readJSON, writeJSON } from './storage.js';
import { generateCompletion } from './llm.js';
import { buildMetaAnalysisMessages } from './prompts.js';
import { getFacts, addFacts } from './facts.js';

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
 * Parses the meta-call JSON response with fallbacks for markdown-wrapped JSON.
 */
function parseMetaResponse(text) {
  // Try direct parse
  try {
    return JSON.parse(text);
  } catch {
    // Try extracting from markdown code block
    const jsonMatch = text.match(/```(?:json)?\s*([\s\S]*?)```/);
    if (jsonMatch) {
      try {
        return JSON.parse(jsonMatch[1]);
      } catch { /* fall through */ }
    }
    // Try finding a JSON object in the text
    const objMatch = text.match(/\{[\s\S]*\}/);
    if (objMatch) {
      try {
        return JSON.parse(objMatch[0]);
      } catch { /* fall through */ }
    }
    throw new Error('Could not parse meta-call response as JSON');
  }
}

/**
 * Enriched meta-call: updates characters, detects new ones, flags inconsistencies,
 * extracts important facts. Returns the full analysis result.
 */
export async function runMetaAnalysis(sessionId, recentChunks, settings) {
  const characters = await getCharacters(sessionId);
  const importantFacts = await getFacts(sessionId);

  if (recentChunks.length === 0) {
    return { characters, consistencyFlags: [], importantFacts };
  }

  const messages = buildMetaAnalysisMessages({
    characters,
    recentChunks,
    importantFacts,
    metaPrompt: settings.metaPrompt,
  });

  try {
    const { narrative: responseText } = await generateCompletion(messages, settings);
    const result = parseMetaResponse(responseText);

    const now = new Date().toISOString();

    // 1. Update existing characters
    if (result.characterUpdates?.length) {
      for (const update of result.characterUpdates) {
        const existing = characters.find(c => c.name === update.name);
        if (existing) {
          existing.currentState = update.currentState || existing.currentState;
          existing.traits = update.traits || existing.traits;
          existing.keyEvents = update.keyEvents || existing.keyEvents;
          existing.lastUpdated = now;
        }
      }
    }

    // 2. Add new characters
    if (result.newCharacters?.length) {
      for (const newChar of result.newCharacters) {
        // Don't add if already exists
        if (!characters.find(c => c.name === newChar.name)) {
          characters.push({
            name: newChar.name,
            currentState: newChar.currentState || '',
            traits: newChar.traits || [],
            keyEvents: newChar.keyEvents || [],
            lastUpdated: now,
          });
        }
      }
    }

    await saveCharacters(sessionId, characters);

    // 3. Store new important facts
    if (result.importantFacts?.length) {
      await addFacts(sessionId, result.importantFacts);
    }

    return {
      characters,
      consistencyFlags: result.consistencyFlags || [],
      newCharacters: result.newCharacters || [],
      importantFacts: result.importantFacts || [],
    };
  } catch (err) {
    console.error('Meta-analysis failed:', err.message);
    return { characters, consistencyFlags: [], importantFacts: [] };
  }
}
