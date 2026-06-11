"""Reconciler: join the subjective stream (report_confusion intents) against
the objective stream (FrictionSignals) by seat + turn-window and grade:

CONFIRMED  — both agree (complaint + hard signal within ±1 turn, same seat)
BEHAVIORAL — objective only: the bot muddled through without complaining
CLAIMED    — subjective only: complaint with clean behavior (kept, down-ranked)

MODEL_ERROR signals are down-weighted: they are model failures, not UI
failures, and never promote a complaint to CONFIRMED.
"""

from __future__ import annotations

from understudy.types import (
    Finding,
    FrictionSignal,
    Grade,
    IntentKind,
    SignalKind,
    TranscriptRow,
)

_DOWNWEIGHTED = {SignalKind.MODEL_ERROR}
_WINDOW = 1  # turns either side of a complaint


def _hard_signals(rows: list[TranscriptRow]) -> list[FrictionSignal]:
    return [s for r in rows for s in r.signals if s.kind not in _DOWNWEIGHTED]


def reconcile(rows: list[TranscriptRow], archetype_by_seat: dict[int, str]) -> list[Finding]:
    findings: list[Finding] = []
    seats = sorted({r.seat for r in rows})
    for seat in seats:
        seat_rows = sorted((r for r in rows if r.seat == seat), key=lambda r: r.turn)
        hard = _hard_signals(seat_rows)
        archetype = archetype_by_seat.get(seat, "unknown")

        # Subjective pass: every complaint becomes CONFIRMED or CLAIMED.
        complaint_windows: set[int] = set()
        for row in seat_rows:
            if row.intent is None or row.intent.kind is not IntentKind.REPORT_CONFUSION:
                continue
            window = [s for s in hard if abs(s.turn - row.turn) <= _WINDOW]
            grade = Grade.CONFIRMED if window else Grade.CLAIMED
            complaint_windows.update(t for t in range(row.turn - _WINDOW, row.turn + _WINDOW + 1))
            findings.append(
                Finding(
                    grade=grade,
                    seat=seat,
                    archetype=archetype,
                    turn=row.turn,
                    confusion_reason=row.intent.reason,
                    signals=window,
                    snapshot_excerpt=row.snapshot[:800],
                )
            )

        # Objective pass: hard friction with no nearby complaint → BEHAVIORAL.
        for row in seat_rows:
            row_hard = [s for s in row.signals if s.kind not in _DOWNWEIGHTED]
            if row_hard and row.turn not in complaint_windows:
                findings.append(
                    Finding(
                        grade=Grade.BEHAVIORAL,
                        seat=seat,
                        archetype=archetype,
                        turn=row.turn,
                        confusion_reason=None,
                        signals=row_hard,
                        snapshot_excerpt=row.snapshot[:800],
                    )
                )
    return findings
