import pytest
from pydantic import ValidationError

from understudy.types import (
    Finding,
    FrictionSignal,
    Grade,
    Intent,
    IntentKind,
    SignalKind,
    TranscriptRow,
)


def test_act_intent_requires_target():
    with pytest.raises(ValidationError):
        Intent(kind=IntentKind.ACT)


def test_act_intent_with_target_validates():
    i = Intent(kind=IntentKind.ACT, target_role="button", target_name="Send")
    assert i.target_name == "Send"


def test_confusion_requires_reason():
    with pytest.raises(ValidationError):
        Intent(kind=IntentKind.REPORT_CONFUSION)


def test_wait_is_bare():
    i = Intent(kind=IntentKind.WAIT)
    assert i.kind is IntentKind.WAIT


def test_intent_rejects_extra_fields():
    with pytest.raises(ValidationError):
        Intent(kind=IntentKind.WAIT, hitpoints=10)


def test_transcript_row_roundtrips_json():
    row = TranscriptRow(
        seat=2,
        turn=3,
        snapshot='- button "Send"',
        intent=Intent(kind=IntentKind.WAIT),
        resolution="n/a",
        narration_delta="",
        signals=[FrictionSignal(kind=SignalKind.DECIDE_TIMEOUT, seat=2, turn=3, detail="120s")],
    )
    again = TranscriptRow.model_validate_json(row.model_dump_json())
    assert again.signals[0].kind is SignalKind.DECIDE_TIMEOUT


def test_finding_grade_values():
    assert {g.value for g in Grade} == {"confirmed", "behavioral", "claimed"}
    f = Finding(
        grade=Grade.CLAIMED, seat=1, archetype="hesitant", turn=4,
        confusion_reason="cannot tell whose turn it is", signals=[], snapshot_excerpt="…",
    )
    assert f.grade is Grade.CLAIMED
