"""Jaeger span capture — port of scripts/playtest.py's Phase-E capture
(orchestrator repo, lines 127-300). The server's narration.turn spans are the
engine-side lie detector: bot said X, harness saw Y, spans say Z."""

from __future__ import annotations

import asyncio
import json
import time
from pathlib import Path
from typing import Any

import httpx

# OTEL service.name the server registers (telemetry/setup.py default).
JAEGER_SERVICE = "sidequest-server"

# The span we gate on. If zero of these are present for the run after the
# settle window, the run was not traced — fail loud, never an empty file.
NARRATION_TURN_SPAN = "narration.turn"


class SpanCaptureEmpty(RuntimeError):
    """Raised when a --span-jsonl capture would be empty.

    An empty capture is never written silently: it means the run wasn't
    traced (operator forgot ``just up-traced`` / wrong --jaeger-url /
    Jaeger down). Per CLAUDE.md "No Silent Fallbacks" this is surfaced
    loudly and maps to exit code 1.
    """


def flatten_jaeger_tags(tags: list[dict[str, Any]]) -> dict[str, Any]:
    """Flatten a Jaeger span ``tags`` array into a plain dict.

    Jaeger v2's query API emits each tag as ``{key, type, value}`` with
    the value already typed (int64/float64/bool/string). We keep the
    native Python value so ``narration.turn.total_input_tokens`` stays an
    int and ``narration.turn.tool_calls_json`` stays its JSON string
    verbatim (it is double-decoded by the consumer, not here).
    """
    flat: dict[str, Any] = {}
    for tag in tags or []:
        key = tag.get("key")
        if key is None:
            continue
        flat[key] = tag.get("value")
    return flat


def _parent_span_id(span: dict[str, Any]) -> str | None:
    """Return the CHILD_OF parent spanID, or None for a root span."""
    for ref in span.get("references") or []:
        if ref.get("refType") == "CHILD_OF" and ref.get("spanID"):
            return ref["spanID"]
    return None


def jaeger_span_to_record(span: dict[str, Any]) -> dict[str, Any]:
    """Convert one Jaeger query-API span into a JSONL record.

    Preserves name, span/trace/parent ids, start (μs since epoch) and
    duration (μs), plus the full flattened attribute dict — so a
    ``narration.turn`` record carries ``narration.turn.tool_calls_json``,
    ``.model_chosen``, the token rollups and ``.tool_call_count``.
    """
    return {
        "name": span.get("operationName", ""),
        "span_id": span.get("spanID", ""),
        "trace_id": span.get("traceID", ""),
        "parent_span_id": _parent_span_id(span),
        "start_us": int(span.get("startTime", 0)),
        "duration_us": int(span.get("duration", 0)),
        "attributes": flatten_jaeger_tags(span.get("tags") or []),
    }


def traces_to_jsonl_records(payload: dict[str, Any]) -> list[dict[str, Any]]:
    """Flatten a Jaeger ``/api/traces`` payload to a flat span-record list.

    Jaeger groups spans under traces (``payload["data"][].spans[]``); the
    JSONL is one object per span across every trace in the payload, so the
    parent/child tree is reconstructable downstream from
    ``span_id``/``parent_span_id``.
    """
    records: list[dict[str, Any]] = []
    for trace in payload.get("data") or []:
        for span in trace.get("spans") or []:
            records.append(jaeger_span_to_record(span))
    return records


def write_span_jsonl(records: list[dict[str, Any]], path: Path) -> int:
    """Write span records to ``path`` as JSONL. Returns the count written.

    Refuses to write an empty file: zero records means the run wasn't
    traced and a 0-byte success artifact would silently pass the parity
    gate. Raises :class:`SpanCaptureEmpty` instead (no file touched).
    """
    if not records:
        raise SpanCaptureEmpty(
            "refusing to write an empty span JSONL — zero spans captured"
        )
    lines = "\n".join(json.dumps(rec, sort_keys=True) for rec in records)
    path.write_text(lines + "\n")
    return len(records)


def _now_us() -> int:
    """Wall-clock microseconds since epoch (Jaeger query time unit)."""
    return int(time.time() * 1_000_000)


async def _query_jaeger_traces(
    jaeger_url: str,
    *,
    service: str,
    start_us: int,
    end_us: int,
    limit: int = 200,
) -> dict[str, Any]:
    """GET Jaeger's /api/traces scoped to one service + wall-clock window.

    Jaeger's classic query API (Jaeger v2 keeps it UI-compatible) takes
    ``start``/``end`` in microseconds since epoch. Scoping by both the
    service name AND the run's time window keeps stale traces from
    previous runs out of the capture.
    """
    params = {
        "service": service,
        "start": str(start_us),
        "end": str(end_us),
        "limit": str(limit),
    }
    async with httpx.AsyncClient(timeout=15.0) as client:
        resp = await client.get(f"{jaeger_url.rstrip('/')}/api/traces", params=params)
        resp.raise_for_status()
        try:
            return resp.json()
        except json.JSONDecodeError as exc:
            # A reverse proxy / wrong --jaeger-url can answer HTTP 200 with
            # an HTML error page. That is NOT an httpx.HTTPError, so a raw
            # JSONDecodeError would escape amain's handler as a traceback.
            # Re-raise as httpx.HTTPError so the existing fail-loud path
            # (clean "[span-jsonl] Jaeger query failed" + exit 1, no file)
            # handles it identically to an unreachable Jaeger — no silent
            # fallback.
            raise httpx.HTTPError(
                f"Jaeger returned non-JSON from {resp.request.url} "
                f"(HTTP {resp.status_code}, content-type "
                f"{resp.headers.get('content-type', '?')!r}): {exc}"
            ) from exc


async def capture_run_spans(
    jaeger_url: str,
    *,
    run_start_us: int,
    run_end_us: int,
    settle_attempts: int = 8,
    settle_interval: float = 1.5,
) -> list[dict[str, Any]]:
    """Poll Jaeger until this run's narration.turn spans land, then return all.

    The server's gRPC OTLP exporter batches with a ~2 s schedule delay
    (telemetry/setup.py: schedule_delay_millis=2000), so a single query
    fired the instant the scenario ends races the export. We poll with a
    bounded settle (default ~12 s total) until at least one
    ``narration.turn`` span for the window appears, then return every span
    in the window so children (llm.request / tool.*) ride along.

    Raises :class:`SpanCaptureEmpty` if no narration.turn span ever
    appears, and lets ``httpx`` errors propagate (Jaeger unreachable is a
    loud failure, not a silent empty capture).
    """
    last_records: list[dict[str, Any]] = []
    for attempt in range(1, settle_attempts + 1):
        # Re-read the window end each poll so spans that close *after* the
        # scenario loop exits (trailing narration flush) are still caught.
        # max() guards a backward wall-clock step (NTP slew); _now_us()
        # normally wins so run_end_us is the floor, not the typical value.
        payload = await _query_jaeger_traces(
            jaeger_url,
            service=JAEGER_SERVICE,
            start_us=run_start_us,
            end_us=max(run_end_us, _now_us()),
        )
        last_records = traces_to_jsonl_records(payload)
        has_turn = any(r["name"] == NARRATION_TURN_SPAN for r in last_records)
        if has_turn:
            return last_records
        if attempt < settle_attempts:
            await asyncio.sleep(settle_interval)

    raise SpanCaptureEmpty(
        f"no {NARRATION_TURN_SPAN!r} spans found in Jaeger ({jaeger_url}) "
        f"for service {JAEGER_SERVICE!r} in the run window after "
        f"{settle_attempts} polls (~{settle_attempts * settle_interval:.0f}s). "
        f"Saw {len(last_records)} other span(s). The run was not traced — "
        f"start Jaeger ('just jaeger') and the server with OTEL export "
        f"('just up-traced', SIDEQUEST_OTLP_ENDPOINT=localhost:4317)."
    )
