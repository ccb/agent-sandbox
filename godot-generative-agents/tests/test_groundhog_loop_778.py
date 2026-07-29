"""Break the groundhog-day conversation loop (issue #778).

Two co-located agents who keep choosing `talk_to` each other re-ran
substantially the same conversation forever. Two mechanisms, fixed here:

**A.** The #582 outcome pass produced a concrete `commitment` ("leaving right
now to grab food") on 16 of 18 calls in the live run `run-20260724-194343-78858a`
and threw every one away: the only consumer was `maybe_revise_plan`, and the
default `plan_mode: "schedule"` wires `MockPlanner`, whose `revise()` is a no-op.
The commitment now becomes a durable PLAN memory in the speaker's own stream.

**C.** `schedule.advance()` only fires for a CREDITED settle, and a *dropped*
`talk_to` routes through `settle_after_dead_talk`, which sets
`credit_stop = False` (#689). Before #831 a real conversation held anywhere
but the agent's own scheduled place was never credited either, so the pointer
could sit on a stop the conversation had already completed. A real
conversation now credits that stop wherever it was held (#831 dropped the
place requirement here too), by setting the pre-pass's own `credit_stop` flag
-- no second signal, and one-shot for free, since every path that sets
`perform_until` re-stamps `credit_stop`.

Fully offline (fake brains + fake planners). Run from the repo root::

    PYTHONPATH=.:godot-generative-agents uv run --no-sync pytest \\
        godot-generative-agents/tests/test_groundhog_loop_778.py -v
"""

import sys
from pathlib import Path

# Same import shim as test_conversation_consequences_582.py: the Penn sim
# modules run as scripts (no package), so tests import them off the sim
# directory itself.
_SIM_DIR = (
    Path(__file__).resolve().parents[2] / "godot-generative-agents" / "backend" / "penn"
)
sys.path.insert(0, str(_SIM_DIR))

from text_adventure_games.memory import AgentMemory, MemoryKind  # noqa: E402
from text_adventure_games.planning import DailyPlan, Stop  # noqa: E402
from text_adventure_games.things import Character  # noqa: E402

from backend import cognition  # noqa: E402
from backend.prompt_templates import render  # noqa: E402


def test_commitment_memory_renders_from_its_template():
    """The memory text is a .prompty, per the repo rule that agent-facing strings
    are never hand-built inline -- pinned here like #779's relationship_memory."""
    assert (
        render(
            "commitment_memory",
            other="Chris Donnelly",
            commitment="Pizza place near campus in about 20 minutes",
        )
        == "I agreed with Chris Donnelly: Pizza place near campus in about 20 minutes"
    )


class _OutcomeBrain:
    """A real-shaped brain: answers exactly one conversation_outcome call with a
    scripted dict, and records what tools it was asked for."""

    def __init__(self, result):
        self._result = result
        self.context: dict = {}
        self.calls: list[dict] = []

    def call_tool(self, messages, tool, max_tokens=256, temperature=0.0):
        self.calls.append({"tool": tool["name"], "messages": messages})
        return self._result


class _NoOpPlanner:
    """The planner shape the DEFAULT live run actually has: MockPlanner, whose
    revise() returns the plan unchanged. This is the configuration that dropped
    all 16 of the live run's commitments, so it is the one the regression pins.
    """

    def __init__(self):
        self.triggers = []

    def generate(self, persona=None, memory=None, clock=None):
        return DailyPlan(stops=[Stop(place="Cafe", activity="reading", steps=5)])

    def revise(self, plan, trigger=None, memory=None, clock=None):
        self.triggers.append(trigger)
        return plan  # unchanged -> maybe_revise_plan commits nothing


class _FakeSchedule:
    """Minimal stand-in for the pacing client maybe_revise_plan reads (#581)."""

    def __init__(self):
        self.stop_index = 0
        self.replaced = None

    def replace_schedule(self, entries):
        self.replaced = entries


def _agent_with(brain, planner):
    """A bare LLMAgent-shaped stub carrying just what the outcome path reads."""
    char = Character("Maria Lopez", "Maria", "")
    agent = type("A", (), {})()
    agent.llm_client = brain
    agent.max_tokens = 256
    agent.memory = AgentMemory()
    agent.memory.owner = char.name
    agent.planner = planner
    agent.plan = planner.generate()
    agent.schedule = _FakeSchedule()
    agent._structured_system_message = lambda: "You are Maria Lopez."
    char.set_agent(agent)
    return char


def _plans(char):
    return [r for r in char.agent.memory.records if r.kind == MemoryKind.PLAN]


def test_commitment_becomes_a_locked_plan_memory():
    brain = _OutcomeBrain(
        {
            "plans_changed": True,
            "commitment": "meet Ayesha at the Library at 2pm",
            "relationship_note": "Ayesha is a kindred spirit about robotics.",
        }
    )
    maria = _agent_with(brain, _NoOpPlanner())

    cognition.apply_conversation_outcome(
        maria, "Ayesha Khan", "Maria Lopez: Library at 2?\nAyesha Khan: Yes.", step=7
    )

    plans = _plans(maria)
    assert len(plans) == 1
    # First-person, naming the partner and carrying the commitment verbatim.
    assert plans[0].text == (
        "I agreed with Ayesha Khan: meet Ayesha at the Library at 2pm"
    )
    assert plans[0].created_turn == 7
    # Importance is load-bearing: the SAME conversation mints an 8.0 relationship
    # note and 7-8 scored talk observations, so add_plan's 5.0 default would be
    # crowded straight out of the retrieved block by its own partner-chatter.
    assert plans[0].importance == cognition.RELATIONSHIP_NOTE_IMPORTANCE
    # Locked, for the same reason the note is: a deliberate high signal that the
    # #583 scorer must not re-guess.
    assert plans[0].metadata[cognition._IMPORTANCE_LOCKED] is True


def test_commitment_lands_even_though_the_planner_is_a_no_op():
    """The live-run regression. plan_mode "schedule" -> MockPlanner.revise is a
    no-op, so apply_conversation_outcome returns False and NOTHING used to
    survive the call. The intention must persist regardless."""
    brain = _OutcomeBrain(
        {
            "plans_changed": True,
            "commitment": "grab food with Ayesha, leaving right now",
            "commitment_timing": "immediate",
        }
    )
    planner = _NoOpPlanner()
    maria = _agent_with(brain, planner)

    changed = cognition.apply_conversation_outcome(
        maria, "Ayesha Khan", "Maria Lopez: Food?\nAyesha Khan: Now!", step=263
    )

    assert changed.changed is False  # planner proposed no change, as in live run
    assert changed.immediate_next is False
    assert planner.triggers[0].reason == cognition.CONVERSATION  # still offered
    assert len(_plans(maria)) == 1  # ...and the intention survived anyway


def test_no_commitment_writes_no_plan_memory():
    """plans_changed with no commitment string: the transcript remains the
    revision DETAIL (existing #582 behaviour), but a whole transcript must never
    be stored as a plan -- that is noise, not an intention."""
    brain = _OutcomeBrain({"plans_changed": True})  # no commitment key
    planner = _NoOpPlanner()
    maria = _agent_with(brain, planner)
    transcript = "Maria Lopez: See you at the game.\nAyesha Khan: I'll be there."

    cognition.apply_conversation_outcome(maria, "Ayesha Khan", transcript, step=1)

    assert planner.triggers[0].detail == transcript  # unchanged from #582
    assert _plans(maria) == []


def test_blank_commitment_writes_no_plan_memory():
    brain = _OutcomeBrain({"plans_changed": True, "commitment": "   "})
    maria = _agent_with(brain, _NoOpPlanner())

    cognition.apply_conversation_outcome(maria, "Ayesha Khan", "t", step=1)

    assert _plans(maria) == []


def test_plans_unchanged_writes_no_plan_memory():
    """A commitment string present but plans_changed false: the model did not
    commit to anything, so nothing is written."""
    brain = _OutcomeBrain(
        {"plans_changed": False, "commitment": "maybe coffee sometime"}
    )
    maria = _agent_with(brain, _NoOpPlanner())

    cognition.apply_conversation_outcome(maria, "Ayesha Khan", "t", step=1)

    assert _plans(maria) == []


from backend.build_world import build_world  # noqa: E402
from backend.cognition import attach_agents, maybe_converse  # noqa: E402

_LOCATIONS = [
    {"name": "Plaza", "description": "the plaza", "address": None, "hub": True},
    {"name": "Library", "description": "a library", "address": "T:Library:desks"},
    {"name": "Cafe", "description": "a cafe", "address": "T:Cafe:counter"},
]


def _convo_persona(name):
    """A persona whose single scheduled stop is the Cafe, so a conversation held
    IN the Cafe is at the scheduled place and one held in the Plaza is not."""
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


class _ConvoThenOutcomeBrain:
    """A real-shaped brain that both talks (one line, then done) and answers
    conversation_outcome. Shared by both agents, like the live path."""

    def __init__(self):
        self.context: dict = {}
        self.outcome_calls = 0

    def call_tool(self, messages, tool, max_tokens=256, temperature=0.0):
        if tool["name"] == "conversation_outcome":
            self.outcome_calls += 1
            return {"plans_changed": True, "commitment": "meet at the Library"}
        # The engine's dialogue seam (Agent.converse) forces the "speak" tool.
        return {"utterance": "Library later?", "done": True}


def _pair_talking_in(place_name, *, performing=True):
    """Co-locate two Cafe-scheduled agents in `place_name` and mark them settled.
    Returns (game, chars, state, frame, order) ready for maybe_converse."""
    personas = [_convo_persona("Maria Lopez"), _convo_persona("Ayesha Khan")]
    game, chars = build_world(None, personas, _LOCATIONS)
    attach_agents(chars, personas, llm_client=_ConvoThenOutcomeBrain())
    order = ["Maria Lopez", "Ayesha Khan"]
    room = game.locations[place_name]
    for name in order:
        ch = chars[name]
        if ch.location is not None:
            ch.location.remove_character(ch)
        room.add_character(ch)
    # credit_stop starts False here to simulate an agent latched by a #689
    # dead-talk settle (settle_after_dead_talk) who then goes on to hold a REAL
    # conversation -- the one case #831 actually changes the outcome for (see
    # cognition._credit_stop_for_conversation). So each test below asserts the
    # credit flipped that flag, not merely that it is set.
    state = {
        n: {
            "performing": performing,
            "path": None,
            "chat": None,
            "credit_stop": False,
        }
        for n in order
    }
    frame = {n: {} for n in order}
    return game, chars, state, frame, order


def test_conversation_at_the_scheduled_place_credits_the_stop():
    game, chars, state, frame, order = _pair_talking_in("Cafe")

    happened = maybe_converse(game, chars, state, frame, 4, {}, order, clock=None)

    assert happened == 1
    for name in order:
        # The flag the pre-pass reads to advance the schedule, flipped from the
        # False that settle_after_dead_talk left behind.
        assert state[name]["credit_stop"] is True


def test_conversation_away_from_the_scheduled_place_still_credits():
    """#831: a chat in the Plaza is a deviation from the scheduled Cafe stop,
    but the conversation still ran. Crediting nothing here was the same bug
    the perform-settle branch had on the sibling path -- but the practical
    effect was narrower than "pinned for the rest of the run": an uncredited
    settle still un-latches at its own expiry (`dead_talk_settle_steps`), so
    only a *repeating* dropped-talk loop actually froze the pointer.
    `performing` is the only guard now, not place."""
    game, chars, state, frame, order = _pair_talking_in("Plaza")

    happened = maybe_converse(game, chars, state, frame, 4, {}, order, clock=None)

    assert happened == 1  # they did talk...
    for name in order:
        assert state[name]["credit_stop"] is True  # ...and it was credited


def test_unsettled_agent_is_never_credited():
    """`performing` is required -- tested by calling the helper DIRECTLY.

    Going through maybe_converse here would be vacuous: its own pairing already
    requires both agents settled, so no conversation would open and the
    assertion would pass for the wrong reason. The only way an unsettled agent
    reaches the credit is a conversation maybe_react (#370) started mid-walk,
    which pins a WALKING agent that completed no stop -- crediting it would mark
    a stop the agent has not even arrived at as done.
    """
    game, chars, state, frame, order = _pair_talking_in("Cafe", performing=False)
    maria, st = chars["Maria Lopez"], state["Maria Lopez"]
    # Same agent, same room as the crediting test above -- only `performing`
    # differs, so this isolates the guard itself.
    assert maria.location.name == maria.agent.schedule.destination

    credited = cognition._credit_stop_for_conversation(maria, st)

    assert credited is False
    assert st["credit_stop"] is False
    # And the positive control: flip the one flag and the same call credits.
    st["performing"] = True
    assert cognition._credit_stop_for_conversation(maria, st) is True
    assert st["credit_stop"] is True


def test_mock_brain_credits_nothing():
    """Byte-identity guard at the unit level: the mock never converses, so the
    credit is never stamped and the pre-pass sees exactly what it sees today."""
    personas = [_convo_persona("Maria Lopez"), _convo_persona("Ayesha Khan")]
    game, chars = build_world(None, personas, _LOCATIONS)
    attach_agents(chars, personas, llm_client=None)  # mock brain
    order = ["Maria Lopez", "Ayesha Khan"]
    cafe = game.locations["Cafe"]
    for name in order:
        ch = chars[name]
        if ch.location is not None:
            ch.location.remove_character(ch)
        cafe.add_character(ch)
    state = {
        n: {"performing": True, "path": None, "chat": None, "credit_stop": False}
        for n in order
    }
    frame = {n: {} for n in order}

    happened = maybe_converse(game, chars, state, frame, 4, {}, order, clock=None)

    assert happened == 0
    for name in order:
        assert state[name]["credit_stop"] is False


from backend.run_simulation import step  # noqa: E402

_LOOP_LOCATIONS = [
    {"name": "Plaza", "description": "the plaza", "address": None, "hub": True},
    {"name": "Library", "description": "a library", "address": "T:Library:desk"},
]


class _StubMap:
    """No-op world map (pattern from test_dead_talk_settle_689.py): a `travel`
    decide always calls walk_path, so a bare stub keeps that path harmless."""

    def walk_path(self, src, address, furniture=None):
        return [(1, 1)]


def _loop_persona(name):
    """Two stops, so an advance is observable as stop_index moving."""
    return {
        "name": name,
        "home": "Plaza",
        "persona": f"I am {name}.",
        "emoji": "\U0001f9d1",
        "start_tile": [0, 0],
        "destination": "Plaza",
        "activity": "reading",
        "schedule": [
            {"place": "Plaza", "activity": "reading", "emoji": None, "steps": 5},
            {"place": "Library", "activity": "studying", "emoji": None, "steps": 5},
        ],
        "vision_r": 3,
    }


def _full_state(tile=(0, 0)):
    """A state entry with every key step() reads (from
    test_dead_talk_settle_689.py)."""
    return {
        "tile": tuple(tile),
        "path": [],
        "pron": "\U0001f9d1",
        "desc": "reading",
        "performing": False,
        "perform_until": None,
        "reasoning": "(r)",
        "memories": [],
        "chat": None,
        "stop_since": 0,
        "credit_stop": True,
        "conversing": False,
    }


def _pair_mid_dead_talk_settle():
    """Two co-located mock agents; Diego is latched in a #689 dead-talk settle
    (performing, credit_stop False, expiring at step 30) -- exactly the state a
    talk_to leaves behind."""
    personas = [_loop_persona("Diego Cruz"), _loop_persona("Sofia Reyes")]
    game, chars = build_world(None, personas, _LOOP_LOCATIONS)
    attach_agents(chars, personas, llm_client=None)
    order = ["Diego Cruz", "Sofia Reyes"]
    state = {n: _full_state() for n in order}
    state["Diego Cruz"].update(
        {"performing": True, "credit_stop": False, "perform_until": 30}
    )
    emoji = {n: "\U0001f9d1" for n in order}
    return game, chars, state, order, emoji


def test_credited_settle_expiry_advances_the_schedule():
    game, chars, state, order, emoji = _pair_mid_dead_talk_settle()
    diego, st = chars["Diego Cruz"], state["Diego Cruz"]
    # Produce the credit the way a real conversation does rather than hand-setting
    # the flag, so this pins the whole seam: credit -> pre-pass -> advance. Diego
    # is settled at Plaza, his current scheduled stop.
    assert cognition._credit_stop_for_conversation(diego, st) is True

    step(game, chars, state, 30, order=order, world_map=_StubMap(), emoji=emoji)

    assert diego.agent.schedule.stop_index == 1


def test_credit_at_the_last_stop_settles_in_place():
    """At the FINAL stop advance() returns False, so the agent stays latched and
    settles there for the rest of the run.

    That is deliberate -- the same end-of-day "stay put" rule an on-plan agent
    gets -- and load-bearing for the mock bake: un-latching here would make the
    mock re-decide at its last stop and drift every later frame. Pinned because
    the credit is what routes a *conversing* agent onto this branch at all
    (before #778 introduced this credit, a conversing agent's settle expiry had
    no way to see it had completed its last stop, and simply un-latched)."""
    game, chars, state, order, emoji = _pair_mid_dead_talk_settle()
    diego, st = chars["Diego Cruz"], state["Diego Cruz"]
    diego.agent.schedule.stop_index = 1  # the last of two stops: Library
    library = game.locations["Library"]
    diego.location.remove_character(diego)
    library.add_character(diego)
    assert cognition._credit_stop_for_conversation(diego, st) is True

    step(game, chars, state, 30, order=order, world_map=_StubMap(), emoji=emoji)

    assert diego.agent.schedule.stop_index == 1  # nothing left to advance to
    assert st["performing"] is True  # still latched, i.e. settled for the run
    assert st["perform_until"] is None


def test_uncredited_settle_expiry_does_not_advance():
    """Pins today's behaviour: an uncredited dead-talk settle still reads
    `credited = False`, so the pre-pass skips `advance()` and un-latches
    without moving the pointer (#689)."""
    game, chars, state, order, emoji = _pair_mid_dead_talk_settle()

    step(game, chars, state, 30, order=order, world_map=_StubMap(), emoji=emoji)

    assert chars["Diego Cruz"].agent.schedule.stop_index == 0
