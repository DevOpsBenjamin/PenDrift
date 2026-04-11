import path from 'node:path';
import { v4 as uuidv4 } from 'uuid';
import { SESSIONS_DIR } from '../utils/paths.js';
import { readJSON, writeJSON, ensureDir, listFiles, fileExists, deleteFile } from './storage.js';

function chunksDir(sessionId) {
  return path.join(SESSIONS_DIR, sessionId, 'chunks');
}

function chunkFile(sessionId, chunkId) {
  return path.join(chunksDir(sessionId), `${chunkId}.json`);
}

function orderFile(sessionId) {
  return path.join(chunksDir(sessionId), 'order.json');
}

function legacyChunksFile(sessionId) {
  return path.join(SESSIONS_DIR, sessionId, 'chunks.json');
}

/**
 * Migrate from single chunks.json to directory structure if needed.
 */
async function migrateIfNeeded(sessionId) {
  const legacy = legacyChunksFile(sessionId);
  const dir = chunksDir(sessionId);

  if (await fileExists(legacy) && !(await fileExists(orderFile(sessionId)))) {
    console.log(`[Migration] Migrating chunks for session ${sessionId.slice(0, 8)}...`);
    const chunks = await readJSON(legacy) || [];
    await ensureDir(dir);

    const order = [];
    for (const chunk of chunks) {
      await writeJSON(chunkFile(sessionId, chunk.id), chunk);
      order.push(chunk.id);
    }
    await writeJSON(orderFile(sessionId), order);

    // Rename old file as backup
    const fs = await import('node:fs/promises');
    await fs.rename(legacy, legacy + '.bak');
    console.log(`[Migration] Done — ${chunks.length} chunks migrated`);
  }
}

export async function getChunks(sessionId) {
  await migrateIfNeeded(sessionId);
  const order = await readJSON(orderFile(sessionId)) || [];
  const chunks = [];
  for (const id of order) {
    const chunk = await readJSON(chunkFile(sessionId, id));
    if (chunk) chunks.push(chunk);
  }
  return chunks;
}

export async function getChunksByChapter(sessionId, chapterId) {
  const chunks = await getChunks(sessionId);
  return chunks.filter(c => c.chapterId === chapterId);
}

export function getActiveVersion(chunk) {
  if (!chunk.versions?.length) return chunk;
  return chunk.versions[chunk.activeVersion ?? 0];
}

export function getActiveNarrative(chunk) {
  return getActiveVersion(chunk).narrative;
}

export async function appendChunk(sessionId, { chapterId, narrative, thinking, stats, directive, isKeyMoment, from }) {
  await migrateIfNeeded(sessionId);
  await ensureDir(chunksDir(sessionId));

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

  await writeJSON(chunkFile(sessionId, chunk.id), chunk);

  const order = await readJSON(orderFile(sessionId)) || [];
  order.push(chunk.id);
  await writeJSON(orderFile(sessionId), order);

  return chunk;
}

export async function addChunkVersion(sessionId, chunkId, { narrative, thinking, stats, directive, from }) {
  await migrateIfNeeded(sessionId);
  const chunk = await readJSON(chunkFile(sessionId, chunkId));
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
      from: chunk.from || null,
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

  await writeJSON(chunkFile(sessionId, chunkId), chunk);
  return chunk;
}

export async function setActiveVersion(sessionId, chunkId, versionIndex) {
  const chunk = await readJSON(chunkFile(sessionId, chunkId));
  if (!chunk) {
    throw Object.assign(new Error('Chunk not found'), { status: 404 });
  }
  if (versionIndex < 0 || versionIndex >= chunk.versions.length) {
    throw Object.assign(new Error('Version index out of range'), { status: 400 });
  }

  chunk.activeVersion = versionIndex;
  await writeJSON(chunkFile(sessionId, chunkId), chunk);
  return chunk;
}

export async function deleteLastChunk(sessionId, chapterId) {
  await migrateIfNeeded(sessionId);
  const order = await readJSON(orderFile(sessionId)) || [];
  const chunks = await getChunks(sessionId);
  const chapterChunks = chunks.filter(c => c.chapterId === chapterId);

  if (chapterChunks.length === 0) {
    throw Object.assign(new Error('No chunks to delete'), { status: 400 });
  }

  const lastChunk = chapterChunks[chapterChunks.length - 1];

  // Remove from order
  const newOrder = order.filter(id => id !== lastChunk.id);
  await writeJSON(orderFile(sessionId), newOrder);

  // Delete chunk file
  await deleteFile(chunkFile(sessionId, lastChunk.id));

  return lastChunk;
}

export async function getLastChunk(sessionId, chapterId) {
  const chunks = await getChunksByChapter(sessionId, chapterId);
  return chunks[chunks.length - 1] || null;
}

/**
 * Get a single chunk by ID.
 */
export async function getChunkById(sessionId, chunkId) {
  await migrateIfNeeded(sessionId);
  return await readJSON(chunkFile(sessionId, chunkId));
}

/**
 * Save a single chunk (for direct edits from routes).
 */
export async function saveChunk(sessionId, chunk) {
  await writeJSON(chunkFile(sessionId, chunk.id), chunk);
}
