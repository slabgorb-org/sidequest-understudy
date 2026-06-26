"""WIRING (159-5): the companion plays a whole scripted session end to end —
Plan C Task 11.

CLAUDE.md: 'Every Test Suite Needs a Wiring Test.' This drives the REAL
run_companion through a complete session shape — connect -> chargen scene -> play
a turn -> a dice request -> session end — with a fake brain and a scripted fake
server, proving the whole pipeline is wired together, not merely unit-correct in
isolation. It is the offline half of the contract-drift tripwire (the online half
is a gated real-server smoke, out of v1 scope).
"""

from __future__ import annotations

import random

from companion.intent import CompanionIntent, IntentKind
from companion.manifest import CompanionDef
from companion.run import run_companion
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


async def test_companion_plays_a_full_scripted_session():
    incoming = [
        {"type": "SESSION_EVENT", "payload": {"event": "connected"}, "player_id": "rex-pid"},
        {"type": "CHARACTER_CREATION", "payload": {
            "phase": "scene", "prompt": "What is your origin?",
            "choices": [{"label": "Show cat"}, {"label": "Alley cat"}]}},
        {"type": "SESSION_EVENT", "payload": {"event": "ready"}, "player_id": "rex-pid"},
        {"type": "NARRATION", "payload": {"text": "The warren reeks of goblin."}},
        {"type": "TURN_STATUS", "payload": {"entries": [
            {"player_id": "rex-pid", "status": "pending"}]}},
        {"type": "DICE_REQUEST", "payload": {"roller": "Princess Donut", "die_system": "d20"}},
        {"type": "NARRATION_END", "payload": {"round": 1}},
        {"type": "SESSION_EVENT", "payload": {"event": "ended"}},
    ]
    server = FakeServer(incoming)
    brain = FakeStructuredModel(
        [
            CompanionIntent(kind=IntentKind.ACT, text="Show cat, OBVIOUSLY."),  # chargen
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
    # chargen answered (the brain's actual choice, not a fallback), then a turn,
    # then the dice request answered
    assert "CHARACTER_CREATION" in types
    cc = next(f for f in server.sent if f["type"] == "CHARACTER_CREATION")
    assert cc["payload"]["choice"] == "Show cat, OBVIOUSLY."
    assert "PLAYER_ACTION" in types
    action = next(f for f in server.sent if f["type"] == "PLAYER_ACTION")
    assert action["payload"]["action"] == "I sniff and deign to lead."
    assert action["player_id"] == "rex-pid"
    assert "DICE_THROW" in types
    throw = next(f for f in server.sent if f["type"] == "DICE_THROW")
    assert len(throw["payload"]["faces"]) == 1 and 1 <= throw["payload"]["faces"][0] <= 20
