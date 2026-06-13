"""seat_session_url — per-seat loopback host so each bot is a distinct human.

The server keys the *human* identity off the Host header (ADR-119); two seats on
`localhost` share an identity and a browser origin, which never happens in real
play. Each seat gets `player{N}.local` instead, with port/path preserved so the
deterministic session slug — and thus the shared MP session — is untouched.
"""

import pytest

from understudy.orchestrate.run import seat_session_url


def test_localhost_becomes_per_seat_host_port_preserved():
    assert seat_session_url("http://localhost:5173", 1) == "http://player1.local:5173"
    assert seat_session_url("http://localhost:5173", 2) == "http://player2.local:5173"


def test_path_and_query_preserved_so_session_slug_survives():
    url = "http://localhost:5173/play/2026-06-13-beneath_sunden-mp?x=1"
    assert seat_session_url(url, 3) == "http://player3.local:5173/play/2026-06-13-beneath_sunden-mp?x=1"


def test_127_0_0_1_is_also_loopback():
    assert seat_session_url("http://127.0.0.1:5173", 2) == "http://player2.local:5173"


def test_already_player_host_is_redistributed_by_seat():
    # A manifest pointed at player1.local must still give seat 2 player2.local,
    # not leave both on player1.local.
    assert seat_session_url("http://player1.local:5173", 2) == "http://player2.local:5173"


def test_remote_host_is_left_untouched():
    # A real deployment (identity via Cf-Access email) must not be rewritten.
    url = "https://sidequest.example.com/play/abc"
    assert seat_session_url(url, 1) == url


def test_seat_is_one_based_and_fails_loud_below_one():
    with pytest.raises(ValueError):
        seat_session_url("http://localhost:5173", 0)
