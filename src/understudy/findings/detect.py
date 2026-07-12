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
    `- role "name"` prefix (e.g. `- paragraph: Molgrath...` → `Molgrath...`).
    Non-prose tokens yield "" and never leak into narration: bare role nodes
    (`- paragraph:`), VALUELESS role tokens (`- separator` — the <hr> per
    NARRATION_END; it fell through and became a phantom "separator" beat,
    final-review Finding 1a), property lines (`- /url: "#footnote-1"`), and
    quoted-name openers whose content is on child lines (`- link "1":`)."""
    s = re.sub(r"^-\s*", "", line.strip())
    if s.startswith("/"):  # `/url: ...` — a node property, not a node
        return ""
    if m := re.match(r"[\w-]+\s*:\s*(.+)$", s):  # `paragraph: text`
        return m.group(1).strip().strip('"')
    if m := re.match(r'[\w-]+\s+"(.+)"\s*$', s):  # `text "quoted"`
        return m.group(1).strip()
    if re.match(r"[\w-]+\s*:\s*$", s):  # bare role node — prose is on child lines
        return ""
    if re.match(r"[\w-]+$", s):  # valueless role token (`separator`) — not prose
        return ""
    if re.match(r'[\w-]+\s+".*"\s*:\s*$', s):  # `link "1":` opener — content is children
        return ""
    return s.strip().strip('"')


def _narration_entries(lines: list[str]) -> list[str]:
    """The individual narration beats inside the aria `log` live-region(s), in
    screen order — the granular list `_narration` joins into one string. Reads
    BOTH forms Playwright emits: inline ``log: <text>`` (one beat) and the real
    nested form (a bare ``log:`` opener with each beat on its own deeper-indented
    child line — the shipped NarrationScroll accumulates one `<p>` per beat).
    Once inside a log region, child lines are read as prose, so a literal
    "log:" appearing in the narration is never mistaken for a new node. Empty
    wrapper nodes (a bare role line whose text lives on a still-deeper child)
    are dropped, never leaking a role token as a phantom beat."""
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
    return [p for p in parts if p]


def _narration(lines: list[str]) -> str:
    """The narration prose the player reads — the content of the aria `log`
    live-region(s) — as one joined string. See `_narration_entries` for the
    per-beat breakdown this is built from."""
    return " ".join(_narration_entries(lines))


# Roles inside the log region (empirically, from Playwright aria_snapshot over
# the shipped NarrationScroll DOM): each markdown <p> is `- paragraph:`; the
# player's echoed action and turn-status/gallery-notice chrome are `- text:`;
# each NARRATION_END <hr> is a bare `- separator`. Only paragraphs are the
# narrator's prose.
_CHILD_ROLE = re.compile(r"^-\s*([\w-]+)")


def _log_prose_turns(lines: list[str]) -> list[str]:
    """Narration PROSE grouped into TURNS — separator-delimited groups of
    paragraph text inside the aria `log` live-region(s), in screen order.

    Unlike :func:`_narration_entries` (every node, flat), this walker keeps
    only what the narrator wrote: `paragraph` nodes — including prose that
    inline markup (**bold** foe names, footnote sups) pushes onto deeper
    child lines — and the idealized inline ``log: <text>`` form. Player
    echoes and system chrome (`text` nodes) are NOT the story naming a foe
    and are excluded; `separator` nodes (one per NARRATION_END) delimit the
    turns and never leak as prose (final-review Finding 1)."""
    turns: list[str] = []
    current: list[str] = []

    def close_turn() -> None:
        if current:
            turns.append(" ".join(current))
            current.clear()

    in_log = False
    log_indent = -1
    in_para = False
    para_indent = -1
    for line in lines:
        if not line.strip():
            continue
        indent = len(line) - len(line.lstrip())
        if in_log and indent > log_indent:
            if in_para and indent > para_indent:  # inline-markup child of a paragraph
                if text := _node_text(line):
                    current.append(text)
                continue
            in_para = False
            m = _CHILD_ROLE.match(line.strip())
            role = m.group(1) if m else None
            if role == "separator":  # the NARRATION_END <hr> — a turn boundary
                close_turn()
            elif role == "paragraph":
                if text := _node_text(line):
                    current.append(text)
                in_para = True  # markup may have pushed prose onto child lines
                para_indent = indent
            # anything else (text: echoes/chrome, images, groups) is not prose
            continue
        in_log = False
        in_para = False
        if m := _LOG.search(line):  # inline `log: <text>` — a one-beat turn
            close_turn()
            turns.append(m.group(1).strip())
        elif _LOG_OPEN.search(line):  # bare `log:` — prose is on the child lines
            in_log = True
            log_indent = indent
    close_turn()
    return turns


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


# The wrong-Other window, in narration TURNS (separator-delimited prose
# groups), NOT aria nodes (final-review Finding 1: node-counting had ~1
# paragraph of effective depth against the shipped segment mix and fired on a
# CORRECT server). Realistic narrator turns run 2-4 paragraphs and name the
# foe in the OPENING one; two full turns of story (~4-8 paragraphs) that never
# name the seated foe is the wrong-Other signal.
WRONG_OTHER_WINDOW = 2


def wrong_other(snapshot: str, window: int = WRONG_OTHER_WINDOW) -> list[str]:
    """Flag the naive-player-visible wrong-Other regression (166-5, closed
    server-side by ADR-156's Green Room materializer + target-first seater):
    the Enemies panel seats a foe whose name never appears anywhere in the
    last `window` narration TURNS — evidence the engine seated somebody the
    story isn't about.

    Screen-only, zero LLM judgment (mirrors :func:`two_names_one_enemy`): reads
    ONLY the aria ``snapshot`` the player perceives via `_enemy_labels` and
    `_log_prose_turns` — never a creature_id, an origin tier, or a
    `green_room.materialized` span (that backend state would break the
    naivety invariant). Only narration PROSE is judged (paragraph nodes /
    inline log text, grouped into separator-delimited turns); the player's
    own echoed action and system chrome are not the story naming a foe.

    Each Enemies listitem is its own DISTINCT seated foe (the shipped panel
    exposes one plain name per foe), so every foe is judged independently and
    every absent one is reported. The classic 166-5 shape seats the CORRECT
    target plus a mechanically-convenient bystander: the narration names the
    target — it's the story target — and never the bystander, and the
    bystander must not hide behind the target's mentions.

    Matching is a case-insensitive substring test on both sides (the brief's
    chosen normalization) — no word-boundary requirement, so possessives
    ("the Grazer's claws") and mid-sentence mentions still suppress. Two
    documented, accepted edges: an epithet the panel doesn't display ("the
    Scrapborn" vs a panel label of "Ihnsch of the Rusted Works") will NOT
    suppress — the naive bot has no screen-visible link between them, so that
    reads as the same fork a real player would see (don't over-suppress);
    and a short panel label swallowed by a LONGER narrated name ("Grazer" ⊂
    "Resonance Grazer-kin") wrongly suppresses — an accepted false negative
    of substring matching.

    Returns the panel display names of every seated foe absent from the
    recent turns, in panel order; empty when there are no seated foes, no
    narration yet to judge against, or every foe is named.
    """
    if not snapshot:
        return []
    lines = snapshot.splitlines()
    labels = _enemy_labels(lines)
    if not labels:
        return []
    turns = _log_prose_turns(lines)
    if not turns:
        return []
    recent = [turn.casefold() for turn in turns[-window:]]
    return [label for label in labels if not any(label.casefold() in turn for turn in recent)]
