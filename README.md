# sidequest-understudy

A naive simulated-player playtest client for SideQuest. Bots join a real
session through the actual React UI in a (headless) browser, perceive the
page the way a screen reader does, and role-play a seat in persona — one
LLM call per turn, model-agnostic (Anthropic / Ollama / claude -p).

**The naivety invariant:** the bot is handed only what a player is handed.
Interface confusion is a *finding*, not a failure. There are no alias maps,
no curated action menus, no fuzzy rescue. A bot that asks for a control
that isn't there has just produced the data this tool exists to collect.

## Setup (once)

    uv sync
    uv run playwright install chromium

## Run a table

    uv run understudy run runs/four_seat_demo.yaml          # headless
    uv run understudy run runs/four_seat_demo.yaml --headed # watch it play
    uv run understudy run runs/four_seat_demo.yaml --turns 20  # override the manifest's turn cap

To drive a seat yourself, set one seat to `human` in the manifest and join
the session_url in your own browser. Human seats are simply not driven by
this process — composition falls out for free.

Reports land in `reports/<date>-<name>-rN/` (override the root with `--out`):

| File                  | What it is |
|-----------------------|------------|
| `report.md`           | Human-readable summary: graded findings + per-seat stats |
| `findings.json`       | Machine-readable findings (CONFIRMED / BEHAVIORAL / CLAIMED) |
| `transcript/seat-N.jsonl` | One row per perceive→decide→act→observe cycle |
| `spans.jsonl`         | Server-side `narration.turn` OTEL spans pulled from Jaeger |

**Exit codes:** `0` run completed and spans captured (or capture disabled);
`1` run completed but span capture failed — the report exists, the engine-side
trace is missing; `2` manifest invalid or missing.

## Reconnect (skip chargen)

Every run automatically snapshots each bot seat's browser state to
`reports/<run>/state/seat-{idx}.json`. Re-run with `--reconnect` pointed at a
prior run's report dir to restore that state — the bot's lobby surfaces its
one-click resume entry and it rejoins its character past chargen, so the turn
budget goes to play instead of character creation.

    uv run understudy run runs/four_seat_demo.yaml                          # run 1: chargen + play; writes state/
    uv run understudy run runs/four_seat_demo.yaml --reconnect reports/<run1>  # run 2: resume, skip chargen

The reconnect run must declare the same seat order and count as the seed run
(same manifest is the normal case); mapping is by seat index. A missing or
incomplete `<DIR>/state/` fails loud (exit 2) before any browser launches. If a
stored session no longer loads (server restarted, different day), the bot
naively falls into chargen — a legitimate finding, not a suppressed error.
Reconnect targets the iterate-on-play loop within a session's life, not
long-term replay.

## The manifest

A run is declared in one YAML file. Required fields:

```yaml
name: four_seat_demo          # report directory naming
genre: mutant_wasteland       # with world: the table's social contract — told to each
world: flickering_reach       #   bot as intent ("the group agreed on this world",
                              #   multiplayer when seats > 1), never as UI instructions
session_url: http://localhost:5173   # explicit, never derived
seats:
  - engaged_generalist                          # bare string = archetype, default model
  - { archetype: hesitant, model: ollama/qwen3:8b }  # per-seat model override
  - human                                       # not driven; join it yourself
```

Optional fields and their defaults:

| Field               | Default                  | Meaning |
|---------------------|--------------------------|---------|
| `turns`             | `12`                     | max perceive→act cycles per seat |
| `wall_clock_minutes`| `30.0`                   | hard deadline for the whole run |
| `decide_timeout_s`  | `120.0`                  | per-turn LLM decision timeout |
| `settle_ms`         | `4000`                   | wait after each action before re-perceiving |
| `max_tokens_total`  | none                     | shared token ceiling across all seats; breach = graceful stop, partial report |
| `capture_spans`     | `true`                   | pull `narration.turn` spans from Jaeger after the run |
| `jaeger_url`        | `http://localhost:16686` | where to pull them from |

Every guard (turn cap, token ceiling, decide timeout, wall clock) ends in a
partial transcript and a written report — never a hung process.

## Archetypes

The playgroup as test matrix. An archetype shapes *behavior and attention*,
not knowledge — a mechanics-first bot doesn't know the dice tray exists; it
wants it to exist and goes looking. "Looked and could not find" is the
per-user-type finding.

| Archetype            | Plays like |
|----------------------|------------|
| `narrative_first`    | Story prose, ignores buttons and numbers unless needed, reads everything |
| `mechanics_first`    | Hunts for the roll, the cost, the delta; probes controls and panels |
| `hesitant`           | Short plain actions; waits when unsure; says so rather than guess |
| `engaged_generalist` | Experienced, deliberate, probes methodically |

Add one by dropping a YAML file in `src/understudy/persona/archetypes/`.

Each seat arrives at chargen with its **own character name already in mind**,
assigned by seat index (`persona/prompts.py:name_for_seat`). A naive LLM faced
with an empty free-text name field free-associates the same pet name ("Kael")
from its own prior on every seat — it isn't reading a default off the screen,
the bias is in the model — and the engine keys seated characters *by name*, so
two same-named PCs in one session collapse onto a single slot.

The names come in **themed sets** harvested from the Pennyfarthing persona
themes (`THEME_SETS`), one set per table, so a save reads at a glance as a
recognizable cast — the default `mash` table seats Hawkeye, Potter, Radar,
Winchester… Pick another with `name_theme:` in the manifest (e.g. `firefly`,
`discworld`, `princess_bride`); an unknown theme fails loud. Pre-deciding the name per seat keeps a table
collision-free. A name is content the player brings, not interface knowledge, so
the naivety invariant holds.

## Models

Per-seat `model` spec is `<backend>/<model-id>`:

- `claude_p/<model>` — default (`claude_p/haiku`); `claude -p` subprocess, bills to the
  operator's subscription plan, no token metering (the token ledger only guards
  API-backend spend). The subprocess runs with `ANTHROPIC_API_KEY`/`ANTHROPIC_ADMIN_KEY`
  stripped from its env so it uses subscription OAuth, never the metered API — with no
  subscription login it fails loud rather than silently billing per-token.
- `anthropic/<model-id>` — Anthropic API; intent forced via tool call, real token
  metering. The per-seat system prompt is cached, so each turn after the first re-reads
  it at ~0.1× input cost; reported `input_tokens` still sums cached + uncached, so
  `max_tokens_total` bounds true volume — only the bill drops, not the ceiling.
- `ollama/<model-id>` — zero-cost local lane; structured output via JSON schema
- `fake` — scripted brain, no LLM; used by the wiring test

## How findings are graded

The harness keeps two streams per seat: the bot's *subjective* complaints
(`report_confusion` intents) and *objective* stuck-signals it observed with
zero LLM judgment (failed target resolution, ambiguous duplicate controls,
repeated identical actions, decide timeouts, console errors, screens with no
operable controls). The reconciler joins them by seat and ±1 turn:

- **CONFIRMED** — the bot complained *and* the harness saw friction. Trust these.
- **BEHAVIORAL** — friction without complaint; the bot muddled through silently.
- **CLAIMED** — complaint with clean behavior. Kept, but down-ranked: wolf-cry candidate.

Malformed model output is logged as a model failure, not a UI failure, and
never promotes a complaint to CONFIRMED.

Design: `oq-2/docs/superpowers/specs/completed/2026-06-11-simulated-player-understudy-design.md`
