"""Browser-state reconnect helpers.

Persisting a bot seat's localStorage lets a later run rejoin its character past
chargen — the same way a returning player's browser would. These are the pure
path/kwargs/validation helpers; the live save/restore calls live in run.py. The
``state/seat-{idx}.json`` convention lives here and nowhere else.
"""

from __future__ import annotations

from pathlib import Path

from understudy.manifest import ManifestError


def seat_state_path(report_dir: Path, idx: int) -> Path:
    """The storage_state file for seat ``idx`` under a run's report dir."""
    return report_dir / "state" / f"seat-{idx}.json"


def reconnect_context_kwargs(reconnect: Path | None, idx: int) -> dict:
    """kwargs for ``browser.new_context()``.

    Restores seat ``idx``'s saved state when reconnecting, empty otherwise. This
    is the seam the wiring asserts on: exactly what ``new_context`` receives.
    """
    if reconnect is None:
        return {}
    return {"storage_state": str(seat_state_path(reconnect, idx))}


def validate_reconnect_dir(reconnect: Path, bot_seat_indices: list[int]) -> None:
    """Fail loud before any browser launches.

    The dir, its ``state/`` subdir, and a ``seat-{idx}.json`` for every bot seat
    must all exist. No silent fall-through to chargen (No Silent Fallbacks).
    Raises ManifestError (usage class — CLI maps it to exit 2).
    """
    if not reconnect.exists():
        raise ManifestError(f"--reconnect dir does not exist: {reconnect}")
    if not (reconnect / "state").is_dir():
        raise ManifestError(f"--reconnect dir has no state/ subdir: {reconnect}")
    for idx in bot_seat_indices:
        p = seat_state_path(reconnect, idx)
        if not p.is_file():
            raise ManifestError(
                f"--reconnect: missing browser state for seat {idx}: {p}"
            )
