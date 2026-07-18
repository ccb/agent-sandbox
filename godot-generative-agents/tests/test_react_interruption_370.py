"""React-or-continue: perception-driven interruption (issue #370).

A mid-activity agent that newly comes within mutual sight of another resident
remembers the encounter and -- behind a rule tier plus one bounded `react`
LLM call -- may pause its walk to greet (a #371 multi-tick conversation) or
replan. Default off; the mock brain never consults, so the bake stays
byte-identical.

Fully offline (fake brains). Run from the repo root::

    PYTHONPATH=.:godot-generative-agents uv run --no-sync pytest \\
        godot-generative-agents/tests/test_react_interruption_370.py -v
"""

import pytest

from backend.sim_config import CognitionConfig


def test_cognition_config_react_defaults():
    cog = CognitionConfig()
    assert cog.react_enabled is False
    assert cog.react_cooldown_steps == 90
    assert cog.react_hour_cap == 4


def test_react_knobs_load_from_dict():
    from backend.sim_config import SimulationConfig

    config = SimulationConfig.from_dict(
        {"cognition": {"react_enabled": True, "react_hour_cap": 2}}
    )
    assert config.cognition.react_enabled is True
    assert config.cognition.react_hour_cap == 2
    assert config.cognition.react_cooldown_steps == 90


def test_encounter_template_pins_exact_output():
    from backend.prompt_templates import render

    text = render(
        "encounter", partner="Ayesha Khan", doing="walking to Van Pelt Library"
    )
    assert text == "I noticed Ayesha Khan nearby while walking to Van Pelt Library."


def test_react_template_renders_all_blocks():
    from backend.prompt_templates import render

    text = render(
        "react",
        partner="Ayesha Khan",
        doing="walking to Van Pelt Library",
        time="Monday 09:30 AM",
        memories=["Ayesha Khan is my study partner."],
    )
    # Substring pins (the template has optional blocks, so exact-match would be
    # brittle across Jinja whitespace): every semantic piece must appear.
    assert "It is Monday 09:30 AM." in text
    assert "While walking to Van Pelt Library, you notice Ayesha Khan nearby." in text
    assert "- Ayesha Khan is my study partner." in text
    assert '"continue"' in text and '"greet"' in text and '"replan"' in text


def test_react_template_without_time_or_memories():
    from backend.prompt_templates import render

    text = render(
        "react", partner="Ayesha Khan", doing="reading", time=None, memories=[]
    )
    assert "It is" not in text
    assert "What you remember" not in text
    assert "While reading, you notice Ayesha Khan nearby." in text


from backend.build_world import build_world  # noqa: E402
from backend.cognition import (  # noqa: E402
    REACTED,
    attach_agents,
    maybe_converse,
    maybe_react,
)

_LOCATIONS = [
    {"name": "Plaza", "description": "the plaza", "address": None, "hub": True},
    {"name": "Cafe", "description": "a cafe", "address": "T:Cafe:counter"},
    {"name": "Library", "description": "a library", "address": "T:Library:desk"},
]


def _persona(name, dest="Cafe"):
    return {
        "name": name,
        "home": "Plaza",
        "persona": f"I am {name}.",
        "emoji": "\U0001f9d1",
        "start_tile": [0, 0],
        "destination": dest,
        "activity": "reading",
        "schedule": [{"place": dest, "activity": "reading", "emoji": None, "steps": 5}],
        "vision_r": 3,
    }


class _ReactBrain:
    """Answers the `react` tool with a scripted choice, speaks scripted dialogue
    lines (the engine's converse path forces the speak tool), and is inert on
    conversation_outcome. Snapshots context at call time so the stamped role is
    observable after the shared dict mutates."""

    def __init__(self, choice="continue", lines=()):
        self.choice = choice
        self._lines = list(lines)
        self.context: dict = {}
        self.react_calls: list[dict] = []

    def call_tool(self, messages, tool, max_tokens=256, temperature=0.0):
        if tool["name"] == "react":
            self.react_calls.append(
                {"context": dict(self.context), "messages": messages}
            )
            return {"choice": self.choice, "detail": "meet up later"}
        if tool["name"] == "conversation_outcome":
            return {"plans_changed": False}
        if self._lines:
            return {"utterance": self._lines.pop(0), "done": not self._lines}
        return {}


def _pair(brain, tiles=((0, 0), (2, 0)), paths=([(1, 0)], [(3, 0)])):
    """Two agents mid-walk at the given tiles. brain=None -> pure mock."""
    personas = [_persona("Maria Lopez"), _persona("Ayesha Khan", dest="Library")]
    game, chars = build_world(None, personas, _LOCATIONS)
    attach_agents(chars, personas, llm_client=brain)
    order = ["Maria Lopez", "Ayesha Khan"]
    state = {}
    for name, tile, path in zip(order, tiles, paths):
        state[name] = {
            "tile": tuple(tile),
            "path": list(path),
            "performing": False,
            "conversing": False,
            "chat": None,
        }
    frame = {n: {} for n in order}
    return game, chars, state, frame, order


def test_encounter_memory_written_for_mid_activity_members():
    brain = _ReactBrain(choice="continue")
    game, chars, state, frame, order = _pair(brain)
    maybe_react(chars, state, 0, {}, order, react_state={}, active={})
    for name, other in (("Maria Lopez", "Ayesha Khan"), ("Ayesha Khan", "Maria Lopez")):
        texts = [r.text for r in chars[name].agent.memory.records]
        assert any(f"I noticed {other} nearby" in t for t in texts)


def test_encounter_memory_deduped_within_react_cooldown_window():
    # A pair pacing in and out of mutual range writes ONE encounter record per
    # react-cooldown window, not one per re-entry -- repeated identical records
    # are what buries a distinctive memory at retrieval (PR #650 review).
    game, chars, state, frame, order = _pair(None)
    react_state: dict = {}
    kw = dict(react_state=react_state, active={}, react_cooldown_steps=100)
    maybe_react(chars, state, 0, {}, order, **kw)
    state["Ayesha Khan"]["tile"] = (50, 50)
    maybe_react(chars, state, 1, {}, order, **kw)
    state["Ayesha Khan"]["tile"] = (2, 0)
    maybe_react(chars, state, 2, {}, order, **kw)  # re-edge inside the window
    texts = [r.text for r in chars["Maria Lopez"].agent.memory.records]
    assert sum("I noticed Ayesha Khan nearby" in t for t in texts) == 1
    state["Ayesha Khan"]["tile"] = (50, 50)
    maybe_react(chars, state, 150, {}, order, **kw)
    state["Ayesha Khan"]["tile"] = (2, 0)
    maybe_react(chars, state, 151, {}, order, **kw)  # window elapsed: news again
    texts = [r.text for r in chars["Maria Lopez"].agent.memory.records]
    assert sum("I noticed Ayesha Khan nearby" in t for t in texts) == 2


def test_idle_agents_get_no_encounter_memory_and_no_consult():
    brain = _ReactBrain(choice="greet")
    game, chars, state, frame, order = _pair(brain, paths=([], []))
    # Neither walking nor performing: idle agents perceive at their own
    # decision point; and with no walking member there is no reactor.
    baseline = {n: len(chars[n].agent.memory.records) for n in order}
    consults = maybe_react(chars, state, 0, {}, order, react_state={}, active={})
    assert consults == 0
    assert brain.react_calls == []
    for n in order:
        assert len(chars[n].agent.memory.records) == baseline[n]


def test_edge_triggered_consult_once_until_pair_leaves_range():
    brain = _ReactBrain(choice="continue")
    game, chars, state, frame, order = _pair(brain)
    react_state: dict = {}
    maybe_react(
        chars,
        state,
        0,
        {},
        order,
        react_state=react_state,
        active={},
        react_cooldown_steps=0,
    )
    assert len(brain.react_calls) == 1
    # Still in range next tick: no re-consult (edge-triggered, not level).
    maybe_react(
        chars,
        state,
        1,
        {},
        order,
        react_state=react_state,
        active={},
        react_cooldown_steps=0,
    )
    assert len(brain.react_calls) == 1
    # Walk apart, then back into range: a fresh edge, a fresh consult.
    state["Ayesha Khan"]["tile"] = (50, 50)
    maybe_react(
        chars,
        state,
        2,
        {},
        order,
        react_state=react_state,
        active={},
        react_cooldown_steps=0,
    )
    state["Ayesha Khan"]["tile"] = (2, 0)
    maybe_react(
        chars,
        state,
        3,
        {},
        order,
        react_state=react_state,
        active={},
        react_cooldown_steps=0,
    )
    assert len(brain.react_calls) == 2


def test_greet_starts_pinned_conversation_and_first_line_fires_via_converse():
    brain = _ReactBrain(choice="greet", lines=["Oh hey!", "Hi, in a rush!"])
    game, chars, state, frame, order = _pair(brain)
    react_state: dict = {}
    active: dict = {}
    cooldowns: dict = {}
    consults = maybe_react(
        chars, state, 0, cooldowns, order, react_state=react_state, active=active
    )
    assert consults == 1
    assert len(active) == 1
    assert state["Maria Lopez"]["conversing"] is True
    assert state["Ayesha Khan"]["conversing"] is True
    # step() calls maybe_converse right after; its advance phase speaks the
    # greeting the same tick.
    maybe_converse(game, chars, state, frame, 0, cooldowns, order, active=active)
    assert frame["Maria Lopez"]["chat"] == [["Maria Lopez", "Oh hey!"]]
    # Both walks are paused but preserved -- resume happens in step() (Task 4).
    assert state["Maria Lopez"]["path"] == [(1, 0)]
    # The consult was billed under role "react".
    assert brain.react_calls[0]["context"]["role"] == "react"


def test_replan_choice_fires_reacted_revision_trigger():
    brain = _ReactBrain(choice="replan")
    game, chars, state, frame, order = _pair(brain)

    class _RecordingPlanner:
        def __init__(self):
            self.triggers = []

        def revise(self, plan, trigger, memory, clock=None):
            self.triggers.append(trigger)
            return plan  # unchanged -> no schedule commit needed

    recorder = _RecordingPlanner()
    chars["Maria Lopez"].agent.planner = recorder
    maybe_react(chars, state, 0, {}, order, react_state={}, active={})
    assert len(recorder.triggers) == 1
    assert recorder.triggers[0].reason == REACTED
    assert recorder.triggers[0].detail == "meet up later"
    assert state["Maria Lopez"]["conversing"] is False  # replan does not pin


def test_rule_tier_cooldowns_and_hour_cap():
    brain = _ReactBrain(choice="continue")
    game, chars, state, frame, order = _pair(brain)
    react_state: dict = {}
    # Per-agent react cooldown: second edge within the window is silent.
    maybe_react(
        chars,
        state,
        0,
        {},
        order,
        react_state=react_state,
        active={},
        react_cooldown_steps=100,
    )
    state["Ayesha Khan"]["tile"] = (50, 50)
    maybe_react(
        chars,
        state,
        1,
        {},
        order,
        react_state=react_state,
        active={},
        react_cooldown_steps=100,
    )
    state["Ayesha Khan"]["tile"] = (2, 0)
    maybe_react(
        chars,
        state,
        2,
        {},
        order,
        react_state=react_state,
        active={},
        react_cooldown_steps=100,
    )
    assert len(brain.react_calls) == 1
    # Hourly cap: with cooldown off, the cap (default window 360 steps with no
    # clock) stops consult N+1.
    react_state2: dict = {}
    calls_before = len(brain.react_calls)
    for i in range(6):
        state["Ayesha Khan"]["tile"] = (50, 50)
        maybe_react(
            chars,
            state,
            10 + 2 * i,
            {},
            order,
            react_state=react_state2,
            active={},
            react_cooldown_steps=0,
            react_hour_cap=2,
        )
        state["Ayesha Khan"]["tile"] = (2, 0)
        maybe_react(
            chars,
            state,
            11 + 2 * i,
            {},
            order,
            react_state=react_state2,
            active={},
            react_cooldown_steps=0,
            react_hour_cap=2,
        )
    assert len(brain.react_calls) - calls_before == 2


def test_react_consult_threads_a_real_sim_clock():
    # serve_penn always threads a SimClock, so exercise that branch (PR #650
    # review): the prompt carries the formatted time, and the hourly-cap
    # window follows the clock's step rate instead of the 360-step fallback.
    import datetime as dt

    from backend.sim_clock import SimClock

    brain = _ReactBrain(choice="continue")
    game, chars, state, frame, order = _pair(brain)
    clock = SimClock(start_dt=dt.datetime(2026, 7, 13, 9, 0), sec_per_step=60)
    react_state: dict = {}
    kw = dict(
        react_state=react_state,
        active={},
        react_cooldown_steps=0,
        react_hour_cap=1,
        clock=clock,
    )
    maybe_react(chars, state, 0, {}, order, **kw)
    assert len(brain.react_calls) == 1
    prompt = brain.react_calls[0]["messages"][1]["content"]
    assert "It is Monday 09:00 AM." in prompt
    # Cap window = clock.steps_for_seconds(3600) = 60 steps at 60 s/step.
    # A re-edge inside it is capped (hour_cap=1)...
    state["Ayesha Khan"]["tile"] = (50, 50)
    maybe_react(chars, state, 30, {}, order, **kw)
    state["Ayesha Khan"]["tile"] = (2, 0)
    maybe_react(chars, state, 31, {}, order, **kw)
    assert len(brain.react_calls) == 1
    # ...but one past it consults again -- under the clockless 360-step
    # fallback, step 71 would still be inside the window and blocked.
    state["Ayesha Khan"]["tile"] = (50, 50)
    maybe_react(chars, state, 70, {}, order, **kw)
    state["Ayesha Khan"]["tile"] = (2, 0)
    maybe_react(chars, state, 71, {}, order, **kw)
    assert len(brain.react_calls) == 2


def test_pair_conversation_cooldown_blocks_consult():
    brain = _ReactBrain(choice="greet")
    game, chars, state, frame, order = _pair(brain)
    cooldowns = {frozenset(("Maria Lopez", "Ayesha Khan")): 0}
    consults = maybe_react(
        chars,
        state,
        5,
        cooldowns,
        order,
        react_state={},
        active={},
        cooldown_steps=90,
    )
    assert consults == 0 and brain.react_calls == []


def test_busy_or_conversing_pairs_are_skipped():
    brain = _ReactBrain(choice="greet")
    game, chars, state, frame, order = _pair(brain)
    state["Ayesha Khan"]["conversing"] = True
    consults = maybe_react(chars, state, 0, {}, order, react_state={}, active={})
    assert consults == 0 and brain.react_calls == []


def test_mock_brain_never_consults_but_still_remembers():
    # No llm_client -> the brain IS the schedule client (identity gate).
    game, chars, state, frame, order = _pair(None)
    react_state: dict = {}
    consults = maybe_react(
        chars, state, 0, {}, order, react_state=react_state, active={}
    )
    assert consults == 0
    assert react_state.get("last_react", {}) == {}
    texts = [r.text for r in chars["Maria Lopez"].agent.memory.records]
    assert any("I noticed Ayesha Khan nearby" in t for t in texts)


def test_malformed_react_reply_still_consumes_cooldown_and_cap():
    # A real brain that answers the react tool badly must still be billed
    # against the react cooldown/cap -- otherwise every new edge makes an
    # uncapped paid call (final-review Important #1).
    brain = _ReactBrain(choice="shrug")  # not in the enum -> unusable reply
    game, chars, state, frame, order = _pair(brain)
    react_state: dict = {}
    consults = maybe_react(
        chars,
        state,
        0,
        {},
        order,
        react_state=react_state,
        active={},
        react_cooldown_steps=100,
    )
    assert len(brain.react_calls) == 1
    assert consults == 1  # a made call is a consult, usable or not
    assert react_state["last_react"]["Maria Lopez"] == 0  # cooldown engaged
    # Leave and re-enter range within the cooldown window: no second call.
    state["Ayesha Khan"]["tile"] = (50, 50)
    maybe_react(
        chars,
        state,
        1,
        {},
        order,
        react_state=react_state,
        active={},
        react_cooldown_steps=100,
    )
    state["Ayesha Khan"]["tile"] = (2, 0)
    maybe_react(
        chars,
        state,
        2,
        {},
        order,
        react_state=react_state,
        active={},
        react_cooldown_steps=100,
    )
    assert len(brain.react_calls) == 1


from backend.run_simulation import step  # noqa: E402


def _full_state(tile, path, conversing=False):
    """A state entry with every key step() reads."""
    return {
        "tile": tuple(tile),
        "path": list(path),
        "pron": "\U0001f9d1",
        "desc": "walking",
        "performing": False,
        "perform_until": None,
        "reasoning": "(r)",
        "memories": [],
        "chat": None,
        "stop_since": 0,
        "on_plan": True,
        "conversing": conversing,
    }


def test_step_pauses_pinned_walker_and_resumes_after():
    # Both agents mid-walk (non-empty path -> never at a decision point, so
    # world_map=None is safe: step() only touches it on a travel decide).
    game, chars, _, _, order = _pair(None)
    emoji = {n: "\U0001f9d1" for n in order}
    state = {
        "Maria Lopez": _full_state((0, 0), [(1, 0), (2, 0)], conversing=True),
        "Ayesha Khan": _full_state((9, 9), [(8, 9), (7, 9)]),
    }
    frame, _ = step(game, chars, state, 0, order=order, world_map=None, emoji=emoji)
    # Pinned mid-walk: tile and path untouched.
    assert state["Maria Lopez"]["tile"] == (0, 0)
    assert state["Maria Lopez"]["path"] == [(1, 0), (2, 0)]
    # Unpinned walker advanced normally.
    assert state["Ayesha Khan"]["tile"] == (8, 9)
    # Conversation over: the preserved walk resumes.
    state["Maria Lopez"]["conversing"] = False
    step(game, chars, state, 1, order=order, world_map=None, emoji=emoji)
    assert state["Maria Lopez"]["tile"] == (1, 0)
    assert state["Maria Lopez"]["path"] == [(2, 0)]


def test_step_rejects_react_enabled_without_persistent_react_state():
    from backend.sim_config import CognitionConfig

    game, chars, _, _, order = _pair(None)
    emoji = {n: "\U0001f9d1" for n in order}
    state = {
        "Maria Lopez": _full_state((0, 0), [(1, 0)]),
        "Ayesha Khan": _full_state((9, 9), [(8, 9)]),
    }
    with pytest.raises(ValueError, match="react_state"):
        step(
            game,
            chars,
            state,
            0,
            order=order,
            world_map=None,
            emoji=emoji,
            conversation_enabled=True,
            active_conversations={},
            cog=CognitionConfig(react_enabled=True),
            react_state=None,
        )


def test_step_runs_react_before_converse_so_greeting_lands_same_tick():
    from backend.sim_config import CognitionConfig

    brain = _ReactBrain(choice="greet", lines=["Oh hey!", "Hi!"])
    game, chars, _, _, order = _pair(brain)
    emoji = {n: "\U0001f9d1" for n in order}
    # Walking toward each other, already within mutual sight (vision_r=3).
    state = {
        "Maria Lopez": _full_state((0, 0), [(1, 0), (2, 0)]),
        "Ayesha Khan": _full_state((2, 0), [(1, 0)]),
    }
    react_state: dict = {}
    active: dict = {}
    frame, _ = step(
        game,
        chars,
        state,
        0,
        order=order,
        world_map=None,
        emoji=emoji,
        conversation_enabled=True,
        active_conversations=active,
        cog=CognitionConfig(react_enabled=True),
        react_state=react_state,
    )
    # The crossing fired within vision: pinned + first line this same tick.
    assert state["Maria Lopez"]["conversing"] is True
    assert state["Ayesha Khan"]["conversing"] is True
    assert frame["Maria Lopez"]["chat"] == [["Maria Lopez", "Oh hey!"]]
    assert len(active) == 1
    # Walks preserved for the resume (movement ran before the react pass this
    # tick, so each already advanced one tile).
    assert state["Maria Lopez"]["path"] == [(2, 0)]


def test_default_cog_equals_explicit_default():
    # An explicit CognitionConfig() behaves identically to the implicit
    # default (react off). The branch's real byte-identity guarantee against
    # the baked replay is pinned by the external determinism suites.
    game, chars, _, _, order = _pair(None)
    emoji = {n: "\U0001f9d1" for n in order}

    def _states():
        return {
            "Maria Lopez": _full_state((0, 0), [(1, 0), (2, 0)]),
            "Ayesha Khan": _full_state((2, 0), [(1, 0)]),
        }

    # Default cog (react off) vs. explicit CognitionConfig(): same frames.
    s1, s2 = _states(), _states()
    f1, _ = step(game, chars, s1, 0, order=order, world_map=None, emoji=emoji)
    from backend.sim_config import CognitionConfig

    f2, _ = step(
        game,
        chars,
        s2,
        1,
        order=order,
        world_map=None,
        emoji=emoji,
        cog=CognitionConfig(),
    )
    assert f1 == f2
    assert {k: {x: v[x] for x in ("tile", "path")} for k, v in s1.items()} == {
        k: {x: v[x] for x in ("tile", "path")} for k, v in s2.items()
    }
