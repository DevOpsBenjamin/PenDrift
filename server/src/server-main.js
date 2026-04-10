import express, { Router } from 'express';
import path from 'node:path';
import { fileURLToPath } from 'node:url';
import { initDataDirectories } from './services/init.js';
import sessionsRouter from './routes/sessions.js';
import templatesRouter from './routes/templates.js';
import presetsRouter from './routes/presets.js';
import sessionScopedRouter from './routes/session-scoped.js';

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

  // Mount all API routes on a single /api router
  // ORDER MATTERS: session-scoped routes before sessions CRUD
  // because sessionsRouter's GET /:id would catch everything
  app.use('/api/presets/templates', templatesRouter);
  app.use('/api/presets/settings', presetsRouter);
  app.use('/api/sessions/:sessionId', sessionScopedRouter);
  app.use('/api/sessions', sessionsRouter);

  // In production, serve the built Vue client
  if (process.env.NODE_ENV === 'production') {
    const clientDist = path.resolve(__dirname, '../../client/dist');
    app.use(express.static(clientDist));
    app.get('*', (req, res) => {
      res.sendFile(path.join(clientDist, 'index.html'));
    });
  }

  const server = app.listen(PORT, () => {
    console.log(`PenDrift server running on http://localhost:${PORT}`);
  });

  server.on('error', (err) => {
    if (err.code === 'EADDRINUSE') {
      console.error(`\x1b[31mERROR: Port ${PORT} is already in use. Kill the other process or change PORT.\x1b[0m`);
    } else {
      console.error(`\x1b[31mERROR: Server failed to start: ${err.message}\x1b[0m`);
    }
    process.exit(1);
  });
}
