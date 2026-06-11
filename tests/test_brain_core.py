import pytest

from understudy.brain.core import (
    DecideResult,
    FakeActionModel,
    Message,
    ModelError,
    parse_intent,
)
from understudy.types import Intent, IntentKind


def test_parse_intent_strict_json():
    raw = '{"kind": "act", "target_role": "button", "target_name": "Send"}'
    intent = parse_intent(raw)
    assert intent.kind is IntentKind.ACT


def test_parse_intent_tolerates_code_fence():
    raw = '```json\n{"kind": "wait"}\n```'
    assert parse_intent(raw).kind is IntentKind.WAIT


def test_parse_intent_raises_model_error_on_garbage():
    with pytest.raises(ModelError):
        parse_intent("I attack the goblin!")


def test_parse_intent_raises_model_error_on_bad_shape():
    with pytest.raises(ModelError):
        parse_intent('{"kind": "act"}')  # act without target


async def test_fake_model_plays_script_then_waits():
    script = [Intent(kind=IntentKind.ACT, target_role="button", target_name="Send")]
    fake = FakeActionModel(script)
    first = await fake.decide("sys", [Message(role="user", content="screen")])
    assert isinstance(first, DecideResult)
    assert first.intent.kind is IntentKind.ACT
    assert (first.input_tokens, first.output_tokens) == (0, 0)
    second = await fake.decide("sys", [])
    assert second.intent.kind is IntentKind.WAIT  # script exhausted → wait forever
