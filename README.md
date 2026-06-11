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

## Models

Per-seat `model` spec is `<backend>/<model-id>`:

- `claude_p/<model>` — default (`claude_p/haiku`); `claude -p` subprocess, bills to the
  operator's plan, no token metering (the token ledger only guards API-backend spend)
- `anthropic/<model-id>` — Anthropic API; intent forced via tool call, real token metering
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
