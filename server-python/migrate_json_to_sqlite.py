"""Migrate existing PenDrift JSON data to SQLite.

Run once after switching to the Python backend:
    python migrate_json_to_sqlite.py
"""
import asyncio
import json
import sys
from pathlib import Path

# Add parent to path for app imports
sys.path.insert(0, str(Path(__file__).parent))

from app.config import DATA_DIR, DB_PATH
from app.database import init_db, get_db

SESSIONS_DIR = DATA_DIR / "sessions"


async def migrate():
    if not SESSIONS_DIR.is_dir():
        print("No data/sessions/ directory found. Nothing to migrate.")
        return

    print(f"Database: {DB_PATH}")
    await init_db()
    db = await get_db()

    session_dirs = [d for d in SESSIONS_DIR.iterdir() if d.is_dir()]
    print(f"Found {len(session_dirs)} session(s) to migrate.\n")

    for session_dir in session_dirs:
        session_file = session_dir / "session.json"
        if not session_file.is_file():
            print(f"  SKIP {session_dir.name} (no session.json)")
            continue

        session = json.loads(session_file.read_text(encoding="utf-8"))
        sid = session["id"]
        print(f"  Migrating session: {session.get('title', sid)}")

        # Insert session
        await db.execute(
            "INSERT OR IGNORE INTO sessions (id, title, template_id, settings_preset_id, cover_image, created_at, updated_at, last_meta_after_chunk_index) VALUES (?,?,?,?,?,?,?,?)",
            (sid, session.get("title", "Untitled"), session.get("templateId", ""),
             session.get("settingsPresetId", "default"), session.get("coverImage"),
             session.get("createdAt", ""), session.get("updatedAt", ""),
             session.get("lastMetaAfterChunkIndex")),
        )

        # Insert chapters
        for ch in session.get("chapters", []):
            await db.execute(
                'INSERT OR IGNORE INTO chapters (id, session_id, title, "order", finalized, created_at) VALUES (?,?,?,?,?,?)',
                (ch["id"], sid, ch.get("title", ""), ch.get("order", 0),
                 int(ch.get("finalized", False)), ch.get("createdAt", "")),
            )

        # Insert chunks
        chunks_dir = session_dir / "chunks"
        order_file = chunks_dir / "order.json"
        if order_file.is_file():
            order = json.loads(order_file.read_text(encoding="utf-8"))
            for idx, chunk_id in enumerate(order):
                chunk_file = chunks_dir / f"{chunk_id}.json"
                if not chunk_file.is_file():
                    continue
                chunk = json.loads(chunk_file.read_text(encoding="utf-8"))

                # Ensure versioned format
                if "versions" not in chunk or not chunk["versions"]:
                    chunk["versions"] = [{
                        "narrative": chunk.get("narrative", ""),
                        "thinking": chunk.get("thinking"),
                        "stats": chunk.get("stats"),
                        "directive": chunk.get("directive"),
                        "from": chunk.get("from", "narrative"),
                        "createdAt": chunk.get("createdAt", ""),
                    }]
                    chunk["activeVersion"] = 0

                await db.execute(
                    'INSERT OR IGNORE INTO chunks (id, session_id, chapter_id, "order", active_version, versions, is_key_moment, image_prompt, image_path, audio_path) VALUES (?,?,?,?,?,?,?,?,?,?)',
                    (chunk["id"], sid, chunk.get("chapterId", ""), idx,
                     chunk.get("activeVersion", 0), json.dumps(chunk["versions"]),
                     int(chunk.get("isKeyMoment", False)),
                     chunk.get("imagePrompt"), chunk.get("imagePath"), chunk.get("audioPath")),
                )

        # Insert characters
        chars_file = session_dir / "characters.json"
        if chars_file.is_file():
            characters = json.loads(chars_file.read_text(encoding="utf-8"))
            for char in characters:
                await db.execute(
                    "INSERT OR IGNORE INTO characters (session_id, name, current_state, traits, key_events, last_updated) VALUES (?,?,?,?,?,?)",
                    (sid, char["name"], char.get("currentState", ""),
                     json.dumps(char.get("traits", [])), json.dumps(char.get("keyEvents", [])),
                     char.get("lastUpdated", "")),
                )

        # Insert facts
        facts_file = session_dir / "facts.json"
        if facts_file.is_file():
            facts = json.loads(facts_file.read_text(encoding="utf-8"))
            for fact in facts:
                await db.execute(
                    "INSERT INTO facts (session_id, fact, created_at) VALUES (?,?,?)",
                    (sid, fact, session.get("updatedAt", "")),
                )

        # Insert meta history
        meta_dir = session_dir / "meta-history"
        if meta_dir.is_dir():
            for mf in sorted(meta_dir.glob("*.json")):
                entry = json.loads(mf.read_text(encoding="utf-8"))
                await db.execute(
                    "INSERT INTO meta_history (session_id, timestamp, chunk_range, status, error, result, raw_response) VALUES (?,?,?,?,?,?,?)",
                    (sid, entry.get("timestamp", ""),
                     json.dumps(entry.get("chunkRange", {})),
                     entry.get("status", "success"), entry.get("error"),
                     json.dumps(entry.get("result", {})), entry.get("rawResponse")),
                )

        # Insert API logs
        logs_dir = session_dir / "api-logs"
        if logs_dir.is_dir():
            for lf in sorted(logs_dir.glob("*.json")):
                log_entry = json.loads(lf.read_text(encoding="utf-8"))
                await db.execute(
                    "INSERT INTO api_logs (session_id, timestamp, type, model, messages, params, status, response, error, duration_ms) VALUES (?,?,?,?,?,?,?,?,?,?)",
                    (sid, log_entry.get("timestamp", ""), log_entry.get("type"),
                     log_entry.get("model"), json.dumps(log_entry.get("messages", [])),
                     json.dumps(log_entry.get("params", {})), log_entry.get("status", "pending"),
                     json.dumps(log_entry.get("response")) if log_entry.get("response") else None,
                     log_entry.get("error"), log_entry.get("durationMs")),
                )

    await db.commit()
    print(f"\nMigration complete! Database: {DB_PATH}")


if __name__ == "__main__":
    asyncio.run(migrate())
