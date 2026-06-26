"""RED (159-4): packaging + the coupling ruling — wiring test.

The owner's ruling (2026-06-26): the companion is a SIBLING package inside
sidequest-understudy, alongside seat_core and understudy. It imports the in-tree
seat_core PACKAGE directly and MUST NOT depend on the understudy (test-harness)
package — the constraint is honored at the package boundary, not the repo
boundary. These tests structurally enforce that ruling so it can't silently rot.

CLAUDE.md: 'Every Test Suite Needs a Wiring Test' — this is it for 159-4.
"""

from __future__ import annotations

import re
import tomllib
from pathlib import Path

# tests/companion/test_packaging.py -> parents[2] == repo root (sidequest-understudy)
_REPO_ROOT = Path(__file__).resolve().parents[2]
_COMPANION_SRC = _REPO_ROOT / "src" / "companion"
_PYPROJECT = _REPO_ROOT / "pyproject.toml"

_UNDERSTUDY_IMPORT = re.compile(r"^\s*(?:from|import)\s+understudy(?:\.|\s|$)", re.MULTILINE)


def test_companion_package_imports():
    # The package is on the path (scaffold + wheel packaging wired). AC #10.
    import companion  # noqa: F401

    assert companion.__doc__, "companion package should carry a module docstring"


def test_companion_manifest_built_on_seat_core_types():
    # The manifest's axes field IS seat_core's SeatAxes — proves the companion
    # reaches the in-tree seat_core package, not a private copy. AC #11.
    from companion.manifest import CompanionDef
    from seat_core.persona.axis import SeatAxes

    assert CompanionDef.model_fields["axes"].annotation is SeatAxes


def test_companion_source_does_not_import_understudy():
    # The ruling's load-bearing invariant: no companion source file may import
    # the understudy test harness. A violation here means the package boundary
    # was breached.
    assert _COMPANION_SRC.is_dir(), f"companion package not found at {_COMPANION_SRC}"
    offenders = [
        py.relative_to(_REPO_ROOT)
        for py in _COMPANION_SRC.rglob("*.py")
        if _UNDERSTUDY_IMPORT.search(py.read_text(encoding="utf-8"))
    ]
    assert not offenders, f"companion must not import understudy; offenders: {offenders}"


def test_companion_registered_in_wheel_packages():
    # AC #10: companion is built into the distribution wheel alongside the others.
    data = tomllib.loads(_PYPROJECT.read_text(encoding="utf-8"))
    packages = data["tool"]["hatch"]["build"]["targets"]["wheel"]["packages"]
    assert "src/companion" in packages, f"src/companion missing from wheel packages: {packages}"
