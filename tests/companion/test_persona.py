"""RED (159-4): companion voice/role system prompt — Plan C Task 4.

The prompt carries identity + the authored voice, and structurally states the
SOUL.md *Test*: the companion acts ONLY for itself, never narrates others. The
role (pet/peer/hireling) shapes the bond statement.
"""

from pathlib import Path

from companion.manifest import load_companion
from companion.persona import build_system_prompt

_DEF = """
name: Princess Donut
species: cat
role: pet
voice: VAIN AND THEATRICAL.
axes: {narrative_vs_mechanical: 0.4, verbosity: medium, decisiveness: high, reading_tolerance: medium}
companion_of: alice@home
genre: caverns_and_claudes
world: beneath_sunden
session_url: ws://x/ws
"""


def _defn(tmp_path: Path, *, role: str = "pet"):
    p = tmp_path / "d.yaml"
    p.write_text(_DEF.replace("role: pet", f"role: {role}"))
    return load_companion(p)


def test_prompt_carries_identity_and_voice(tmp_path: Path):
    s = build_system_prompt(_defn(tmp_path))
    assert "Princess Donut" in s
    assert "VAIN AND THEATRICAL." in s
    assert "cat" in s


def test_prompt_states_player_not_narrator(tmp_path: Path):
    s = build_system_prompt(_defn(tmp_path)).lower()
    # SOUL.md Test: never act for others. The frame must say so explicitly.
    assert "only your own" in s or "never narrate" in s


def test_prompt_reflects_pet_bond(tmp_path: Path):
    s = build_system_prompt(_defn(tmp_path, role="pet")).lower()
    assert "bonded" in s or "your human" in s


def test_prompt_reflects_hireling_distance(tmp_path: Path):
    # A hireling is NOT privy to its employer's private thoughts — the bond
    # statement differs from the pet's. Guards against a single hardcoded bond.
    s = build_system_prompt(_defn(tmp_path, role="hireling")).lower()
    assert "hireling" in s or "contract" in s
