"""`claude -p` subprocess backend. One-shot; no token metering available
(reported as zeros — the ledger guards API spend, and claude -p bills to the
operator's plan, not per-token)."""

from __future__ import annotations

import asyncio
import json

from understudy.brain.core import DecideResult, Message, ModelError, parse_intent


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
