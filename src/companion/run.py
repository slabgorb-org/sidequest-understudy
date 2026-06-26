"""The run loop: connect, then react to server pushes for as long as the session
runs. Event-driven (not turn-capped). Exits on a closed transport or a session
'ended' event. Every decision is bounded by the definition's decide timeout, so a
slow or broken brain degrades to YIELD — the companion never stalls the table and
never fabricates an action the persona did not choose."""

from __future__ import annotations

import logging
import random
import re

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

logger = logging.getLogger(__name__)

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
            await transport.send(chargen_choice_frame(_chargen_choice(intent, payload)))
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
    # 1-based, matching the server's choice resolution (chargen_mixin.py::
    # _chargen_scene resolves an index as max(0, n - 1)). Showing the brain the
    # same numbering the server expects keeps a bare-index reply off-by-one-free.
    lines = [f"{i + 1}: {c.get('label', '')}" for i, c in enumerate(choices)]
    return f"{prompt}\n" + "\n".join(lines) if lines else prompt


def _chargen_choice(intent: CompanionIntent, payload: dict) -> str:
    """Map the brain's decision to a choice string the SERVER can resolve.

    The server (sidequest-server .../chargen_mixin.py::_chargen_scene) resolves a
    select-scene choice as a 1-based index, else a case-insensitive exact label
    match, else ``apply_freeform``. Forwarding the brain's ACT prose verbatim
    therefore stalls a select scene (prose matches neither index nor exact
    label) — the 159-7 bug.

    Select scene → map the pick to a 1-based index string. Freeform scene → the
    prose IS the answer. On a select scene, a non-ACT/YIELD pick takes the first
    option, and an unmappable ACT pick logs loudly and falls back to the first
    option (never stall, never silently send unresolvable prose). On a freeform
    scene, a non-ACT/YIELD pick logs and sends a "." placeholder.
    """
    choices = payload.get("choices") or []
    allows_freeform = bool(payload.get("allows_freeform"))
    text = intent.text if (intent.kind is IntentKind.ACT and intent.text) else None

    # Pure free-text scene (name/background): no fixed options — the prose answers.
    if not choices:
        if text is not None:
            return text
        logger.warning(
            "chargen: free-text scene but the brain yielded with no text — "
            "sending a placeholder so the table does not stall"
        )
        return "."

    # Select scene: resolve the pick to a 1-based index the server accepts.
    if text is not None:
        idx = _match_choice(text, choices)
        if idx is not None:
            return str(idx + 1)
        if allows_freeform:
            return text  # a select+write-in scene accepts free text as the answer
        logger.warning(
            "chargen: unmappable pick %r against choices %r — defaulting to the "
            "first option (never stall the table)",
            text,
            [c.get("label", "") for c in choices],
        )
        return "1"

    # YIELD / non-ACT on a select scene: take the first option, never stall.
    return "1"


def _match_choice(text: str, choices: list[dict]) -> int | None:
    """Deterministically map the brain's prose to a 0-based choice index, or None
    when it matches no option or is ambiguous (the caller fails loud). Order:
    case-insensitive exact label, then a unique case-insensitive label substring,
    then a leading 1-based index token. No fuzzy scoring — ambiguity returns None."""
    t = text.strip()
    tl = t.casefold()
    labels = [str(c.get("label", "")).strip() for c in choices]

    # 1) exact label (case-insensitive)
    for i, label in enumerate(labels):
        if label and label.casefold() == tl:
            return i
    # 2) unique label appearing verbatim inside the prose ("Expert, obviously!")
    hits = [i for i, label in enumerate(labels) if label and label.casefold() in tl]
    if len(hits) == 1:
        return hits[0]
    # 3) leading 1-based index token ("2", "2.", "2) because…")
    m = re.match(r"(\d+)", t)
    if m:
        n = int(m.group(1))
        if 1 <= n <= len(choices):
            return n - 1
    return None


def _prompt_situation(kind: str, payload: dict) -> str:
    if kind == "DICE_REQUEST":
        return f"The game asks you to roll ({payload.get('context', '')}). Roll."
    if kind == "CONFRONTATION":
        beats = [b.get("id") for b in (payload.get("beats") or [])]
        return f"You are in a confrontation. Choose a beat from: {beats}."
    return "An attack is coming at you. Defend."
