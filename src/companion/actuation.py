"""Turn a CompanionIntent into one outgoing WS frame. Dice faces are generated
fair here (physics-is-the-roll) from the pending prompt's die system; FATE_DEFEND
uses 4dF."""

from __future__ import annotations

import random

from companion.dice import roll_faces
from companion.intent import CompanionIntent, IntentKind
from companion.protocol import (
    StateMirror,
    aside_frame,
    dice_throw_frame,
    fate_throw_frame,
    player_action_frame,
    yield_frame,
)


def _die_system(mirror: StateMirror, default: str) -> str:
    if mirror.pending is not None:
        return mirror.pending[1].get("die_system", default)
    return default


def actuate(
    intent: CompanionIntent, mirror: StateMirror, *, rng: random.Random | None = None
) -> dict | None:
    pid = mirror.self_player_id
    if pid is None:
        return None
    match intent.kind:
        case IntentKind.ACT:
            return player_action_frame(pid, intent.text or "", mirror.round)
        case IntentKind.ASIDE:
            return aside_frame(pid, intent.text or "", mirror.round)
        case IntentKind.ROLL:
            return dice_throw_frame(pid, roll_faces(_die_system(mirror, "d20"), rng))
        case IntentKind.BEAT:
            return dice_throw_frame(
                pid, roll_faces(_die_system(mirror, "2d6"), rng), beat_id=intent.beat_id
            )
        case IntentKind.DEFEND:
            return fate_throw_frame(pid, "defend", roll_faces("4dF", rng))
        case IntentKind.YIELD:
            return yield_frame(pid, mirror.round)
    return yield_frame(pid, mirror.round)  # unreachable; defensive safe pass
