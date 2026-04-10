import path from 'node:path';
import { v4 as uuidv4 } from 'uuid';
import { SESSIONS_DIR } from '../utils/paths.js';
import { readJSON, writeJSON } from './storage.js';

function chunksFile(sessionId) {
  return path.join(SESSIONS_DIR, sessionId, 'chunks.json');
}

export async function getChunks(sessionId) {
  return await readJSON(chunksFile(sessionId)) || [];
}

export async function getChunksByChapter(sessionId, chapterId) {
  const chunks = await getChunks(sessionId);
  return chunks.filter(c => c.chapterId === chapterId);
}

/**
 * Get the active version of a chunk.
 */
export function getActiveVersion(chunk) {
  if (!chunk.versions?.length) {
    // Legacy chunk without versions — return the chunk itself
    return chunk;
  }
  return chunk.versions[chunk.activeVersion ?? 0];
}

/**
 * Get the active narrative text from a chunk.
 */
export function getActiveNarrative(chunk) {
  return getActiveVersion(chunk).narrative;
}

/**
 * Create a new chunk with its first version.
 */
export async function appendChunk(sessionId, { chapterId, narrative, thinking, stats, directive, isKeyMoment, from }) {
  const chunks = await getChunks(sessionId);

  const chunk = {
    id: uuidv4(),
    sessionId,
    chapterId,
    activeVersion: 0,
    versions: [
      {
        narrative,
        thinking: thinking || null,
        stats: stats || null,
        directive: directive || null,
        from: from || null,
        createdAt: new Date().toISOString(),
      },
    ],
    isKeyMoment: isKeyMoment || false,
    imagePrompt: null,
    imagePath: null,
    audioPath: null,
  };

  chunks.push(chunk);
  await writeJSON(chunksFile(sessionId), chunks);
  return chunk;
}

/**
 * Add a new version to an existing chunk (swipe/retry/edit).
 */
export async function addChunkVersion(sessionId, chunkId, { narrative, thinking, stats, directive, from }) {
  const chunks = await getChunks(sessionId);
  const chunk = chunks.find(c => c.id === chunkId);
  if (!chunk) {
    throw Object.assign(new Error('Chunk not found'), { status: 404 });
  }

  // Migrate legacy chunk to versioned format
  if (!chunk.versions) {
    chunk.versions = [{
      narrative: chunk.narrative,
      thinking: chunk.thinking || null,
      stats: chunk.stats || null,
      directive: chunk.directive || null,
      createdAt: chunk.createdAt,
    }];
    chunk.activeVersion = 0;
    delete chunk.narrative;
    delete chunk.thinking;
    delete chunk.stats;
    delete chunk.directive;
  }

  const newIndex = chunk.versions.length;
  chunk.versions.push({
    narrative,
    thinking: thinking || null,
    stats: stats || null,
    directive: directive || null,
    from: from || null,
    createdAt: new Date().toISOString(),
  });
  chunk.activeVersion = newIndex;

  await writeJSON(chunksFile(sessionId), chunks);
  return chunk;
}

/**
 * Set which version is active for a chunk.
 */
export async function setActiveVersion(sessionId, chunkId, versionIndex) {
  const chunks = await getChunks(sessionId);
  const chunk = chunks.find(c => c.id === chunkId);
  if (!chunk) {
    throw Object.assign(new Error('Chunk not found'), { status: 404 });
  }
  if (versionIndex < 0 || versionIndex >= chunk.versions.length) {
    throw Object.assign(new Error('Version index out of range'), { status: 400 });
  }

  chunk.activeVersion = versionIndex;
  await writeJSON(chunksFile(sessionId), chunks);
  return chunk;
}

export async function deleteLastChunk(sessionId, chapterId) {
  const chunks = await getChunks(sessionId);
  const chapterChunks = chunks.filter(c => c.chapterId === chapterId);

  if (chapterChunks.length === 0) {
    throw Object.assign(new Error('No chunks to delete'), { status: 400 });
  }

  const lastChunk = chapterChunks[chapterChunks.length - 1];
  const filtered = chunks.filter(c => c.id !== lastChunk.id);
  await writeJSON(chunksFile(sessionId), filtered);
  return lastChunk;
}

export async function getLastChunk(sessionId, chapterId) {
  const chunks = await getChunksByChapter(sessionId, chapterId);
  return chunks[chunks.length - 1] || null;
}
