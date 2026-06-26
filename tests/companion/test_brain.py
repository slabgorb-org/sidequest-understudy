"""RED (159-4): per-turn decision via seat-core — Plan C Task 7.

The brain binds seat-core's model backends to CompanionIntent. EVERY failure
mode degrades to YIELD — a legitimate choice — so the companion never stalls the
table and never fabricates an action the persona did not choose. A SUCCESSFUL
decision must NOT be swallowed (lang-review #1: broad catch is intentional here,
but it must not eat valid results).
"""

import asyncio

from pydantic import BaseModel

from companion.brain import build_turn_context, decide, make_brain
from companion.intent import CompanionIntent, IntentKind
from companion.protocol import StateMirror
from seat_core.core import DecideResult, FakeStructuredModel, Message


async def test_decide_returns_scripted_intent():
    # The happy path is NOT swallowed by the safety net.
    brain = FakeStructuredModel(
        [CompanionIntent(kind=IntentKind.ACT, text="I pounce.")],
        default=CompanionIntent(kind=IntentKind.YIELD),
    )
    out = await decide(brain, "sys", [Message(role="user", content="x")], timeout_s=5)
    assert out.kind is IntentKind.ACT and out.text == "I pounce."


async def test_decide_times_out_to_yield():
    class Slow:
        async def decide(self, system, transcript):
            await asyncio.sleep(10)

    out = await decide(Slow(), "sys", [], timeout_s=0.05)
    assert out.kind is IntentKind.YIELD  # never stalls the table


async def test_decide_model_error_to_yield():
    class Broken:
        async def decide(self, system, transcript):
            raise RuntimeError("boom")

    out = await decide(Broken(), "sys", [], timeout_s=5)
    assert out.kind is IntentKind.YIELD  # never fabricates


async def test_decide_non_intent_value_to_yield():
    # The model returns a valid DecideResult whose value is NOT a CompanionIntent.
    # The brain must degrade to YIELD, not forward a wrong-shaped decision.
    class WrongShape(BaseModel):
        pass

    class WrongModel:
        async def decide(self, system, transcript):
            return DecideResult(value=WrongShape(), input_tokens=0, output_tokens=0)

    out = await decide(WrongModel(), "sys", [], timeout_s=5)
    assert out.kind is IntentKind.YIELD


def test_make_brain_binds_companion_intent():
    brain = make_brain("fake")
    assert brain.__class__.__name__ == "FakeStructuredModel"


def test_build_turn_context_includes_situation():
    m = StateMirror()
    m.last_narration = "A goblin snarls."
    ctx = build_turn_context(m, "It is your turn.")
    assert any("goblin" in msg.content for msg in ctx)
    assert any("your turn" in msg.content for msg in ctx)
