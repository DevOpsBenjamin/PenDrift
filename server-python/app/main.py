import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from app.database import init_db
from app.config import DATA_DIR, CLIENT_DIST
from app.routers import sessions, templates, presets, generate, chapters, characters, chunks, api_logs, llm_management, facts, import_chub, prompts as prompts_router


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Startup / shutdown."""
    from app.services.llm_process import reap_orphans, stop_server
    # Kill any orphan llama-server left by a previous force-closed run.
    reap_orphans()
    await init_db()
    yield
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
app.include_router(prompts_router.router, prefix="/api/prompts", tags=["prompts"])


@app.get("/api/health")
async def health():
    return {"status": "ok", "name": "PenDrift", "version": "0.2.0"}


# Migrate any pre-folder templates to the new folder structure on startup.
# Idempotent — only runs work the first time it sees flat-file templates.
from app.services.template_store import migrate_flat_files as _migrate_templates
from app.services.prompts_registry import migrate_strip_legacy_prompts as _migrate_prompts
try:
    _migrated = _migrate_templates()
    if _migrated:
        logging.getLogger("pendrift.startup").info(
            "Migrated %d template(s) to folder structure", _migrated
        )
except Exception as _e:
    logging.getLogger("pendrift.startup").warning("Template migration error: %s", _e)

try:
    _stripped = _migrate_prompts()
    if _stripped:
        logging.getLogger("pendrift.startup").info(
            "Stripped legacy prompt fields from %d settings file(s)", _stripped
        )
except Exception as _e:
    logging.getLogger("pendrift.startup").warning("Prompts migration error: %s", _e)
# Note: cover images are now served by a dedicated route in the templates
# router (GET /api/presets/templates/{id}/image), since each template's image
# lives inside its own folder at <id>/image.<ext>.

# Serve Vue client build in production (SPA fallback for Vue Router)
if CLIENT_DIST.is_dir():
    app.mount("/assets", StaticFiles(directory=str(CLIENT_DIST / "assets")), name="assets")

    @app.get("/{full_path:path}")
    async def spa_fallback(full_path: str):
        # Serve an actual file if it exists at dist root (favicon, etc), otherwise index.html
        file_path = CLIENT_DIST / full_path
        if full_path and file_path.is_file():
            return FileResponse(file_path)
        return FileResponse(CLIENT_DIST / "index.html")
