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

# A real player walks up to chargen with a name already in their head; a naive
# LLM does not. Faced with an empty free-text field it free-associates from its
# own prior and types the same pet name — "Kael" — letter by letter, on every
# seat independently. It is not reading a default off the screen; the bias is in
# the model. The collision that follows is not cosmetic: the engine keys a
# seated character by NAME (snapshot.player_seats values, character_locations),
# so two same-named PCs in one session collapse onto a single name slot.
#
# We hand each seat a name drawn from a single THEME SET, indexed by its 1-based
# seat number: distinct within a table (no collision) AND a coherent recognizable
# cast, so a test save reads at a glance as "the M*A*S*H table" rather than a
# pile of anonymous PCs. The rosters are harvested from the Pennyfarthing persona
# theme files; they are baked in rather than read at runtime so understudy keeps
# no live filesystem dependency on a sibling repo. A name is content the player
# brings — not a control, rule, or affordance — so the naivety invariant holds.
THEME_SETS: dict[str, tuple[str, ...]] = {
    "mash": (
        "Hawkeye",
        "Potter",
        "Radar",
        "Winchester",
        "Margaret",
        "Mulcahy",
        "Klinger",
        "Sidney",
        "Frank",
    ),
    "princess_bride": (
        "Inigo",
        "Fezzik",
        "Vizzini",
        "Westley",
        "Buttercup",
        "Humperdinck",
        "Max",
        "Grandfather",
    ),
    "lord_of_the_rings": (
        "Aragorn",
        "Gandalf",
        "Legolas",
        "Gimli",
        "Frodo",
        "Sam",
        "Pippin",
        "Bilbo",
        "Elrond",
        "Gollum",
        "Boromir",
        "Saruman",
    ),
    "discworld": (
        "Vetinari",
        "Carrot",
        "Granny",
        "Moist",
        "Ponder",
        "Igor",
        "Leonard",
        "Sacharissa",
        "Adora",
        "Lu-Tze",
        "DEATH",
    ),
    "star_trek_tng": (
        "Picard",
        "Data",
        "Geordi",
        "Worf",
        "Beverly",
        "Deanna",
        "Miles",
        "Spock",
        "Q",
    ),
    "the_expanse": (
        "Holden",
        "Naomi",
        "Amos",
        "Alex",
        "Drummer",
        "Avasarala",
        "Investigator",
    ),
    "firefly": (
        "Malcolm",
        "Zoe",
        "Jayne",
        "Kaylee",
        "River",
        "Simon",
        "Inara",
        "Hoban",
        "Book",
    ),
}

DEFAULT_NAME_THEME = "mash"


def name_for_seat(seat: int, *, theme: str = DEFAULT_NAME_THEME) -> str:
    """The character name the player at this 1-based seat already has in mind.

    Drawn from ``theme``'s roster and distinct per seat for any table no larger
    than that roster (every bundled set holds >= 7 names), so two bots never
    choose the same name — which the engine, keying characters by name, cannot
    disambiguate. Unknown ``theme`` fails loud: no silent fallback to a default.
    """
    if seat < 1:
        raise ValueError(f"seat is 1-based; got {seat!r}")
    try:
        roster = THEME_SETS[theme]
    except KeyError:
        raise ValueError(
            f"unknown name theme {theme!r}; known: {sorted(THEME_SETS)}"
        ) from None
    return roster[(seat - 1) % len(roster)]

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


def _your_character(player_name: str) -> str:
    """The name the player already has in mind. Intent, not interface: it never
    names the chargen control, only what the player would type when they meet it."""
    return "\n".join(
        [
            "## Your character",
            f'You already have a name in mind for your character: "{player_name}". '
            "When the game asks you to name or create your character, use that "
            "name. It is yours — do not borrow a name the game suggests to you, "
            "and do not settle for a generic default.",
        ]
    )


def build_system_prompt(
    arch: Archetype, *, world: str, genre: str, party_size: int, player_name: str
) -> str:
    cap = VERBOSITY_CHAR_CAP[arch.verbosity]
    return "\n".join(
        [
            _FRAME,
            _table_contract(world, genre, party_size),
            _your_character(player_name),
            "## Who you are as a player",
            arch.prompt_fragment.strip(),
            _LEAN[_lean_bucket(arch.narrative_vs_mechanical)],
            f"Keep anything you type under {cap} characters — short, like a real "
            "player at a table, not an author.",
        ]
    )
