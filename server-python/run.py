"""Entry point for the PenDrift Python backend."""
import os
import copy

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
