import pytest

from understudy.manifest import DEFAULT_MODEL, ManifestError, load_manifest


def test_seats_coerce_bare_strings(tmp_path):
    p = tmp_path / "run.yaml"
    p.write_text(
        "name: t\ngenre: g\nworld: w\nsession_url: http://x/play/s\n"
        "seats:\n  - human\n  - mechanics_first\n  - {archetype: hesitant, model: ollama/qwen3:8b}\n"
        "turns: 5\n"
    )
    m = load_manifest(p)
    assert [s.archetype for s in m.seats] == ["human", "mechanics_first", "hesitant"]
    assert m.seats[2].model == "ollama/qwen3:8b"
    # default backend: claude -p (plan-billed via env scrub, see claude_p_model.py)
    assert m.seats[1].model == DEFAULT_MODEL
    assert m.seats[1].model.startswith("claude_p/")


def test_unknown_archetype_in_manifest_fails_loud(tmp_path):
    p = tmp_path / "run.yaml"
    p.write_text(
        "name: t\ngenre: g\nworld: w\nsession_url: http://x/p\nseats: [balrog]\nturns: 2\n"
    )
    with pytest.raises(ManifestError, match="balrog"):
        load_manifest(p)


def test_missing_session_url_fails_loud(tmp_path):
    p = tmp_path / "run.yaml"
    p.write_text("name: t\ngenre: g\nworld: w\nseats: [hesitant]\nturns: 2\n")
    with pytest.raises(ManifestError):
        load_manifest(p)
