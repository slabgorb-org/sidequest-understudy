"""Green Room Task 7 final review (Finding 2) — the wrong-Other detector
round-trips through REAL-UI ARIA.

tests/wiring/test_wrong_other_finding.py proves the detector is wired into the
seat loop, but against an IDEALIZED fixture (inline `role="log"` text). The
shipped NarrationScroll emits a much noisier segment mix inside role="log":
player-action echo divs, MULTIPLE <p> per markdown text segment, an <hr>
(aria `- separator`) per NARRATION_END, and turn-status / gallery-notice
chrome. That mix is exactly what made the first implementation fire on a
CORRECT server: the <hr> leaked as a phantom "separator" beat and a window
counted in aria NODES was ~1 paragraph of effective prose depth, while real
narrators name the foe in the turn's OPENING paragraph.

These wiring tests drive the REAL run loop over fixtures that faithfully
reproduce the SHIPPED DOM, both polarities:
  * the named fixture — the seated foe is named in each turn's opening
    paragraph -> NO wrong_other finding. This is the regression gate for the
    node-vs-beat window bug (RED before the fix: the detector flagged a
    correctly-seated, correctly-narrated foe);
  * the wrong-Other fixture — the seated "Resonance Grazer" is never named;
    the prose is all about "Ihnsch of the Rusted Works" -> finding FIRES.

Naivety invariant: the finding is inferred from screen-visible aria only — no
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

WRONG_OTHER_FIXTURE = Path(__file__).parent / "fixture_wrong_other_realdom.html"
NAMED_FIXTURE = Path(__file__).parent / "fixture_wrong_other_named_realdom.html"

# Benign script: act twice so turns resolve and the narration grows, then wait.
# No REPORT_CONFUSION — the bot muddles through silently, so the harness must
# catch (or correctly NOT catch) the mis-seated Other on its own.
_SCRIPT = [
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


async def _run_fixture(fixture: Path, tmp_path) -> list[dict]:
    """Drive the real run loop over `fixture` and return the findings.json list."""
    page_copy = tmp_path / fixture.name
    shutil.copy(fixture, page_copy)
    manifest = RunManifest(
        name=fixture.stem,
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
        model_factory=lambda spec: FakeActionModel(list(_SCRIPT)),
    )
    assert code == 0
    run_dirs = list((tmp_path / "reports").iterdir())
    assert len(run_dirs) == 1
    return json.loads((run_dirs[0] / "findings.json").read_text())


def _wrong_other(findings: list[dict]) -> list[dict]:
    return [
        f for f in findings if any(s["kind"] == SignalKind.WRONG_OTHER.value for s in f["signals"])
    ]


async def test_wrong_other_fires_against_real_ui_dom(tmp_path):
    findings = await _run_fixture(WRONG_OTHER_FIXTURE, tmp_path)
    hits = _wrong_other(findings)
    assert hits, (
        "no wrong-other finding emitted against the SHIPPED-DOM fixture — the "
        "detector is inert against the live NarrationScroll segment mix "
        "(findings.json signals: "
        f"{[s['kind'] for f in findings for s in f['signals']]!r})"
    )
    assert hits[0]["grade"] in {"behavioral", "confirmed"}


async def test_named_foe_does_not_false_fire_against_real_ui_dom(tmp_path):
    """The regression gate for the node-vs-beat window bug: the seated foe IS
    named — in each turn's OPENING paragraph, the realistic narrator shape —
    across the full shipped segment mix (echo + multi-<p> + separators +
    chrome). A window counted in aria nodes (or a phantom `separator` beat)
    pushes that mention out of range and flags a CORRECT server."""
    findings = await _run_fixture(NAMED_FIXTURE, tmp_path)
    hits = _wrong_other(findings)
    assert not hits, (
        "a wrong-other finding was emitted although the seated foe is named in "
        "the current narration turn — the window is being counted in aria "
        "nodes, not narration turns (or chrome/separator nodes are polluting "
        "the prose): "
        f"{[f['signals'] for f in hits]!r}"
    )
