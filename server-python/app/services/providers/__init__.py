"""LLM provider registry.

Each provider implements the `LLMProvider` protocol from `base.py` —
a single async generator that yields normalized events from the underlying
LLM API. Higher-level code (services/llm.py, services/llm_stream.py,
chub_importer, meta_analysis, etc.) consumes these events without knowing
which provider is doing the work.

Add a new provider:
1. Implement `LLMProvider` in `your_provider.py`.
2. Register it below in `_PROVIDERS`.
3. Optionally expose its config in the settings UI.
"""
from __future__ import annotations

from app.services.providers.base import LLMProvider
from app.services.providers.llama_server import LlamaServerProvider
from app.services.providers.openai_compatible import OpenAICompatibleProvider
from app.services.providers.xai import XAIProvider

_PROVIDERS: dict[str, type[LLMProvider]] = {
    "llama-server": LlamaServerProvider,
    "openai": OpenAICompatibleProvider,
    "xai": XAIProvider,
    # Future:
    # "anthropic": AnthropicProvider,
    # "openrouter": OpenRouterProvider,
    # "gemini": GeminiProvider,
}


def get_provider(name: str = "llama-server", **config) -> LLMProvider:
    """Instantiate a provider by name. Unknown names raise ValueError."""
    cls = _PROVIDERS.get(name)
    if cls is None:
        raise ValueError(
            f"Unknown LLM provider: {name!r}. Available: {sorted(_PROVIDERS)}"
        )
    return cls(**config)


def list_providers() -> list[str]:
    return sorted(_PROVIDERS)


__all__ = ["LLMProvider", "get_provider", "list_providers"]
