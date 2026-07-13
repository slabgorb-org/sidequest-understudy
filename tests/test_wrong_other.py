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
the Enemies panel and checks EACH one against the last 2 narration TURNS —
nothing more. Every listitem in the panel is its own distinct seated foe (the
shipped ConfrontationOverlay exposes one plain name per foe — there is no
alias-chip UI), so each foe is judged independently and every absent one is
reported: the classic 166-5 shape seats the CORRECT target plus a
mechanically-convenient bystander, and the bystander must not hide behind the
target's narration mentions.

THE WINDOW IS NARRATION TURNS, NOT ARIA NODES (final-review Finding 1). The
shipped NarrationScroll emits a noisy segment mix inside role="log": player
echo divs (`- text:`), MULTIPLE `- paragraph:` nodes per markdown turn, an
<hr> (`- separator`) per NARRATION_END, and turn-status / gallery-notice
chrome (`- text:`). Real narrators name the foe in the turn's OPENING
paragraph, so a window counted in nodes has ~1 paragraph of effective prose
depth and fires on a CORRECT server. The detector therefore judges PROSE only
(paragraph nodes / inline log text — echoes and chrome excluded), grouped
into separator-delimited turns, over the last 2 turns (~4-8 paragraphs of
realistic prose).
"""

from understudy.findings.detect import _log_prose_turns, _node_text, wrong_other
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

# The Enemies panel seats "Resonance Grazer" — but the narration turn is all
# about "Ihnsch of the Rusted Works" (the Salt Camp Scrapborn, the 166-5
# regression's actual fiction target). The seated Other's name never appears
# in the recent story: evidence the engine seated somebody the story isn't
# about.
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
            "a seated opponent absent from the recent narration turns was not flagged"
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


# The exact segment mix the shipped NarrationScroll emits through Playwright's
# aria_snapshot (empirically dumped from the real-DOM fixture): player echoes
# and turn-status/gallery chrome are `- text:` nodes, each markdown paragraph
# is its own `- paragraph:` node, each NARRATION_END <hr> is a bare
# `- separator`. The seated foe IS named — in the current turn's OPENING
# paragraph, the realistic narrator shape. The final-review Finding 1 bug: a
# window counted in aria NODES (with the phantom "separator" beat) pushes that
# mention out of range and flags a CORRECT server.
SEGMENT_MIX_NAMED = """\
- region "Enemies":
  - listitem: Resonance Grazer
- log:
  - paragraph: You pick your way into the salt camp as dusk settles over the flats.
  - paragraph: Scavengers watch from the shadows of rusted gantries, muttering.
  - separator
  - text: I circle wide and look for an opening
  - paragraph: The Resonance Grazer rears up between the scrap heaps, shrieking.
  - paragraph: Its cry rattles loose bolts from the gantry overhead.
  - paragraph: Dust sheets down across the salt flats as the echoes die away.
  - text: Waiting for the table… 2 images added to the gallery
  - separator
- textbox "Action"
- button "Send"
"""


class TestWindow:
    """The window is the last 2 narration TURNS — separator-delimited groups
    of prose (real narrator turns run 2-4 paragraphs and name the foe in the
    opening one), never a count of aria nodes."""

    def test_named_in_current_turn_of_shipped_segment_mix_is_clean(self) -> None:
        """The final-review Finding 1 regression gate at unit level: foe named
        in the current turn's opening paragraph across the full shipped
        segment mix (echo + multi-paragraph + chrome + separators) must NOT
        fire. RED before the turn-window fix."""
        assert wrong_other(SEGMENT_MIX_NAMED) == []

    def test_mention_before_the_last_two_turns_still_fires(self) -> None:
        """The opponent was named three turns back but pacing has moved on for
        two full turns — that's exactly the signal the detector wants, not a
        reason to suppress (don't over-suppress)."""
        snapshot = """\
- region "Enemies":
  - listitem: Resonance Grazer
- log:
  - paragraph: Resonance Grazer rears up in the dark.
  - separator
  - paragraph: You duck past the collapsed catwalk.
  - paragraph: Sparks rain from the severed conduit.
  - separator
  - paragraph: The Scrapborn's crew regroups at the far door.
  - separator
"""
        assert wrong_other(snapshot) == ["Resonance Grazer"]

    def test_mention_within_the_last_two_turns_suppresses(self) -> None:
        snapshot = """\
- region "Enemies":
  - listitem: Resonance Grazer
- log:
  - paragraph: You duck past the collapsed catwalk.
  - separator
  - paragraph: Resonance Grazer rears up in the dark.
  - separator
  - paragraph: Sparks rain from the severed conduit.
  - separator
"""
        assert wrong_other(snapshot) == []


class TestProseVsChrome:
    """Only narration PROSE counts: paragraph nodes and inline log text. The
    player's own echoed action and system chrome (`- text:` nodes) are not
    the story naming the foe."""

    def test_player_echo_naming_the_foe_does_not_suppress(self) -> None:
        """The player typing "I attack the Resonance Grazer" is not the
        narration being about the Grazer — if the story itself never names
        the seated foe, the finding still fires."""
        snapshot = """\
- region "Enemies":
  - listitem: Resonance Grazer
- log:
  - text: I attack the Resonance Grazer
  - paragraph: Ihnsch of the Rusted Works shoves you back into the heaps.
  - separator
"""
        assert wrong_other(snapshot) == ["Resonance Grazer"]

    def test_bold_foe_name_in_prose_suppresses(self) -> None:
        """A paragraph with inline markup is an element-only `- paragraph:`
        opener whose prose lands on deeper child lines (`- strong:`,
        `- text:`, footnote `- superscript:`/`- link`/`- /url:` noise) —
        empirically dumped from markdownToHtml output. The bolded foe name is
        still prose and must suppress; the /url property must not leak."""
        snapshot = """\
- region "Enemies":
  - listitem: Resonance Grazer
- log:
  - paragraph:
    - text: The
    - strong: Resonance Grazer
    - text: rears up, shrieking.
    - superscript:
      - link "1":
        - /url: "#footnote-1"
  - separator
"""
        assert wrong_other(snapshot) == []


class TestNodeTextGuards:
    """Aria tokens that must never leak into prose (final-review Finding 1a:
    the bare `- separator` fell through `_node_text` and became a phantom
    narration beat)."""

    def test_valueless_role_token_is_not_prose(self) -> None:
        assert _node_text("  - separator") == ""

    def test_property_line_is_not_prose(self) -> None:
        assert _node_text('        - /url: "#footnote-1"') == ""

    def test_quoted_name_opener_is_not_prose(self) -> None:
        assert _node_text('      - link "1":') == ""


class TestProseTurns:
    """Direct coverage of the turn-grouping walker `_log_prose_turns` (the
    prose spine of the turn window), the way TestNarration pins `_narration`
    for the 162-11 sibling."""

    def test_groups_paragraphs_by_separator(self) -> None:
        lines = [
            "- log:",
            "  - paragraph: First turn opens.",
            "  - paragraph: First turn continues.",
            "  - separator",
            "  - paragraph: Second turn.",
            "  - separator",
        ]
        assert _log_prose_turns(lines) == [
            "First turn opens. First turn continues.",
            "Second turn.",
        ]

    def test_excludes_text_chrome_and_echoes(self) -> None:
        lines = [
            "- log:",
            "  - text: I circle wide and look for an opening",
            "  - paragraph: The Grazer rears up.",
            "  - text: Waiting for the table…",
            "  - separator",
        ]
        assert _log_prose_turns(lines) == ["The Grazer rears up."]

    def test_inline_log_text_is_one_turn(self) -> None:
        """The idealized single-line form (`- log: <text>`) reads as one
        one-beat turn, keeping the pre-realdom fixtures meaningful."""
        assert _log_prose_turns(["- log: Molgrath the Eyeless lunges."]) == [
            "Molgrath the Eyeless lunges."
        ]

    def test_trailing_separator_leaves_no_empty_turn(self) -> None:
        lines = ["- log:", "  - paragraph: Only turn.", "  - separator"]
        assert _log_prose_turns(lines) == ["Only turn."]


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
