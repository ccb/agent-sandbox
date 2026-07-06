"""The live Penn server's REAL-LLM mode (issue #261, the live-LLM MVP).

Pins the contracts the ``--brain llm`` path stands on, fully offline (no SDK,
no network, no key -- a scripted "real-shaped" brain stands in for Anthropic):

* ``resolve_llm`` -- the mock default builds nothing; the llm mode merges the
  world YAML's ``llm:`` block with CLI overrides, accepts only Anthropic, and
  refuses to start without ``ANTHROPIC_API_KEY``;
* the world YAML declares the model (``claude-haiku-4-5``) and cost ceiling,
  and ``PennWorld``/``meta()`` carry them to the stepper and the viewer;
* with a real brain wired: every agent decides through it, real conversations
  fire between co-located settled agents exactly once per cooldown window, the
  scripted meeting injector stands down, an API outage degrades to
  idle-and-retry (never a crash), and the cost ceiling ends the day.

Run from ``generative-agents``::

    uv run pytest tests/test_penn_live_llm.py -v
"""

import io
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest

from backend.llm_monitor import LlmCallMonitor

# The Penn sim modules live in the Godot tree and are run as scripts (no
# package); import them off the sim directory, like test_penn_live.py.
_SIM_DIR = Path(__file__).resolve().parents[2] / "godot-generative-agents" / "sim"
sys.path.insert(0, str(_SIM_DIR))

import serve_penn  # noqa: E402
from penn_world import build_penn_world  # noqa: E402
from serve_penn import DEFAULT_LLM_MODEL, PennStepper, resolve_llm  # noqa: E402
from text_adventure_games.memory import MemoryKind  # noqa: E402
from text_adventure_games.usage import UsageLedger, record_call  # noqa: E402

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
        if tool["name"] == "speak":
            result = {"utterance": "Want to compare notes on campus?", "done": True}
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


def _llm_stepper(monkeypatch, max_cost=5.0, fail=False, monitor=None):
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
    return PennStepper(num_steps=50, world=build_penn_world(), monitor=monitor, llm=llm)


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
    monitor = LlmCallMonitor(stream=io.StringIO(), color=False)
    stepper = _llm_stepper(monkeypatch, monitor=monitor)
    assert stepper.drain_events() == []  # nothing before the first tick
    assert stepper.tick() is not None
    events = stepper.drain_events()
    assert events  # the t0 decides were monitored
    for ev in events:
        assert ev["kind"] == "llm_call"
        assert ev["model"] == "claude-haiku-4-5"
        assert ev["role"] in {"decide", "converse", "reflect"}
        assert {"call_no", "cum_cost_usd", "time", "actor", "cost_usd"} <= set(ev)
    assert stepper.drain_events() == []  # drained means drained


def test_drain_events_is_empty_without_a_monitor(monkeypatch):
    # --no-monitor: nothing is kept, so nothing rides the feed.
    stepper = _llm_stepper(monkeypatch)
    assert stepper.tick() is not None
    assert stepper.drain_events() == []
