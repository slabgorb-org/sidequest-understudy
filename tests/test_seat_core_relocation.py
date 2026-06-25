"""Relocation wiring tests for story 159-6.

Keith decided (2026-06-25) that `seat_core` should live INSIDE
sidequest-understudy as an in-tree package, reversing 159-1's standalone-repo
extraction. These tests assert the END STATE of that move: seat_core importable
in-tree (no `../sidequest-seat-core` uv path dependency), packaged by
understudy's build, with its test modules relocated alongside.

They fail RED until Dev performs the move; they pass GREEN once seat_core lives
under understudy's src/ and its tests are in understudy's suite. The 34 seat_core
*unit* tests travel with the package during GREEN — this file only verifies the
relocation wiring/structure, not seat_core's internal behavior (already covered
by the moved tests).

AC#4 (delete the standalone repo + remove the orchestrator .gitignore entry) is
orchestrator-level cross-repo state and is intentionally NOT asserted here — a
test living in understudy must not depend on being nested inside the orchestrator
checkout. Reviewer verifies AC#4 manually. See the TEA Assessment deviation log.
"""

import tomllib
from pathlib import Path

# tests/<this file> -> parents[1] is the understudy repo root (holds pyproject.toml)
REPO_ROOT = Path(__file__).resolve().parents[1]
PYPROJECT = REPO_ROOT / "pyproject.toml"

# The seat_core test modules that must travel with the package (AC#3).
SEAT_CORE_TEST_MODULES = {
    "test_smoke.py",
    "test_core.py",
    "test_axis.py",
    "test_factory.py",
    "test_anthropic.py",
    "test_ollama.py",
    "test_claude_p.py",
}


def _load_pyproject() -> dict:
    with PYPROJECT.open("rb") as f:
        return tomllib.load(f)


def test_seat_core_importable():
    """AC#1: seat_core is importable from within understudy's environment."""
    import seat_core

    assert seat_core.__doc__, "seat_core must keep its package docstring after relocation"


def test_seat_core_is_in_tree():
    """AC#1/#2: seat_core resolves to a path INSIDE the understudy repo, proving it
    is an in-tree package rather than an external `../sidequest-seat-core` path dep."""
    import seat_core

    pkg_path = Path(seat_core.__file__).resolve()
    assert REPO_ROOT in pkg_path.parents, (
        f"seat_core must live in-tree under {REPO_ROOT}, but resolved to {pkg_path}"
    )


def test_seat_core_public_surface_importable():
    """AC#3: the whole package came across — core, persona.axis, and llm.factory
    all import, not just the top-level package marker."""
    from seat_core.core import DecideResult, Message, ModelError, parse_structured  # noqa: F401
    from seat_core.llm.factory import make_model  # noqa: F401
    from seat_core.persona.axis import Role, RoleDial, SeatAxes  # noqa: F401


def test_pyproject_packages_seat_core_in_tree():
    """AC#1: understudy's wheel build packages seat_core in-tree (src/seat_core)."""
    cfg = _load_pyproject()
    packages = cfg["tool"]["hatch"]["build"]["targets"]["wheel"]["packages"]
    assert "src/seat_core" in packages, (
        f"understudy pyproject must package src/seat_core in-tree; got {packages}"
    )


def test_no_standalone_seat_core_path_dependency():
    """AC#2 (guard): no `../sidequest-seat-core` path/source dependency exists in
    understudy's pyproject. Green from the start — guards against Dev wiring the
    package as an external uv path source instead of moving it in-tree."""
    raw = PYPROJECT.read_text()
    assert "sidequest-seat-core" not in raw, (
        "understudy pyproject must not reference the standalone sidequest-seat-core repo"
    )
    sources = _load_pyproject().get("tool", {}).get("uv", {}).get("sources", {})
    assert "sidequest-seat-core" not in sources and "seat_core" not in sources, (
        f"no uv path source may point at the standalone seat-core repo; got {sources}"
    )


def test_seat_core_tests_relocated():
    """AC#3: the seat_core test modules moved into understudy's tests tree
    (location-tolerant: anywhere under tests/)."""
    tests_root = REPO_ROOT / "tests"
    present = {p.name for p in tests_root.rglob("test_*.py")}
    missing = SEAT_CORE_TEST_MODULES - present
    assert not missing, (
        f"seat_core test modules not relocated into understudy/tests: {sorted(missing)}"
    )
