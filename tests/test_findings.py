from understudy.findings.detect import repeated_action
from understudy.findings.reconcile import reconcile
from understudy.types import (
    FrictionSignal,
    Grade,
    Intent,
    IntentKind,
    SignalKind,
    TranscriptRow,
)


def _act(name="Send"):
    return Intent(kind=IntentKind.ACT, target_role="button", target_name=name)


def _row(seat, turn, intent=None, signals=(), snapshot="- main:"):
    return TranscriptRow(
        seat=seat,
        turn=turn,
        snapshot=snapshot,
        intent=intent,
        resolution="n/a",
        narration_delta="",
        signals=list(signals),
    )


def _sig(kind, seat, turn):
    return FrictionSignal(kind=kind, seat=seat, turn=turn, detail="x")


def test_repeated_action_detects_three_identical_acts():
    assert repeated_action([_act(), _act(), _act()], n=3)
    assert not repeated_action([_act(), _act("Roll"), _act()], n=3)
    assert not repeated_action([_act(), _act()], n=3)


def test_confirmed_when_confusion_meets_objective_signal_in_window():
    confusion = Intent(kind=IntentKind.REPORT_CONFUSION, reason="cannot find submit")
    rows = [
        _row(1, 4, _act(), [_sig(SignalKind.RESOLUTION_FAILED, 1, 4)]),
        _row(1, 5, confusion),
    ]
    findings = reconcile(rows, {1: "hesitant"})
    grades = {f.grade for f in findings}
    assert Grade.CONFIRMED in grades


def test_claimed_when_confusion_has_clean_behavior():
    confusion = Intent(kind=IntentKind.REPORT_CONFUSION, reason="this is weird")
    findings = reconcile([_row(1, 2, confusion)], {1: "narrative_first"})
    assert [f.grade for f in findings] == [Grade.CLAIMED]
    assert findings[0].confusion_reason == "this is weird"


def test_behavioral_when_friction_without_complaint():
    rows = [_row(2, 7, _act(), [_sig(SignalKind.REPEATED_ACTION, 2, 7)])]
    findings = reconcile(rows, {2: "mechanics_first"})
    assert [f.grade for f in findings] == [Grade.BEHAVIORAL]


def test_model_error_is_downweighted_never_confirms():
    confusion = Intent(kind=IntentKind.REPORT_CONFUSION, reason="huh")
    rows = [
        _row(3, 1, None, [_sig(SignalKind.MODEL_ERROR, 3, 1)]),
        _row(3, 2, confusion),
    ]
    findings = reconcile(rows, {3: "hesitant"})
    assert all(f.grade is not Grade.CONFIRMED for f in findings)


def test_signals_from_other_seats_never_cross():
    confusion = Intent(kind=IntentKind.REPORT_CONFUSION, reason="lost")
    rows = [
        _row(1, 3, _act(), [_sig(SignalKind.RESOLUTION_FAILED, 1, 3)]),
        _row(2, 3, confusion),
    ]
    findings = reconcile(rows, {1: "hesitant", 2: "narrative_first"})
    claimed = [f for f in findings if f.seat == 2]
    assert [f.grade for f in claimed] == [Grade.CLAIMED]


def _confused(reason="stuck"):
    return Intent(kind=IntentKind.REPORT_CONFUSION, reason=reason)


def test_same_stuck_state_collapses_to_one_finding_with_turn_range():
    """40 complaints against a frozen page are ONE finding (the r2 lesson:
    145 rows of the same missing portrait picker). Same seat + same snapshot
    = same stuck state, regardless of how the complaint is reworded."""
    frozen = "- main:\n  - paragraph: Choose a portrait"
    rows = [
        _row(1, t, _confused(f"still no portraits, wording {t}"), snapshot=frozen)
        for t in range(11, 21)
    ]
    findings = reconcile(rows, {1: "hesitant"})
    assert len(findings) == 1
    f = findings[0]
    assert f.turn == 11
    assert f.turn_end == 20
    assert f.occurrences == 10
    assert "still no portraits" in (f.confusion_reason or "")


def test_different_snapshots_do_not_collapse():
    rows = [
        _row(1, 1, _confused("lost on page A"), snapshot="- main: page A"),
        _row(1, 2, _confused("lost on page B"), snapshot="- main: page B"),
    ]
    findings = reconcile(rows, {1: "hesitant"})
    assert len(findings) == 2
    assert all(f.occurrences == 1 and f.turn_end == f.turn for f in findings)


def test_collapse_does_not_cross_seats_or_grades():
    frozen = "- main: frozen"
    rows = [
        # seat 1: claimed complaints on the frozen page
        _row(1, 1, _confused("stuck"), snapshot=frozen),
        _row(1, 2, _confused("still stuck"), snapshot=frozen),
        # seat 2: same page, but its complaint is CONFIRMED by a hard signal
        _row(
            2,
            1,
            _confused("stuck too"),
            [_sig(SignalKind.RESOLUTION_FAILED, 2, 1)],
            snapshot=frozen,
        ),
    ]
    findings = reconcile(rows, {1: "hesitant", 2: "mechanics_first"})
    by_seat = {f.seat: f for f in findings}
    assert len(findings) == 2
    assert by_seat[1].grade is Grade.CLAIMED and by_seat[1].occurrences == 2
    assert by_seat[2].grade is Grade.CONFIRMED and by_seat[2].occurrences == 1


def test_waits_between_complaints_do_not_split_the_collapse():
    """hesitant waits between complaints; the stuck-state is still one finding."""
    frozen = "- main: frozen"
    rows = [
        _row(1, 1, _confused("stuck"), snapshot=frozen),
        _row(1, 2, Intent(kind=IntentKind.WAIT), snapshot=frozen),
        _row(1, 3, _confused("yep still stuck"), snapshot=frozen),
    ]
    findings = reconcile(rows, {1: "hesitant"})
    assert len(findings) == 1
    assert findings[0].turn == 1 and findings[0].turn_end == 3 and findings[0].occurrences == 2
