"""Base interface for LLM providers + shared helpers.

A provider exposes a single async generator that yields normalized events
from the underlying LLM API:

  {"type": "first_token", "ms": int}
  {"type": "delta", "text": str}              # only when delta.content non-empty
  {"type": "model", "name": str}              # from chunk["model"]
  {"type": "usage", "data": dict}             # from chunk["usage"]

The event format is what callers expect — providers translate from their
native API (OpenAI SSE, Anthropic events, llama-server SSE, ...) into this.

Heartbeat + first-token timing + periodic progress logging are concerns
shared across providers. Helpers live here so each provider doesn't
re-invent them.
"""
from __future__ import annotations

import asyncio
import logging
import time
from typing import AsyncIterator, Protocol

log = logging.getLogger("pendrift.providers")


class LLMProvider(Protocol):
    """Protocol every provider must satisfy.

    `body` is an OpenAI-compatible chat completion body (messages, sampling
    params, optional structured-output marker). Each provider is responsible
    for translating provider-specific bits (e.g., GBNF grammar → JSON Schema
    response_format, parameter renames, auth headers).
    """

    name: str

    def sse_completion(
        self,
        body: dict,
        *,
        activity_call=None,
        kind: str = "completion",
    ) -> AsyncIterator[dict]:
        ...

    def get_default_prompt(self, kind: str) -> str:
        ...


# ── Shared helpers ──────────────────────────────────────
def start_heartbeat(kind: str) -> tuple[asyncio.Event, asyncio.Task]:
    """Start a "still waiting…" heartbeat that logs every 10s while we're
    waiting for the first token. Caller sets the returned Event when the
    first token arrives. Returns (stop_event, task)."""
    stop = asyncio.Event()

    async def _beat():
        hb_start = time.monotonic()
        while not stop.is_set():
            try:
                await asyncio.wait_for(stop.wait(), timeout=10.0)
                return
            except asyncio.TimeoutError:
                log.info(
                    "[%s] still waiting… (%ds elapsed, server likely prompt-processing)",
                    kind, int(time.monotonic() - hb_start),
                )

    task = asyncio.create_task(_beat())
    return stop, task


class ProgressLogger:
    """Logs `streaming… N tokens (X tok/s)` every ~5s after first token."""

    def __init__(self, kind: str, interval_s: float = 5.0):
        self.kind = kind
        self.interval_s = interval_s
        self.first_token_at: float | None = None
        self._last_log = 0.0
        self._tokens = 0

    def first_token(self, ms: int) -> None:
        self.first_token_at = time.time()

    def tick(self) -> None:
        self._tokens += 1
        now = time.monotonic()
        if now - self._last_log <= self.interval_s:
            return
        elapsed = (time.time() - self.first_token_at) if self.first_token_at else 0.0
        rate = self._tokens / elapsed if elapsed > 0.1 else 0.0
        log.info(
            "[%s] streaming… %d content tokens (%.1f tok/s)",
            self.kind, self._tokens, rate,
        )
        self._last_log = now

    @property
    def token_count(self) -> int:
        return self._tokens
