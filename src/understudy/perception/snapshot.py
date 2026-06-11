"""Perception: render the page the way a screen reader presents it.

Playwright's aria_snapshot() yields a YAML-ish structured-text tree of roles,
accessible names, and text. We present it FAITHFULLY — including ambiguous or
unlabeled nodes. No post-processing into a clean menu of clickables:
spoon-feeding affordances would delete the affordance test.
"""

from __future__ import annotations

from playwright.async_api import Page

# Roles a user can operate. Used ONLY for the harness-side
# NO_ACTIONABLE_ELEMENTS stuck-signal — never shown to the brain.
ACTIONABLE_ROLES = frozenset(
    {
        "button", "textbox", "searchbox", "link", "combobox", "checkbox",
        "radio", "slider", "spinbutton", "switch", "tab", "menuitem", "option",
    }
)


def _node_role(line: str) -> str | None:
    s = line.strip()
    if not s.startswith("- "):
        return None
    head = s[2:].split(" ", 1)[0].rstrip(":")
    return head or None


def count_actionable(snapshot: str) -> int:
    """Count operable controls in a snapshot (harness-side signal input)."""
    return sum(1 for line in snapshot.splitlines() if _node_role(line) in ACTIONABLE_ROLES)


def new_lines(before: str, after: str) -> str:
    """Lines present in `after` but not `before` — the narration delta."""
    seen = set(before.splitlines())
    fresh = [ln for ln in after.splitlines() if ln.strip() and ln not in seen]
    return "\n".join(fresh)


async def perceive(page: Page) -> str:
    """The ONLY thing the brain ever receives about the game."""
    title = await page.title()
    tree = await page.locator("body").aria_snapshot()
    return f"# Page: {title}\n{tree}"
