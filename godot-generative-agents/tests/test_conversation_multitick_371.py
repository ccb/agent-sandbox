"""Multi-tick conversation pacing (issue #371) and the playback hold (#673).

A conversation is a stateful activity spread across ticks: roughly one line per
tick, participants pinned "conversing" (they neither walk nor re-decide), each
line published on the tick it was said, and the #582 outcome pass firing only
when the conversation ends. After the last line the pair stays pinned for the
viewer's playback window -- ``len(lines) * line_playback_steps`` further steps
(#673) -- so the map shows them standing together while the exchange plays back,
instead of a conversation link stretching between two walkers. The deterministic
mock never produces an utterance, so every conversation dies on its first empty
line, holds nobody, and the bake is byte-identical.

Fully offline (fake brains). Run from the repo root::

    PYTHONPATH=.:godot-generative-agents uv run --no-sync pytest \\
        godot-generative-agents/tests/test_conversation_multitick_371.py -v
"""

import sys
from pathlib import Path

import pytest

_SIM_DIR = (
    Path(__file__).resolve().parents[2] / "godot-generative-agents" / "backend" / "penn"
)
sys.path.insert(0, str(_SIM_DIR))

from backend import cognition  # noqa: E402
from backend.build_world import build_world  # noqa: E402
from backend.cognition import (  # noqa: E402
    ActiveConversation,
    attach_agents,
    maybe_converse,
)
from text_adventure_games import conversation as convo  # noqa: E402

_LOCATIONS = [
    {"name": "Plaza", "description": "the plaza", "address": None, "hub": True},
    {"name": "Cafe", "description": "a cafe", "address": "T:Cafe:counter"},
]


def _persona(name):
    return {
        "name": name,
        "home": "Plaza",
        "persona": f"I am {name}.",
        "emoji": "\U0001f9d1",
        "start_tile": [0, 0],
        "destination": "Cafe",
        "activity": "reading",
        "schedule": [
            {"place": "Cafe", "activity": "reading", "emoji": None, "steps": 5}
        ],
    }


class _ScriptedConvoBrain:
    """A brain that speaks a fixed list of lines (one per converse() ask) then
    goes silent, and answers conversation_outcome inertly. Shared by both agents,
    like the classic single-brain live path -- the speaker alternates each tick,
    so the shared list drains across both."""

    def __init__(self, lines):
        self._lines = list(lines)
        self.context: dict = {}
        self.outcome_calls = 0

    def call_tool(self, messages, tool, max_tokens=256, temperature=0.0):
        if tool["name"] == "conversation_outcome":
            self.outcome_calls += 1
            return {"plans_changed": False}
        # The engine's dialogue seam (Agent.converse) forces the "speak" tool.
        if self._lines:
            return {"utterance": self._lines.pop(0), "done": not self._lines}
        return {}  # nothing left to say -> ends the conversation


def _colocated_pair(brain):
    personas = [_persona("Maria Lopez"), _persona("Ayesha Khan")]
    game, chars = build_world(None, personas, _LOCATIONS)
    attach_agents(chars, personas, llm_client=brain)
    plaza = game.locations["Plaza"]
    order = ["Maria Lopez", "Ayesha Khan"]
    for name in order:
        ch = chars[name]
        if ch.location is not None:
            ch.location.remove_character(ch)
        plaza.add_character(ch)
    state = {n: {"performing": True, "path": None, "chat": None} for n in order}
    frame = {n: {} for n in order}
    return game, chars, state, frame, order


def test_conversation_spans_multiple_ticks_one_line_each():
    # Three lines -> three ticks with a line; the end tick completes the
    # conversation (outcome + cooldown) but HOLDS the pair for the playback
    # window (#673): 3 lines x 2 steps/line -> released at tick 2 + 6 = 8.
    brain = _ScriptedConvoBrain(["Hi!", "How are you?", "Good, bye!"])
    game, chars, state, frame, order = _colocated_pair(brain)
    active: dict = {}
    cooldowns: dict = {}

    # Tick 0: conversation starts, first line said, still going.
    completed = maybe_converse(
        game,
        chars,
        state,
        frame,
        0,
        cooldowns,
        order,
        active=active,
        line_playback_steps=2,
    )
    assert completed == 0
    assert len(active) == 1
    assert state["Maria Lopez"]["conversing"] is True
    assert state["Ayesha Khan"]["conversing"] is True
    assert frame["Maria Lopez"]["chat"] == [["Maria Lopez", "Hi!"]]
    assert brain.outcome_calls == 0  # no outcome mid-conversation

    # Tick 1: second line, transcript grows by one.
    completed = maybe_converse(
        game,
        chars,
        state,
        frame,
        1,
        cooldowns,
        order,
        active=active,
        line_playback_steps=2,
    )
    assert completed == 0
    assert frame["Maria Lopez"]["chat"] == [
        ["Maria Lopez", "Hi!"],
        ["Ayesha Khan", "How are you?"],
    ]

    # Tick 2: third line carries done=True -> the conversation COMPLETES this
    # tick (counted, outcome pass, cooldown) but the pair stays pinned.
    completed = maybe_converse(
        game,
        chars,
        state,
        frame,
        2,
        cooldowns,
        order,
        active=active,
        line_playback_steps=2,
    )
    assert completed == 1
    assert brain.outcome_calls == 2  # outcome fires once per participant, on end
    assert cooldowns  # cooldown recorded on end
    # Full transcript on both cards.
    assert len(frame["Maria Lopez"]["chat"]) == 3
    # The playback hold (#673): the record stays active, both stay conversing.
    assert len(active) == 1
    assert state["Maria Lopez"]["conversing"] is True
    assert state["Ayesha Khan"]["conversing"] is True

    # Ticks 3..7: held -- no new lines, no new completions, still pinned.
    for step in range(3, 8):
        completed = maybe_converse(
            game,
            chars,
            state,
            frame,
            step,
            cooldowns,
            order,
            active=active,
            line_playback_steps=2,
        )
        assert completed == 0
        assert len(frame["Maria Lopez"]["chat"]) == 3
        assert state["Maria Lopez"]["conversing"] is True, f"released early at {step}"
        assert state["Ayesha Khan"]["conversing"] is True

    # Tick 8: the window (3 lines x 2 steps) has elapsed -> released.
    completed = maybe_converse(
        game,
        chars,
        state,
        frame,
        8,
        cooldowns,
        order,
        active=active,
        line_playback_steps=2,
    )
    assert completed == 0
    assert active == {}
    assert state["Maria Lopez"]["conversing"] is False
    assert state["Ayesha Khan"]["conversing"] is False
    assert brain.outcome_calls == 2  # release runs no second outcome pass


def test_max_exchanges_caps_across_ticks():
    # Ramble forever; the cap ends the conversation after max_exchanges lines.
    # Lines land ticks 0-3, so the 1-step/line playback hold (#673) elapses at
    # tick 3 + 4 = 7 -- comfortably inside the 10-tick drive.
    brain = _ScriptedConvoBrain([f"line{i}" for i in range(50)])
    game, chars, state, frame, order = _colocated_pair(brain)
    active: dict = {}
    cooldowns: dict = {}
    total = 0
    for step in range(10):
        total += maybe_converse(
            game,
            chars,
            state,
            frame,
            step,
            cooldowns,
            order,
            active=active,
            max_exchanges=4,
            line_playback_steps=1,
        )
    assert total == 1  # exactly one conversation, capped and completed
    assert active == {}
    assert len(frame["Maria Lopez"]["chat"]) == 4


def _colocated_trio(brain, names):
    """Three co-located residents, all sharing one brain -- attach_agents wires
    the same ``llm_client`` onto every persona, exactly as ``_colocated_pair``
    does for two, so a single scripted brain must answer for whichever of the
    three is asked."""
    personas = [_persona(n) for n in names]
    game, chars = build_world(None, personas, _LOCATIONS)
    attach_agents(chars, personas, llm_client=brain)
    plaza = game.locations["Plaza"]
    for name in names:
        ch = chars[name]
        if ch.location is not None:
            ch.location.remove_character(ch)
        plaza.add_character(ch)
    state = {n: {"performing": True, "path": None, "chat": None} for n in names}
    frame = {n: {} for n in names}
    return game, chars, state, frame


class _TrioConvoBrain:
    """Shared by all three agents. Every "speak" ask gets a done-flagged line,
    so any conversation that gets a turn this tick completes on its first line
    -- which is what makes a same-tick second conversation observable. Outcome
    calls are tallied by actor name (stamped onto ``context`` right before each
    call, like the real ``apply_conversation_outcome``/``_stamp_convo_ctx``
    seams): #187 says a participant holds at most one conversation per step, so
    a name appearing twice here is exactly that violation."""

    def __init__(self):
        self.context: dict = {}
        self.outcome_by_actor: dict[str, int] = {}
        self._line_count = 0

    def call_tool(self, messages, tool, max_tokens=256, temperature=0.0):
        actor = self.context.get("actor")
        if tool["name"] == "conversation_outcome":
            self.outcome_by_actor[actor] = self.outcome_by_actor.get(actor, 0) + 1
            return {"plans_changed": False}
        self._line_count += 1
        return {"utterance": f"line{self._line_count}", "done": True}


def test_finished_participant_not_repaired_same_tick():
    """#187: a participant whose in-progress conversation COMPLETES in phase 1
    must not be free to start a second conversation with a third party in the
    SAME tick. Bug: phase 2's ``busy`` set was computed straight from ``active``
    -- AFTER phase 1's ``del active[key]`` for anything that just finished -- so
    a just-freed participant looked exactly like someone who was never talking
    this step, and could immediately start (and finish) a second conversation.
    """
    a_name, b_name, c_name = "Maria Lopez", "Ayesha Khan", "Diego Fields"
    brain = _TrioConvoBrain()
    game, chars, state, frame = _colocated_trio(brain, [a_name, b_name, c_name])
    order = [a_name, b_name, c_name]

    # Seed an in-progress A-B conversation: one line already said, B's turn
    # next -- and the brain always answers with a done-flagged line, so A-B
    # completes this tick (phase 1).
    ac = ActiveConversation(
        a=a_name,
        b=b_name,
        convo=convo.Conversation(participants=(a_name, b_name), lines=[(a_name, "Hi")]),
        next_speaker=b_name,
        started=0,
    )
    active = {frozenset((a_name, b_name)): ac}
    state[a_name]["conversing"] = True
    state[b_name]["conversing"] = True
    # Mirror the earlier tick's publish, so a same-tick clobber is visible.
    state[a_name]["chat"] = state[b_name]["chat"] = [[a_name, "Hi"]]
    cooldowns: dict = {}

    completed = maybe_converse(
        game, chars, state, frame, 5, cooldowns, order, active=active
    )

    # Only A-B completed -- C (settled, ready to talk) never got a partner:
    # A and B are still "busy" this step even though phase 1 just freed them.
    assert completed == 1
    assert state[c_name]["chat"] is None
    # The just-finished A-B transcript survives untouched -- not overwritten by
    # a second, same-tick conversation with C.
    assert state[a_name]["chat"] == [[a_name, "Hi"], [b_name, "line1"]]
    assert state[b_name]["chat"] == state[a_name]["chat"]
    # The #582 outcome pass fires once per participant per step, never twice.
    assert brain.outcome_by_actor.get(a_name) == 1
    assert brain.outcome_by_actor.get(b_name) == 1
    assert c_name not in brain.outcome_by_actor


def test_playback_hold_keeps_pair_busy_and_undraftable():
    """#673: for the whole playback window a just-finished pair is still "busy"
    -- neither participant may be drafted into a new conversation -- and the
    release sweep runs no second outcome/cooldown pass. Diego (settled, willing)
    has no free partner until the window elapses."""
    a_name, b_name, c_name = "Maria Lopez", "Ayesha Khan", "Diego Fields"
    brain = _ScriptedConvoBrain(["Hi!", "How are you?", "Good, bye!"])
    game, chars, state, frame = _colocated_trio(brain, [a_name, b_name, c_name])
    order = [a_name, b_name, c_name]
    active: dict = {}
    cooldowns: dict = {}

    # Ticks 0-2: A-B talk (first-come matching leaves C without a partner);
    # the third line carries done=True, ending the exchange at tick 2.
    completed = 0
    for step in range(3):
        completed += maybe_converse(
            game,
            chars,
            state,
            frame,
            step,
            cooldowns,
            order,
            active=active,
            line_playback_steps=2,
        )
    assert completed == 1
    assert brain.outcome_calls == 2
    cooldowns_at_end = dict(cooldowns)

    # Hold window: 3 lines x 2 steps/line -> ticks 3..7 held, released at 8.
    for step in range(3, 8):
        maybe_converse(
            game,
            chars,
            state,
            frame,
            step,
            cooldowns,
            order,
            active=active,
            line_playback_steps=2,
        )
        assert state[a_name]["conversing"] is True, f"released early at {step}"
        assert state[b_name]["conversing"] is True
        # C never got a partner: both A and B are still busy while held.
        assert state[c_name]["chat"] is None

    maybe_converse(
        game,
        chars,
        state,
        frame,
        8,
        cooldowns,
        order,
        active=active,
        line_playback_steps=2,
    )
    assert active == {}
    assert state[a_name]["conversing"] is False
    assert state[b_name]["conversing"] is False
    # The release is bookkeeping only: no second outcome pass, no new cooldown.
    assert brain.outcome_calls == 2
    assert cooldowns == cooldowns_at_end


def test_mock_brain_never_converses_and_stays_inert():
    personas = [_persona("Maria Lopez"), _persona("Ayesha Khan")]
    game, chars = build_world(None, personas, _LOCATIONS)
    attach_agents(chars, personas, llm_client=None)  # mock brain
    plaza = game.locations["Plaza"]
    order = ["Maria Lopez", "Ayesha Khan"]
    for name in order:
        ch = chars[name]
        if ch.location is not None:
            ch.location.remove_character(ch)
        plaza.add_character(ch)
    state = {n: {"performing": True, "path": None, "chat": None} for n in order}
    frame = {n: {} for n in order}
    active: dict = {}

    completed = maybe_converse(game, chars, state, frame, 0, {}, order, active=active)

    assert completed == 0
    assert active == {}
    # chat stays None (never written) -> the frame is byte-identical to today.
    assert state["Maria Lopez"]["chat"] is None
    assert "chat" not in frame["Maria Lopez"]
    assert state["Maria Lopez"].get("conversing") in (None, False)


from backend.run_simulation import step  # noqa: E402
from backend.sim_config import CognitionConfig  # noqa: E402
from backend.world_map import WorldMap  # noqa: E402


def test_step_pins_conversing_agents_from_deciding_and_moving():
    """A conversing agent stays put and is not asked to decide: step() must
    read state["conversing"] and skip its schedule-advance/decision/movement."""
    brain = _ScriptedConvoBrain(["Hi!", "Hello!", "Bye!"])
    game, chars, state, frame_seed, order = _colocated_pair(brain)
    # Flesh out state to what step() reads (mirror simulate()'s per-agent dict).
    for name in order:
        st = state[name]
        st.update(
            {
                "tile": (0, 0),
                "path": [],
                "pron": "\U0001f9d1",
                "desc": "reading",
                "perform_until": None,  # stay put; not the thing under test
                "reasoning": "",
                "memories": [],
                "stop_since": 0,
                "on_plan": True,
            }
        )
    active: dict = {}
    wm = WorldMap.__new__(WorldMap)  # unused: conversing agents never path this test
    emoji = {n: "\U0001f9d1" for n in order}

    # Tick 0 starts the conversation (agents are settled+co-located).
    frame, _ = step(
        game,
        chars,
        state,
        0,
        order=order,
        world_map=wm,
        emoji=emoji,
        conversation_enabled=True,
        active_conversations=active,
    )
    assert active  # conversation is live
    assert state["Maria Lopez"]["conversing"] is True
    tile_before = state["Maria Lopez"]["tile"]

    # Tick 1: conversing agents must NOT move and must NOT be re-decided. If the
    # gate is missing, step() would treat them as "due" and call decide (the
    # scripted brain has no decide command -> it would error or move).
    frame, _ = step(
        game,
        chars,
        state,
        1,
        order=order,
        world_map=wm,
        emoji=emoji,
        conversation_enabled=True,
        active_conversations=active,
    )
    assert state["Maria Lopez"]["tile"] == tile_before  # stayed put
    assert len(frame["Maria Lopez"]["chat"]) == 2  # a second line was said


def test_step_perform_until_gate_holds_conversing_agent_pinned():
    """#371 Task 3: the OTHER conversing-pin guard -- on the perform_until-advance
    block (run_simulation.step, ~line 237) -- actually matters.

    The test above never reaches this block: it leaves ``perform_until`` at
    ``None`` forever, so the block's own ``perform_until is not None`` guard
    already skips it, and the ``and not st.get("conversing")`` conjunct is
    never exercised. Here the scheduled activity's timer ELAPSES *during* the
    conversation (the realistic #371 scenario: an agent settles into an
    activity, then starts chatting, and the activity's clock runs out mid-chat).
    Without the guard, the block would fire, call ``char.agent.schedule.advance()``,
    and flip ``performing`` to ``False`` mid-conversation -- un-pinning the agent.
    """
    brain = _ScriptedConvoBrain(["Hi!", "Hello!", "Bye!"])
    game, chars, state, frame_seed, order = _colocated_pair(brain)
    # The shared persona's schedule has a single stop, so schedule.advance() is
    # always a no-op (nothing to advance to) regardless of the guard -- not
    # useful for telling "gate held" apart from "gate missing". Append a second
    # stop so advance() can actually succeed, exactly like a real multi-stop day.
    for name in order:
        chars[name].agent.schedule.schedule.append(
            {"place": "Cafe", "activity": "eating", "emoji": None, "steps": 5}
        )
    for name in order:
        st = state[name]
        st.update(
            {
                "tile": (0, 0),
                "path": [],
                "pron": "\U0001f9d1",
                "desc": "reading",
                "perform_until": 100,  # far off; the conversation starts first
                "reasoning": "",
                "memories": [],
                "stop_since": 0,
                "on_plan": True,
            }
        )
    active: dict = {}
    wm = WorldMap.__new__(WorldMap)  # unused: conversing agents never path this test
    emoji = {n: "\U0001f9d1" for n in order}

    # Tick 0: settled + co-located -> a conversation starts.
    frame, _ = step(
        game,
        chars,
        state,
        0,
        order=order,
        world_map=wm,
        emoji=emoji,
        conversation_enabled=True,
        active_conversations=active,
    )
    assert active  # conversation is live
    assert state["Maria Lopez"]["conversing"] is True
    assert state["Ayesha Khan"]["conversing"] is True
    tile_before = state["Maria Lopez"]["tile"]
    chat_before = len(frame["Maria Lopez"]["chat"])

    # The activity's timer elapses mid-conversation: an already-elapsed
    # perform_until satisfies the block's ``step_idx >= perform_until`` this tick.
    state["Maria Lopez"]["perform_until"] = 1
    state["Ayesha Khan"]["perform_until"] = 1

    frame, _ = step(
        game,
        chars,
        state,
        1,
        order=order,
        world_map=wm,
        emoji=emoji,
        conversation_enabled=True,
        active_conversations=active,
    )

    # The gate held: the schedule was NOT advanced (performing stays True), the
    # agent didn't move, and the conversation carried on regardless.
    assert state["Maria Lopez"]["performing"] is True
    assert state["Maria Lopez"]["tile"] == tile_before
    assert len(frame["Maria Lopez"]["chat"]) == chat_before + 1


def test_step_holds_pair_through_playback_window_then_releases():
    """#673 at the step() level: after the last line, an elapsed activity timer
    must NOT un-pin the pair -- they stand together (no walk, no re-decide, no
    schedule advance) until the playback window elapses, then the sweep releases
    them. With 3 lines at 1 step/line, the exchange ends at tick 2 and the hold
    covers ticks 3-5."""
    brain = _ScriptedConvoBrain(["Hi!", "Hello!", "Bye!"])
    game, chars, state, _seed, order = _colocated_pair(brain)
    for name in order:
        state[name].update(
            {
                "tile": (0, 0),
                "path": [],
                "pron": "\U0001f9d1",
                "desc": "reading",
                "perform_until": 100,  # far off while the conversation runs
                "reasoning": "",
                "memories": [],
                "stop_since": 0,
                "on_plan": True,
            }
        )
    active: dict = {}
    wm = WorldMap.__new__(WorldMap)  # unused: held agents never path
    emoji = {n: "\U0001f9d1" for n in order}
    cog = CognitionConfig(conversation_line_playback_steps=1)

    # Ticks 0-2: the conversation runs and ends (done=True on the third line).
    for step_idx in range(3):
        frame, _ = step(
            game,
            chars,
            state,
            step_idx,
            order=order,
            world_map=wm,
            emoji=emoji,
            conversation_enabled=True,
            active_conversations=active,
            cog=cog,
        )
    assert len(frame["Maria Lopez"]["chat"]) == 3
    assert state["Maria Lopez"]["conversing"] is True  # held past the last line
    tile_before = state["Maria Lopez"]["tile"]

    # The scheduled activity's timer elapses mid-hold: without the hold the
    # pre-pass would advance the schedule and free the agents to walk.
    state["Maria Lopez"]["perform_until"] = 1
    state["Ayesha Khan"]["perform_until"] = 1

    # Ticks 3-4: held -- pinned in place, schedule untouched, transcript frozen.
    for step_idx in (3, 4):
        frame, _ = step(
            game,
            chars,
            state,
            step_idx,
            order=order,
            world_map=wm,
            emoji=emoji,
            conversation_enabled=True,
            active_conversations=active,
            cog=cog,
        )
        assert state["Maria Lopez"]["conversing"] is True, f"released at {step_idx}"
        assert state["Maria Lopez"]["performing"] is True
        assert state["Maria Lopez"]["tile"] == tile_before
        assert len(frame["Maria Lopez"]["chat"]) == 3

    # Tick 5: the window (3 lines x 1 step) elapses -> the sweep releases both.
    # The pre-pass ran before the sweep this tick, so they still didn't move;
    # from the next tick they resume their schedules normally.
    frame, _ = step(
        game,
        chars,
        state,
        5,
        order=order,
        world_map=wm,
        emoji=emoji,
        conversation_enabled=True,
        active_conversations=active,
        cog=cog,
    )
    assert active == {}
    assert state["Maria Lopez"]["conversing"] is False
    assert state["Ayesha Khan"]["conversing"] is False
    assert state["Maria Lopez"]["tile"] == tile_before


def test_playback_pacing_mirrors_viewer_constant():
    """The backend hold and the viewer's playback must count the same steps, or
    the link/bubbles outlive the pin again (#673). viewer.gd shows each line for
    DIALOGUE_LINE_STEPS (14.0) steps; penn_world.py mirrors it for the authored
    meeting injectors; cognition.py mirrors it for the hold. Pin all three."""
    assert cognition.CONVERSATION_LINE_PLAYBACK_STEPS == 14
    assert CognitionConfig().conversation_line_playback_steps == 14


def test_step_rejects_conversation_enabled_without_active_dict():
    """#371 contract: a multi-tick meeting only spans ticks if its state persists
    across them. Enabling conversation while letting active_conversations default
    to None would hand maybe_converse a throwaway dict every tick -- the meeting
    would restart, re-greet, and re-pin the pair, which then never resumes its
    schedule. step() refuses that combination up front, mirroring the existing
    decide_executor/decide_timeout contract guard."""
    brain = _ScriptedConvoBrain(["Hi!"])
    game, chars, state, _frame, order = _colocated_pair(brain)
    wm = WorldMap.__new__(WorldMap)  # never reached: the guard raises first
    emoji = {n: "\U0001f9d1" for n in order}
    with pytest.raises(ValueError, match="active_conversations"):
        step(
            game,
            chars,
            state,
            0,
            order=order,
            world_map=wm,
            emoji=emoji,
            conversation_enabled=True,  # active_conversations omitted -> None
        )


# --- the escalating pair cooldown (issue #803) -------------------------------

_PAIR = frozenset(("Maria Lopez", "Ayesha Khan"))


def _open_at(step_idx, cooldowns, *, brain=None):
    """Try to open a proximity conversation at *step_idx*. Returns the number of
    conversations that completed (the one-line brain finishes on its first line)."""
    brain = brain or _ScriptedConvoBrain(["Hi again!"])
    game, chars, state, frame, order = _colocated_pair(brain)
    return maybe_converse(
        game,
        chars,
        state,
        frame,
        step_idx,
        cooldowns,
        order,
        active={},
        cooldown_steps=10,
        line_playback_steps=1,
    )


def test_repeat_conversations_wait_an_escalated_cooldown():
    """#803: the Nth conversation between a pair waits N x cooldown_steps.

    A flat window set the *tempo* of repetition rather than bounding it: the
    reported run held four near-identical Omar/Tanaka meetings exactly 95 steps
    apart -- cooldown plus one open -- each greeting the other cold."""
    cooldowns = {_PAIR: (0, 2)}  # two conversations held, the last ending at step 0

    # The plain window (10) lapsed long ago, but the third conversation owes 2 x 10.
    assert _open_at(19, cooldowns) == 0
    assert cooldowns == {_PAIR: (0, 2)}  # blocked, so nothing is recorded

    assert _open_at(20, cooldowns) == 1
    # The count rides along, so their FOURTH conversation owes 3 x 10.
    assert cooldowns == {_PAIR: (20, 3)}


def test_a_pair_that_talked_once_waits_only_the_plain_window():
    """The #803 escalation must not deaden a sim that was socializing normally
    (a live run once logged zero conversations): after ONE conversation the next
    still opens the moment the plain window lapses.

    A bare int is also what every pre-#803 entry and test seed looks like, and it
    reads as exactly that -- one conversation, ended then."""
    cooldowns = {_PAIR: 0}

    assert _open_at(9, cooldowns) == 0
    assert _open_at(10, cooldowns) == 1
    assert cooldowns == {_PAIR: (10, 2)}
