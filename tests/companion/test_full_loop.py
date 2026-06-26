"""WIRING (159-5, extended): the companion plays a whole scripted session end to
end — Plan C Task 11.

CLAUDE.md: 'Every Test Suite Needs a Wiring Test.' This drives the REAL
run_companion through a complete session shape — connect -> the FULL chargen FSM
(scene -> continue -> story -> portrait -> confirmation -> complete) -> play a
turn -> a dice request -> session end — with a fake brain and a scripted fake
server, proving the whole pipeline is wired together, not merely unit-correct in
isolation. It is the offline half of the contract-drift tripwire (the online half
is a gated real-server smoke, out of v1 scope).

The chargen leg models the REAL server contract (the GM playtest 2026-06-26 and
the design note docs/superpowers/specs/2026-06-26-companion-chargen-driver-decision.md):
the server keeps ``phase="scene"`` for every scene-stage step and differentiates
the step in ``input_type`` (choice/continue/story/pick_portrait), then emits
``phase="confirmation"`` to commit and ``phase="complete"`` when the PC is built.
A companion that only ever answers ``phase="scene"`` (the pre-fix bug) never
finalises a character. This fixture would catch that regression.
"""

from __future__ import annotations

import random

import pytest

from companion.intent import CompanionIntent, IntentKind
from companion.manifest import CompanionDef
from companion.run import ChargenStepUnsupported, run_companion
from seat_core.core import FakeStructuredModel
from seat_core.persona.axis import Role, SeatAxes


class FakeServer:
    def __init__(self, incoming: list[dict]) -> None:
        self._incoming = list(incoming)
        self.sent: list[dict] = []

    async def send(self, frame: dict) -> None:
        self.sent.append(frame)

    async def recv(self) -> dict | None:
        return self._incoming.pop(0) if self._incoming else None


def _donut() -> CompanionDef:
    return CompanionDef(
        name="Princess Donut",
        species="cat",
        role=Role.PET,
        voice="VAIN.",
        axes=SeatAxes(
            narrative_vs_mechanical=0.4,
            verbosity="medium",
            decisiveness="high",
            reading_tolerance="medium",
        ),
        companion_of="alice@home",
        genre="caverns_and_claudes",
        world="beneath_sunden",
        game_slug="caverns-night-1",  # the human's room slug — NOT the WS endpoint
        session_url="ws://player2.local:8765/ws",
    )


def _chargen(payload: dict) -> dict:
    return {"type": "CHARACTER_CREATION", "payload": payload}


def _by_phase(sent: list[dict], phase: str) -> dict:
    return next(
        f for f in sent if f["type"] == "CHARACTER_CREATION" and f["payload"].get("phase") == phase
    )


async def test_companion_plays_a_full_scripted_session():
    incoming = [
        {"type": "SESSION_EVENT", "payload": {"event": "connected"}, "player_id": "rex-pid"},
        # --- the full chargen FSM, the way the real server drives it ----------
        _chargen(
            {
                "phase": "scene",
                "input_type": "choice",
                "prompt": "Pick your calling.",
                "choices": [{"label": "Warrior"}, {"label": "Expert"}, {"label": "Mage"}],
            }
        ),
        _chargen(
            {
                "phase": "scene",
                "input_type": "continue",
                "prompt": "Standard kit.",
                "choices": [],
                "allows_freeform": False,
            }
        ),
        _chargen(
            {
                "phase": "scene",
                "input_type": "story",
                "prompt": "Who are you?",
                "choices": [],
                "pronouns_required": True,
            }
        ),
        _chargen({"phase": "scene", "input_type": "pick_portrait", "portraits_available": True}),
        _chargen({"phase": "confirmation", "character_preview": {"name": "Princess Donut"}}),
        _chargen({"phase": "complete"}),
        # --- play -------------------------------------------------------------
        {"type": "SESSION_EVENT", "payload": {"event": "ready"}, "player_id": "rex-pid"},
        {"type": "NARRATION", "payload": {"text": "The warren reeks of goblin."}},
        {
            "type": "TURN_STATUS",
            "payload": {"entries": [{"player_id": "rex-pid", "status": "pending"}]},
        },
        {"type": "DICE_REQUEST", "payload": {"roller": "Princess Donut", "die_system": "d20"}},
        {"type": "NARRATION_END", "payload": {"round": 1}},
        {"type": "SESSION_EVENT", "payload": {"event": "ended"}},
    ]
    server = FakeServer(incoming)
    brain = FakeStructuredModel(
        [
            CompanionIntent(kind=IntentKind.ACT, text="Expert, OBVIOUSLY."),  # class scene
            CompanionIntent(kind=IntentKind.ACT, text="A cat of intimidating lineage."),  # story
            CompanionIntent(kind=IntentKind.ACT, text="I sniff and deign to lead."),  # turn
            CompanionIntent(kind=IntentKind.ROLL),  # dice request
        ],
        default=CompanionIntent(kind=IntentKind.YIELD),
    )

    defn = _donut()
    await run_companion(defn, server, brain, rng=random.Random(0))

    types = [f["type"] for f in server.sent]
    # connect first, carrying the bond metadata the server's bond registry reads
    assert types[0] == "SESSION_EVENT"
    assert server.sent[0]["payload"]["event"] == "connect"
    assert server.sent[0]["payload"]["companion_of"] == "alice@home"
    assert server.sent[0]["payload"]["relationship"] == "pet"
    # the connect frame carries the ROOM SLUG (so the companion lands in the
    # human's SessionRoom), NOT the WS endpoint URL (Reviewer 159-5 — the HIGH bug)
    assert server.sent[0]["payload"]["game_slug"] == defn.game_slug
    assert server.sent[0]["payload"]["game_slug"] != defn.session_url

    # --- chargen drove the WHOLE FSM, not just the opening scene -------------
    # 159-7: a select scene resolves to a server-resolvable selector for "Expert"
    # (1-based index or exact label) — never the raw prose.
    scene_resp = next(
        f
        for f in server.sent
        if f["type"] == "CHARACTER_CREATION"
        and f["payload"].get("phase") == "scene"
        and "choice" in f["payload"]
    )
    choice = scene_resp["payload"]["choice"]
    assert choice != "Expert, OBVIOUSLY.", "must not forward raw prose as the choice"
    assert choice == "2" or str(choice).casefold() == "expert", (
        f"chargen choice {choice!r} must be a server-resolvable selector for 'Expert'"
    )
    # display-only scene acknowledged
    _by_phase(server.sent, "continue")
    # identity scene answered with the structured story_confirm fields
    story = _by_phase(server.sent, "story_confirm")
    assert story["payload"].get("pronouns"), "story_confirm must carry pronouns"
    assert story["payload"].get("background"), "story_confirm must carry a background"
    assert "description" in story["payload"], "story_confirm must carry a description"
    # portrait step skipped (no daemon dependency for a bot)
    portrait = _by_phase(server.sent, "portrait_confirm")
    assert portrait["payload"]["selected_portrait_ref"] is None
    # and the character is COMMITTED — the step that was unreachable before
    commit = _by_phase(server.sent, "confirmation")
    assert commit["payload"]["choice"] == "1"

    # --- play leg unchanged --------------------------------------------------
    assert "PLAYER_ACTION" in types
    action = next(f for f in server.sent if f["type"] == "PLAYER_ACTION")
    assert action["payload"]["action"] == "I sniff and deign to lead."
    assert action["player_id"] == "rex-pid"
    assert "DICE_THROW" in types
    throw = next(f for f in server.sent if f["type"] == "DICE_THROW")
    assert len(throw["payload"]["faces"]) == 1 and 1 <= throw["payload"]["faces"][0] <= 20


async def test_unsupported_chargen_step_fails_loud():
    """80%-path boundary (Keith 2026-06-26): ruleset-specific chargen steps
    (stat_arrange / roll_the_bones / fate_*) are NOT silently faked — the
    companion fails loud so an unsupported genre is a visible finding, not a
    garbage submission (SOUL: No Silent Fallbacks; design note §5)."""
    incoming = [
        {"type": "SESSION_EVENT", "payload": {"event": "connected"}, "player_id": "rex-pid"},
        _chargen(
            {"phase": "scene", "input_type": "stat_arrange", "ability_names": ["STR", "DEX", "CON"]}
        ),
    ]
    server = FakeServer(incoming)
    brain = FakeStructuredModel([], default=CompanionIntent(kind=IntentKind.YIELD))

    with pytest.raises(ChargenStepUnsupported):
        await run_companion(_donut(), server, brain, rng=random.Random(0))
