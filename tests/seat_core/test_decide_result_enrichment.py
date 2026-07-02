"""RED (161-2, AC #1): seat_core DecideResult carries model + cache tokens + cost.

Companion-seat brain telemetry needs the real per-decision cost/token ledger, not
the hardcoded zeros claude_p currently emits. This enriches the shared
``DecideResult`` (used by the companion via ``companion.brain``) with three new
fields and proves every backend fills them:

  * ``claude_p`` — parse the ``claude -p --output-format json`` envelope's
    ``usage`` + ``total_cost_usd`` instead of discarding them (the zeros bug at
    ``claude_p_model.py:60``).
  * ``anthropic`` — already meters tokens; now also reports ``model``.
  * ``ollama`` — meters tokens; reports ``model`` and a zero cost (local, free).

CONTRACT for Dev (part a):
    @dataclass(frozen=True)
    class DecideResult:
        value: BaseModel
        input_tokens: int
        output_tokens: int
        cache_tokens: int = 0
        model: str | None = None
        cost_usd: float = 0.0
Defaults keep every existing 3-arg call site (metering ledger, FakeStructuredModel)
working unchanged.
"""

from __future__ import annotations

import asyncio
import json
from typing import Literal

import anthropic
import httpx
import pytest
from pydantic import BaseModel

from seat_core.core import DecideResult, FakeStructuredModel, Message, ModelError
from seat_core.llm.anthropic_model import AnthropicModel
from seat_core.llm.claude_p_model import ClaudePModel
from seat_core.llm.ollama_model import OllamaModel


class Ping(BaseModel):
    kind: Literal["a", "b"]


# --- DecideResult shape (the data contract) ------------------------------------


def test_decide_result_carries_model_cache_and_cost():
    # RED today: the frozen dataclass has only value/input_tokens/output_tokens,
    # so these kwargs raise TypeError. Dev adds cache_tokens/model/cost_usd.
    r = DecideResult(
        value=Ping(kind="a"),
        input_tokens=120,
        output_tokens=45,
        cache_tokens=105,
        model="claude-haiku",
        cost_usd=0.0034,
    )
    assert r.cache_tokens == 105
    assert r.model == "claude-haiku"
    assert r.cost_usd == pytest.approx(0.0034)


async def test_fake_model_result_exposes_enrichment_defaults():
    # The wiring lane's scripted brain must still produce a well-shaped result:
    # zero tokens/cost, no model — but the FIELDS must exist, or the emit path
    # (161-2 part b) has nothing to read.
    brain = FakeStructuredModel([], default=Ping(kind="a"))
    r = await brain.decide("sys", [])
    assert r.model is None
    assert r.cache_tokens == 0
    assert r.cost_usd == 0.0


# --- claude_p: parse the JSON envelope (no more hardcoded zeros) ----------------


class _FakeProc:
    def __init__(self, returncode: int, stdout: bytes, stderr: bytes) -> None:
        self.returncode = returncode
        self._stdout = stdout
        self._stderr = stderr

    async def communicate(self, _stdin: bytes | None = None):
        return self._stdout, self._stderr


def _patch_subprocess(
    monkeypatch, *, returncode: int = 0, stdout: bytes = b"", stderr: bytes = b""
):
    async def fake_exec(*_args, **_kwargs):
        return _FakeProc(returncode, stdout, stderr)

    monkeypatch.setattr(asyncio, "create_subprocess_exec", fake_exec)


async def test_claude_p_parses_envelope_usage_and_cost(monkeypatch):
    # The whole point of the claude_p backend is to bill the operator's plan; the
    # per-call cost/tokens are IN the envelope and were being thrown away. Parse
    # them so the GM panel can meter every companion decision.
    envelope = {
        "result": '{"kind": "a"}',
        "usage": {
            "input_tokens": 120,
            "output_tokens": 45,
            "cache_read_input_tokens": 100,
            "cache_creation_input_tokens": 5,
        },
        "total_cost_usd": 0.0034,
    }
    _patch_subprocess(monkeypatch, returncode=0, stdout=json.dumps(envelope).encode())
    model = ClaudePModel("haiku", Ping)
    r = await model.decide("sys", [Message(role="user", content="x")])

    assert r.value.kind == "a"
    # No more hardcoded zeros — real usage flows through.
    assert r.output_tokens == 45
    assert r.input_tokens >= 120, "input tokens must reflect the envelope, not 0"
    assert r.cache_tokens == 105, "cache tokens = cache_read + cache_creation"
    assert r.cost_usd == pytest.approx(0.0034)
    assert r.model == "haiku"


async def test_claude_p_missing_usage_defaults_to_zero_not_crash(monkeypatch):
    # A minimal envelope (no usage/total_cost_usd) must degrade to zeros, never a
    # KeyError that breaks a companion's move (No Silent Fallbacks applies to the
    # DECISION, not the telemetry — telemetry gaps are zeros, not crashes).
    envelope = {"result": '{"kind": "b"}'}
    _patch_subprocess(monkeypatch, returncode=0, stdout=json.dumps(envelope).encode())
    model = ClaudePModel("haiku", Ping)
    r = await model.decide("sys", [Message(role="user", content="x")])
    assert r.value.kind == "b"
    assert (r.input_tokens, r.output_tokens, r.cache_tokens, r.cost_usd) == (0, 0, 0, 0.0)
    assert r.model == "haiku"


async def test_claude_p_nonzero_exit_still_raises_model_error(monkeypatch):
    # Enrichment must not weaken the fail-loud contract: a non-zero exit is still
    # a ModelError, never a fabricated zero-cost decision.
    _patch_subprocess(monkeypatch, returncode=1, stdout=b"", stderr=b"boom")
    model = ClaudePModel("haiku", Ping)
    with pytest.raises(ModelError):
        await model.decide("sys", [Message(role="user", content="x")])


# --- anthropic / ollama: report the model id ----------------------------------


def _anthropic_client_returning(body: dict) -> anthropic.AsyncAnthropic:
    def handler(_request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json=body)

    return anthropic.AsyncAnthropic(
        api_key="test", http_client=httpx.AsyncClient(transport=httpx.MockTransport(handler))
    )


async def test_anthropic_reports_model_on_result():
    client = _anthropic_client_returning(
        {
            "id": "msg_1",
            "type": "message",
            "role": "assistant",
            "model": "claude-haiku-4-5-20251001",
            "content": [
                {"type": "tool_use", "id": "tu_1", "name": "submit", "input": {"kind": "b"}}
            ],
            "stop_reason": "tool_use",
            "stop_sequence": None,
            "usage": {"input_tokens": 10, "output_tokens": 5},
        }
    )
    model = AnthropicModel("claude-haiku-4-5-20251001", Ping, client=client)
    r = await model.decide("sys", [Message(role="user", content="screen")])
    assert r.value.kind == "b"
    assert r.model == "claude-haiku-4-5-20251001", "the emit path needs to know which model decided"


def _ollama_transport(reply: dict) -> httpx.MockTransport:
    def handler(_request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json=reply)

    return httpx.MockTransport(handler)


async def test_ollama_reports_model_and_zero_cost():
    reply = {
        "message": {"role": "assistant", "content": '{"kind": "a"}'},
        "prompt_eval_count": 10,
        "eval_count": 3,
    }
    model = OllamaModel(
        "qwen3:8b", Ping, client=httpx.AsyncClient(transport=_ollama_transport(reply))
    )
    r = await model.decide("sys", [Message(role="user", content="screen")])
    assert r.value.kind == "a"
    assert r.model == "qwen3:8b"
    assert r.cost_usd == 0.0, "local ollama is free — cost is a real 0.0, not unknown"
