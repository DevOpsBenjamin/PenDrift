import path from 'node:path';
import { SESSIONS_DIR } from '../utils/paths.js';
import { readJSON, writeJSON } from './storage.js';

function factsFile(sessionId) {
  return path.join(SESSIONS_DIR, sessionId, 'facts.json');
}

export async function getFacts(sessionId) {
  return await readJSON(factsFile(sessionId)) || [];
}

export async function addFacts(sessionId, newFacts) {
  if (!newFacts?.length) return;
  const existing = await getFacts(sessionId);
  // Deduplicate by checking if the fact is already present (simple string match)
  const unique = newFacts.filter(f => !existing.includes(f));
  if (unique.length > 0) {
    existing.push(...unique);
    await writeJSON(factsFile(sessionId), existing);
  }
  return existing;
}
