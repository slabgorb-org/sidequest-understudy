"""Companion CLI. `companion play <def.yaml> [--session URL]`.

Fails loud (exit code 2) on a missing/invalid definition BEFORE any socket opens.
Exit codes: 0 ok; 2 invalid/missing definition."""

from __future__ import annotations

import asyncio
from pathlib import Path

import typer
import websockets

from companion.brain import make_brain
from companion.manifest import CompanionDef, ManifestError, load_companion
from companion.run import run_companion
from companion.ws_transport import WebSocketTransport

app = typer.Typer(add_completion=False)


@app.callback()
def main() -> None:
    """Companion: a full-PC AI companion that joins a live SideQuest session over WS."""
    # A callback forces Typer to keep `play` as a named subcommand even though it
    # is the only command — otherwise a single-command app collapses and the
    # subcommand name is parsed as the first positional argument.


async def play(defn: CompanionDef) -> None:
    """Open the session socket and run the loop until the session ends."""
    async with websockets.connect(defn.session_url) as ws:
        await run_companion(defn, WebSocketTransport(ws), make_brain(defn.model))


def play_cmd(
    definition: Path = typer.Argument(..., metavar="DEFINITION"),
    session: str | None = typer.Option(None, "--session", help="override session_url"),
) -> None:
    """Join a live session as the companion described in DEFINITION."""
    try:
        defn = load_companion(definition)
    except ManifestError as exc:
        typer.echo(f"invalid companion definition: {exc}")
        raise typer.Exit(2) from exc
    if session is not None:
        defn = defn.model_copy(update={"session_url": session})
    asyncio.run(play(defn))


# Register exactly once, under the name "play".
app.command(name="play")(play_cmd)
