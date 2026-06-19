"""Offline tests for the unified GameConfig (see text_adventure_games/config.py).

Three things to prove:

  A. Construction — defaults, from_dict/to_dict round-trip, from_file (YAML+JSON),
     from_env, and friendly errors on bad input.
  B. Game integration — a config actually drives the engine (clock, turn_mode,
     phases, hints, caps), and the explicit time_config/turn_mode arguments still
     win for back-compat.
  C. Agent wiring — the behavior factories thread AgentConfig into the LLMAgent.

Everything here is free and offline (no LLM calls).

Run with pytest::

    pytest tests/test_config.py -v
"""

import json

import pytest

from text_adventure_games import games, npc, things
from text_adventure_games.config import (
    AgentConfig,
    ClockConfig,
    EngineConfig,
    GameConfig,
    ObservabilityConfig,
    RenderConfig,
)
from text_adventure_games.llm_client import LlmConfig
from text_adventure_games.turns import DEFAULT_PHASES
from text_adventure_games.usage import RunLog


def build_game(**game_kwargs):
    """A minimal one-room, player-only world; pass any Game kwargs through."""
    field = things.Location("Field", "An open grassy field.")
    forest = things.Location("Forest", "A dark tangled forest.")
    field.add_connection("north", forest)
    player = things.Character("player", "a brave adventurer", "I explore.")
    return games.Game(field, player, **game_kwargs)


# ----------------------------------------------------------------------
# Section A: construction
# ----------------------------------------------------------------------


def test_defaults_match_historical_values():
    c = GameConfig()
    assert c.llm is None
    assert c.engine.turn_mode == "sequential"
    assert c.engine.phases is False
    assert c.engine.give_hints is True
    assert c.engine.max_actions_per_turn == 100
    assert c.engine.heard_max == 5
    assert c.engine.cascade_passes == 2
    assert c.agent.temperature == 0.7
    assert c.agent.max_tokens == 128
    assert c.agent.max_retries == 1
    assert c.agent.max_duration == 24 * 60
    assert c.clock.enabled is False
    assert c.clock.start_hour == 8
    assert c.clock.minutes_per_turn == 15
    assert c.render.level is None  # follow OUTPUT_LEVEL / default
    assert c.render.width == 80
    assert c.render.no_color is None
    assert c.observability.log_path is None  # no usage artifact by default
    assert c.observability.log_prompts is False


def test_to_dict_from_dict_round_trip():
    c = GameConfig(
        llm=LlmConfig(provider="mock", model="x"),
        agent=AgentConfig(temperature=0.1, max_tokens=64),
        engine=EngineConfig(turn_mode="simultaneous", max_actions_per_turn=7),
        clock=ClockConfig(enabled=True, start_hour=6, minutes_per_turn=30),
        render=RenderConfig(level="verbose", width=100),
    )
    d = c.to_dict()
    assert d["llm"]["provider"] == "mock"
    assert d["engine"]["turn_mode"] == "simultaneous"

    c2 = GameConfig.from_dict(d)
    assert c2.llm.provider == "mock"
    assert c2.llm.model == "x"
    assert c2.agent.temperature == 0.1
    assert c2.engine.max_actions_per_turn == 7
    assert c2.clock.enabled is True and c2.clock.minutes_per_turn == 30
    assert c2.render.level == "verbose"


def test_from_dict_no_llm_section_means_none():
    c = GameConfig.from_dict({"engine": {"turn_mode": "simultaneous"}})
    assert c.llm is None
    assert c.engine.turn_mode == "simultaneous"
    # omitted sections keep their defaults
    assert c.agent.temperature == 0.7


def test_from_dict_rejects_unknown_section():
    with pytest.raises(ValueError, match="Unknown config section"):
        GameConfig.from_dict({"bogus": {}})


def test_from_dict_rejects_unknown_key():
    with pytest.raises(ValueError, match="Unknown key"):
        GameConfig.from_dict({"engine": {"not_a_real_field": 1}})


def test_from_file_json(tmp_path):
    path = tmp_path / "config.json"
    path.write_text(
        json.dumps(
            {
                "engine": {"turn_mode": "simultaneous"},
                "clock": {"enabled": True, "start_hour": 6},
            }
        )
    )
    c = GameConfig.from_file(path)
    assert c.engine.turn_mode == "simultaneous"
    assert c.clock.enabled is True and c.clock.start_hour == 6


def test_from_file_yaml(tmp_path):
    pytest.importorskip("yaml")
    path = tmp_path / "config.yaml"
    path.write_text("engine:\n  turn_mode: simultaneous\nagent:\n  temperature: 0.2\n")
    c = GameConfig.from_file(path)
    assert c.engine.turn_mode == "simultaneous"
    assert c.agent.temperature == 0.2


def test_from_file_unsupported_extension(tmp_path):
    path = tmp_path / "config.toml"
    path.write_text("nope")
    with pytest.raises(ValueError, match="Unsupported config file type"):
        GameConfig.from_file(path)


def test_from_env_reads_llm_and_render(monkeypatch):
    monkeypatch.setenv("LLM_PROVIDER", "mock")
    monkeypatch.setenv("LLM_MODEL", "m")
    monkeypatch.setenv("OUTPUT_LEVEL", "verbose")
    monkeypatch.setenv("NO_COLOR", "1")
    c = GameConfig.from_env()
    assert c.llm.provider == "mock"
    assert c.llm.model == "m"
    assert c.render.level == "verbose"
    assert c.render.no_color is True


def test_from_env_no_provider_means_no_llm(monkeypatch):
    monkeypatch.delenv("LLM_PROVIDER", raising=False)
    monkeypatch.delenv("OUTPUT_LEVEL", raising=False)
    monkeypatch.delenv("NO_COLOR", raising=False)
    c = GameConfig.from_env()
    assert c.llm is None
    assert c.render.level is None


def test_build_llm_client_none_when_unset():
    assert GameConfig().build_llm_client() is None


# ----------------------------------------------------------------------
# Section A': observability (the usage-log knobs)
# ----------------------------------------------------------------------


def test_observability_round_trips_through_dict():
    c = GameConfig(
        observability=ObservabilityConfig(log_path="runs/", log_prompts=True)
    )
    d = c.to_dict()
    assert d["observability"] == {"log_path": "runs/", "log_prompts": True}

    c2 = GameConfig.from_dict(d)
    assert c2.observability.log_path == "runs/"
    assert c2.observability.log_prompts is True


def test_from_dict_rejects_unknown_observability_key():
    with pytest.raises(ValueError, match="Unknown key"):
        GameConfig.from_dict({"observability": {"nope": 1}})


def test_from_env_reads_observability(monkeypatch):
    monkeypatch.setenv("LLM_LOG", "runs/")
    monkeypatch.setenv("LLM_LOG_PROMPTS", "1")
    c = GameConfig.from_env()
    assert c.observability.log_path == "runs/"
    assert c.observability.log_prompts is True


def test_from_env_no_observability_means_off(monkeypatch):
    monkeypatch.delenv("LLM_LOG", raising=False)
    monkeypatch.delenv("LLM_LOG_PROMPTS", raising=False)
    c = GameConfig.from_env()
    assert c.observability.log_path is None
    assert c.observability.log_prompts is False


def test_build_run_log_none_when_logging_off():
    assert GameConfig().build_run_log(provider="mock", model="mock") is None


def test_build_run_log_directory_gets_timestamped_file(tmp_path):
    cfg = GameConfig(observability=ObservabilityConfig(log_path=str(tmp_path)))
    log = cfg.build_run_log(provider="mock", model="mock", turn_mode="simultaneous")
    assert isinstance(log, RunLog)
    # A directory log_path becomes a timestamped, provider-tagged file inside it.
    assert log.path.startswith(str(tmp_path))
    assert log.path.endswith("-mock.jsonl")
    assert log.provider == "mock" and log.turn_mode == "simultaneous"
    assert log.log_prompts is False


def test_build_run_log_explicit_file_used_verbatim(tmp_path):
    target = tmp_path / "cost.jsonl"
    cfg = GameConfig(
        observability=ObservabilityConfig(log_path=str(target), log_prompts=True)
    )
    log = cfg.build_run_log(provider="mock", model="mock")
    # A path ending in .jsonl/.json is used as-is (no timestamp inserted).
    assert log.path == str(target)
    assert log.log_prompts is True


def test_build_run_log_writes_artifact_end_to_end(tmp_path):
    """The config-built RunLog drives the same header/summary artifact as before."""
    from text_adventure_games.usage import UsageLedger

    cfg = GameConfig(observability=ObservabilityConfig(log_path=str(tmp_path)))
    ledger = UsageLedger()
    log = cfg.build_run_log(provider="mock", model="mock")
    with log:
        log.attach(ledger)
    lines = [json.loads(ln) for ln in open(log.path).read().splitlines()]
    assert lines[0]["kind"] == "run" and lines[0]["provider"] == "mock"
    assert lines[-1]["kind"] == "summary"


# ----------------------------------------------------------------------
# Section B: Game integration
# ----------------------------------------------------------------------


def test_no_config_reproduces_old_behavior():
    game = build_game()
    assert game.turn_mode == "sequential"
    assert game.clock is None
    assert game.phases is None
    assert game.give_hints is True
    assert game._max_actions_per_turn == 100
    assert game._cascade_passes == 2
    assert game.player.heard_max == 5


def test_config_drives_clock():
    cfg = GameConfig(clock=ClockConfig(enabled=True, start_hour=6, minutes_per_turn=30))
    game = build_game(config=cfg)
    assert game.clock is not None
    assert game.clock.start_hour == 6
    assert game.clock.minutes_per_turn == 30


def test_clock_disabled_by_default():
    game = build_game(config=GameConfig())
    assert game.clock is None


def test_explicit_time_config_overrides_config_clock():
    cfg = GameConfig(clock=ClockConfig(enabled=True, start_hour=6))
    game = build_game(time_config={"start_hour": 10}, config=cfg)
    assert game.clock.start_hour == 10


def test_config_drives_turn_mode():
    game = build_game(config=GameConfig(engine=EngineConfig(turn_mode="simultaneous")))
    assert game.turn_mode == "simultaneous"


def test_explicit_turn_mode_overrides_config():
    cfg = GameConfig(engine=EngineConfig(turn_mode="simultaneous"))
    game = build_game(config=cfg, turn_mode="sequential")
    assert game.turn_mode == "sequential"


def test_invalid_turn_mode_raises():
    with pytest.raises(Exception, match="invalid turn_mode"):
        build_game(config=GameConfig(engine=EngineConfig(turn_mode="bogus")))


def test_config_drives_phases():
    game = build_game(config=GameConfig(engine=EngineConfig(phases=True)))
    assert game.phases == DEFAULT_PHASES

    custom = {"go": 1, "attack": 2}
    game = build_game(config=GameConfig(engine=EngineConfig(phases=custom)))
    assert game.phases == custom


def test_config_drives_engine_caps_and_hints():
    cfg = GameConfig(
        engine=EngineConfig(
            give_hints=False,
            max_actions_per_turn=7,
            cascade_passes=5,
            heard_max=2,
        )
    )
    game = build_game(config=cfg)
    assert game.give_hints is False
    assert game._max_actions_per_turn == 7
    assert game._cascade_passes == 5
    assert game.player.heard_max == 2


def test_heard_buffer_respects_configured_cap():
    game = build_game(config=GameConfig(engine=EngineConfig(heard_max=2)))
    for i in range(5):
        game.player.hear(f"line {i}")
    assert game.player.heard == ["line 3", "line 4"]


def test_render_config_threads_to_parser():
    cfg = GameConfig(render=RenderConfig(level="quiet", width=40, no_color=True))
    game = build_game(config=cfg)
    # no_color=True forces the plain renderer with the configured width/level.
    from text_adventure_games.reporting import PlainRenderer

    assert isinstance(game.parser.renderer, PlainRenderer)
    assert game.parser.renderer.level == "quiet"
    assert game.parser.renderer.width == 40


# ----------------------------------------------------------------------
# Section C: agent wiring
# ----------------------------------------------------------------------


def test_llmagent_stores_sampling_config():
    agent = npc.LLMAgent(object(), max_tokens=64, temperature=0.2, max_duration=30)
    assert agent.max_tokens == 64
    assert agent.temperature == 0.2
    assert agent.max_duration == 30


def test_parse_duration_clamps_to_configured_max():
    assert npc._parse_duration("120", max_duration=30) == 30
    assert npc._parse_duration("10", max_duration=30) == 10
    # default cap is one in-game day
    assert npc._parse_duration("999999") == 24 * 60


def test_make_react_behavior_threads_agent_config(monkeypatch):
    captured = {}

    class SpyAgent(npc.LLMAgent):
        def __init__(self, client, **kwargs):
            captured.update(kwargs)
            super().__init__(client, **kwargs)

    monkeypatch.setattr(npc, "LLMAgent", SpyAgent)
    behavior = npc.make_react_behavior(
        object(),
        config=AgentConfig(temperature=0.3, max_tokens=64, max_duration=42),
    )
    assert callable(behavior)
    assert captured["temperature"] == 0.3
    assert captured["max_tokens"] == 64
    assert captured["max_duration"] == 42


def test_explicit_max_retries_overrides_config(monkeypatch):
    seen = {}

    def fake_react_behavior(character, game, agent, max_retries=1):
        seen["max_retries"] = max_retries
        return False

    monkeypatch.setattr(npc, "react_behavior", fake_react_behavior)

    # config says 4, but the explicit argument wins
    behavior = npc.make_react_behavior(
        object(), max_retries=9, config=AgentConfig(max_retries=4)
    )
    game = build_game()
    game.player.persona = "p"
    behavior(game.player, game)
    assert seen["max_retries"] == 9


def test_config_max_retries_used_when_arg_omitted(monkeypatch):
    seen = {}

    def fake_react_behavior(character, game, agent, max_retries=1):
        seen["max_retries"] = max_retries
        return False

    monkeypatch.setattr(npc, "react_behavior", fake_react_behavior)

    behavior = npc.make_react_behavior(object(), config=AgentConfig(max_retries=4))
    game = build_game()
    game.player.persona = "p"
    behavior(game.player, game)
    assert seen["max_retries"] == 4
