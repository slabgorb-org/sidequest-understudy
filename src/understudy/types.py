"""Core wire-free types shared by every understudy module.

The Intent is the ONLY thing the brain returns: a typed claim about what the
player does next, naming its target the way a player would say it aloud —
never a node id, never a coordinate.
"""

from __future__ import annotations

from enum import StrEnum

from pydantic import BaseModel, ConfigDict, model_validator


class IntentKind(StrEnum):
    ACT = "act"
    REPORT_CONFUSION = "report_confusion"
    WAIT = "wait"


class Intent(BaseModel):
    """What the bot does this cycle. One interaction at a time:
    type into a field (text_input set) OR click a control (text_input None)."""

    model_config = ConfigDict(extra="forbid")

    kind: IntentKind
    target_role: str | None = None  # ARIA role as the bot perceives it ("button")
    target_name: str | None = None  # accessible name as the bot would say it ("Send")
    text_input: str | None = None  # text to type into the target, if any
    reason: str | None = None  # for report_confusion / wait

    @model_validator(mode="after")
    def _shape(self) -> "Intent":
        if self.kind is IntentKind.ACT and not (self.target_role and self.target_name):
            raise ValueError("act intent requires target_role and target_name")
        if self.kind is IntentKind.REPORT_CONFUSION and not self.reason:
            raise ValueError("report_confusion intent requires a reason")
        return self


class SignalKind(StrEnum):
    RESOLUTION_FAILED = "resolution_failed"
    RESOLUTION_AMBIGUOUS = "resolution_ambiguous"
    REPEATED_ACTION = "repeated_action"
    DECIDE_TIMEOUT = "decide_timeout"
    CONSOLE_ERROR = "console_error"
    NO_ACTIONABLE_ELEMENTS = "no_actionable_elements"
    MODEL_ERROR = "model_error"  # malformed model output — down-weighted in reconciliation


class FrictionSignal(BaseModel):
    """One objective stuck-signal observed by the harness (zero LLM judgment)."""

    kind: SignalKind
    seat: int
    turn: int
    detail: str


class TranscriptRow(BaseModel):
    """One perceive→decide→act→observe cycle for one seat."""

    seat: int
    turn: int
    snapshot: str  # the structured-text a11y snapshot the brain saw
    intent: Intent | None  # None when decide failed or timed out
    resolution: str  # "resolved" | "ambiguous" | "failed" | "n/a"
    narration_delta: str  # new text observed after acting
    signals: list[FrictionSignal] = []


class Grade(StrEnum):
    CONFIRMED = "confirmed"  # subjective + objective agree
    BEHAVIORAL = "behavioral"  # objective only — bot muddled through silently
    CLAIMED = "claimed"  # subjective only — wolf-cry candidate, kept but down-ranked


class Finding(BaseModel):
    grade: Grade
    seat: int
    archetype: str
    turn: int
    turn_end: int = 0  # last turn of a collapsed stuck-state; coerced to >= turn
    occurrences: int = 1  # how many per-turn findings collapsed into this one
    confusion_reason: str | None
    signals: list[FrictionSignal]
    snapshot_excerpt: str

    @model_validator(mode="after")
    def _range(self) -> "Finding":
        if self.turn_end < self.turn:
            self.turn_end = self.turn
        return self
