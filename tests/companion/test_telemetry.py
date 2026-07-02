"""RED (161-2, parts b/c): the understudy->server watcher bridge.

A NEW module, ``companion.telemetry``, mirrors the daemon's
``sidequest_daemon.telemetry.watcher_bridge`` (stdlib urllib POST, 2s timeout,
network failures logged WARNING and swallowed — telemetry must never break a
companion's move) but adds the two fields 161-2 needs: an envelope-level
``session_slug`` (which room the companion is in) and an explicit ``severity``
(so a degraded/timed-out decision fires at WARNING, not INFO).

CONTRACT for Dev:
    # src/companion/telemetry.py
    def emit_watcher_event(
        event_type: str,
        fields: dict[str, Any],
        *,
        component: str = "companion_brain",
        session_slug: str | None = None,
        severity: str | None = None,
    ) -> None
POSTs ``{event_type, fields, component, session_slug, severity}`` to
``{SIDEQUEST_SERVER_URL}/internal/watcher/emit`` via a module-level ``_post(url, body)``
helper, catching (URLError, ConnectionError, OSError, TimeoutError) → ``log.warning``.
Mirror the daemon module exactly, plus the two new body keys.
"""

from __future__ import annotations

import inspect
import urllib.error
from unittest.mock import patch

from companion.telemetry import emit_watcher_event


def test_emit_posts_companion_event_with_session_slug_and_severity():
    with patch("companion.telemetry._post") as mock_post:
        emit_watcher_event(
            "companion_brain_decide",
            {"seat": "Donut", "role": "pet"},
            session_slug="game-1",
            severity="warning",
        )
        mock_post.assert_called_once()
        url, body = mock_post.call_args[0]
        assert url.endswith("/internal/watcher/emit")
        assert body["event_type"] == "companion_brain_decide"
        assert body["fields"] == {"seat": "Donut", "role": "pet"}
        assert body["component"] == "companion_brain"
        assert body["session_slug"] == "game-1"
        assert body["severity"] == "warning"


def test_emit_defaults_component_to_companion_brain():
    with patch("companion.telemetry._post") as mock_post:
        emit_watcher_event("companion_brain_decide", {})
        _url, body = mock_post.call_args[0]
        assert body["component"] == "companion_brain"


def test_emit_swallows_urllib_error_and_logs_warning():
    # Server down (connection refused) is urllib.error.URLError — the real failure
    # mode. It must LOG (loud) but never raise (never break the companion's move).
    with patch("companion.telemetry._post", side_effect=urllib.error.URLError("refused")):
        with patch("companion.telemetry.log") as mock_log:
            emit_watcher_event("companion_brain_decide", {})  # must not raise
            mock_log.warning.assert_called_once()


def test_emit_swallows_connection_error_and_logs_warning():
    with patch("companion.telemetry._post", side_effect=ConnectionError("down")):
        with patch("companion.telemetry.log") as mock_log:
            emit_watcher_event("companion_brain_decide", {})
            mock_log.warning.assert_called_once()


def test_server_base_url_honors_env_override(monkeypatch):
    monkeypatch.setenv("SIDEQUEST_SERVER_URL", "http://other:9999/")
    from companion import telemetry

    assert telemetry._server_base_url() == "http://other:9999"


def test_emit_watcher_event_has_typed_signature():
    # lang-review #3: the module boundary is annotated (params + return).
    sig = inspect.signature(emit_watcher_event)
    assert sig.return_annotation is not inspect.Signature.empty
    for name in ("event_type", "fields", "session_slug", "severity"):
        assert sig.parameters[name].annotation is not inspect.Signature.empty
