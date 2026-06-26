"""RED (159-4): CompanionIntent decision contract — Plan C Task 2.

The intent is the brain's per-turn output. ACT/ASIDE carry prose; BEAT names a
confrontation beat; ROLL/DEFEND/YIELD carry nothing. Validators enforce the
shape so a malformed decision can never leave the brain pretending to be valid.
"""

import pytest
from pydantic import ValidationError

from companion.intent import CompanionIntent, IntentKind, YIELD_INTENT


def test_act_requires_text():
    CompanionIntent(kind=IntentKind.ACT, text="I scout ahead.")  # ok
    with pytest.raises(ValidationError):
        CompanionIntent(kind=IntentKind.ACT)


def test_aside_requires_text():
    CompanionIntent(kind=IntentKind.ASIDE, text="(brb, refilling tea)")  # ok
    with pytest.raises(ValidationError):
        CompanionIntent(kind=IntentKind.ASIDE)


def test_beat_requires_beat_id():
    CompanionIntent(kind=IntentKind.BEAT, beat_id="riposte")  # ok
    with pytest.raises(ValidationError):
        CompanionIntent(kind=IntentKind.BEAT)


def test_yield_and_roll_and_defend_need_nothing():
    assert CompanionIntent(kind=IntentKind.YIELD).kind is IntentKind.YIELD
    assert CompanionIntent(kind=IntentKind.ROLL).kind is IntentKind.ROLL
    assert CompanionIntent(kind=IntentKind.DEFEND).kind is IntentKind.DEFEND


def test_yield_default_constant():
    # The safe default the brain falls back to on any failure.
    assert YIELD_INTENT.kind is IntentKind.YIELD


def test_extra_fields_rejected():
    # extra="forbid" — a fabricated field must not silently ride along.
    with pytest.raises(ValidationError):
        CompanionIntent(kind=IntentKind.YIELD, smuggled="payload")
