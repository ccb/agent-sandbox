"""Offline tests for the Smallville :class:`SimulationConfig` (no Django, no live
LLM, no setup.sh).

Mirrors the engine's ``tests/test_config.py`` for the sim's composed config:
defaults reproduce today's behavior, round-trips are lossless, files and the
environment load correctly, unknown keys are rejected, and the config threads
through ``simulate`` while keeping the mock-driven replay byte-identical.

Run from the ``generative-agents`` directory (``uv run`` uses the repo's project
env that has the engine installed)::

    uv run pytest tests/test_sim_config.py -v
"""

import pytest

from gen_agents import build_world, smallville_agents
from gen_agents.build_world import PERSONAS
from gen_agents.run_simulation import simulate
from gen_agents.sim_config import (
    CognitionConfig,
    RetrievalConfig,
    SimulationConfig,
    SimulationRuntimeConfig,
)
from gen_agents.world_map import WorldMap
from synthetic_ville import build_synthetic_ville
from text_adventure_games import memory
from text_adventure_games.config import GameConfig
from text_adventure_games.embedding_client import EmbeddingConfig, MockEmbeddingClient
from text_adventure_games.llm_client import LlmConfig


@pytest.fixture(autouse=True)
def _clear_env(monkeypatch):
    """Keep from_env tests deterministic regardless of the runner's environment."""
    for var in (
        "LLM_PROVIDER",
        "LLM_MODEL",
        "OUTPUT_LEVEL",
        "NO_COLOR",
        "LLM_LOG",
        "EMBEDDING_PROVIDER",
        "EMBEDDING_MODEL",
        "EMBEDDING_API_KEY",
        "EMBEDDING_BASE_URL",
    ):
        monkeypatch.delenv(var, raising=False)


@pytest.fixture(scope="module")
def world_map(tmp_path_factory):
    ville = build_synthetic_ville(str(tmp_path_factory.mktemp("ville")))
    return WorldMap(ville)


# --------------------------------------------------------------------------
# Defaults
# --------------------------------------------------------------------------


def test_defaults_match_today():
    config = SimulationConfig()
    # Run-time knobs mirror run_simulation's historical CLI defaults.
    assert config.simulation.start == "2023-02-13 08:00:00"
    assert config.simulation.steps == 1080
    assert config.simulation.sec_per_step == 10
    assert config.simulation.sim_code == "mock_the_ville_n25"
    assert config.simulation.base_sim == "base_the_ville_n25"
    assert config.simulation.num_agents == 5
    assert config.simulation.seed is None
    # Cognition defaults mirror smallville_agents' module constants.
    assert config.cognition.vision_r == 8
    assert config.cognition.conversation_cooldown_steps == 90
    assert config.cognition.conversation_max_exchanges == 6
    # No embedding -> keyword-overlap relevance, the offline default.
    assert config.embedding is None
    # The embedded engine config is a plain default GameConfig.
    assert isinstance(config.game, GameConfig)
    assert config.game.engine.turn_mode == "sequential"


def test_retrieval_defaults_equal_memory_constants():
    # The RetrievalConfig defaults must track the engine's module constants, so an
    # unconfigured sim scores memories exactly as before. Fails loudly on drift.
    r = RetrievalConfig()
    assert r.alpha_recency == memory.ALPHA_RECENCY
    assert r.alpha_importance == memory.ALPHA_IMPORTANCE
    assert r.alpha_relevance == memory.ALPHA_RELEVANCE
    assert r.recency_decay == memory.DEFAULT_DECAY
    assert r.max_records == memory.DEFAULT_MAX_RECORDS
    assert r.token_budget == memory.DEFAULT_TOKEN_BUDGET


def test_cognition_and_cast_defaults_match_module_constants():
    # CognitionConfig and num_agents defaults must track the gen_agents module
    # constants they mirror, so an unconfigured sim behaves exactly as before.
    cog = CognitionConfig()
    assert cog.vision_r == smallville_agents.SMALLVILLE_VISION_R
    assert (
        cog.conversation_cooldown_steps == smallville_agents.CONVERSATION_COOLDOWN_STEPS
    )
    assert (
        cog.conversation_max_exchanges == smallville_agents.CONVERSATION_MAX_EXCHANGES
    )
    assert SimulationRuntimeConfig().num_agents == build_world.MAX_ACTIVE_PERSONAS


# --------------------------------------------------------------------------
# Round-trip: to_dict <-> from_dict
# --------------------------------------------------------------------------


def test_to_dict_from_dict_round_trip():
    config = SimulationConfig(
        simulation=SimulationRuntimeConfig(steps=24, start="2023-02-13 18:00:00"),
        retrieval=RetrievalConfig(max_records=3, alpha_relevance=2.0),
        embedding=EmbeddingConfig(provider="mock"),
    )
    config.game.engine.turn_mode = "simultaneous"
    data = config.to_dict()
    assert set(data) == {"game", "simulation", "retrieval", "cognition", "embedding"}
    # provider is stored as a plain string, not an enum, so the dict is JSON-able.
    assert data["embedding"]["provider"] == "mock"
    assert SimulationConfig.from_dict(data) == config


def test_to_dict_omits_embedding_when_unset():
    data = SimulationConfig().to_dict()
    assert "embedding" not in data


# --------------------------------------------------------------------------
# from_dict: delegation + validation
# --------------------------------------------------------------------------


def test_from_dict_delegates_game_section():
    config = SimulationConfig.from_dict(
        {"game": {"engine": {"turn_mode": "simultaneous"}}}
    )
    assert config.game.engine.turn_mode == "simultaneous"


def test_from_dict_surfaces_game_validation():
    # An unknown key inside the game section raises GameConfig's own ValueError.
    with pytest.raises(ValueError):
        SimulationConfig.from_dict({"game": {"engine": {"bogus": 1}}})


def test_from_dict_rejects_unknown_section():
    with pytest.raises(ValueError, match="Unknown config section"):
        SimulationConfig.from_dict({"bogus": {}})


def test_from_dict_rejects_unknown_key():
    with pytest.raises(ValueError, match="Unknown key"):
        SimulationConfig.from_dict({"retrieval": {"not_a_field": 1}})


def test_from_dict_embedding_requires_provider():
    with pytest.raises(ValueError, match="requires a 'provider'"):
        SimulationConfig.from_dict({"embedding": {}})


# --------------------------------------------------------------------------
# from_file: YAML + JSON
# --------------------------------------------------------------------------


def test_from_file_json(tmp_path):
    path = tmp_path / "sim.json"
    path.write_text(
        '{"simulation": {"steps": 12}, "retrieval": {"alpha_relevance": 2.0}, '
        '"game": {"engine": {"turn_mode": "simultaneous"}}}'
    )
    config = SimulationConfig.from_file(str(path))
    assert config.simulation.steps == 12
    assert config.retrieval.alpha_relevance == 2.0
    assert config.game.engine.turn_mode == "simultaneous"


def test_from_file_yaml(tmp_path):
    pytest.importorskip("yaml")
    path = tmp_path / "sim.yaml"
    path.write_text(
        "game:\n"
        "  engine:\n"
        "    turn_mode: simultaneous\n"
        "simulation:\n"
        "  steps: 12\n"
        "retrieval:\n"
        "  max_records: 2\n"
        "embedding:\n"
        "  provider: mock\n"
    )
    config = SimulationConfig.from_file(str(path))
    assert config.simulation.steps == 12
    assert config.retrieval.max_records == 2
    assert config.game.engine.turn_mode == "simultaneous"
    assert config.embedding.provider == "mock"


def test_from_file_unsupported_extension(tmp_path):
    path = tmp_path / "sim.toml"
    path.write_text("steps = 12")
    with pytest.raises(ValueError, match="Unsupported config file type"):
        SimulationConfig.from_file(str(path))


# --------------------------------------------------------------------------
# from_env
# --------------------------------------------------------------------------


def test_from_env_reads_llm_and_embedding(monkeypatch):
    monkeypatch.setenv("LLM_PROVIDER", "mock")
    monkeypatch.setenv("EMBEDDING_PROVIDER", "mock")
    config = SimulationConfig.from_env()
    assert config.game.llm is not None and config.game.llm.provider == "mock"
    assert config.embedding is not None and config.embedding.provider == "mock"


def test_from_env_no_vars_means_defaults():
    config = SimulationConfig.from_env()
    assert config.game.llm is None
    assert config.embedding is None


# --------------------------------------------------------------------------
# build_* convenience
# --------------------------------------------------------------------------


def test_build_embedding_client_none_vs_instance():
    assert SimulationConfig().build_embedding_client() is None
    config = SimulationConfig(embedding=EmbeddingConfig(provider="mock"))
    assert isinstance(config.build_embedding_client(), MockEmbeddingClient)


def test_build_llm_client_forwards_to_game():
    assert SimulationConfig().build_llm_client() is None
    config = SimulationConfig()
    config.game.llm = LlmConfig(provider="mock")
    assert config.build_llm_client() is not None


# --------------------------------------------------------------------------
# Integration: the config threads through simulate (offline, mock-driven)
# --------------------------------------------------------------------------


def test_simulate_with_sim_config_retrieval(world_map):
    # A non-default retrieval config + a mock embedding client still produce frames
    # that satisfy the export contract.
    config = SimulationConfig(
        retrieval=RetrievalConfig(max_records=2, alpha_relevance=3.0),
        embedding=EmbeddingConfig(provider="mock"),
    )
    frames = simulate(
        world_map,
        num_steps=12,
        embedding_client=config.build_embedding_client(),
        retrieval=config.retrieval,
    )
    assert len(frames) == 12
    names = {p["name"] for p in PERSONAS}
    for frame in frames:
        assert set(frame.keys()) == names
        for entry in frame.values():
            assert isinstance(entry["movement"], list) and len(entry["movement"]) == 2
            assert all(isinstance(c, int) for c in entry["movement"])
            assert isinstance(entry["pronunciatio"], str) and entry["pronunciatio"]
            assert (
                isinstance(entry["description"], str) and " @ " in entry["description"]
            )
            assert entry["chat"] is None


def test_sim_config_retrieval_keeps_replay_byte_identical(world_map):
    # The mock brain decides from location alone, so tuning retrieval (and adding a
    # mock embedding client) only reorders the retrieved-memory block surfaced on
    # each frame for the replay's inspection card (the ``memories`` field) -- never
    # the decisions. The movement/pronunciatio/description/chat that actually drive
    # the replay stay byte-identical to the default run.
    default = simulate(world_map, num_steps=12)
    tuned = simulate(
        world_map,
        num_steps=12,
        embedding_client=MockEmbeddingClient(),
        retrieval=RetrievalConfig(max_records=2, alpha_relevance=3.0),
    )

    def decisions(frames):
        # Drop the mock-ignored ``memories`` block: its size/ordering is exactly
        # what retrieval tuning is meant to change. Everything else is the replay.
        return [
            {
                name: {k: v for k, v in entry.items() if k != "memories"}
                for name, entry in frame.items()
            }
            for frame in frames
        ]

    assert decisions(tuned) == decisions(default)


def test_num_agents_slices_the_active_cast(world_map):
    # num_agents controls how many residents run: the runner slices ALL_PERSONAS and
    # builds the world from the *same* cast (build_world_fn), so the frames carry
    # exactly that many personas. This is the mechanism run_simulation.main() uses.
    cast = build_world.ALL_PERSONAS[:3]
    frames = simulate(
        world_map,
        num_steps=4,
        personas=cast,
        build_world_fn=lambda wm: build_world.build_world(wm, cast),
    )
    expected = {p["name"] for p in cast}
    assert len(expected) == 3
    assert all(set(frame.keys()) == expected for frame in frames)


def test_cognition_vision_r_reaches_characters(world_map):
    # A CognitionConfig.vision_r threads through simulate -> attach_agents and lands
    # on each resident (unless a persona overrides it in world_data.yaml). Proven via
    # attach_agents directly so it doesn't depend on the mock replay.
    game, chars = build_world.build_world(world_map)
    smallville_agents.attach_agents(chars, PERSONAS, vision_r=3)
    defaulted = [p for p in PERSONAS if "vision_r" not in p]
    assert defaulted, "expected at least one persona without a vision_r override"
    assert all(chars[p["name"]].vision_r == 3 for p in defaulted)
