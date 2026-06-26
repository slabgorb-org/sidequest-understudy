"""CompanionIntent — what the companion does this turn.

ACT carries in-character prose; the server's IntentRouter extracts any ability
from the text, so ACT covers most of 'playing'. ROLL/BEAT/DEFEND are responses
to server-pushed prompts (the faces are generated client-side at actuation).
ASIDE is out-of-character table-talk. YIELD passes the turn — always safe."""

from __future__ import annotations

from enum import StrEnum

from pydantic import BaseModel, ConfigDict, model_validator


class IntentKind(StrEnum):
    ACT = "act"
    ASIDE = "aside"
    ROLL = "roll"
    BEAT = "beat"
    DEFEND = "defend"
    YIELD = "yield"


class CompanionIntent(BaseModel):
    model_config = ConfigDict(extra="forbid")

    kind: IntentKind
    text: str | None = None  # ACT / ASIDE prose
    beat_id: str | None = None  # BEAT: which confrontation beat
    reason: str | None = None  # optional rationale (logged, not sent)

    @model_validator(mode="after")
    def _shape(self) -> "CompanionIntent":
        if self.kind in (IntentKind.ACT, IntentKind.ASIDE) and not self.text:
            raise ValueError(f"{self.kind} intent requires text")
        if self.kind is IntentKind.BEAT and not self.beat_id:
            raise ValueError("beat intent requires beat_id")
        return self


YIELD_INTENT = CompanionIntent(kind=IntentKind.YIELD)
