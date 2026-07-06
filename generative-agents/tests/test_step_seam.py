"""The one-tick seam: ``run_simulation.step`` (issue #296).

``simulate`` builds the world once and loops over ``step`` -- one 10-second tick
each. A live backend (#349) instead drives ``step`` itself, one call per frame,
so it can ship each frame the moment it exists and hot-swap the tick's code
between calls (the self-coding experiment, #299). These tests pin the extraction:
driving ``step`` tick-by-tick reproduces ``simulate`` byte-for-byte, which is the
whole contract of the refactor.

Fully offline (mock brain, synthetic maze fixture) and deterministic. Run from
``generative-agents``::

    uv run pytest tests/test_step_seam.py -v
"""

import pytest

from backend.build_world import PERSONAS, build_world
from backend.run_simulation import simulate, step
from backend.sim_config import CognitionConfig
from backend.smallville_agents import attach_agents
from backend.world_map import WorldMap
from synthetic_ville import build_synthetic_ville


@pytest.fixture(scope="module")
def world_map(tmp_path_factory):
    ville = build_synthetic_ville(str(tmp_path_factory.mktemp("ville")))
    return WorldMap(ville)


def _build_run(world_map, num_steps):
    """Reproduce simulate()'s pre-loop setup so a test can drive step() directly.

    Mirrors run_simulation.simulate up to the ``for _step in range`` line: build
    the world, attach the mock brain, and seed each persona's per-step ``state``.
    Returns everything step() needs. If simulate's setup ever drifts from this,
    the equivalence test below fails -- which is the point.
    """
    cog = CognitionConfig()
    game, chars = build_world(world_map)
    attach_agents(chars, PERSONAS, vision_r=cog.vision_r, num_steps=num_steps)
    emoji = {p["name"]: p["emoji"] for p in PERSONAS}
    order = [p["name"] for p in PERSONAS]
    state = {}
    for spec in PERSONAS:
        char = chars[spec["name"]]
        state[char.name] = {
            "tile": tuple(spec["start_tile"]),
            "path": [],
            "pron": emoji[char.name],
            "desc": f"waking up @ {char.location.tile_address}",
            "performing": False,
            "perform_until": None,
            "reasoning": "(waking up)",
            "memories": [],
            "chat": None,
        }
    return game, chars, state, order, emoji, cog


def test_step_loop_reproduces_simulate(world_map):
    # Driving step() one tick at a time, exactly as a live backend would
    # (`for i in range(n): frame, _ = step(...)`), yields the same frames as the
    # sealed simulate() loop -- byte-identical, which is issue #296's hard gate.
    num_steps = 40
    game, chars, state, order, emoji, cog = _build_run(world_map, num_steps)

    frames = []
    for i in range(num_steps):
        frame, chats = step(
            game,
            chars,
            state,
            i,
            order=order,
            world_map=world_map,
            emoji=emoji,
            cog=cog,
        )
        # No real brain -> conversation is off -> no chats (the mock is silent).
        assert chats == 0
        frames.append(frame)

    assert frames == simulate(world_map, num_steps=num_steps)


def test_step_sets_game_turn(world_map):
    # step() owns the memory time axis (game.turn = step_idx, issue #75): a caller
    # that never calls end_turn still gets a coherent turn per tick.
    game, chars, state, order, emoji, cog = _build_run(world_map, 3)
    for i in range(3):
        step(
            game,
            chars,
            state,
            i,
            order=order,
            world_map=world_map,
            emoji=emoji,
            cog=cog,
        )
        assert game.turn == i
