import { Router } from 'express';
import { v4 as uuidv4 } from 'uuid';
import { getSession, updateSession } from '../services/sessions.js';
import { getChunksByChapter } from '../services/chunks.js';

const router = Router({ mergeParams: true });

// List chapters for a session
router.get('/', async (req, res) => {
  try {
    const session = await getSession(req.params.sessionId);
    res.json(session.chapters);
  } catch (err) {
    res.status(err.status || 500).json({ message: err.message });
  }
});

// Get a chapter with its chunks
router.get('/:chapterId', async (req, res) => {
  try {
    const { sessionId, chapterId } = req.params;
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

// Create a new chapter
router.post('/', async (req, res) => {
  try {
    const { sessionId } = req.params;
    const { title } = req.body;
    const session = await getSession(sessionId);

    const chapter = {
      id: uuidv4(),
      title: title || `Chapter ${session.chapters.length + 1}`,
      order: session.chapters.length,
      createdAt: new Date().toISOString(),
    };

    session.chapters.push(chapter);
    await updateSession(sessionId, {});

    // We need to write the full session since updateSession only handles allowed fields
    // Let's use a direct write instead
    const path = await import('node:path');
    const { SESSIONS_DIR } = await import('../utils/paths.js');
    const { writeJSON } = await import('../services/storage.js');
    await writeJSON(path.join(SESSIONS_DIR, sessionId, 'session.json'), session);

    res.status(201).json(chapter);
  } catch (err) {
    res.status(err.status || 500).json({ message: err.message });
  }
});

export default router;
