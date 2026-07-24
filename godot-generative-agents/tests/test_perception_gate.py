"""The tile-distance perception gate (issue #662).

All three Penn residents spawn in the single outdoor hub Location ("Penn
campus", no tile footprint), so before #662 every same-location channel --
presence memories, the observation's "Characters here:", the conversation
audience -- treated residents 150 tiles apart as co-present from turn 0.

The fix is character-granular: characters carry their live map tile
(``char.tile``, stamped at spawn by ``build_world`` and kept fresh by the
shared ``run_simulation.step``), and ``TiledGame.can_perceive`` admits only
things within the observer's ``vision_r`` in Chebyshev tiles (the same metric
as ``WorldMap.tile_gap``). The silent Observer -- the engine's required
"player", which never acts -- is gated out entirely.

The presence/observation assertions exercise the engine side of the seam
(``Game.can_perceive``, landed on ``main`` via #668) end to end. Run from the
repo root::

    uv run pytest godot-generative-agents/tests/test_perception_gate.py -v
"""

import sys
from pathlib import Path

import pytest

_SIM_DIR = (
    Path(__file__).resolve().parents[2] / "godot-generative-agents" / "backend" / "penn"
)
sys.path.insert(0, str(_SIM_DIR))

from backend.cognition import DEFAULT_VISION_R, attach_agents  # noqa: E402
from penn_world import build_penn_world  # noqa: E402
from serve_penn import PennStepper  # noqa: E402
from text_adventure_games.things import Character  # noqa: E402


@pytest.fixture
def penn():
    """The exact world serve_penn builds: game + agent-attached characters."""
    pw = build_penn_world()
    game, chars = pw.build_world_fn(pw.world_map)
    attach_agents(chars, pw.personas, vision_r=DEFAULT_VISION_R)
    return pw, game, chars


def _presence_texts(mem):
    return {r.text for r in mem.records if "presence" in r.tags}


# ------------------------------------------------- TiledGame.can_perceive


def test_can_perceive_gates_by_chebyshev_tile_distance(penn):
    _pw, game, chars = penn
    sofia = chars["Sofia Ramirez"]
    tanaka = chars["Professor Tanaka"]
    # At spawn they are ~149 tiles apart -- same Location, far out of range.
    assert not game.can_perceive(sofia, tanaka)
    # Exactly at the radius counts as in view (tile_gap's inclusive edge)...
    sofia.tile = (100, 100)
    tanaka.tile = (100 + DEFAULT_VISION_R, 100)
    assert game.can_perceive(sofia, tanaka)
    # ...one tile past it does not, and diagonals count as one step.
    tanaka.tile = (100 + DEFAULT_VISION_R + 1, 100)
    assert not game.can_perceive(sofia, tanaka)
    tanaka.tile = (100 + DEFAULT_VISION_R, 100 + DEFAULT_VISION_R)
    assert game.can_perceive(sofia, tanaka)


def test_can_perceive_stays_open_without_tiles(penn):
    """A character with no map tile keeps room granularity -- the engine
    default -- so plain engine games and un-stamped NPCs are unchanged."""
    _pw, game, chars = penn
    sofia = chars["Sofia Ramirez"]
    ghost = Character("ghost", "an untiled character", "I drift.")
    game.locations["Penn campus"].add_character(ghost)
    assert game.can_perceive(sofia, ghost)
    assert game.can_perceive(ghost, sofia)


def test_the_silent_observer_is_never_perceived(penn):
    """The engine's required "player" is plumbing, not a resident: nobody
    should record "I see Observer nearby." (the #662 side wart)."""
    _pw, game, chars = penn
    sofia = chars["Sofia Ramirez"]
    assert not game.can_perceive(sofia, game.player)
    # ...while the Observer itself (the api.py world view) still sees everyone.
    assert game.can_perceive(game.player, sofia)


# ------------------------------------------------------- tile stamping


def test_build_world_stamps_spawn_tiles(penn):
    pw, _game, chars = penn
    for spec in pw.personas:
        assert chars[spec["name"]].tile == tuple(spec["start_tile"])


def test_step_keeps_character_tiles_in_sync():
    """The shared step loop moves state tiles; characters must follow, or
    perception would judge distance from stale spawn positions."""
    world = build_penn_world()
    spawns = {p["name"]: tuple(p["start_tile"]) for p in world.personas}
    stepper = PennStepper(num_steps=10, world=world)
    for _ in range(6):
        stepper.tick()
    for name, char in stepper.chars.items():
        assert char.tile == tuple(stepper.state[name]["tile"])
    # The walk has actually started: at least one resident is off its spawn
    # tile, so the sync above is exercised on a *moved* tile, not a no-op.
    assert any(char.tile != spawns[name] for name, char in stepper.chars.items())


# ------------------------------------------------- conversation audience


def test_audience_excludes_out_of_range_residents(penn):
    _pw, game, chars = penn
    sofia = chars["Sofia Ramirez"]
    tanaka = chars["Professor Tanaka"]
    names = {c.name for c in game.audience_for(sofia, "hi")}
    assert "Professor Tanaka" not in names  # 149 tiles away at spawn
    assert "Observer" not in names
    # Bring Tanaka within range and he becomes a legal partner again.
    tanaka.tile = (sofia.tile[0] + 2, sofia.tile[1])
    names = {c.name for c in game.audience_for(sofia, "hi")}
    assert "Professor Tanaka" in names


# ------------------------- end-to-end spawn awareness


def test_spawn_first_perceive_records_no_cross_campus_sightings(penn):
    _pw, game, chars = penn
    sofia = chars["Sofia Ramirez"]
    sofia.agent.memory.perceive(game, sofia)
    texts = _presence_texts(sofia.agent.memory)
    assert "I see Professor Tanaka nearby." not in texts
    assert "I see Observer nearby." not in texts


def test_spawn_observation_omits_cross_campus_characters(penn):
    _pw, game, chars = penn
    sofia = chars["Sofia Ramirez"]
    obs = game.describe_for(sofia)
    assert "Professor Tanaka" not in obs
    assert "Observer" not in obs


def test_close_residents_still_perceive_each_other(penn):
    """The gate must not overshoot: residents inside vision_r stay mutually
    present in both memory and the observation text."""
    _pw, game, chars = penn
    sofia = chars["Sofia Ramirez"]
    diego = chars["Diego Torres"]
    sofia.tile = (100, 100)
    diego.tile = (104, 102)  # Chebyshev 4 <= vision_r 8
    added = sofia.agent.memory.perceive(game, sofia)
    assert any(r.text == "I see Diego Torres nearby." for r in added)
    assert "Diego Torres" in game.describe_for(sofia)
