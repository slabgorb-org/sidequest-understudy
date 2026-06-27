"""RED (160-1): wiring test for the animal companion persona templates.

Story 160-1 ships five `CompanionDef` example YAMLs under
`src/companion/examples/` — cat/owl/raven/toad/goat — each a `role: pet`
companion bound to caverns_and_claudes/beneath_sunden, reusing the epic-159
run loop. This is the integration proof those files exist, parse as valid
CompanionDefs, and carry the load-bearing fields. The register *quality*
(does owl read pedantic, does raven read ominous) is a review-phase judgment;
here we enforce loadability, role, binding, backend, and that the five voices
are not literal clones of one persona.

Donut (`donut_sunden.yaml`) stays as the canonical cat *example*; the five
files below are the new species templates the story delivers.
"""

from pathlib import Path

import pytest

from companion import manifest as manifest_mod
from companion.manifest import CompanionDef, load_companion
from seat_core.persona.axis import Role

# examples/ ships inside the companion package — locate it package-relative so
# the test survives a move of the tests/ tree.
EXAMPLES_DIR = Path(manifest_mod.__file__).parent / "examples"

# (species, filename) for the five animal companion templates this story adds.
ANIMAL_TEMPLATES = [
    ("cat", "cat_sunden.yaml"),
    ("owl", "owl_sunden.yaml"),
    ("raven", "raven_sunden.yaml"),
    ("toad", "toad_sunden.yaml"),
    ("goat", "goat_sunden.yaml"),
]


@pytest.mark.parametrize("species,filename", ANIMAL_TEMPLATES)
def test_animal_template_file_exists(species: str, filename: str):
    assert (EXAMPLES_DIR / filename).is_file(), (
        f"missing animal companion template for {species}: "
        f"{EXAMPLES_DIR / filename}"
    )


@pytest.mark.parametrize("species,filename", ANIMAL_TEMPLATES)
def test_animal_template_is_valid_pet_companion(species: str, filename: str):
    d = load_companion(EXAMPLES_DIR / filename)
    assert isinstance(d, CompanionDef)
    assert d.role is Role.PET, f"{filename}: role must be pet, got {d.role!r}"
    assert d.species == species, (
        f"{filename}: species must be {species!r}, got {d.species!r}"
    )
    assert d.voice.strip(), f"{filename}: voice must be non-empty"
    assert d.name.strip(), f"{filename}: name must be non-empty"


@pytest.mark.parametrize("species,filename", ANIMAL_TEMPLATES)
def test_animal_template_bound_to_beneath_sunden(species: str, filename: str):
    d = load_companion(EXAMPLES_DIR / filename)
    assert d.genre == "caverns_and_claudes", (
        f"{filename}: genre must be caverns_and_claudes, got {d.genre!r}"
    )
    assert d.world == "beneath_sunden", (
        f"{filename}: world must be beneath_sunden, got {d.world!r}"
    )


@pytest.mark.parametrize("species,filename", ANIMAL_TEMPLATES)
def test_animal_template_uses_claude_p_sonnet(species: str, filename: str):
    # The anthropic/* default breaks on the dev box (API key disabled); the
    # working backend is claude_p — see donut_sunden.yaml and the chargen-driver
    # doc §7 carryover. A template that defaults to anthropic/* is dead on arrival.
    d = load_companion(EXAMPLES_DIR / filename)
    assert d.model == "claude_p/sonnet", (
        f"{filename}: model must be claude_p/sonnet, got {d.model!r}"
    )


@pytest.mark.parametrize("species,filename", ANIMAL_TEMPLATES)
def test_animal_template_game_slug_is_unfilled_placeholder(species: str, filename: str):
    # A committed template must NOT carry a live room slug — the UI mints those
    # per session. It stays a REPLACE-* placeholder the operator fills by hand
    # (mirrors donut_sunden.yaml). Guards against pasting a real slug into git.
    d = load_companion(EXAMPLES_DIR / filename)
    assert d.game_slug.upper().startswith("REPLACE"), (
        f"{filename}: game_slug must stay a REPLACE-* placeholder, "
        f"got {d.game_slug!r}"
    )


def test_animal_voices_are_distinct():
    # The deliverable is FIVE distinct voices, not five clones of one persona.
    # Voice quality is a review judgment; byte-identity is the cheap mechanical
    # floor that catches a copy-paste-the-same-voice regression.
    voices = {}
    for species, filename in ANIMAL_TEMPLATES:
        d = load_companion(EXAMPLES_DIR / filename)
        voices[species] = d.voice.strip()
    unique = set(voices.values())
    assert len(unique) == len(ANIMAL_TEMPLATES), (
        f"animal companion voices must be pairwise distinct; got "
        f"{len(unique)} unique of {len(ANIMAL_TEMPLATES)} ({sorted(voices)})"
    )


def test_every_example_yaml_loads_as_companion_def():
    # Durable wiring guard: every shipped example YAML must be a loadable
    # CompanionDef with a non-empty species and voice — no orphan or broken
    # files. Covers donut today and the five animals once Dev adds them.
    yamls = sorted(EXAMPLES_DIR.glob("*.yaml"))
    assert yamls, f"no example companion YAMLs found under {EXAMPLES_DIR}"
    for path in yamls:
        d = load_companion(path)
        assert isinstance(d, CompanionDef), f"{path.name} did not load as CompanionDef"
        assert d.species.strip(), f"{path.name}: species must be non-empty"
        assert d.voice.strip(), f"{path.name}: voice must be non-empty"
