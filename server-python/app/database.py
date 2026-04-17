import json
import shutil
import aiosqlite

from app.config import DATA_DIR, DB_PATH, SETTINGS_DIR, TEMPLATES_DIR, DEFAULTS_DIR

_db: aiosqlite.Connection | None = None

SCHEMA = """
CREATE TABLE IF NOT EXISTS sessions (
    id              TEXT PRIMARY KEY,
    title           TEXT NOT NULL,
    template_id     TEXT NOT NULL,
    settings_preset_id TEXT NOT NULL DEFAULT 'default',
    cover_image     TEXT,
    last_meta_after_chunk_index INTEGER,
    created_at      TEXT NOT NULL,
    updated_at      TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS chapters (
    id              TEXT PRIMARY KEY,
    session_id      TEXT NOT NULL REFERENCES sessions(id) ON DELETE CASCADE,
    title           TEXT NOT NULL,
    "order"         INTEGER NOT NULL,
    finalized       INTEGER NOT NULL DEFAULT 0,
    created_at      TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_chapters_session ON chapters(session_id);

CREATE TABLE IF NOT EXISTS chunks (
    id              TEXT PRIMARY KEY,
    session_id      TEXT NOT NULL REFERENCES sessions(id) ON DELETE CASCADE,
    chapter_id      TEXT NOT NULL REFERENCES chapters(id) ON DELETE CASCADE,
    "order"         INTEGER NOT NULL,
    active_version  INTEGER NOT NULL DEFAULT 0,
    versions        TEXT NOT NULL DEFAULT '[]',   -- JSON array
    is_key_moment   INTEGER NOT NULL DEFAULT 0,
    image_prompt    TEXT,
    image_path      TEXT,
    audio_path      TEXT
);
CREATE INDEX IF NOT EXISTS idx_chunks_chapter ON chunks(chapter_id);
CREATE INDEX IF NOT EXISTS idx_chunks_session ON chunks(session_id);

CREATE TABLE IF NOT EXISTS characters (
    session_id      TEXT NOT NULL REFERENCES sessions(id) ON DELETE CASCADE,
    name            TEXT NOT NULL,
    current_state   TEXT,
    traits          TEXT NOT NULL DEFAULT '[]',    -- JSON array
    key_events      TEXT NOT NULL DEFAULT '[]',    -- JSON array
    last_updated    TEXT,
    PRIMARY KEY (session_id, name)
);

CREATE TABLE IF NOT EXISTS facts (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    session_id      TEXT NOT NULL REFERENCES sessions(id) ON DELETE CASCADE,
    fact            TEXT NOT NULL,
    created_at      TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_facts_session ON facts(session_id);

CREATE TABLE IF NOT EXISTS meta_history (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    session_id      TEXT NOT NULL REFERENCES sessions(id) ON DELETE CASCADE,
    timestamp       TEXT NOT NULL,
    chunk_range     TEXT NOT NULL DEFAULT '{}',    -- JSON {from, to, count}
    status          TEXT NOT NULL DEFAULT 'success',
    error           TEXT,
    result          TEXT NOT NULL DEFAULT '{}',    -- JSON
    raw_response    TEXT
);
CREATE INDEX IF NOT EXISTS idx_meta_session ON meta_history(session_id);

CREATE TABLE IF NOT EXISTS api_logs (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    session_id      TEXT NOT NULL REFERENCES sessions(id) ON DELETE CASCADE,
    timestamp       TEXT NOT NULL,
    type            TEXT,
    model           TEXT,
    messages        TEXT NOT NULL DEFAULT '[]',    -- JSON
    params          TEXT NOT NULL DEFAULT '{}',    -- JSON
    status          TEXT NOT NULL DEFAULT 'pending',
    response        TEXT,                          -- JSON (truncated)
    error           TEXT,
    duration_ms     INTEGER
);
CREATE INDEX IF NOT EXISTS idx_api_logs_session ON api_logs(session_id);
"""


async def get_db() -> aiosqlite.Connection:
    global _db
    if _db is None:
        DATA_DIR.mkdir(parents=True, exist_ok=True)
        _db = await aiosqlite.connect(str(DB_PATH))
        _db.row_factory = aiosqlite.Row
        await _db.execute("PRAGMA journal_mode=WAL")
        await _db.execute("PRAGMA foreign_keys=ON")
    return _db


async def init_db():
    db = await get_db()
    await db.executescript(SCHEMA)
    await db.commit()
    _seed_defaults()


def _seed_defaults():
    """Copy default presets/templates to data/ if they don't exist (JSON files, same as Node version)."""
    for subdir in ("settings", "templates"):
        src = DEFAULTS_DIR / subdir
        dst = DATA_DIR / "presets" / subdir
        if not src.is_dir():
            continue
        dst.mkdir(parents=True, exist_ok=True)
        for f in src.glob("*.json"):
            target = dst / f.name
            if not target.exists():
                shutil.copy2(f, target)
