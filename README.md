# PenDrift

Collaborative narrative writing tool powered by local LLMs.

## Quick Start

```bash
# Requires Node.js >= 20 and pnpm
pnpm --prefix server install
pnpm --prefix client install
pnpm --prefix client build
node server/server.js
```

Or use the startup scripts: `Start.bat` (Windows) / `start.sh` (Linux/Mac).

## Development

```bash
pnpm install
pnpm --prefix server install
pnpm --prefix client install
pnpm dev
```

Starts the Express backend on `http://localhost:3000` and the Vite dev server on `http://localhost:5173`.

## License

MIT
