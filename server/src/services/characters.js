import path from 'node:path';
import { SESSIONS_DIR } from '../utils/paths.js';
import { readJSON, writeJSON } from './storage.js';
import { generateCompletion } from './llm.js';
import { buildMetaAnalysisMessages } from './prompts.js';
import { getFacts, addFacts } from './facts.js';

function charactersFile(sessionId) {
  return path.join(SESSIONS_DIR, sessionId, 'characters.json');
}

function metaHistoryFile(sessionId) {
  return path.join(SESSIONS_DIR, sessionId, 'meta-history.json');
}

export async function getCharacters(sessionId) {
  return await readJSON(charactersFile(sessionId)) || [];
}

export async function saveCharacters(sessionId, characters) {
  await writeJSON(charactersFile(sessionId), characters);
}

export async function getMetaHistory(sessionId) {
  return await readJSON(metaHistoryFile(sessionId)) || [];
}

/**
 * Try parsing JSON from the meta-call response.
 */
function tryParseMetaJSON(text) {
  // Direct parse
  try { return JSON.parse(text); } catch { /* continue */ }

  // Markdown code block
  const jsonMatch = text.match(/```(?:json)?\s*([\s\S]*?)```/);
  if (jsonMatch) {
    try { return JSON.parse(jsonMatch[1]); } catch { /* continue */ }
  }

  // Find JSON object in text
  const objMatch = text.match(/\{[\s\S]*\}/);
  if (objMatch) {
    try { return JSON.parse(objMatch[0]); } catch { /* continue */ }
  }

  return null;
}

/**
 * Use the utility model to fix malformed JSON output.
 */
async function fixJSONWithUtility(rawText, settings, sessionId) {
  const utilityModel = settings.utilityModel || settings.narrativeModel;
  const fixerPrompt = settings.formatFixerPrompt || 'Extract and return only valid JSON from the following text.';

  const messages = [
    { role: 'system', content: fixerPrompt },
    { role: 'user', content: rawText },
  ];

  const { narrative } = await generateCompletion(messages, settings, utilityModel, sessionId, 'format-fixer');
  return tryParseMetaJSON(narrative);
}

/**
 * Enriched meta-call with format fixer fallback and history logging.
 */
export async function runMetaAnalysis(sessionId, recentChunks, settings) {
  const characters = await getCharacters(sessionId);
  const importantFacts = await getFacts(sessionId);

  if (recentChunks.length === 0) {
    return { characters, consistencyFlags: [], importantFacts: [] };
  }

  const metaModel = settings.metaModel || settings.narrativeModel;

  const messages = buildMetaAnalysisMessages({
    characters,
    recentChunks,
    importantFacts,
    metaPrompt: settings.metaPrompt,
  });

  let rawResponse = '';
  let result = null;

  try {
    // Step 1: meta-analysis with the smart model
    const response = await generateCompletion(messages, settings, metaModel, sessionId, 'meta');
    rawResponse = response.raw;

    // Step 2: try parsing directly
    result = tryParseMetaJSON(response.narrative);

    // Step 3: if parse fails, use utility model to fix format
    if (!result) {
      console.log('Meta-call JSON parse failed, trying format fixer...');
      result = await fixJSONWithUtility(response.raw, settings, sessionId);
    }

    if (!result) {
      throw new Error('Could not parse meta-analysis response even after format fixing');
    }
  } catch (err) {
    console.error('Meta-analysis failed:', err.message);

    // Log the failure in history anyway
    const history = await getMetaHistory(sessionId);
    history.push({
      timestamp: new Date().toISOString(),
      chunkRange: {
        from: recentChunks[0]?.id,
        to: recentChunks[recentChunks.length - 1]?.id,
      },
      status: 'failed',
      error: err.message,
      rawResponse,
    });
    await writeJSON(metaHistoryFile(sessionId), history);

    return { characters, consistencyFlags: [], importantFacts: [] };
  }

  const now = new Date().toISOString();

  // Apply character updates
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

  // Add new characters
  if (result.newCharacters?.length) {
    for (const newChar of result.newCharacters) {
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

  // Store new important facts
  if (result.importantFacts?.length) {
    await addFacts(sessionId, result.importantFacts);
  }

  // Save to meta history
  const history = await getMetaHistory(sessionId);
  history.push({
    timestamp: now,
    chunkRange: {
      from: recentChunks[0]?.id,
      to: recentChunks[recentChunks.length - 1]?.id,
      count: recentChunks.length,
    },
    status: 'success',
    result: {
      characterUpdates: result.characterUpdates || [],
      newCharacters: result.newCharacters || [],
      consistencyFlags: result.consistencyFlags || [],
      importantFacts: result.importantFacts || [],
    },
    rawResponse,
  });
  await writeJSON(metaHistoryFile(sessionId), history);

  return {
    characters,
    consistencyFlags: result.consistencyFlags || [],
    newCharacters: result.newCharacters || [],
    importantFacts: result.importantFacts || [],
  };
}
