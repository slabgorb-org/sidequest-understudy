"""RED (159-7): the companion's chargen choice must satisfy the REAL server's
select-scene contract — a 1-based index or an exact label that the server resolves
to the option the brain picked — never a prose paragraph.

Found by the first real-server companion playtest (2026-06-26): the brain returns
flavored prose ("Expert, obviously!"); ``run.py::_chargen_choice`` forwarded it
verbatim as the scene ``choice``; and the server's ``_chargen_scene``
(sidequest-server/sidequest/server/websocket_handlers/chargen_mixin.py) resolves a
choice by ``int()`` as a 1-based index, else an EXACT case-insensitive label match,
else ``apply_freeform()``. A prose paragraph matches neither, so on a SELECT scene
it falls through to freeform and chargen never advances — blocking the entire
companion lifecycle (play, dice, bond/pet-widening).

``_server_resolves`` below is a faithful reproduction of that server rule and is
the offline contract oracle — the contract-drift tripwire the spec called for. If
the server's resolution changes, this oracle must change with it; the scripted
full-loop fixture missed this exact bug precisely because it had no such oracle.
Keep in sync with ``chargen_mixin.py::_chargen_scene``.
"""

from __future__ import annotations

import logging
import random

from companion.intent import CompanionIntent, IntentKind
from companion.manifest import CompanionDef
from companion.run import run_companion
from seat_core.core import FakeStructuredModel
from seat_core.persona.axis import Role, SeatAxes


class FakeTransport:
    """Scripted server: yields ``incoming`` in order then None; captures ``sent``."""

    def __init__(self, incoming: list[dict]) -> None:
        self._incoming = list(incoming)
        self.sent: list[dict] = []

    async def send(self, frame: dict) -> None:
        self.sent.append(frame)

    async def recv(self) -> dict | None:
        return self._incoming.pop(0) if self._incoming else None


def _defn() -> CompanionDef:
    return CompanionDef(
        name="Donut",
        species="cat",
        role=Role.PET,
        voice="v",
        axes=SeatAxes(
            narrative_vs_mechanical=0.4,
            verbosity="medium",
            decisiveness="high",
            reading_tolerance="medium",
        ),
        companion_of="alice@home",
        genre="g",
        world="w",
        game_slug="game-1",
        session_url="ws://x/ws",
    )


def _brain(*intents: CompanionIntent) -> FakeStructuredModel:
    return FakeStructuredModel(list(intents), default=CompanionIntent(kind=IntentKind.YIELD))


_CONNECTED = {"type": "SESSION_EVENT", "payload": {"event": "connected"}, "player_id": "rex-pid"}
_ENDED = {"type": "SESSION_EVENT", "payload": {"event": "ended"}}
_CLASSES = [{"label": "Warrior"}, {"label": "Expert"}, {"label": "Mage"}]


def _select_scene(choices: list[dict]) -> dict:
    return {
        "type": "CHARACTER_CREATION",
        "payload": {
            "phase": "scene",
            "prompt": "Pick the one you'll die as.",
            "choices": choices,
            "input_type": "select",
            "allows_freeform": False,
        },
    }


def _freeform_scene() -> dict:
    return {
        "type": "CHARACTER_CREATION",
        "payload": {
            "phase": "scene",
            "prompt": "What is your name?",
            "choices": [],
            "input_type": "text",
            "allows_freeform": True,
        },
    }


def _server_resolves(choice_str: object, choices: list[dict]) -> int | None:
    """Faithful reproduction of ``chargen_mixin.py::_chargen_scene`` select-scene
    resolution. Returns the 0-based index the server would ``apply_choice``, or
    None — meaning the server falls through to ``apply_freeform`` (the stall on a
    select scene). Contract oracle; keep in sync with the server."""
    try:
        n = int(choice_str)  # type: ignore[arg-type]
        return max(0, n - 1)
    except (ValueError, TypeError):
        for i, c in enumerate(choices):
            if c["label"].casefold() == str(choice_str).casefold():
                return i
        return None


def _sent_chargen_choice(sent: list[dict]) -> object:
    cc = next((f for f in sent if f["type"] == "CHARACTER_CREATION"), None)
    assert cc is not None, "companion must answer the chargen scene"
    return cc["payload"]["choice"]


async def _run_select(brain_text: str, choices: list[dict] = _CLASSES) -> object:
    transport = FakeTransport([_CONNECTED, _select_scene(choices), _ENDED])
    brain = _brain(CompanionIntent(kind=IntentKind.ACT, text=brain_text))
    await run_companion(_defn(), transport, brain, rng=random.Random(0))
    return _sent_chargen_choice(transport.sent)


# --- AC1 / AC4: select-scene choice resolves to the picked option, never prose ---


async def test_select_choice_resolves_to_picked_middle_option():
    # The exact live failure: flavored prose naming the 2nd option.
    choice = await _run_select("Expert, obviously! I am precise.")
    assert _server_resolves(choice, _CLASSES) == 1, (
        f"choice {choice!r} must resolve to Expert (index 1) on the server"
    )


async def test_select_choice_resolves_to_first_option():
    choice = await _run_select("Warrior — I'll take the hits.")
    assert _server_resolves(choice, _CLASSES) == 0


async def test_select_choice_resolves_to_last_option_no_off_by_one():
    # Catches the _chargen_situation 0-based vs server 1-based off-by-one: the last
    # option must land on index 2, not 1 or out of range.
    choice = await _run_select("Mage, naturally.")
    assert _server_resolves(choice, _CLASSES) == 2


async def test_select_choice_is_server_resolvable_in_range_not_prose():
    choice = await _run_select("Expert, obviously! I am precise.")
    idx = _server_resolves(choice, _CLASSES)
    assert idx is not None and 0 <= idx < len(_CLASSES), (
        f"select choice {choice!r} must be a server-resolvable in-range selector, "
        "never a prose paragraph"
    )


# --- AC3: freeform scenes still send the brain's prose verbatim ------------------


async def test_freeform_scene_sends_prose_answer():
    transport = FakeTransport([_CONNECTED, _freeform_scene(), _ENDED])
    brain = _brain(CompanionIntent(kind=IntentKind.ACT, text="Princess Donut the Magnificent"))
    await run_companion(_defn(), transport, brain, rng=random.Random(0))
    assert _sent_chargen_choice(transport.sent) == "Princess Donut the Magnificent", (
        "a freeform/allows_freeform scene must still send the brain's prose as the answer"
    )


# --- AC2 + lang-review #4: an unmappable pick fails loud, never silent-stalls -----


async def test_unmappable_select_pick_does_not_stall_and_logs(caplog):
    with caplog.at_level(logging.WARNING):
        choice = await _run_select("I refuse to be labelled by your ledger.")
    idx = _server_resolves(choice, _CLASSES)
    assert idx is not None and 0 <= idx < len(_CLASSES), (
        "an unmappable chargen pick must still send a server-resolvable choice "
        "(never forward unresolvable prose that stalls the table)"
    )
    assert any(r.levelno >= logging.WARNING for r in caplog.records), (
        "an unmappable chargen pick must log loudly (No Silent Fallbacks)"
    )


# --- The 'never stall chargen' YIELD fallback stays server-resolvable ------------


async def test_yield_fallback_choice_resolves_to_first_option():
    transport = FakeTransport([_CONNECTED, _select_scene(_CLASSES), _ENDED])
    await run_companion(_defn(), transport, _brain(), rng=random.Random(0))  # default = YIELD
    choice = _sent_chargen_choice(transport.sent)
    assert _server_resolves(choice, _CLASSES) == 0, (
        f"the YIELD fallback choice {choice!r} must resolve to the first option"
    )
