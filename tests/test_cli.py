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
