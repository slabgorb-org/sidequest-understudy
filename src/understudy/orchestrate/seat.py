"""The per-seat perceive→decide→act→observe loop.

A turn = ONE interaction cycle (type OR click OR wait OR complain), the way a
screen-reader user operates. Guards (ADR-134's lesson, applied client-side):
turn cap, token ledger, per-decide timeout, wall-clock deadline. Every guard
ends in a graceful partial transcript, never a hung process.
"""

from __future__ import annotations

import asyncio
import time

from playwright.async_api import Page

from understudy.actuation.act import Resolution, perform_act
from understudy.brain.core import ActionModel, Message, ModelError
from understudy.findings.detect import repeated_action
from understudy.perception.snapshot import count_actionable, new_lines, perceive
from understudy.persona.model import Archetype
from understudy.persona.prompts import (
    HISTORY_DEPTH,
    VERBOSITY_CHAR_CAP,
    WAIT_POLL_SECONDS,
    build_system_prompt,
)
from understudy.types import FrictionSignal, Intent, IntentKind, SignalKind, TranscriptRow


class TokenLedger:
    """Shared across all seats in a run — the pool is per-run, not per-seat."""

    def __init__(self, ceiling: int | None):
        self.total = 0
        self.ceiling = ceiling

    def add(self, input_tokens: int, output_tokens: int) -> None:
        self.total += input_tokens + output_tokens

    @property
    def breached(self) -> bool:
        return self.ceiling is not None and self.total >= self.ceiling


class SeatRunner:
    def __init__(
        self,
        *,
        seat: int,
        archetype: Archetype,
        model: ActionModel,
        page: Page,
        turns: int,
        decide_timeout_s: float,
        settle_ms: int,
        ledger: TokenLedger,
        deadline: float | None,  # time.monotonic() deadline, None = no wall clock
    ):
        self.seat = seat
        self.archetype = archetype
        self.model = model
        self.page = page
        self.turns = turns
        self.decide_timeout_s = decide_timeout_s
        self.settle_ms = settle_ms
        self.ledger = ledger
        self.deadline = deadline
        self._system = build_system_prompt(archetype)
        self._history: list[Message] = []
        self._intents: list[Intent | None] = []
        self._console_errors: list[str] = []
        page.on("console", self._on_console)
        page.on("pageerror", lambda err: self._console_errors.append(str(err)))

    def _on_console(self, msg) -> None:
        if msg.type == "error":
            self._console_errors.append(msg.text)

    def _drain_console(self, turn: int) -> list[FrictionSignal]:
        sigs = [
            FrictionSignal(
                kind=SignalKind.CONSOLE_ERROR, seat=self.seat, turn=turn, detail=text[:300]
            )
            for text in self._console_errors
        ]
        self._console_errors.clear()
        return sigs

    async def run(self) -> list[TranscriptRow]:
        rows: list[TranscriptRow] = []
        depth = HISTORY_DEPTH[self.archetype.reading_tolerance]
        cap = VERBOSITY_CHAR_CAP[self.archetype.verbosity]
        wait_poll = WAIT_POLL_SECONDS[self.archetype.decisiveness]

        for turn in range(1, self.turns + 1):
            if self.deadline is not None and time.monotonic() > self.deadline:
                break
            if self.ledger.breached:
                break

            snapshot = await perceive(self.page)
            signals: list[FrictionSignal] = self._drain_console(turn)
            if count_actionable(snapshot) == 0:
                signals.append(
                    FrictionSignal(
                        kind=SignalKind.NO_ACTIONABLE_ELEMENTS,
                        seat=self.seat,
                        turn=turn,
                        detail="no operable controls exposed to a semantic reader",
                    )
                )

            self._history.append(Message(role="user", content=snapshot))
            context = self._history[-depth:]

            intent: Intent | None = None
            try:
                result = await asyncio.wait_for(
                    self.model.decide(self._system, context),
                    timeout=self.decide_timeout_s,
                )
                self.ledger.add(result.input_tokens, result.output_tokens)
                intent = result.intent
            except TimeoutError:
                signals.append(
                    FrictionSignal(
                        kind=SignalKind.DECIDE_TIMEOUT,
                        seat=self.seat,
                        turn=turn,
                        detail=f"model did not decide within {self.decide_timeout_s}s",
                    )
                )
            except ModelError as exc:
                signals.append(
                    FrictionSignal(
                        kind=SignalKind.MODEL_ERROR,
                        seat=self.seat,
                        turn=turn,
                        detail=str(exc)[:300],
                    )
                )

            self._intents.append(intent)
            if repeated_action(self._intents):
                signals.append(
                    FrictionSignal(
                        kind=SignalKind.REPEATED_ACTION,
                        seat=self.seat,
                        turn=turn,
                        detail="same act three times running",
                    )
                )

            resolution = "n/a"
            narration_delta = ""
            if intent is not None and intent.kind is IntentKind.ACT:
                if intent.text_input and len(intent.text_input) > cap:
                    intent = intent.model_copy(update={"text_input": intent.text_input[:cap]})
                outcome = await perform_act(self.page, intent, self.settle_ms)
                resolution = outcome.resolution.value
                if outcome.resolution is Resolution.FAILED:
                    signals.append(
                        FrictionSignal(
                            kind=SignalKind.RESOLUTION_FAILED,
                            seat=self.seat,
                            turn=turn,
                            detail=outcome.detail,
                        )
                    )
                elif outcome.resolution is Resolution.AMBIGUOUS:
                    signals.append(
                        FrictionSignal(
                            kind=SignalKind.RESOLUTION_AMBIGUOUS,
                            seat=self.seat,
                            turn=turn,
                            detail=outcome.detail,
                        )
                    )
                after = await perceive(self.page)
                narration_delta = new_lines(snapshot, after)
            elif intent is not None and intent.kind is IntentKind.WAIT:
                await asyncio.sleep(wait_poll)

            if intent is not None:
                self._history.append(Message(role="assistant", content=intent.model_dump_json()))

            rows.append(
                TranscriptRow(
                    seat=self.seat,
                    turn=turn,
                    snapshot=snapshot,
                    intent=intent,
                    resolution=resolution,
                    narration_delta=narration_delta,
                    signals=signals,
                )
            )
        return rows
