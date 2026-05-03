# PenDrift

Collaborative narrative writing tool powered by local LLMs.

## Quick Start

1. Run `SetupPython.bat` (Windows) to create the local conda environment.
2. Run `BuildClient.bat` to build the frontend.
3. Run `StartPython.bat` to start the PenDrift server on `http://localhost:3000`.

## Development

```bash
# Terminal 1: Start backend
set PENDRIFT_DEV=1
cd server-python
..\conda\condabin\conda.bat activate .\env
python run.py

# Terminal 2: Start frontend
cd client
pnpm install
pnpm dev
```

Alternatively, use `Dev.bat` on Windows.
Starts the FastAPI backend on `http://localhost:3000` and the Vite dev server on `http://localhost:5173`.

## License

MIT
