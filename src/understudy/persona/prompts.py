"""System-prompt assembly + the mechanical axis maps.

The frame is deliberately GAME-AGNOSTIC: it never teaches the game's rules,
names its controls, or enumerates valid actions. Doing so would delete the
affordance test (the naivety invariant).
"""

from __future__ import annotations

from understudy.persona.model import Archetype

# reading_tolerance → how many transcript messages replay into context each turn
# (also the token-cost knob for local models)
HISTORY_DEPTH: dict[str, int] = {"low": 4, "medium": 8, "high": 16}

# verbosity → hard cap on typed-action length (the "playtest actions stay
# short" rule, enforced mechanically by truncation at the cap)
VERBOSITY_CHAR_CAP: dict[str, int] = {"low": 160, "medium": 300, "high": 450}

# decisiveness → seconds a waiting bot sleeps before re-perceiving
WAIT_POLL_SECONDS: dict[str, float] = {"low": 8.0, "medium": 5.0, "high": 2.0}

_FRAME = """\
You are a person playing an online multiplayer tabletop-style game you have
never seen before. Each turn you are shown what is currently on your screen,
described the way a screen reader would describe it. Decide what you, as a
player, do next.

You respond with exactly one intent:
- act: interact with ONE thing on the screen. Name it the way you would say
  it aloud (its role and its label, e.g. the "Send" button, the text box
  labeled "Action"). To type, include the text. One interaction at a time:
  type into a field, OR click a control — never both at once.
- report_confusion: if you cannot work out what to do, or the screen does
  not make sense to you, say why. This is always allowed and never wrong.
- wait: if you believe it is not your turn, or the game seems busy.

Stay in character as the player described below. Never narrate other
players' actions. Never invent controls you cannot see.
"""

_LEAN = {
    "low": "You lean heavily toward story and prose over rules and numbers.",
    "medium": "You balance story and mechanics evenly.",
    "high": "You lean heavily toward rules, numbers, and how the system works.",
}


def _lean_bucket(x: float) -> str:
    return "low" if x < 0.34 else ("high" if x > 0.66 else "medium")


def _humanize(slug: str) -> str:
    """'flickering_reach' → 'Flickering Reach' — the way a friend says it."""
    return slug.replace("_", " ").title()


def _table_contract(world: str, genre: str, party_size: int) -> str:
    """The social contract of game night: who's coming and what was agreed.
    Intent only — never names a control (the naivety invariant holds)."""
    world_name, genre_name = _humanize(world), _humanize(genre)
    if party_size > 1:
        company = (
            f"You arranged this game with friends: {party_size} players are "
            "sitting down together tonight, and all of you must end up in the "
            "SAME shared multiplayer session. If you find yourself heading "
            "into a game alone, something has gone wrong — look for a way to "
            "play together, and report confusion if you cannot find one."
        )
    else:
        company = "It is just you and the narrator tonight — a game of your own is correct."
    return "\n".join(
        [
            "## Tonight's table",
            company,
            f'The group agreed on the world called "{world_name}" (a {genre_name} '
            "game). Find that exact world and choose it — not a different one, "
            "however tempting it looks.",
        ]
    )


def build_system_prompt(arch: Archetype, *, world: str, genre: str, party_size: int) -> str:
    cap = VERBOSITY_CHAR_CAP[arch.verbosity]
    return "\n".join(
        [
            _FRAME,
            _table_contract(world, genre, party_size),
            "## Who you are as a player",
            arch.prompt_fragment.strip(),
            _LEAN[_lean_bucket(arch.narrative_vs_mechanical)],
            f"Keep anything you type under {cap} characters — short, like a real "
            "player at a table, not an author.",
        ]
    )
