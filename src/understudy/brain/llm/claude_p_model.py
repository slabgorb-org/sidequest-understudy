"""`claude -p` subprocess backend. One-shot; no token metering available
(reported as zeros).

To actually bill the operator's plan (the whole point of this backend) the
subprocess must NOT see an API key — `claude -p` prefers `ANTHROPIC_API_KEY`
over subscription OAuth and will otherwise bill the metered API per-token,
uncached. We strip the key from the child env: with a subscription login it
bills the plan; with none it fails loud, never silently falling back to API
spend."""

from __future__ import annotations

import asyncio
import json
import os

from understudy.brain.core import DecideResult, Message, ModelError, parse_intent

# Env vars that, if inherited, would silently route claude -p to API billing.
_API_KEY_VARS = ("ANTHROPIC_API_KEY", "ANTHROPIC_ADMIN_KEY")


def _plan_env() -> dict[str, str]:
    return {k: v for k, v in os.environ.items() if k not in _API_KEY_VARS}


class ClaudePModel:
    def __init__(self, model: str = "haiku"):
        self._model = model

    async def decide(self, system: str, transcript: list[Message]) -> DecideResult:
        convo = "\n\n".join(f"[{m.role}]\n{m.content}" for m in transcript)
        prompt = (
            f"{system}\n\n{convo}\n\n"
            "Reply with ONLY a JSON object for your intent — no prose. Shape: "
            '{"kind": "act"|"report_confusion"|"wait", "target_role": str|null, '
            '"target_name": str|null, "text_input": str|null, "reason": str|null}'
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
        intent = parse_intent(str(envelope.get("result", "")))
        return DecideResult(intent=intent, input_tokens=0, output_tokens=0)
