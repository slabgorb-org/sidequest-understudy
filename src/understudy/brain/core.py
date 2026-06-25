"""Brain seam: understudy's binding of the generic seat_core decision protocol.

The protocol (`StructuredModel`), the fence-stripping strict parser, the
`DecideResult`/`Message`/`ModelError` types, and the scripted fake all live in
`seat_core.core`, generic over a pydantic output model. This module is the thin
understudy-facing binding: it specialises that machinery to understudy's `Intent`
payload (`parse_intent`, `FakeActionModel`) and re-exports the shared names under
understudy's historical spelling (`StructuredModel` → `ActionModel`) so existing
imports keep working unchanged.
"""

from __future__ import annotations

from seat_core.core import (
    DecideResult,
    FakeStructuredModel,
    Message,
    ModelError,
    StructuredModel as ActionModel,
    parse_structured,
)

from understudy.types import Intent, IntentKind

__all__ = [
    "ActionModel",
    "DecideResult",
    "FakeActionModel",
    "Message",
    "ModelError",
    "parse_intent",
    "parse_structured",
]


def parse_intent(raw: str) -> Intent:
    """Strict JSON → Intent. Anything else is a ModelError — never a guess."""
    return parse_structured(raw, Intent)


class FakeActionModel(FakeStructuredModel):
    """Scripted brain for tests and the wiring lane. Zero tokens, zero LLM.
    Plays `script` in order, then returns a WAIT intent forever."""

    def __init__(self, script: list[Intent]):
        super().__init__(script, Intent(kind=IntentKind.WAIT))
