"""Green Room Task 7 — the wrong-Other hunt is wired end-to-end.

The unit tests (tests/test_wrong_other.py) prove the pure detector and its
grading in isolation. This is the WIRING test the story requires (understudy
CLAUDE.md "No half-wired features"): drive the REAL run loop over a fixture
whose Enemies panel seats an opponent the narration never mentions, and assert
the finding surfaces in findings.json — proof `wrong_other` is actually called
inside the per-turn seat loop, not merely defined.

Naivety invariant: the finding is inferred from screen-visible text only —
the fixture is a plain HTML page (an Enemies panel naming "Resonance Grazer",
a narration log naming "Ihnsch of the Rusted Works" and only ever that). No
engine identity, creature_id, or green_room.materialized span is available to
the bot.
"""

import json
import shutil
from pathlib import Path

from understudy.brain.core import FakeActionModel
from understudy.manifest import RunManifest, SeatSpec
from understudy.orchestrate.run import run_table
from understudy.types import Intent, IntentKind, SignalKind

FIXTURE = Path(__file__).parent / "fixture_wrong_other.html"


async def test_wrong_other_surfaces_in_findings(tmp_path):
    page_copy = tmp_path / "wrong_other.html"
    shutil.copy(FIXTURE, page_copy)

    # A benign script: act a couple of times (so turns resolve and the
    # narration grows), then wait. No REPORT_CONFUSION — the bot muddles
    # through silently, so the harness must catch the mis-seated Other on its
    # own (objective -> BEHAVIORAL).
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
        name="wrong-other",
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

    wrong_other = [
        f for f in findings if any(s["kind"] == SignalKind.WRONG_OTHER.value for s in f["signals"])
    ]
    assert wrong_other, (
        "no wrong-other finding emitted — the detector is not wired into the "
        "per-turn seat loop (findings.json signals: "
        f"{[s['kind'] for f in findings for s in f['signals']]!r})"
    )
    # The bot never complained, so the mis-seated Other lands as an
    # objective-only finding.
    assert wrong_other[0]["grade"] in {"behavioral", "confirmed"}
