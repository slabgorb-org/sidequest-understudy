"""Per-seat model factory. Spec form: '<backend>/<model-id>' (e.g.
'anthropic/claude-haiku-4-5-20251001', 'ollama/qwen3:8b', 'claude_p/haiku',
or bare 'fake' for the scripted lane). Unknown backend = loud failure."""

from __future__ import annotations

from understudy.brain.core import ActionModel, FakeActionModel
from understudy.brain.llm.anthropic_model import AnthropicModel
from understudy.brain.llm.claude_p_model import ClaudePModel
from understudy.brain.llm.ollama_model import OllamaModel


def make_model(spec: str) -> ActionModel:
    backend, _, model_id = spec.partition("/")
    match backend:
        case "anthropic":
            return AnthropicModel(model_id)
        case "ollama":
            return OllamaModel(model_id)
        case "claude_p":
            return ClaudePModel(model_id or "haiku")
        case "fake":
            return FakeActionModel([])
        case _:
            raise ValueError(f"unknown model backend: {spec!r}")
