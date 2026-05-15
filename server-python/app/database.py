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
    template_version TEXT,
    settings_preset_id TEXT NOT NULL DEFAULT 'default',
    cover_image     TEXT,
    last_meta_after_chunk_index INTEGER,
    finished_at     TEXT,
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
    -- Structured fields produced by initial meta at session creation,
    -- evolved by regular meta during the session.
    identity            TEXT NOT NULL DEFAULT '',  -- durable self-conception
    voice               TEXT NOT NULL DEFAULT '',  -- speech patterns / register
    appearance          TEXT NOT NULL DEFAULT '',  -- durable visible presentation
    backstory           TEXT NOT NULL DEFAULT '',  -- past, set at session start
    backstory_additions TEXT NOT NULL DEFAULT '[]', -- JSON array, append-only
    masked_intents      TEXT NOT NULL DEFAULT '[]', -- JSON array, removed on resolution
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

CREATE TABLE IF NOT EXISTS session_queries (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    session_id      TEXT NOT NULL REFERENCES sessions(id) ON DELETE CASCADE,
    question        TEXT NOT NULL,
    thinking        TEXT NOT NULL DEFAULT '',
    answer          TEXT NOT NULL DEFAULT '',
    status          TEXT NOT NULL DEFAULT 'running', -- 'running' | 'success' | 'error' | 'cancelled'
    error           TEXT,
    model           TEXT,
    created_at      TEXT NOT NULL,
    completed_at    TEXT
);
CREATE INDEX IF NOT EXISTS idx_session_queries_session ON session_queries(session_id);

-- Meta-analytical Q&A about a template (its goals, hidden mechanics, gaps).
-- Lives at the template level, not per-session: the user can ask from a
-- specific session (in which case `session_id` records the session that
-- provided the evidence/context), or from the template view directly.
-- session_id has NO FK so a session deletion doesn't drop the asks — they
-- remain useful diagnostic history for the template.
CREATE TABLE IF NOT EXISTS template_queries (
    id               INTEGER PRIMARY KEY AUTOINCREMENT,
    template_id      TEXT NOT NULL,
    template_version TEXT,
    session_id       TEXT,
    question         TEXT NOT NULL,
    thinking         TEXT NOT NULL DEFAULT '',
    answer           TEXT NOT NULL DEFAULT '',
    status           TEXT NOT NULL DEFAULT 'running',
    error            TEXT,
    model            TEXT,
    created_at       TEXT NOT NULL,
    completed_at     TEXT
);
CREATE INDEX IF NOT EXISTS idx_template_queries_template ON template_queries(template_id);
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
    await _backup_db()
    db = await get_db()
    await db.executescript(SCHEMA)
    await _migrate_columns(db)
    await db.commit()
    _seed_defaults()


async def _backup_db():
    if not DB_PATH.is_file():
        return
    import datetime
    
    backups_dir = DATA_DIR / "backups"
    backups_dir.mkdir(parents=True, exist_ok=True)
    
    today = datetime.date.today().isoformat()
    backup_file = backups_dir / f"pendrift_{today}.db"
    
    if not backup_file.exists():
        # Copy the database
        shutil.copy2(DB_PATH, backup_file)
        
        # Keep only the 7 most recent backups
        backups = sorted(backups_dir.glob("pendrift_*.db"))
        if len(backups) > 7:
            for old_backup in backups[:-7]:
                try:
                    old_backup.unlink()
                except OSError:
                    pass


async def _migrate_columns(db: aiosqlite.Connection):
    """Idempotent ALTERs for columns added after initial schema."""
    cur = await db.execute("PRAGMA table_info(sessions)")
    session_cols = {row[1] for row in await cur.fetchall()}
    if "template_version" not in session_cols:
        await db.execute("ALTER TABLE sessions ADD COLUMN template_version TEXT")
    if "finished_at" not in session_cols:
        await db.execute("ALTER TABLE sessions ADD COLUMN finished_at TEXT")
    if "pending_milestones" not in session_cols:
        await db.execute("ALTER TABLE sessions ADD COLUMN pending_milestones TEXT NOT NULL DEFAULT '[]'")
    if "achieved_milestones" not in session_cols:
        await db.execute("ALTER TABLE sessions ADD COLUMN achieved_milestones TEXT NOT NULL DEFAULT '[]'")
    if "initial_meta_status" not in session_cols:
        # 'done' for migration (existing sessions were running fine without
        # this concept). New sessions set 'pending' explicitly at insert.
        await db.execute("ALTER TABLE sessions ADD COLUMN initial_meta_status TEXT NOT NULL DEFAULT 'done'")

    cur = await db.execute("PRAGMA table_info(characters)")
    char_cols = {row[1] for row in await cur.fetchall()}
    for col, ddl in [
        ("identity", "TEXT NOT NULL DEFAULT ''"),
        ("voice", "TEXT NOT NULL DEFAULT ''"),
        ("appearance", "TEXT NOT NULL DEFAULT ''"),
        ("backstory", "TEXT NOT NULL DEFAULT ''"),
        ("backstory_additions", "TEXT NOT NULL DEFAULT '[]'"),
        ("masked_intents", "TEXT NOT NULL DEFAULT '[]'"),
    ]:
        if col not in char_cols:
            await db.execute(f"ALTER TABLE characters ADD COLUMN {col} {ddl}")


def _seed_defaults():
    """Copy default presets/templates to data/ if they don't exist, and fill in
    any keys that have since been added to the source defaults (never overwrites
    existing values)."""
    import json

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
                continue
            try:
                source = json.loads(f.read_text(encoding="utf-8"))
                current = json.loads(target.read_text(encoding="utf-8"))
            except (json.JSONDecodeError, OSError):
                continue
            missing = {k: v for k, v in source.items() if k not in current}
            if missing:
                current.update(missing)
                target.write_text(json.dumps(current, indent=2, ensure_ascii=False), encoding="utf-8")
