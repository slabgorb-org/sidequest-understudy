"""Story 160-4 (RED): the companion run loop must FAIL LOUD on a rejected
connect — it must not silently loop back to ``recv()`` and hang forever.

Bug (sq-playtest 2026-06-27): when the server rejects a connect it replies
``{"type": "ERROR", "payload": {"message": "...", "reconnect_required": false}}``
and (for a SOLO-slot conflict) keeps the socket open. ``run_companion`` handles
only ``SESSION_EVENT``-ended / ``CHARACTER_CREATION`` / the prompt kinds /
``TURN_STATUS``; an ``ERROR`` frame matches no branch, so the loop falls through
and calls ``recv()`` again — which blocks forever. The rejection is swallowed
(No Silent Fallbacks violation) and the run hangs with no diagnostic.

This half of 160-4 is independent of the server-side SOLO fork: a rejected
connect of ANY kind must surface loudly. Contract: on an ``ERROR`` frame the
loop raises a loud RuntimeError-family exception carrying the server's message
(the CLI leaves it uncaught → non-zero exit; ``cli.py`` only catches
``ManifestError``). The exact exception class is Dev's choice — the module's own
``ChargenStepUnsupported(RuntimeError)`` is the established fail-loud shape.
"""

from __future__ import annotations

import asyncio
import logging
import random

import pytest

from companion.intent import CompanionIntent, IntentKind
from companion.manifest import CompanionDef
from companion.run import run_companion
from seat_core.core import FakeStructuredModel
from seat_core.persona.axis import Role, SeatAxes

# The exact frame the server sends on a SOLO-slot rejection (story 160-4 repro).
_SOLO_REJECT = {
    "type": "ERROR",
    "payload": {
        "message": "solo game 2026-06-27-beneath_sunden already occupied by Curly",
        "reconnect_required": False,
    },
}


def _defn() -> CompanionDef:
    return CompanionDef(
        name="Owl",
        species="owl",
        role=Role.PET,
        voice="v",
        axes=SeatAxes(
            narrative_vs_mechanical=0.4,
            verbosity="medium",
            decisiveness="high",
            reading_tolerance="medium",
        ),
        companion_of="player1.local",
        genre="caverns_and_claudes",
        world="beneath_sunden",
        game_slug="2026-06-27-beneath_sunden",
        session_url="ws://x/ws",
        decide_timeout_s=30.0,
    )


def _brain() -> FakeStructuredModel:
    return FakeStructuredModel([], default=CompanionIntent(kind=IntentKind.YIELD))


class _OneShotRejectTransport:
    """Scripted server: sends its connect frame, replies with the ERROR
    rejection, then closes (``recv`` -> None)."""

    def __init__(self) -> None:
        self._incoming: list[dict] = [_SOLO_REJECT]
        self.sent: list[dict] = []

    async def send(self, frame: dict) -> None:
        self.sent.append(frame)

    async def recv(self) -> dict | None:
        return self._incoming.pop(0) if self._incoming else None


class _HangingRejectTransport:
    """Models production faithfully: the server rejects, then HOLDS the socket
    open. ``recv`` yields the ERROR frame once; a second ``recv`` (the real
    hang) fails loud so the test can prove the loop did not loop back to it."""

    def __init__(self) -> None:
        self.sent: list[dict] = []
        self.recv_calls = 0

    async def send(self, frame: dict) -> None:
        self.sent.append(frame)

    async def recv(self) -> dict | None:
        self.recv_calls += 1
        if self.recv_calls == 1:
            return _SOLO_REJECT
        raise AssertionError(
            "run loop called recv() again after an ERROR connect rejection — in "
            "production the server holds the socket open here and this recv() "
            "blocks forever (the 160-4 hang). The loop must fail loud on the "
            "ERROR frame instead of looping back."
        )


async def test_error_connect_rejection_raises_loud(caplog: pytest.LogCaptureFixture) -> None:
    """AC4: an ERROR connect rejection makes ``run_companion`` fail loud — raise
    (carrying the server's message) instead of returning as if nothing happened.
    Today the loop swallows the ERROR frame and returns cleanly on the closed
    transport; no exception is raised."""
    transport = _OneShotRejectTransport()
    with caplog.at_level(logging.WARNING, logger="companion.run"):
        with pytest.raises(RuntimeError) as excinfo:
            await asyncio.wait_for(
                run_companion(_defn(), transport, _brain(), rng=random.Random(0)),
                timeout=2.0,
            )

    assert "already occupied by Curly" in str(excinfo.value), (
        "the loud failure must surface the server's rejection message (No Silent "
        f"Fallbacks); got {excinfo.value!r}"
    )
    assert any("already occupied by Curly" in r.getMessage() for r in caplog.records), (
        "the rejection must also be logged so it is visible in the run output"
    )


async def test_error_rejection_does_not_loop_back_to_recv_and_hang() -> None:
    """AC4 (anti-hang): the loop must fail loud ON the ERROR frame and never call
    ``recv()`` a second time — that second ``recv()`` is where production blocks
    forever. Proven by a transport that raises if ``recv`` is called twice."""
    transport = _HangingRejectTransport()
    with pytest.raises(RuntimeError):
        await asyncio.wait_for(
            run_companion(_defn(), transport, _brain(), rng=random.Random(0)),
            timeout=2.0,
        )

    assert transport.recv_calls == 1, (
        "run_companion must fail loud on the ERROR frame, not loop back to recv() "
        f"(the hang); recv was called {transport.recv_calls} times"
    )
