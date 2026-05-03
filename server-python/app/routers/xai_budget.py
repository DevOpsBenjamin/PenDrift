"""Routes for the xAI budget widget."""
from fastapi import APIRouter

from app.services import xai_budget

router = APIRouter()


@router.get("")
async def get_budget():
    """Return the current xAI budget snapshot.

    Bootstraps lazily on first hit when an `XAI_MANAGEMENT_KEY` is set;
    subsequent calls return the in-RAM state (estimated after local decrements)."""
    await xai_budget.bootstrap_if_needed()
    return xai_budget.snapshot()


@router.post("/refresh")
async def refresh_budget():
    """Force a resync with xAI's billing API. Resets the `estimated` flag."""
    await xai_budget.refresh()
    return xai_budget.snapshot()
