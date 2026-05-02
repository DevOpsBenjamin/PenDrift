"""Folder-based storage for narrative templates.

Each template lives in its own directory under `data/presets/templates/<id>/`:

    <id>/
    ├── 0001.json           ← initial version
    ├── 0002.json           ← later edits / enrich operations
    ├── image.png           ← cover image (any allowed ext)
    ├── index.json          ← {currentVersion, history: [...]}
    └── sources/
        ├── 0001-card.json  ← original chub card from the import
        └── 0002-card.json  ← card from a later enrich call

Versions are 4-digit zero-padded, monotonically increasing. The "current"
version is what the app loads by default; older versions are kept for
inspection / rollback. Manual edits update the current version in place
(no version bump). LLM-driven changes (import, enrich, reread, restore)
create a new version and append a history entry.
"""
from __future__ import annotations

import json
import logging
import re
import shutil
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterable

from app.config import DATA_DIR

log = logging.getLogger("pendrift.template_store")

TEMPLATES_DIR = DATA_DIR / "presets" / "templates"
ALLOWED_IMAGE_EXT = {".png", ".jpg", ".jpeg", ".webp", ".gif"}

_VERSION_PATTERN = re.compile(r"^(\d{4})\.json$")


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _ensure_root() -> None:
    TEMPLATES_DIR.mkdir(parents=True, exist_ok=True)


def template_dir(template_id: str) -> Path:
    return TEMPLATES_DIR / template_id


def is_template_folder(path: Path) -> bool:
    """A folder is a template if it has at least one NNNN.json file or an index.json."""
    if not path.is_dir():
        return False
    if (path / "index.json").is_file():
        return True
    return any(_VERSION_PATTERN.match(f.name) for f in path.iterdir() if f.is_file())


def _list_version_files(folder: Path) -> list[Path]:
    """Return the version files in ascending order."""
    return sorted(
        (f for f in folder.iterdir() if f.is_file() and _VERSION_PATTERN.match(f.name)),
        key=lambda f: f.name,
    )


def _next_version_number(folder: Path) -> str:
    files = _list_version_files(folder)
    if not files:
        return "0001"
    last = int(_VERSION_PATTERN.match(files[-1].name).group(1))
    return f"{last + 1:04d}"


def _read_index(folder: Path) -> dict:
    path = folder / "index.json"
    if path.is_file():
        try:
            return json.loads(path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            log.warning("Corrupt index.json in %s, will rebuild", folder)
    # Fallback: rebuild minimally from disk
    files = _list_version_files(folder)
    if not files:
        return {"currentVersion": None, "history": []}
    last = _VERSION_PATTERN.match(files[-1].name).group(1)
    return {"currentVersion": last, "history": []}


def _write_index(folder: Path, index: dict) -> None:
    (folder / "index.json").write_text(
        json.dumps(index, indent=2, ensure_ascii=False), encoding="utf-8"
    )


def find_image(folder: Path) -> Path | None:
    for ext in ALLOWED_IMAGE_EXT:
        p = folder / f"image{ext}"
        if p.is_file():
            return p
    return None


def list_templates() -> list[dict]:
    """Return the current version of every template."""
    _ensure_root()
    out = []
    for entry in sorted(TEMPLATES_DIR.iterdir(), key=lambda p: p.name.lower()):
        if not is_template_folder(entry):
            continue
        try:
            current = load_current(entry.name)
            if current is not None:
                out.append(current)
        except Exception as e:
            log.warning("Skipping unreadable template %s: %s", entry.name, e)
    return out


def load_current(template_id: str) -> dict | None:
    folder = template_dir(template_id)
    if not is_template_folder(folder):
        return None
    index = _read_index(folder)
    cv = index.get("currentVersion")
    if cv:
        path = folder / f"{cv}.json"
        if path.is_file():
            data = json.loads(path.read_text(encoding="utf-8"))
            data["id"] = template_id  # always re-derive from folder name
            return data
    # Fallback: pick the highest-numbered version file
    files = _list_version_files(folder)
    if not files:
        return None
    data = json.loads(files[-1].read_text(encoding="utf-8"))
    data["id"] = template_id
    return data


def current_version(template_id: str) -> str | None:
    """Return the current version string (e.g. "0003") or None if the
    template doesn't exist."""
    folder = template_dir(template_id)
    if not is_template_folder(folder):
        return None
    index = _read_index(folder)
    return index.get("currentVersion")


def load_version(template_id: str, version: str) -> dict | None:
    folder = template_dir(template_id)
    if not _VERSION_PATTERN.match(f"{version}.json"):
        return None
    path = folder / f"{version}.json"
    if not path.is_file():
        return None
    data = json.loads(path.read_text(encoding="utf-8"))
    data["id"] = template_id
    return data


def list_versions(template_id: str) -> list[dict]:
    """Return [{version, action, at, source, sourceRef, url}] for each known version."""
    folder = template_dir(template_id)
    if not is_template_folder(folder):
        return []
    index = _read_index(folder)
    history = {h["version"]: h for h in index.get("history", []) if "version" in h}
    out = []
    for f in _list_version_files(folder):
        version = _VERSION_PATTERN.match(f.name).group(1)
        meta = history.get(version, {})
        out.append({
            "version": version,
            "action": meta.get("action", "unknown"),
            "at": meta.get("at"),
            "source": meta.get("source"),
            "sourceRef": meta.get("sourceRef"),
            "url": meta.get("url"),
        })
    return out


def save_in_place(template_id: str, body: dict) -> dict:
    """Manual-edit save: overwrites the current version file. Does NOT bump
    the version or add to history. Use this when the user just edits fields
    in the UI."""
    folder = template_dir(template_id)
    folder.mkdir(parents=True, exist_ok=True)
    index = _read_index(folder)
    cv = index.get("currentVersion")
    if not cv:
        # First-time save: create 0001
        return create_new_template(template_id, body, action="manual-create")
    path = folder / f"{cv}.json"
    body = dict(body)
    body["id"] = template_id
    body.pop("_versions", None)  # transient field, never persist
    path.write_text(json.dumps(body, indent=2, ensure_ascii=False), encoding="utf-8")
    return body


def create_new_template(
    template_id: str,
    body: dict,
    *,
    action: str = "manual-create",
    source_filename: str | None = None,
    source_url: str | None = None,
    source_json: dict | None = None,
) -> dict:
    """Create a brand-new template folder with version 0001."""
    folder = template_dir(template_id)
    folder.mkdir(parents=True, exist_ok=True)
    if _list_version_files(folder):
        raise ValueError(f"Template '{template_id}' already exists")
    body = dict(body)
    body["id"] = template_id
    body.pop("_versions", None)
    version = "0001"
    (folder / f"{version}.json").write_text(
        json.dumps(body, indent=2, ensure_ascii=False), encoding="utf-8"
    )
    saved_source = None
    if source_json is not None:
        saved_source = _save_source(folder, version, source_json)
    history_entry = {
        "version": version,
        "action": action,
        "at": _now(),
    }
    if saved_source:
        history_entry["source"] = saved_source
    if source_url:
        history_entry["url"] = source_url
    _write_index(folder, {
        "currentVersion": version,
        "history": [history_entry],
    })
    return body


def add_version(
    template_id: str,
    body: dict,
    *,
    action: str,
    source_filename: str | None = None,
    source_url: str | None = None,
    source_json: dict | None = None,
    source_ref: str | None = None,
) -> tuple[dict, str]:
    """Append a new numbered version to an existing template, update index,
    and make it the current. Returns (body, version_str).

    Source bookkeeping options (use whichever applies):
    - `source_json`: a card dict to persist alongside the version (saved to
      sources/<version>-card.json, recorded as `source` in history).
    - `source_ref`: a bare filename of an EXISTING source under sources/
      (e.g. '0001-card.json' for a rerun) — recorded as `sourceRef` in
      history without re-writing the file.
    - `source_url`: the chub URL to record as `url` in history."""
    folder = template_dir(template_id)
    if not folder.is_dir():
        raise FileNotFoundError(f"Template '{template_id}' not found")
    body = dict(body)
    body["id"] = template_id
    body.pop("_versions", None)
    version = _next_version_number(folder)
    (folder / f"{version}.json").write_text(
        json.dumps(body, indent=2, ensure_ascii=False), encoding="utf-8"
    )
    saved_source = None
    if source_json is not None:
        saved_source = _save_source(folder, version, source_json)
    index = _read_index(folder)
    history = index.get("history", [])
    entry = {"version": version, "action": action, "at": _now()}
    if saved_source:
        entry["source"] = saved_source
    if source_ref:
        entry["sourceRef"] = source_ref
    if source_url:
        entry["url"] = source_url
    history.append(entry)
    _write_index(folder, {"currentVersion": version, "history": history})
    return body, version


def restore_version(template_id: str, version: str) -> tuple[dict, str]:
    """Copy `version` to a new latest version with action='restore-from-X'."""
    src = load_version(template_id, version)
    if src is None:
        raise FileNotFoundError(f"Version {version} not found for template '{template_id}'")
    return add_version(template_id, src, action=f"restore-from-{version}")


def delete_template(template_id: str) -> bool:
    """Remove the entire template folder."""
    folder = template_dir(template_id)
    if not folder.is_dir():
        return False
    shutil.rmtree(folder)
    return True


def write_image(template_id: str, content: bytes, ext: str) -> str:
    """Write image bytes to <id>/image.<ext>, removing any prior image first.
    Returns the filename written (e.g. 'image.png')."""
    ext = ext.lower()
    if not ext.startswith("."):
        ext = "." + ext
    if ext not in ALLOWED_IMAGE_EXT:
        raise ValueError(f"Unsupported image type: {ext}")
    folder = template_dir(template_id)
    folder.mkdir(parents=True, exist_ok=True)
    # Wipe any existing image of any extension
    for old in folder.glob("image.*"):
        try:
            old.unlink()
        except OSError:
            pass
    filename = f"image{ext}"
    (folder / filename).write_bytes(content)
    return filename


def delete_image(template_id: str) -> bool:
    folder = template_dir(template_id)
    found = False
    for old in folder.glob("image.*"):
        try:
            old.unlink()
            found = True
        except OSError:
            pass
    return found


def _save_source(folder: Path, version: str, card_json: dict) -> str:
    """Persist the source card JSON to sources/<version>-card.json. Returns
    relative path string."""
    sources_dir = folder / "sources"
    sources_dir.mkdir(parents=True, exist_ok=True)
    filename = f"{version}-card.json"
    (sources_dir / filename).write_text(
        json.dumps(card_json, indent=2, ensure_ascii=False), encoding="utf-8"
    )
    return f"sources/{filename}"


def migrate_flat_files() -> int:
    """Convert any pre-folder templates ('<id>.json' at root + 'images/<id>.<ext>')
    into the folder structure. Idempotent — safe to run on every startup.

    Returns the number of templates migrated."""
    _ensure_root()
    legacy_images_dir = TEMPLATES_DIR / "images"
    migrated = 0
    for entry in list(TEMPLATES_DIR.iterdir()):
        # Only flat JSON files at the root are candidates
        if not entry.is_file() or entry.suffix.lower() != ".json":
            continue
        # Skip files inside a folder (we're at root level here)
        template_id = entry.stem
        target_folder = TEMPLATES_DIR / template_id
        if target_folder.exists() and target_folder.is_dir():
            # The folder already holds the canonical version. If it has a
            # readable 0001.json, the flat file is a stale leftover from
            # before the format change — delete it so the warning doesn't
            # re-spam every startup. Otherwise leave both alone and warn,
            # since something unusual is going on.
            initial = target_folder / "0001.json"
            if initial.is_file():
                try:
                    json.loads(initial.read_text(encoding="utf-8"))
                    entry.unlink()
                    log.info("Removed stale flat template %s (folder already migrated)", entry.name)
                except (json.JSONDecodeError, OSError) as e:
                    log.warning("Folder for %s exists but 0001.json unreadable (%s) — leaving flat file in place", entry.name, e)
            else:
                log.warning("Cannot migrate %s: folder %s exists but has no 0001.json", entry.name, target_folder)
            continue
        try:
            data = json.loads(entry.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError) as e:
            log.warning("Cannot read %s for migration: %s", entry, e)
            continue

        # Strip stale coverImage that referenced the old path; we'll set
        # `coverImage: "image.<ext>"` if we find an image to move.
        old_cover = data.pop("coverImage", None)
        new_cover = None

        target_folder.mkdir(parents=True, exist_ok=True)
        # Write 0001.json
        (target_folder / "0001.json").write_text(
            json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8"
        )

        # Migrate the image if any
        if legacy_images_dir.is_dir():
            for img in legacy_images_dir.glob(f"{template_id}.*"):
                ext = img.suffix.lower()
                if ext not in ALLOWED_IMAGE_EXT:
                    continue
                try:
                    shutil.move(str(img), str(target_folder / f"image{ext}"))
                    new_cover = f"image{ext}"
                    break
                except OSError as e:
                    log.warning("Could not move image %s: %s", img, e)

        # If image was found, update 0001.json to record it
        if new_cover:
            data["coverImage"] = new_cover
            (target_folder / "0001.json").write_text(
                json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8"
            )

        # Write index.json
        history_entry = {
            "version": "0001",
            "action": "migrated",
            "at": _now(),
            "originalCoverImage": old_cover,
        }
        _write_index(target_folder, {"currentVersion": "0001", "history": [history_entry]})

        # Remove the legacy flat file
        try:
            entry.unlink()
        except OSError as e:
            log.warning("Could not delete legacy file %s: %s", entry, e)

        migrated += 1
        log.info("Migrated template '%s' to folder structure", template_id)

    # Clean up the now-empty legacy images dir
    if legacy_images_dir.is_dir():
        try:
            remaining = list(legacy_images_dir.iterdir())
            if not remaining:
                legacy_images_dir.rmdir()
                log.info("Removed empty legacy images dir")
            else:
                log.info("Legacy images dir kept (still has %d files)", len(remaining))
        except OSError:
            pass

    return migrated


def load_source(template_id: str, source_filename: str) -> dict | None:
    """Load a saved source card. `source_filename` is either bare (e.g.
    '0001-card.json') or relative to the template folder (e.g.
    'sources/0001-card.json'). Both are accepted."""
    if ".." in source_filename or source_filename.startswith("/") or source_filename.startswith("\\"):
        return None
    folder = template_dir(template_id)
    # Normalize: if no 'sources/' prefix, add it
    if not source_filename.startswith("sources/") and not source_filename.startswith("sources\\"):
        path = folder / "sources" / source_filename
    else:
        path = folder / source_filename
    if not path.is_file():
        return None
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return None


def _chub_url_from_card(card: dict) -> str | None:
    """Reconstruct the chub.ai URL from a card's `extensions.chub.full_path`.
    Works on both wrapped V2 cards ({spec, data: {...}}) and flat cards."""
    if not isinstance(card, dict):
        return None
    # Try flat first, then V2 wrapper
    candidates = [card, card.get("data") if isinstance(card.get("data"), dict) else {}]
    for c in candidates:
        ext = c.get("extensions") if isinstance(c, dict) else None
        if isinstance(ext, dict):
            chub = ext.get("chub")
            if isinstance(chub, dict):
                full_path = chub.get("full_path")
                if full_path:
                    return f"https://chub.ai/characters/{full_path}"
    return None


def list_sources(template_id: str) -> list[dict]:
    """Return [{filename, sizeBytes, addedAt, url}] for each card JSON in
    <id>/sources/. Sorted by filename ascending. `url` is the reconstructed
    chub.ai URL when the card carries `extensions.chub.full_path`."""
    folder = template_dir(template_id)
    sources_dir = folder / "sources"
    if not sources_dir.is_dir():
        return []
    out = []
    for f in sorted(sources_dir.iterdir(), key=lambda p: p.name):
        if not f.is_file() or not f.name.endswith(".json"):
            continue
        try:
            stat = f.stat()
        except OSError:
            continue
        url = None
        try:
            card = json.loads(f.read_text(encoding="utf-8"))
            url = _chub_url_from_card(card)
        except (json.JSONDecodeError, OSError):
            pass
        out.append({
            "filename": f.name,
            "sizeBytes": stat.st_size,
            "addedAt": datetime.fromtimestamp(stat.st_mtime, tz=timezone.utc).isoformat(),
            "url": url,
        })
    return out


def attach_source(template_id: str, card_json: dict) -> str:
    """Attach a card JSON as a new entry under <id>/sources/. Picks the next
    available numbered slot (e.g. '0003-card.json') so existing entries are
    never overwritten. Independent of the version history (sources can be
    added without bumping the template version). Returns the new filename."""
    folder = template_dir(template_id)
    if not is_template_folder(folder):
        raise FileNotFoundError(f"Template '{template_id}' not found")
    sources_dir = folder / "sources"
    sources_dir.mkdir(parents=True, exist_ok=True)
    # Find the next free NNNN slot, skipping any taken by version-bound sources
    next_num = 1
    for f in sources_dir.iterdir():
        m = re.match(r"^(\d{4})-card\.json$", f.name)
        if m:
            next_num = max(next_num, int(m.group(1)) + 1)
    filename = f"{next_num:04d}-card.json"
    (sources_dir / filename).write_text(
        json.dumps(card_json, indent=2, ensure_ascii=False), encoding="utf-8"
    )
    return filename


def delete_source(template_id: str, filename: str) -> bool:
    """Delete a source file by bare filename. Returns True if deleted."""
    if ".." in filename or "/" in filename or "\\" in filename:
        return False
    folder = template_dir(template_id)
    path = folder / "sources" / filename
    if not path.is_file():
        return False
    try:
        path.unlink()
        return True
    except OSError:
        return False
