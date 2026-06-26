"""Real Transport over `websockets`. JSON frames in/out. recv() returns None on a
closed connection so the run loop exits cleanly instead of hanging. Only a close
becomes None — any other error propagates (a genuine bug must never be swallowed)."""

from __future__ import annotations

import json
from typing import Protocol

import websockets

from companion.protocol import Transport


class _WSConnection(Protocol):
    """The raw websockets connection contract this adapter wraps: text frames in
    and out. Structural, so both `websockets.connect(...)` and a test double satisfy it."""

    async def send(self, data: str) -> None: ...
    async def recv(self) -> str: ...


class WebSocketTransport(Transport):
    def __init__(self, ws: _WSConnection) -> None:
        self._ws = ws

    async def send(self, frame: dict) -> None:
        await self._ws.send(json.dumps(frame))

    async def recv(self) -> dict | None:
        try:
            raw = await self._ws.recv()
        except websockets.ConnectionClosed:
            return None
        return json.loads(raw)
