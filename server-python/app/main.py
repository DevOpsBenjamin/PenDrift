from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from app.database import init_db
from app.config import DATA_DIR, CLIENT_DIST
from app.routers import sessions, templates, presets, generate, chapters, characters, chunks, api_logs, llm_management, facts, import_chub


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Startup / shutdown."""
    await init_db()
    yield
    # Shutdown: kill llama-server if running
    from app.services.llm_process import stop_server
    await stop_server()


app = FastAPI(title="PenDrift", version="0.2.0", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

# ── Routes ──────────────────────────────────────────────
app.include_router(sessions.router, prefix="/api/sessions", tags=["sessions"])
app.include_router(templates.router, prefix="/api/presets/templates", tags=["templates"])
app.include_router(presets.router, prefix="/api/presets/settings", tags=["presets"])
app.include_router(llm_management.router, prefix="/api/llm", tags=["llm"])
app.include_router(generate.router, prefix="/api/sessions/{session_id}", tags=["generate"])
app.include_router(chapters.router, prefix="/api/sessions/{session_id}/chapters", tags=["chapters"])
app.include_router(characters.router, prefix="/api/sessions/{session_id}/characters", tags=["characters"])
app.include_router(chunks.router, prefix="/api/sessions/{session_id}/chunks", tags=["chunks"])
app.include_router(facts.router, prefix="/api/sessions/{session_id}/facts", tags=["facts"])
app.include_router(api_logs.router, prefix="/api/sessions/{session_id}/api-logs", tags=["api-logs"])
app.include_router(import_chub.router, prefix="/api/import", tags=["import"])


@app.get("/api/health")
async def health():
    return {"status": "ok", "name": "PenDrift", "version": "0.2.0"}


# Serve Vue client build in production
if CLIENT_DIST.is_dir():
    app.mount("/", StaticFiles(directory=str(CLIENT_DIST), html=True), name="client")
