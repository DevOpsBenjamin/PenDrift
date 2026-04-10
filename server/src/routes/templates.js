import { Router } from 'express';
import * as templates from '../services/templates.js';

const router = Router();

router.get('/', async (req, res) => {
  try {
    const list = await templates.listTemplates();
    res.json(list);
  } catch (err) {
    res.status(err.status || 500).json({ message: err.message });
  }
});

router.get('/:id', async (req, res) => {
  try {
    const template = await templates.getTemplate(req.params.id);
    res.json(template);
  } catch (err) {
    res.status(err.status || 500).json({ message: err.message });
  }
});

router.post('/', async (req, res) => {
  try {
    const template = await templates.saveTemplate(req.body);
    res.json(template);
  } catch (err) {
    res.status(err.status || 500).json({ message: err.message });
  }
});

router.delete('/:id', async (req, res) => {
  try {
    await templates.deleteTemplate(req.params.id);
    res.json({ ok: true });
  } catch (err) {
    res.status(err.status || 500).json({ message: err.message });
  }
});

export default router;
