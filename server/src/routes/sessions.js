import { Router } from 'express';
import * as sessions from '../services/sessions.js';

const router = Router();

router.get('/', async (req, res) => {
  try {
    const list = await sessions.listSessions();
    res.json(list);
  } catch (err) {
    res.status(err.status || 500).json({ message: err.message });
  }
});

router.post('/', async (req, res) => {
  try {
    const { templateId, title, settingsPresetId } = req.body;
    if (!templateId) {
      return res.status(400).json({ message: 'templateId is required' });
    }
    const session = await sessions.createSession({ templateId, title, settingsPresetId });
    res.status(201).json(session);
  } catch (err) {
    res.status(err.status || 500).json({ message: err.message });
  }
});

router.get('/:id', async (req, res) => {
  try {
    const session = await sessions.getSession(req.params.id);
    res.json(session);
  } catch (err) {
    res.status(err.status || 500).json({ message: err.message });
  }
});

router.put('/:id', async (req, res) => {
  try {
    const session = await sessions.updateSession(req.params.id, req.body);
    res.json(session);
  } catch (err) {
    res.status(err.status || 500).json({ message: err.message });
  }
});

router.delete('/:id', async (req, res) => {
  try {
    await sessions.deleteSession(req.params.id);
    res.json({ ok: true });
  } catch (err) {
    res.status(err.status || 500).json({ message: err.message });
  }
});

export default router;
