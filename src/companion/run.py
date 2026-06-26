"""The run loop: connect, then react to server pushes for as long as the session
runs. Event-driven (not turn-capped). Exits on a closed transport or a session
'ended' event. Every decision is bounded by the definition's decide timeout, so a
slow or broken brain degrades to YIELD — the companion never stalls the table and
never fabricates an action the persona did not choose."""

from __future__ import annotations

import random

from companion.actuation import actuate
from companion.brain import build_turn_context, decide
from companion.intent import CompanionIntent, IntentKind
from companion.manifest import CompanionDef
from companion.persona import build_system_prompt
from companion.protocol import (
    StateMirror,
    Transport,
    chargen_choice_frame,
    connect_frame,
)
from seat_core.core import StructuredModel

_PROMPT_KINDS = frozenset({"DICE_REQUEST", "CONFRONTATION", "FATE_DEFEND_REQUEST"})


async def run_companion(
    defn: CompanionDef,
    transport: Transport,
    brain: StructuredModel,
    *,
    rng: random.Random | None = None,
) -> None:
    system = build_system_prompt(defn)
    mirror = StateMirror()
    await transport.send(connect_frame(defn))

    while True:
        frame = await transport.recv()
        if frame is None:
            return  # transport closed
        mirror.apply(frame)
        kind = frame.get("type")
        payload = frame.get("payload", {}) or {}

        if kind == "SESSION_EVENT" and payload.get("event") == "ended":
            return

        if kind == "CHARACTER_CREATION" and payload.get("phase") == "scene":
            intent = await decide(
                brain,
                system,
                build_turn_context(mirror, _chargen_situation(payload)),
                defn.decide_timeout_s,
            )
            await transport.send(chargen_choice_frame(_chargen_choice(intent)))
            continue

        if kind in _PROMPT_KINDS:
            intent = await decide(
                brain,
                system,
                build_turn_context(mirror, _prompt_situation(kind, payload)),
                defn.decide_timeout_s,
            )
            out = actuate(intent, mirror, rng=rng)
            if out is not None:
                await transport.send(out)
            continue

        if kind == "TURN_STATUS" and mirror.my_turn():
            intent = await decide(
                brain,
                system,
                build_turn_context(mirror, "It is your turn. What do you do?"),
                defn.decide_timeout_s,
            )
            out = actuate(intent, mirror, rng=rng)
            if out is not None:
                await transport.send(out)
            continue


def _chargen_situation(payload: dict) -> str:
    prompt = payload.get("prompt", "Create your character.")
    choices = payload.get("choices") or []
    lines = [f"{i}: {c.get('label', '')}" for i, c in enumerate(choices)]
    return f"{prompt}\n" + "\n".join(lines) if lines else prompt


def _chargen_choice(intent: CompanionIntent) -> str:
    # The brain answers chargen in character (ACT prose) or yields. We forward the
    # prose verbatim; a YIELD/empty decision maps to "0" (first option) so chargen
    # always completes rather than stalling the table.
    if intent.kind is IntentKind.ACT and intent.text:
        return intent.text
    return "0"


def _prompt_situation(kind: str, payload: dict) -> str:
    if kind == "DICE_REQUEST":
        return f"The game asks you to roll ({payload.get('context', '')}). Roll."
    if kind == "CONFRONTATION":
        beats = [b.get("id") for b in (payload.get("beats") or [])]
        return f"You are in a confrontation. Choose a beat from: {beats}."
    return "An attack is coming at you. Defend."
