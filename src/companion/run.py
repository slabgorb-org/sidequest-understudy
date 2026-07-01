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
    chargen_confirmation_frame,
    chargen_continue_frame,
    chargen_portrait_skip_frame,
    chargen_story_frame,
    connect_frame,
)
from seat_core.core import StructuredModel

logger = logging.getLogger(__name__)

_PROMPT_KINDS = frozenset({"DICE_REQUEST", "CONFRONTATION", "FATE_DEFEND_REQUEST"})

# Scene steps whose answer is a creative pick the brain must make. ``None`` covers
# plain scenes that omit input_type. Steps not handled explicitly in
# ``_chargen_response`` (stat_arrange / roll_the_bones / fate_*) fail loud — the
# v1 (80%) boundary.
_CHARGEN_BRAIN_INPUTS = frozenset({None, "choice", "stock", "name", "text"})


class ChargenStepUnsupported(RuntimeError):
    """A chargen step the companion does not drive yet — the ruleset-specific
    stat_arrange / roll_the_bones / fate_* steps (the 80% boundary, Keith
    2026-06-26). Raised loud so an unsupported genre is a visible finding, never a
    garbage submission (SOUL: No Silent Fallbacks)."""


class ConnectRejected(RuntimeError):
    """The server sent an ``ERROR`` frame — most often a rejected connect (Story
    160-4: a SOLO-slot conflict, ``{"type": "ERROR", "payload": {"message": ...}}``).
    Raised loud carrying the server's message so the run surfaces the rejection
    and exits non-zero, instead of looping back to ``recv()`` and hanging forever
    on a socket the server is holding open (SOUL: No Silent Fallbacks)."""


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

        if kind == "ERROR":
            # No Silent Fallbacks: an ERROR frame (e.g. a rejected connect) matches
            # no play branch. Surface it loudly and stop — never loop back to
            # recv() on a socket the server is holding open (the 160-4 hang).
            message = payload.get("message", "")
            logger.error("companion aborted — server sent ERROR: %s", message)
            raise ConnectRejected(f"server rejected the companion: {message}")

        if kind == "CHARACTER_CREATION":
            out = await _chargen_response(brain, system, mirror, defn, payload)
            if out is not None:
                await transport.send(out)
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


async def _chargen_response(
    brain: StructuredModel,
    system: str,
    mirror: StateMirror,
    defn: CompanionDef,
    payload: dict,
) -> dict | None:
    """Drive one chargen frame to its server-resolvable response.

    The real server keeps ``phase="scene"`` for every scene-stage step and puts
    the actual step kind in ``input_type`` (choice/continue/story/pick_portrait/
    stat_arrange/roll_the_bones/fate_*); it then emits ``phase="confirmation"`` to
    commit and ``phase="complete"`` once the PC is built. Answering only
    ``phase="scene"`` (the pre-fix bug) never finalises a character. We dispatch
    on phase, then input_type. Returns the frame to send, ``None`` when the step
    needs no reply (chargen complete). Raises ``ChargenStepUnsupported`` outside
    the v1 (80%) path — the brain is consulted only for the creative steps."""
    phase = payload.get("phase")
    if phase == "complete":
        return None  # PC built — the play loop takes over
    if phase == "confirmation":
        return chargen_confirmation_frame()
    if phase != "scene":
        raise ChargenStepUnsupported(f"unhandled chargen phase {phase!r}")

    input_type = payload.get("input_type")
    if input_type == "continue":
        return chargen_continue_frame()  # display-only ack — no brain
    if input_type == "pick_portrait":
        return chargen_portrait_skip_frame()  # a bot has no portrait to pick
    if input_type == "story":
        intent = await decide(
            brain,
            system,
            build_turn_context(mirror, _chargen_situation(payload)),
            defn.decide_timeout_s,
        )
        # The cat describes herself; pronouns default neutral (the def carries no
        # pronoun field — the voice, not the sheet, is load-bearing in play).
        background = (
            intent.text if (intent.kind is IntentKind.ACT and intent.text) else f"A {defn.species}."
        )
        return chargen_story_frame(
            pronouns="they/them", background=background, description=f"A {defn.species}."
        )
    if input_type in _CHARGEN_BRAIN_INPUTS:
        intent = await decide(
            brain,
            system,
            build_turn_context(mirror, _chargen_situation(payload)),
            defn.decide_timeout_s,
        )
        return chargen_choice_frame(_chargen_choice(intent, payload))

    raise ChargenStepUnsupported(
        f"chargen input_type {input_type!r} is not in the v1 path "
        "(stat_arrange / roll_the_bones / fate_* not driven yet) — failing loud "
        "instead of faking a pick"
    )


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
