import json
from typing import Literal

import httpx
import pytest
from pydantic import BaseModel

from seat_core.core import Message, ModelError
from seat_core.llm.ollama_model import OllamaModel


class Ping(BaseModel):
    kind: Literal["a", "b"]


def _transport(reply: dict) -> httpx.MockTransport:
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.path == "/api/chat"
        body = json.loads(request.content)
        assert body["stream"] is False
        assert body["format"]["properties"]["kind"]  # output schema passed
        return httpx.Response(200, json=reply)

    return httpx.MockTransport(handler)


async def test_ollama_decides_and_meters_tokens():
    reply = {
        "message": {"role": "assistant", "content": '{"kind": "a"}'},
        "prompt_eval_count": 100,
        "eval_count": 12,
    }
    model = OllamaModel("qwen3:8b", Ping, client=httpx.AsyncClient(transport=_transport(reply)))
    result = await model.decide("sys", [Message(role="user", content="screen")])
    assert result.value.kind == "a"
    assert (result.input_tokens, result.output_tokens) == (100, 12)


async def test_ollama_garbage_raises_model_error():
    reply = {"message": {"role": "assistant", "content": "lol no"}}
    model = OllamaModel("qwen3:8b", Ping, client=httpx.AsyncClient(transport=_transport(reply)))
    with pytest.raises(ModelError):
        await model.decide("sys", [Message(role="user", content="screen")])


# --- TEA adversarial additions ---


async def test_ollama_missing_message_content_raises_model_error():
    # A malformed envelope (no message/content) is a loud ModelError, not a KeyError
    # that leaks out of the backend uncaught.
    reply: dict = {"prompt_eval_count": 5}
    model = OllamaModel("qwen3:8b", Ping, client=httpx.AsyncClient(transport=_transport(reply)))
    with pytest.raises(ModelError):
        await model.decide("sys", [Message(role="user", content="screen")])


async def test_ollama_meters_zero_when_counts_absent():
    # Ollama may omit prompt_eval_count/eval_count; metering defaults to 0 rather
    # than crashing, while still returning the decided value.
    reply = {"message": {"role": "assistant", "content": '{"kind": "b"}'}}
    model = OllamaModel("qwen3:8b", Ping, client=httpx.AsyncClient(transport=_transport(reply)))
    result = await model.decide("sys", [Message(role="user", content="screen")])
    assert result.value.kind == "b"
    assert (result.input_tokens, result.output_tokens) == (0, 0)
