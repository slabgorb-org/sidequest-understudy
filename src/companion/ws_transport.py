"""Real Transport over `websockets`. JSON frames in/out. recv() returns None on a
closed connection so the run loop exits cleanly instead of hanging. Only a close
becomes None — any other error propagates (a genuine bug must never be swallowed)."""

from __future__ import annotations

import json

import websockets

from companion.protocol import Transport


class WebSocketTransport(Transport):
    def __init__(self, ws) -> None:
        self._ws = ws

    async def send(self, frame: dict) -> None:
        await self._ws.send(json.dumps(frame))

    async def recv(self) -> dict | None:
        try:
            raw = await self._ws.recv()
        except websockets.ConnectionClosed:
            return None
        return json.loads(raw)
