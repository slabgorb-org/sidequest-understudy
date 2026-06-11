"""Table runner: N isolated browser contexts, one per bot seat. Human seats
are simply not driven — the human joins the same session_url in their own
browser. Composition falls out; nothing here knows about '2 and 2'."""

from __future__ import annotations

import asyncio
import time
from pathlib import Path

import httpx
from playwright.async_api import async_playwright

from understudy.brain.llm.factory import make_model
from understudy.findings.reconcile import reconcile
from understudy.manifest import RunManifest
from understudy.orchestrate.seat import SeatRunner, TokenLedger
from understudy.persona.model import load_archetype
from understudy.report.spans import SpanCaptureEmpty, capture_run_spans
from understudy.report.write import write_report


async def run_table(
    manifest: RunManifest,
    *,
    headed: bool = False,
    out_root: Path = Path("reports"),
    model_factory=make_model,  # injection seam for the wiring test
) -> int:
    """Returns a process exit code: 0 ok, 1 span-capture failure (run report
    still written — the artifact is partial, and that is said loudly)."""
    bot_seats = [
        (idx, spec) for idx, spec in enumerate(manifest.seats, start=1) if spec.archetype != "human"
    ]
    for idx, spec in enumerate(manifest.seats, start=1):
        if spec.archetype == "human":
            print(f"seat {idx}: human — join {manifest.session_url} yourself")

    ledger = TokenLedger(ceiling=manifest.max_tokens_total)
    deadline = time.monotonic() + manifest.wall_clock_minutes * 60.0
    run_start_us = int(time.time() * 1_000_000)

    async with async_playwright() as pw:
        browser = await pw.chromium.launch(headless=not headed)
        runners: list[SeatRunner] = []
        for idx, spec in bot_seats:
            context = await browser.new_context()
            page = await context.new_page()
            await page.goto(manifest.session_url)
            runners.append(
                SeatRunner(
                    seat=idx,
                    archetype=load_archetype(spec.archetype),
                    model=model_factory(spec.model),
                    page=page,
                    turns=manifest.turns,
                    decide_timeout_s=manifest.decide_timeout_s,
                    settle_ms=manifest.settle_ms,
                    ledger=ledger,
                    deadline=deadline,
                )
            )
        all_rows_nested = await asyncio.gather(*(r.run() for r in runners))
        await browser.close()

    run_end_us = int(time.time() * 1_000_000)
    rows = [row for seat_rows in all_rows_nested for row in seat_rows]
    archetype_by_seat = {idx: spec.archetype for idx, spec in bot_seats}
    findings = reconcile(rows, archetype_by_seat)

    spans: list[dict] | None = None
    spans_error: str | None = None
    if manifest.capture_spans:
        try:
            spans = await capture_run_spans(
                manifest.jaeger_url, run_start_us=run_start_us, run_end_us=run_end_us
            )
        except (httpx.HTTPError, SpanCaptureEmpty) as exc:
            spans_error = str(exc)

    out = write_report(out_root, manifest, rows, findings, spans, spans_error)
    print(f"report: {out}")
    if manifest.capture_spans and not spans:
        print("SPAN CAPTURE FAILED — run was not traced or Jaeger unreachable")
        return 1
    return 0
