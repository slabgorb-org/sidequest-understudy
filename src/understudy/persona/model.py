"""Play-style archetypes — the playgroup as test matrix.

An archetype shapes BEHAVIOR AND ATTENTION, not knowledge: a mechanics_first
bot does not know the dice tray exists — it wants it to exist and goes
looking. 'Looked and could not find' is the per-user-type finding the
instrument exists to produce.
"""

from __future__ import annotations

from pathlib import Path
from typing import Literal

import yaml
from pydantic import BaseModel, ConfigDict, Field

_ARCHETYPE_DIR = Path(__file__).parent / "archetypes"

Level = Literal["low", "medium", "high"]


class Archetype(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: str
    narrative_vs_mechanical: float = Field(ge=0.0, le=1.0)  # 0 = narrative, 1 = crunch
    verbosity: Level
    decisiveness: Level
    affordance_hunger: Level
    reading_tolerance: Level
    prompt_fragment: str


def load_archetype(archetype_id: str) -> Archetype:
    path = _ARCHETYPE_DIR / f"{archetype_id}.yaml"
    if not path.exists():
        raise FileNotFoundError(f"no archetype {archetype_id!r} at {path}")
    return Archetype.model_validate(yaml.safe_load(path.read_text()))


def load_all_archetypes() -> dict[str, Archetype]:
    return {p.stem: load_archetype(p.stem) for p in sorted(_ARCHETYPE_DIR.glob("*.yaml"))}
