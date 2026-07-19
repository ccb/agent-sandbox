"""The live Penn server's REAL-LLM mode (issue #261, the live-LLM MVP).

Pins the contracts the ``--brain llm`` path stands on, fully offline (no SDK,
no network, no key -- a scripted "real-shaped" brain stands in for Anthropic):

* ``resolve_llm`` -- the mock default builds nothing; the llm mode merges the
  world YAML's ``llm:`` block with CLI overrides, accepts only Anthropic, and
  refuses to start without ``ANTHROPIC_API_KEY``;
* ``check_anthropic_key`` -- boot aborts when the API *rejects* the key (401/
  403), and shrugs off transient trouble (network down, 5xx) with a warning;
* the world YAML declares the model (``claude-haiku-4-5``) and cost ceiling,
  and ``PennWorld``/``meta()`` carry them to the stepper and the viewer;
* with a real brain wired: every agent decides through it, real conversations
  fire between co-located settled agents exactly once per cooldown window, the
  scripted meeting injector stands down, an API outage degrades to
  idle-and-retry (never a crash), and the cost ceiling ends the day.

Run from the repo root::

    uv run pytest godot-generative-agents/tests/test_penn_live_llm.py -v
"""

import io
import sys
import urllib.error
from pathlib import Path
from types import SimpleNamespace

import pytest

from backend.llm_monitor import LlmCallMonitor

# The Penn sim modules live in the Godot tree and are run as scripts (no
# package); import them off the sim directory, like test_penn_live.py.
_SIM_DIR = (
    Path(__file__).resolve().parents[2] / "godot-generative-agents" / "backend" / "penn"
)
sys.path.insert(0, str(_SIM_DIR))

import serve_penn  # noqa: E402
from penn_world import build_penn_world  # noqa: E402
from serve_penn import DEFAULT_LLM_MODEL, PennStepper, resolve_llm  # noqa: E402
from text_adventure_games.memory import MemoryKind  # noqa: E402
from text_adventure_games.usage import UsageLedger, record_call  # noqa: E402
from backend.planner import LLMPlanner, MockPlanner  # noqa: E402

# -------------------------------------------------------------- resolve_llm


def test_mock_brain_resolves_to_none_regardless_of_yaml():
    world_llm = {"provider": "anthropic", "model": "claude-haiku-4-5"}
    assert resolve_llm(world_llm, "mock") is None
    assert resolve_llm(None, "mock") is None


def test_llm_brain_merges_yaml_with_cli_overrides(monkeypatch):
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-ant-test")
    world_llm = {
        "provider": "anthropic",
        "model": "claude-haiku-4-5",
        "max_cost_usd": 5.0,
    }
    llm = resolve_llm(world_llm, "llm")
    assert llm == {
        "provider": "anthropic",
        "model": "claude-haiku-4-5",
        "max_cost_usd": 5.0,
    }
    # CLI overrides win for one run; the YAML dict itself is never mutated.
    llm = resolve_llm(world_llm, "llm", model="claude-haiku-4-5-20251001", max_cost=0.5)
    assert llm["model"] == "claude-haiku-4-5-20251001"
    assert llm["max_cost_usd"] == 0.5
    assert world_llm["model"] == "claude-haiku-4-5"


def test_llm_brain_defaults_to_haiku_without_a_yaml_block(monkeypatch):
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-ant-test")
    llm = resolve_llm(None, "llm")
    assert llm["provider"] == "anthropic"
    assert llm["model"] == DEFAULT_LLM_MODEL == "claude-haiku-4-5"


def test_llm_brain_accepts_only_anthropic(monkeypatch):
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-ant-test")
    with pytest.raises(SystemExit, match="anthropic"):
        resolve_llm({"provider": "openai"}, "llm")


def test_llm_brain_requires_the_anthropic_key(monkeypatch):
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    # Other keys in the environment must never satisfy (or be read by) the gate.
    monkeypatch.setenv("OPENAI_API_KEY", "sk-should-never-be-read")
    monkeypatch.setenv("LLM_API_KEY", "sk-should-never-be-read")
    with pytest.raises(SystemExit, match="ANTHROPIC_API_KEY"):
        resolve_llm({"provider": "anthropic"}, "llm")


# --------------------------------------------------- check_anthropic_key
#
# resolve_llm proves the key EXISTS; check_anthropic_key proves it WORKS,
# with one free models-list request at boot. Past boot, a rejected key is
# invisible by design (every decide error degrades to an idle tick -- the
# brain-outage contract), so the whole cast just sits on "waking up" at $0
# spend. The tests inject a fake ``urlopen`` and stay offline.


class _OkResponse:
    def close(self):
        pass


def test_key_check_exits_when_the_api_rejects_the_key(monkeypatch):
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-ant-wrong")

    def reject(request, timeout):
        raise urllib.error.HTTPError(
            request.full_url, 401, "Unauthorized", hdrs=None, fp=None
        )

    with pytest.raises(SystemExit, match="rejected"):
        serve_penn.check_anthropic_key(urlopen=reject)


def test_key_check_sends_the_key_and_passes_on_200(monkeypatch):
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-ant-good")
    seen = {}

    def accept(request, timeout):
        seen["url"] = request.full_url
        seen["key"] = request.get_header("X-api-key")
        return _OkResponse()

    serve_penn.check_anthropic_key(urlopen=accept)  # must not raise
    assert seen["url"].startswith("https://api.anthropic.com/v1/models")
    assert seen["key"] == "sk-ant-good"


def test_key_check_shrugs_off_network_trouble(monkeypatch, capsys):
    # Transient trouble (no network, a 5xx) is the run's retry path's job,
    # not a boot blocker: warn and continue instead of refusing to start.
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-ant-good")

    def down(request, timeout):
        raise urllib.error.URLError("no route to host")

    serve_penn.check_anthropic_key(urlopen=down)  # must not raise
    assert "could not verify" in capsys.readouterr().out


def test_key_check_shrugs_off_server_errors(monkeypatch, capsys):
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-ant-good")

    def overloaded(request, timeout):
        raise urllib.error.HTTPError(
            request.full_url, 529, "Overloaded", hdrs=None, fp=None
        )

    serve_penn.check_anthropic_key(urlopen=overloaded)  # must not raise
    assert "could not verify" in capsys.readouterr().out


# ------------------------------------------------- the world's llm: block


def test_world_yaml_declares_haiku():
    # The simulation config is the source of truth for WHICH model drives the
    # live cast: pin it so a silent model swap can't slip through review.
    pw = build_penn_world()
    assert pw.llm == {
        "provider": "anthropic",
        "model": "claude-haiku-4-5",
        "max_cost_usd": 5.0,
    }


# ----------------------------------------------- the real-brain live path
#
# PennStepper builds its clients through serve_penn.create_llm_client; the
# tests monkeypatch that factory so the whole --brain llm path runs against a
# scripted stand-in with the Anthropic adapter's exact seams (structured
# call_tool answers; one priced claude-haiku-4-5 ledger record per call).


class _ScriptedBrain:
    """A 'real-shaped' brain: answers the two structured tools the way a live
    model would, and records a priced haiku call (1000 in / 100 out =
    $0.0015) into its ledger -- so cost accounting, the monitor, and the
    kill-switch all see real numbers. ``fail=True`` simulates a provider
    outage: every route returns None, exactly like the Anthropic adapter after
    an API exception."""

    def __init__(self, ledger=None, fail=False):
        self.ledger = ledger or UsageLedger()
        self.context: dict = {}
        self.fail = fail
        self.tool_calls: list[str] = []
        self.chat_calls = 0

    def _record(self, messages, response):
        raw = SimpleNamespace(
            input_tokens=1000,
            output_tokens=100,
            cache_creation_input_tokens=0,
            cache_read_input_tokens=0,
        )
        record_call(
            self.ledger,
            self.context,
            "anthropic",
            "claude-haiku-4-5",
            raw,
            messages,
            str(response),
            latency_ms=42.0,
        )

    def chat(self, messages, max_tokens=256, temperature=0.0):
        self.chat_calls += 1
        self._record(messages, None)
        return None

    def call_tool(self, messages, tool, max_tokens=256, temperature=0.0):
        self.tool_calls.append(tool["name"])
        if self.fail:
            self._record(messages, None)
            return None
        if tool["name"] == "day_outline":
            result = {"blocks": [{"label": "midday", "summary": "lunch then study"}]}
        elif tool["name"] == "hourly_plan":
            result = {"hours": [{"start_hour": 12, "summary": "lunch at Houston Hall"}]}
        elif tool["name"] == "minute_plan":
            # Houston Hall is a real Penn location, so validate_stops keeps it and
            # the plan source is "llm" (a hallucinated place would be dropped ->
            # empty plan -> static fallback).
            result = {
                "stops": [
                    {
                        "place": "Houston Hall",
                        "activity": "eating lunch",
                        "emoji": "\U0001f37d️",
                        "steps": 10,
                    }
                ]
            }
        elif tool["name"] == "speak":
            result = {"utterance": "Want to compare notes on campus?", "done": True}
        elif tool["name"] == "conversation_outcome":
            # A live model reflecting on the meeting: an agreement + a note.
            result = {
                "plans_changed": True,
                "commitment": "meet up at the library later",
                "relationship_note": "Worth studying with again.",
            }
        else:  # choose_action
            result = {
                "reasoning": "scripted decision",
                "action": "perform",
                "arguments": "pondering the day",
            }
        self._record(messages, result)
        return result

    def count_tokens(self, text):
        return len(text) // 4


def _llm_stepper(monkeypatch, max_cost=5.0, fail=False, monitor=None, plan="schedule"):
    """A PennStepper in --brain llm mode, with the factory swapped for fakes."""

    def fake_create(config, ledger=None):
        assert str(config.provider).lower() == "anthropic"
        assert config.model == "claude-haiku-4-5"
        return _ScriptedBrain(ledger=ledger, fail=fail)

    monkeypatch.setattr(serve_penn, "create_llm_client", fake_create)
    llm = {
        "provider": "anthropic",
        "model": "claude-haiku-4-5",
        "max_cost_usd": max_cost,
    }
    return PennStepper(
        num_steps=50,
        world=build_penn_world(),
        monitor=monitor,
        llm=llm,
        plan_mode=plan,
    )


def _move(char, location):
    if char.location is not None:
        char.location.remove_character(char)
    location.add_character(char)


def _settle_pair_at_an_arena(stepper):
    """Force two agents settled + co-located (and the third settled far away),
    so the only thing tick() can do with the model is converse them."""
    vision_r = stepper.cog.vision_r
    arenas = [
        loc
        for loc in stepper.game.locations.values()
        if getattr(loc, "tile_address", None) is not None
    ]
    near = arenas[0]
    far = next(
        loc
        for loc in arenas
        if stepper.world.world_map.tile_gap(near.tile_address, loc.tile_address)
        > vision_r
    )
    a, b, c = (stepper.chars[name] for name in stepper.order)
    for char, spot in ((a, near), (b, near), (c, far)):
        _move(char, spot)
        # Teleporting must move the character's map tile too (issue #662):
        # perception and the conversation audience are tile-gated, so a pair
        # is only really "co-located" when standing on its arena, not when
        # parked there by location with spawn-distant tiles.
        char.tile = min(stepper.world.world_map.tiles_for(spot.tile_address))
        stepper.state[char.name].update({"performing": True, "path": []})
    return a, b


def test_real_brain_is_wired_and_the_injector_stands_down(monkeypatch):
    stepper = _llm_stepper(monkeypatch)
    assert isinstance(stepper.llm_client, _ScriptedBrain)
    for name in stepper.order:
        agent = stepper.chars[name].agent
        assert agent.llm_client is stepper.llm_client  # one shared brain
        assert agent.reflector is not None  # reflection wired (own client)
        assert agent.schedule is not stepper.llm_client  # pacing stays mock
    assert stepper.injector._meetings == []  # authored dialogue stands down
    assert stepper.meta()["llm"] == {
        "provider": "anthropic",
        "model": "claude-haiku-4-5",
    }
    # The ledger is armed with the config's ceiling and shared by every client.
    assert stepper.ledger.max_cost_usd == 5.0
    assert stepper.llm_client.ledger is stepper.ledger
    assert stepper.reflector_client.ledger is stepper.ledger


def test_llm_plan_mode_authors_each_agents_day(monkeypatch):
    stepper = _llm_stepper(monkeypatch, plan="llm")
    # A dedicated planner client (its own instance), recording into the ledger.
    assert isinstance(stepper.planner_client, _ScriptedBrain)
    assert stepper.planner_client is not stepper.llm_client
    assert stepper.planner_client.ledger is stepper.ledger
    # The three planning levels each ran (once per agent) at attach time.
    calls = stepper.planner_client.tool_calls
    assert calls.count("minute_plan") == len(stepper.order)
    assert "day_outline" in calls and "hourly_plan" in calls
    # Every agent now runs a model-authored plan, not the mock, and the
    # generated day (Houston Hall) replaced the authored schedule.
    for name in stepper.order:
        agent = stepper.chars[name].agent
        assert isinstance(agent.planner, LLMPlanner)
        assert [s.place for s in agent.plan.stops] == ["Houston Hall"]


def test_schedule_plan_mode_keeps_the_mock_planner(monkeypatch):
    stepper = _llm_stepper(monkeypatch)  # default plan="schedule"
    assert stepper.planner_client is None
    for name in stepper.order:
        assert isinstance(stepper.chars[name].agent.planner, MockPlanner)


def test_llm_plan_mode_requires_a_real_brain():
    # No llm dict (== --brain mock): the planner has no client to share.
    with pytest.raises(SystemExit, match="--plan llm needs --brain llm"):
        PennStepper(num_steps=2, world=build_penn_world(), plan_mode="llm")


def test_llm_plan_mode_rejects_the_scripted_brain():
    # --brain scripted's sentinel is truthy, so the guard must reject it too
    # (else the planner would try to build from an unset _llm_config -> crash).
    scripted = resolve_llm(None, "scripted")
    with pytest.raises(SystemExit, match="--plan llm needs --brain llm"):
        PennStepper(
            num_steps=2, world=build_penn_world(), llm=scripted, plan_mode="llm"
        )


def test_real_conversation_fires_once_and_cools_down(monkeypatch):
    stepper = _llm_stepper(monkeypatch)
    a, b = _settle_pair_at_an_arena(stepper)

    frame = stepper.tick()
    chat = frame[a.name]["chat"]
    assert chat, "co-located settled agents should have conversed"
    assert frame[b.name]["chat"] == chat
    assert {speaker for speaker, _ in chat} <= {a.name, b.name}
    assert "speak" in stepper.llm_client.tool_calls
    # Both participants remember the exchange as CHAT memories.
    for char in (a, b):
        kinds = {r.kind for r in char.agent.memory.records}
        assert MemoryKind.CHAT in kinds

    # The per-pair cooldown persists across ticks: the next tick must not
    # re-converse the (still settled, still co-located) pair.
    speak_calls = stepper.llm_client.tool_calls.count("speak")
    stepper.tick()
    assert stepper.llm_client.tool_calls.count("speak") == speak_calls

    # The consequence pass ran (#582): each participant recorded a high-importance
    # relationship note, and the outcome tool was called at most twice.
    from backend.cognition import RELATIONSHIP_NOTE_IMPORTANCE

    for char in (a, b):
        assert any(
            r.importance == RELATIONSHIP_NOTE_IMPORTANCE
            for r in char.agent.memory.records
        )
    assert stepper.llm_client.tool_calls.count("conversation_outcome") == 2


def test_brain_outage_degrades_to_idle_and_retry(monkeypatch):
    stepper = _llm_stepper(monkeypatch, fail=True)
    frame = stepper.tick()  # every agent hits its decision point; every call fails
    assert set(frame) == set(stepper.order)
    for name in stepper.order:
        st = stepper.state[name]
        assert st["path"] == [] and not st["performing"]  # idled, not crashed
        assert frame[name]["act"].startswith("waking up")
    # Still at a decision point next tick -> the stepper simply asks again.
    asked = len(stepper.llm_client.tool_calls)
    stepper.tick()
    assert len(stepper.llm_client.tool_calls) > asked


def test_cost_ceiling_ends_the_day(monkeypatch):
    stepper = _llm_stepper(monkeypatch, max_cost=0.001)  # < one $0.0015 call
    assert stepper.tick() is not None  # the tick that crosses the ceiling
    assert stepper.ledger.over_budget()
    assert stepper.tick() is None  # the gate ends the day before more spend
    assert stepper.step == 1


# ------------------------------------------------ the live event feed (#398)


def test_drain_events_feeds_the_monitor_rows_to_the_live_feed(monkeypatch):
    # backend.live probes drain_events() after every tick and publishes each
    # returned dict as a kind:"engine" event -- this is what puts the terminal
    # monitor's rows into the viewer HUD's request log. The payload is the
    # monitor's kept record, re-stamped kind:"llm_call" (to_primitive() says
    # kind:"call", which a feed consumer shouldn't have to know about).
    # The method also drains GameEvents as game_event rows (#467).
    monitor = LlmCallMonitor(stream=io.StringIO(), color=False)
    stepper = _llm_stepper(monkeypatch, monitor=monitor)
    assert stepper.drain_events() == []  # nothing before the first tick
    assert stepper.tick() is not None
    events = stepper.drain_events()
    llm_calls = [ev for ev in events if ev["kind"] == "llm_call"]
    assert llm_calls  # the t0 decides were monitored
    for ev in llm_calls:
        assert ev["model"] == "claude-haiku-4-5"
        # "outcome" (issue #582): maybe_converse now runs the post-conversation
        # consequence pass for each participant right after a real "speak" call.
        # "score" (issue #583): score_new_memories now runs on the real-brain
        # path right after remember_outcome, one score_memories call per acting
        # agent per tick -- the scripted brain answers it via the same
        # catch-all as every other unrecognized tool, so a "score" row is
        # expected here too.
        assert ev["role"] in {
            "decide",
            "converse",
            "reflect",
            "outcome",
            "score",
            "react",
        }
        assert {"call_no", "cum_cost_usd", "time", "actor", "cost_usd"} <= set(ev)
    all_drained = stepper.drain_events()
    assert all_drained == []  # drained means drained


def test_drain_events_has_no_llm_rows_without_a_monitor(monkeypatch):
    # --no-monitor: the monitor keeps nothing, but drain_events still returns
    # any GameEvents logged during the tick (#467).
    stepper = _llm_stepper(monkeypatch)
    assert stepper.tick() is not None
    events = stepper.drain_events()
    # Without a monitor there are no llm_call records, but game_events may exist.
    llm_calls = [ev for ev in events if ev["kind"] == "llm_call"]
    assert llm_calls == []  # no monitor means no llm_call rows
    # Without a monitor the only rows are engine game_events (#467), each the
    # EventState shape re-stamped with kind.
    for row in events:
        assert row["kind"] == "game_event"
        assert set(row) == {"turn", "actor", "action", "summary", "payload", "kind"}
