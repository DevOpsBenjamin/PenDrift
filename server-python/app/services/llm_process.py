"""Manage the llama-server subprocess lifecycle."""
import asyncio
import os
import subprocess
import logging

import httpx

from app.config import DATA_DIR

log = logging.getLogger("pendrift.llm_process")

_process: subprocess.Popen | None = None
_model_path: str | None = None
_port: int = 8080

# llama-server writes logs to this file via its --log-file flag.
# Stdout still goes to the parent terminal (live) — see start_server below.
_LOG_PATH = DATA_DIR / "llama-server.log"


def get_log_tail(lines: int = 200) -> list[str]:
    """Return the last N lines from llama-server's log file."""
    if lines <= 0 or not _LOG_PATH.is_file():
        return []
    try:
        # Read full file; fine for typical sizes (MBs). For huge files we'd seek from end.
        with _LOG_PATH.open("r", encoding="utf-8", errors="replace") as f:
            all_lines = f.read().splitlines()
        return all_lines[-lines:]
    except OSError:
        return []


def reap_orphans() -> int:
    """Kill any stale llama-server.exe processes left over from previous runs
    (e.g., after a force-close that skipped graceful shutdown). Returns the
    number killed (best-effort, silent on failure)."""
    if os.name == "nt":
        result = subprocess.run(
            ["taskkill", "/F", "/IM", "llama-server.exe"],
            capture_output=True, text=True,
        )
        # taskkill returns 0 on kill, 128 when no matching process.
        if result.returncode == 0:
            killed = result.stdout.count("SUCCESS")
            if killed:
                log.info("Reaped %d orphan llama-server.exe process(es)", killed)
            return killed
        return 0
    # POSIX
    result = subprocess.run(
        ["pkill", "-9", "-f", "llama-server"],
        capture_output=True, text=True,
    )
    return 1 if result.returncode == 0 else 0


def is_running() -> bool:
    return _process is not None and _process.poll() is None


def current_status() -> dict:
    return {
        "running": is_running(),
        "modelPath": _model_path,
        "port": _port if is_running() else None,
    }


async def start_server(
    llama_server_exe: str,
    model_path: str,
    port: int = 8080,
    gpu_layers: int = 99,
    context_size: int = 65536,
) -> None:
    global _process, _model_path, _port

    # Kill existing if running
    if is_running():
        await stop_server()

    _LOG_PATH.parent.mkdir(parents=True, exist_ok=True)
    cmd = [
        llama_server_exe,
        "-m", model_path,
        "--port", str(port),
        "--n-gpu-layers", str(gpu_layers),
        "--ctx-size", str(context_size),
        "--host", "127.0.0.1",
        "--slots",
        "--metrics",
        "--log-file", str(_LOG_PATH),
    ]

    log.info("Starting llama-server: %s", " ".join(cmd))
    # Silence llama-server's stdout/stderr in our Python terminal — its verbose
    # logs clutter the flow. llama-server still writes everything to
    # `data/llama-server.log` via --log-file for post-mortem/Activity panel.
    _process = subprocess.Popen(
        cmd,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    _model_path = model_path
    _port = port

    # Wait for server to be ready (poll /health)
    base = f"http://127.0.0.1:{port}"
    async with httpx.AsyncClient() as client:
        for attempt in range(60):  # up to 60s
            if _process.poll() is not None:
                raise RuntimeError(
                    f"llama-server exited during startup (code {_process.returncode}) — see terminal output above"
                )
            try:
                r = await client.get(f"{base}/health", timeout=2)
                if r.status_code == 200:
                    log.info("llama-server ready on port %d", port)
                    return
            except httpx.ConnectError:
                pass
            await asyncio.sleep(1)

    raise TimeoutError("llama-server did not become ready within 60s")


async def stop_server() -> None:
    global _process, _model_path
    if _process is not None:
        log.info("Stopping llama-server (pid=%d)", _process.pid)
        _process.terminate()
        try:
            _process.wait(timeout=10)
        except subprocess.TimeoutExpired:
            _process.kill()
        _process = None
        _model_path = None


def get_base_url() -> str:
    if not is_running():
        raise RuntimeError("llama-server is not running. Load a model first.")
    return f"http://127.0.0.1:{_port}"


async def ensure_loaded(settings: dict) -> bool:
    """Start llama-server using `settings` (modelPath/port/gpuLayers/contextSize)
    if it's not already running. Returns True if a load was performed, False if
    already running. Raises RuntimeError if the preset has no modelPath, or
    propagates HTTPException from get_exe() / start_server errors."""
    if is_running():
        return False
    model_path = settings.get("modelPath")
    if not model_path:
        raise RuntimeError(
            "No model is loaded and the preset has no modelPath. Set one in Settings."
        )
    from app.routers.llm_management import get_exe
    exe = get_exe()
    await start_server(
        llama_server_exe=exe,
        model_path=model_path,
        port=settings.get("port", 8080),
        gpu_layers=settings.get("gpuLayers", 99),
        context_size=settings.get("contextSize", 65536),
    )
    return True
