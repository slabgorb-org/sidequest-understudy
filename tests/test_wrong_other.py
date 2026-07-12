"""Green Room Task 7 (RED) — the understudy wrong-Other detector, closing 166-5.

Server-side, ADR-156's Green Room materializer + target-first seater stop the
engine from seating a mechanically-convenient bystander (e.g. a co-located
"Resonance Grazer") when the fiction names a specific target (e.g. "Ihnsch of
the Rusted Works", the Salt Camp Scrapborn). This is the naive-player-visible
detector for a REGRESSION of that fix: if the Enemies panel ever again seats an
opponent the recent story never mentions, a playtest bot must catch it without
being told anything about creature ids, origin tiers, or the
`green_room.materialized` span — those are backend state a player never sees.

NAIVETY INVARIANT (understudy CLAUDE.md — load-bearing): the detector reads
ONLY screen-visible text (the aria snapshot the player perceives), exactly
like its 162-11 sibling `two_names_one_enemy`. It infers the seated foes from
the Enemies panel and checks EACH one against the last 3 narration beats —
nothing more. Every listitem in the panel is its own distinct seated foe (the
shipped ConfrontationOverlay exposes one plain name per foe — there is no
alias-chip UI), so each foe is judged independently and every absent one is
reported: the classic 166-5 shape seats the CORRECT target plus a
mechanically-convenient bystander, and the bystander must not hide behind the
target's narration mentions.

RED today: ``understudy.findings.detect.wrong_other`` does not exist and
``SignalKind.WRONG_OTHER`` is not a member. GREEN = implement the pure
detector (mirroring ``two_names_one_enemy``'s zero-LLM style, reusing its
`_enemy_labels` / `_narration_entries` helpers) + the new signal kind, and wire
it into the per-turn seat loop so it grades through ``reconcile``.
"""

from understudy.findings.detect import wrong_other
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

# The Enemies panel seats "Resonance Grazer" — but the last three narration
# beats are all about "Ihnsch of the Rusted Works" (the Salt Camp Scrapborn,
# the 166-5 regression's actual fiction target). The seated Other's name never
# appears in the recent story: evidence the engine seated somebody the story
# isn't about.
SEATED_WRONG = """\
- heading "Combat" [level=1]
- region "Enemies":
  - list:
    - listitem: Resonance Grazer
- log:
  - paragraph: You grab the loudest one by the collar.
  - paragraph: Ihnsch of the Rusted Works snarls and shoves back.
  - paragraph: The Scrapborn's crew scatters into the scrap heaps.
- textbox "Action"
- button "Send"
"""

# The inverse: the seated Other IS the fiction's target — the narration names
# it directly. Clean.
SEATED_RIGHT = """\
- heading "Combat" [level=1]
- region "Enemies":
  - list:
    - listitem: Ihnsch of the Rusted Works
- log:
  - paragraph: You grab the loudest one by the collar.
  - paragraph: Ihnsch of the Rusted Works snarls and shoves back.
  - paragraph: His crew scatters into the scrap heaps.
- textbox "Action"
- button "Send"
"""

# No enemy panel at all — nothing seated, nothing to judge. Must NOT flag.
NO_COMBAT = """\
- heading "The Flickering Reach" [level=1]
- main:
  - log: Old Hessa the innkeeper waves you over to the bar.
  - textbox "Action"
  - button "Send"
"""


class TestDetector:
    def test_flags_seated_opponent_absent_from_recent_narration(self) -> None:
        assert wrong_other(SEATED_WRONG) == ["Resonance Grazer"], (
            "a seated opponent absent from the last 3 narration beats was not flagged"
        )

    def test_seated_opponent_named_in_narration_is_clean(self) -> None:
        assert wrong_other(SEATED_RIGHT) == []

    def test_no_combat_panel_is_clean(self) -> None:
        assert wrong_other(NO_COMBAT) == []

    def test_empty_snapshot_is_clean(self) -> None:
        assert wrong_other("") == []

    def test_no_narration_yet_is_clean(self) -> None:
        """A freshly-opened confrontation panel with no narration beats yet is
        not evidence of anything — nothing to judge against."""
        snapshot = """\
- region "Enemies":
  - list:
    - listitem: Resonance Grazer
- textbox "Action"
"""
        assert wrong_other(snapshot) == []

    def test_epithet_only_narration_still_fires(self) -> None:
        """Documented, accepted scope: the panel exposes only the canonical
        name ("Ihnsch of the Rusted Works"); the narration uses only the
        epithet ("the Scrapborn"). The bot has no screen-visible link between
        them — so this reads as a fork, the same confusion a naive player
        reading only the screen would have. Don't over-suppress."""
        snapshot = """\
- region "Enemies":
  - list:
    - listitem: Ihnsch of the Rusted Works
- log:
  - paragraph: The Scrapborn lunges from the scrap heap.
"""
        assert wrong_other(snapshot) == ["Ihnsch of the Rusted Works"]


class TestWindow:
    """The brief's chosen window is the last 3 narration entries."""

    def test_mention_outside_the_last_three_still_fires(self) -> None:
        """The opponent was named four beats back but pacing has moved on
        entirely — that's exactly the signal the detector wants, not a reason
        to suppress (don't over-suppress)."""
        snapshot = """\
- region "Enemies":
  - list:
    - listitem: Resonance Grazer
- log:
  - paragraph: Resonance Grazer rears up in the dark.
  - paragraph: You duck past the collapsed catwalk.
  - paragraph: Sparks rain from the severed conduit.
  - paragraph: The Scrapborn's crew regroups at the far door.
"""
        assert wrong_other(snapshot) == ["Resonance Grazer"]

    def test_mention_within_the_last_three_suppresses(self) -> None:
        snapshot = """\
- region "Enemies":
  - list:
    - listitem: Resonance Grazer
- log:
  - paragraph: You duck past the collapsed catwalk.
  - paragraph: Sparks rain from the severed conduit.
  - paragraph: Resonance Grazer rears up in the dark.
"""
        assert wrong_other(snapshot) == []


class TestNormalization:
    def test_case_insensitive_match_suppresses(self) -> None:
        snapshot = """\
- region "Enemies":
  - list:
    - listitem: resonance grazer
- log:
  - paragraph: The RESONANCE GRAZER shrieks and charges.
"""
        assert wrong_other(snapshot) == []

    def test_possessive_mention_suppresses(self) -> None:
        """Substring matching catches possessive phrasing ("the Grazer's
        claws") for free — no dedicated possessive-stripping rule needed."""
        snapshot = """\
- region "Enemies":
  - list:
    - listitem: Grazer
- log:
  - paragraph: The Grazer's claws rake your arm.
"""
        assert wrong_other(snapshot) == []


class TestMultiFoe:
    """Every Enemies listitem is its own distinct seated foe (the shipped
    panel exposes one plain name per foe — no alias-chip UI exists), so each
    is judged independently against the recent-narration window and EVERY
    absent one is reported."""

    def test_correct_target_plus_silent_bystander_flags_only_bystander(self) -> None:
        """The classic 166-5 shape: the engine seats the CORRECT fiction
        target ("Ihnsch of the Rusted Works") PLUS a mechanically-convenient
        bystander ("Resonance Grazer"). Narration names the target — it's the
        story target — and never the bystander. The bystander must be flagged;
        it must not hide behind the target's narration mentions."""
        snapshot = """\
- region "Enemies":
  - list:
    - listitem: Ihnsch of the Rusted Works
    - listitem: Resonance Grazer
- log:
  - paragraph: You grab the loudest one by the collar.
  - paragraph: Ihnsch of the Rusted Works snarls and shoves back.
  - paragraph: His crew scatters into the scrap heaps.
"""
        assert wrong_other(snapshot) == ["Resonance Grazer"]

    def test_both_foes_absent_flags_both(self) -> None:
        snapshot = """\
- region "Enemies":
  - list:
    - listitem: Resonance Grazer
    - listitem: Rustwing Vulture
- log:
  - paragraph: You grab the loudest one by the collar.
  - paragraph: Ihnsch of the Rusted Works snarls and shoves back.
  - paragraph: His crew scatters into the scrap heaps.
"""
        assert wrong_other(snapshot) == ["Resonance Grazer", "Rustwing Vulture"]

    def test_both_foes_named_is_clean(self) -> None:
        snapshot = """\
- region "Enemies":
  - list:
    - listitem: Ihnsch of the Rusted Works
    - listitem: Resonance Grazer
- log:
  - paragraph: Ihnsch of the Rusted Works snarls and shoves back.
  - paragraph: A resonance grazer rears up behind him, shrieking.
  - paragraph: The scrapyard erupts.
"""
        assert wrong_other(snapshot) == []


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


def _wrong_other_signal(seat, turn, detail="Resonance Grazer seated; absent from recent narration"):
    return FrictionSignal(kind=SignalKind.WRONG_OTHER, seat=seat, turn=turn, detail=detail)


class TestGrading:
    def test_wrong_other_signal_alone_grades_behavioral(self) -> None:
        """The bot muddled through the mis-seated Other without complaining —
        the harness still catches it (objective-only -> BEHAVIORAL). Pins that
        the new kind is a HARD signal, not down-weighted like MODEL_ERROR."""
        rows = [_row(1, 3, signals=[_wrong_other_signal(1, 3)])]
        findings = reconcile(rows, {1: "mechanics_first"})
        assert [f.grade for f in findings] == [Grade.BEHAVIORAL]
        assert findings[0].signals[0].kind is SignalKind.WRONG_OTHER

    def test_wrong_other_signal_with_complaint_grades_confirmed(self) -> None:
        confusion = Intent(
            kind=IntentKind.REPORT_CONFUSION,
            reason="I'm fighting a Resonance Grazer but the story never mentions one",
        )
        rows = [
            _row(1, 4, signals=[_wrong_other_signal(1, 4)]),
            _row(1, 5, confusion),
        ]
        findings = reconcile(rows, {1: "mechanics_first"})
        assert Grade.CONFIRMED in {f.grade for f in findings}
