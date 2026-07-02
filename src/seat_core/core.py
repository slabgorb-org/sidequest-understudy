"""Brain seam: the structured-decision protocol every backend implements.

Backends are generic over a pydantic output model bound at construction, so the
same code serves understudy's Intent and the companion's CompanionIntent. The
protocol returns DecideResult (value + token usage) so a run's token ledger can
meter API backends.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from typing import Literal, Protocol

from pydantic import BaseModel, ValidationError


class ModelError(Exception):
    """The model produced output that is not a valid instance of the target
    schema. Callers log this as a model failure — never a guess."""


@dataclass(frozen=True)
class Message:
    role: Literal["user", "assistant"]
    content: str


@dataclass(frozen=True)
class DecideResult:
    value: BaseModel
    input_tokens: int
    output_tokens: int
    cache_tokens: int = 0
    model: str | None = None
    cost_usd: float = 0.0


class StructuredModel(Protocol):
    async def decide(self, system: str, transcript: list[Message]) -> DecideResult: ...


_FENCE = re.compile(r"^```(?:json)?\s*|\s*```$", re.MULTILINE)


def parse_structured(raw: str, model: type[BaseModel]) -> BaseModel:
    """Strict JSON → validated model instance. Anything else is a ModelError."""
    cleaned = _FENCE.sub("", raw.strip()).strip()
    try:
        data = json.loads(cleaned)
    except json.JSONDecodeError as exc:
        raise ModelError(f"model output is not JSON: {raw[:200]!r}") from exc
    try:
        return model.model_validate(data)
    except ValidationError as exc:
        raise ModelError(f"model JSON is not a valid {model.__name__}: {exc}") from exc


class FakeStructuredModel:
    """Scripted brain for tests and wiring lanes. Zero tokens, zero LLM.
    Plays `script` in order, then returns `default` forever."""

    def __init__(self, script: list[BaseModel], default: BaseModel):
        self._script = list(script)
        self._default = default

    async def decide(self, system: str, transcript: list[Message]) -> DecideResult:
        value = self._script.pop(0) if self._script else self._default
        return DecideResult(value=value, input_tokens=0, output_tokens=0)
