"""Entry point for the PenDrift Python backend."""
import asyncio
import os
import sys
import copy
from dotenv import load_dotenv

load_dotenv()

# Windows: switch from the default ProactorEventLoop to SelectorEventLoop.
# Proactor uses I/O completion ports which can starve the accept loop while
# a long-running async stream (httpx → llama-server SSE during prompt
# processing) holds a socket. Symptom: heartbeats keep firing (the loop is
# alive for timers) but new HTTP connections queue indefinitely — F5 spins,
# Activity won't poll, etc. Selector trades a bit of throughput for fairness
# and is the documented workaround for this pattern.
# Trade-off: SelectorEventLoop on Windows doesn't support subprocess pipes
# directly, but PenDrift only spawns llama-server with stdout/stderr=DEVNULL
# (no pipe reading from Python), so this is safe.
if sys.platform == "win32":
    asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())

import uvicorn
from uvicorn.config import LOGGING_CONFIG


def _build_log_config():
    cfg = copy.deepcopy(LOGGING_CONFIG)
    cfg.setdefault("filters", {})["silence_polling"] = {
        "()": "app.log_filters.SilentPathsFilter",
    }
    cfg["handlers"]["access"]["filters"] = ["silence_polling"]
    # Route our own loggers through uvicorn's default handler at INFO level
    cfg["loggers"]["pendrift"] = {
        "handlers": ["default"],
        "level": "INFO",
        "propagate": False,
    }
    return cfg


if __name__ == "__main__":
    dev = os.environ.get("PENDRIFT_DEV") == "1"
    try:
        uvicorn.run(
            "app.main:app",
            host="0.0.0.0",
            port=3000,
            reload=dev,
            log_config=_build_log_config(),
        )
    finally:
        # Windows + asyncio ProactorEventLoop can leave non-daemon threads alive
        # after uvicorn returns, blocking interpreter shutdown. Force-kill.
        os._exit(0)
