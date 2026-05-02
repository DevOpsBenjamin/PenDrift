"""Routes for managing the llama-server process (load/unload models, auto-download)."""
import os
import string
from pathlib import Path

from fastapi import APIRouter, HTTPException

from app.models import LoadModelRequest, LlmStatus
from app.services import llm_process
from app.services import llm_updater
from app.services import llm_activity

router = APIRouter()

# Path to llama-server binary — auto-detected or manually set
_llama_server_exe: str | None = None


@router.get("/status")
async def llm_status():
    installed = llm_updater.get_installed_version()
    return {
        **llm_process.current_status(),
        "installedVersion": installed,
        "exePath": _llama_server_exe or (str(llm_updater.get_exe_path()) if llm_updater.get_exe_path() else None),
    }


@router.post("/load")
async def load_model(req: LoadModelRequest):
    model_path = req.model_path
    if not Path(model_path).is_file():
        raise HTTPException(400, f"Model file not found: {model_path}")

    exe = get_exe()
    try:
        await llm_process.start_server(
            llama_server_exe=exe,
            model_path=model_path,
            port=req.port,
            gpu_layers=req.gpu_layers,
            context_size=req.context_size,
        )
    except (RuntimeError, TimeoutError) as e:
        raise HTTPException(500, str(e))

    return {"ok": True, **llm_process.current_status()}


@router.post("/unload")
async def unload_model():
    await llm_process.stop_server()
    return {"ok": True}


@router.post("/configure")
async def configure_exe(body: dict):
    """Set the path to the llama-server executable manually."""
    global _llama_server_exe
    exe_path = body.get("executablePath")
    if not exe_path or not Path(exe_path).is_file():
        raise HTTPException(400, f"Executable not found: {exe_path}")
    _llama_server_exe = exe_path
    return {"ok": True, "executablePath": _llama_server_exe}


# ── Auto-download management ────────────────────────────

@router.get("/version")
async def get_version():
    """Get installed and latest available versions."""
    installed = llm_updater.get_installed_version()
    try:
        latest = await llm_updater.check_latest_version()
        latest_tag = latest["tag"]
    except Exception:
        latest_tag = None

    return {
        "installed": installed,
        "latest": latest_tag,
        "updateAvailable": installed is not None and latest_tag is not None and installed.get("tag") != latest_tag,
        "exePath": str(llm_updater.get_exe_path()) if llm_updater.get_exe_path() else None,
    }


@router.post("/download")
async def download_llama_server(body: dict = {}):
    """Download the latest llama-server release from GitHub.

    Body:
    - variant: "cuda13" (default, RTX 50xx), "cuda12" (older cards), "cpu"
    """
    variant = body.get("variant", "cuda13")
    if variant not in ("cuda13", "cuda12", "cpu"):
        raise HTTPException(400, f"Unknown variant: {variant}. Use cuda13, cuda12, or cpu.")

    try:
        result = await llm_updater.download_and_install(variant)
    except Exception as e:
        raise HTTPException(500, f"Download failed: {e}")

    # Auto-configure the exe path
    global _llama_server_exe
    _llama_server_exe = result["exe"]

    return result


@router.post("/cancel/{call_id}")
async def cancel_call(call_id: str):
    """Cancel an in-flight LLM call by ID."""
    if not llm_activity.cancel(call_id):
        raise HTTPException(404, "Call not found or already finished")
    return {"ok": True, "id": call_id}


@router.get("/response/{filename}")
async def get_response_dump(filename: str):
    """Return a stored LLM raw response dump (by filename from activity snapshot)."""
    return _read_dump(filename, "llm-responses")


@router.get("/request/{filename}")
async def get_request_dump(filename: str):
    """Return a stored LLM request body (messages + samplers + grammar)."""
    return _read_dump(filename, "llm-requests")


def _read_dump(filename: str, subdir: str) -> dict:
    from app.config import DATA_DIR
    if "/" in filename or "\\" in filename or ".." in filename:
        raise HTTPException(400, "Invalid filename")
    path = DATA_DIR / subdir / filename
    if not path.is_file():
        raise HTTPException(404, "Dump not found")
    return {"filename": filename, "content": path.read_text(encoding="utf-8")}


@router.get("/logs")
async def get_logs(lines: int = 200):
    """Return the last N lines from llama-server stdout (captured via tee).
    0 or negative returns empty; full buffer is up to 1000 lines."""
    return {"lines": llm_process.get_log_tail(lines)}


@router.get("/activity")
async def get_activity():
    """Snapshot of LLM call activity: queued/running/history. Live metrics
    (tokens generated, tok/s, TTFT) are pushed into the tracker from the SSE
    reader, so we no longer poll llama-server — nothing touches its log loop."""
    snap = llm_activity.snapshot()
    return {
        "active": snap["active"],
        "history": snap["history"],
        "llamaServer": {"running": llm_process.is_running()},
    }


@router.get("/browse")
async def browse_filesystem(path: str | None = None):
    """List directories and .gguf files for the in-app file picker.

    - `path=None` or empty: returns available drives (Windows) or `/` (POSIX).
    - Otherwise lists immediate subdirectories and `.gguf` files at that path.
    """
    if not path:
        if os.name == "nt":
            drives = [
                f"{letter}:\\"
                for letter in string.ascii_uppercase
                if Path(f"{letter}:\\").exists()
            ]
            return {"currentPath": "", "parent": None, "directories": drives, "files": []}
        return {"currentPath": "/", "parent": None, "directories": ["/"], "files": []}

    p = Path(path).resolve()
    if not p.is_dir():
        raise HTTPException(400, f"Not a directory: {path}")

    dirs: list[str] = []
    files: list[dict] = []
    try:
        with os.scandir(p) as it:
            for entry in it:
                try:
                    if entry.is_dir(follow_symlinks=False) and not entry.name.startswith("."):
                        dirs.append(entry.name)
                    elif entry.is_file(follow_symlinks=False) and entry.name.lower().endswith(".gguf"):
                        files.append({"name": entry.name, "size": entry.stat().st_size})
                except (OSError, PermissionError):
                    continue
    except PermissionError:
        raise HTTPException(403, f"Permission denied: {path}")

    dirs.sort(key=str.lower)
    files.sort(key=lambda f: f["name"].lower())

    parent = str(p.parent) if p.parent != p else None

    return {
        "currentPath": str(p),
        "parent": parent,
        "directories": dirs,
        "files": files,
    }


def get_exe() -> str:
    global _llama_server_exe
    # Auto-detect from downloaded version
    if not _llama_server_exe:
        auto = llm_updater.get_exe_path()
        if auto:
            _llama_server_exe = str(auto)
    if _llama_server_exe:
        return _llama_server_exe
    raise HTTPException(400, "llama-server not found. Use POST /api/llm/download to install it, or POST /api/llm/configure to set the path manually.")
