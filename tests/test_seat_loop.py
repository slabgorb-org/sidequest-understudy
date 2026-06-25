# tests/test_seat_loop.py
from understudy.brain.core import FakeActionModel
from understudy.orchestrate.seat import SeatRunner, TokenLedger
from understudy.persona.model import load_archetype
from understudy.types import Intent, IntentKind, SignalKind

FIXTURE = """
<main>
  <div role="log">You stand at the gate.</div>
  <textarea aria-label="Action"></textarea>
  <button onclick="document.querySelector('[role=log]').append(' Done.')">Send</button>
</main>
"""


def _ledger():
    return TokenLedger(ceiling=None)


async def test_seat_runs_script_and_records_transcript(page):
    await page.set_content(FIXTURE)
    script = [
        Intent(
            kind=IntentKind.ACT,
            target_role="textbox",
            target_name="Action",
            text_input="I open the gate",
        ),
        Intent(kind=IntentKind.ACT, target_role="button", target_name="Send"),
        Intent(kind=IntentKind.REPORT_CONFUSION, reason="cannot tell whose turn it is"),
    ]
    runner = SeatRunner(
        seat=1,
        archetype=load_archetype("narrative_first"),
        model=FakeActionModel(script),
        page=page,
        turns=3,
        decide_timeout_s=10.0,
        settle_ms=50,
        ledger=_ledger(),
        deadline=None,
        world="beneath_sunden",
        genre="caverns_and_claudes",
        party_size=1,
        name_theme="mash",
    )
    rows = await runner.run()
    assert len(rows) == 3
    assert rows[0].resolution == "resolved"
    assert rows[1].resolution == "resolved"
    assert "Done." in rows[1].narration_delta
    assert rows[2].intent.kind is IntentKind.REPORT_CONFUSION


async def test_failed_resolution_emits_signal(page):
    await page.set_content(FIXTURE)
    script = [Intent(kind=IntentKind.ACT, target_role="button", target_name="Dice Tray")]
    runner = SeatRunner(
        seat=1,
        archetype=load_archetype("mechanics_first"),
        model=FakeActionModel(script),
        page=page,
        turns=1,
        decide_timeout_s=10.0,
        settle_ms=50,
        ledger=_ledger(),
        deadline=None,
        world="beneath_sunden",
        genre="caverns_and_claudes",
        party_size=1,
        name_theme="mash",
    )
    rows = await runner.run()
    assert rows[0].resolution == "failed"
    assert any(s.kind is SignalKind.RESOLUTION_FAILED for s in rows[0].signals)


async def test_token_ledger_breach_stops_gracefully(page):
    await page.set_content(FIXTURE)

    class CostlyFake(FakeActionModel):
        async def decide(self, system, transcript):
            result = await super().decide(system, transcript)
            return type(result)(value=result.value, input_tokens=600, output_tokens=0)

    runner = SeatRunner(
        seat=1,
        archetype=load_archetype("hesitant"),
        model=CostlyFake([Intent(kind=IntentKind.WAIT)] * 10),
        page=page,
        turns=10,
        decide_timeout_s=10.0,
        settle_ms=10,
        ledger=TokenLedger(ceiling=1000),
        deadline=None,
        world="beneath_sunden",
        genre="caverns_and_claudes",
        party_size=1,
        name_theme="mash",
    )
    rows = await runner.run()
    assert len(rows) < 10  # stopped at the ceiling, partial transcript kept
