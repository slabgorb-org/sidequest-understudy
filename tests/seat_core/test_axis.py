import pytest
from pydantic import ValidationError

from seat_core.persona.axis import Role, RoleDial, SeatAxes


def test_seat_axes_validate_bounds():
    a = SeatAxes(
        narrative_vs_mechanical=0.85, verbosity="low", decisiveness="high", reading_tolerance="medium"
    )
    assert a.narrative_vs_mechanical == 0.85


def test_seat_axes_reject_out_of_range():
    with pytest.raises(ValidationError):
        SeatAxes(
            narrative_vs_mechanical=1.5, verbosity="low", decisiveness="high", reading_tolerance="low"
        )


def test_role_dial_perception_scope():
    assert RoleDial(role=Role.PET).perception_scope == "owner_private"
    assert RoleDial(role=Role.PEER).perception_scope == "party"
    assert RoleDial(role=Role.HIRELING).perception_scope == "public"


def test_role_rejects_unknown():
    with pytest.raises(ValidationError):
        RoleDial(role="sidekick")


# --- TEA adversarial additions ---


def test_seat_axes_forbids_extra_fields():
    # extra="forbid" guards the contract Archetype will subclass (159-2): a typo'd
    # or smuggled field must fail validation, not silently attach.
    with pytest.raises(ValidationError):
        SeatAxes(
            narrative_vs_mechanical=0.5,
            verbosity="low",
            decisiveness="low",
            reading_tolerance="low",
            affordance_hunger="high",  # not a SeatAxes field
        )


@pytest.mark.parametrize("value", [0.0, 1.0])
def test_seat_axes_accepts_inclusive_bounds(value):
    a = SeatAxes(
        narrative_vs_mechanical=value,
        verbosity="low",
        decisiveness="low",
        reading_tolerance="low",
    )
    assert a.narrative_vs_mechanical == value


def test_seat_axes_rejects_below_lower_bound():
    with pytest.raises(ValidationError):
        SeatAxes(
            narrative_vs_mechanical=-0.1,
            verbosity="low",
            decisiveness="low",
            reading_tolerance="low",
        )


def test_seat_axes_rejects_bad_level_literal():
    # verbosity/decisiveness/reading_tolerance are Level literals — "extreme" is not one.
    with pytest.raises(ValidationError):
        SeatAxes(
            narrative_vs_mechanical=0.5,
            verbosity="extreme",
            decisiveness="low",
            reading_tolerance="low",
        )


def test_role_is_str_enum_with_string_values():
    assert Role.PET == "pet"
    assert Role("hireling") is Role.HIRELING
