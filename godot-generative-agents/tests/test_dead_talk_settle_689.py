"""Bound the dead-talk retry loop through the pair cooldown (issue #689).

A decide-level `talk to <partner>` never produces a real conversation for a
Penn resident -- that's `maybe_converse`/`maybe_react`'s job, not the agent's
own decide (Penn characters never set `talk_text`/`talk_topics` on the shared
engine `Talk` action). Without a settle, a talk that resolves empty ("has
nothing to say") or blocked ("no one here to talk to") leaves the agent
immediately `due` for its next paid decide, every tick, for as long as the
#86 pair cooldown blocks a real conversation.

Fully offline (fake brains). Run from the repo root::

    PYTHONPATH=.:godot-generative-agents uv run --no-sync pytest \\
        godot-generative-agents/tests/test_dead_talk_settle_689.py -v
"""

from backend.sim_config import CognitionConfig


def test_cognition_config_dead_talk_settle_default():
    cog = CognitionConfig()
    assert cog.dead_talk_settle_steps == 30


def test_dead_talk_settle_knob_loads_from_dict():
    from backend.sim_config import SimulationConfig

    config = SimulationConfig.from_dict({"cognition": {"dead_talk_settle_steps": 10}})
    assert config.cognition.dead_talk_settle_steps == 10
    assert config.cognition.deviation_cooldown_steps == 30  # untouched sibling default


from backend.build_world import build_world  # noqa: E402
from backend.cognition import attach_agents  # noqa: E402
from backend.run_simulation import step  # noqa: E402

_LOCATIONS = [
    {"name": "Plaza", "description": "the plaza", "address": None, "hub": True},
    {"name": "Library", "description": "a library", "address": "T:Library:desk"},
]


class _StubMap:
    """No-op world map (pattern from test_pacing_authority_581.py's _StubMap).

    Sofia's own schedule (two 5-step stops, Plaza then Library) advances and
    issues a real `travel` decide once her own stop expires -- independent of
    Diego's dead-talk settle under test here. A `travel` decide always calls
    `world_map.walk_path(...)` to lay in a tile path (run_simulation.py), so a
    bare `world_map=_StubMap()` crashes as soon as Sofia's own travel fires; this
    stub keeps that unrelated path harmless.
    """

    def walk_path(self, src, address, furniture=None):
        return [(1, 1)]


def _persona(name, home):
    return {
        "name": name,
        "home": home,
        "persona": f"I am {name}.",
        "emoji": "\U0001f9d1",
        "start_tile": [0, 0],
        "destination": "Plaza",
        "activity": "reading",
        # Two stops so an *erroneous* schedule.advance() (the bug the
        # on_plan=False guard prevents) is observable as stop_index moving.
        "schedule": [
            {"place": "Plaza", "activity": "reading", "emoji": None, "steps": 5},
            {"place": "Library", "activity": "studying", "emoji": None, "steps": 5},
        ],
        "vision_r": 3,
    }


def _build(sofia_home="Plaza"):
    """Diego always lives at Plaza; sofia_home="Plaza" co-locates them
    (the empty-success "has nothing to say" case), sofia_home="Library"
    does not (the blocked "no one here to talk to" case, Task 3)."""
    personas = [_persona("Diego Cruz", "Plaza"), _persona("Sofia Reyes", sofia_home)]
    game, chars = build_world(None, personas, _LOCATIONS)
    attach_agents(chars, personas, llm_client=None)
    order = ["Diego Cruz", "Sofia Reyes"]
    return game, chars, order


def _full_state(tile=(0, 0)):
    """A state entry with every key step() reads; step() fills gaps via
    st.get(...) defaults, but this is the full shape run_simulation writes
    back into every tick."""
    return {
        "tile": tuple(tile),
        "path": [],
        "pron": "\U0001f9d1",
        "desc": "reading",
        "performing": False,
        "perform_until": None,
        "reasoning": "(r)",
        "memories": [],
        "chat": None,
        "stop_since": 0,
        "on_plan": True,
        "conversing": False,
    }


def _script_decide_forever(chars, actor_name, command):
    """Override actor_name's decide to always return `command`. Returns the
    list of observations it was called with, so a test can assert call count
    (a call = a paid decide in the real system)."""
    calls = []

    def _decide(observation):
        calls.append(observation)
        return command

    chars[actor_name].agent.decide = _decide
    return calls


def test_empty_talk_settles_briefly_and_bounds_the_retry():
    game, chars, order = _build(sofia_home="Plaza")  # co-located -> "nothing to say"
    calls = _script_decide_forever(chars, "Diego Cruz", "talk to Sofia Reyes")
    state = {n: _full_state() for n in order}
    emoji = {n: "\U0001f9d1" for n in order}

    step(game, chars, state, 0, order=order, world_map=_StubMap(), emoji=emoji)
    assert len(calls) == 1
    assert state["Diego Cruz"]["performing"] is True
    assert state["Diego Cruz"]["on_plan"] is False
    assert (
        state["Diego Cruz"]["perform_until"] == 30
    )  # 0 + default dead_talk_settle_steps

    # Mid-settle: NOT due, so no re-decide (the bug this fix closes).
    step(game, chars, state, 5, order=order, world_map=_StubMap(), emoji=emoji)
    assert len(calls) == 1

    # Settle expires: due again, re-decides -- bounded, not permanently stuck --
    # and the on_plan=False guard means the schedule pointer never moved.
    step(game, chars, state, 30, order=order, world_map=_StubMap(), emoji=emoji)
    assert len(calls) == 2
    assert chars["Diego Cruz"].agent.schedule.stop_index == 0
