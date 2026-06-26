"""Per-turn decision. Reuses seat-core's model backends bound to CompanionIntent.
Every failure mode degrades to YIELD — the companion never stalls the table and
never fabricates an action the persona did not choose."""

from __future__ import annotations

import asyncio

from companion.intent import CompanionIntent, YIELD_INTENT
from companion.protocol import StateMirror
from seat_core.core import Message, StructuredModel
from seat_core.llm.factory import make_model


def make_brain(model_spec: str) -> StructuredModel:
    return make_model(model_spec, CompanionIntent, default=YIELD_INTENT)


def build_turn_context(mirror: StateMirror, situation: str) -> list[Message]:
    parts: list[str] = []
    if mirror.last_narration:
        parts.append(f"The scene so far:\n{mirror.last_narration}")
    parts.append(situation)
    return [Message(role="user", content="\n\n".join(parts))]


async def decide(
    brain: StructuredModel, system: str, context: list[Message], timeout_s: float
) -> CompanionIntent:
    try:
        result = await asyncio.wait_for(brain.decide(system, context), timeout=timeout_s)
    except Exception:  # noqa: BLE001 — any failure degrades to a safe YIELD (never stall, never fabricate)
        return YIELD_INTENT
    value = result.value
    return value if isinstance(value, CompanionIntent) else YIELD_INTENT
