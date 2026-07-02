"""Anthropic SDK backend. The output shape is forced via a tool call so it is
validated at the API layer, not parsed from prose.

A seat's `system` prompt is byte-stable for the whole run, so it carries a
`cache_control` breakpoint: every turn re-reads the same cached prefix (tool
schema + system) at ~0.1x input cost. `input_tokens` reported to the ledger
sums cached and uncached input, so a token ceiling still bounds true work."""

from __future__ import annotations

import anthropic
from pydantic import BaseModel, ValidationError

from seat_core.core import DecideResult, Message, ModelError


class AnthropicModel:
    def __init__(
        self,
        model: str,
        output_model: type[BaseModel],
        client: anthropic.AsyncAnthropic | None = None,
        tool_name: str = "submit",
    ):
        self._model = model
        self._output_model = output_model
        self._tool_name = tool_name
        self._client = client or anthropic.AsyncAnthropic()
        self._tool = {
            "name": tool_name,
            "description": "Submit your structured decision.",
            "input_schema": output_model.model_json_schema(),
        }

    async def decide(self, system: str, transcript: list[Message]) -> DecideResult:
        resp = await self._client.messages.create(
            model=self._model,
            max_tokens=512,
            system=[{"type": "text", "text": system, "cache_control": {"type": "ephemeral"}}],
            messages=[{"role": m.role, "content": m.content} for m in transcript],
            tools=[self._tool],
            tool_choice={"type": "tool", "name": self._tool_name},
        )
        block = next((b for b in resp.content if b.type == "tool_use"), None)
        if block is None:
            raise ModelError("anthropic response contained no tool_use block")
        try:
            value = self._output_model.model_validate(block.input)
        except ValidationError as exc:
            raise ModelError(
                f"tool input is not a valid {self._output_model.__name__}: {exc}"
            ) from exc
        usage = resp.usage
        cache_read = getattr(usage, "cache_read_input_tokens", 0) or 0
        cache_creation = getattr(usage, "cache_creation_input_tokens", 0) or 0
        # input_tokens keeps summing cache (the token ceiling meters true work);
        # cache_tokens + model are surfaced separately for the companion telemetry
        # ledger (161-2). cost_usd stays 0.0 — the Anthropic SDK response reports no
        # per-call price (claude_p is the cost-metered backend via total_cost_usd).
        return DecideResult(
            value=value,
            input_tokens=usage.input_tokens + cache_read + cache_creation,
            output_tokens=usage.output_tokens,
            cache_tokens=cache_read + cache_creation,
            model=self._model,
        )
