from pathlib import Path

from typer.testing import CliRunner

from understudy.cli import app

runner = CliRunner()


def test_invalid_manifest_exits_2(tmp_path):
    bad = tmp_path / "bad.yaml"
    bad.write_text("name: x\n")  # missing required fields
    result = runner.invoke(app, ["run", str(bad)])
    assert result.exit_code == 2
    assert "invalid manifest" in result.output


def test_missing_manifest_exits_2(tmp_path):
    result = runner.invoke(app, ["run", str(tmp_path / "ghost.yaml")])
    assert result.exit_code == 2


def test_turns_flag_overrides_manifest(tmp_path, monkeypatch):
    good = tmp_path / "ok.yaml"
    good.write_text(
        "name: t\ngenre: g\nworld: w\nsession_url: http://x\nseats: [hesitant]\nturns: 5\n"
    )
    captured = {}

    async def fake_run_table(m, *, headed, out_root, reconnect):
        captured["turns"] = m.turns
        return 0

    monkeypatch.setattr("understudy.cli.run_table", fake_run_table)
    result = runner.invoke(app, ["run", str(good), "--turns", "33"])
    assert result.exit_code == 0
    assert captured["turns"] == 33


def test_no_turns_flag_keeps_manifest_value(tmp_path, monkeypatch):
    good = tmp_path / "ok.yaml"
    good.write_text(
        "name: t\ngenre: g\nworld: w\nsession_url: http://x\nseats: [hesitant]\nturns: 5\n"
    )
    captured = {}

    async def fake_run_table(m, *, headed, out_root, reconnect):
        captured["turns"] = m.turns
        return 0

    monkeypatch.setattr("understudy.cli.run_table", fake_run_table)
    result = runner.invoke(app, ["run", str(good)])
    assert result.exit_code == 0
    assert captured["turns"] == 5


def test_reconnect_flag_threaded_to_run_table(tmp_path, monkeypatch):
    good = tmp_path / "ok.yaml"
    good.write_text(
        "name: t\ngenre: g\nworld: w\nsession_url: http://x\nseats: [hesitant]\n"
    )
    captured = {}

    async def fake_run_table(m, *, headed, out_root, reconnect):
        captured["reconnect"] = reconnect
        return 0

    monkeypatch.setattr("understudy.cli.run_table", fake_run_table)
    result = runner.invoke(app, ["run", str(good), "--reconnect", "reports/prev"])
    assert result.exit_code == 0
    assert captured["reconnect"] == Path("reports/prev")
