import json

import httpx
import pytest

from understudy.brain.core import Message, ModelError
from understudy.brain.llm.factory import make_model
from understudy.brain.llm.ollama_model import OllamaModel
from understudy.types import IntentKind


def test_factory_dispatches_by_prefix():
    assert type(make_model("ollama/qwen3:8b")).__name__ == "OllamaModel"
    assert type(make_model("claude_p/haiku")).__name__ == "ClaudePModel"
    assert type(make_model("fake")).__name__ == "FakeActionModel"


def test_factory_fails_loud_on_unknown_backend():
    with pytest.raises(ValueError, match="unknown model backend"):
        make_model("bard/gpt-1")


def _ollama_transport(reply: dict) -> httpx.MockTransport:
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.path == "/api/chat"
        body = json.loads(request.content)
        assert body["stream"] is False
        assert body["format"]["properties"]["kind"]  # Intent schema passed
        return httpx.Response(200, json=reply)

    return httpx.MockTransport(handler)


async def test_ollama_decides_and_meters_tokens():
    reply = {
        "message": {"role": "assistant", "content": '{"kind": "wait"}'},
        "prompt_eval_count": 100,
        "eval_count": 12,
    }
    model = OllamaModel(
        "qwen3:8b", client=httpx.AsyncClient(transport=_ollama_transport(reply))
    )
    result = await model.decide("sys", [Message(role="user", content="screen")])
    assert result.intent.kind is IntentKind.WAIT
    assert (result.input_tokens, result.output_tokens) == (100, 12)


async def test_ollama_garbage_raises_model_error():
    reply = {"message": {"role": "assistant", "content": "lol no"}}
    model = OllamaModel(
        "qwen3:8b", client=httpx.AsyncClient(transport=_ollama_transport(reply))
    )
    with pytest.raises(ModelError):
        await model.decide("sys", [Message(role="user", content="screen")])
