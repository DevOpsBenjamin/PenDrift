import { Router } from 'express';
import { getSession, updateSession } from '../services/sessions.js';
import { getSettingsPreset } from '../services/presets.js';
import { getTemplate } from '../services/templates.js';
import { getChunksByChapter, appendChunk, deleteLastChunk, getLastChunk } from '../services/chunks.js';
import { getCharacters, runMetaAnalysis, getMetaHistory } from '../services/characters.js';
import { getFacts } from '../services/facts.js';
import { generateCompletion } from '../services/llm.js';
import { buildMessages } from '../services/prompts.js';
import { v4 as uuidv4 } from 'uuid';
import path from 'node:path';
import { SESSIONS_DIR } from '../utils/paths.js';
import { writeJSON } from '../services/storage.js';

const router = Router({ mergeParams: true });

// Track in-progress meta-analysis per session
const metaStatus = new Map();

// === GENERATE ===

router.post('/generate', async (req, res) => {
  try {
    const sessionId = req.params.sessionId || req.sessionId;
    const { chapterId, directive, isKeyMoment } = req.body;

    if (!directive) {
      return res.status(400).json({ message: 'directive is required' });
    }

    const session = await getSession(sessionId);
    const chapter = session.chapters.find(c => c.id === chapterId);
    if (!chapter) {
      return res.status(404).json({ message: 'Chapter not found' });
    }

    const settings = await getSettingsPreset(session.settingsPresetId);
    const template = await getTemplate(session.templateId);
    const characters = await getCharacters(sessionId);
    const importantFacts = await getFacts(sessionId);
    const chunks = await getChunksByChapter(sessionId, chapterId);

    const messages = buildMessages({ settings, characters, template, chunks, directive, importantFacts });
    const { narrative, thinking } = await generateCompletion(messages, settings);

    if (!narrative) {
      return res.status(502).json({ message: 'LLM returned empty narrative' });
    }

    const chunk = await appendChunk(sessionId, {
      chapterId,
      narrative,
      directive,
      isKeyMoment: isKeyMoment || false,
    });

    await updateSession(sessionId, {});

    const allChapterChunks = await getChunksByChapter(sessionId, chapterId);
    const interval = settings.chunkUpdateInterval || 10;
    const shouldUpdate = allChapterChunks.length > 0 && allChapterChunks.length % interval === 0;

    if (shouldUpdate || isKeyMoment) {
      metaStatus.set(sessionId, { status: 'updating', result: null });
      const recentChunks = allChapterChunks.slice(-interval);
      runMetaAnalysis(sessionId, recentChunks, settings)
        .then(result => metaStatus.set(sessionId, { status: 'done', result }))
        .catch(() => metaStatus.set(sessionId, { status: 'failed', result: null }));
    }

    res.json({
      chunk,
      thinking: thinking || null,
      metaUpdatePending: shouldUpdate || isKeyMoment || false,
    });
  } catch (err) {
    console.error('Generate error:', err);
    res.status(err.status || 500).json({ message: err.message });
  }
});

router.post('/regenerate', async (req, res) => {
  try {
    const sessionId = req.params.sessionId || req.sessionId;
    const { chapterId } = req.body;

    if (!chapterId) {
      return res.status(400).json({ message: 'chapterId is required' });
    }

    const lastChunk = await getLastChunk(sessionId, chapterId);
    if (!lastChunk) {
      return res.status(400).json({ message: 'No chunks to regenerate' });
    }

    const directive = lastChunk.directive;
    if (!directive) {
      return res.status(400).json({ message: 'Last chunk has no directive to regenerate from' });
    }

    await deleteLastChunk(sessionId, chapterId);

    const session = await getSession(sessionId);
    const settings = await getSettingsPreset(session.settingsPresetId);
    const template = await getTemplate(session.templateId);
    const characters = await getCharacters(sessionId);
    const importantFacts = await getFacts(sessionId);
    const chunks = await getChunksByChapter(sessionId, chapterId);

    const messages = buildMessages({ settings, characters, template, chunks, directive, importantFacts });
    const { narrative, thinking } = await generateCompletion(messages, settings);

    if (!narrative) {
      return res.status(502).json({ message: 'LLM returned empty narrative' });
    }

    const chunk = await appendChunk(sessionId, {
      chapterId,
      narrative,
      directive,
      isKeyMoment: lastChunk.isKeyMoment,
    });

    await updateSession(sessionId, {});
    res.json({ chunk, thinking: thinking || null });
  } catch (err) {
    console.error('Regenerate error:', err);
    res.status(err.status || 500).json({ message: err.message });
  }
});

router.delete('/chunks/last', async (req, res) => {
  try {
    const sessionId = req.params.sessionId || req.sessionId;
    const { chapterId } = req.query;

    if (!chapterId) {
      return res.status(400).json({ message: 'chapterId query param is required' });
    }

    const deleted = await deleteLastChunk(sessionId, chapterId);
    res.json({ deleted });
  } catch (err) {
    res.status(err.status || 500).json({ message: err.message });
  }
});

router.get('/meta/status', (req, res) => {
  const sessionId = req.params.sessionId || req.sessionId;
  const meta = metaStatus.get(sessionId) || { status: 'idle', result: null };
  res.json(meta);
});

// === CHARACTERS ===

router.get('/characters', async (req, res) => {
  try {
    const sessionId = req.params.sessionId || req.sessionId;
    const characters = await getCharacters(sessionId);
    res.json(characters);
  } catch (err) {
    res.status(err.status || 500).json({ message: err.message });
  }
});

router.post('/characters/update', async (req, res) => {
  try {
    const sessionId = req.params.sessionId || req.sessionId;
    const { chapterId } = req.body;

    const session = await getSession(sessionId);
    const settings = await getSettingsPreset(session.settingsPresetId);

    let chunks = [];
    if (chapterId) {
      chunks = await getChunksByChapter(sessionId, chapterId);
    }

    const interval = settings.chunkUpdateInterval || 10;
    const recentChunks = chunks.slice(-interval);

    const result = await runMetaAnalysis(sessionId, recentChunks, settings);
    res.json(result);
  } catch (err) {
    res.status(err.status || 500).json({ message: err.message });
  }
});

router.get('/characters/meta-history', async (req, res) => {
  try {
    const sessionId = req.params.sessionId || req.sessionId;
    const history = await getMetaHistory(sessionId);
    res.json(history);
  } catch (err) {
    res.status(err.status || 500).json({ message: err.message });
  }
});

// === CHAPTERS ===

router.get('/chapters', async (req, res) => {
  try {
    const sessionId = req.params.sessionId || req.sessionId;
    const session = await getSession(sessionId);
    res.json(session.chapters);
  } catch (err) {
    res.status(err.status || 500).json({ message: err.message });
  }
});

router.get('/chapters/:chapterId', async (req, res) => {
  try {
    const sessionId = req.params.sessionId || req.sessionId;
    const { chapterId } = req.params;
    const session = await getSession(sessionId);
    const chapter = session.chapters.find(c => c.id === chapterId);
    if (!chapter) {
      return res.status(404).json({ message: 'Chapter not found' });
    }
    const chunks = await getChunksByChapter(sessionId, chapterId);
    res.json({ ...chapter, chunks });
  } catch (err) {
    res.status(err.status || 500).json({ message: err.message });
  }
});

router.post('/chapters', async (req, res) => {
  try {
    const sessionId = req.params.sessionId || req.sessionId;
    const { title } = req.body;
    const session = await getSession(sessionId);

    const chapter = {
      id: uuidv4(),
      title: title || `Chapter ${session.chapters.length + 1}`,
      order: session.chapters.length,
      createdAt: new Date().toISOString(),
    };

    session.chapters.push(chapter);
    await writeJSON(path.join(SESSIONS_DIR, sessionId, 'session.json'), session);

    res.status(201).json(chapter);
  } catch (err) {
    res.status(err.status || 500).json({ message: err.message });
  }
});

router.put('/chapters/:chapterId', async (req, res) => {
  try {
    const sessionId = req.params.sessionId || req.sessionId;
    const { chapterId } = req.params;
    const { title } = req.body;
    const session = await getSession(sessionId);

    const chapter = session.chapters.find(c => c.id === chapterId);
    if (!chapter) {
      return res.status(404).json({ message: 'Chapter not found' });
    }

    if (title) chapter.title = title;
    await writeJSON(path.join(SESSIONS_DIR, sessionId, 'session.json'), session);

    res.json(chapter);
  } catch (err) {
    res.status(err.status || 500).json({ message: err.message });
  }
});

export default router;
