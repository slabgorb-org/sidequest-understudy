"""Behavioral stuck-detection helpers — zero LLM judgment."""

from __future__ import annotations

from understudy.types import Intent, IntentKind


def repeated_action(intents: list[Intent | None], n: int = 3) -> bool:
    """True when the last `n` ACT intents are identical (target + text)."""
    acts = [i for i in intents if i is not None and i.kind is IntentKind.ACT]
    if len(acts) < n:
        return False
    tail = acts[-n:]
    first = (tail[0].target_role, tail[0].target_name, tail[0].text_input)
    return all((a.target_role, a.target_name, a.text_input) == first for a in tail)
