import pytest

from understudy.persona.model import load_archetype, load_all_archetypes
from understudy.persona.prompts import (
    DEFAULT_NAME_THEME,
    HISTORY_DEPTH,
    THEME_SETS,
    VERBOSITY_CHAR_CAP,
    _your_character,
    build_system_prompt,
    name_for_seat,
)


def test_four_starting_archetypes_load():
    all_ = load_all_archetypes()
    assert set(all_) == {"narrative_first", "mechanics_first", "hesitant", "engaged_generalist"}


def test_axes_are_validated():
    a = load_archetype("mechanics_first")
    assert 0.0 <= a.narrative_vs_mechanical <= 1.0
    assert a.narrative_vs_mechanical > 0.5  # mechanics_first leans crunch
    assert a.verbosity in ("low", "medium", "high")


def test_unknown_archetype_fails_loud():
    with pytest.raises(FileNotFoundError):
        load_archetype("min_maxer_3000")


def test_system_prompt_is_game_agnostic_and_in_persona():
    a = load_archetype("hesitant")
    prompt = build_system_prompt(
        a, world="beneath_sunden", genre="caverns_and_claudes", party_size=1, player_name="Bram"
    )
    # game-agnostic frame: never teaches the game's rules or affordances
    for forbidden in ("SideQuest", "dice tray", "WebSocket", "chargen"):
        assert forbidden not in prompt
    # the archetype's voice is present
    assert a.prompt_fragment.strip().splitlines()[0] in prompt
    # the three intent kinds are explained
    for kind in ("act", "report_confusion", "wait"):
        assert kind in prompt


def test_multiplayer_table_contract_in_prompt():
    """A table of N>1 knows it sits down TOGETHER: the agreed world, the head
    count, and the shared-session intent — stated as social contract, never as
    UI instructions (the naivety invariant)."""
    a = load_archetype("engaged_generalist")
    prompt = build_system_prompt(
        a, world="flickering_reach", genre="mutant_wasteland", party_size=4, player_name="Nadia"
    )
    assert "Flickering Reach" in prompt  # humanized, the way a friend says it
    assert "Mutant Wasteland" in prompt
    assert "4 players" in prompt
    assert "same" in prompt.lower() and "multiplayer" in prompt.lower()
    # intent, not instructions: no control names, no UI nouns
    for forbidden in ("Game mode", "radiogroup", "radio ", "Start Adventure", "checked"):
        assert forbidden not in prompt


def test_solo_table_contract_in_prompt():
    """One seat = a solo game IS correct; the prompt must not push a lone bot
    to hunt for a shared session."""
    a = load_archetype("hesitant")
    prompt = build_system_prompt(
        a, world="beneath_sunden", genre="caverns_and_claudes", party_size=1, player_name="Otto"
    )
    assert "Beneath Sunden" in prompt
    assert "just you" in prompt.lower()
    assert "players are sitting down" not in prompt


def test_seat_names_are_distinct_per_seat():
    """Two bots at one table must never arrive with the same character name —
    the engine keys seated characters by name and cannot disambiguate a clash."""
    names = [name_for_seat(s) for s in range(1, 5)]
    assert len(set(names)) == len(names)
    # and not the pet name the model free-types that prompted this fix
    assert "Kael" not in names


def test_default_theme_is_mash_and_draws_its_cast():
    assert DEFAULT_NAME_THEME == "mash"
    table = [name_for_seat(s) for s in range(1, 5)]
    assert set(table) <= set(THEME_SETS["mash"])
    assert "Hawkeye" in THEME_SETS["mash"]


def test_a_table_draws_one_coherent_named_cast():
    """A whole table from one theme reads as that cast — the save is legible."""
    crew = [name_for_seat(s, theme="firefly") for s in range(1, 5)]
    assert len(set(crew)) == len(crew)
    assert set(crew) <= set(THEME_SETS["firefly"])


def test_every_bundled_theme_seats_a_real_table():
    """Each set must hold enough distinct names for a normal table (>= 7)."""
    for theme, roster in THEME_SETS.items():
        assert len(roster) >= 7, theme
        assert len(set(roster)) == len(roster), f"{theme} has a duplicate name"


def test_unknown_theme_fails_loud():
    with pytest.raises(ValueError):
        name_for_seat(1, theme="downton_abbey")


def test_seat_is_one_based_and_fails_loud_below_one():
    with pytest.raises(ValueError):
        name_for_seat(0)


def test_player_brings_their_own_name_to_chargen():
    """The seat's name rides in the prompt as the player's own pre-decided
    choice, with an explicit push away from generic defaults (the Kael trap) —
    stated as intent, never naming the chargen control (naivety invariant)."""
    a = load_archetype("engaged_generalist")
    prompt = build_system_prompt(
        a, world="beneath_sunden", genre="caverns_and_claudes", party_size=2, player_name="Cassia"
    )
    assert "Cassia" in prompt
    assert "generic default" in prompt
    # the name section itself stays intent-only — it must not name the chargen
    # control (the frame elsewhere legitimately says "text box", so scope the
    # leak check to the section under test)
    section = _your_character("Cassia")
    for forbidden in ("text box", "field labeled", "Create Character", "button"):
        assert forbidden not in section


def test_mechanical_axis_maps_exist():
    assert set(HISTORY_DEPTH) == {"low", "medium", "high"}
    assert set(VERBOSITY_CHAR_CAP) == {"low", "medium", "high"}
    assert HISTORY_DEPTH["low"] < HISTORY_DEPTH["high"]
