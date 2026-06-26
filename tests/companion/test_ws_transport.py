"""RED (159-5): the real WebSocket transport — Plan C Task 10.

WebSocketTransport adapts a live `websockets` connection to the Transport seam the
run loop speaks: JSON frames out, dict frames in. The load-bearing behavior is
recv()'s close handling — a closed connection becomes None so the run loop exits
cleanly instead of hanging. A close is None; any OTHER error must propagate
(lang-review #1: catch the close specifically, never swallow real bugs).
"""

from __future__ import annotations

import inspect
import json

import pytest
import websockets

from companion.ws_transport import WebSocketTransport


class _FakeWS:
    """Stand-in for a websockets client connection: records sent strings, scripts
    recv() output, or raises a scripted error on recv()."""

    def __init__(self, incoming: list[str] | None = None, raise_on_recv: Exception | None = None):
        self.sent: list[str] = []
        self._incoming = list(incoming or [])
        self._raise = raise_on_recv

    async def send(self, raw: str) -> None:
        self.sent.append(raw)

    async def recv(self) -> str:
        if self._raise is not None:
            raise self._raise
        return self._incoming.pop(0)


async def test_send_json_encodes_frame():
    ws = _FakeWS()
    t = WebSocketTransport(ws)
    await t.send({"type": "PLAYER_ACTION", "payload": {"action": "hi", "round": 1}})
    assert len(ws.sent) == 1
    assert json.loads(ws.sent[0]) == {
        "type": "PLAYER_ACTION",
        "payload": {"action": "hi", "round": 1},
    }


async def test_recv_decodes_json_to_dict():
    ws = _FakeWS(incoming=[json.dumps({"type": "NARRATION", "payload": {"text": "hi"}})])
    t = WebSocketTransport(ws)
    frame = await t.recv()
    assert frame == {"type": "NARRATION", "payload": {"text": "hi"}}


async def test_recv_returns_none_on_connection_closed():
    # A closed socket → None, so the run loop returns instead of hanging.
    ws = _FakeWS(raise_on_recv=websockets.ConnectionClosed(None, None))
    t = WebSocketTransport(ws)
    assert await t.recv() is None


async def test_recv_does_not_swallow_unexpected_errors():
    # lang-review #1: only a close becomes None; a genuine bug must NOT be eaten.
    ws = _FakeWS(raise_on_recv=ValueError("not a close"))
    t = WebSocketTransport(ws)
    with pytest.raises(ValueError):
        await t.recv()


async def test_recv_propagates_malformed_json():
    # The socket SUCCEEDS in recv() but returns a non-JSON string; json.loads
    # raises and MUST propagate (loud contract-drift tripwire) — closing the
    # 'only a close becomes None' contract as a complete triple. (Reviewer 159-5.)
    ws = _FakeWS(incoming=["this is not json"])
    t = WebSocketTransport(ws)
    with pytest.raises(json.JSONDecodeError):
        await t.recv()


def test_init_ws_param_is_annotated():
    # lang-review #3: parameters on a public class __init__ MUST be annotated.
    # (Reviewer 159-5: the `ws` param was unannotated.)
    sig = inspect.signature(WebSocketTransport.__init__)
    assert sig.parameters["ws"].annotation is not inspect.Signature.empty
