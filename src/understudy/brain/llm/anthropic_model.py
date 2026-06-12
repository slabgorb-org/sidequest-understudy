"""Anthropic SDK backend. Intent is forced via a tool call so the shape is
validated at the API layer, not parsed out of prose.

A seat's ``system`` prompt (frame + table contract + persona) is byte-stable
for the whole run, so it carries a ``cache_control`` breakpoint: every one of
a seat's ~50 turns re-reads the same cached prefix (tools + system) at ~0.1x
input cost instead of re-paying it cold. ``input_tokens`` reported to the
ledger sums cached and uncached input so ``max_tokens_total`` still bounds
true work — only the *cost* drops, not the metered volume."""

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
            # Single cache breakpoint on the system block caches everything
            # earlier in the prefix (the Intent tool schema) plus the system
            # prompt itself — the whole stable, per-seat-constant head.
            system=[
                {
                    "type": "text",
                    "text": system,
                    "cache_control": {"type": "ephemeral"},
                }
            ],
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
        usage = resp.usage
        cache_read = getattr(usage, "cache_read_input_tokens", 0) or 0
        cache_creation = getattr(usage, "cache_creation_input_tokens", 0) or 0
        return DecideResult(
            intent=intent,
            input_tokens=usage.input_tokens + cache_read + cache_creation,
            output_tokens=usage.output_tokens,
        )
