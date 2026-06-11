import json
import shutil
from pathlib import Path

from understudy.brain.core import FakeActionModel
from understudy.manifest import RunManifest, SeatSpec
from understudy.orchestrate.run import run_table
from understudy.types import Grade, Intent, IntentKind

FIXTURE = Path(__file__).parent / "fixture_table.html"


async def test_full_loop_produces_graded_report(tmp_path):
    page_copy = tmp_path / "table.html"
    shutil.copy(FIXTURE, page_copy)

    script = [
        Intent(
            kind=IntentKind.ACT,
            target_role="textbox",
            target_name="Action",
            text_input="I open the gate",
        ),
        Intent(kind=IntentKind.ACT, target_role="button", target_name="Send"),
        Intent(kind=IntentKind.ACT, target_role="button", target_name="Dice Tray"),
        Intent(
            kind=IntentKind.REPORT_CONFUSION,
            reason="I expected a way to roll dice and cannot find one",
        ),
    ]

    manifest = RunManifest(
        name="wiring",
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
    out = run_dirs[0]

    transcript = [
        json.loads(line) for line in (out / "transcript" / "seat-1.jsonl").read_text().splitlines()
    ]
    assert len(transcript) == 4
    assert transcript[0]["resolution"] == "resolved"  # typed into Action
    assert transcript[1]["resolution"] == "resolved"  # clicked Send
    assert "I open the gate" in transcript[1]["narration_delta"]
    assert transcript[2]["resolution"] == "failed"  # Dice Tray isn't there

    findings = json.loads((out / "findings.json").read_text())
    grades = {f["grade"] for f in findings}
    # confusion at turn 4 sits within ±1 of the failed resolve at turn 3 → CONFIRMED
    assert Grade.CONFIRMED.value in grades

    md = (out / "report.md").read_text()
    assert "mechanics_first" in md and "confirmed" in md.lower()
