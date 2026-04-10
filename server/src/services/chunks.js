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

export async function appendChunk(sessionId, { chapterId, narrative, directive, isKeyMoment }) {
  const chunks = await getChunks(sessionId);

  const chunk = {
    id: uuidv4(),
    sessionId,
    chapterId,
    narrative,
    directive: directive || null,
    imagePrompt: null,
    imagePath: null,
    audioPath: null,
    isKeyMoment: isKeyMoment || false,
    createdAt: new Date().toISOString(),
  };

  chunks.push(chunk);
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
