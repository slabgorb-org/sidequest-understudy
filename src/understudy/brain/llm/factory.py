"""Per-seat model factory. Spec form: '<backend>/<model-id>' (e.g.
'anthropic/claude-haiku-4-5-20251001', 'ollama/qwen3:8b', 'claude_p/haiku',
or bare 'fake' for the scripted lane). Unknown backend = loud failure.

Thin understudy binding over seat_core's generic factory: every real backend is
constructed for understudy's `Intent` payload, and 'fake' returns the
Intent-defaulting `FakeActionModel` (no explicit default value required, unlike
seat_core's generic `make_model('fake', ...)`)."""

from __future__ import annotations

from seat_core.llm.factory import make_model as _make_model

from understudy.brain.core import ActionModel, FakeActionModel
from understudy.types import Intent


def make_model(spec: str) -> ActionModel:
    if spec.partition("/")[0] == "fake":
        return FakeActionModel([])
    return _make_model(spec, Intent)
