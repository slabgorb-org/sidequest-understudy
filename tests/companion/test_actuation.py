"""RED (159-4): actuation — intent -> outgoing frame — Plan C Task 8.

actuate() is the in-package integration point: it composes intent + StateMirror +
dice.roll_faces + protocol frame builders into exactly one outgoing frame. Dice
faces are generated fair here (physics-is-the-roll) from the pending prompt's die
system. With no self id yet, there is nothing to send -> None (never a frame with
a null player).
"""

import random

from companion.actuation import actuate
from companion.intent import CompanionIntent, IntentKind
from companion.protocol import StateMirror


def _mirror(pending=None, round_=3) -> StateMirror:
    m = StateMirror()
    m.self_player_id = "rex-pid"
    m.round = round_
    m.pending = pending
    return m


def test_act_becomes_player_action():
    f = actuate(CompanionIntent(kind=IntentKind.ACT, text="I pounce."), _mirror())
    assert f["type"] == "PLAYER_ACTION"
    assert f["payload"]["action"] == "I pounce."
    assert f["payload"]["round"] == 3
    assert f["player_id"] == "rex-pid"


def test_aside_becomes_aside_player_action():
    f = actuate(CompanionIntent(kind=IntentKind.ASIDE, text="(brb)"), _mirror())
    assert f["type"] == "PLAYER_ACTION"
    assert f["payload"]["aside"] is True


def test_yield_becomes_yield_frame():
    f = actuate(CompanionIntent(kind=IntentKind.YIELD), _mirror())
    assert f["type"] == "YIELD"


def test_roll_uses_pending_die_system_and_fair_faces():
    m = _mirror(pending=("DICE_REQUEST", {"die_system": "d20"}))
    f = actuate(CompanionIntent(kind=IntentKind.ROLL), m, rng=random.Random(1))
    assert f["type"] == "DICE_THROW"
    assert len(f["payload"]["faces"]) == 1 and 1 <= f["payload"]["faces"][0] <= 20


def test_beat_carries_beat_id_and_faces():
    m = _mirror(pending=("CONFRONTATION", {"die_system": "2d6"}))
    f = actuate(CompanionIntent(kind=IntentKind.BEAT, beat_id="riposte"), m, rng=random.Random(2))
    assert f["type"] == "DICE_THROW"
    assert f["payload"]["beat_id"] == "riposte"
    assert len(f["payload"]["faces"]) == 2


def test_defend_becomes_fate_throw():
    m = _mirror(pending=("FATE_DEFEND_REQUEST", {}))
    f = actuate(CompanionIntent(kind=IntentKind.DEFEND), m, rng=random.Random(3))
    assert f["type"] == "FATE_THROW"
    assert f["payload"]["action"] == "defend"
    assert len(f["payload"]["faces"]) == 4


def test_no_self_id_returns_none():
    m = StateMirror()  # no self_player_id
    assert actuate(CompanionIntent(kind=IntentKind.YIELD), m) is None
