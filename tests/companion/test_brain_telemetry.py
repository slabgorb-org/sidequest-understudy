"""RED (161-2, part b + AC #2/#3/#5/#6): the companion run loop emits telemetry.

These drive the REAL spine (``run_companion``) with a scripted FakeTransport and a
FakeStructuredModel brain — the same harness as ``test_run.py`` — and assert on the
watcher bridge's network boundary (``companion.telemetry._post``). This is a
behavior/OTEL assertion, NOT a source-text grep (project rule: No Source-Text
Wiring Tests): drive a real decision, prove a real ``companion_brain_decide`` event
goes out carrying the right session/seat/role.

The bridge is patched at ``companion.telemetry._post`` so the assertions hold no
matter which module (run.py or brain.py) ultimately invokes the emit — only that a
companion decision, end to end, produces the POST.

Covers:
  * AC #6 (wiring) — a fake-brain decision emits companion_brain_decide with the
    correct session_slug + seat + role.
  * AC #2 (breadth) — the event carries the full field set.
  * AC #3 (degraded) — a timed-out decision still emits, degraded + severity=warning.
  * AC #5 (non-fatal) — an emit failure logs WARNING and never breaks the turn.
"""

from __future__ import annotations

import asyncio
import logging
import random
import urllib.error
from unittest.mock import patch

from companion.intent import CompanionIntent, IntentKind
from companion.manifest import CompanionDef
from companion.run import run_companion
from seat_core.core import FakeStructuredModel
from seat_core.persona.axis import Role, SeatAxes


class FakeTransport:
    """Scripted server: yields ``incoming`` frames in order, then None (closed).
    Captures everything the companion sends in ``sent`` (mirrors test_run.py)."""

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
        game_slug="game-1",  # the human's room slug — the telemetry session_slug
        session_url="ws://x/ws",
        decide_timeout_s=decide_timeout_s,
    )


def _brain(*intents: CompanionIntent) -> FakeStructuredModel:
    return FakeStructuredModel(list(intents), default=CompanionIntent(kind=IntentKind.YIELD))


_CONNECTED = {"type": "SESSION_EVENT", "payload": {"event": "connected"}, "player_id": "rex-pid"}
_ENDED = {"type": "SESSION_EVENT", "payload": {"event": "ended"}}
_MY_TURN = {
    "type": "TURN_STATUS",
    "payload": {"entries": [{"player_id": "rex-pid", "status": "pending"}]},
}


def _decide_bodies(mock_post) -> list[dict]:
    """The bodies of every companion_brain_decide POST the run produced."""
    bodies = [call.args[1] for call in mock_post.call_args_list]
    return [b for b in bodies if b.get("event_type") == "companion_brain_decide"]


async def test_companion_decision_emits_brain_decide_event():
    # AC #6: THE wiring test. A real decision through the real loop must produce a
    # companion_brain_decide event tagged with the room slug, seat, and role.
    transport = FakeTransport([_CONNECTED, _MY_TURN, _ENDED])
    brain = _brain(CompanionIntent(kind=IntentKind.ACT, text="I deign to pounce."))
    with patch("companion.telemetry._post") as mock_post:
        await run_companion(_defn(), transport, brain, rng=random.Random(0))

    decides = _decide_bodies(mock_post)
    assert len(decides) == 1, "exactly one decision this turn -> exactly one telemetry event"
    ev = decides[0]
    # Envelope-level partition key (AC #6): the room the companion is playing in.
    assert ev["session_slug"] == "game-1"
    f = ev["fields"]
    # Identity (AC #6): seat + role. Role is a StrEnum, equal to its string value.
    assert f["seat"] == "Donut"
    assert f["role"] == "pet"
    assert f["species"] == "cat"
    # Breadth (AC #2): the full field set must be present, or the Inspector tab
    # (161-3) has nothing to render.
    for key in (
        "owner",
        "outcome",
        "intent_kind",
        "degraded",
        "timed_out",
        "backend",
        "model",
        "duration_ms",
        "tokens",
        "cost_usd",
    ):
        assert key in f, f"companion_brain_decide missing required field {key!r}"
    # A successful ACT is neither degraded nor a timeout.
    assert f["degraded"] is False
    assert f["timed_out"] is False
    assert f["intent_kind"] == "act"
    assert isinstance(f["duration_ms"], (int, float)) and f["duration_ms"] >= 0


async def test_timed_out_decision_still_emits_degraded_warning():
    # AC #3: silence is not acceptable for a lie-detector. A brain slower than the
    # decide timeout degrades to YIELD (never stalls the table) AND still fires an
    # event marked degraded + timed_out at WARNING severity.
    class Slow:
        async def decide(self, system, transcript):
            await asyncio.sleep(10)

    transport = FakeTransport([_CONNECTED, _MY_TURN, _ENDED])
    with patch("companion.telemetry._post") as mock_post:
        await asyncio.wait_for(
            run_companion(_defn(decide_timeout_s=0.05), transport, Slow(), rng=random.Random(0)),
            timeout=3.0,
        )

    # The table never stalls — the turn still yields.
    assert "YIELD" in [f["type"] for f in transport.sent]
    # ...and the degraded decision is not silent.
    decides = _decide_bodies(mock_post)
    assert decides, "a timed-out decision must STILL emit an event (silence is a bug)"
    ev = decides[0]
    assert ev["severity"] == "warning"
    assert ev["fields"]["degraded"] is True
    assert ev["fields"]["timed_out"] is True


async def test_emit_failure_never_breaks_the_companion_turn(caplog):
    # AC #5: a bridge POST failure (server down) is logged loudly and swallowed —
    # the companion's move still goes out. Telemetry must never break play.
    transport = FakeTransport([_CONNECTED, _MY_TURN, _ENDED])
    brain = _brain(CompanionIntent(kind=IntentKind.ACT, text="I deign to pounce."))
    with patch("companion.telemetry._post", side_effect=urllib.error.URLError("server down")):
        with caplog.at_level(logging.WARNING):
            await run_companion(_defn(), transport, brain, rng=random.Random(0))

    # The move still happened despite the telemetry failure.
    assert "PLAYER_ACTION" in [f["type"] for f in transport.sent]
    # And the failure was logged loudly (fail-loud-non-fatal), not silently dropped.
    assert any(r.levelno == logging.WARNING for r in caplog.records), (
        "an emit failure must be visible at WARNING, never a silent swallow"
    )
