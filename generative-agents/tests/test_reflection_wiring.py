"""Offline tests for periodic reflection wired into the Smallville port (#84).

The engine's reflection seam is covered in ``tests/test_reflection.py`` (one level
up). These cover the *port-side* wiring:

* ``attach_agents`` gives each agent an ``LLMReflector`` only when a
  ``reflector_client`` is supplied (a real provider); the offline default leaves
  ``agent.reflector`` None, so reflection never fires;
* the step loop's :func:`~text_adventure_games.npc.maybe_reflect` call actually
  synthesizes and writes back a reflection once importance crosses the threshold,
  consulting the supplied reflector client; and
* a default (mock) ``simulate`` run produces *no* reflection records, so the
  exported replay stays byte-identical.

Fully offline (``build_world`` + a scripted fake client, no maze assets, no LLM).
Run from ``generative-agents``::

    uv run pytest tests/test_reflection_wiring.py -v
"""

import pytest

from backend.build_world import PERSONAS, build_world
from backend.run_simulation import simulate
from backend.smallville_agents import attach_agents
from backend.world_map import WorldMap

from text_adventure_games.npc import maybe_reflect
from text_adventure_games.reflection import (
    INSIGHT_TOOL,
    SALIENT_QUESTIONS_TOOL,
    LLMReflector,
)

from synthetic_ville import build_synthetic_ville


@pytest.fixture(scope="module")
def world_map(tmp_path_factory):
    ville = build_synthetic_ville(str(tmp_path_factory.mktemp("ville")))
    return WorldMap(ville)


class _ScriptedReflectorClient:
    """A fake ``LlmClient`` returning canned questions + an insight by tool name."""

    def __init__(self):
        self.calls = []

    def call_tool(self, messages, tool, max_tokens=256, temperature=0.0):
        self.calls.append(tool["name"])
        if tool["name"] == SALIENT_QUESTIONS_TOOL["name"]:
            return {"questions": ["What should I make of Maria?"]}
        if tool["name"] == INSIGHT_TOOL["name"]:
            return {"insight": "Maria keeps coming up in my day.", "evidence": [1]}
        return None

    def chat(self, *args, **kwargs):
        return None

    def count_tokens(self, text):
        return len(text.split())


def test_no_reflector_client_leaves_reflection_off():
    # The offline default: no reflector wired on, so the loop's maybe_reflect is a
    # no-op and the replay stays byte-identical.
    _, chars = build_world()
    attach_agents(chars, PERSONAS)
    for spec in PERSONAS:
        assert chars[spec["name"]].agent.reflector is None


def test_reflector_client_attaches_llm_reflector():
    _, chars = build_world()
    attach_agents(chars, PERSONAS, reflector_client=_ScriptedReflectorClient())
    for spec in PERSONAS:
        assert isinstance(chars[spec["name"]].agent.reflector, LLMReflector)


def test_loop_reflection_fires_and_writes_back():
    # Exercise the exact seam the step loop uses: maybe_reflect(char.agent, game).
    # Pump the agent's memory over the importance threshold, then reflect.
    client = _ScriptedReflectorClient()
    game, chars = build_world()
    attach_agents(chars, PERSONAS, reflector_client=client)
    char = chars[PERSONAS[0]["name"]]
    agent = char.agent
    for i in range(10):  # 10 * 4.0 = 40 > the default 30 threshold
        agent.memory.add_observation(
            "Maria stopped by to chat", turn=i, importance=4.0, actor="Maria"
        )
    game.turn = 10

    created = maybe_reflect(agent, game)

    assert created  # a reflection was synthesized
    assert client.calls  # the reflector client was actually consulted
    kinds = [r.kind.value for r in agent.memory.records]
    assert "reflection" in kinds
    # The accumulator reset, so an immediate second pass adds nothing.
    assert maybe_reflect(agent, game) == []


def test_default_mock_simulate_produces_no_reflections(world_map):
    # A plain mock run wires no reflector, so the full memory stream an agent forms
    # contains only observations/plans -- never a reflection. This is what keeps the
    # default exported replay byte-identical (reflection is purely additive + gated).
    out_memories: dict = {}
    simulate(world_map, num_steps=40, out_memories=out_memories)
    for name, stream in out_memories.items():
        assert all(m["kind"] != "reflection" for m in stream), name
