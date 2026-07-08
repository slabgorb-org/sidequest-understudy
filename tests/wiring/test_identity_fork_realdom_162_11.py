"""Story 162-11 — the identity-fork detector round-trips through REAL-UI ARIA.

tests/wiring/test_identity_fork_finding.py proves the detector is wired into the
seat loop, but against an IDEALIZED fixture (`<section
aria-label="Enemies"><ul><li>Thief</li></ul>`) whose inline markup the detector's
regex was first authored to match. The live ConfrontationOverlay renders each foe
as a portrait chip beside a name span, so Playwright's aria_snapshot presents the
`listitem` name on a CHILD line and the narration nested under `role="log"` — a
shape the original detector could not read, so it returned None on every real
session (inert in production).

These wiring tests drive the REAL run loop over fixtures that faithfully
reproduce the SHIPPED DOM (aria-hidden decorative portrait + role="listitem" +
role="log" narration), exercising the actual perceive() -> aria_snapshot ->
detector path over the CLEAN `listitem: Thief` the fixed component emits:
  * the fork fixture — panel "Thief", narration "Molgrath the Eyeless" -> FIRES;
  * the consistent fixture — panel and narration both "the Thief" -> does NOT
    fire. This is the fixture-fidelity guard: if the fixture ever drifts back to
    a non-aria-hidden portrait (`listitem: T Thief`), the consistent case
    false-forks and this test fails loudly.

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

FORK_FIXTURE = Path(__file__).parent / "fixture_identity_fork_realdom.html"
CONSISTENT_FIXTURE = Path(__file__).parent / "fixture_identity_consistent_realdom.html"

# Benign script: act twice so turns resolve and the narration grows, then wait.
# No REPORT_CONFUSION — the bot muddles through silently, so the harness must
# catch (or correctly NOT catch) the fork on its own.
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


def _two_names(findings: list[dict]) -> list[dict]:
    return [
        f
        for f in findings
        if any(s["kind"] == SignalKind.TWO_NAMES_ONE_ENEMY.value for s in f["signals"])
    ]


async def test_two_names_one_enemy_fires_against_real_ui_dom(tmp_path):
    findings = await _run_fixture(FORK_FIXTURE, tmp_path)
    two_names = _two_names(findings)
    assert two_names, (
        "no two-names-one-enemy finding emitted against the SHIPPED-DOM fixture — "
        "the detector is inert against the live ConfrontationOverlay/NarrationScroll "
        "(findings.json signals: "
        f"{[s['kind'] for f in findings for s in f['signals']]!r})"
    )
    assert two_names[0]["grade"] in {"behavioral", "confirmed"}


async def test_consistent_naming_does_not_false_fork(tmp_path):
    """Fixture-fidelity guard: the shipped DOM emits a CLEAN `listitem: Thief`
    (aria-hidden portrait), so consistent panel+narration naming must produce NO
    fork. If the fixture drifts back to a bare portrait (`listitem: T Thief`),
    "the Thief" prose false-forks and this assertion fails."""
    findings = await _run_fixture(CONSISTENT_FIXTURE, tmp_path)
    two_names = _two_names(findings)
    assert not two_names, (
        "a two-names-one-enemy finding was emitted for CONSISTENT naming — the "
        "fixture's portrait initial is contaminating the perceived foe name "
        "(the aria-hidden fidelity guard has drifted): "
        f"{[f['signals'] for f in two_names]!r}"
    )
