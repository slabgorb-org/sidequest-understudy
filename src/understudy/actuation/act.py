"""Actuation: resolve the bot's NAMED target (role + accessible name, the way
a player refers to it) to a live locator, then do exactly one interaction.

Three outcomes, all meaningful:
- RESOLVED: clean single match — interaction performed.
- AMBIGUOUS: multiple matches — first is used, friction logged. Two controls
  with the same name is itself a legibility finding.
- FAILED: the bot asked for something that is not there. The bot's mental
  model diverged from the page. This is the gold the instrument mines —
  it is NEVER rescued with alias maps or fuzzy heroics (naivety invariant).
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum

from playwright.async_api import Error as PlaywrightError, Page

from understudy.types import Intent


class Resolution(StrEnum):
    RESOLVED = "resolved"
    AMBIGUOUS = "ambiguous"
    FAILED = "failed"


@dataclass(frozen=True)
class ActOutcome:
    resolution: Resolution
    detail: str = ""


async def perform_act(page: Page, intent: Intent, settle_ms: int) -> ActOutcome:
    assert intent.target_role and intent.target_name  # guaranteed by Intent validator
    try:
        loc = page.get_by_role(intent.target_role, name=intent.target_name, exact=False)
        count = await loc.count()
    except PlaywrightError as exc:
        # e.g. the bot invented a non-ARIA role — its mental model diverged
        return ActOutcome(Resolution.FAILED, f"unresolvable target: {exc}")
    if count == 0:
        return ActOutcome(
            Resolution.FAILED,
            f'nothing on the page matches {intent.target_role} "{intent.target_name}"',
        )
    resolution = Resolution.RESOLVED if count == 1 else Resolution.AMBIGUOUS
    target = loc.first
    try:
        if intent.text_input is not None:
            await target.fill(intent.text_input)
        else:
            await target.click()
    except PlaywrightError as exc:
        # found but not operable (disabled, covered, detached mid-action)
        return ActOutcome(Resolution.FAILED, f"target found but not operable: {exc}")
    await page.wait_for_timeout(settle_ms)
    detail = "" if resolution is Resolution.RESOLVED else f"{count} elements matched"
    return ActOutcome(resolution, detail)
