"""Universal verbs (issue #614): `wait` offered with #581 pacing slots so a
chosen idle settles like `perform`, and agent-initiated `talk_to` that enters
the existing #582/#371 conversation loop -- including (#793) what a `talk_to`
request owes its initiator when maybe_converse cannot open it.

Fully offline. Run from the repo root::

    uv run pytest godot-generative-agents/tests/test_universal_verbs_614.py -v
"""

import sys
from pathlib import Path

_SIM_DIR = (
    Path(__file__).resolve().parents[2] / "godot-generative-agents" / "backend" / "penn"
)
sys.path.insert(0, str(_SIM_DIR))

from backend.actions import TalkTo, WaitPenn  # noqa: E402
from backend.build_world import build_world  # noqa: E402
from backend.cognition import (  # noqa: E402
    DEAD_TALK_SETTLE_STEPS,
    ActiveConversation,
    action_tools_for,
    attach_agents,
    maybe_converse,
    remember_outcome,
)
from backend.prompt_templates import render  # noqa: E402
from backend.run_simulation import step  # noqa: E402
from backend.sim_config import CognitionConfig  # noqa: E402
from penn_world import (  # noqa: E402
    PENN_ACTION_VERBS,
    PENN_EXTRA_ACTIONS,
    _gate_conversations_by_perception,
)
from text_adventure_games import conversation as convo  # noqa: E402
from text_adventure_games.llm_client import ToolCallResult  # noqa: E402

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


def _world(names, extra=None, llm_client=None):
    personas = [_persona(n) for n in names]
    game, chars = build_world(None, personas, _LOCATIONS)
    for cls in PENN_EXTRA_ACTIONS:
        game.parser.add_action(cls)
    attach_agents(
        chars, personas, extra_action_names=extra or [], llm_client=llm_client
    )
    return game, chars


class _ToolBrain:
    """Minimal real-brain stand-in: has call_tools and is not agent.schedule,
    so _use_action_tools is True and the per-action tool path is live."""

    def __init__(self):
        self.context: dict = {}

    def call_tools(self, messages, tools, **kwargs):
        return None  # decline; tests call action_tools_for directly


# ---------------------------------------------------------------- wait offer


def test_wait_is_in_penn_action_verbs():
    assert "wait" in PENN_ACTION_VERBS


def test_wait_penn_is_registered_and_overrides_engine_wait():
    game, _chars = _world(["Ada"])
    assert game.parser.actions["wait"] is WaitPenn


def test_wait_tool_offered_with_pacing_slots():
    game, chars = _world(
        ["Ada"], extra=list(PENN_ACTION_VERBS), llm_client=_ToolBrain()
    )
    tools = {t["name"]: t for t in action_tools_for(game, chars["Ada"])}
    assert "wait" in tools
    props = tools["wait"]["parameters"]["properties"]
    assert "duration_minutes" in props
    assert "emoji" in props
    assert "duration_minutes" in tools["wait"]["parameters"]["required"]


def test_authored_wait_spacers_now_promote_to_action_names():
    personas = [_persona("Ada")]
    personas[0]["schedule"][0]["commands"] = ["wait", "wait"]
    game, chars = build_world(None, personas, _LOCATIONS)
    attach_agents(chars, personas)
    assert "wait" in chars["Ada"].agent.action_names


def test_wait_apply_effects_is_engine_identical_without_a_stash():
    # The mock path (schedule spacers) must be byte-identical: no stashed
    # duration -> no activity stamp, and the engine's "Time passes." message.
    game, chars = _world(["Ada"])
    ada = chars["Ada"]
    ada.set_property("activity", "reading")
    assert game.parser.parse_command("wait", actor=ada)
    assert ada.get_property("activity") == "reading"  # untouched


def test_settled_wait_stamps_waiting_activity():
    game, chars = _world(["Ada"])
    ada = chars["Ada"]
    ada.set_property("activity", "reading")
    ada.agent.last_duration_minutes = 20  # what _take_pacing_args stashes
    assert game.parser.parse_command("wait", actor=ada)
    assert ada.get_property("activity") == "waiting"


# ------------------------------------------------------------ wait memory


def test_reflection_template_pins_the_wait_line():
    assert render("reflection", verb="wait") == "I waited; nothing needed doing."


def test_spacer_wait_writes_no_memory():
    game, chars = _world(["Ada"])
    ada = chars["Ada"]
    remember_outcome(ada, "wait", 3)
    texts = [r.text for r in ada.agent.memory.retrieve(query="waited", turn=3)]
    assert "I waited; nothing needed doing." not in texts


def test_settled_wait_writes_the_honest_idle_memory():
    game, chars = _world(["Ada"])
    ada = chars["Ada"]
    ada.agent.last_duration_minutes = 20
    remember_outcome(ada, "wait", 3)
    texts = [r.text for r in ada.agent.memory.retrieve(query="waited", turn=3)]
    assert "I waited; nothing needed doing." in texts


# ------------------------------------------------------------ talk_to gate


def _colocate(game, chars, names, place="Plaza"):
    loc = game.locations[place]
    for n in names:
        ch = chars[n]
        if ch.location is not None:
            ch.location.remove_character(ch)
        loc.add_character(ch)


def test_talk_to_is_registered_and_in_penn_action_verbs():
    game, _chars = _world(["Ada"])
    assert game.parser.actions["talk_to"] is TalkTo
    assert "talk_to" in PENN_ACTION_VERBS


def test_talk_to_gate_rejects_an_absent_target_with_actionable_feedback():
    game, chars = _world(["Ada", "Bo"])
    _colocate(game, chars, ["Ada"], "Plaza")
    _colocate(game, chars, ["Bo"], "Cafe")  # not co-located
    ok = game.parser.parse_command("talk_to Bo", actor=chars["Ada"])
    assert not ok
    assert "no one" in game.parser.last_fail_message.lower()
    assert not chars["Ada"].get_property("talk_request")


def test_talk_to_gate_rejects_a_dead_target():
    game, chars = _world(["Ada", "Bo"])
    _colocate(game, chars, ["Ada", "Bo"])
    chars["Bo"].set_property("is_dead", True)
    ok = game.parser.parse_command("talk_to Bo", actor=chars["Ada"])
    assert not ok
    assert "Bo" in game.parser.last_fail_message
    assert not chars["Ada"].get_property("talk_request")


def test_talk_to_success_sets_the_one_shot_markers():
    game, chars = _world(["Ada", "Bo"])
    _colocate(game, chars, ["Ada", "Bo"])
    assert game.parser.parse_command("talk_to Bo about the demo", actor=chars["Ada"])
    assert chars["Ada"].get_property("talk_request") == "Bo"
    assert chars["Ada"].get_property("talk_topic") == "the demo"


def test_talk_to_without_topic_sets_no_topic_marker():
    game, chars = _world(["Ada", "Bo"])
    _colocate(game, chars, ["Ada", "Bo"])
    assert game.parser.parse_command("talk_to Bo", actor=chars["Ada"])
    assert chars["Ada"].get_property("talk_request") == "Bo"
    assert chars["Ada"].get_property("talk_topic") is False  # defaultdict default


# ------------------------------------------------------- talk_to curation


def _tools(game, char):
    return {t["name"]: t for t in action_tools_for(game, char)}


def test_talk_to_not_offered_when_alone():
    game, chars = _world(
        ["Ada", "Bo"], extra=list(PENN_ACTION_VERBS), llm_client=_ToolBrain()
    )
    _colocate(game, chars, ["Ada"], "Plaza")
    _colocate(game, chars, ["Bo"], "Cafe")
    assert "talk_to" not in _tools(game, chars["Ada"])


def test_talk_to_offered_with_colocated_living_names_as_enum():
    game, chars = _world(
        ["Ada", "Bo"], extra=list(PENN_ACTION_VERBS), llm_client=_ToolBrain()
    )
    _colocate(game, chars, ["Ada", "Bo"])
    tool = _tools(game, chars["Ada"])["talk_to"]
    assert tool["parameters"]["properties"]["person"]["enum"] == ["Bo"]


def test_talk_to_not_offered_when_the_only_other_is_dead():
    game, chars = _world(
        ["Ada", "Bo"], extra=list(PENN_ACTION_VERBS), llm_client=_ToolBrain()
    )
    _colocate(game, chars, ["Ada", "Bo"])
    chars["Bo"].set_property("is_dead", True)
    assert "talk_to" not in _tools(game, chars["Ada"])


def test_offered_iff_gate_passes():
    # The symmetry the epic's invariant demands: whenever the tool is offered,
    # a talk_to at one of the enum names passes the gate; whenever it isn't,
    # the gate fails for every co-located candidate.
    game, chars = _world(
        ["Ada", "Bo"], extra=list(PENN_ACTION_VERBS), llm_client=_ToolBrain()
    )
    for placement, expect_offered in ((["Ada", "Bo"], True), (["Ada"], False)):
        _colocate(game, chars, placement, "Plaza")
        if "Bo" not in placement:
            _colocate(game, chars, ["Bo"], "Cafe")
        offered = "talk_to" in _tools(game, chars["Ada"])
        gate = game.parser.parse_command("talk_to Bo", actor=chars["Ada"])
        assert offered == expect_offered == bool(gate)
        chars["Ada"].set_property("talk_request", False)  # reset between rounds


def test_agentless_observer_is_never_a_talk_target():
    # build_world's silent "Observer" (the engine's required player) has no
    # agent, so it can never converse -- neither offered nor gate-passable.
    game, chars = _world(
        ["Ada", "Bo"], extra=list(PENN_ACTION_VERBS), llm_client=_ToolBrain()
    )
    _colocate(game, chars, ["Ada"], "Plaza")
    _colocate(game, chars, ["Bo"], "Cafe")
    assert "talk_to" not in _tools(game, chars["Ada"])  # Observer doesn't count
    assert not game.parser.parse_command("talk_to Observer", actor=chars["Ada"])


# ------------------------------------------- talk_request -> conversation


class _ScriptedConvoBrain:
    """Speaks fixed lines (one per converse() ask) then goes silent; answers
    conversation_outcome inertly and counts those calls (the #582 assert).
    Mirrors test_conversation_multitick_371's brain."""

    def __init__(self, lines):
        self._lines = list(lines)
        self.context: dict = {}
        self.outcome_calls = 0

    def call_tool(self, messages, tool, max_tokens=256, temperature=0.0):
        if tool["name"] == "conversation_outcome":
            self.outcome_calls += 1
            return {"plans_changed": False}
        if self._lines:
            return {"utterance": self._lines.pop(0), "done": not self._lines}
        return {}


def _request_setup(brain, target_walking=False):
    game, chars = _world(["Ada", "Bo"], llm_client=brain)
    _colocate(game, chars, ["Ada", "Bo"])
    order = ["Ada", "Bo"]
    state = {n: {"performing": True, "path": [], "chat": None} for n in order}
    if target_walking:
        state["Bo"]["path"] = [(1, 1), (2, 2)]
    frame = {n: {} for n in order}
    return game, chars, state, frame, order


def test_talk_request_opens_the_conversation_same_tick_initiator_first():
    brain = _ScriptedConvoBrain(["About that demo...", "Sure, let's sync."])
    game, chars, state, frame, order = _request_setup(brain)
    assert game.parser.parse_command("talk_to Bo about the demo", actor=chars["Ada"])
    active: dict = {}
    completed = maybe_converse(game, chars, state, frame, 0, {}, order, active=active)
    assert completed == 0 and len(active) == 1
    assert frame["Ada"]["chat"] == [["Ada", "About that demo..."]]  # Ada opens
    assert state["Ada"]["conversing"] and state["Bo"]["conversing"]
    assert chars["Ada"].get_property("talk_request") is False  # marker consumed


def test_talk_request_conversation_end_fires_the_582_outcome():
    brain = _ScriptedConvoBrain(["Hi Bo!"])  # one line, done=True -> ends tick 0
    game, chars, state, frame, order = _request_setup(brain)
    assert game.parser.parse_command("talk_to Bo", actor=chars["Ada"])
    cooldowns: dict = {}
    completed = maybe_converse(
        game, chars, state, frame, 0, cooldowns, order, active={}
    )
    assert completed == 1
    assert brain.outcome_calls == 2  # one pass per participant (#582)
    assert frozenset(("Ada", "Bo")) in cooldowns


def test_talk_request_respects_the_pair_cooldown():
    brain = _ScriptedConvoBrain(["Hi again!"])
    game, chars, state, frame, order = _request_setup(brain)
    cooldowns = {frozenset(("Ada", "Bo")): 0}  # just talked
    assert game.parser.parse_command("talk_to Bo", actor=chars["Ada"])
    completed = maybe_converse(
        game, chars, state, frame, 1, cooldowns, order, active={}
    )
    assert completed == 0
    assert frame["Ada"].get("chat") is None
    assert chars["Ada"].get_property("talk_request") is False  # still consumed
    # The dropped request leaves no false "I went to talk to Bo." record.
    texts = [r.text for r in chars["Ada"].agent.memory.retrieve(query="Bo", turn=1)]
    assert "I went to talk to Bo." not in texts


def test_talk_request_dropped_while_target_is_walking():
    brain = _ScriptedConvoBrain(["Hey!"])
    game, chars, state, frame, order = _request_setup(brain, target_walking=True)
    assert game.parser.parse_command("talk_to Bo", actor=chars["Ada"])
    completed = maybe_converse(game, chars, state, frame, 0, {}, order, active={})
    assert completed == 0
    assert frame["Ada"].get("chat") is None


def test_talk_request_dropped_when_target_or_initiator_is_busy():
    # Target already conversing: the request is consumed and dropped. (Mirror
    # the caller's real invariant -- run_simulation.step() clears `performing`
    # while conversing -- so phase 2's own pair-scan doesn't independently
    # re-match them and mask which guard actually fired.)
    brain = _ScriptedConvoBrain(["Hey!"])
    game, chars, state, frame, order = _request_setup(brain)
    state["Bo"]["conversing"] = True
    state["Bo"]["performing"] = False
    assert game.parser.parse_command("talk_to Bo", actor=chars["Ada"])
    completed = maybe_converse(game, chars, state, frame, 0, {}, order, active={})
    assert completed == 0
    assert frame["Ada"].get("chat") is None
    assert chars["Ada"].get_property("talk_request") is False

    # Initiator already mid-conversation (in the active set): a pre-seeded
    # Ada/Bo ActiveConversation dies on its first (inert) advance -- landing
    # both in finished_this_step, still "busy" for the rest of this tick -- so
    # Ada's talk_to toward a third resident is dropped by the same guard.
    brain2 = _ScriptedConvoBrain([])  # no lines: the pre-seeded convo ends at once
    game2, chars2 = _world(["Ada", "Bo", "Cara"], llm_client=brain2)
    _colocate(game2, chars2, ["Ada", "Bo", "Cara"])
    order2 = ["Ada", "Bo", "Cara"]
    state2 = {n: {"performing": True, "path": [], "chat": None} for n in order2}
    frame2 = {n: {} for n in order2}
    active = {
        frozenset(("Ada", "Bo")): ActiveConversation(
            a="Ada",
            b="Bo",
            convo=convo.Conversation(participants=("Ada", "Bo")),
            next_speaker="Ada",
            started=0,
        )
    }
    assert game2.parser.parse_command("talk_to Cara", actor=chars2["Ada"])
    completed2 = maybe_converse(
        game2, chars2, state2, frame2, 0, {}, order2, active=active
    )
    assert completed2 == 0
    assert frame2["Ada"].get("chat") is None
    assert chars2["Ada"].get_property("talk_request") is False


def test_talk_to_reflection_memory_carries_the_topic():
    assert (
        render("reflection", verb="talk_to", person="Bo", topic="the demo")
        == "I went to talk to Bo about the demo."
    )
    assert (
        render("reflection", verb="talk_to", person="Bo", topic="")
        == "I went to talk to Bo."
    )


def test_talk_to_memory_is_written_only_when_the_conversation_opens():
    # Parse alone records nothing: a request phase 1.5 drops (cooldown, busy
    # target) must not stamp a false 4.0 memory on every un-settled retry.
    brain = _ScriptedConvoBrain(["About that demo..."])
    game, chars, state, frame, order = _request_setup(brain)
    ada = chars["Ada"]
    assert game.parser.parse_command("talk_to Bo about the demo", actor=ada)
    remember_outcome(ada, "talk_to Bo about the demo", 0)
    texts = [r.text for r in ada.agent.memory.retrieve(query="Bo", turn=0)]
    assert "I went to talk to Bo about the demo." not in texts
    # The open writes it -- before the first line, so the opener's retrieval
    # (query = partner name) can thread the topic into what gets said.
    maybe_converse(game, chars, state, frame, 0, {}, order, active={})
    texts = [r.text for r in ada.agent.memory.retrieve(query="Bo", turn=0)]
    assert "I went to talk to Bo about the demo." in texts


# ------------------------------------- a dropped request is not silent (#793)


def test_dropped_talk_request_is_remembered_and_bounded_793():
    # TalkTo.apply_effects already returned `ok`, so nothing else can record
    # this: without both halves the agent re-decides talk_to against an
    # unchanged world every tick (#793 measured a 112-decision streak).
    brain = _ScriptedConvoBrain(["Hi again!"])
    game, chars, state, frame, order = _request_setup(brain)
    cooldowns = {frozenset(("Ada", "Bo")): 0}  # just talked
    assert game.parser.parse_command("talk_to Bo about the demo", actor=chars["Ada"])
    completed = maybe_converse(
        game, chars, state, frame, 1, cooldowns, order, active={}
    )
    assert completed == 0
    # (a) the reason is in the memory, keyed to the command the agent issued --
    # the topic included, so the record matches what it actually asked for.
    texts = [r.text for r in chars["Ada"].agent.memory.retrieve(query="Bo", turn=1)]
    assert (
        'I tried to "talk_to Bo about the demo" but it didn\'t work: we have'
        " talked recently, and it's too soon to talk again." in texts
    )
    # (b) the retry is bounded: settled, off-plan, so the pre-pass un-latches
    # without advancing the schedule pointer.
    assert state["Ada"]["performing"] is True
    assert state["Ada"]["credit_stop"] is False
    assert state["Ada"]["perform_until"] == 1 + DEAD_TALK_SETTLE_STEPS


def test_dropped_talk_request_reason_names_the_walking_target_793():
    # Each gate gets its own clause: a generic "it didn't work" gives the model
    # nothing to steer around, which is the whole point of the fix.
    brain = _ScriptedConvoBrain(["Hey!"])
    game, chars, state, frame, order = _request_setup(brain, target_walking=True)
    assert game.parser.parse_command("talk_to Bo", actor=chars["Ada"])
    assert maybe_converse(game, chars, state, frame, 0, {}, order, active={}) == 0
    texts = [r.text for r in chars["Ada"].agent.memory.retrieve(query="Bo", turn=0)]
    assert (
        'I tried to "talk_to Bo" but it didn\'t work: they were walking '
        "somewhere else." in texts
    )


def test_talk_request_that_opens_with_nothing_still_settles_793():
    # The sibling hole: the conversation opened, so no gate dropped it, but it
    # produced no line -- and _finish_conversation records no cooldown when
    # nothing was said, so the settle is the ONLY thing bounding this retry.
    brain = _ScriptedConvoBrain([])  # first ask returns {} -> dies at once
    game, chars, state, frame, order = _request_setup(brain)
    cooldowns: dict = {}
    assert game.parser.parse_command("talk_to Bo", actor=chars["Ada"])
    completed = maybe_converse(
        game, chars, state, frame, 0, cooldowns, order, active={}
    )
    assert completed == 0
    assert frozenset(("Ada", "Bo")) not in cooldowns  # nothing said -> no cooldown
    assert state["Ada"]["perform_until"] == 0 + DEAD_TALK_SETTLE_STEPS


def test_opened_talk_request_is_not_a_dead_talk_settle_793_837():
    # A conversation that really opens writes the intent memory (asserted
    # above), no failure record, and never receives the DEAD-talk retry settle.
    # Since #837 its initiator does receive a completed one-shot latch so the
    # schedule credit has a consumption site after the conversation releases.
    brain = _ScriptedConvoBrain(["About that demo...", "Sure, let's sync."])
    game, chars, state, frame, order = _request_setup(brain)
    state["Ada"]["performing"] = False
    assert game.parser.parse_command("talk_to Bo", actor=chars["Ada"])
    maybe_converse(game, chars, state, frame, 0, {}, order, active={})
    texts = [r.text for r in chars["Ada"].agent.memory.retrieve(query="Bo", turn=0)]
    assert not [t for t in texts if t.startswith("I tried to")]
    assert state["Ada"]["performing"] is True
    assert state["Ada"]["credit_stop"] is True
    assert state["Ada"]["perform_until"] == 0
    assert state["Ada"]["conversing"] is True
    # The target did not choose talk_to and was already performing; its own
    # activity latch is left intact.
    assert state["Bo"].get("perform_until") is None


def test_talk_request_credit_advances_schedule_after_release_837():
    """The successful opener's latch reaches the real schedule pre-pass.

    This is the regression from #837 end to end: the first line earns a
    one-shot latch, the playback hold delays it, and the first tick after
    release advances the pointer rather than leaving the conversation stop
    current forever.
    """
    brain = _ScriptedConvoBrain(["Hi Bo!"])  # one real line, then playback hold
    game, chars, state, frame, order = _request_setup(brain)
    ada = chars["Ada"]
    ada.agent.schedule.schedule.append(
        {"place": "Plaza", "activity": "walking", "emoji": None, "steps": 5}
    )
    state["Ada"]["performing"] = False
    assert game.parser.parse_command("talk_to Bo", actor=ada)

    active: dict = {}
    assert maybe_converse(game, chars, state, frame, 0, {}, order, active=active) == 1
    assert ada.agent.schedule.stop_index == 0
    assert state["Ada"]["conversing"] is True

    # Release the completed exchange after its viewer playback hold. The
    # schedule pre-pass has not run yet, so the pointer must still be at stop 0.
    hold_until = next(iter(active.values())).hold_until
    assert hold_until is not None
    maybe_converse(game, chars, state, frame, hold_until, {}, order, active=active)
    assert not active
    assert state["Ada"]["conversing"] is False
    assert ada.agent.schedule.stop_index == 0

    # Fill the display state step() reads. A one-tile path keeps Ada out of the
    # decision phase after the pre-pass; it is immaterial to credit consumption.
    state["Ada"].update(
        {
            "tile": (0, 0),
            "path": [(0, 0)],
            "pron": "\U0001f9d1",
            "desc": "talking",
            "reasoning": "(r)",
            "memories": [],
            "trace": [],
            "stop_since": 0,
        }
    )
    step(
        game,
        chars,
        state,
        hold_until + 1,
        order=["Ada"],
        world_map=None,
        emoji={"Ada": "\U0001f9d1"},
    )

    assert ada.agent.schedule.stop_index == 1
    assert state["Ada"]["perform_until"] is None


# ---------------------------------------- proximity is tiles, not rooms (#835)


def _colocate_at_tiles(chars, ada_tile, bo_tile, vision_r=8):
    """Put Ada/Bo out of (or in) tile range within their shared Location, and
    install the Penn perception gate the live sim wires in (build_world alone
    leaves audience_for room-based, so can_converse would ignore tiles)."""
    for n in ("Ada", "Bo"):
        chars[n].vision_r = vision_r
    chars["Ada"].tile = ada_tile
    chars["Bo"].tile = bo_tile


def test_talk_request_dropped_when_target_is_out_of_tile_range_835():
    # Ada and Bo share one engine Location (the hub) but stand 50 tiles apart --
    # a Penn building interior / the outdoor hub is one ~2000-tile address, so
    # room identity is not proximity. The opener must gate on the same tile
    # metric the auto-pairing scan uses, or it pairs them into a conversation
    # that renders as stretching across the map (#835). The parse gate is still
    # room-based, so the request is issued and it's THIS gate that must drop it.
    brain = _ScriptedConvoBrain(["Hey, over here!"])
    game, chars, state, frame, order = _request_setup(brain)
    _gate_conversations_by_perception((game, chars))
    _colocate_at_tiles(chars, (0, 0), (50, 50))
    assert game.parser.parse_command("talk_to Bo", actor=chars["Ada"])
    completed = maybe_converse(game, chars, state, frame, 0, {}, order, active={})
    assert completed == 0
    assert frame["Ada"].get("chat") is None
    # Not a silent drop: the #793 failure memory names the reason and the retry
    # is bounded by a dead-talk settle.
    texts = [r.text for r in chars["Ada"].agent.memory.retrieve(query="Bo", turn=0)]
    assert (
        'I tried to "talk_to Bo" but it didn\'t work: they were not close'
        " enough to talk to." in texts
    )
    assert state["Ada"]["perform_until"] == 0 + DEAD_TALK_SETTLE_STEPS


def test_talk_request_opens_when_target_is_within_tile_range_835():
    # The same setup and gate, but 3 tiles apart (within vision_r=8): the
    # conversation opens, so the gate isn't just always-closed -- it's the tile
    # distance that decides, exactly as it does for the automatic pair scan.
    brain = _ScriptedConvoBrain(["Hey, over here!"])
    game, chars, state, frame, order = _request_setup(brain)
    _gate_conversations_by_perception((game, chars))
    _colocate_at_tiles(chars, (0, 0), (3, 3))
    assert game.parser.parse_command("talk_to Bo", actor=chars["Ada"])
    maybe_converse(game, chars, state, frame, 0, {}, order, active={})
    assert frame["Ada"]["chat"] == [["Ada", "Hey, over here!"]]  # opened
    assert state["Ada"]["conversing"] and state["Bo"]["conversing"]


def test_talk_to_target_match_skips_the_verb_token():
    # character_in_room scans by substring: a resident named "Al" sits inside
    # the literal "talk_to", so the match must only see the person head.
    game, chars = _world(["Ada", "Al", "Bo"])
    _colocate(game, chars, ["Ada", "Al", "Bo"])
    assert game.parser.parse_command("talk_to Bo", actor=chars["Ada"])
    assert chars["Ada"].get_property("talk_request") == "Bo"
    # And an absent target fails the gate instead of ghost-matching Al.
    game2, chars2 = _world(["Ada", "Al"])
    _colocate(game2, chars2, ["Ada", "Al"])
    assert not game2.parser.parse_command("talk_to Zoe", actor=chars2["Ada"])
    assert chars2["Ada"].get_property("talk_request") is False


def test_clockless_wait_is_a_plain_one_tick_idle():
    # With no SimClock the #581 duration can't be honored (the settle trigger
    # reads minutes -> steps), so step() drops the stash pre-command: no
    # "waiting" stamp, no honest-idle memory, no settle -- the predicates
    # agree instead of recording a settled wait that never settles.
    class _WaitOnceBrain:
        def __init__(self):
            self.context: dict = {}

        def call_tools(self, messages, tools, **kwargs):
            return ToolCallResult(
                text=None,
                tool_calls=[
                    {
                        "id": "c1",
                        "name": "wait",
                        "arguments": {"reasoning": "idle", "duration_minutes": 20},
                    }
                ],
            )

    class _StubMap:
        def walk_path(self, src, address, furniture=None):
            return []

    game, chars = _world(
        ["Ada"], extra=list(PENN_ACTION_VERBS), llm_client=_WaitOnceBrain()
    )
    ada = chars["Ada"]
    ada.set_property("activity", "reading")
    state = {
        "Ada": {
            "tile": (0, 0),
            "path": [],
            "pron": "\U0001f9d1",
            "desc": "idling",
            "performing": False,
            "perform_until": None,
            "reasoning": "",
            "memories": [],
            "chat": None,
            "stop_since": 0,
        }
    }
    step(
        game,
        {"Ada": ada},
        state,
        0,
        order=["Ada"],
        world_map=_StubMap(),
        emoji={"Ada": "\U0001f9d1"},
        clock=None,
        cog=CognitionConfig(),
    )
    assert ada.get_property("activity") == "reading"  # no "waiting" stamp
    assert state["Ada"]["performing"] is False  # did not settle
    texts = [r.text for r in ada.agent.memory.retrieve(query="waited", turn=0)]
    assert "I waited; nothing needed doing." not in texts
