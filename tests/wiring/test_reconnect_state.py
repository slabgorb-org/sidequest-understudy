import shutil
from pathlib import Path

from understudy.brain.core import FakeActionModel
from understudy.manifest import RunManifest, SeatSpec
from understudy.orchestrate.run import run_table
from understudy.types import Intent, IntentKind

FIXTURE = Path(__file__).parent / "fixture_table.html"


async def test_run_saves_browser_state_for_bot_seats_only(tmp_path):
    page_copy = tmp_path / "table.html"
    shutil.copy(FIXTURE, page_copy)

    # one quick resolving act so the seat loop runs and exits fast
    script = [
        Intent(
            kind=IntentKind.ACT,
            target_role="textbox",
            target_name="Action",
            text_input="hi",
        )
    ]

    manifest = RunManifest(
        name="statesave",
        genre="fixture",
        world="fixture",
        session_url=page_copy.as_uri(),
        seats=[
            SeatSpec(archetype="mechanics_first", model="fake"),  # seat 1 (bot)
            SeatSpec(archetype="human"),                          # seat 2 (not driven)
        ],
        turns=1,
        settle_ms=50,
        capture_spans=False,
    )

    code = await run_table(
        manifest,
        out_root=tmp_path / "reports",
        model_factory=lambda spec: FakeActionModel(list(script)),
    )
    assert code == 0

    out = next((tmp_path / "reports").iterdir())
    assert (out / "state" / "seat-1.json").exists()       # bot seat persisted
    assert not (out / "state" / "seat-2.json").exists()   # human seat skipped
