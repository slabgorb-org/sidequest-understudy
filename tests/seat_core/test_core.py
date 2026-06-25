from typing import Literal

import pytest
from pydantic import BaseModel

from seat_core.core import (
    DecideResult,
    FakeStructuredModel,
    Message,
    ModelError,
    parse_structured,
)


class Ping(BaseModel):
    kind: Literal["a", "b"]


def test_parse_structured_strict_json():
    assert parse_structured('{"kind": "a"}', Ping).kind == "a"


def test_parse_structured_tolerates_code_fence():
    assert parse_structured('```json\n{"kind": "b"}\n```', Ping).kind == "b"


def test_parse_structured_raises_on_prose():
    with pytest.raises(ModelError):
        parse_structured("I choose a!", Ping)


def test_parse_structured_raises_on_bad_shape():
    with pytest.raises(ModelError):
        parse_structured('{"kind": "z"}', Ping)  # not in Literal


async def test_fake_plays_script_then_default():
    fake = FakeStructuredModel([Ping(kind="a")], default=Ping(kind="b"))
    first = await fake.decide("sys", [Message(role="user", content="x")])
    assert isinstance(first, DecideResult)
    assert first.value.kind == "a"
    assert (first.input_tokens, first.output_tokens) == (0, 0)
    second = await fake.decide("sys", [])
    assert second.value.kind == "b"  # script exhausted → default forever


# --- TEA adversarial additions (error paths the plan's impl promises) ---


def test_parse_structured_raises_on_empty_string():
    # An empty model reply is a model failure, not a silent {} — must raise loud.
    with pytest.raises(ModelError):
        parse_structured("", Ping)


async def test_fake_empty_script_returns_default_immediately():
    # make_model("fake", ...) constructs FakeStructuredModel([], default); the very
    # first decide must yield the default, never IndexError on an empty script.
    fake = FakeStructuredModel([], default=Ping(kind="b"))
    result = await fake.decide("sys", [Message(role="user", content="x")])
    assert result.value.kind == "b"
    assert (result.input_tokens, result.output_tokens) == (0, 0)
