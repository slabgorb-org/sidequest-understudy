"""RED (159-4): fair dice faces (physics-is-the-roll, ADR-074) — Plan C Task 5.

The companion rolls fair RNG client-side and submits settled faces; the server
resolves from them. Known systems map to face counts/ranges; an unknown system
fails LOUD (No Silent Fallbacks) rather than guessing a default die.
"""

import random

import pytest

from companion.dice import roll_faces


def test_d20_in_range():
    rng = random.Random(1)
    for _ in range(50):
        faces = roll_faces("d20", rng)
        assert len(faces) == 1 and 1 <= faces[0] <= 20


def test_2d6_two_faces_in_range():
    faces = roll_faces("2d6", random.Random(2))
    assert len(faces) == 2 and all(1 <= f <= 6 for f in faces)


def test_4dF_four_fudge_faces():
    faces = roll_faces("4dF", random.Random(3))
    assert len(faces) == 4 and all(f in (-1, 0, 1) for f in faces)


def test_seeded_rng_is_deterministic():
    # Same seed → same faces. Reproducible runs (resume-safe randomness).
    assert roll_faces("d20", random.Random(7)) == roll_faces("d20", random.Random(7))


def test_unknown_system_fails_loud():
    with pytest.raises(ValueError, match="unknown die system"):
        roll_faces("d7")
