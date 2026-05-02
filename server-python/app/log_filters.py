"""Logging filters for uvicorn access logs."""
import logging


class SilentPathsFilter(logging.Filter):
    """Drop uvicorn access logs for high-frequency polling endpoints."""

    QUIET = (
        "/api/llm/activity",
        "/api/llm/logs",
    )

    def filter(self, record: logging.LogRecord) -> bool:
        msg = record.getMessage()
        return not any(path in msg for path in self.QUIET)
