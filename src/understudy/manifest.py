"""Run manifest — declares the table. Composition falls out: a seat is just
an independent client; 'human' seats are simply not driven by this process."""

from __future__ import annotations

from pathlib import Path

import yaml
from pydantic import BaseModel, ConfigDict, ValidationError, field_validator

from understudy.persona.model import load_all_archetypes

# claude -p on haiku, billed to the operator's subscription (NOT the metered
# API). This only holds because ClaudePModel strips ANTHROPIC_API_KEY from the
# child env (see claude_p_model.py) — `claude -p` prefers that key over plan
# OAuth and would otherwise bill per-token, uncached. Trade-off: claude_p
# reports zero tokens, so max_tokens_total does not bound these seats (plan
# billing is flat, so there is no runaway-$ risk; wall_clock + turn cap guard).
DEFAULT_MODEL = "claude_p/haiku"


class ManifestError(Exception):
    pass


class SeatSpec(BaseModel):
    model_config = ConfigDict(extra="forbid")

    archetype: str  # "human" or an archetype id
    model: str = DEFAULT_MODEL


class RunManifest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str
    genre: str
    world: str
    session_url: str  # explicit, never derived — no silent fallbacks
    seats: list[SeatSpec]
    turns: int = 12
    wall_clock_minutes: float = 30.0
    decide_timeout_s: float = 120.0
    settle_ms: int = 4000
    max_tokens_total: int | None = None
    capture_spans: bool = True
    jaeger_url: str = "http://localhost:16686"

    @field_validator("seats", mode="before")
    @classmethod
    def _coerce_seats(cls, v: object) -> object:
        if isinstance(v, list):
            return [{"archetype": s} if isinstance(s, str) else s for s in v]
        return v


def load_manifest(path: Path) -> RunManifest:
    if not path.exists():
        raise ManifestError(f"manifest not found: {path}")
    try:
        m = RunManifest.model_validate(yaml.safe_load(path.read_text()))
    except (ValidationError, yaml.YAMLError) as exc:
        raise ManifestError(f"invalid manifest {path}: {exc}") from exc
    known = set(load_all_archetypes())
    for seat in m.seats:
        if seat.archetype != "human" and seat.archetype not in known:
            raise ManifestError(f"unknown archetype {seat.archetype!r} (known: {sorted(known)})")
    return m
