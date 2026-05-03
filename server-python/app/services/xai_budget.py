"""xAI billing budget tracker.

Holds an in-process singleton describing the team's prepaid balance and usage
in the current billing cycle. Bootstrapped from xAI's Management API
(`/auth/management-keys/validation` + `/v1/billing/teams/{id}/postpaid/invoice/preview`)
when an `XAI_MANAGEMENT_KEY` is set in the env.

Each successful xAI chat completion calls `apply_local_cost(ticks)` to
decrement the in-RAM remaining balance — this is an estimate that drifts
from the server until `refresh()` resyncs. The UI flags this divergence as
"estimated" so the user knows the figure may be off (e.g. if usage happened
outside PenDrift between syncs).

All internal state is stored in **ticks** (10 billion ticks = $1) for
precision; conversion to USD is done at the API edge for display.
"""
from __future__ import annotations

import asyncio
import logging
import os
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any

import httpx

log = logging.getLogger("pendrift.xai_budget")

_MANAGEMENT_BASE = "https://management-api.x.ai"
_TICKS_PER_DOLLAR = 10_000_000_000
_TICKS_PER_CENT = _TICKS_PER_DOLLAR // 100  # 100_000_000


@dataclass
class XaiBudgetState:
    configured: bool = False                    # XAI_MANAGEMENT_KEY present
    team_id: str | None = None
    prepaid_total_ticks: int | None = None      # |prepaidCredits|
    prepaid_used_ticks: int | None = None       # |prepaidCreditsUsed| (current cycle only)
    last_synced_at: float | None = None         # unix seconds
    estimated: bool = False                     # True after any local decrement since sync
    local_decrements_since_sync: int = 0
    billing_cycle_year: int | None = None
    billing_cycle_month: int | None = None
    last_error: str | None = None

    @property
    def prepaid_remaining_ticks(self) -> int | None:
        if self.prepaid_total_ticks is None or self.prepaid_used_ticks is None:
            return None
        return max(0, self.prepaid_total_ticks - self.prepaid_used_ticks)


_state = XaiBudgetState()
_lock = asyncio.Lock()


def _management_key() -> str | None:
    key = os.environ.get("XAI_MANAGEMENT_KEY", "").strip()
    if not key or key in ("<REPLACEHER>", "<REPLACE WITH GROK PROMPT>"):
        return None
    return key


def is_configured() -> bool:
    """Cheap check (just env var). Use for the SettingsView indicator."""
    return _management_key() is not None


async def _validate_key(key: str, client: httpx.AsyncClient) -> dict:
    r = await client.get(
        f"{_MANAGEMENT_BASE}/auth/management-keys/validation",
        headers={"Authorization": f"Bearer {key}"},
    )
    r.raise_for_status()
    return r.json()


async def _fetch_invoice_preview(team_id: str, key: str, client: httpx.AsyncClient) -> dict:
    r = await client.get(
        f"{_MANAGEMENT_BASE}/v1/billing/teams/{team_id}/postpaid/invoice/preview",
        headers={"Authorization": f"Bearer {key}"},
    )
    r.raise_for_status()
    return r.json()


def _cents_str_to_ticks(val: Any) -> int:
    """Billing API returns cents as signed strings (e.g. '-2500' for $25 of credit).
    Take absolute value and convert to ticks. Returns 0 on parse failure."""
    try:
        return abs(int(val)) * _TICKS_PER_CENT
    except (TypeError, ValueError):
        return 0


async def _sync_from_server() -> None:
    """Hit validation + invoice/preview, update _state. Caller holds the lock."""
    key = _management_key()
    if not key:
        _state.configured = False
        _state.last_error = "XAI_MANAGEMENT_KEY not set"
        return

    _state.configured = True
    try:
        async with httpx.AsyncClient(timeout=15) as client:
            if not _state.team_id:
                meta = await _validate_key(key, client)
                _state.team_id = meta.get("teamId") or meta.get("scopeId")
                if not _state.team_id:
                    raise RuntimeError("No teamId in validation response")
            invoice = await _fetch_invoice_preview(_state.team_id, key, client)
    except (httpx.HTTPError, RuntimeError) as e:
        _state.last_error = str(e)
        log.warning("xAI budget sync failed: %s", e)
        return

    core = invoice.get("coreInvoice") or {}
    prepaid_credits = (core.get("prepaidCredits") or {}).get("val")
    prepaid_used = (core.get("prepaidCreditsUsed") or {}).get("val")
    cycle = invoice.get("billingCycle") or {}

    _state.prepaid_total_ticks = _cents_str_to_ticks(prepaid_credits)
    _state.prepaid_used_ticks = _cents_str_to_ticks(prepaid_used)
    _state.billing_cycle_year = cycle.get("year")
    _state.billing_cycle_month = cycle.get("month")
    _state.last_synced_at = datetime.now(timezone.utc).timestamp()
    _state.estimated = False
    _state.local_decrements_since_sync = 0
    _state.last_error = None
    log.info(
        "xAI budget synced: total=%s ticks, used=%s ticks (%d/%d)",
        _state.prepaid_total_ticks, _state.prepaid_used_ticks,
        _state.billing_cycle_month or 0, _state.billing_cycle_year or 0,
    )


async def bootstrap_if_needed() -> None:
    """Sync once on first need. Idempotent — subsequent calls are no-ops if
    we already have a snapshot, regardless of staleness."""
    async with _lock:
        if _state.last_synced_at is not None or not _management_key():
            # Already synced, OR no key configured.
            _state.configured = _management_key() is not None
            return
        await _sync_from_server()


async def refresh() -> XaiBudgetState:
    """Force a resync. Used by the manual refresh button."""
    async with _lock:
        await _sync_from_server()
    return _state


def apply_local_cost(ticks: int | None) -> None:
    """Decrement the in-RAM remaining balance by `ticks`. Called on each
    successful xAI completion. Marks state as estimated (drift from server)."""
    if not ticks or ticks <= 0:
        return
    if _state.prepaid_used_ticks is None or _state.prepaid_total_ticks is None:
        # Never bootstrapped — nothing to decrement against. The next refresh
        # will pull authoritative numbers.
        return
    _state.prepaid_used_ticks += int(ticks)
    _state.local_decrements_since_sync += 1
    _state.estimated = True


def snapshot() -> dict:
    """Public state for the GET endpoint. Renders ticks + USD float for the UI."""
    remaining = _state.prepaid_remaining_ticks
    return {
        "configured": _state.configured,
        "teamId": _state.team_id,
        "prepaidTotalTicks": _state.prepaid_total_ticks,
        "prepaidUsedTicks": _state.prepaid_used_ticks,
        "prepaidRemainingTicks": remaining,
        "prepaidTotalUsd": (_state.prepaid_total_ticks or 0) / _TICKS_PER_DOLLAR
            if _state.prepaid_total_ticks is not None else None,
        "prepaidUsedUsd": (_state.prepaid_used_ticks or 0) / _TICKS_PER_DOLLAR
            if _state.prepaid_used_ticks is not None else None,
        "prepaidRemainingUsd": remaining / _TICKS_PER_DOLLAR if remaining is not None else None,
        "lastSyncedAt": _state.last_synced_at,
        "estimated": _state.estimated,
        "localDecrementsSinceSync": _state.local_decrements_since_sync,
        "billingCycle": {
            "year": _state.billing_cycle_year,
            "month": _state.billing_cycle_month,
        } if _state.billing_cycle_year else None,
        "lastError": _state.last_error,
    }
