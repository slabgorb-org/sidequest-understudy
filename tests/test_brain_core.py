import pytest

from understudy.brain.core import (
    DecideResult,
    FakeActionModel,
    Message,
    ModelError,
    parse_intent,
)
from understudy.brain.llm.factory import make_model
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
    assert first.value.kind is IntentKind.ACT
    assert (first.input_tokens, first.output_tokens) == (0, 0)
    second = await fake.decide("sys", [])
    assert second.value.kind is IntentKind.WAIT  # script exhausted → wait forever


# --- Factory shim: understudy binds seat_core's generic factory to Intent.
# seat_core/test_factory.py covers the generic factory; these pin the
# understudy-specific contract (Intent-bound backends, no-default fake).


def test_factory_dispatches_by_prefix(monkeypatch):
    monkeypatch.setenv("ANTHROPIC_API_KEY", "test")  # AsyncAnthropic() needs a key at construct
    assert type(make_model("anthropic/claude-haiku-4-5-20251001")).__name__ == "AnthropicModel"
    assert type(make_model("ollama/qwen3:8b")).__name__ == "OllamaModel"
    assert type(make_model("claude_p/haiku")).__name__ == "ClaudePModel"
    assert type(make_model("fake")).__name__ == "FakeActionModel"


def test_factory_fake_needs_no_default():
    # understudy's shim bakes the WAIT default into FakeActionModel, so 'fake'
    # works with no default arg — unlike seat_core's generic make_model('fake', ...).
    assert isinstance(make_model("fake"), FakeActionModel)


def test_factory_fails_loud_on_unknown_backend():
    with pytest.raises(ValueError, match="unknown model backend"):
        make_model("bard/gpt-1")
