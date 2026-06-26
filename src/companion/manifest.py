"""Companion definition — authored content (YAML). Declares who the companion
is, whom it's bonded to, where it plays, and how it thinks. Fails loud."""

from __future__ import annotations

from pathlib import Path

import yaml
from pydantic import BaseModel, ConfigDict, ValidationError

from seat_core.persona.axis import Role, SeatAxes

DEFAULT_MODEL = "anthropic/claude-haiku-4-5-20251001"


class ManifestError(Exception):
    pass


class CompanionDef(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str
    species: str
    role: Role
    voice: str
    axes: SeatAxes
    companion_of: str  # the OWNER's identity (Cf-Access email / dev Host)
    genre: str
    world: str
    session_url: str  # explicit, never derived
    model: str = DEFAULT_MODEL
    decide_timeout_s: float = 30.0


def load_companion(path: Path) -> CompanionDef:
    if not path.exists():
        raise ManifestError(f"companion definition not found: {path}")
    try:
        return CompanionDef.model_validate(yaml.safe_load(path.read_text()))
    except (ValidationError, yaml.YAMLError) as exc:
        raise ManifestError(f"invalid companion definition {path}: {exc}") from exc
