"""Brain seam: the ActionModel protocol every backend implements.

Spec note: the protocol returns DecideResult (Intent + token usage) rather
than a bare Intent so the run's token ledger can meter API backends; the
Intent remains the decision payload per the design spec.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from typing import Literal, Protocol

from pydantic import ValidationError

from understudy.types import Intent, IntentKind


class ModelError(Exception):
    """The model produced output that is not a valid Intent. Logged as a
    down-weighted friction signal (model failure, not UI failure)."""


@dataclass(frozen=True)
class Message:
    role: Literal["user", "assistant"]
    content: str


@dataclass(frozen=True)
class DecideResult:
    intent: Intent
    input_tokens: int
    output_tokens: int


class ActionModel(Protocol):
    async def decide(self, system: str, transcript: list[Message]) -> DecideResult: ...


_FENCE = re.compile(r"^```(?:json)?\s*|\s*```$", re.MULTILINE)


def parse_intent(raw: str) -> Intent:
    """Strict JSON → Intent. Anything else is a ModelError — never a guess."""
    cleaned = _FENCE.sub("", raw.strip()).strip()
    try:
        data = json.loads(cleaned)
    except json.JSONDecodeError as exc:
        raise ModelError(f"model output is not JSON: {raw[:200]!r}") from exc
    try:
        return Intent.model_validate(data)
    except ValidationError as exc:
        raise ModelError(f"model JSON is not a valid Intent: {exc}") from exc


class FakeActionModel:
    """Scripted brain for tests and the wiring lane. Zero tokens, zero LLM."""

    def __init__(self, script: list[Intent]):
        self._script = list(script)

    async def decide(self, system: str, transcript: list[Message]) -> DecideResult:
        intent = self._script.pop(0) if self._script else Intent(kind=IntentKind.WAIT)
        return DecideResult(intent=intent, input_tokens=0, output_tokens=0)
