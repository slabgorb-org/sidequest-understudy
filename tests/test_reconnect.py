from pathlib import Path

import pytest

from understudy.manifest import ManifestError
from understudy.orchestrate.reconnect import (
    reconnect_context_kwargs,
    seat_state_path,
    validate_reconnect_dir,
)


def test_seat_state_path_uses_state_subdir():
    d = Path("reports/2026-06-12-demo-r1")
    assert seat_state_path(d, 1) == d / "state" / "seat-1.json"
    assert seat_state_path(d, 3) == d / "state" / "seat-3.json"


def test_context_kwargs_empty_when_not_reconnecting():
    assert reconnect_context_kwargs(None, 1) == {}


def test_context_kwargs_carry_storage_state_path():
    d = Path("reports/run1")
    assert reconnect_context_kwargs(d, 2) == {
        "storage_state": str(d / "state" / "seat-2.json")
    }


def test_validate_raises_when_dir_missing(tmp_path):
    with pytest.raises(ManifestError, match="does not exist"):
        validate_reconnect_dir(tmp_path / "ghost", [1])


def test_validate_raises_when_state_subdir_missing(tmp_path):
    with pytest.raises(ManifestError, match="no state/"):
        validate_reconnect_dir(tmp_path, [1])


def test_validate_names_the_missing_seat(tmp_path):
    (tmp_path / "state").mkdir()
    (tmp_path / "state" / "seat-1.json").write_text("{}")
    with pytest.raises(ManifestError, match="seat 2"):
        validate_reconnect_dir(tmp_path, [1, 2])


def test_validate_passes_when_all_seat_files_present(tmp_path):
    (tmp_path / "state").mkdir()
    (tmp_path / "state" / "seat-1.json").write_text("{}")
    validate_reconnect_dir(tmp_path, [1])  # no raise


from understudy.manifest import RunManifest, SeatSpec
from understudy.orchestrate.run import run_table


async def test_run_table_reconnect_missing_seat_raises_before_launch(tmp_path):
    rc = tmp_path / "rc"
    (rc / "state").mkdir(parents=True)  # state/ exists but no seat-1.json
    manifest = RunManifest(
        name="x",
        genre="g",
        world="w",
        session_url="http://x",
        seats=[SeatSpec(archetype="mechanics_first", model="fake")],
        capture_spans=False,
    )
    with pytest.raises(ManifestError, match="seat 1"):
        await run_table(manifest, out_root=tmp_path / "reports", reconnect=rc)
