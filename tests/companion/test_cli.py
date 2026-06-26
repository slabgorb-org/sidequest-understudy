"""RED (159-5): the companion CLI — Plan C Task 10.

`companion play <def.yaml> [--session URL]` is the operator entry point. It fails
loud (exit code 2) on a missing/invalid manifest BEFORE any socket opens
(lang-review #11: validate at the boundary; SOUL 'No Silent Fallbacks'), and an
explicit --session overrides the manifest's session_url. The network play() is
monkeypatched so the wiring is exercised without a live server.
"""

from __future__ import annotations

from pathlib import Path

from typer.testing import CliRunner

from companion.cli import app

runner = CliRunner()

_DEF = """
name: Donut
species: cat
role: pet
voice: v
axes: {narrative_vs_mechanical: 0.4, verbosity: medium, decisiveness: high, reading_tolerance: medium}
companion_of: alice@home
genre: g
world: w
game_slug: g-slug
session_url: ws://x/ws
"""


def test_play_rejects_missing_manifest(tmp_path: Path):
    result = runner.invoke(app, ["play", str(tmp_path / "nope.yaml")])
    assert result.exit_code == 2
    assert "invalid" in result.output.lower() or "not found" in result.output.lower()


def test_play_session_override_parses(tmp_path: Path, monkeypatch):
    played: dict = {}

    async def _fake_play(defn):
        played["url"] = defn.session_url

    # patch where it is used (companion.cli.play), not where defined — lang-review #6
    monkeypatch.setattr("companion.cli.play", _fake_play)
    p = tmp_path / "d.yaml"
    p.write_text(_DEF)
    result = runner.invoke(app, ["play", str(p), "--session", "ws://override/ws"])
    assert result.exit_code == 0, result.output
    assert played["url"] == "ws://override/ws"


def test_play_uses_manifest_session_when_no_override(tmp_path: Path, monkeypatch):
    played: dict = {}

    async def _fake_play(defn):
        played["url"] = defn.session_url

    monkeypatch.setattr("companion.cli.play", _fake_play)
    p = tmp_path / "d.yaml"
    p.write_text(_DEF)
    result = runner.invoke(app, ["play", str(p)])
    assert result.exit_code == 0, result.output
    assert played["url"] == "ws://x/ws"
