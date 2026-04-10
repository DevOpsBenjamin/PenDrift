import { Router } from 'express';
import { getSession, updateSession } from '../services/sessions.js';
import { getSettingsPreset } from '../services/presets.js';
import { getTemplate } from '../services/templates.js';
import { getChunksByChapter, appendChunk, addChunkVersion, setActiveVersion, deleteLastChunk, getLastChunk, getActiveVersion } from '../services/chunks.js';
import { getCharacters, runMetaAnalysis, getMetaHistory } from '../services/characters.js';
import { getFacts } from '../services/facts.js';
import { generateCompletion } from '../services/llm.js';
import { buildMessages } from '../services/prompts.js';
import { v4 as uuidv4 } from 'uuid';
import path from 'node:path';
import { SESSIONS_DIR } from '../utils/paths.js';
import { writeJSON } from '../services/storage.js';

const router = Router({ mergeParams: true });

// Track in-progress jobs and meta-analysis
const jobs = new Map();
const metaStatus = new Map();

// === GENERATE (async job-based) ===

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

    // Create job and return immediately
    const jobId = `job_${Date.now()}_${Math.random().toString(36).slice(2, 8)}`;
    jobs.set(jobId, { status: 'generating', sessionId, chapterId, result: null, error: null });

    res.status(202).json({ jobId });

    // Run generation in background
    runGeneration(jobId, sessionId, chapterId, directive, isKeyMoment, session);
  } catch (err) {
    console.error('Generate error:', err);
    res.status(err.status || 500).json({ message: err.message });
  }
});

// Background generation logic
async function runGeneration(jobId, sessionId, chapterId, directive, isKeyMoment, session) {
  try {
    const settings = await getSettingsPreset(session.settingsPresetId);
    const template = await getTemplate(session.templateId);
    const characters = await getCharacters(sessionId);
    const importantFacts = await getFacts(sessionId);
    const chunks = await getChunksByChapter(sessionId, chapterId);

    const messages = buildMessages({ settings, characters, template, chunks, directive, importantFacts });
    const { narrative, thinking, stats } = await generateCompletion(messages, settings, null, sessionId, 'narrative');

    if (!narrative) {
      jobs.set(jobId, { ...jobs.get(jobId), status: 'failed', error: 'LLM returned empty narrative' });
      return;
    }

    const chunk = await appendChunk(sessionId, {
      chapterId,
      narrative,
      thinking: thinking || null,
      stats: stats || null,
      directive,
      isKeyMoment: isKeyMoment || false,
    });

    await updateSession(sessionId, {});

    // Check meta-analysis trigger
    const allChapterChunks = await getChunksByChapter(sessionId, chapterId);
    const interval = settings.chunkUpdateInterval || 10;
    const shouldUpdate = allChapterChunks.length > 0 && allChapterChunks.length % interval === 0;
    let metaUpdatePending = false;

    if (shouldUpdate || isKeyMoment) {
      metaUpdatePending = true;
      metaStatus.set(sessionId, { status: 'updating', result: null });
      const recentChunks = allChapterChunks.slice(-interval);
      runMetaAnalysis(sessionId, recentChunks, settings)
        .then(result => metaStatus.set(sessionId, { status: 'done', result }))
        .catch(() => metaStatus.set(sessionId, { status: 'failed', result: null }));
    }

    jobs.set(jobId, {
      ...jobs.get(jobId),
      status: 'done',
      result: { chunk, thinking: thinking || null, metaUpdatePending },
    });
  } catch (err) {
    console.error('Generation job failed:', err);
    jobs.set(jobId, { ...jobs.get(jobId), status: 'failed', error: err.message });
  }
}

// Poll job status
router.get('/jobs/:jobId', (req, res) => {
  const job = jobs.get(req.params.jobId);
  if (!job) {
    return res.status(404).json({ message: 'Job not found' });
  }
  res.json(job);
  // Clean up completed jobs after client reads them
  if (job.status === 'done' || job.status === 'failed') {
    setTimeout(() => jobs.delete(req.params.jobId), 30000);
  }
});

// Regenerate — adds a new version to the chunk instead of deleting
router.post('/regenerate', async (req, res) => {
  try {
    const sessionId = req.params.sessionId || req.sessionId;
    const { chunkId, directive: newDirective } = req.body;

    if (!chunkId) {
      return res.status(400).json({ message: 'chunkId is required' });
    }

    // Find the chunk
    const allChunks = await getChunksByChapter(sessionId, req.body.chapterId || '');
    let targetChunk;
    // Search across all chapters if chapterId not provided
    if (!req.body.chapterId) {
      const { getChunks } = await import('../services/chunks.js');
      const all = await getChunks(sessionId);
      targetChunk = all.find(c => c.id === chunkId);
    } else {
      targetChunk = allChunks.find(c => c.id === chunkId);
    }

    if (!targetChunk) {
      return res.status(404).json({ message: 'Chunk not found' });
    }

    // Get directive from the active version or use the provided one
    const activeVer = getActiveVersion(targetChunk);
    const directive = newDirective || activeVer.directive;
    if (!directive) {
      return res.status(400).json({ message: 'No directive to regenerate from' });
    }

    const session = await getSession(sessionId);
    const jobId = `job_${Date.now()}_${Math.random().toString(36).slice(2, 8)}`;
    jobs.set(jobId, { status: 'generating', sessionId, chunkId, result: null, error: null });

    res.status(202).json({ jobId });

    // Run generation and add as new version
    runRegenerationAsVersion(jobId, sessionId, targetChunk, directive, session);
  } catch (err) {
    console.error('Regenerate error:', err);
    res.status(err.status || 500).json({ message: err.message });
  }
});

// Regeneration background job — adds version instead of replacing
async function runRegenerationAsVersion(jobId, sessionId, targetChunk, directive, session) {
  try {
    const settings = await getSettingsPreset(session.settingsPresetId);
    const template = await getTemplate(session.templateId);
    const characters = await getCharacters(sessionId);
    const importantFacts = await getFacts(sessionId);

    // Get chunks BEFORE this chunk for context
    const allChunks = await getChunksByChapter(sessionId, targetChunk.chapterId);
    const chunkIndex = allChunks.findIndex(c => c.id === targetChunk.id);
    const contextChunks = allChunks.slice(0, chunkIndex);

    const messages = buildMessages({ settings, characters, template, chunks: contextChunks, directive, importantFacts });
    const { narrative, thinking, stats } = await generateCompletion(messages, settings, null, sessionId, 'narrative');

    if (!narrative) {
      jobs.set(jobId, { ...jobs.get(jobId), status: 'failed', error: 'LLM returned empty narrative' });
      return;
    }

    const updatedChunk = await addChunkVersion(sessionId, targetChunk.id, {
      narrative, thinking, stats, directive,
    });

    await updateSession(sessionId, {});

    jobs.set(jobId, {
      ...jobs.get(jobId),
      status: 'done',
      result: { chunk: updatedChunk },
    });
  } catch (err) {
    console.error('Regeneration job failed:', err);
    jobs.set(jobId, { ...jobs.get(jobId), status: 'failed', error: err.message });
  }
}

// Edit a chunk — adds a new version with edited narrative
router.put('/chunks/:chunkId', async (req, res) => {
  try {
    const sessionId = req.params.sessionId || req.sessionId;
    const { chunkId } = req.params;
    const { narrative } = req.body;

    if (!narrative) {
      return res.status(400).json({ message: 'narrative is required' });
    }

    // Get the current active version's data to preserve directive/thinking
    const { getChunks } = await import('../services/chunks.js');
    const allChunks = await getChunks(sessionId);
    const chunk = allChunks.find(c => c.id === chunkId);
    if (!chunk) {
      return res.status(404).json({ message: 'Chunk not found' });
    }

    const activeVer = chunk.versions?.[chunk.activeVersion ?? 0] || chunk;
    const updatedChunk = await addChunkVersion(sessionId, chunkId, {
      narrative,
      thinking: activeVer.thinking,
      stats: null,
      directive: activeVer.directive,
    });

    res.json(updatedChunk);
  } catch (err) {
    res.status(err.status || 500).json({ message: err.message });
  }
});

// Delete a version from a chunk (or the whole chunk if last version)
router.delete('/chunks/:chunkId/version', async (req, res) => {
  try {
    const sessionId = req.params.sessionId || req.sessionId;
    const { chunkId } = req.params;
    const { versionIndex } = req.body;

    const { getChunks } = await import('../services/chunks.js');
    const chunks = await getChunks(sessionId);
    const chunk = chunks.find(c => c.id === chunkId);
    if (!chunk) {
      return res.status(404).json({ message: 'Chunk not found' });
    }

    // Migrate legacy if needed
    if (!chunk.versions) {
      // Legacy chunk with no versions — delete the whole chunk
      const filtered = chunks.filter(c => c.id !== chunkId);
      await writeJSON(path.join(SESSIONS_DIR, sessionId, 'chunks.json'), filtered);
      return res.json({ deleted: 'chunk' });
    }

    const idx = versionIndex ?? chunk.activeVersion ?? 0;

    if (chunk.versions.length <= 1) {
      // Last version — delete the whole chunk
      const filtered = chunks.filter(c => c.id !== chunkId);
      await writeJSON(path.join(SESSIONS_DIR, sessionId, 'chunks.json'), filtered);
      return res.json({ deleted: 'chunk' });
    }

    // Remove the version
    chunk.versions.splice(idx, 1);
    // Adjust activeVersion
    if (chunk.activeVersion >= chunk.versions.length) {
      chunk.activeVersion = chunk.versions.length - 1;
    }

    await writeJSON(path.join(SESSIONS_DIR, sessionId, 'chunks.json'), chunks);
    res.json({ deleted: 'version', chunk });
  } catch (err) {
    res.status(err.status || 500).json({ message: err.message });
  }
});

// Switch active version of a chunk
router.put('/chunks/:chunkId/version', async (req, res) => {
  try {
    const sessionId = req.params.sessionId || req.sessionId;
    const { chunkId } = req.params;
    const { versionIndex } = req.body;

    if (versionIndex === undefined) {
      return res.status(400).json({ message: 'versionIndex is required' });
    }

    const updatedChunk = await setActiveVersion(sessionId, chunkId, versionIndex);
    res.json(updatedChunk);
  } catch (err) {
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

// === API LOGS ===

router.get('/api-logs', async (req, res) => {
  try {
    const sessionId = req.params.sessionId || req.sessionId;
    const { readJSON } = await import('../services/storage.js');
    const { SESSIONS_DIR } = await import('../utils/paths.js');
    const path = await import('node:path');
    const logs = await readJSON(path.join(SESSIONS_DIR, sessionId, 'api-logs.json')) || [];
    res.json(logs);
  } catch (err) {
    res.status(err.status || 500).json({ message: err.message });
  }
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
