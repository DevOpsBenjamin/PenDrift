"""Read-only API for the bundled system prompts.

These prompts ship with the app code (see app/prompts/*.md). The UI uses these
endpoints to display the current system default and let users decide whether
to override it per-preset. To EDIT a default, edit the .md file in source.
"""
from __future__ import annotations

from fastapi import APIRouter, HTTPException

from app.services import prompts_registry

router = APIRouter()


@router.get("")
async def list_prompts():
    return prompts_registry.list_prompts()


@router.get("/{name}")
async def get_prompt(name: str):
    body = prompts_registry.get_prompt(name)
    if body is None:
        raise HTTPException(404, f"No bundled prompt named '{name}'")
    return {"name": name, "body": body}
