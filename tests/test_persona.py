import pytest

from understudy.persona.model import Archetype, load_archetype, load_all_archetypes
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
    prompt = build_system_prompt(a)
    # game-agnostic frame: never teaches the game's rules or affordances
    for forbidden in ("SideQuest", "dice tray", "WebSocket", "chargen"):
        assert forbidden not in prompt
    # the archetype's voice is present
    assert a.prompt_fragment.strip().splitlines()[0] in prompt
    # the three intent kinds are explained
    for kind in ("act", "report_confusion", "wait"):
        assert kind in prompt


def test_mechanical_axis_maps_exist():
    assert set(HISTORY_DEPTH) == {"low", "medium", "high"}
    assert set(VERBOSITY_CHAR_CAP) == {"low", "medium", "high"}
    assert HISTORY_DEPTH["low"] < HISTORY_DEPTH["high"]
