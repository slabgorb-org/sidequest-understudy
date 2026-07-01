"""Cross-process watcher event bridge — companion → server (161-2).

The companion runs in its own process and cannot import the server's watcher hub
(``sidequest.telemetry.watcher_hub``), so it POSTs each ``companion_brain_decide``
event to the server's ``/internal/watcher/emit`` endpoint — the same bridge the
daemon uses (``sidequest_daemon.telemetry.watcher_bridge``).

Two additions over the daemon's bridge: an envelope-level ``session_slug`` (which
room the companion is playing in — the companion's slug arrives here, it is not on
the server's ContextVar) and an explicit ``severity`` (a degraded/timed-out
decision fires at WARNING, not INFO — silence is not acceptable for a lie-detector).

Per CLAUDE.md No Silent Fallbacks: network errors are LOGGED LOUDLY, never
swallowed silently — but they never raise, because telemetry must never break a
companion's move. Uses ``urllib.request`` (stdlib) rather than ``requests``/``httpx``
for a fire-and-forget 2-second POST — no new runtime dependency.
"""

from __future__ import annotations

import json
import logging
import os
import urllib.error
import urllib.request
from typing import Any

log = logging.getLogger(__name__)

_DEFAULT_SERVER_URL = "http://127.0.0.1:8765"
_TIMEOUT_SECONDS = 2.0


def _server_base_url() -> str:
    return os.environ.get("SIDEQUEST_SERVER_URL", _DEFAULT_SERVER_URL).rstrip("/")


def _post(url: str, body: dict[str, Any]) -> None:
    """Sync POST with a short timeout. Raises on any network error."""
    data = json.dumps(body).encode("utf-8")
    req = urllib.request.Request(
        url,
        data=data,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=_TIMEOUT_SECONDS):
        pass


def emit_watcher_event(
    event_type: str,
    fields: dict[str, Any],
    *,
    component: str = "companion_brain",
    session_slug: str | None = None,
    severity: str | None = None,
) -> None:
    """Forward a watcher event to the server's hub via HTTP.

    Failures are logged at WARNING — never raised. Telemetry must not break the
    companion's turn, but the failure must be visible.
    """
    url = f"{_server_base_url()}/internal/watcher/emit"
    body = {
        "event_type": event_type,
        "fields": fields,
        "component": component,
        "session_slug": session_slug,
        "severity": severity,
    }
    try:
        _post(url, body)
    except (urllib.error.URLError, ConnectionError, OSError, TimeoutError) as exc:
        log.warning("companion watcher_bridge POST failed (%s): %s", type(exc).__name__, exc)
