import json

import anthropic
import httpx
import pytest

from understudy.brain.core import Message, ModelError
from understudy.brain.llm.anthropic_model import AnthropicModel
from understudy.brain.llm.claude_p_model import _API_KEY_VARS, _plan_env
from understudy.brain.llm.factory import make_model
from understudy.brain.llm.ollama_model import OllamaModel
from understudy.types import IntentKind


def test_factory_dispatches_by_prefix(monkeypatch):
    monkeypatch.setenv("ANTHROPIC_API_KEY", "test")  # AsyncAnthropic() needs a key at construct
    assert type(make_model("anthropic/claude-haiku-4-5-20251001")).__name__ == "AnthropicModel"
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
    model = OllamaModel("qwen3:8b", client=httpx.AsyncClient(transport=_ollama_transport(reply)))
    result = await model.decide("sys", [Message(role="user", content="screen")])
    assert result.intent.kind is IntentKind.WAIT
    assert (result.input_tokens, result.output_tokens) == (100, 12)


async def test_ollama_garbage_raises_model_error():
    reply = {"message": {"role": "assistant", "content": "lol no"}}
    model = OllamaModel("qwen3:8b", client=httpx.AsyncClient(transport=_ollama_transport(reply)))
    with pytest.raises(ModelError):
        await model.decide("sys", [Message(role="user", content="screen")])


def _anthropic_transport(seen: dict) -> httpx.MockTransport:
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
                    {"type": "tool_use", "id": "tu_1", "name": "submit_intent",
                     "input": {"kind": "wait"}},
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


async def test_anthropic_caches_system_prefix_and_meters_cache_tokens():
    seen: dict = {}
    client = anthropic.AsyncAnthropic(
        api_key="test", http_client=httpx.AsyncClient(transport=_anthropic_transport(seen))
    )
    model = AnthropicModel("claude-haiku-4-5-20251001", client=client)
    result = await model.decide("STABLE SYSTEM", [Message(role="user", content="screen")])

    # Intent forced via tool call
    assert result.intent.kind is IntentKind.WAIT
    # Cache breakpoint sits on the stable system block
    assert seen["body"]["system"][0]["cache_control"] == {"type": "ephemeral"}
    assert seen["body"]["system"][0]["text"] == "STABLE SYSTEM"
    # Ledger sees TRUE input volume (uncached + cache read + cache creation),
    # so max_tokens_total still bounds work even when most input is cached.
    assert result.input_tokens == 10 + 200 + 30
    assert result.output_tokens == 5


def test_claude_p_scrubs_api_keys_from_child_env(monkeypatch):
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-ant-leak")
    monkeypatch.setenv("ANTHROPIC_ADMIN_KEY", "sk-ant-admin")
    monkeypatch.setenv("PATH", "/usr/bin")  # ordinary vars survive
    env = _plan_env()
    for var in _API_KEY_VARS:
        assert var not in env, f"{var} would route claude -p to API billing"
    assert env["PATH"] == "/usr/bin"
