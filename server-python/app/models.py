"""Pydantic models for API request/response validation."""
from __future__ import annotations

from pydantic import BaseModel, Field


# ── Sessions ────────────────────────────────────────────

class SessionCreate(BaseModel):
    template_id: str = Field(alias="templateId")
    title: str | None = None
    settings_preset_id: str = Field(default="default", alias="settingsPresetId")

class SessionUpdate(BaseModel):
    title: str | None = None
    settings_preset_id: str | None = Field(default=None, alias="settingsPresetId")

class ChapterInfo(BaseModel):
    id: str
    title: str
    order: int
    finalized: bool
    created_at: str = Field(alias="createdAt")

class SessionOut(BaseModel):
    id: str
    title: str
    template_id: str = Field(alias="templateId")
    settings_preset_id: str = Field(alias="settingsPresetId")
    chapters: list[ChapterInfo] = []
    cover_image: str | None = Field(default=None, alias="coverImage")
    created_at: str = Field(alias="createdAt")
    updated_at: str = Field(alias="updatedAt")
    last_meta_after_chunk_index: int | None = Field(default=None, alias="lastMetaAfterChunkIndex")

    model_config = {"populate_by_name": True}


# ── Chunks ──────────────────────────────────────────────

class ChunkVersion(BaseModel):
    narrative: str
    thinking: str | None = None
    stats: dict = {}
    directive: str | None = None
    source: str = Field(default="narrative", alias="from")
    created_at: str = Field(alias="createdAt")

class ChunkOut(BaseModel):
    id: str
    session_id: str = Field(alias="sessionId")
    chapter_id: str = Field(alias="chapterId")
    order: int
    active_version: int = Field(alias="activeVersion")
    versions: list[ChunkVersion]
    is_key_moment: bool = Field(default=False, alias="isKeyMoment")
    image_prompt: str | None = Field(default=None, alias="imagePrompt")
    image_path: str | None = Field(default=None, alias="imagePath")
    audio_path: str | None = Field(default=None, alias="audioPath")

    model_config = {"populate_by_name": True}

class ChunkEdit(BaseModel):
    narrative: str

class VersionSwitch(BaseModel):
    version_index: int = Field(alias="versionIndex")

class VersionDelete(BaseModel):
    version_index: int = Field(alias="versionIndex")


# ── Characters ──────────────────────────────────────────

class CharacterOut(BaseModel):
    name: str
    current_state: str | None = Field(default=None, alias="currentState")
    traits: list[str] = []
    key_events: list[str] = Field(default=[], alias="keyEvents")
    last_updated: str | None = Field(default=None, alias="lastUpdated")

    model_config = {"populate_by_name": True}

class CharacterCreate(BaseModel):
    name: str
    current_state: str | None = Field(default=None, alias="currentState")
    traits: list[str] = []
    key_events: list[str] = Field(default=[], alias="keyEvents")

class CharacterUpdate(BaseModel):
    current_state: str | None = Field(default=None, alias="currentState")
    traits: list[str] | None = None
    key_events: list[str] | None = Field(default=None, alias="keyEvents")


# ── Generation ──────────────────────────────────────────

class GenerateRequest(BaseModel):
    chapter_id: str = Field(alias="chapterId")
    directive: str | None = None
    is_key_moment: bool = Field(default=False, alias="isKeyMoment")

class RegenerateRequest(BaseModel):
    chunk_id: str = Field(alias="chunkId")
    chapter_id: str = Field(alias="chapterId")
    directive: str | None = None

class JobStatus(BaseModel):
    status: str
    result: dict | None = None
    error: str | None = None


# ── LLM Management ─────────────────────────────────────

class LoadModelRequest(BaseModel):
    model_path: str = Field(alias="modelPath")
    gpu_layers: int = Field(default=99, alias="gpuLayers")
    context_size: int = Field(default=65536, alias="contextSize")
    port: int = 8080

class LlmStatus(BaseModel):
    running: bool
    model_path: str | None = Field(default=None, alias="modelPath")
    port: int | None = None


# ── Meta ────────────────────────────────────────────────

class MetaTrigger(BaseModel):
    chapter_id: str | None = Field(default=None, alias="chapterId")

class FactsUpdate(BaseModel):
    facts: list[str]
