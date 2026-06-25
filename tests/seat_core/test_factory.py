from typing import Literal

import pytest
from pydantic import BaseModel

from seat_core.llm.factory import make_model


class Ping(BaseModel):
    kind: Literal["a", "b"]


def test_factory_dispatches_by_prefix(monkeypatch):
    monkeypatch.setenv("ANTHROPIC_API_KEY", "test")  # AsyncAnthropic() needs a key at construct
    assert type(make_model("anthropic/claude-haiku-4-5-20251001", Ping)).__name__ == "AnthropicModel"
    assert type(make_model("ollama/qwen3:8b", Ping)).__name__ == "OllamaModel"
    assert type(make_model("claude_p/haiku", Ping)).__name__ == "ClaudePModel"
    assert type(make_model("fake", Ping, default=Ping(kind="a"))).__name__ == "FakeStructuredModel"


def test_factory_fake_requires_default():
    with pytest.raises(ValueError, match="fake backend requires a default"):
        make_model("fake", Ping)


def test_factory_fails_loud_on_unknown_backend():
    with pytest.raises(ValueError, match="unknown model backend"):
        make_model("bard/gpt-1", Ping)


# --- TEA adversarial addition ---


def test_factory_bare_claude_p_defaults_model_id():
    # Bare "claude_p" (no /model-id) is allowed and falls back to a default model.
    assert type(make_model("claude_p", Ping)).__name__ == "ClaudePModel"
