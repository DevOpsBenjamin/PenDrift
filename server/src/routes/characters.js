import { Router } from 'express';
import { getCharacters, updateCharacterSheets } from '../services/characters.js';
import { getSession } from '../services/sessions.js';
import { getSettingsPreset } from '../services/presets.js';
import { getChunksByChapter } from '../services/chunks.js';

const router = Router({ mergeParams: true });

router.get('/', async (req, res) => {
  try {
    const characters = await getCharacters(req.params.sessionId);
    res.json(characters);
  } catch (err) {
    res.status(err.status || 500).json({ message: err.message });
  }
});

// Manual trigger for character sheet update
router.post('/update', async (req, res) => {
  try {
    const { sessionId } = req.params;
    const { chapterId } = req.body;

    const session = await getSession(sessionId);
    const settings = await getSettingsPreset(session.settingsPresetId);

    let chunks = [];
    if (chapterId) {
      chunks = await getChunksByChapter(sessionId, chapterId);
    }

    const interval = settings.chunkUpdateInterval || 10;
    const recentChunks = chunks.slice(-interval);

    const updated = await updateCharacterSheets(sessionId, recentChunks, settings);
    res.json(updated);
  } catch (err) {
    res.status(err.status || 500).json({ message: err.message });
  }
});

export default router;
