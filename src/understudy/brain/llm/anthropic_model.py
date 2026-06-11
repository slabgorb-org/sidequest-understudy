"""Anthropic SDK backend. Intent is forced via a tool call so the shape is
validated at the API layer, not parsed out of prose."""

from __future__ import annotations

import anthropic
from pydantic import ValidationError

from understudy.brain.core import DecideResult, Message, ModelError
from understudy.types import Intent

INTENT_TOOL = {
    "name": "submit_intent",
    "description": "Submit what you, the player, do next.",
    "input_schema": Intent.model_json_schema(),
}


class AnthropicModel:
    def __init__(self, model: str, client: anthropic.AsyncAnthropic | None = None):
        self._model = model
        self._client = client or anthropic.AsyncAnthropic()

    async def decide(self, system: str, transcript: list[Message]) -> DecideResult:
        resp = await self._client.messages.create(
            model=self._model,
            max_tokens=512,
            system=system,
            messages=[{"role": m.role, "content": m.content} for m in transcript],
            tools=[INTENT_TOOL],
            tool_choice={"type": "tool", "name": "submit_intent"},
        )
        block = next((b for b in resp.content if b.type == "tool_use"), None)
        if block is None:
            raise ModelError("anthropic response contained no tool_use block")
        try:
            intent = Intent.model_validate(block.input)
        except ValidationError as exc:
            raise ModelError(f"tool input is not a valid Intent: {exc}") from exc
        return DecideResult(
            intent=intent,
            input_tokens=resp.usage.input_tokens,
            output_tokens=resp.usage.output_tokens,
        )
