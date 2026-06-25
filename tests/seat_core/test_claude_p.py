import asyncio
import json
from typing import Literal

import pytest
from pydantic import BaseModel

from seat_core.core import Message, ModelError
from seat_core.llm.claude_p_model import _API_KEY_VARS, ClaudePModel, _plan_env


class Ping(BaseModel):
    kind: Literal["a", "b"]


def test_claude_p_scrubs_api_keys_from_child_env(monkeypatch):
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-ant-leak")
    monkeypatch.setenv("ANTHROPIC_ADMIN_KEY", "sk-ant-admin")
    monkeypatch.setenv("PATH", "/usr/bin")  # ordinary vars survive
    env = _plan_env()
    for var in _API_KEY_VARS:
        assert var not in env, f"{var} would route claude -p to API billing"
    assert env["PATH"] == "/usr/bin"


class _FakeProc:
    def __init__(self, returncode: int, stdout: bytes, stderr: bytes):
        self.returncode = returncode
        self._stdout = stdout
        self._stderr = stderr

    async def communicate(self, _stdin: bytes | None = None):
        return self._stdout, self._stderr


def _patch_subprocess(monkeypatch, *, returncode: int = 0, stdout: bytes = b"", stderr: bytes = b""):
    """Replace asyncio.create_subprocess_exec with a fake that records its kwargs
    so a test can assert HOW the subprocess was launched (env, argv)."""
    captured: dict = {}

    async def fake_exec(*args, **kwargs):
        captured["args"] = args
        captured["env"] = kwargs.get("env")
        return _FakeProc(returncode, stdout, stderr)

    monkeypatch.setattr(asyncio, "create_subprocess_exec", fake_exec)
    return captured


async def test_claude_p_decide_launches_claude_without_api_key(monkeypatch):
    # WIRING: defining _plan_env() is not enough — decide() must actually pass the
    # scrubbed env to the subprocess, else claude -p inherits the key and bills API.
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-ant-leak")
    monkeypatch.setenv("ANTHROPIC_ADMIN_KEY", "sk-ant-admin")
    stdout = json.dumps({"result": '{"kind": "a"}'}).encode()
    captured = _patch_subprocess(monkeypatch, returncode=0, stdout=stdout)

    model = ClaudePModel("haiku", Ping)
    result = await model.decide("sys", [Message(role="user", content="screen")])

    assert result.value.kind == "a"
    assert (result.input_tokens, result.output_tokens) == (0, 0)
    assert captured["args"][:3] == ("claude", "-p", "-")
    assert captured["env"] is not None, "decide() did not pass an explicit env to the subprocess"
    for var in _API_KEY_VARS:
        assert var not in captured["env"], f"{var} leaked into the claude -p child env"


async def test_claude_p_nonzero_exit_raises_model_error(monkeypatch):
    _patch_subprocess(monkeypatch, returncode=1, stdout=b"", stderr=b"boom")
    model = ClaudePModel("haiku", Ping)
    with pytest.raises(ModelError):
        await model.decide("sys", [Message(role="user", content="screen")])


async def test_claude_p_non_json_envelope_raises_model_error(monkeypatch):
    _patch_subprocess(monkeypatch, returncode=0, stdout=b"this is not json")
    model = ClaudePModel("haiku", Ping)
    with pytest.raises(ModelError):
        await model.decide("sys", [Message(role="user", content="screen")])
