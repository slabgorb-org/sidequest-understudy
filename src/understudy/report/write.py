"""Report artifact — one self-contained directory per run.

reports/<date>-<name>-rN/
├── report.md          human-readable summary + graded findings
├── findings.json      machine-readable (the deferred ping-pong seam reads this)
├── transcript/        per-seat per-turn JSONL
└── spans.jsonl        server-side narration.turn OTEL spans (when captured)
"""

from __future__ import annotations

import datetime
import json
from pathlib import Path

from understudy.manifest import RunManifest
from understudy.report.spans import write_span_jsonl
from understudy.types import Finding, Grade, TranscriptRow


def _next_run_dir(root: Path, name: str) -> Path:
    today = datetime.date.today().isoformat()
    n = 1
    while (root / f"{today}-{name}-r{n}").exists():
        n += 1
    out = root / f"{today}-{name}-r{n}"
    out.mkdir(parents=True)
    return out


def _findings_table(findings: list[Finding]) -> str:
    if not findings:
        return "_No findings — clean run._\n"
    lines = ["| Grade | Seat | Archetype | Turn | Summary |", "|---|---|---|---|---|"]
    order = {Grade.CONFIRMED: 0, Grade.BEHAVIORAL: 1, Grade.CLAIMED: 2}
    for f in sorted(findings, key=lambda f: (order[f.grade], f.seat, f.turn)):
        summary = f.confusion_reason or "; ".join(s.kind.value for s in f.signals)
        summary = summary.replace("|", "\\|").replace("\n", " ")
        lines.append(
            f"| {f.grade.value} | {f.seat} | {f.archetype} | {f.turn} | {summary} |"
        )
    return "\n".join(lines) + "\n"


def _seat_stats(rows: list[TranscriptRow]) -> str:
    lines = ["| Seat | Turns | Acts | Waits | Confusions | Failed resolves |", "|---|---|---|---|---|---|"]
    for seat in sorted({r.seat for r in rows}):
        sr = [r for r in rows if r.seat == seat]
        acts = sum(1 for r in sr if r.intent and r.intent.kind.value == "act")
        waits = sum(1 for r in sr if r.intent and r.intent.kind.value == "wait")
        conf = sum(1 for r in sr if r.intent and r.intent.kind.value == "report_confusion")
        failed = sum(1 for r in sr if r.resolution == "failed")
        lines.append(f"| {seat} | {len(sr)} | {acts} | {waits} | {conf} | {failed} |")
    return "\n".join(lines) + "\n"


def write_report(
    out_root: Path,
    manifest: RunManifest,
    rows: list[TranscriptRow],
    findings: list[Finding],
    spans: list[dict] | None,
    spans_error: str | None,
) -> Path:
    out = _next_run_dir(out_root, manifest.name)

    (out / "findings.json").write_text(
        json.dumps([f.model_dump(mode="json") for f in findings], indent=2) + "\n"
    )

    tdir = out / "transcript"
    tdir.mkdir()
    for seat in sorted({r.seat for r in rows}):
        seat_rows = [r for r in rows if r.seat == seat]
        (tdir / f"seat-{seat}.jsonl").write_text(
            "\n".join(r.model_dump_json() for r in seat_rows) + "\n"
        )

    spans_note = ""
    if spans:
        n = write_span_jsonl(spans, out / "spans.jsonl")
        spans_note = f"{n} server spans captured (spans.jsonl)."
    elif spans_error:
        spans_note = f"**SPANS MISSING** — {spans_error}"
    elif manifest.capture_spans:
        spans_note = "**SPANS MISSING** — zero narration.turn spans found for the run window."
    else:
        spans_note = "span capture disabled for this run (capture_spans: false)."

    counts = {g: sum(1 for f in findings if f.grade is g) for g in Grade}
    (out / "report.md").write_text(
        f"# Understudy run — {manifest.name}\n\n"
        f"- **Genre/world:** {manifest.genre} / {manifest.world}\n"
        f"- **Session:** {manifest.session_url}\n"
        f"- **Seats:** {', '.join(s.archetype for s in manifest.seats)}\n"
        f"- **Findings:** {counts[Grade.CONFIRMED]} confirmed, "
        f"{counts[Grade.BEHAVIORAL]} behavioral, {counts[Grade.CLAIMED]} claimed\n"
        f"- **OTEL:** {spans_note}\n\n"
        f"## Findings\n\n{_findings_table(findings)}\n"
        f"## Per-seat outcomes\n\n{_seat_stats(rows)}"
    )
    return out
