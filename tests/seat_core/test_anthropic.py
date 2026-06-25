import json
from typing import Literal

import anthropic
import httpx
import pytest
from pydantic import BaseModel

from seat_core.core import Message, ModelError
from seat_core.llm.anthropic_model import AnthropicModel


class Ping(BaseModel):
    kind: Literal["a", "b"]


def _transport(seen: dict) -> httpx.MockTransport:
    def handler(request: httpx.Request) -> httpx.Response:
        seen["body"] = json.loads(request.content)
        return httpx.Response(
            200,
            json={
                "id": "msg_1",
                "type": "message",
                "role": "assistant",
                "model": "claude-haiku-4-5-20251001",
                "content": [
                    {"type": "tool_use", "id": "tu_1", "name": "submit", "input": {"kind": "b"}}
                ],
                "stop_reason": "tool_use",
                "stop_sequence": None,
                "usage": {
                    "input_tokens": 10,
                    "output_tokens": 5,
                    "cache_read_input_tokens": 200,
                    "cache_creation_input_tokens": 30,
                },
            },
        )

    return httpx.MockTransport(handler)


def _client_returning(body: dict) -> anthropic.AsyncAnthropic:
    """Build an AsyncAnthropic whose every call returns `body` as the response JSON."""

    def handler(_request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json=body)

    return anthropic.AsyncAnthropic(
        api_key="test", http_client=httpx.AsyncClient(transport=httpx.MockTransport(handler))
    )


async def test_anthropic_forces_tool_caches_prefix_and_meters_true_input():
    seen: dict = {}
    client = anthropic.AsyncAnthropic(
        api_key="test", http_client=httpx.AsyncClient(transport=_transport(seen))
    )
    model = AnthropicModel("claude-haiku-4-5-20251001", Ping, client=client)
    result = await model.decide("STABLE SYSTEM", [Message(role="user", content="screen")])

    assert result.value.kind == "b"
    assert seen["body"]["tools"][0]["input_schema"] == Ping.model_json_schema()
    assert seen["body"]["tool_choice"] == {"type": "tool", "name": "submit"}
    assert seen["body"]["system"][0]["cache_control"] == {"type": "ephemeral"}
    assert seen["body"]["system"][0]["text"] == "STABLE SYSTEM"
    assert result.input_tokens == 10 + 200 + 30
    assert result.output_tokens == 5


# --- TEA adversarial additions (error paths + metering edges) ---


async def test_anthropic_no_tool_use_block_raises_model_error():
    # If the model answers in prose instead of calling the tool, fail loud — never
    # fabricate a decision from an empty parse.
    client = _client_returning(
        {
            "id": "msg_2",
            "type": "message",
            "role": "assistant",
            "model": "claude-haiku-4-5-20251001",
            "content": [{"type": "text", "text": "I think I'll go with a."}],
            "stop_reason": "end_turn",
            "stop_sequence": None,
            "usage": {"input_tokens": 4, "output_tokens": 6},
        }
    )
    model = AnthropicModel("claude-haiku-4-5-20251001", Ping, client=client)
    with pytest.raises(ModelError):
        await model.decide("sys", [Message(role="user", content="screen")])


async def test_anthropic_invalid_tool_input_raises_model_error():
    # Tool input that violates the bound schema is a model failure, not a fallback.
    client = _client_returning(
        {
            "id": "msg_3",
            "type": "message",
            "role": "assistant",
            "model": "claude-haiku-4-5-20251001",
            "content": [
                {"type": "tool_use", "id": "tu_3", "name": "submit", "input": {"kind": "z"}}
            ],
            "stop_reason": "tool_use",
            "stop_sequence": None,
            "usage": {"input_tokens": 4, "output_tokens": 6},
        }
    )
    model = AnthropicModel("claude-haiku-4-5-20251001", Ping, client=client)
    with pytest.raises(ModelError):
        await model.decide("sys", [Message(role="user", content="screen")])


async def test_anthropic_meters_without_cache_fields():
    # Uncached responses omit cache_*_input_tokens; metering must treat them as 0,
    # not crash, so a token ceiling still works on the no-cache path.
    client = _client_returning(
        {
            "id": "msg_4",
            "type": "message",
            "role": "assistant",
            "model": "claude-haiku-4-5-20251001",
            "content": [
                {"type": "tool_use", "id": "tu_4", "name": "submit", "input": {"kind": "a"}}
            ],
            "stop_reason": "tool_use",
            "stop_sequence": None,
            "usage": {"input_tokens": 7, "output_tokens": 3},
        }
    )
    model = AnthropicModel("claude-haiku-4-5-20251001", Ping, client=client)
    result = await model.decide("sys", [Message(role="user", content="screen")])
    assert result.value.kind == "a"
    assert result.input_tokens == 7
    assert result.output_tokens == 3
