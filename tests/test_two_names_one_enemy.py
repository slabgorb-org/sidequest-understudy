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

from understudy.findings.detect import _narration, _node_text, two_names_one_enemy
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


# ═══════════════════════════════════════════════════════════════════════════
# Story 162-11 (rework, round-trip 1) — direct coverage of the _narration /
# _node_text helpers that reconcile the detector to Playwright's REAL nested
# aria_snapshot. Review found these had zero direct unit tests and one genuine
# silent-fallback (a `log:` opener with a trailing space dropped the narration →
# detector returned None on a valid fork, the exact inert-in-production bug the
# story exists to kill). These pin the helpers the way TestDetector pins
# two_names_one_enemy: pure functions, zero LLM, screen-text only.
# (_narration / _node_text are imported at the top of the module.)
# ═══════════════════════════════════════════════════════════════════════════


class TestNodeText:
    def test_strips_role_prefix(self) -> None:
        assert _node_text("  - paragraph: Molgrath the Eyeless lunges.") == "Molgrath the Eyeless lunges."

    def test_reads_quoted_form(self) -> None:
        assert _node_text('  - text "Molgrath strikes"') == "Molgrath strikes"

    def test_bare_role_node_has_no_text(self) -> None:
        """A role node with no inline text (an element-only `- paragraph:` whose
        prose lives on deeper child lines) must yield NO text — the role token
        must never leak into the narration string. RED before the rework."""
        assert _node_text("- paragraph:") == ""
        assert _node_text("  - list:") == ""


class TestNarration:
    def test_reads_inline_log(self) -> None:
        assert _narration(["- log: Molgrath the Eyeless lunges."]) == "Molgrath the Eyeless lunges."

    def test_reads_nested_log(self) -> None:
        lines = ["- log:", "  - paragraph: Molgrath the Eyeless lunges."]
        assert _narration(lines) == "Molgrath the Eyeless lunges."

    def test_trailing_space_opener_still_reads_nested_prose(self) -> None:
        """A bare `log:` opener that carries a trailing space must NOT be
        mis-read as an inline log with empty text — the nested child prose must
        still be collected. RED before the rework (returned '')."""
        lines = ["- log: ", "  - paragraph: Molgrath the Eyeless lunges."]
        assert _narration(lines) == "Molgrath the Eyeless lunges."

    def test_empty_paragraph_node_leaks_no_role_token(self) -> None:
        """An element-only paragraph (prose on a deeper `- text:` child) must not
        inject the literal 'paragraph:' token into the narration. RED before the
        rework (returned 'paragraph: Molgrath strikes.')."""
        lines = ["- log:", "  - paragraph:", "    - text: Molgrath strikes."]
        assert _narration(lines) == "Molgrath strikes."

    def test_literal_log_in_prose_is_kept_whole(self) -> None:
        """Once inside a log region a child line is prose, so a literal 'log:'
        inside the narrated sentence is never re-parsed as a new node."""
        lines = ["- log:", "  - paragraph: You read the ship log: entry five."]
        assert _narration(lines) == "You read the ship log: entry five."

    def test_two_sequential_log_regions_both_read(self) -> None:
        lines = ["- log:", "  - paragraph: First.", "- log:", "  - paragraph: Second Molgrath."]
        assert _narration(lines) == "First. Second Molgrath."

    def test_no_log_yields_empty(self) -> None:
        assert _narration(["- region \"Enemies\":", "  - listitem: Thief"]) == ""


class TestDetectorNestedRealDom:
    """The end-to-end detector against real-shaped nested aria — the shape the
    live ConfrontationOverlay/NarrationScroll emit."""

    def _snap(self, log_lines: list[str]) -> str:
        return "\n".join(['- region "Enemies":', "  - listitem: Thief", *log_lines])

    def test_flags_fork_with_nested_log(self) -> None:
        hit = two_names_one_enemy(self._snap(["- log:", "  - paragraph: Molgrath the Eyeless lunges."]))
        assert hit is not None and "Molgrath" in hit

    def test_flags_fork_with_trailing_space_log_opener(self) -> None:
        """The silent-fallback the review caught: a trailing space after the
        `log:` opener must not blind the detector to a real fork. RED before the
        rework (detector returned None)."""
        hit = two_names_one_enemy(self._snap(["- log: ", "  - paragraph: Molgrath the Eyeless lunges."]))
        assert hit is not None and "Molgrath" in hit

    def test_consistent_nested_naming_is_clean(self) -> None:
        """A clean panel label ("Thief") that the narration also uses is not a
        fork — guards against the portrait-initial contamination reappearing
        (were the label "T Thief", "The Thief" prose would false-fork)."""
        assert two_names_one_enemy(self._snap(["- log:", "  - paragraph: The Thief lunges from the dark."])) is None
