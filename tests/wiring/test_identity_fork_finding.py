"""Story 162-7 (RED) — the identity-split hunt is wired end-to-end.

The unit tests (tests/test_two_names_one_enemy.py) prove the pure detector and
the grading in isolation. This is the WIRING test the story requires (understudy
CLAUDE.md "No half-wired features"): drive the REAL run loop over a fixture whose
screen-visible narration names one enemy two ways, and assert the finding
surfaces in findings.json — proof the detector is actually called inside the
per-turn seat loop, not merely defined.

RED today: the detector and its ``SignalKind.TWO_NAMES_ONE_ENEMY`` do not exist,
and nothing in ``SeatRunner.run`` scans narration for the fork, so no such signal
is ever emitted. GREEN = the detector exists AND is wired into the loop.

Naivety invariant: the fork is inferred from screen-visible text only — the
fixture is a plain HTML page (an enemy panel labelled "Thief", a narration log
naming "Molgrath the Eyeless"). No engine identity is available to the bot.
"""

import json
import shutil
from pathlib import Path

from understudy.brain.core import FakeActionModel
from understudy.manifest import RunManifest, SeatSpec
from understudy.orchestrate.run import run_table
from understudy.types import Intent, IntentKind, SignalKind

FIXTURE = Path(__file__).parent / "fixture_identity_fork.html"


async def test_two_names_one_enemy_surfaces_in_findings(tmp_path):
    page_copy = tmp_path / "identity_fork.html"
    shutil.copy(FIXTURE, page_copy)

    # A benign script: act a couple of times (so turns resolve and the narration
    # grows), then wait. No REPORT_CONFUSION — the bot muddles through silently,
    # so the harness must catch the fork on its own (objective → BEHAVIORAL).
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
        name="identity-fork",
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
        "no two-names-one-enemy finding emitted — the detector is not wired into "
        "the per-turn seat loop (findings.json signals: "
        f"{[s['kind'] for f in findings for s in f['signals']]!r})"
    )
    # The bot never complained, so the fork lands as an objective-only finding.
    assert two_names[0]["grade"] in {"behavioral", "confirmed"}
