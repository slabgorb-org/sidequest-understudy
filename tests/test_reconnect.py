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
