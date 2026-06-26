"""RED (159-4): CompanionDef manifest loader — Plan C Task 3.

Authored YAML declares who the companion is, whom it's bonded to, where it
plays, and how it thinks. Every malformed input fails LOUD (ManifestError)
before any socket opens — No Silent Fallbacks (SOUL.md / understudy CLAUDE.md).
The loader must use yaml.safe_load (lang-review #8: never unsafe-deserialize).
"""

from pathlib import Path

import pytest

from companion.manifest import CompanionDef, ManifestError, load_companion
from seat_core.persona.axis import Role

_VALID = """
name: Princess Donut
species: cat
role: pet
voice: |
  Vain, theatrical, ALL-CAPS when affronted; ferociously loyal underneath.
axes:
  narrative_vs_mechanical: 0.4
  verbosity: medium
  decisiveness: high
  reading_tolerance: medium
companion_of: alice@home
genre: caverns_and_claudes
world: beneath_sunden
session_url: ws://player2.local:8765/ws
"""


def test_load_valid(tmp_path: Path):
    p = tmp_path / "donut.yaml"
    p.write_text(_VALID)
    d = load_companion(p)
    assert isinstance(d, CompanionDef)
    assert d.role is Role.PET
    assert d.companion_of == "alice@home"
    assert d.model == "anthropic/claude-haiku-4-5-20251001"  # default
    assert d.decide_timeout_s == 30.0  # default — bounds the decide step


def test_missing_file_fails_loud(tmp_path: Path):
    with pytest.raises(ManifestError, match="not found"):
        load_companion(tmp_path / "nope.yaml")


def test_unknown_role_fails_loud(tmp_path: Path):
    p = tmp_path / "bad.yaml"
    p.write_text(_VALID.replace("role: pet", "role: overlord"))
    with pytest.raises(ManifestError):
        load_companion(p)


def test_missing_field_fails_loud(tmp_path: Path):
    p = tmp_path / "bad.yaml"
    p.write_text(_VALID.replace("companion_of: alice@home\n", ""))
    with pytest.raises(ManifestError):
        load_companion(p)


def test_malformed_yaml_fails_loud(tmp_path: Path):
    # Unterminated flow sequence — yaml raises; loader must wrap as ManifestError,
    # never crash raw or swallow (lang-review #8 / No Silent Fallbacks).
    p = tmp_path / "bad.yaml"
    p.write_text("name: [unterminated\n")
    with pytest.raises(ManifestError):
        load_companion(p)


def test_manifest_uses_safe_load_rejects_python_tags(tmp_path: Path):
    # A !!python/object tag would execute under yaml.load() but is rejected by
    # yaml.safe_load(). This proves the loader is safe (lang-review #8, CWE-502).
    p = tmp_path / "evil.yaml"
    p.write_text("!!python/object/apply:os.system ['echo pwned']\n")
    with pytest.raises(ManifestError):
        load_companion(p)
