"""#732: the pre-run config-session seam.

Stepper-level coverage for describe_config()/apply_config() plus the HTTP
routes (GET/POST /config). Fully offline: mock or scripted brain, no keys,
no spend. Run from the repo root:

    PYTHONPATH=.:godot-generative-agents uv run pytest \
        godot-generative-agents/tests/test_config_api_732.py -v
"""

import sys
from pathlib import Path

import pytest

# Penn sim scripts import each other flat, off the sim dir (the
# test_rerun_bridge_715.py shim).
_REPO_ROOT = Path(__file__).resolve().parents[2]
_SIM_DIR = _REPO_ROOT / "godot-generative-agents" / "backend" / "penn"
sys.path.insert(0, str(_SIM_DIR))

from penn_world import WORLD_DATA, build_penn_world  # noqa: E402
from serve_penn import SCENARIOS, SCRIPTED, PennStepper, _GameProxy  # noqa: E402

from backend.build_world import library_personas  # noqa: E402
from backend.run_store import RunStore  # noqa: E402


def test_library_personas_catalog():
    entries = library_personas(WORLD_DATA)
    ids = [e["id"] for e in entries]
    assert ids == sorted(ids)
    assert set(ids) == {"diego", "tanaka", "sofia", "maya", "priya", "ellis", "marcus"}
    by_id = {e["id"]: e for e in entries}
    assert by_id["diego"]["name"] == "Diego Torres"
    assert by_id["diego"]["in_default_cast"] is True
    assert by_id["maya"]["in_default_cast"] is False
    assert by_id["diego"]["blurb"].startswith("I am Diego Torres")


def test_library_personas_no_library_is_empty(tmp_path):
    world = tmp_path / "w.yaml"
    world.write_text("locations: []\n", encoding="utf-8")
    assert library_personas(world) == []


def test_penn_world_carries_its_yaml_path():
    assert build_penn_world().world_data == WORLD_DATA


def test_scenario_builders_accept_cast():
    for name, scenario in SCENARIOS.items():
        world = scenario["world"](cast=["diego"])
        assert [p["name"] for p in world.personas] == ["Diego Torres"], name


def test_reset_keeps_a_configured_cast():
    stepper = PennStepper(num_steps=2, world=build_penn_world(cast=["diego"]))
    stepper._cast = ["diego"]  # what apply_config records (Task 4)
    stepper.reset()
    assert stepper.order == ["Diego Torres"]


def _mock_stepper(**kw):
    kw.setdefault("num_steps", 6)
    kw.setdefault("world", build_penn_world())
    kw.setdefault("seed", 0)
    return PennStepper(**kw)


def test_describe_config_shape(monkeypatch):
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    stepper = _mock_stepper()
    cfg = stepper.describe_config()
    assert {e["id"] for e in cfg["personas"]} >= {"diego", "maya"}
    assert cfg["cast"] == ["diego", "sofia", "tanaka"]  # sorted ids of the MVP cast
    assert cfg["brains"] == ["mock", "scripted"]  # llm needs a key (below)
    assert cfg["run"]["brain"] == "mock"
    assert cfg["run"]["steps"] == 6
    assert cfg["run"]["max_cost"] is None
    # 6 steps x 10s from the 08:00 start
    assert cfg["run"]["stop_time"] == "2023-02-13 08:01:00"
    # knob defaults == an empty SimulationConfig, with the key-carrying
    # sections stripped; an unconfigured server's current == defaults.
    assert "llm" not in cfg["knobs"]["defaults"]["game"]
    assert "embedding" not in cfg["knobs"]["defaults"]
    assert cfg["knobs"]["current"] == cfg["knobs"]["defaults"]


def test_llm_advertised_only_with_a_key(monkeypatch):
    stepper = _mock_stepper()
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-test")
    assert "llm" in stepper.describe_config()["brains"]
    monkeypatch.delenv("ANTHROPIC_API_KEY")
    assert "llm" not in stepper.describe_config()["brains"]


def test_scripted_boot_reports_scripted_brain():
    stepper = _mock_stepper(llm=SCRIPTED)
    assert stepper.describe_config()["run"]["brain"] == "scripted"
