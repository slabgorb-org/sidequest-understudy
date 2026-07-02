"""Per-turn decision. Reuses seat-core's model backends bound to CompanionIntent.
Every failure mode degrades to YIELD — the companion never stalls the table and
never fabricates an action the persona did not choose.

When a ``CompanionDef`` is supplied, every decision self-reports a
``companion_brain_decide`` watcher event (161-2): the GM panel's lie-detector for
the companion seat — model, tokens, cost, timing, and whether the brain yielded,
degraded, or timed out."""

from __future__ import annotations

import asyncio
import logging
import time

from companion.intent import CompanionIntent, IntentKind, YIELD_INTENT
from companion.manifest import CompanionDef
from companion.protocol import StateMirror
from companion.telemetry import emit_watcher_event
from seat_core.core import DecideResult, Message, StructuredModel
from seat_core.llm.factory import make_model

logger = logging.getLogger(__name__)


def make_brain(model_spec: str) -> StructuredModel:
    return make_model(model_spec, CompanionIntent, default=YIELD_INTENT)


def build_turn_context(mirror: StateMirror, situation: str) -> list[Message]:
    parts: list[str] = []
    if mirror.last_narration:
        parts.append(f"The scene so far:\n{mirror.last_narration}")
    parts.append(situation)
    return [Message(role="user", content="\n\n".join(parts))]


async def decide(
    brain: StructuredModel,
    system: str,
    context: list[Message],
    timeout_s: float,
    *,
    defn: CompanionDef | None = None,
) -> CompanionIntent:
    start = time.monotonic()
    degraded = False
    timed_out = False
    result: DecideResult | None = None
    try:
        result = await asyncio.wait_for(brain.decide(system, context), timeout=timeout_s)
    except asyncio.TimeoutError:
        # A brain slower than the decide timeout — still a finding, never a stall.
        degraded = True
        timed_out = True
    except Exception:  # noqa: BLE001 — any failure degrades to a safe YIELD (never stall, never fabricate)
        degraded = True
    duration_ms = (time.monotonic() - start) * 1000.0

    value = result.value if result is not None else None
    if isinstance(value, CompanionIntent):
        intent = value
    else:
        # A valid call whose value is not a usable intent is a model failure — the
        # decision degrades (silence would hide it from the lie-detector).
        if result is not None:
            degraded = True
        intent = YIELD_INTENT

    if defn is not None:
        await _emit_decision(
            defn, intent, result, duration_ms, degraded=degraded, timed_out=timed_out
        )
    return intent


async def _emit_decision(
    defn: CompanionDef,
    intent: CompanionIntent,
    result: DecideResult | None,
    duration_ms: float,
    *,
    degraded: bool,
    timed_out: bool,
) -> None:
    """Self-report one companion decision to the server's watcher hub.

    Offloaded to a thread so the bridge's sync 2s POST never blocks the companion's
    event loop, and fully guarded — a telemetry failure must never break the move.
    """
    fields = {
        "seat": defn.name,
        "role": defn.role.value,
        "species": defn.species,
        "owner": defn.companion_of,
        "outcome": "yield" if intent.kind is IntentKind.YIELD else "act",
        "intent_kind": intent.kind.value,
        "degraded": degraded,
        "timed_out": timed_out,
        "backend": defn.model.split("/", 1)[0],
        "model": result.model if result is not None else None,
        "duration_ms": duration_ms,
        "tokens": (result.input_tokens + result.output_tokens) if result is not None else 0,
        "cost_usd": result.cost_usd if result is not None else 0.0,
    }
    try:
        await asyncio.to_thread(
            emit_watcher_event,
            "companion_brain_decide",
            fields,
            component="companion_brain",
            session_slug=defn.game_slug,
            severity="warning" if degraded else "info",
        )
    except Exception:  # noqa: BLE001 — telemetry must NEVER break the companion's move
        logger.warning("companion telemetry emit failed for seat=%s", defn.name, exc_info=True)
