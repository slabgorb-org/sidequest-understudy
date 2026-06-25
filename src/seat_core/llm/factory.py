"""Per-seat model factory. Spec form '<backend>/<model-id>' (e.g.
'anthropic/claude-haiku-4-5-20251001', 'ollama/qwen3:8b', 'claude_p/haiku')
or bare 'fake'. Unknown backend = loud failure."""

from __future__ import annotations

from pydantic import BaseModel

from seat_core.core import FakeStructuredModel, StructuredModel
from seat_core.llm.anthropic_model import AnthropicModel
from seat_core.llm.claude_p_model import ClaudePModel
from seat_core.llm.ollama_model import OllamaModel


def make_model(
    spec: str, output_model: type[BaseModel], *, default: BaseModel | None = None
) -> StructuredModel:
    backend, _, model_id = spec.partition("/")
    match backend:
        case "anthropic":
            return AnthropicModel(model_id, output_model)
        case "ollama":
            return OllamaModel(model_id, output_model)
        case "claude_p":
            return ClaudePModel(model_id or "haiku", output_model)
        case "fake":
            if default is None:
                raise ValueError("fake backend requires a default value")
            return FakeStructuredModel([], default)
        case _:
            raise ValueError(f"unknown model backend: {spec!r}")
