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
from backend.sim_config import CognitionConfig, SimulationConfig  # noqa: E402
from text_adventure_games.config import GameConfig  # noqa: E402
from text_adventure_games.embedding_client import EmbeddingConfig  # noqa: E402
from text_adventure_games.llm_client import LlmConfig  # noqa: E402


def test_library_personas_catalog():
    entries = library_personas(WORLD_DATA)
    ids = [e["id"] for e in entries]
    assert ids == sorted(ids)
    assert set(ids) == {
        # the #731 originals (default cast + first parked batch) ...
        "diego",
        "tanaka",
        "sofia",
        "maya",
        "priya",
        "ellis",
        "marcus",
        # ... plus the #762 library growth, round 1 (all parked, never in the default cast)
        "casey",
        "debra",
        "gus",
        "imani",
        "leon",
        "nadia",
        "rosa",
        "theo",
        # ... plus the #762 library growth, round 2 (also all parked)
        "aiden",
        "bethany",
        "chris",
        "dana",
        "desmond",
        "elena",
        "fatima",
        "grace",
        "hannah",
        "jamal",
        "lily",
        "mateo",
        "nina",
        "omar",
        "ravi",
        "sam",
        "tessa",
        "victor",
        "wesley",
        "yuki",
        # ... plus the #762 library growth, round 3 (campus workforce +
        # visitors; also all parked)
        "amara",
        "angela",
        "benny",
        "evelyn",
        "terrence",
        "vera",
    }
    by_id = {e["id"]: e for e in entries}
    assert by_id["diego"]["name"] == "Diego Torres"
    assert by_id["diego"]["in_default_cast"] is True
    assert by_id["maya"]["in_default_cast"] is False
    assert by_id["diego"]["blurb"].startswith("I am Diego Torres")


def test_library_personas_no_library_is_empty(tmp_path):
    world = tmp_path / "w.yaml"
    world.write_text("locations: []\n", encoding="utf-8")
    assert library_personas(world) == []


def test_library_personas_skips_syntax_broken_files(tmp_path):
    world = tmp_path / "w.yaml"
    world.write_text("cast: [ok]\nlocations: []\n", encoding="utf-8")
    lib = tmp_path / "personas"
    lib.mkdir()
    (lib / "ok.yaml").write_text("name: Ok\npersona: I am Ok.\n", encoding="utf-8")
    (lib / "broken.yaml").write_text("name: [unclosed\n", encoding="utf-8")
    assert [e["id"] for e in library_personas(world)] == ["ok"]


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


def test_apply_cast_subset_rebuilds_the_world(tmp_path):
    stepper = _mock_stepper(run_store=RunStore(tmp_path / "runs"))
    applied = stepper.apply_config(cast=["diego"], tick_seconds=0.1)
    assert stepper.order == ["Diego Torres"]
    assert applied["cast"] == ["diego"]
    assert stepper._decide_executor is None  # a mock brain stays serial (#732 fix 6)
    # the new run's manifest records the setup
    manifest = stepper.run_store.get_run(stepper.run_id)["manifest"]
    assert manifest["config"]["cast"] == ["diego"]
    assert manifest["config"]["run"]["tick_seconds"] == 0.1
    # and a later plain reset KEEPS the configured cast
    stepper.reset()
    assert stepper.order == ["Diego Torres"]


def test_unconfigured_manifest_has_no_config_block(tmp_path):
    stepper = _mock_stepper(run_store=RunStore(tmp_path / "runs"))
    assert "config" not in stepper.run_store.get_run(stepper.run_id)["manifest"]


def test_apply_brain_scripted_swaps_the_clients():
    stepper = _mock_stepper()
    assert stepper.llm_client is None
    stepper.apply_config(brain="scripted")
    assert stepper.llm == SCRIPTED
    assert stepper.llm_client is not None
    assert stepper.cognition_tools is True  # the scripted coupling re-resolved


def test_apply_sim_config_reaches_the_knobs():
    stepper = _mock_stepper()
    stepper.apply_config(sim_config={"cognition": {"vision_r": 3}})
    assert stepper.cog.vision_r == 3
    assert stepper.describe_config()["knobs"]["current"]["cognition"]["vision_r"] == 3


def test_apply_config_preserves_stripped_key_bearing_sections():
    """#753: GET /config strips embedding + game.llm (they can carry api_key
    material and never travel over HTTP), so a client posts them back absent.
    apply_config must MERGE the posted knobs over the live config, not
    full-replace -- else a server launched with a non-default embedding
    silently reverts to keyword relevance the moment any knob is edited."""
    launched = SimulationConfig(
        embedding=EmbeddingConfig(provider="mock"),
        game=GameConfig(llm=LlmConfig(provider="mock")),
        cognition=CognitionConfig(vision_r=5),
    )
    stepper = _mock_stepper(sim_config=launched)
    # Exactly what the client received from GET /config and posts back after
    # editing one unrelated knob: the full knobs.current, with the two
    # key-bearing sections already stripped by the server.
    posted = stepper.describe_config()["knobs"]["current"]
    assert "embedding" not in posted  # never on the wire
    assert "llm" not in posted["game"]  # never on the wire
    posted["cognition"]["vision_r"] = 3  # the user's edit

    stepper.apply_config(sim_config=posted)

    # The edit landed...
    assert stepper.sim_config.cognition.vision_r == 3
    # ...and the stripped, key-bearing sections survived (the bug reset them
    # to None). Compare on the provider string so an enum/str coercion in
    # rebuild can't make this brittle.
    assert stepper.sim_config.embedding is not None
    assert str(stepper.sim_config.embedding.provider) == "mock"
    assert stepper.sim_config.game.llm is not None
    assert str(stepper.sim_config.game.llm.provider) == "mock"


def test_apply_steps_is_the_new_baseline():
    stepper = _mock_stepper()
    stepper.apply_config(steps=3)
    assert stepper.num_steps == 3
    for _ in range(3):
        assert stepper.tick() is not None
    assert stepper.tick() is None  # day over at the configured budget


def test_apply_rejects_bad_input():
    stepper = _mock_stepper()
    with pytest.raises(ValueError):
        stepper.apply_config(cast=[])
    with pytest.raises(ValueError):
        stepper.apply_config(cast=["nobody"])
    with pytest.raises(ValueError):
        stepper.apply_config(brain="gpt")
    with pytest.raises(ValueError):
        stepper.apply_config(sim_config={"nope": {}})
    with pytest.raises(ValueError):
        stepper.apply_config(max_cost=1.0)  # cost ceiling needs the llm brain
    with pytest.raises(ValueError):
        stepper.apply_config(brain="mock", max_cost=1.0)  # explicit free brain, too
    # guard-before-teardown: every rejection above left the stepper serving
    assert stepper.tick() is not None


def test_apply_brain_llm_without_key_raises(monkeypatch):
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    stepper = _mock_stepper()
    with pytest.raises(ValueError, match="ANTHROPIC_API_KEY"):
        stepper.apply_config(brain="llm")


def test_apply_brain_llm_without_extra_fails_before_teardown(monkeypatch, tmp_path):
    # A keyed server missing the llm extra must reject brain="llm" BEFORE
    # closing the live run: the probe import fails pre-teardown, so the
    # stepper keeps serving and the run row is untouched.
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-test")
    monkeypatch.setitem(sys.modules, "anthropic", None)  # import -> ImportError
    stepper = _mock_stepper(run_store=RunStore(tmp_path / "runs"))
    run_id = stepper.run_id
    with pytest.raises(ValueError, match="extra llm"):
        stepper.apply_config(brain="llm")
    assert stepper.run_id == run_id
    assert stepper.tick() is not None


def test_switching_to_a_free_brain_clears_a_tripped_ceiling():
    # A paid run that hit its budget finishes every tick; after the gate
    # re-opens, reconfiguring to a free brain must actually run (#732
    # final review finding 1): the stale ceiling would otherwise keep
    # over_budget() true forever (an empty ledger's total is 0.0 >= 0.0).
    stepper = _mock_stepper()
    stepper.ledger.max_cost_usd = 0.0
    assert stepper.tick() is None  # ceiling tripped: day ends immediately
    stepper.apply_config(brain="mock")
    assert stepper.ledger.max_cost_usd is None
    assert stepper.tick() is not None


def test_plan_follows_the_configured_brain_and_is_overridable():
    # #787: the setup screen picks a brain, and the planner follows it -- the
    # config session is the run's setup authority, so a server launched on the
    # default "auto" must re-resolve against the brain THIS apply lands on
    # rather than being frozen at boot.
    stepper = _mock_stepper()
    assert stepper.plan_mode == "schedule"  # free brain: the authored day
    assert stepper.apply_config(brain="scripted")["plan"] == "schedule"
    # A brain-only apply carries no `plan`, so the request flag itself must
    # stay untouched (still "auto") -- only the resolved value re-follows the
    # new brain.
    assert stepper._plan_mode_flag == "auto"
    # An explicit planner on a brain with no client to plan with is refused
    # (a 400 upstream), the same rule --plan llm applies at launch.
    with pytest.raises(ValueError, match="needs the llm brain"):
        stepper.apply_config(plan="llm")
    # ...and an explicit "schedule" sticks: it survives later applies, so a
    # deliberate opt-out isn't silently undone by the auto rule.
    stepper.apply_config(plan="schedule")
    assert stepper._plan_mode_flag == "schedule"
    with pytest.raises(ValueError, match="unknown plan"):
        stepper.apply_config(plan="nonsense")


def test_post_config_accepts_the_plan_knob():
    client, stepper = _client()
    body = client.get("/config").json()
    assert body["plans"] == ["auto", "schedule", "llm"]
    assert body["run"]["plan"] == "schedule"
    resp = client.post("/config", json={"plan": "schedule", "brain": "scripted"})
    assert resp.status_code == 200
    assert resp.json()["applied"]["plan"] == "schedule"
    # A model planner with no model to plan with is a 400, not a 500.
    assert client.post("/config", json={"plan": "llm"}).status_code == 400


def test_config_serves_the_asked_for_plan():
    # #791: run.plan is the RESOLVED planner (never "auto"), which is the wrong
    # default for a setup-screen dropdown -- an untouched dropdown must mean
    # "keep the session's request" under the only-send-changed contract. So
    # both GET /config and the applied echo also carry the raw request.
    client, stepper = _client()
    body = client.get("/config").json()
    assert body["run"]["plan"] == "schedule"  # resolved: free brain
    assert body["run"]["plan_request"] == "auto"  # what was actually asked
    resp = client.post("/config", json={"plan": "schedule", "brain": "scripted"})
    assert resp.status_code == 200
    applied = resp.json()["applied"]
    assert applied["plan"] == "schedule"
    assert applied["plan_request"] == "schedule"
    # The next GET reflects the new request, so a reloaded setup screen
    # defaults to the explicit opt-out rather than silently reverting to auto.
    assert client.get("/config").json()["run"]["plan_request"] == "schedule"


def test_effort_is_advertised_and_paid_brain_only():
    # #845: thinking depth joins the config surface as a vocabulary + a current
    # value, so a client hard-codes no level list and an untouched dropdown means
    # "keep the session's depth". It is a paid-brain setting: a free brain reports
    # "default" and refuses a level rather than accepting an inert one.
    stepper = _mock_stepper()
    cfg = stepper.describe_config()
    assert cfg["efforts"] == ["default", "low", "medium", "high", "xhigh", "max"]
    assert cfg["run"]["effort"] == "default"
    with pytest.raises(ValueError, match="needs the llm brain"):
        stepper.apply_config(effort="high")
    with pytest.raises(ValueError, match="unknown effort"):
        stepper.apply_config(effort="nonsense")
    # guard-before-teardown: both rejections left the stepper serving
    assert stepper.tick() is not None
    # "default" on a free brain is a no-op, not an error -- it asks for exactly
    # what a free brain already has, so a re-run seed can send it unconditionally.
    assert stepper.apply_config(effort="default")["effort"] == "default"


def test_post_config_accepts_the_effort_knob():
    client, stepper = _client()
    body = client.get("/config").json()
    assert "medium" in body["efforts"]
    assert body["run"]["effort"] == "default"
    # A depth with no paid brain to think with is a 400, not a 500 (the plan
    # knob's rule) -- this also pins that req.effort reaches apply_config at all.
    resp = client.post("/config", json={"effort": "high"})
    assert resp.status_code == 400
    assert "llm brain" in resp.json()["detail"]
    assert client.post("/config", json={"effort": "nonsense"}).status_code == 400


def test_model_is_advertised_and_paid_brain_only():
    # #887: the model joins the config surface, so a saved run's model can be
    # asked for again on a fresh server instead of silently resolving the world
    # YAML's. The vocabulary is the PRICED Anthropic models -- an unpriced model
    # costs $0 in usage.price, so a run driven by one reports no spend at all.
    stepper = _mock_stepper()
    cfg = stepper.describe_config()
    assert "claude-sonnet-5" in cfg["models"]
    assert "claude-haiku-4-5" in cfg["models"]
    assert not [m for m in cfg["models"] if not m.startswith("claude-")]
    # Concrete even on a free brain: the model a switch to llm would use, which
    # is what makes leaving the dropdown untouched safe.
    assert cfg["run"]["model"] == "claude-haiku-4-5"
    with pytest.raises(ValueError, match="needs the llm brain"):
        stepper.apply_config(model="claude-sonnet-5")
    with pytest.raises(ValueError, match="unknown model"):
        stepper.apply_config(model="claude-sonnet-9")
    # An OpenAI model is priced but not offered: resolve_llm is Anthropic-only.
    with pytest.raises(ValueError, match="unknown model"):
        stepper.apply_config(model="gpt-4o")
    assert stepper.tick() is not None  # guard-before-teardown


def test_post_config_accepts_the_model_knob():
    client, stepper = _client()
    body = client.get("/config").json()
    assert "claude-sonnet-5" in body["models"]
    assert body["run"]["model"] == "claude-haiku-4-5"
    # Pins that req.model reaches apply_config, and that both rejections are
    # 400s rather than 500s.
    resp = client.post("/config", json={"model": "claude-sonnet-5"})
    assert resp.status_code == 400
    assert "llm brain" in resp.json()["detail"]
    assert client.post("/config", json={"model": "nope"}).status_code == 400


def test_create_run_drops_a_prior_applied_config(tmp_path):
    stepper = _mock_stepper(run_store=RunStore(tmp_path / "runs"))
    stepper.apply_config(cast=["diego"])
    assert stepper.order == ["Diego Torres"]
    new_id = stepper.create_run("penn")
    # the named-world create is a fresh default-cast setup: full cast back,
    # no stale config block claiming otherwise (#732 final review finding 2)
    assert len(stepper.order) == 3
    assert "config" not in stepper.run_store.get_run(new_id)["manifest"]
    stepper.reset()  # and the configured cast must not resurface
    assert len(stepper.order) == 3


pytest.importorskip("fastapi")
pytest.importorskip("httpx")

from fastapi.testclient import TestClient  # noqa: E402

from backend.api import create_app  # noqa: E402


def _client(tmp_path=None, **stepper_kw):
    if tmp_path is not None:
        stepper_kw.setdefault("run_store", RunStore(tmp_path / "runs"))
    stepper = _mock_stepper(**stepper_kw)
    app = create_app(
        _GameProxy(stepper), stepper=stepper, start_paused=True, tick_seconds=0.05
    )
    return TestClient(app), stepper


def test_get_config_configurable_at_tick_zero():
    client, _ = _client()
    body = client.get("/config").json()
    assert body["status"] == "configurable"
    assert body["run"]["tick_seconds"] == 0.05
    assert {"personas", "cast", "knobs", "brains", "run"} <= set(body)


def test_config_locks_once_started():
    client, _ = _client()
    client.post("/resume")  # the Start button: paused -> False, gate closes
    assert client.get("/config").json()["status"] == "locked"
    resp = client.post("/config", json={"cast": ["diego"]})
    assert resp.status_code == 409


def test_post_config_applies_cast_and_publishes_adoption(tmp_path):
    client, stepper = _client(tmp_path)
    resp = client.post("/config", json={"cast": ["diego"], "tick_seconds": 0.5})
    assert resp.status_code == 200
    body = resp.json()
    assert body["applied"]["cast"] == ["diego"]
    assert body["run_id"] == stepper.run_id
    # the live handshake now shows the sub-cast and the new cadence
    live = client.get("/live").json()
    assert [p["name"] for p in live["meta"]["personas"]] == ["Diego Torres"]
    assert live["tick_seconds"] == 0.5
    # followers got the standard rebuild signal
    events = client.get("/events?since=0").json()["events"]
    assert any(
        e["kind"] == "status" and e.get("reason") == "reset" and e.get("run_id")
        for e in events
    )
    # still configurable (paused, tick 0): the UI may keep adjusting
    assert client.get("/config").json()["status"] == "configurable"
    assert client.get("/config").json()["cast"] == ["diego"]
    # and the persisted manifest records the setup
    manifest = client.get(f"/runs/{body['run_id']}").json()["manifest"]
    assert manifest["config"]["cast"] == ["diego"]


def test_post_config_bad_inputs_are_400():
    client, _ = _client()
    assert client.post("/config", json={"cast": []}).status_code == 400
    assert client.post("/config", json={"cast": ["nobody"]}).status_code == 400
    assert client.post("/config", json={"brain": "gpt"}).status_code == 400
    assert client.post("/config", json={"sim_config": {"nope": {}}}).status_code == 400


def test_post_config_llm_without_key_is_400(monkeypatch):
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    client, _ = _client()
    assert client.post("/config", json={"brain": "llm"}).status_code == 400


def test_runs_index_carries_the_config_block(tmp_path):
    """#734: each /runs row exposes its manifest's applied `config` block (or
    None), so the Past-runs browser can show a run's setup and re-run it
    without fetching every manifest."""
    client, stepper = _client(tmp_path)
    # The boot run was never configured -> its row's config is None, and the
    # full manifest still stays off the list.
    rows = client.get("/runs").json()["runs"]
    assert len(rows) == 1
    assert rows[0]["config"] is None
    assert "manifest" not in rows[0]
    # Configure a run; its row now carries the applied block verbatim.
    client.post("/config", json={"cast": ["diego"], "tick_seconds": 0.5})
    rows = client.get("/runs").json()["runs"]
    current = next(r for r in rows if r["id"] == stepper.run_id)
    assert current["config"]["cast"] == ["diego"]
    assert current["config"]["brain"] == "mock"
    assert current["config"]["run"]["tick_seconds"] == 0.5


def test_config_404_without_a_live_loop():
    from backend.api import _demo_game

    client = TestClient(create_app(_demo_game()))
    assert client.get("/config").status_code == 404
    assert client.post("/config", json={}).status_code == 404
