import pytest

from understudy.persona.model import load_archetype, load_all_archetypes
from understudy.persona.prompts import HISTORY_DEPTH, VERBOSITY_CHAR_CAP, build_system_prompt


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
        a, world="beneath_sunden", genre="caverns_and_claudes", party_size=1
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
        a, world="flickering_reach", genre="mutant_wasteland", party_size=4
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
        a, world="beneath_sunden", genre="caverns_and_claudes", party_size=1
    )
    assert "Beneath Sunden" in prompt
    assert "just you" in prompt.lower()
    assert "players are sitting down" not in prompt


def test_mechanical_axis_maps_exist():
    assert set(HISTORY_DEPTH) == {"low", "medium", "high"}
    assert set(VERBOSITY_CHAR_CAP) == {"low", "medium", "high"}
    assert HISTORY_DEPTH["low"] < HISTORY_DEPTH["high"]
