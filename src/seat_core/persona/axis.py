"""Persona axes shared by any seated player-agent.

SeatAxes are behavior/attention dials true of a naive playtest bot AND a
companion. The role dial adds the companion's autonomy/bond axis and the
perception scope it implies. No prompts here — consumers build prompts."""

from __future__ import annotations

from enum import StrEnum
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

Level = Literal["low", "medium", "high"]


class SeatAxes(BaseModel):
    model_config = ConfigDict(extra="forbid")

    narrative_vs_mechanical: float = Field(ge=0.0, le=1.0)  # 0 = narrative, 1 = crunch
    verbosity: Level
    decisiveness: Level
    reading_tolerance: Level


class Role(StrEnum):
    PET = "pet"
    PEER = "peer"
    HIRELING = "hireling"


_PERCEPTION_SCOPE: dict[Role, str] = {
    Role.PET: "owner_private",
    Role.PEER: "party",
    Role.HIRELING: "public",
}


class RoleDial(BaseModel):
    model_config = ConfigDict(extra="forbid")

    role: Role

    @property
    def perception_scope(self) -> str:
        """What the server should let this companion see about its human:
        owner_private (pet), party (peer), public (hireling)."""
        return _PERCEPTION_SCOPE[self.role]
