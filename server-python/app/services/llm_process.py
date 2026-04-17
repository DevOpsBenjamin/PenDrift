"""Manage the llama-server subprocess lifecycle."""
import asyncio
import subprocess
import logging

import httpx

log = logging.getLogger("pendrift.llm_process")

_process: subprocess.Popen | None = None
_model_path: str | None = None
_port: int = 8080


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

    cmd = [
        llama_server_exe,
        "-m", model_path,
        "--port", str(port),
        "--n-gpu-layers", str(gpu_layers),
        "--ctx-size", str(context_size),
        "--host", "127.0.0.1",
    ]

    log.info("Starting llama-server: %s", " ".join(cmd))
    _process = subprocess.Popen(
        cmd,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        creationflags=subprocess.CREATE_NO_WINDOW if hasattr(subprocess, "CREATE_NO_WINDOW") else 0,
    )
    _model_path = model_path
    _port = port

    # Wait for server to be ready (poll /health)
    base = f"http://127.0.0.1:{port}"
    async with httpx.AsyncClient() as client:
        for attempt in range(60):  # up to 60s
            if _process.poll() is not None:
                stderr = _process.stderr.read().decode(errors="replace") if _process.stderr else ""
                raise RuntimeError(f"llama-server exited during startup: {stderr[:500]}")
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
