# CLAUDE.md — SideQuest Understudy (Python)

Naive simulated-player playtest client for SideQuest. Bots join a **real**
session through the actual React UI in a (headless) browser, perceive the page
the way a screen reader does, and role-play a seat in persona — one LLM call per
turn, model-agnostic (Anthropic API / Ollama / `claude -p`). It is a test
harness, not part of the runtime: nothing here ships to players.

## CRITICAL: The Naivety Invariant

**The bot is handed only what a player is handed.** This is the load-bearing
constraint and the whole reason the tool exists.

- No alias maps, no curated action menus, no fuzzy rescue, no knowledge of
  control names the screen doesn't surface.
- A bot that asks for a control that isn't there has just produced the data this
  tool collects. **Interface confusion is a *finding*, not a failure.**
- An archetype shapes *behavior and attention*, not knowledge — a mechanics-first
  bot doesn't know the dice tray exists; it wants it to and goes looking.
  "Looked and could not find" is the per-user-type finding.

Any change that smuggles engine knowledge into the bot (alias tables, action
allowlists, target-resolution fallbacks) **breaks the invariant** and invalidates
every finding. Don't add them.

## CRITICAL: Personal Project

This is a personal project under the `slabgorb-org` GitHub organization.
- **No Jira integration.** Never create, reference, or interact with Jira tickets.
- **No 1898 org.** Nothing goes to the work GitHub org. Ever.
- All live repos are under `github.com/slabgorb-org/` (use `gh ... -R slabgorb-org/<repo>`). The historical Rust prototype `sidequest-api` remains under `github.com/slabgorb/`.

## SideQuest System Overview

Six repos compose the SideQuest stack (Python backend per ADR-082, ported from the Rust prototype 2026-04):
- **sidequest-server** — Python/FastAPI game engine and WebSocket API on port 8765
- **sidequest-ui** — React/TypeScript game client (Vite, port 5173)
- **sidequest-daemon** — Python media services (image gen, music gen)
- **sidequest-content** — Genre packs (YAML configs, audio, images, world data)
- **sidequest-composer** — Standalone CLI: public-domain notation → rights-free audio
- **sidequest-understudy** *(this repo)* — Naive simulated-player playtest client

Orchestrator repo (`orc-quest`, also cloned as `oq-1` / `oq-2`) coordinates sprint tracking, docs, ADRs, and cross-repo scripts.

## Quality Rules

- No stubs, no hacks, no "we'll fix it later" shortcuts
- No skipping tests to save time
- No half-wired features — connect the full pipeline or don't start
- **Never** rescue a confused bot with engine knowledge — that's the finding, not a bug to paper over
- **Never downgrade to a "quick fix" because you think the context is "just a playtest."** This repo *is* the playtest.

### No Silent Fallbacks
If something isn't where it should be, fail loudly. A missing manifest field, an
absent reconnect-state dir, an unknown name theme — all fail loud (non-zero exit)
*before* a browser launches. Never silently substitute a default.

### No Stubbing
The only scripted brain is `fake`, used by the wiring test. Everything else
drives a real LLM against the real UI.

## Build Commands

```bash
uv sync                                 # Install deps
uv run playwright install chromium      # One-time browser install
uv run understudy run <manifest.yaml>            # Headless run
uv run understudy run <manifest.yaml> --headed   # Watch it play
uv run understudy run <manifest.yaml> --turns 20 # Override the manifest turn cap
uv run understudy run <manifest.yaml> --reconnect reports/<prior-run>  # Resume past chargen
uv run pytest                           # Tests
uv run ruff check .                     # Lint
```

From the orchestrator root: `just understudy <manifest> [flags]`.

## Architecture

```
src/understudy/
├── cli.py            # Typer entrypoint (`understudy run`)
├── orchestrate/      # Run loop, seat scheduling, guards (turn cap, token ceiling, wall clock)
├── perception/       # Screen-reader-style page reading (what the player sees)
├── brain/            # Per-turn LLM decision (model-agnostic backend dispatch)
├── actuation/        # Turning a decision into browser actions (Playwright)
├── persona/          # Archetypes + themed name sets (prompts.py:name_for_seat)
├── findings/         # Subjective complaints + objective stuck-signals → graded findings
└── report/           # report.md / findings.json / transcript / spans writers
runs/                 # Example run manifests
reports/              # Run outputs (gitignored); each run writes state/ for --reconnect
tests/
```

A run is **one YAML manifest**: `name`, `genre`, `world`, `session_url`, `seats`
(required); `turns`, `wall_clock_minutes`, `decide_timeout_s`, `settle_ms`,
`max_tokens_total`, `capture_spans`, `jaeger_url`, `name_theme` (optional). See
`README.md` for the full field reference.

**Per-seat host.** A loopback `session_url` is rewritten per seat to
`player{N}.local` (port/path preserved) so the server resolves a distinct human
identity per bot from the Host header (ADR-119) — matching real play. Add the
aliases to `/etc/hosts` once. Non-loopback URLs are left untouched.

### Archetypes (the playgroup as test matrix)

`narrative_first`, `mechanics_first`, `hesitant`, `engaged_generalist`. Add one
by dropping a YAML file in `src/understudy/persona/archetypes/`. Each seat
arrives at chargen with its own pre-decided name (themed sets harvested from the
Pennyfarthing persona themes, default `mash`) so a table reads as a recognizable
cast and two seats never collapse onto one name-keyed slot.

### Model backends

Per-seat `model` is `<backend>/<model-id>`:
- `claude_p/<model>` — **default** (`claude_p/haiku`); `claude -p` subprocess on
  subscription OAuth (API keys stripped from its env), no token metering.
- `anthropic/<model-id>` — Anthropic API; intent forced via tool call, real
  token metering, system prompt cached.
- `ollama/<model-id>` — zero-cost local lane; structured output via JSON schema.
- `fake` — scripted, no LLM; wiring test only.

### Findings grades

The reconciler joins subjective complaints and objective stuck-signals by seat
and ±1 turn:
- **CONFIRMED** — bot complained *and* harness saw friction. Trust these.
- **BEHAVIORAL** — friction without complaint; muddled through silently.
- **CLAIMED** — complaint with clean behavior. Kept, down-ranked (wolf-cry).

Malformed model output is logged as a *model* failure, never a UI failure, and
never promotes a complaint to CONFIRMED.

## Git Workflow

- Branch strategy: github-flow
- Default branch: develop
- Feature branches: `feat/{description}`
- PRs target: develop

## Design reference

`orc-quest/docs/superpowers/specs/completed/2026-06-11-simulated-player-understudy-design.md`
