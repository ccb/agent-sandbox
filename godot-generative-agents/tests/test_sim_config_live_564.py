"""serve_penn --config: the #564 live-tuning seam.

Pins that a SimulationConfig loaded from a file reaches the live path:
retrieval weights into every decide (via step()'s existing retrieval param),
temperature / reflection_threshold onto each agent (via attach_agents), and
the cognition knobs into PennStepper.cog -- with NO --config byte-identical to
today by construction. Fully offline (mock brain). Run from the repo root:

    uv run pytest godot-generative-agents/tests/test_sim_config_live_564.py -v
"""

import json
import sys
from pathlib import Path

import pytest

# The Penn sim modules live in the Godot tree and are run as scripts (no
# package); tests import them the way the scripts import each other -- off the
# sim directory itself (same shim as test_penn_live_llm.py).
_SIM_DIR = (
    Path(__file__).resolve().parents[2] / "godot-generative-agents" / "backend" / "penn"
)
sys.path.insert(0, str(_SIM_DIR))

import serve_penn  # noqa: E402
from penn_world import build_penn_world  # noqa: E402
from serve_penn import PennStepper, _build_parser  # noqa: E402

from backend.cognition import attach_agents  # noqa: E402
from backend.run_simulation import observe_and_decide  # noqa: E402
from backend.run_store import RunStore  # noqa: E402
from backend.sim_config import (  # noqa: E402
    CognitionConfig,
    RetrievalConfig,
    SimulationConfig,
)
from text_adventure_games.config import AgentConfig  # noqa: E402


def _cfg(data: dict) -> SimulationConfig:
    return SimulationConfig.from_dict(data)


# -- Task 1: attach_agents threads temperature / reflection_threshold --------


def test_attach_agents_threads_temperature_and_reflection_threshold():
    world = build_penn_world()
    _game, chars = world.build_world_fn(world.world_map)
    attach_agents(chars, world.personas, temperature=0.0, reflection_threshold=10.0)
    for p in world.personas:
        agent = chars[p["name"]].agent
        assert agent.temperature == 0.0
        assert agent.reflection_threshold == 10.0


def test_attach_agents_defaults_are_unchanged():
    world = build_penn_world()
    _game, chars = world.build_world_fn(world.world_map)
    attach_agents(chars, world.personas)
    for p in world.personas:
        agent = chars[p["name"]].agent
        assert agent.temperature == 0.7  # LLMAgent's own default
        assert agent.reflection_threshold == 30.0  # DEFAULT_REFLECTION_THRESHOLD


# -- Task 2: PennStepper holds the config and applies it at _build -----------


def test_stepper_sim_config_threads_cognition_and_temperature():
    cfg = _cfg(
        {
            "game": {"agent": {"temperature": 0.0, "reflection_threshold": 10.0}},
            "cognition": {"vision_r": 2, "conversation_cooldown_steps": 5},
            "retrieval": {"max_records": 1},
        }
    )
    stepper = PennStepper(num_steps=2, world=build_penn_world(), sim_config=cfg)
    assert stepper.cog.vision_r == 2
    assert stepper.cog.conversation_cooldown_steps == 5
    assert stepper.retrieval.max_records == 1
    for char in stepper.chars.values():
        assert char.agent.temperature == 0.0
        assert char.agent.reflection_threshold == 10.0
        assert char.vision_r == 2  # attach_agents' vision_r came from cog


def test_stepper_sim_config_survives_reset():
    cfg = _cfg({"cognition": {"vision_r": 2}})
    stepper = PennStepper(num_steps=2, world=build_penn_world(), sim_config=cfg)
    stepper.reset()  # POST /reset re-runs _build -- the config must re-apply
    assert stepper.cog.vision_r == 2


def test_stepper_without_config_keeps_todays_defaults():
    stepper = PennStepper(num_steps=2, world=build_penn_world())
    assert stepper.sim_config is None
    assert stepper.retrieval is None
    assert stepper.cog == CognitionConfig()  # mock brain: no flag couplings fire
    for char in stepper.chars.values():
        assert char.agent.temperature == 0.7


def test_cli_flag_still_forces_cognition_tools_on_over_config():
    cfg = _cfg({"cognition": {"cognition_tools": False}})
    stepper = PennStepper(
        num_steps=2, world=build_penn_world(), sim_config=cfg, cognition_tools=True
    )
    assert stepper.cog.cognition_tools is True


def test_config_can_switch_cognition_tools_and_react_on():
    cfg = _cfg({"cognition": {"cognition_tools": True, "react_enabled": True}})
    stepper = PennStepper(num_steps=2, world=build_penn_world(), sim_config=cfg)
    assert stepper.cognition_tools is True
    assert stepper.cog.cognition_tools is True
    assert stepper.react is True
    assert stepper.cog.react_enabled is True


# -- Task 3: retrieval reaches every live decide ------------------------------


def _tick_with_step_spy(monkeypatch, stepper):
    """Tick once with serve_penn.step wrapped so its kwargs are captured."""
    captured = {}
    real_step = serve_penn.step

    def spy(*args, **kwargs):
        captured.update(kwargs)
        return real_step(*args, **kwargs)

    monkeypatch.setattr(serve_penn, "step", spy)
    stepper.tick()
    return captured


def test_tick_passes_the_config_retrieval_into_step(monkeypatch):
    cfg = _cfg({"retrieval": {"max_records": 1, "alpha_recency": 3.0}})
    stepper = PennStepper(num_steps=2, world=build_penn_world(), sim_config=cfg)
    captured = _tick_with_step_spy(monkeypatch, stepper)
    assert captured["retrieval"] is stepper.retrieval
    assert captured["retrieval"].max_records == 1


def test_tick_without_config_passes_retrieval_none(monkeypatch):
    stepper = PennStepper(num_steps=2, world=build_penn_world())
    captured = _tick_with_step_spy(monkeypatch, stepper)
    assert captured["retrieval"] is None  # byte-identical default path


def test_retrieval_config_visibly_changes_what_surfaces():
    # The acceptance's offline half: with more memories than max_records, a
    # tight retrieval config surfaces fewer memories at decide time than the
    # default -- the same observe_and_decide call the live step loop makes.
    stepper = PennStepper(num_steps=2, world=build_penn_world())
    name = stepper.order[0]
    char = stepper.chars[name]
    for i in range(4):
        char.agent.memory.add_observation(f"observation number {i}", turn=i + 1)

    observe_and_decide(stepper.game, char, 5, retrieval=RetrievalConfig(max_records=1))
    assert len(char.agent.last_retrieved) == 1
    observe_and_decide(stepper.game, char, 5, retrieval=None)
    assert len(char.agent.last_retrieved) > 1


# -- Task 4: the config rides the manifest so #715 re-runs reproduce it -------


def test_manifest_records_sim_config_and_roundtrips():
    cfg = _cfg(
        {"retrieval": {"max_records": 1}, "game": {"agent": {"temperature": 0.0}}}
    )
    stepper = PennStepper(num_steps=2, world=build_penn_world(), sim_config=cfg)
    manifest = stepper._store_manifest()
    assert manifest["sim_config"]["retrieval"]["max_records"] == 1
    rebuilt = serve_penn._sim_config_from_manifest(manifest)
    assert rebuilt.retrieval.max_records == 1
    assert rebuilt.game.agent.temperature == 0.0


def test_manifest_sim_config_is_none_without_config():
    stepper = PennStepper(num_steps=2, world=build_penn_world())
    manifest = stepper._store_manifest()
    assert manifest["sim_config"] is None
    assert serve_penn._sim_config_from_manifest(manifest) is None


def test_sim_config_from_manifest_tolerates_old_manifests():
    # Runs recorded before #564 have no sim_config key at all.
    assert serve_penn._sim_config_from_manifest({"seed": 0}) is None


def test_manifest_sim_config_never_stores_api_keys():
    cfg = _cfg(
        {
            "retrieval": {"max_records": 1},
            "game": {"llm": {"provider": "anthropic", "api_key": "sk-SECRET"}},
            "embedding": {"provider": "mock", "api_key": "sk-SECRET2"},
        }
    )
    stepper = PennStepper(num_steps=2, world=build_penn_world(), sim_config=cfg)
    manifest = stepper._store_manifest()
    assert "sk-SECRET" not in json.dumps(manifest)
    assert "llm" not in manifest["sim_config"]["game"]
    assert "embedding" not in manifest["sim_config"]
    # The stripped manifest still reconstructs (llm/embedding read back as None).
    rebuilt = serve_penn._sim_config_from_manifest(manifest)
    assert rebuilt.retrieval.max_records == 1


# -- Task 5: the --config CLI flag --------------------------------------------


def test_config_flag_defaults_to_none():
    assert _build_parser().parse_args([]).config is None


def test_config_flag_takes_a_path():
    assert _build_parser().parse_args(["--config", "sim.yaml"]).config == "sim.yaml"


def test_from_file_malformed_yaml_raises_value_error(tmp_path):
    bad = tmp_path / "bad.yaml"
    bad.write_text("retrieval: [unclosed", encoding="utf-8")
    with pytest.raises(ValueError, match="invalid YAML"):
        SimulationConfig.from_file(bad)


# -- Post-review hardening (#564 review) --------------------------------------
#
# Finding 1: resume (boot --resume and mid-process resume_run()) adopts the
# resumed run's OWN recorded sim_config over whatever this server booted
# with -- otherwise the world silently continues under different knobs and a
# later --re-run of the same run reports DIVERGED.


def test_resume_adopts_manifest_sim_config_boot_path(tmp_path, capsys):
    store = RunStore(tmp_path / "runs")
    recorded_cfg = _cfg({"retrieval": {"max_records": 1}, "cognition": {"vision_r": 2}})
    first = PennStepper(
        num_steps=4, world=build_penn_world(), run_store=store, sim_config=recorded_cfg
    )
    run_id = first.run_id
    first.tick()
    del first  # crash case: the row is orphaned at "running"

    # This server boots with a DIFFERENT config -- the recorded one must win.
    other_cfg = _cfg({"cognition": {"vision_r": 8}})
    resumed = PennStepper(
        num_steps=4,
        world=build_penn_world(),
        run_store=store,
        resume_run_id=run_id,
        sim_config=other_cfg,
    )
    assert resumed.sim_config.to_dict() == recorded_cfg.to_dict()
    assert resumed.cog.vision_r == 2
    assert resumed.retrieval.max_records == 1
    assert "adopts its recorded sim_config" in capsys.readouterr().out


def test_resume_without_recorded_config_keeps_this_servers_own(tmp_path):
    # Pre-#564 (or plain, unconfigured) manifests have no sim_config key at
    # all -- resume must leave this server's own config untouched.
    store = RunStore(tmp_path / "runs")
    first = PennStepper(num_steps=4, world=build_penn_world(), run_store=store)
    run_id = first.run_id
    first.tick()
    del first

    own_cfg = _cfg({"cognition": {"vision_r": 3}})
    resumed = PennStepper(
        num_steps=4,
        world=build_penn_world(),
        run_store=store,
        resume_run_id=run_id,
        sim_config=own_cfg,
    )
    assert resumed.sim_config is own_cfg
    assert resumed.cog.vision_r == 3


def test_resume_cli_flag_still_forces_cognition_tools_on_over_recorded_config(
    tmp_path,
):
    # The one-way rule (a boolean CLI flag always wins) must survive the
    # resume-adoption re-derivation, not just the original __init__ one.
    store = RunStore(tmp_path / "runs")
    recorded_cfg = _cfg({"cognition": {"cognition_tools": False}})
    first = PennStepper(
        num_steps=4, world=build_penn_world(), run_store=store, sim_config=recorded_cfg
    )
    run_id = first.run_id
    first.tick()
    del first

    resumed = PennStepper(
        num_steps=4,
        world=build_penn_world(),
        run_store=store,
        resume_run_id=run_id,
        cognition_tools=True,
    )
    assert resumed.cognition_tools is True


def test_resume_run_mid_process_adopts_manifest_sim_config(tmp_path, capsys):
    # POST /runs/{id}/resume's stepper half (resume_run(), not just boot).
    store = RunStore(tmp_path / "runs")
    recorded_cfg = _cfg({"cognition": {"vision_r": 2}})
    stepper = PennStepper(
        num_steps=4, world=build_penn_world(), run_store=store, sim_config=recorded_cfg
    )
    a = stepper.run_id
    stepper.tick()
    stepper.reset()
    stepper.tick()
    # Pretend the live server is currently running under a DIFFERENT config
    # than run `a` was recorded with (reset() does not itself change
    # sim_config, so this stands in for a server that was reconfigured, or
    # simply booted plain, between `a`'s day and this resume).
    other_cfg = _cfg({"cognition": {"vision_r": 5}})
    stepper.sim_config = other_cfg
    stepper.retrieval = other_cfg.retrieval
    stepper.resume_run(a)
    assert stepper.cog.vision_r == 2  # run `a`'s OWN recorded config wins
    assert "adopts its recorded sim_config" in capsys.readouterr().out


# Finding 3: the boot "Sim config:" print must not crash on a config field
# left blank (YAML null -> None), which `:g` formatting can't handle.


def test_fmt_or_default_is_none_safe():
    assert serve_penn._fmt_or_default(None) == "default"
    assert serve_penn._fmt_or_default(1.5) == "1.5"


def test_sim_config_with_blank_numeric_fields_is_none_safe(tmp_path):
    path = tmp_path / "sim.yaml"
    path.write_text(
        "retrieval:\n  alpha_recency:\ngame:\n  agent:\n    temperature:\n",
        encoding="utf-8",
    )
    cfg = SimulationConfig.from_file(path)
    assert cfg.retrieval.alpha_recency is None
    assert cfg.game.agent.temperature is None
    # What the boot print does with these -- must not raise.
    assert serve_penn._fmt_or_default(cfg.retrieval.alpha_recency) == "default"
    assert serve_penn._fmt_or_default(cfg.game.agent.temperature) == "default"


# Finding 4: the engine's own game.agent.cognition_tools (a plain GameConfig
# key) must not be silently dead just because it rides inside a
# SimulationConfig alongside the sim-level cognition.cognition_tools.


def test_engine_agent_config_cognition_tools_defaults_false():
    # The precondition finding 4's OR-resolution relies on: OR-ing in this
    # key can never turn cognition tools on by default.
    assert AgentConfig().cognition_tools is False


def test_engine_agent_cognition_tools_key_also_switches_it_on():
    cfg = _cfg({"game": {"agent": {"cognition_tools": True}}})
    stepper = PennStepper(num_steps=2, world=build_penn_world(), sim_config=cfg)
    assert stepper.cognition_tools is True
    assert stepper.cog.cognition_tools is True


# Finding 5: --config alongside --re-run is silently ignored (reproduce_run
# always reconstructs the manifest's own config); main() must say so.


def test_main_re_run_with_config_warns_and_is_ignored(tmp_path, monkeypatch, capsys):
    # Redirect the run store so this stays offline with no real runs/ dir.
    monkeypatch.setattr(serve_penn, "DEFAULT_RUNS_DIR", tmp_path / "runs")
    cfg_path = tmp_path / "sim.yaml"
    cfg_path.write_text("retrieval:\n  max_records: 1\n", encoding="utf-8")
    monkeypatch.setattr(
        sys,
        "argv",
        ["serve_penn.py", "--re-run", "run-does-not-exist", "--config", str(cfg_path)],
    )
    with pytest.raises(SystemExit):
        serve_penn.main()
    out = capsys.readouterr().out
    assert f"--config {cfg_path} is ignored for --re-run" in out
