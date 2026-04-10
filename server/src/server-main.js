import express from 'express';
import path from 'node:path';
import { fileURLToPath } from 'node:url';
import { initDataDirectories } from './services/init.js';
import sessionsRouter from './routes/sessions.js';
import templatesRouter from './routes/templates.js';
import presetsRouter from './routes/presets.js';
import generateRouter from './routes/generate.js';
import charactersRouter from './routes/characters.js';
import chaptersRouter from './routes/chapters.js';

const __dirname = path.dirname(fileURLToPath(import.meta.url));
const PORT = process.env.PORT || 3000;

export async function startServer() {
  await initDataDirectories();

  const app = express();

  app.use(express.json());

  // Health check
  app.get('/api/health', (req, res) => {
    res.json({ status: 'ok', name: 'PenDrift', version: '0.1.0' });
  });

  // API routes
  app.use('/api/sessions', sessionsRouter);
  app.use('/api/presets/templates', templatesRouter);
  app.use('/api/presets/settings', presetsRouter);
  app.use('/api/sessions/:sessionId', generateRouter);
  app.use('/api/sessions/:sessionId/characters', charactersRouter);
  app.use('/api/sessions/:sessionId/chapters', chaptersRouter);

  // In production, serve the built Vue client
  if (process.env.NODE_ENV === 'production') {
    const clientDist = path.resolve(__dirname, '../../client/dist');
    app.use(express.static(clientDist));
    app.get('*', (req, res) => {
      res.sendFile(path.join(clientDist, 'index.html'));
    });
  }

  app.listen(PORT, () => {
    console.log(`PenDrift server running on http://localhost:${PORT}`);
  });
}
