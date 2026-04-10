import { Router } from 'express';
import { getSession, updateSession } from '../services/sessions.js';
import { getSettingsPreset } from '../services/presets.js';
import { getTemplate } from '../services/templates.js';
import { getChunksByChapter, appendChunk, deleteLastChunk, getLastChunk } from '../services/chunks.js';
import { getCharacters, updateCharacterSheets } from '../services/characters.js';
import { generateCompletion } from '../services/llm.js';
import { buildMessages } from '../services/prompts.js';

const router = Router({ mergeParams: true });

// Track in-progress character updates per session
const characterUpdateStatus = new Map();

// Generate a new narrative chunk
router.post('/generate', async (req, res) => {
  try {
    const { sessionId } = req.params;
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
    const chunks = await getChunksByChapter(sessionId, chapterId);

    const messages = buildMessages({ settings, characters, template, chunks, directive });
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

    // Check if character sheet update is needed
    const allChapterChunks = await getChunksByChapter(sessionId, chapterId);
    const interval = settings.chunkUpdateInterval || 10;
    const shouldUpdate = allChapterChunks.length > 0 && allChapterChunks.length % interval === 0;

    if (shouldUpdate || isKeyMoment) {
      // Run character update asynchronously
      characterUpdateStatus.set(sessionId, 'updating');
      const recentChunks = allChapterChunks.slice(-interval);
      updateCharacterSheets(sessionId, recentChunks, settings)
        .then(() => characterUpdateStatus.set(sessionId, 'done'))
        .catch(() => characterUpdateStatus.set(sessionId, 'failed'));
    }

    res.json({
      chunk,
      thinking: thinking || null,
      characterUpdatePending: shouldUpdate || isKeyMoment || false,
    });
  } catch (err) {
    console.error('Generate error:', err);
    res.status(err.status || 500).json({ message: err.message });
  }
});

// Regenerate: delete last chunk and re-generate with its directive
router.post('/regenerate', async (req, res) => {
  try {
    const { sessionId } = req.params;
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

    // Delete the last chunk
    await deleteLastChunk(sessionId, chapterId);

    // Re-generate
    const session = await getSession(sessionId);
    const settings = await getSettingsPreset(session.settingsPresetId);
    const template = await getTemplate(session.templateId);
    const characters = await getCharacters(sessionId);
    const chunks = await getChunksByChapter(sessionId, chapterId);

    const messages = buildMessages({ settings, characters, template, chunks, directive });
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

// Delete the last chunk
router.delete('/chunks/last', async (req, res) => {
  try {
    const { sessionId } = req.params;
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

// Character update status
router.get('/characters/status', (req, res) => {
  const { sessionId } = req.params;
  const status = characterUpdateStatus.get(sessionId) || 'idle';
  res.json({ status });
});

export default router;
