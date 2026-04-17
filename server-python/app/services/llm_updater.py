"""Auto-download and version-manage llama-server binaries from GitHub releases."""
from __future__ import annotations

import json
import logging
import shutil
import zipfile
from pathlib import Path

import httpx

from app.config import DATA_DIR

log = logging.getLogger("pendrift.llm_updater")

LLAMA_DIR = DATA_DIR / "llama-server"
VERSION_FILE = LLAMA_DIR / "version.json"

GITHUB_API = "https://api.github.com/repos/ggml-org/llama.cpp/releases/latest"

# Asset name patterns — CUDA 13.1 for Blackwell/modern, CUDA 12.4 as fallback
ASSET_PATTERNS = {
    "cuda13": {
        "bin": "llama-{tag}-bin-win-cuda-13.1-x64.zip",
        "cudart": "cudart-llama-bin-win-cuda-13.1-x64.zip",
    },
    "cuda12": {
        "bin": "llama-{tag}-bin-win-cuda-12.4-x64.zip",
        "cudart": "cudart-llama-bin-win-cuda-12.4-x64.zip",
    },
    "cpu": {
        "bin": "llama-{tag}-bin-win-cpu-x64.zip",
    },
}


def get_exe_path() -> Path | None:
    """Return the path to llama-server.exe if it exists."""
    exe = LLAMA_DIR / "llama-server.exe"
    if exe.is_file():
        return exe
    return None


def get_installed_version() -> dict | None:
    """Return the currently installed version info, or None."""
    if VERSION_FILE.is_file():
        return json.loads(VERSION_FILE.read_text(encoding="utf-8"))
    return None


async def check_latest_version() -> dict:
    """Query GitHub for the latest llama.cpp release."""
    async with httpx.AsyncClient(timeout=15) as client:
        r = await client.get(GITHUB_API, headers={"User-Agent": "PenDrift/0.2"})
        r.raise_for_status()
        data = r.json()

    tag = data["tag_name"]
    assets = {}
    for a in data.get("assets", []):
        assets[a["name"]] = a["browser_download_url"]

    return {"tag": tag, "assets": assets, "published": data.get("published_at")}


async def download_and_install(variant: str = "cuda13") -> dict:
    """Download the latest llama-server release and extract to LLAMA_DIR.

    Args:
        variant: "cuda13" (default, for RTX 50xx+), "cuda12", or "cpu"

    Returns:
        {"tag": "b8827", "variant": "cuda13", "exe": "path/to/llama-server.exe"}
    """
    release = await check_latest_version()
    tag = release["tag"]
    all_assets = release["assets"]
    patterns = ASSET_PATTERNS.get(variant, ASSET_PATTERNS["cuda13"])

    # Resolve asset URLs
    urls_to_download = []
    for key, pattern in patterns.items():
        name = pattern.format(tag=tag)
        url = all_assets.get(name)
        if not url:
            raise ValueError(f"Asset not found in release {tag}: {name}")
        urls_to_download.append((name, url))

    # Clean old install
    if LLAMA_DIR.exists():
        # Keep version.json for reference
        for item in LLAMA_DIR.iterdir():
            if item.name == "version.json":
                continue
            if item.is_dir():
                shutil.rmtree(item)
            else:
                item.unlink()
    LLAMA_DIR.mkdir(parents=True, exist_ok=True)

    # Download and extract each zip
    async with httpx.AsyncClient(timeout=300, follow_redirects=True) as client:
        for name, url in urls_to_download:
            log.info("Downloading %s ...", name)
            zip_path = LLAMA_DIR / name

            # Stream download
            async with client.stream("GET", url) as resp:
                resp.raise_for_status()
                with open(zip_path, "wb") as f:
                    async for chunk in resp.aiter_bytes(chunk_size=65536):
                        f.write(chunk)

            # Extract
            log.info("Extracting %s ...", name)
            with zipfile.ZipFile(zip_path, "r") as zf:
                zf.extractall(LLAMA_DIR)
            zip_path.unlink()

    # Find llama-server.exe (might be in a subfolder)
    exe = None
    for p in LLAMA_DIR.rglob("llama-server.exe"):
        exe = p
        break

    if not exe:
        raise FileNotFoundError("llama-server.exe not found after extraction")

    # Move everything to LLAMA_DIR root if it was in a subfolder
    if exe.parent != LLAMA_DIR:
        for item in exe.parent.iterdir():
            dest = LLAMA_DIR / item.name
            if dest.exists():
                if dest.is_dir():
                    shutil.rmtree(dest)
                else:
                    dest.unlink()
            shutil.move(str(item), str(dest))
        # Clean empty subfolder
        if exe.parent.exists() and exe.parent != LLAMA_DIR:
            shutil.rmtree(exe.parent, ignore_errors=True)

    exe = LLAMA_DIR / "llama-server.exe"

    # Save version info
    version_info = {
        "tag": tag,
        "variant": variant,
        "published": release.get("published"),
        "exe": str(exe),
    }
    VERSION_FILE.write_text(json.dumps(version_info, indent=2), encoding="utf-8")

    log.info("llama-server %s (%s) installed at %s", tag, variant, exe)
    return version_info
