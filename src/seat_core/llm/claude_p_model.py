"""`claude -p` subprocess backend. One-shot; no token metering (reported zeros).

To bill the operator's plan (the point of this backend) the subprocess must NOT
see an API key — `claude -p` prefers ANTHROPIC_API_KEY over subscription OAuth
and would otherwise bill the metered API. We strip the key from the child env:
with a subscription login it bills the plan; with none it fails loud."""

from __future__ import annotations

import asyncio
import json
import os

from pydantic import BaseModel

from seat_core.core import DecideResult, Message, ModelError, parse_structured

# Env vars that, if inherited, would silently route claude -p to API billing.
_API_KEY_VARS = ("ANTHROPIC_API_KEY", "ANTHROPIC_ADMIN_KEY")


def _plan_env() -> dict[str, str]:
    return {k: v for k, v in os.environ.items() if k not in _API_KEY_VARS}


class ClaudePModel:
    def __init__(self, model: str, output_model: type[BaseModel]):
        self._model = model
        self._output_model = output_model

    async def decide(self, system: str, transcript: list[Message]) -> DecideResult:
        convo = "\n\n".join(f"[{m.role}]\n{m.content}" for m in transcript)
        schema = json.dumps(self._output_model.model_json_schema())
        prompt = (
            f"{system}\n\n{convo}\n\n"
            "Reply with ONLY a JSON object matching this schema — no prose:\n"
            f"{schema}"
        )
        proc = await asyncio.create_subprocess_exec(
            "claude",
            "-p",
            "-",
            "--output-format",
            "json",
            "--model",
            self._model,
            stdin=asyncio.subprocess.PIPE,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            env=_plan_env(),
        )
        stdout, stderr = await proc.communicate(prompt.encode())
        if proc.returncode != 0:
            raise ModelError(f"claude -p exited {proc.returncode}: {stderr.decode()[:300]}")
        try:
            envelope = json.loads(stdout.decode())
        except json.JSONDecodeError as exc:
            raise ModelError(f"claude -p emitted non-JSON envelope: {exc}") from exc
        value = parse_structured(str(envelope.get("result", "")), self._output_model)
        return DecideResult(value=value, input_tokens=0, output_tokens=0)
