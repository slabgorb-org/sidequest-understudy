from understudy.actuation.act import Resolution, perform_act
from understudy.types import Intent, IntentKind

FIXTURE = """
<main>
  <h1>Fixture Table</h1>
  <div id="narration" role="log">You stand at the gate.</div>
  <textarea aria-label="Action"></textarea>
  <button onclick="document.getElementById('narration').append(' You did: ' +
    document.querySelector('textarea').value)">Send</button>
  <button>Send</button>
</main>
"""


async def test_fill_resolves_textbox_by_name(page):
    await page.set_content(FIXTURE)
    intent = Intent(kind=IntentKind.ACT, target_role="textbox", target_name="Action",
                    text_input="I open the gate")
    outcome = await perform_act(page, intent, settle_ms=50)
    assert outcome.resolution is Resolution.RESOLVED
    assert await page.locator("textarea").input_value() == "I open the gate"


async def test_duplicate_buttons_are_ambiguous_but_still_clicked(page):
    await page.set_content(FIXTURE)
    intent = Intent(kind=IntentKind.ACT, target_role="button", target_name="Send")
    outcome = await perform_act(page, intent, settle_ms=50)
    assert outcome.resolution is Resolution.AMBIGUOUS  # two Send buttons — real friction


async def test_missing_target_fails_without_crashing(page):
    await page.set_content(FIXTURE)
    intent = Intent(kind=IntentKind.ACT, target_role="button", target_name="Dice Tray")
    outcome = await perform_act(page, intent, settle_ms=50)
    assert outcome.resolution is Resolution.FAILED
    assert "Dice Tray" in outcome.detail


async def test_invalid_role_is_failed_resolution_not_crash(page):
    await page.set_content(FIXTURE)
    intent = Intent(kind=IntentKind.ACT, target_role="clicky thing", target_name="Send")
    outcome = await perform_act(page, intent, settle_ms=50)
    assert outcome.resolution is Resolution.FAILED
