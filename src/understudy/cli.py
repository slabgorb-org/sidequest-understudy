"""Understudy CLI.

Exit codes (mirrors scripts/playtest.py conventions):
  0 — run completed, report written, spans captured (or capture disabled)
  1 — run completed but span capture failed (partial artifact, said loudly)
  2 — manifest invalid or missing
"""

from __future__ import annotations

import asyncio
from pathlib import Path

import typer

from understudy.manifest import ManifestError, load_manifest
from understudy.orchestrate.run import run_table

app = typer.Typer(add_completion=False)


@app.callback()
def main() -> None:
    """Understudy: automated playtest client for SideQuest."""


@app.command()
def run(
    manifest: Path,
    headed: bool = typer.Option(False, "--headed", help="show the browser windows"),
    out: Path = typer.Option(Path("reports"), "--out", help="report output root"),
    turns: int | None = typer.Option(
        None, "--turns", min=1, help="override the manifest's per-seat turn cap"
    ),
) -> None:
    """Run a table from a manifest: N naive bot seats join the session and play."""
    try:
        m = load_manifest(manifest)
    except ManifestError as exc:
        typer.echo(f"invalid manifest: {exc}")
        raise typer.Exit(2)
    if turns is not None:
        m = m.model_copy(update={"turns": turns})
    code = asyncio.run(run_table(m, headed=headed, out_root=out))
    raise typer.Exit(code)
