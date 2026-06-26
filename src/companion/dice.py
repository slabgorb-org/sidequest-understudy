"""Fair dice faces. Physics-is-the-roll (ADR-074): the client submits the
settled faces and the server resolves from them — so the companion just rolls
fair RNG. No Rapier, no 3D."""

from __future__ import annotations

import random


def roll_faces(die_system: str, rng: random.Random | None = None) -> list[int]:
    r = rng or random.Random()
    match die_system:
        case "d20":
            return [r.randint(1, 20)]
        case "2d6":
            return [r.randint(1, 6), r.randint(1, 6)]
        case "4dF":
            return [r.choice((-1, 0, 1)) for _ in range(4)]
        case _:
            raise ValueError(f"unknown die system: {die_system!r}")
