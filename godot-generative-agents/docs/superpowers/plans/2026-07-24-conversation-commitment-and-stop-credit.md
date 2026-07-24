# Breaking the Groundhog-Day Conversation Loop — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Stop two co-located agents from re-negotiating the same conversation
forever, by persisting the commitment the model already produces and by letting
a conversation held at an agent's scheduled place complete that stop.

**Architecture:** Two independent changes to the Penn cognition layer. **Fix A**
writes the `conversation_outcome` tool's `commitment` string into the speaker's
own memory stream as a locked, high-importance `PLAN` record — today it is only
handed to `maybe_revise_plan`, whose default planner (`MockPlanner`) is a no-op,
so the intention is discarded. **Fix C** stamps a `convo_at_stop` credit when a
real conversation finishes at the agent's scheduled place, and spends that credit
at `run_simulation`'s latch-expiry pre-pass so `schedule.advance()` finally
fires. Both are unreachable under the deterministic mock brain, which never
converses, so the byte-identical bake is preserved by vacuity.

**Tech Stack:** Python 3.12, uv (`uv.lock` + `.python-version` pinned), pytest,
black. No new dependencies.

**Spec:** `godot-generative-agents/docs/specs/2026-07-24-conversation-commitment-and-stop-credit-design.md`
**Issue:** #778 · **Draft PR:** #785 · **Branch:** `worktree-fix-778-groundhog-loop` (base `main`)

## Global Constraints

- **The mock bake must stay byte-identical.** Neither fix may change a single
  byte of the offline replay. Guarded by `test_bake_is_byte_identical` in
  `godot-generative-agents/tests/test_replay_contract.py:240` (runs each
  scenario under 3 different `PYTHONHASHSEED` values). This is the repo's
  hardest invariant — if it fails, the change is wrong, not the test.
- **The worktree's venv starts bare.** Run `uv sync --extra dev server llm`
  once before the first test command, or every import fails.
- **All test commands run from the repo root** with the sim package on the path:
  `PYTHONPATH=.:godot-generative-agents uv run --no-sync pytest ...`
- **Format with `uv run black .`** before each commit.
- **Never use bare `git stash` / `git stash pop`** — the stash stack is shared
  with other worktrees and other sessions. Use a WIP commit instead.
- **Do not push to `main`, force-push, or merge.** Work lands on
  `worktree-fix-778-groundhog-loop`, which is already pushed as draft PR #785.
- **Reuse the existing constants**, do not add new ones:
  `cognition.RELATIONSHIP_NOTE_IMPORTANCE` (`8.0`) and
  `cognition._IMPORTANCE_LOCKED` (`"importance_locked"`).
- **Test files never import each other** in this repo — each per-issue test file
  carries its own fixtures. Duplicating a small fixture into the new test file
  is correct here, not a DRY violation.

---

## File Structure

| File | Responsibility | Change |
|---|---|---|
| `godot-generative-agents/backend/cognition.py` | Penn cognition: the outcome pass and the conversation driver | **Modify** — Fix A in `apply_conversation_outcome`; Fix C's new `_credit_stop_for_conversation` helper + its call in `_advance_conversation` |
| `godot-generative-agents/backend/run_simulation.py` | The step loop, including the latch-expiry pre-pass that owns `schedule.advance()` | **Modify** — spend the `convo_at_stop` credit (2 lines) |
| `godot-generative-agents/tests/test_groundhog_loop_778.py` | All tests for both fixes | **Create** — new per-issue test file, matching the repo's `test_dead_talk_settle_689.py` / `test_failure_memory_636.py` convention |

No new files in `backend/`. Both edits are small and land in the module that
already owns the behaviour — `cognition.py` owns conversation bookkeeping,
`run_simulation.py` owns the schedule pointer. Splitting either into a new
module would separate code that changes together.

---

## Task 1: Fix A — the commitment becomes a locked PLAN memory

**Files:**
- Modify: `godot-generative-agents/backend/cognition.py:1291-1303` (the tail of `apply_conversation_outcome`)
- Test: `godot-generative-agents/tests/test_groundhog_loop_778.py` (create)

**Interfaces:**
- Consumes: nothing from earlier tasks.
- Produces: no new public names. `apply_conversation_outcome(char, partner_name,
  transcript, step, clock=None) -> bool` keeps its exact signature and return
  meaning (`True` iff the plan changed). The new side effect is one extra
  `MemoryKind.PLAN` record in `char.agent.memory.records`, with
  `importance == cognition.RELATIONSHIP_NOTE_IMPORTANCE` and
  `metadata[cognition._IMPORTANCE_LOCKED] is True`.

- [ ] **Step 1: Sync the worktree venv** (once, before any test command)

```bash
uv sync --extra dev server llm
```

Expected: exits 0 and creates `.venv/`. Skip if `.venv/bin/python` already exists.

- [ ] **Step 2: Write the failing tests**

Create `godot-generative-agents/tests/test_groundhog_loop_778.py` with exactly
this content. (Fixtures are adapted from
`tests/test_conversation_consequences_582.py`; per-issue test files in this repo
are self-contained.)

```python
"""Break the groundhog-day conversation loop (issue #778).

Two co-located agents who keep choosing `talk_to` each other re-ran
substantially the same conversation forever. Two mechanisms, fixed here:

**A.** The #582 outcome pass produced a concrete `commitment` ("leaving right
now to grab food") on 16 of 18 calls in the live run `run-20260724-194343-78858a`
and threw every one away: the only consumer was `maybe_revise_plan`, and the
default `plan_mode: "schedule"` wires `MockPlanner`, whose `revise()` is a no-op.
The commitment now becomes a durable PLAN memory in the speaker's own stream.

**C.** `schedule.advance()` only fires for an ON-PLAN settle, and a `talk_to`
routes through `_settle_after_dead_talk`, which sets `on_plan = False` (#689).
So no conversation ever advanced a stop -- not even when the conversation WAS
the scheduled activity. A real conversation held at the scheduled place now
credits that stop.

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
        {"plans_changed": True, "commitment": "grab food with Ayesha, leaving right now"}
    )
    planner = _NoOpPlanner()
    maria = _agent_with(brain, planner)

    changed = cognition.apply_conversation_outcome(
        maria, "Ayesha Khan", "Maria Lopez: Food?\nAyesha Khan: Now!", step=263
    )

    assert changed is False  # the planner proposed no change -- as in the live run
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
```

- [ ] **Step 3: Run the tests to verify they fail**

```bash
PYTHONPATH=.:godot-generative-agents uv run --no-sync pytest \
    godot-generative-agents/tests/test_groundhog_loop_778.py -v
```

Expected: `test_commitment_becomes_a_locked_plan_memory` and
`test_commitment_lands_even_though_the_planner_is_a_no_op` FAIL with
`assert 0 == 1` (`len(plans)` is 0 — nothing writes a PLAN record yet). The three
negative tests already PASS, which is correct: they pin behaviour that must not
change.

- [ ] **Step 4: Implement Fix A**

In `godot-generative-agents/backend/cognition.py`, replace the tail of
`apply_conversation_outcome` — currently:

```python
    if result.get("plans_changed") is not True:
        return False
    commitment = result.get("commitment")
    detail = (
        commitment.strip()
        if isinstance(commitment, str) and commitment.strip()
        else transcript
    )
    return maybe_revise_plan(char, RevisionTrigger(CONVERSATION, step, detail), clock)
```

with:

```python
    if result.get("plans_changed") is not True:
        return False
    commitment = result.get("commitment")
    has_commitment = isinstance(commitment, str) and bool(commitment.strip())
    detail = commitment.strip() if has_commitment else transcript
    # #778: the commitment becomes a durable INTENTION in this agent's own
    # stream, not merely a revision trigger. Before this, maybe_revise_plan was
    # its ONLY consumer -- and the default plan_mode "schedule" wires
    # MockPlanner, whose revise() returns the plan unchanged, so an agreement
    # the model stated outright ("leaving right now to grab food") was silently
    # dropped and re-negotiated on every cooldown expiry. Written here, BEFORE
    # the revision, so it lands whether or not the planner does anything.
    #
    # RELATIONSHIP_NOTE_IMPORTANCE, not add_plan's 5.0 default, is load-bearing:
    # the same conversation mints an 8.0 relationship note and 7-8 #583-scored
    # talk observations, so a 5.0 intention is crowded out of the retrieved
    # block by its own partner-chatter. Locked for the same reason the note
    # above is -- a deliberate high signal the scorer must not re-guess.
    # The transcript fallback is deliberately NOT written: a whole transcript
    # stored as a "plan" is noise, so only a real commitment persists.
    if has_commitment:
        intent = agent.memory.add_plan(
            f"I agreed with {partner_name}: {detail}",
            turn=step,
            importance=RELATIONSHIP_NOTE_IMPORTANCE,
        )
        intent.metadata[_IMPORTANCE_LOCKED] = True
    return maybe_revise_plan(char, RevisionTrigger(CONVERSATION, step, detail), clock)
```

- [ ] **Step 5: Run the tests to verify they pass**

```bash
PYTHONPATH=.:godot-generative-agents uv run --no-sync pytest \
    godot-generative-agents/tests/test_groundhog_loop_778.py -v
```

Expected: 5 passed.

- [ ] **Step 6: Run the #582 and #583 suites for regressions**

```bash
PYTHONPATH=.:godot-generative-agents uv run --no-sync pytest \
    godot-generative-agents/tests/test_conversation_consequences_582.py \
    godot-generative-agents/tests/test_importance_scoring_583.py \
    godot-generative-agents/tests/test_conversation_multitick_371.py -v
```

Expected: all pass. Note especially that
`test_small_talk_changes_nothing` asserts `memory.records == []` and
`test_missing_commitment_falls_back_to_the_transcript_as_detail` asserts the
transcript detail — both must still pass, which is what the `has_commitment`
gate guarantees.

- [ ] **Step 7: Format and commit**

```bash
uv run black godot-generative-agents/backend/cognition.py \
    godot-generative-agents/tests/test_groundhog_loop_778.py
git add godot-generative-agents/backend/cognition.py \
    godot-generative-agents/tests/test_groundhog_loop_778.py
git commit -m "fix(#778): persist the conversation commitment as a locked PLAN memory

The #582 outcome pass already asks the model what the conversation changed,
and 16 of 18 calls in run-20260724-194343-78858a answered plans_changed:true
with a concrete commitment ('Pizza place near campus in about 20 minutes',
'leaving right now'). Every one was discarded: maybe_revise_plan was the only
consumer, and the default plan_mode 'schedule' wires MockPlanner, whose
revise() returns the plan unchanged. Meanwhile the relationship_note half of
the same response persisted at importance 8.0 locked -- so the social half of
#582 survived forever and the intentional half evaporated, and the pair
re-negotiated the same agreement on every cooldown expiry.

The commitment now becomes a PLAN record in the speaker's own stream at
RELATIONSHIP_NOTE_IMPORTANCE, locked. The importance is load-bearing: at
add_plan's 5.0 default the intention is crowded out of the retrieved block by
the 8.0 notes and 7-8 scored talk observations the same conversation mints.

Zero new LLM calls (the commitment is already in the discarded response) and no
prompt change (PLAN bullets already render). Unreachable under the mock brain,
which never converses, so the bake is untouched.

Co-Authored-By: Claude Opus 5 (1M context) <noreply@anthropic.com>"
```

---

## Task 2: Fix C, part 1 — stamp the stop credit when a conversation finishes

**Files:**
- Modify: `godot-generative-agents/backend/cognition.py` — add
  `_credit_stop_for_conversation` next to `_finish_conversation` (around line
  1722), and call it in `_advance_conversation`'s `if ac.convo.happened:` branch
  (around line 1761)
- Test: `godot-generative-agents/tests/test_groundhog_loop_778.py` (append)

**Interfaces:**
- Consumes: nothing from Task 1 (the two fixes are independent).
- Produces: `cognition._credit_stop_for_conversation(char, st) -> bool` — module
  private. `char` is an engine `Character` with `.agent.schedule` and
  `.location`; `st` is that agent's `run_simulation` state dict. Returns whether
  a credit was stamped. Side effects when it returns `True`:
  `st["convo_at_stop"] = True` and `char.set_property("activity", <the stop's
  activity>)`. **Task 3 consumes the `"convo_at_stop"` state key.**

- [ ] **Step 1: Write the failing tests**

Append to `godot-generative-agents/tests/test_groundhog_loop_778.py`:

```python
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
    state = {
        n: {"performing": performing, "path": None, "chat": None} for n in order
    }
    frame = {n: {} for n in order}
    return game, chars, state, frame, order


def test_conversation_at_the_scheduled_place_credits_the_stop():
    game, chars, state, frame, order = _pair_talking_in("Cafe")

    happened = maybe_converse(game, chars, state, frame, 4, {}, order, clock=None)

    assert happened == 1
    for name in order:
        # The credit Task 3's pre-pass spends to advance the schedule.
        assert state[name]["convo_at_stop"] is True
        # ...and the activity is now set, so the frame stops rendering the
        # "spending time" placeholder over a stop that actually happened.
        assert chars[name].get_property("activity") == "reading"


def test_conversation_away_from_the_scheduled_place_does_not_credit():
    """A chat in the Plaza is a deviation, not the scheduled Cafe stop. Same
    place-match rule the pre-pass already uses for on_plan."""
    game, chars, state, frame, order = _pair_talking_in("Plaza")

    happened = maybe_converse(game, chars, state, frame, 4, {}, order, clock=None)

    assert happened == 1  # they did talk...
    for name in order:
        assert "convo_at_stop" not in state[name]  # ...but nothing was credited


def test_unsettled_agent_is_never_credited():
    """`performing` is required -- tested by calling the helper DIRECTLY.

    Going through maybe_converse here would be vacuous: its own pairing already
    requires both agents settled, so no conversation would open and the
    assertion would pass for the wrong reason. The only way an unsettled agent
    reaches the credit is a conversation maybe_react (#370) started mid-walk,
    which pins a WALKING agent that completed no stop -- and without this guard
    its credit would linger in state and be spent on a later, unrelated stop.
    """
    game, chars, state, frame, order = _pair_talking_in("Cafe", performing=False)
    maria, st = chars["Maria Lopez"], state["Maria Lopez"]
    # Same agent, same room as the crediting test above -- only `performing`
    # differs, so this isolates the guard itself.
    assert maria.location.name == maria.agent.schedule.destination

    credited = cognition._credit_stop_for_conversation(maria, st)

    assert credited is False
    assert "convo_at_stop" not in st
    # And the positive control: flip the one flag and the same call credits.
    st["performing"] = True
    assert cognition._credit_stop_for_conversation(maria, st) is True
    assert st["convo_at_stop"] is True


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
    state = {n: {"performing": True, "path": None, "chat": None} for n in order}
    frame = {n: {} for n in order}

    happened = maybe_converse(game, chars, state, frame, 4, {}, order, clock=None)

    assert happened == 0
    for name in order:
        assert "convo_at_stop" not in state[name]
```

- [ ] **Step 2: Run the tests to verify they fail**

```bash
PYTHONPATH=.:godot-generative-agents uv run --no-sync pytest \
    godot-generative-agents/tests/test_groundhog_loop_778.py -v -k credit
```

Expected: `test_conversation_at_the_scheduled_place_credits_the_stop` FAILS with
`KeyError: 'convo_at_stop'`. The three negative tests
(`..._does_not_credit`, `test_unsettled_conversation_does_not_credit`,
`test_mock_brain_credits_nothing`) already PASS — they pin behaviour that must
stay put.

- [ ] **Step 3: Add the helper**

In `godot-generative-agents/backend/cognition.py`, insert this function
immediately after `_finish_conversation` (which ends with `return 1`, around
line 1721) and before `def _advance_conversation(`:

```python
def _credit_stop_for_conversation(char, st) -> bool:
    """A real conversation held AT the agent's scheduled place completes that
    stop (issue #778).

    ``schedule.advance()`` fires from exactly one place -- ``run_simulation``'s
    latch-expiry pre-pass -- and only for an ON-PLAN settle. But a ``talk_to``
    is an instantaneous command that routes through
    ``_settle_after_dead_talk``, which sets ``on_plan = False`` (#689,
    correctly: a *dead* talk completed nothing), and a talk that went on to open
    a REAL conversation took that same path first, so it inherited the same
    flag. The result was that no conversation ever advanced a stop -- not even
    when the conversation *was* the scheduled activity ("sizing up a brand-new
    roommate"), which is how the #778 pair stayed on stop 0 for a whole run.
    This stamps the credit the pre-pass spends, and sets ``activity`` so the
    frame stops rendering the ``"spending time"`` placeholder over a stop that
    actually happened.

    Place-match is the same rule the pre-pass already applies for ``on_plan``:
    standing at the scheduled stop means this completed it. Any real
    conversation there counts, social activity or not -- one authority, no new
    concept.

    ``performing`` is required so a conversation started mid-walk by
    ``maybe_react`` (#370), which pins a *walking* agent, cannot leave a credit
    lying in state to be spent later on an unrelated stop. Every path that
    should credit still does: ``maybe_converse``'s own pairing already requires
    both agents settled.

    Returns whether a credit was stamped (for tests; callers ignore it).
    """
    if not st.get("performing"):
        return False
    schedule = getattr(getattr(char, "agent", None), "schedule", None)
    place = getattr(schedule, "destination", None)
    if not place or char.location is None or char.location.name != place:
        return False
    st["convo_at_stop"] = True
    activity = getattr(schedule, "activity", None)
    if activity:
        char.set_property("activity", activity)
    return True
```

- [ ] **Step 4: Call it from the conversation driver**

In the same file, in `_advance_conversation`, change the real-exchange branch —
currently:

```python
    if ac.convo.happened:
        ac.hold_until = step + len(ac.convo.lines) * line_playback_steps
        state[ac.a]["conversing"] = True
        state[ac.b]["conversing"] = True
        return False, delta
```

to:

```python
    if ac.convo.happened:
        ac.hold_until = step + len(ac.convo.lines) * line_playback_steps
        state[ac.a]["conversing"] = True
        state[ac.b]["conversing"] = True
        # #778: credit the scheduled stop this conversation just completed.
        for nm in (ac.a, ac.b):
            _credit_stop_for_conversation(chars[nm], state[nm])
        return False, delta
```

- [ ] **Step 5: Run the tests to verify they pass**

```bash
PYTHONPATH=.:godot-generative-agents uv run --no-sync pytest \
    godot-generative-agents/tests/test_groundhog_loop_778.py -v
```

Expected: 9 passed (5 from Task 1, 4 new).

- [ ] **Step 6: Run the conversation suites for regressions**

```bash
PYTHONPATH=.:godot-generative-agents uv run --no-sync pytest \
    godot-generative-agents/tests/test_conversation_consequences_582.py \
    godot-generative-agents/tests/test_conversation_multitick_371.py \
    godot-generative-agents/tests/test_conversation_guard.py \
    godot-generative-agents/tests/test_react_interruption_370.py \
    godot-generative-agents/tests/test_universal_verbs_614.py -v
```

Expected: all pass.

- [ ] **Step 7: Format and commit**

```bash
uv run black godot-generative-agents/backend/cognition.py \
    godot-generative-agents/tests/test_groundhog_loop_778.py
git add godot-generative-agents/backend/cognition.py \
    godot-generative-agents/tests/test_groundhog_loop_778.py
git commit -m "fix(#778): stamp a stop credit when a conversation finishes at the scheduled place

schedule.advance() only fires for an on-plan settle, and every talk_to routes
through _settle_after_dead_talk, which sets on_plan=False (#689 -- correct for a
DEAD talk, but a talk that opened a real conversation took the same path and
inherited the same flag). So no conversation ever advanced a stop, even when the
conversation was the scheduled activity: the #778 pair's stop 0 was literally
'sizing up a brand-new roommate' and it never completed.

_credit_stop_for_conversation stamps state['convo_at_stop'] when a real
conversation ends at the agent's scheduled place, reusing the same place-match
rule the pre-pass already applies for on_plan, and sets the activity property so
the frame stops rendering the 'spending time' placeholder over a stop that
actually happened. Requiring `performing` keeps a maybe_react conversation
started mid-walk (#370) from leaving a credit to be spent on a later stop.

The credit is spent in the next commit. Unreachable under the mock brain, which
never converses.

Co-Authored-By: Claude Opus 5 (1M context) <noreply@anthropic.com>"
```

---

## Task 3: Fix C, part 2 — spend the credit at settle expiry

**Files:**
- Modify: `godot-generative-agents/backend/run_simulation.py:316-329` (the
  latch-expiry pre-pass in `step`)
- Test: `godot-generative-agents/tests/test_groundhog_loop_778.py` (append)

**Interfaces:**
- Consumes: the `"convo_at_stop"` state key that Task 2's
  `_credit_stop_for_conversation` sets to `True`. The test block below also
  relies on `build_world` and `attach_agents`, which Task 2 already imported at
  the top of its appended block in the same file — append after it, don't
  re-import.
- Produces: no new names. Behaviour change only — `char.agent.schedule.advance()`
  now also fires when the expiring settle carried a conversation credit, and
  `st["convo_at_stop"]` is removed from the state dict when consumed.

- [ ] **Step 1: Write the failing tests**

Append to `godot-generative-agents/tests/test_groundhog_loop_778.py`:

```python
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
    test_dead_talk_settle_689.py). Deliberately has NO 'convo_at_stop' key --
    the pre-pass must tolerate its absence."""
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
        "on_plan": True,
        "conversing": False,
    }


def _pair_mid_dead_talk_settle():
    """Two co-located mock agents; Diego is latched in a #689 dead-talk settle
    (performing, on_plan False, expiring at step 30) -- exactly the state a
    talk_to leaves behind."""
    personas = [_loop_persona("Diego Cruz"), _loop_persona("Sofia Reyes")]
    game, chars = build_world(None, personas, _LOOP_LOCATIONS)
    attach_agents(chars, personas, llm_client=None)
    order = ["Diego Cruz", "Sofia Reyes"]
    state = {n: _full_state() for n in order}
    state["Diego Cruz"].update(
        {"performing": True, "on_plan": False, "perform_until": 30}
    )
    emoji = {n: "\U0001f9d1" for n in order}
    return game, chars, state, order, emoji


def test_credited_settle_expiry_advances_the_schedule():
    game, chars, state, order, emoji = _pair_mid_dead_talk_settle()
    # The credit Task 2 stamps when the conversation ended at the scheduled place.
    state["Diego Cruz"]["convo_at_stop"] = True

    step(game, chars, state, 30, order=order, world_map=_StubMap(), emoji=emoji)

    assert chars["Diego Cruz"].agent.schedule.stop_index == 1
    # Consumed, so a credit can never outlive the settle that earned it.
    assert "convo_at_stop" not in state["Diego Cruz"]


def test_uncredited_settle_expiry_does_not_advance():
    """Pins today's behaviour: an uncredited dead-talk settle still routes
    through the deviation branch and leaves the pointer alone (#689)."""
    game, chars, state, order, emoji = _pair_mid_dead_talk_settle()

    step(game, chars, state, 30, order=order, world_map=_StubMap(), emoji=emoji)

    assert chars["Diego Cruz"].agent.schedule.stop_index == 0
```

- [ ] **Step 2: Run the tests to verify one fails**

```bash
PYTHONPATH=.:godot-generative-agents uv run --no-sync pytest \
    godot-generative-agents/tests/test_groundhog_loop_778.py -v -k settle_expiry
```

Expected: `test_credited_settle_expiry_advances_the_schedule` FAILS with
`assert 0 == 1` — the credit is stamped but nothing spends it.
`test_uncredited_settle_expiry_does_not_advance` PASSES already.

- [ ] **Step 3: Spend the credit**

In `godot-generative-agents/backend/run_simulation.py`, in `step`'s latch-expiry
block — currently:

```python
        if (
            st["performing"]
            and st["perform_until"] is not None
            and step_idx >= st["perform_until"]
            and not st.get("conversing")
        ):
            if st.get("on_plan", True):
                if char.agent.schedule.advance():
```

change to:

```python
        if (
            st["performing"]
            and st["perform_until"] is not None
            and step_idx >= st["perform_until"]
            and not st.get("conversing")
        ):
            # #778: a real conversation held at the scheduled place counts as
            # having done that stop. cognition._credit_stop_for_conversation
            # stamps the credit; this is where it is spent. Popped
            # unconditionally so a credit can never outlive the settle that
            # earned it. Absent for the mock (which never converses), so
            # `credited` is False and the branch is byte-identical.
            credited = st.pop("convo_at_stop", False)
            if st.get("on_plan", True) or credited:
                if char.agent.schedule.advance():
```

Leave the rest of the block — the `st["performing"] = False` / `stop_since`
re-anchor and the `else:` deviation branch — exactly as it is.

- [ ] **Step 4: Run the tests to verify they pass**

```bash
PYTHONPATH=.:godot-generative-agents uv run --no-sync pytest \
    godot-generative-agents/tests/test_groundhog_loop_778.py -v
```

Expected: 11 passed.

- [ ] **Step 5: Run the loop-behaviour suites for regressions**

```bash
PYTHONPATH=.:godot-generative-agents uv run --no-sync pytest \
    godot-generative-agents/tests/test_dead_talk_settle_689.py \
    godot-generative-agents/tests/test_pacing_authority_581.py \
    godot-generative-agents/tests/test_arena_verbs_615.py \
    godot-generative-agents/tests/test_universal_verbs_614.py \
    godot-generative-agents/tests/test_decide_context.py \
    godot-generative-agents/tests/test_failure_memory_636.py -v
```

Expected: all pass. `test_dead_talk_settle_689.py`'s
`test_empty_talk_settles_briefly_and_bounds_the_retry` is the key one — it
asserts `stop_index == 0` after an uncredited dead talk.

- [ ] **Step 6: Format and commit**

```bash
uv run black godot-generative-agents/backend/run_simulation.py \
    godot-generative-agents/tests/test_groundhog_loop_778.py
git add godot-generative-agents/backend/run_simulation.py \
    godot-generative-agents/tests/test_groundhog_loop_778.py
git commit -m "fix(#778): spend the conversation stop-credit at settle expiry

The latch-expiry pre-pass owns schedule.advance() and gated it on on_plan
alone, so the credit the previous commit stamps had no consumer. It now
advances the pointer when the expiring settle carried a conversation credit,
popping the flag unconditionally so a credit can never outlive the settle that
earned it.

With this, the #778 pair separates: Aiden's Reading Room stop ('sizing up a
brand-new roommate') completes at the conversation that WAS that activity and he
moves on to College Hall, while Chris moves on to Van Pelt -- the physical
separation that distinguished the healthy baseline run.

Byte-identical to the mock bake: the mock never converses, so the key is absent,
st.pop returns False, and the branch resolves exactly as before.

Co-Authored-By: Claude Opus 5 (1M context) <noreply@anthropic.com>"
```

---

## Task 4: Verify byte-identity and the full suite, then update the PR

**Files:**
- No source changes. Verification and PR bookkeeping only.

**Interfaces:**
- Consumes: the finished implementation from Tasks 1-3.
- Produces: nothing consumed by later tasks (this is the last task).

- [ ] **Step 1: Run the byte-identical bake guard**

This is the repo's hardest invariant and the whole reason both fixes are gated
on brain identity. It bakes each scenario under 3 different `PYTHONHASHSEED`
values, so it is slow — allow several minutes.

```bash
PYTHONPATH=.:godot-generative-agents uv run --no-sync pytest \
    godot-generative-agents/tests/test_replay_contract.py -v
```

Expected: all pass, including `test_bake_is_byte_identical`. **If this fails,
stop.** It means a fix reached the mock path; re-check the `performing` guard in
`_credit_stop_for_conversation` and the `st.pop` default in `run_simulation`.

- [ ] **Step 2: Run the full backend suite**

```bash
PYTHONPATH=.:godot-generative-agents uv run --no-sync pytest \
    godot-generative-agents/tests/ -q
```

Expected: all pass, no new failures.

- [ ] **Step 3: Run the engine suite**

```bash
uv run --no-sync pytest tests/ -q
```

Expected: all pass. (Neither fix touches `text_adventure_games/`, so this is a
blast-radius check.)

- [ ] **Step 4: Confirm formatting is clean**

```bash
uv run black --check .
```

Expected: "All done!" with no files reformatted. If it reformats anything,
commit the result.

- [ ] **Step 5: Push and update the draft PR**

```bash
git push
gh pr view 785 --json commits -q '.commits[].messageHeadline'
```

Expected: the push succeeds and the PR lists the design commit plus the three
implementation commits.

- [ ] **Step 6: Update the PR body to describe the shipped change**

The body opens with "Design spec only — no source changes yet. Implementation
lands on this branch once the spec is approved." Replace exactly those two
sentences with the text below, leaving every later section (the diagnosis and
its receipts) untouched — that is the evidence for the change.

```bash
gh pr view 785 --json body -q .body > /tmp/pr785-body.md
```

Open `/tmp/pr785-body.md`, replace the opening paragraph with:

```markdown
Spec **plus implementation**. Fix A persists the commitment as a locked
importance-8.0 `PLAN` memory; Fix C credits a real conversation held at the
agent's scheduled place as completing that stop. New tests in
`godot-generative-agents/tests/test_groundhog_loop_778.py` (11 cases), and
`test_bake_is_byte_identical` passes — the mock bake is unchanged, as both
fixes are unreachable without a conversing brain.
```

Then apply it and retitle:

```bash
gh pr edit 785 --body-file /tmp/pr785-body.md \
  --title "fix(#778): break the groundhog-day conversation loop — commitment→memory + conversation credits the stop"
```

- [ ] **Step 7: Mark the PR ready for review**

Only after Steps 1-3 all passed.

```bash
gh pr ready 785
```

Note: do **not** run `gh pr merge`. Merging is the user's call, and the harness
classifier denies it.

---

## Notes for the implementer

**Why two commits for one conceptually single fix (Tasks 2 and 3).** Task 2's
credit is observable on its own (the state flag and the `activity` property), and
Task 3's spend is testable on its own (stamp the flag by hand, assert the
pointer moves). A reviewer can reject either half independently, which is the
task-boundary test.

**The residual ceiling, deliberately not fixed.** An agent frozen by repeatedly
*blocked* actions rather than by conversation still does not advance its
schedule. The spec's "Rejected: a general stop deadline" section explains why the
general fix was turned down (bake-drift risk, and `stop_since` re-anchors on any
arrival so it would not have fixed the reported agent). If you want that recorded
in code, add a single `ponytail:` comment above the `credited = st.pop(...)`
line naming the ceiling — do not implement the deadline.

**What is explicitly out of scope**, per the approved spec: cooldown escalation
on repeated `talk_to`; the unbounded accumulation of locked 8.0 relationship
notes that crowd the retrieved block (Fix A mitigates this by giving the
intention equal weight, it does not solve it); and any change to `--plan llm`.
