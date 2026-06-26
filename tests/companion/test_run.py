"""RED (159-5): the companion run loop — Plan C Task 9.

run_companion is the event-driven spine: connect, then react to server pushes for
as long as the session runs. Two invariants a real game depends on:

  * It NEVER stalls the table — a slow or broken brain degrades to YIELD through
    the bounded `companion.brain.decide`, never a hang and never a fabrication.
  * It exits cleanly on a closed transport OR a SESSION_EVENT 'ended', and never
    plays a turn that arrives after the session has ended.

These tests drive the real loop with a scripted FakeTransport (captures what the
companion sends) and a FakeStructuredModel brain (scripts what it decides).
"""

from __future__ import annotations

import asyncio
import inspect
import random

from companion.intent import CompanionIntent, IntentKind
from companion.manifest import CompanionDef
from companion.run import run_companion
from seat_core.core import FakeStructuredModel
from seat_core.persona.axis import Role, SeatAxes


class FakeTransport:
    """Scripted server: yields `incoming` frames in order, then None (closed).
    Captures everything the companion sends in `sent`."""

    def __init__(self, incoming: list[dict]) -> None:
        self._incoming = list(incoming)
        self.sent: list[dict] = []

    async def send(self, frame: dict) -> None:
        self.sent.append(frame)

    async def recv(self) -> dict | None:
        return self._incoming.pop(0) if self._incoming else None


def _defn(decide_timeout_s: float = 30.0) -> CompanionDef:
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
        game_slug="game-1",  # the human's room slug — distinct from the WS endpoint
        session_url="ws://x/ws",
        decide_timeout_s=decide_timeout_s,
    )


def _brain(*intents: CompanionIntent) -> FakeStructuredModel:
    return FakeStructuredModel(list(intents), default=CompanionIntent(kind=IntentKind.YIELD))


_CONNECTED = {"type": "SESSION_EVENT", "payload": {"event": "connected"}, "player_id": "rex-pid"}
_ENDED = {"type": "SESSION_EVENT", "payload": {"event": "ended"}}
_MY_TURN = {"type": "TURN_STATUS", "payload": {"entries": [
    {"player_id": "rex-pid", "status": "pending"}]}}


async def test_connect_frame_sent_first():
    transport = FakeTransport([])
    await run_companion(_defn(), transport, _brain(), rng=random.Random(0))
    assert transport.sent, "companion must announce itself before anything else"
    first = transport.sent[0]
    assert first["type"] == "SESSION_EVENT"
    assert first["payload"]["event"] == "connect"
    assert first["payload"]["companion_of"] == "alice@home"
    assert first["payload"]["relationship"] == "pet"


async def test_plays_turn_then_throws_then_exits():
    incoming = [
        _CONNECTED,
        _MY_TURN,
        {"type": "DICE_REQUEST", "payload": {"roller": "Donut", "die_system": "d20"}},
        _ENDED,
    ]
    transport = FakeTransport(incoming)
    brain = _brain(
        CompanionIntent(kind=IntentKind.ACT, text="I deign to scout ahead."),
        CompanionIntent(kind=IntentKind.ROLL),
    )
    await run_companion(_defn(), transport, brain, rng=random.Random(0))
    sent_types = [f["type"] for f in transport.sent]
    assert "PLAYER_ACTION" in sent_types
    action = next(f for f in transport.sent if f["type"] == "PLAYER_ACTION")
    assert action["payload"]["action"] == "I deign to scout ahead."
    assert action["player_id"] == "rex-pid"
    assert "DICE_THROW" in sent_types
    # the d20 throw carries exactly one fair face in range (Reviewer 159-5)
    throw = next(f for f in transport.sent if f["type"] == "DICE_THROW")
    assert len(throw["payload"]["faces"]) == 1 and 1 <= throw["payload"]["faces"][0] <= 20


async def test_exits_cleanly_on_closed_transport():
    # recv() yields None after the one frame; the loop must return, not hang.
    transport = FakeTransport([_CONNECTED])
    await asyncio.wait_for(run_companion(_defn(), transport, _brain()), timeout=2.0)
    # it ran (connected) and then returned on the closed transport
    assert transport.sent[0]["payload"]["event"] == "connect"


async def test_exits_on_session_ended_without_consuming_more():
    # A pending turn AFTER 'ended' must never be played — the loop stops at ended.
    transport = FakeTransport([_CONNECTED, _ENDED, _MY_TURN])
    brain = _brain(CompanionIntent(kind=IntentKind.ACT, text="I should not act."))
    await run_companion(_defn(), transport, brain, rng=random.Random(0))
    assert "PLAYER_ACTION" not in [f["type"] for f in transport.sent]


async def test_chargen_scene_answered_in_persona():
    incoming = [
        _CONNECTED,
        {"type": "CHARACTER_CREATION", "payload": {
            "phase": "scene", "prompt": "Origin?", "choices": [{"label": "Show cat"}]}},
        _ENDED,
    ]
    transport = FakeTransport(incoming)
    brain = _brain(CompanionIntent(kind=IntentKind.ACT, text="Show cat, OBVIOUSLY."))
    await run_companion(_defn(), transport, brain, rng=random.Random(0))
    cc = next((f for f in transport.sent if f["type"] == "CHARACTER_CREATION"), None)
    assert cc is not None, "companion must answer the chargen scene"
    assert cc["payload"]["choice"] == "Show cat, OBVIOUSLY."


async def test_chargen_falls_back_to_first_option_when_brain_yields():
    # The 'never stall chargen' degradation: when the brain yields (or returns any
    # non-ACT decision), the choice maps to "0" (first option) so chargen always
    # completes rather than hanging the table. (Reviewer 159-5 — was untested.)
    incoming = [
        _CONNECTED,
        {"type": "CHARACTER_CREATION", "payload": {
            "phase": "scene", "prompt": "Origin?", "choices": [{"label": "Show cat"}]}},
        _ENDED,
    ]
    transport = FakeTransport(incoming)
    await run_companion(_defn(), transport, _brain(), rng=random.Random(0))  # default = YIELD
    cc = next((f for f in transport.sent if f["type"] == "CHARACTER_CREATION"), None)
    assert cc is not None, "companion must still answer chargen when it yields"
    assert cc["payload"]["choice"] == "0"


async def test_not_my_turn_sends_no_action():
    incoming = [
        _CONNECTED,
        {"type": "TURN_STATUS", "payload": {"entries": [
            {"player_id": "alice-pid", "status": "pending"}]}},
        _ENDED,
    ]
    transport = FakeTransport(incoming)
    brain = _brain(CompanionIntent(kind=IntentKind.ACT, text="not mine"))
    await run_companion(_defn(), transport, brain, rng=random.Random(0))
    assert "PLAYER_ACTION" not in [f["type"] for f in transport.sent]


async def test_confrontation_prompt_answered_with_beat():
    incoming = [
        _CONNECTED,
        {"type": "CONFRONTATION", "payload": {"die_system": "2d6", "beats": [{"id": "riposte"}]}},
        _ENDED,
    ]
    transport = FakeTransport(incoming)
    brain = _brain(CompanionIntent(kind=IntentKind.BEAT, beat_id="riposte"))
    await run_companion(_defn(), transport, brain, rng=random.Random(2))
    throw = next((f for f in transport.sent if f["type"] == "DICE_THROW"), None)
    assert throw is not None, "a confrontation prompt must produce a throw"
    assert throw["payload"]["beat_id"] == "riposte"
    assert len(throw["payload"]["faces"]) == 2


async def test_fate_defend_prompt_answered_with_fate_throw():
    incoming = [
        _CONNECTED,
        {"type": "FATE_DEFEND_REQUEST", "payload": {}},
        _ENDED,
    ]
    transport = FakeTransport(incoming)
    brain = _brain(CompanionIntent(kind=IntentKind.DEFEND))
    await run_companion(_defn(), transport, brain, rng=random.Random(3))
    throw = next((f for f in transport.sent if f["type"] == "FATE_THROW"), None)
    assert throw is not None, "a fate-defend prompt must produce a fate throw"
    assert throw["payload"]["action"] == "defend"
    assert len(throw["payload"]["faces"]) == 4


async def test_slow_brain_yields_and_does_not_stall():
    # lang-review #9 (async) + 'never stall the table': a brain slower than the
    # decide timeout must degrade to a YIELD frame — fast, via the bounded decide.
    class Slow:
        async def decide(self, system, transcript):
            await asyncio.sleep(10)

    transport = FakeTransport([_CONNECTED, _MY_TURN, _ENDED])
    await asyncio.wait_for(
        run_companion(_defn(decide_timeout_s=0.05), transport, Slow(), rng=random.Random(0)),
        timeout=3.0,
    )
    assert "YIELD" in [f["type"] for f in transport.sent]


def test_run_companion_has_typed_signature():
    # lang-review #3: the public boundary is annotated (params + return).
    sig = inspect.signature(run_companion)
    assert sig.return_annotation is not inspect.Signature.empty
    for name in ("defn", "transport", "brain"):
        assert sig.parameters[name].annotation is not inspect.Signature.empty
