"""Ollama backend — the zero-cost local lane. Uses /api/chat with a JSON
schema `format` so structured output comes from the runtime, not regex."""

from __future__ import annotations

import httpx

from understudy.brain.core import DecideResult, Message, ModelError, parse_intent
from understudy.types import Intent


class OllamaModel:
    def __init__(
        self,
        model: str,
        host: str = "http://localhost:11434",
        client: httpx.AsyncClient | None = None,
    ):
        self._model = model
        self._host = host.rstrip("/")
        self._client = client or httpx.AsyncClient(timeout=300.0)

    async def decide(self, system: str, transcript: list[Message]) -> DecideResult:
        payload = {
            "model": self._model,
            "stream": False,
            "format": Intent.model_json_schema(),
            "messages": [
                {"role": "system", "content": system},
                *({"role": m.role, "content": m.content} for m in transcript),
            ],
        }
        resp = await self._client.post(f"{self._host}/api/chat", json=payload)
        resp.raise_for_status()
        data = resp.json()
        try:
            content = data["message"]["content"]
        except (KeyError, TypeError) as exc:
            raise ModelError(f"ollama response missing message content: {data!r:.300}") from exc
        intent = parse_intent(content)
        return DecideResult(
            intent=intent,
            input_tokens=int(data.get("prompt_eval_count", 0)),
            output_tokens=int(data.get("eval_count", 0)),
        )
