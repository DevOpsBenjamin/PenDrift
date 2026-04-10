import { Router } from 'express';
import * as presets from '../services/presets.js';

const router = Router();

router.get('/', async (req, res) => {
  try {
    const list = await presets.listSettingsPresets();
    res.json(list);
  } catch (err) {
    res.status(err.status || 500).json({ message: err.message });
  }
});

router.get('/:id', async (req, res) => {
  try {
    const preset = await presets.getSettingsPreset(req.params.id);
    res.json(preset);
  } catch (err) {
    res.status(err.status || 500).json({ message: err.message });
  }
});

router.post('/', async (req, res) => {
  try {
    const preset = await presets.saveSettingsPreset(req.body);
    res.json(preset);
  } catch (err) {
    res.status(err.status || 500).json({ message: err.message });
  }
});

router.delete('/:id', async (req, res) => {
  try {
    await presets.deleteSettingsPreset(req.params.id);
    res.json({ ok: true });
  } catch (err) {
    res.status(err.status || 500).json({ message: err.message });
  }
});

export default router;
