# sidequest-understudy

A naive simulated-player playtest client for SideQuest. Bots join a real
session through the actual React UI in a (headless) browser, perceive the
page the way a screen reader does, and role-play a seat in persona — one
LLM call per turn, model-agnostic (Anthropic / Ollama / claude -p).

**The naivety invariant:** the bot is handed only what a player is handed.
Interface confusion is a *finding*, not a failure.

## Run a table

    uv run understudy run runs/four_seat_demo.yaml          # headless
    uv run understudy run runs/four_seat_demo.yaml --headed # watch it play

To drive a seat yourself, set one seat to `human` in the manifest and join
the session_url in your own browser.

Reports land in `reports/<date>-<name>-rN/`: `report.md`, `findings.json`
(CONFIRMED / BEHAVIORAL / CLAIMED), per-seat transcripts, and the server's
`narration.turn` OTEL spans pulled from Jaeger.

Design: `oq-2/docs/superpowers/specs/2026-06-11-simulated-player-understudy-design.md`
