"""RED (159-4): transport seam, frame builders, state mirror — Plan C Task 6.

The protocol module is the thin typed WS subset: outgoing-frame builders (the
companion's OWN actions only — never narration, SOUL.md Test) and a StateMirror
that merges server pushes into 'what I currently know' (self id, round, turn,
pending roll/confrontation prompt). The real WebSocket adapter is 159-5.
"""

from companion.manifest import CompanionDef
from companion.protocol import (
    StateMirror,
    connect_frame,
    dice_throw_frame,
    player_action_frame,
    yield_frame,
)
from seat_core.persona.axis import Role, SeatAxes


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
        session_url="ws://x/ws",
    )


def test_connect_frame_carries_companion_metadata():
    f = connect_frame(_defn())
    assert f["type"] == "SESSION_EVENT"
    assert f["payload"]["event"] == "connect"
    assert f["payload"]["player_name"] == "Donut"
    assert f["payload"]["companion_of"] == "alice@home"
    assert f["payload"]["relationship"] == "pet"


def test_player_action_frame_shape():
    f = player_action_frame("rex-pid", "I scout ahead.", 3)
    assert f["type"] == "PLAYER_ACTION"
    assert f["payload"]["action"] == "I scout ahead."
    assert f["payload"]["round"] == 3
    assert f["player_id"] == "rex-pid"


def test_dice_throw_frame_shape():
    f = dice_throw_frame("rex-pid", [4, 3, 5, 2], beat_id="riposte")
    assert f["type"] == "DICE_THROW"
    assert f["payload"]["faces"] == [4, 3, 5, 2]
    assert f["payload"]["beat_id"] == "riposte"


def test_dice_throw_frame_omits_beat_id_when_absent():
    # A plain roll carries no beat_id key (it's not a confrontation beat).
    f = dice_throw_frame("rex-pid", [11])
    assert "beat_id" not in f["payload"]


def test_yield_frame_shape():
    f = yield_frame("rex-pid", 4)
    assert f["type"] == "YIELD"
    assert f["player_id"] == "rex-pid"
    assert f["payload"]["round"] == 4


def test_mirror_captures_self_id_round_and_turn():
    m = StateMirror()
    m.apply({"type": "SESSION_EVENT", "payload": {"event": "connected"}, "player_id": "rex-pid"})
    assert m.self_player_id == "rex-pid"
    m.apply({"type": "NARRATION_END", "payload": {"round": 5}})
    assert m.round == 5
    # my seat is pending → my turn
    m.apply({"type": "TURN_STATUS", "payload": {"entries": [
        {"player_id": "rex-pid", "status": "pending"},
        {"player_id": "alice-pid", "status": "submitted"},
    ]}})
    assert m.my_turn() is True
    # after I submit, not my turn
    m.apply({"type": "TURN_STATUS", "payload": {"entries": [
        {"player_id": "rex-pid", "status": "submitted"},
    ]}})
    assert m.my_turn() is False


def test_mirror_my_turn_false_before_self_id_known():
    # No self id yet → never claim it's my turn (can't act for an unknown seat).
    m = StateMirror()
    m.apply({"type": "TURN_STATUS", "payload": {"entries": [
        {"player_id": "rex-pid", "status": "pending"},
    ]}})
    assert m.my_turn() is False


def test_mirror_records_pending_dice_request():
    m = StateMirror()
    m.apply({"type": "SESSION_EVENT", "payload": {"event": "connected"}, "player_id": "rex-pid"})
    m.apply({"type": "DICE_REQUEST", "payload": {"roller": "Donut", "die_system": "d20"}})
    assert m.pending == ("DICE_REQUEST", {"roller": "Donut", "die_system": "d20"})


def test_mirror_resolved_round_clears_stale_prompt():
    # A resolved round must clear a stale pending prompt, else the companion
    # could answer a roll the table already moved past.
    m = StateMirror()
    m.apply({"type": "DICE_REQUEST", "payload": {"die_system": "d20"}})
    assert m.pending is not None
    m.apply({"type": "NARRATION_END", "payload": {"round": 2}})
    assert m.pending is None
