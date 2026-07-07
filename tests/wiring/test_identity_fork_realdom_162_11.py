"""Story 162-11 (RED) — the identity-fork detector fires against REAL-UI ARIA.

tests/wiring/test_identity_fork_finding.py already proves the detector is wired
into the seat loop — but against an IDEALIZED fixture (`<section
aria-label="Enemies"><ul><li>Thief</li></ul>`) whose markup the detector's regex
was authored to match. That fixture is a stub: the live ConfrontationOverlay
renders each foe as a portrait chip beside a name span, so Playwright's
aria_snapshot presents the `listitem` with its name on a CHILD line, not inline —
and the narration is a plain scroll div with no `log` role at all. The detector
therefore returns None on every real session (inert in production).

This is the reconciliation wiring test the story requires: drive the REAL run
loop over `fixture_identity_fork_realdom.html`, a faithful reproduction of the
live DOM carrying the 162-11 target ARIA roles, and assert the
two_names_one_enemy finding still surfaces. It exercises the actual
perceive() -> aria_snapshot -> detector path against real-shaped markup.

RED today: the detector's `region "Enemies"` / `listitem` / `log:` parsing was
written for the idealized fixture's inline-text list items; against the real
chip-and-span DOM the label is not extracted and no signal is emitted. GREEN =
the detector (or the UI's role structure) is reconciled so the foe's name is
perceivable and the fork is flagged end-to-end.

Naivety invariant: the fork is inferred from screen-visible aria only — no engine
identity, creature_id, or alias map is available to the bot.
"""

import json
import shutil
from pathlib import Path

from understudy.brain.core import FakeActionModel
from understudy.manifest import RunManifest, SeatSpec
from understudy.orchestrate.run import run_table
from understudy.types import Intent, IntentKind, SignalKind

FIXTURE = Path(__file__).parent / "fixture_identity_fork_realdom.html"


async def test_two_names_one_enemy_fires_against_real_ui_dom(tmp_path):
    page_copy = tmp_path / "identity_fork_realdom.html"
    shutil.copy(FIXTURE, page_copy)

    # Benign script: act twice so turns resolve and the narration grows, then
    # wait. No REPORT_CONFUSION — the bot muddles through silently, so the
    # harness must catch the fork on its own (objective → BEHAVIORAL).
    script = [
        Intent(
            kind=IntentKind.ACT,
            target_role="textbox",
            target_name="Action",
            text_input="I strike the enemy",
        ),
        Intent(kind=IntentKind.ACT, target_role="button", target_name="Send"),
        Intent(kind=IntentKind.WAIT),
        Intent(kind=IntentKind.WAIT),
    ]

    manifest = RunManifest(
        name="identity-fork-realdom",
        genre="fixture",
        world="fixture",
        session_url=page_copy.as_uri(),
        seats=[SeatSpec(archetype="mechanics_first", model="fake")],
        turns=4,
        settle_ms=50,
        capture_spans=False,
    )

    code = await run_table(
        manifest,
        out_root=tmp_path / "reports",
        model_factory=lambda spec: FakeActionModel(list(script)),
    )
    assert code == 0

    run_dirs = list((tmp_path / "reports").iterdir())
    assert len(run_dirs) == 1
    findings = json.loads((run_dirs[0] / "findings.json").read_text())

    two_names = [
        f
        for f in findings
        if any(s["kind"] == SignalKind.TWO_NAMES_ONE_ENEMY.value for s in f["signals"])
    ]
    assert two_names, (
        "no two-names-one-enemy finding emitted against the REAL-UI-shaped DOM — "
        "the detector parses only the idealized fixture's inline listitem/log "
        "markup, so it is inert against the live ConfrontationOverlay/NarrationScroll "
        "(findings.json signals: "
        f"{[s['kind'] for f in findings for s in f['signals']]!r})"
    )
    assert two_names[0]["grade"] in {"behavioral", "confirmed"}
