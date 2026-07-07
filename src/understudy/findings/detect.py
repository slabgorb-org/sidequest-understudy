"""Behavioral stuck-detection helpers — zero LLM judgment."""

from __future__ import annotations

import re

from understudy.types import Intent, IntentKind


def repeated_action(intents: list[Intent | None], n: int = 3) -> bool:
    """True when the last `n` ACT intents are identical (target + text)."""
    acts = [i for i in intents if i is not None and i.kind is IntentKind.ACT]
    if len(acts) < n:
        return False
    tail = acts[-n:]
    first = (tail[0].target_role, tail[0].target_name, tail[0].text_input)
    return all((a.target_role, a.target_name, a.text_input) == first for a in tail)


# The aria snapshot the player perceives (perception/snapshot.py) is indented,
# YAML-ish text: an enemy panel is a `region "Enemies"` with `listitem` foes;
# narration is the content of a `log:` live-region. Playwright emits that content
# two ways: inline (`log: <text>`) when the log's text is a direct child, and —
# for the real ConfrontationOverlay/NarrationScroll DOM — a bare `log:` opener
# with the prose on deeper-indented child lines (`- paragraph: ...`). The
# detector must read BOTH; reading only the inline form left it inert in
# production (162-11).
_ENEMY_REGION = re.compile(r'region\s+"(?:enem\w*|foes?|opponents?|hostiles?)"', re.IGNORECASE)
_LISTITEM = re.compile(r'listitem(?:\s*:\s*|\s+")(.+?)"?\s*$')
# The inline form REQUIRES a non-whitespace char after the colon: a bare `log:`
# opener that carries trailing whitespace must fall through to `_LOG_OPEN` (and
# be read as a nested region), not match here with an empty capture and silently
# drop the child prose (162-11 rework — the "detector returns None on a valid
# fork" silent-fallback the review caught).
_LOG = re.compile(r"\blog\s*:\s*(\S.*)$")
_LOG_OPEN = re.compile(r"\blog\s*:\s*$")
# A proper-noun phrase: capitalized words, optionally joined by lowercase
# connectors ("Molgrath the Eyeless", "Grethll of the Deep").
_PROPER_NOUN = re.compile(
    r"\b[A-Z][a-z]+(?:\s+(?:the|of|de|la|le|von|van|del|di|da)\s+[A-Z][a-z]+|\s+[A-Z][a-z]+)*"
)


def _enemy_labels(lines: list[str]) -> list[str]:
    """The foe labels listed under the aria enemy panel (`region "Enemies"`)."""
    labels: list[str] = []
    in_panel = False
    panel_indent = -1
    for line in lines:
        if _ENEMY_REGION.search(line):
            in_panel = True
            panel_indent = len(line) - len(line.lstrip())
            continue
        if not in_panel:
            continue
        # A line at or below the panel's indent closes the panel.
        if line.strip() and (len(line) - len(line.lstrip())) <= panel_indent:
            in_panel = False
            continue
        m = _LISTITEM.search(line)
        if m:
            labels.append(m.group(1).strip())
    return labels


def _node_text(line: str) -> str:
    """The visible text of one aria-snapshot line, stripped of its `- role:` /
    `- role "name"` prefix (e.g. `- paragraph: Molgrath...` → `Molgrath...`)."""
    s = re.sub(r"^-\s*", "", line.strip())
    if m := re.match(r"[\w-]+\s*:\s*(.+)$", s):  # `paragraph: text`
        return m.group(1).strip().strip('"')
    if m := re.match(r'[\w-]+\s+"(.+)"\s*$', s):  # `text "quoted"`
        return m.group(1).strip()
    if re.match(r"[\w-]+\s*:\s*$", s):  # bare role node — prose is on child lines
        return ""
    return s.strip().strip('"')


def _narration(lines: list[str]) -> str:
    """The narration prose the player reads — the content of the aria `log`
    live-region — across BOTH forms Playwright emits: inline ``log: <text>`` and
    the real nested form (a bare ``log:`` opener with prose on deeper-indented
    child lines). Once inside a log region, child lines are read as prose, so a
    literal "log:" appearing in the narration is never mistaken for a new node."""
    parts: list[str] = []
    in_log = False
    log_indent = -1
    for line in lines:
        if not line.strip():
            continue
        indent = len(line) - len(line.lstrip())
        if in_log and indent > log_indent:
            parts.append(_node_text(line))
            continue
        in_log = False
        if m := _LOG.search(line):  # inline `log: <text>`
            parts.append(m.group(1).strip())
        elif _LOG_OPEN.search(line):  # bare `log:` — prose is on the child lines
            in_log = True
            log_indent = indent
    return " ".join(p for p in parts if p)


def two_names_one_enemy(snapshot: str) -> str | None:
    """Flag the naive-player-visible identity fork (108-2 two-names-one-enemy):
    the combat panel names the single foe one way while the narration names the
    SAME foe another way.

    Screen-only, zero LLM judgment (mirrors :func:`repeated_action`): reads ONLY
    the aria ``snapshot`` the player perceives — never a creature_id, an alias
    map, or an OTEL span (that backend state would break the naivety invariant).
    "One enemy" is inferred from the screen: exactly one foe in the panel.

    Returns the conflicting narrated name when the fork is visible; ``None`` when
    the panel and narration agree, there is no single foe, or there is no combat
    panel at all (a named NPC in a non-combat scene is not a fork).
    """
    if not snapshot:
        return None
    lines = snapshot.splitlines()
    labels = _enemy_labels(lines)
    if len(labels) != 1:
        # No enemy panel, or more than one foe — two names is expected then.
        return None
    label = labels[0]
    narration = _narration(lines)
    if not narration:
        return None
    # If the panel label appears in the prose, the player has the link — clean.
    if re.search(rf"\b{re.escape(label)}\b", narration, re.IGNORECASE):
        return None
    # The narration names the foe by a name the panel never uses → the fork.
    for m in _PROPER_NOUN.finditer(narration):
        phrase = m.group(0)
        bare = re.sub(r"^(?:the|a|an)\s+", "", phrase, flags=re.IGNORECASE)
        if bare.casefold() != label.casefold():
            return phrase
    return None
