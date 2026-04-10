import path from 'node:path';
import { v4 as uuidv4 } from 'uuid';
import { SESSIONS_DIR, TEMPLATES_DIR } from '../utils/paths.js';
import { readJSON, writeJSON, listFiles, deleteDir, ensureDir } from './storage.js';

function sessionDir(sessionId) {
  return path.join(SESSIONS_DIR, sessionId);
}

function sessionFile(sessionId) {
  return path.join(sessionDir(sessionId), 'session.json');
}

function chunksFile(sessionId) {
  return path.join(sessionDir(sessionId), 'chunks.json');
}

function charactersFile(sessionId) {
  return path.join(sessionDir(sessionId), 'characters.json');
}

function summariesFile(sessionId) {
  return path.join(sessionDir(sessionId), 'summaries.json');
}

export async function createSession({ templateId, title, settingsPresetId }) {
  const template = await readJSON(path.join(TEMPLATES_DIR, `${templateId}.json`));
  if (!template) {
    throw Object.assign(new Error(`Template '${templateId}' not found`), { status: 404 });
  }

  const sessionId = uuidv4();
  const firstChapterId = uuidv4();
  const now = new Date().toISOString();
  const vars = template.variables || {};

  // Resolve {{variables}} in text
  const resolve = (text) => {
    if (!text) return text;
    return text.replace(/\{\{(\w+)\}\}/g, (match, key) => vars[key] !== undefined ? vars[key] : match);
  };

  const session = {
    id: sessionId,
    title: title || template.name,
    templateId,
    settingsPresetId: settingsPresetId || 'default',
    chapters: [
      { id: firstChapterId, title: 'Chapter 1', order: 0, createdAt: now },
    ],
    coverImage: null,
    createdAt: now,
    updatedAt: now,
  };

  // Initialize character sheets from template
  const characters = (template.characters || []).map(c => ({
    name: resolve(c.name),
    currentState: resolve(c.initialState || ''),
    traits: [],
    keyEvents: [],
    lastUpdated: now,
  }));

  await ensureDir(path.join(sessionDir(sessionId), 'assets', 'images'));
  await ensureDir(path.join(sessionDir(sessionId), 'assets', 'audio'));
  await writeJSON(sessionFile(sessionId), session);
  await writeJSON(chunksFile(sessionId), []);
  await writeJSON(charactersFile(sessionId), characters);
  await writeJSON(summariesFile(sessionId), []);

  return session;
}

export async function listSessions() {
  const dirs = await listFiles(SESSIONS_DIR);
  const sessions = [];

  for (const dir of dirs) {
    const session = await readJSON(path.join(SESSIONS_DIR, dir, 'session.json'));
    if (session) sessions.push(session);
  }

  sessions.sort((a, b) => new Date(b.updatedAt) - new Date(a.updatedAt));
  return sessions;
}

export async function getSession(sessionId) {
  const session = await readJSON(sessionFile(sessionId));
  if (!session) {
    throw Object.assign(new Error('Session not found'), { status: 404 });
  }
  return session;
}

export async function updateSession(sessionId, updates) {
  const session = await getSession(sessionId);
  const allowed = ['title', 'settingsPresetId'];
  for (const key of allowed) {
    if (updates[key] !== undefined) {
      session[key] = updates[key];
    }
  }
  session.updatedAt = new Date().toISOString();
  await writeJSON(sessionFile(sessionId), session);
  return session;
}

export async function deleteSession(sessionId) {
  await deleteDir(sessionDir(sessionId));
}
