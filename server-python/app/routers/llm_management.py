"""Routes for managing the llama-server process (load/unload models, auto-download)."""
from pathlib import Path

from fastapi import APIRouter, HTTPException

from app.models import LoadModelRequest, LlmStatus
from app.services import llm_process
from app.services import llm_updater

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

    exe = _get_exe()
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


def _get_exe() -> str:
    global _llama_server_exe
    # Auto-detect from downloaded version
    if not _llama_server_exe:
        auto = llm_updater.get_exe_path()
        if auto:
            _llama_server_exe = str(auto)
    if _llama_server_exe:
        return _llama_server_exe
    raise HTTPException(400, "llama-server not found. Use POST /api/llm/download to install it, or POST /api/llm/configure to set the path manually.")
