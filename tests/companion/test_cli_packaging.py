"""RED (159-5): packaging wiring for the transport + CLI — Plan C Task 10.

159-5 adds two things to the distribution surface that must be wired, not
half-built: the WebSocket transport needs `websockets` DECLARED and PINNED
(lang-review #12: no unpinned deps), and the CLI must be reachable as a console
entry point (CLAUDE.md 'Wire It Up'). These tests guard both with pure stdlib so
they fail on a clean assertion, not an import error.
"""

from __future__ import annotations

import tomllib
from pathlib import Path

# tests/companion/test_cli_packaging.py -> parents[2] == repo root (sidequest-understudy)
_REPO_ROOT = Path(__file__).resolve().parents[2]
_PYPROJECT = _REPO_ROOT / "pyproject.toml"


def _pyproject() -> dict:
    return tomllib.loads(_PYPROJECT.read_text(encoding="utf-8"))


def test_websockets_dependency_declared_and_pinned():
    deps = _pyproject()["project"]["dependencies"]
    matches = [d for d in deps if d.replace("_", "-").lower().startswith("websockets")]
    assert matches, f"websockets must be a declared dependency (the WS transport needs it): {deps}"
    spec = matches[0]
    # lang-review #12: pinned with a version specifier, not a bare name.
    assert any(c in spec for c in "=<>~!"), f"websockets must be pinned, got: {spec}"


def test_companion_cli_registered_as_console_script():
    scripts = _pyproject()["project"].get("scripts", {})
    assert scripts.get("companion") == "companion.cli:app", (
        f"companion CLI must be wired as a console entry point: {scripts}"
    )
