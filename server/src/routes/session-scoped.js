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
    if (chapter.finalized) {
      return res.status(400).json({ message: 'Cannot generate in a finalized chapter' });
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
    const chunks = await getChunksByChapter(sessionId, chapterId);
    const interval = settings.chunkUpdateInterval || 10;

    // Meta trigger: run BEFORE generating if we've crossed the threshold
    // e.g. we have 10 chunks and are about to generate the 11th
    let metaRanNow = false;
    const lastMetaAfterChunk = session.lastMetaAfterChunkIndex ?? null;

    if (chunks.length > 0 && chunks.length % interval === 0 && lastMetaAfterChunk !== chunks.length - 1) {
      console.log(`[Meta] Running meta-analysis before chunk ${chunks.length + 1} (threshold: ${interval})`);
      metaStatus.set(sessionId, { status: 'updating', result: null });
      try {
        const metaChunks = chunks.slice(-interval);
        const result = await runMetaAnalysis(sessionId, metaChunks, settings);
        metaStatus.set(sessionId, { status: 'done', result });

        // Store where meta was run in session
        session.lastMetaAfterChunkIndex = chunks.length - 1;
        await writeJSON(path.join(SESSIONS_DIR, sessionId, 'session.json'), session);
        metaRanNow = true;
      } catch (err) {
        console.error('[Meta] Analysis failed:', err.message);
        metaStatus.set(sessionId, { status: 'failed', result: null });
      }
    }

    // Key moment also triggers meta
    if (isKeyMoment && !metaRanNow) {
      console.log('[Meta] Key moment triggered meta-analysis');
      metaStatus.set(sessionId, { status: 'updating', result: null });
      try {
        const metaChunks = chunks.slice(-interval);
        const result = await runMetaAnalysis(sessionId, metaChunks, settings);
        metaStatus.set(sessionId, { status: 'done', result });
        session.lastMetaAfterChunkIndex = chunks.length - 1;
        await writeJSON(path.join(SESSIONS_DIR, sessionId, 'session.json'), session);
        metaRanNow = true;
      } catch (err) {
        console.error('[Meta] Key moment analysis failed:', err.message);
        metaStatus.set(sessionId, { status: 'failed', result: null });
      }
    }

    // Now generate with fresh characters/facts (meta may have updated them)
    const characters = await getCharacters(sessionId);
    const importantFacts = await getFacts(sessionId);

    // Cross-chapter context: if this chapter is empty, get previous chapter's last chunks
    let previousChapterChunks = null;
    if (chunks.length === 0) {
      const chapterIdx = session.chapters.findIndex(c => c.id === chapterId);
      if (chapterIdx > 0) {
        const prevChapterId = session.chapters[chapterIdx - 1].id;
        previousChapterChunks = await getChunksByChapter(sessionId, prevChapterId);
      }
    }

    const messages = buildMessages({
      settings, characters, template, chunks, directive, importantFacts,
      lastMetaAfterChunkIndex: session.lastMetaAfterChunkIndex ?? null,
      previousChapterChunks,
    });
    const { narrative, thinking, stats, modelName } = await generateCompletion(messages, settings, null, sessionId, 'narrative');

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
      from: modelName,
    });

    await updateSession(sessionId, {});

    jobs.set(jobId, {
      ...jobs.get(jobId),
      status: 'done',
      result: { chunk, thinking: thinking || null, metaUpdatePending: metaRanNow },
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
    const { narrative, thinking, stats, modelName } = await generateCompletion(messages, settings, null, sessionId, 'narrative');

    if (!narrative) {
      jobs.set(jobId, { ...jobs.get(jobId), status: 'failed', error: 'LLM returned empty narrative' });
      return;
    }

    const updatedChunk = await addChunkVersion(sessionId, targetChunk.id, {
      narrative, thinking, stats, directive, from: modelName,
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
      from: 'manual edit',
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

    const { getChunkById, saveChunk, deleteLastChunk: delChunk } = await import('../services/chunks.js');
    const { readJSON: rJSON, writeJSON: wJSON, deleteFile: delFile } = await import('../services/storage.js');
    const { SESSIONS_DIR: SD } = await import('../utils/paths.js');
    const p = await import('node:path');

    const chunk = await getChunkById(sessionId, chunkId);
    if (!chunk) {
      return res.status(404).json({ message: 'Chunk not found' });
    }

    if (!chunk.versions || chunk.versions.length <= 1) {
      // Delete the whole chunk
      const orderPath = p.join(SD, sessionId, 'chunks', 'order.json');
      const order = await rJSON(orderPath) || [];
      await wJSON(orderPath, order.filter(id => id !== chunkId));
      await delFile(p.join(SD, sessionId, 'chunks', `${chunkId}.json`));
      return res.json({ deleted: 'chunk' });
    }

    const idx = versionIndex ?? chunk.activeVersion ?? 0;
    chunk.versions.splice(idx, 1);
    if (chunk.activeVersion >= chunk.versions.length) {
      chunk.activeVersion = chunk.versions.length - 1;
    }

    await saveChunk(sessionId, chunk);
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
    const { getApiLogs } = await import('../services/api-logger.js');
    const logs = await getApiLogs(sessionId);
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

// Save a single character sheet (manual edit)
router.put('/characters/:charName', async (req, res) => {
  try {
    const sessionId = req.params.sessionId || req.sessionId;
    const { charName } = req.params;
    const update = req.body;

    const { saveCharacters } = await import('../services/characters.js');
    const characters = await getCharacters(sessionId);
    const idx = characters.findIndex(c => c.name === decodeURIComponent(charName));
    if (idx === -1) {
      return res.status(404).json({ message: 'Character not found' });
    }

    characters[idx] = { ...characters[idx], ...update };
    await saveCharacters(sessionId, characters);
    res.json(characters[idx]);
  } catch (err) {
    res.status(err.status || 500).json({ message: err.message });
  }
});

// Get/save facts
router.get('/facts', async (req, res) => {
  try {
    const sessionId = req.params.sessionId || req.sessionId;
    const facts = await getFacts(sessionId);
    res.json(facts);
  } catch (err) {
    res.status(err.status || 500).json({ message: err.message });
  }
});

router.put('/facts', async (req, res) => {
  try {
    const sessionId = req.params.sessionId || req.sessionId;
    const { facts } = req.body;

    const { SESSIONS_DIR } = await import('../utils/paths.js');
    await writeJSON(path.join(SESSIONS_DIR, sessionId, 'facts.json'), facts || []);
    res.json(facts || []);
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

// Finalize current chapter: run meta, generate title, create next chapter
router.post('/chapters/finalize', async (req, res) => {
  try {
    const sessionId = req.params.sessionId || req.sessionId;
    const { chapterId } = req.body;

    const session = await getSession(sessionId);
    const chapter = session.chapters.find(c => c.id === chapterId);
    if (!chapter) {
      return res.status(404).json({ message: 'Chapter not found' });
    }
    if (chapter.finalized) {
      return res.status(400).json({ message: 'Chapter already finalized' });
    }

    const settings = await getSettingsPreset(session.settingsPresetId);
    const chunks = await getChunksByChapter(sessionId, chapterId);

    // Run meta-analysis on recent chunks (not all)
    if (chunks.length > 0) {
      const interval = settings.chunkUpdateInterval || 5;
      const recentChunks = chunks.slice(-interval);
      console.log(`[Finalize] Running meta-analysis on chapter "${chapter.title}" (${recentChunks.length} of ${chunks.length} chunks)`);
      await runMetaAnalysis(sessionId, recentChunks, settings);
      session.lastMetaAfterChunkIndex = null; // Reset for new chapter
    }

    // Generate chapter title from the LLM
    let generatedTitle = `Chapter ${chapter.order + 1}`;
    try {
      const getNarrative = (c) => {
        if (c.versions?.length) return c.versions[c.activeVersion ?? 0].narrative;
        return c.narrative;
      };

      // Build title prompt: 2 first, 1 middle, 2 last chunks + meta summary
      const titleMessages = [
        { role: 'system', content: 'You are a chapter title generator for a novel. You will receive excerpts from the beginning, middle, and end of a chapter, plus a meta-analysis summary. Suggest a short, evocative chapter title (3-6 words max). Return ONLY the title, nothing else. No quotes, no explanation.' },
      ];

      // First 2 chunks
      if (chunks.length >= 1) {
        titleMessages.push({ role: 'user', content: 'This is the BEGINNING of the chapter:' });
        titleMessages.push({ role: 'assistant', content: getNarrative(chunks[0]).slice(0, 500) });
        if (chunks.length >= 2) {
          titleMessages.push({ role: 'assistant', content: getNarrative(chunks[1]).slice(0, 500) });
        }
      }

      // Middle chunk
      if (chunks.length >= 5) {
        const midIdx = Math.floor(chunks.length / 2);
        titleMessages.push({ role: 'user', content: 'This is the MIDDLE of the chapter:' });
        titleMessages.push({ role: 'assistant', content: getNarrative(chunks[midIdx]).slice(0, 500) });
      }

      // Last 2 chunks
      if (chunks.length >= 3) {
        titleMessages.push({ role: 'user', content: 'This is the END of the chapter:' });
        if (chunks.length >= 4) {
          titleMessages.push({ role: 'assistant', content: getNarrative(chunks[chunks.length - 2]).slice(0, 500) });
        }
        titleMessages.push({ role: 'assistant', content: getNarrative(chunks[chunks.length - 1]).slice(0, 500) });
      }

      // Meta summary
      const characters = await getCharacters(sessionId);
      const importantFacts = await getFacts(sessionId);
      let metaSummary = 'Meta-analysis summary:\n';
      metaSummary += 'Characters: ' + characters.map(c => `${c.name} (${c.currentState})`).join('; ') + '\n';
      if (importantFacts.length) {
        metaSummary += 'Key facts: ' + importantFacts.slice(-5).join('; ');
      }
      titleMessages.push({ role: 'user', content: metaSummary + '\n\nBased on all of the above, suggest a chapter title.' });

      const metaModel = settings.metaModel || settings.narrativeModel;
      const titleSettings = { ...settings, maxTokens: (settings.maxTokens || 1024) * 2 };
      const { narrative: titleResult } = await generateCompletion(titleMessages, titleSettings, metaModel, sessionId, 'title');
      if (titleResult && titleResult.length < 80) {
        generatedTitle = titleResult.replace(/["']/g, '').trim();
      }
    } catch (err) {
      console.error('[Finalize] Title generation failed:', err.message);
    }

    // Finalize the chapter
    chapter.finalized = true;
    chapter.title = generatedTitle;

    // Create new chapter
    const newChapter = {
      id: uuidv4(),
      title: `Chapter ${session.chapters.length + 1}`,
      order: session.chapters.length,
      finalized: false,
      createdAt: new Date().toISOString(),
    };
    session.chapters.push(newChapter);

    await writeJSON(path.join(SESSIONS_DIR, sessionId, 'session.json'), session);

    res.json({ finalizedChapter: chapter, newChapter });
  } catch (err) {
    console.error('Finalize error:', err);
    res.status(err.status || 500).json({ message: err.message });
  }
});

// Regenerate chapter title only (no meta re-run)
router.post('/chapters/:chapterId/regen-title', async (req, res) => {
  try {
    const sessionId = req.params.sessionId || req.sessionId;
    const { chapterId } = req.params;

    const session = await getSession(sessionId);
    const chapter = session.chapters.find(c => c.id === chapterId);
    if (!chapter) {
      return res.status(404).json({ message: 'Chapter not found' });
    }

    const settings = await getSettingsPreset(session.settingsPresetId);
    const chunks = await getChunksByChapter(sessionId, chapterId);

    const getNarrative = (c) => {
      if (c.versions?.length) return c.versions[c.activeVersion ?? 0].narrative;
      return c.narrative;
    };

    const titleMessages = [
      { role: 'system', content: 'You are a chapter title generator for a novel. You will receive excerpts from the beginning, middle, and end of a chapter, plus a meta-analysis summary. Suggest a short, evocative chapter title (3-6 words max). Return ONLY the title, nothing else. No quotes, no explanation.' },
    ];

    if (chunks.length >= 1) {
      titleMessages.push({ role: 'user', content: 'This is the BEGINNING of the chapter:' });
      titleMessages.push({ role: 'assistant', content: getNarrative(chunks[0]).slice(0, 500) });
      if (chunks.length >= 2) {
        titleMessages.push({ role: 'assistant', content: getNarrative(chunks[1]).slice(0, 500) });
      }
    }

    if (chunks.length >= 5) {
      const midIdx = Math.floor(chunks.length / 2);
      titleMessages.push({ role: 'user', content: 'This is the MIDDLE of the chapter:' });
      titleMessages.push({ role: 'assistant', content: getNarrative(chunks[midIdx]).slice(0, 500) });
    }

    if (chunks.length >= 3) {
      titleMessages.push({ role: 'user', content: 'This is the END of the chapter:' });
      if (chunks.length >= 4) {
        titleMessages.push({ role: 'assistant', content: getNarrative(chunks[chunks.length - 2]).slice(0, 500) });
      }
      titleMessages.push({ role: 'assistant', content: getNarrative(chunks[chunks.length - 1]).slice(0, 500) });
    }

    const characters = await getCharacters(sessionId);
    const importantFacts = await getFacts(sessionId);
    let metaSummary = 'Meta-analysis summary:\n';
    metaSummary += 'Characters: ' + characters.map(c => `${c.name} (${c.currentState})`).join('; ') + '\n';
    if (importantFacts.length) {
      metaSummary += 'Key facts: ' + importantFacts.slice(-5).join('; ');
    }
    titleMessages.push({ role: 'user', content: metaSummary + '\n\nBased on all of the above, suggest a chapter title.' });

    const metaModel = settings.metaModel || settings.narrativeModel;
    const titleSettings = { ...settings, maxTokens: (settings.maxTokens || 1024) * 2 };
    const { narrative: titleResult } = await generateCompletion(titleMessages, titleSettings, metaModel, sessionId, 'title');

    if (titleResult && titleResult.length < 80) {
      chapter.title = titleResult.replace(/["']/g, '').trim();
      await writeJSON(path.join(SESSIONS_DIR, sessionId, 'session.json'), session);
    }

    res.json(chapter);
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
