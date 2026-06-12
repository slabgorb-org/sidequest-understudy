import json

import pytest

from understudy.manifest import RunManifest, SeatSpec
from understudy.report.spans import (
    SpanCaptureEmpty,
    flatten_jaeger_tags,
    traces_to_jsonl_records,
    write_span_jsonl,
)
from understudy.report.write import write_report
from understudy.types import (
    Finding,
    Grade,
    Intent,
    IntentKind,
    TranscriptRow,
)

JAEGER_PAYLOAD = {
    "data": [
        {
            "spans": [
                {
                    "operationName": "narration.turn",
                    "spanID": "abc",
                    "traceID": "t1",
                    "references": [{"refType": "CHILD_OF", "spanID": "root"}],
                    "startTime": 1000,
                    "duration": 50,
                    "tags": [{"key": "narration.turn.model_chosen", "value": "haiku"}],
                }
            ]
        }
    ]
}


def test_flatten_tags_keeps_native_values():
    flat = flatten_jaeger_tags([{"key": "k", "value": 7}, {"key": "s", "value": "x"}])
    assert flat == {"k": 7, "s": "x"}


def test_traces_flatten_to_records_with_parent():
    recs = traces_to_jsonl_records(JAEGER_PAYLOAD)
    assert recs[0]["name"] == "narration.turn"
    assert recs[0]["parent_span_id"] == "root"


def test_empty_span_write_refuses(tmp_path):
    with pytest.raises(SpanCaptureEmpty):
        write_span_jsonl([], tmp_path / "spans.jsonl")


def _manifest():
    return RunManifest(
        name="t",
        genre="g",
        world="w",
        session_url="http://x/p",
        seats=[SeatSpec(archetype="hesitant")],
        turns=2,
        capture_spans=False,
    )


def test_write_report_produces_all_artifacts(tmp_path):
    rows = [
        TranscriptRow(
            seat=1,
            turn=1,
            snapshot="- main:",
            resolution="resolved",
            intent=Intent(kind=IntentKind.ACT, target_role="button", target_name="Send"),
            narration_delta="a guard approaches",
            signals=[],
        )
    ]
    findings = [
        Finding(
            grade=Grade.CLAIMED,
            seat=1,
            archetype="hesitant",
            turn=1,
            confusion_reason="lost",
            signals=[],
            snapshot_excerpt="- main:",
        )
    ]
    out = write_report(tmp_path, _manifest(), rows, findings, spans=None, spans_error=None)
    assert (out / "report.md").exists()
    assert (out / "findings.json").exists()
    assert (out / "transcript" / "seat-1.jsonl").exists()
    loaded = json.loads((out / "findings.json").read_text())
    assert loaded[0]["grade"] == "claimed"
    md = (out / "report.md").read_text()
    assert "claimed" in md.lower() and "hesitant" in md


def test_spans_written_when_present(tmp_path):
    spans = traces_to_jsonl_records(JAEGER_PAYLOAD)
    out = write_report(tmp_path, _manifest(), [], [], spans=spans, spans_error=None)
    spans_path = out / "spans.jsonl"
    assert spans_path.exists()
    for line in spans_path.read_text().splitlines():
        json.loads(line)
    md = (out / "report.md").read_text()
    assert "1 server spans captured" in md


def test_spans_error_is_loud_in_report(tmp_path):
    out = write_report(
        tmp_path,
        _manifest(),
        [],
        [],
        spans=None,
        spans_error="Jaeger unreachable at http://localhost:16686",
    )
    md = (out / "report.md").read_text()
    assert "SPANS MISSING" in md
    assert not (out / "spans.jsonl").exists()


def test_write_report_uses_injected_run_dir(tmp_path):
    out_dir = tmp_path / "premade-r1"
    out_dir.mkdir()
    out = write_report(
        tmp_path, _manifest(), [], [], spans=None, spans_error=None, run_dir=out_dir
    )
    assert out == out_dir
    assert (out_dir / "report.md").exists()
    assert (out_dir / "findings.json").exists()
