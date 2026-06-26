"""Thin typed WebSocket subset: a Transport seam, outgoing-frame builders, and a
StateMirror that merges server pushes into 'what I currently know'. The real
`websockets` adapter and the full-loop wiring test live in 159-5."""

from __future__ import annotations

from typing import Protocol

from companion.manifest import CompanionDef

# Server pushes that ask the companion to throw/pick (the brain must respond).
_PROMPT_KINDS = frozenset({"DICE_REQUEST", "CONFRONTATION", "FATE_DEFEND_REQUEST"})


class Transport(Protocol):
    async def send(self, frame: dict) -> None: ...
    async def recv(self) -> dict | None: ...  # None means the connection closed


def connect_frame(defn: CompanionDef) -> dict:
    return {
        "type": "SESSION_EVENT",
        "payload": {
            # The room/session slug the human is in — same game_slug → same
            # SessionRoom (the /ws route carries NO path slug; the server reads it
            # from this payload field, exactly as the React client does).
            "event": "connect",
            "game_slug": defn.game_slug,
            "player_name": defn.name,
            "companion_of": defn.companion_of,
            "relationship": defn.role.value,
        },
    }


def seat_frame(character_slot: str) -> dict:
    return {"type": "PLAYER_SEAT", "payload": {"character_slot": character_slot}}


def chargen_choice_frame(choice: str) -> dict:
    return {"type": "CHARACTER_CREATION", "payload": {"phase": "scene", "choice": choice}}


def player_action_frame(player_id: str, text: str, round_: int) -> dict:
    return {
        "type": "PLAYER_ACTION",
        "player_id": player_id,
        "payload": {"action": text, "aside": False, "round": round_},
    }


def aside_frame(player_id: str, text: str, round_: int) -> dict:
    return {
        "type": "PLAYER_ACTION",
        "player_id": player_id,
        "payload": {"action": text, "aside": True, "round": round_},
    }


def dice_throw_frame(player_id: str, faces: list[int], beat_id: str | None = None) -> dict:
    payload: dict = {"faces": faces}
    if beat_id is not None:
        payload["beat_id"] = beat_id
    return {"type": "DICE_THROW", "player_id": player_id, "payload": payload}


def fate_throw_frame(player_id: str, action: str, faces: list[int]) -> dict:
    return {
        "type": "FATE_THROW",
        "player_id": player_id,
        "payload": {"action": action, "faces": faces},
    }


def yield_frame(player_id: str, round_: int) -> dict:
    return {"type": "YIELD", "player_id": player_id, "payload": {"round": round_}}


class StateMirror:
    """Accumulates server pushes into the companion's current view."""

    def __init__(self) -> None:
        self.self_player_id: str | None = None
        self.round: int = 0
        self.last_narration: str = ""
        self.party_status: dict = {}
        self.pending: tuple[str, dict] | None = None  # (kind, payload) of a roll/confrontation prompt
        self._turn_entries: list[dict] = []

    def apply(self, frame: dict) -> None:
        kind = frame.get("type")
        payload = frame.get("payload", {}) or {}
        if kind == "SESSION_EVENT" and payload.get("event") in {"connected", "ready"}:
            if frame.get("player_id"):
                self.self_player_id = frame["player_id"]
        elif kind == "NARRATION":
            self.last_narration = payload.get("text", "")
        elif kind == "NARRATION_END":
            if isinstance(payload.get("round"), int):
                self.round = payload["round"]
            self.pending = None  # a resolved round clears any stale prompt
        elif kind == "PARTY_STATUS":
            self.party_status = payload
        elif kind == "TURN_STATUS":
            self._turn_entries = payload.get("entries", []) or []
        elif kind in _PROMPT_KINDS:
            self.pending = (kind, payload)

    def my_turn(self) -> bool:
        if self.self_player_id is None:
            return False
        return any(
            e.get("player_id") == self.self_player_id and e.get("status") == "pending"
            for e in self._turn_entries
        )
