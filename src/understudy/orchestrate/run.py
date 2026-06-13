"""Table runner: N isolated browser contexts, one per bot seat. Human seats
are simply not driven — the human joins the same session_url in their own
browser. Composition falls out; nothing here knows about '2 and 2'."""

from __future__ import annotations

import asyncio
import re
import time
from pathlib import Path
from urllib.parse import urlsplit, urlunsplit

import httpx
from playwright.async_api import async_playwright

from understudy.brain.llm.factory import make_model
from understudy.findings.reconcile import reconcile
from understudy.manifest import RunManifest
from understudy.orchestrate.seat import SeatRunner, TokenLedger
from understudy.persona.model import load_archetype
from understudy.report.spans import SpanCaptureEmpty, capture_run_spans
from understudy.report.write import resolve_run_dir, write_report
from understudy.orchestrate.reconnect import (
    reconnect_context_kwargs,
    seat_state_path,
    validate_reconnect_dir,
)


_LOOPBACK_HOSTS = frozenset({"localhost", "127.0.0.1", "::1"})
_PLAYER_HOST = re.compile(r"player\d+\.local\Z")


def seat_session_url(session_url: str, seat: int) -> str:
    """Give each seat its own loopback hostname: ``player{seat}.local``.

    The server resolves the *human* player identity from the Host header
    (``player_identity.resolve_player_identity``, ADR-119); local dev is meant to
    distinguish players exactly this way (player1.local, player2.local — mapped to
    127.0.0.1 in /etc/hosts). Sharing ``localhost`` hands every seat the same human
    identity and the same browser origin, a one-human-drives-N-seats state that
    never occurs in real play and only invites bugs. Scheme, port, and path are
    preserved, so the deterministic session slug is untouched and all seats land in
    the same multiplayer session. A non-loopback host (a real deployment behind
    Cloudflare Access, where identity comes from the Cf-Access email) is returned
    unchanged — no rewrite, no silent breakage.
    """
    if seat < 1:
        raise ValueError(f"seat is 1-based; got {seat!r}")
    parts = urlsplit(session_url)
    host = parts.hostname or ""
    if host not in _LOOPBACK_HOSTS and not _PLAYER_HOST.match(host):
        return session_url
    netloc = f"player{seat}.local"
    if parts.port is not None:
        netloc = f"{netloc}:{parts.port}"
    return urlunsplit((parts.scheme, netloc, parts.path, parts.query, parts.fragment))


async def run_table(
    manifest: RunManifest,
    *,
    headed: bool = False,
    out_root: Path = Path("reports"),
    reconnect: Path | None = None,
    model_factory=make_model,  # injection seam for the wiring test
) -> int:
    """Returns a process exit code: 0 ok, 1 span-capture failure (run report
    still written — the artifact is partial, and that is said loudly)."""
    bot_seats = [
        (idx, spec) for idx, spec in enumerate(manifest.seats, start=1) if spec.archetype != "human"
    ]
    if reconnect is not None:
        validate_reconnect_dir(reconnect, [idx for idx, _ in bot_seats])
    out_dir = resolve_run_dir(out_root, manifest.name)
    for idx, spec in enumerate(manifest.seats, start=1):
        if spec.archetype == "human":
            # Join at this seat's own host so the human is a distinct player too.
            print(f"seat {idx}: human — join {seat_session_url(manifest.session_url, idx)} yourself")

    ledger = TokenLedger(ceiling=manifest.max_tokens_total)
    deadline = time.monotonic() + manifest.wall_clock_minutes * 60.0
    run_start_us = int(time.time() * 1_000_000)

    async with async_playwright() as pw:
        browser = await pw.chromium.launch(headless=not headed)
        runners: list[SeatRunner] = []
        seat_contexts: list[tuple[int, object]] = []  # (idx, BrowserContext)
        for idx, spec in bot_seats:
            context_kwargs = reconnect_context_kwargs(reconnect, idx)
            if headed:
                # Watching it: fill the real OS window. Headless keeps Playwright's
                # deterministic 1280×720 default so the tested breakpoint doesn't shift.
                context_kwargs["no_viewport"] = True
            context = await browser.new_context(**context_kwargs)
            seat_contexts.append((idx, context))
            page = await context.new_page()
            await page.goto(seat_session_url(manifest.session_url, idx))
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
                    world=manifest.world,
                    genre=manifest.genre,
                    party_size=len(manifest.seats),  # humans count — they share the table
                    name_theme=manifest.name_theme,
                )
            )
        all_rows_nested = await asyncio.gather(*(r.run() for r in runners))
        (out_dir / "state").mkdir(parents=True, exist_ok=True)
        for idx, context in seat_contexts:
            await context.storage_state(path=str(seat_state_path(out_dir, idx)))
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

    out = write_report(out_root, manifest, rows, findings, spans, spans_error, run_dir=out_dir)
    print(f"report: {out}")
    if manifest.capture_spans and not spans:
        print("SPAN CAPTURE FAILED — run was not traced or Jaeger unreachable")
        return 1
    return 0
