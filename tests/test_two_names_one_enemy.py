"""Story 162-7 (RED) — the understudy identity-split hunt.

The naive-player-visible symptom of a server identity fork (the 108-2
two-names-one-enemy report): the combat panel names the single foe one way
(the mechanical label, e.g. "Thief") while the narration names the SAME foe
another way ("Molgrath the Eyeless"). A player fighting one enemy sees two
names for it and cannot tell they are the same being. That confusion is a
finding.

NAIVETY INVARIANT (understudy CLAUDE.md — load-bearing): the detector reads
ONLY screen-visible text (the aria snapshot the player perceives). It must
NEVER consult an engine alias map, a creature_id, or the OTEL identity.resolved
span — those are backend state a player never sees. It infers "one enemy" from
the screen alone: exactly one entry in the enemy panel, plus a differently-named
foe in the narration.

RED today: ``understudy.findings.detect.two_names_one_enemy`` does not exist and
``SignalKind.TWO_NAMES_ONE_ENEMY`` is not a member. GREEN = implement the pure
detector (mirroring ``repeated_action``'s zero-LLM style) + the new signal kind,
and wire it into the per-turn signal collection so it grades through
``reconcile`` (see tests/wiring/test_identity_fork_finding.py for the wiring).
"""

from understudy.findings.detect import two_names_one_enemy
from understudy.findings.reconcile import reconcile
from understudy.types import (
    FrictionSignal,
    Grade,
    Intent,
    IntentKind,
    SignalKind,
    TranscriptRow,
)

# --- screen-visible aria snapshots (what perceive() hands the player) --------

# One enemy in the panel ("Thief"); the narration names the foe differently
# ("Molgrath the Eyeless"). Two names, one enemy — the fork the player sees.
FORKED = """\
- heading "Combat" [level=1]
- region "Enemies":
  - list:
    - listitem: Thief
- log: Molgrath the Eyeless lunges at you from the dark.
- textbox "Action"
- button "Send"
"""

# The panel and the narration agree — the foe is "the Thief" throughout. Clean.
CONSISTENT = """\
- heading "Combat" [level=1]
- region "Enemies":
  - list:
    - listitem: Thief
- log: The Thief lunges at you from the dark.
- textbox "Action"
- button "Send"
"""

# No enemy panel at all — a proper noun in the narration is an NPC the player is
# talking to, not a mislabeled foe. Must NOT flag (false-positive guard).
NO_COMBAT = """\
- heading "The Flickering Reach" [level=1]
- main:
  - log: Old Hessa the innkeeper waves you over to the bar.
  - textbox "Action"
  - button "Send"
"""


class TestDetector:
    def test_flags_panel_label_vs_narrated_foe(self) -> None:
        hit = two_names_one_enemy(FORKED)
        assert hit is not None, "the fork the player sees was not flagged"
        assert "Molgrath" in hit, f"the flagged conflict should name the narrated foe, got {hit!r}"

    def test_consistent_naming_is_clean(self) -> None:
        assert two_names_one_enemy(CONSISTENT) is None

    def test_no_combat_panel_is_clean(self) -> None:
        """A named NPC with no enemy panel is not a combat identity fork."""
        assert two_names_one_enemy(NO_COMBAT) is None

    def test_empty_snapshot_is_clean(self) -> None:
        assert two_names_one_enemy("") is None


# --- the new signal grades through the existing reconciler -------------------


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


def _two_names_signal(seat, turn, detail="Thief vs Molgrath the Eyeless"):
    return FrictionSignal(kind=SignalKind.TWO_NAMES_ONE_ENEMY, seat=seat, turn=turn, detail=detail)


class TestGrading:
    def test_two_names_signal_alone_grades_behavioral(self) -> None:
        """The bot muddled through the mislabeled foe without complaining — the
        harness still catches it (objective-only → BEHAVIORAL). This pins that
        the new kind is a HARD signal, not down-weighted like MODEL_ERROR."""
        rows = [_row(1, 3, signals=[_two_names_signal(1, 3)])]
        findings = reconcile(rows, {1: "mechanics_first"})
        assert [f.grade for f in findings] == [Grade.BEHAVIORAL]
        assert findings[0].signals[0].kind is SignalKind.TWO_NAMES_ONE_ENEMY

    def test_two_names_signal_with_complaint_grades_confirmed(self) -> None:
        """A naive player who ALSO says 'wait, who is Molgrath — I'm fighting a
        Thief?' within ±1 turn confirms the objective signal → CONFIRMED."""
        confusion = Intent(
            kind=IntentKind.REPORT_CONFUSION,
            reason="the panel says Thief but the story keeps naming someone called Molgrath",
        )
        rows = [
            _row(1, 4, signals=[_two_names_signal(1, 4)]),
            _row(1, 5, confusion),
        ]
        findings = reconcile(rows, {1: "mechanics_first"})
        assert Grade.CONFIRMED in {f.grade for f in findings}
