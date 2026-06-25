"""LLM brains for the Smallville cast.

By default the port uses no live LLM: each persona is driven by a
:class:`SmallvilleMockClient` -- a subclass of the engine's
``MockReActClient`` (provider ``"mock"``) that keeps the same client interface
the agent layer calls (``chat`` / ``call_tool``) but swaps the Action-Castle
decision logic for a tiny, deterministic Smallville brain:

* If the agent is not yet at its destination, it decides ``"travel to <dest>"``.
* Once there, it decides ``"perform <activity>"``.

The "where am I now" signal is read straight from the observation the engine
hands the agent (``describe_for`` puts the current location name on the first
line), so the decision genuinely flows through the engine's observe -> decide
seam -- it's just a stand-in for a model, exactly as ``MockReActClient`` is.

A real model can take over those decisions (NEXT-STEPS Phase A): pass an
``llm_client`` to :func:`attach_agents` and it becomes each agent's brain, while a
``SmallvilleMockClient`` stays on ``agent.schedule`` to pace the day. With none, the
mock is both brain and schedule driver and the replay is byte-identical.
"""

import json
from dataclasses import replace

from text_adventure_games.llm_client import MockReActClient
from text_adventure_games.npc import LLMAgent, format_observation_with_memories
from text_adventure_games.usage import UsageLedger, record_call

from . import seed
from .build_world import LOCATION_NAMES
from .planner import LLMPlanner, MockPlanner


class SmallvilleMockClient(MockReActClient):
    """Deterministic mock LLM that walks a persona through a *schedule* of stops.

    A schedule is an ordered list of ``{place, activity, emoji, steps}`` stops
    (built by :func:`build_world._normalize_personas`). The brain only ever looks
    at the *current* stop -- travel until it is standing in ``place``, then perform
    ``activity`` there. The step loop (:func:`run_simulation.simulate`) owns the
    clock: when a stop's ``steps`` have elapsed it calls :meth:`advance` to point
    the brain at the next stop, and the agent walks on. That hand-off is what makes
    each agent keep acting -- and keep accumulating memories -- all run long,
    instead of freezing in a single activity.
    """

    def __init__(self, schedule: list[dict], config=None, ledger=None):
        super().__init__(config, ledger=ledger)
        self.schedule = schedule
        self.stop_index = 0

    @property
    def _stop(self) -> dict:
        """The stop the agent is currently working on."""
        return self.schedule[self.stop_index]

    # The brain reads these off the current stop; advancing the schedule (below)
    # is all it takes to re-point travel/perform at the next place + activity.
    @property
    def destination(self) -> str:
        return self._stop["place"]

    @property
    def activity(self) -> str:
        return self._stop["activity"]

    @property
    def emoji(self) -> str:
        return self._stop["emoji"]

    @property
    def steps(self):
        """Steps to perform the current activity, or ``None`` to stay put."""
        return self._stop["steps"]

    def advance(self) -> bool:
        """Move to the next scheduled stop. Returns ``False`` if none remain."""
        if self.stop_index + 1 < len(self.schedule):
            self.stop_index += 1
            return True
        return False

    def replace_schedule(self, schedule: list[dict]) -> None:
        """Swap in a revised schedule, keeping the current ``stop_index``.

        A revised plan (``planning.replace_tail``) preserves the stops the agent
        has already executed or is performing -- everything up to and including
        ``stop_index`` -- so the index stays valid and only the upcoming tail
        differs. The mock never calls this (its day is static); it exists for the
        revision seam a real planner drives (``smallville_agents.maybe_revise_plan``).
        """
        self.schedule = schedule

    def _current_location(self, observation: str) -> str:
        """describe_for() puts the location name (UPPERCASE) on the first line."""
        for line in (observation or "").splitlines():
            if line.strip():
                return line.strip().lower()
        return ""

    def _choose(self, observation: str) -> str:
        if self._current_location(observation) != self.destination.lower():
            return f"travel to {self.destination}"
        return f"perform {self.activity}"

    # -- the two routes the agent layer may take; both defer to _choose --------

    def _decide(self, messages, max_tokens, temperature):
        """Free-text (chat) route -- the fallback path in LLMAgent.decide."""
        observation = messages[-1]["content"] if messages else ""
        system = messages[0]["content"] if messages else ""
        command = self._choose(observation)
        self.decisions.append({"command": command, "system": system})
        return command

    def call_tool(
        self, messages, tool, max_tokens: int = 256, temperature: float = 0.0
    ):
        """Structured (tool-calling) route -- the path LLMAgent.decide prefers."""
        self.tool_calls.append(
            {
                "messages": messages,
                "tool": tool,
                "max_tokens": max_tokens,
                "temperature": temperature,
            }
        )
        observation = messages[-1]["content"] if messages else ""
        system = messages[0]["content"] if messages else ""
        command = self._choose(observation)
        self.decisions.append({"command": command, "system": system})
        verb, _, rest = command.partition(" ")
        reasoning = (
            f"I'm on my way to {self.destination}."
            if verb == "travel"
            else f"I've arrived, so I'll get on with {self.activity}."
        )
        result = {"reasoning": reasoning, "action": verb, "arguments": rest}
        # Zero-cost usage record (this override doesn't call super().call_tool),
        # so each persona's decision lands in the shared ledger.
        record_call(
            getattr(self, "ledger", None),
            getattr(self, "context", {}),
            "mock",
            "mock",
            None,
            messages,
            json.dumps(result),
        )
        return result


def attach_agents(
    characters: dict,
    personas: list[dict],
    ledger: UsageLedger | None = None,
    embedding_client=None,
    *,
    relationships_csv: str | None = None,
    base_personas_dir: str | None = None,
    planner_client=None,
    llm_client=None,
    clock=None,
    num_steps: int | None = None,
    out_planner_sources: dict | None = None,
    out_plans: dict | None = None,
) -> None:
    """Wire one mock-driven :class:`LLMAgent` onto each persona character.

    ``characters`` maps name -> Character (from :func:`build_world.build_world`);
    ``personas`` is the metadata list (``build_world.PERSONAS``). Pass a shared
    ``ledger`` so every persona's LLM calls accumulate in one place for a
    per-agent cost summary (usage.py); omit it and each client keeps its own.

    Pass an optional ``embedding_client`` (issue #76) to score memory relevance
    semantically; with none, retrieval uses keyword overlap. The mock brain
    decides from location alone, so the replay stays byte-identical either way --
    the embedding only changes *which* memories surface in the (mock-ignored)
    prompt, never the decision.

    Each agent also starts the day with one *plan* memory (issue #75) -- "go to
    <destination> and <activity>" -- seeded from the persona spec. It is the
    agent's own private intention, distinct from its persona (already in the
    system prompt): it gives retrieval something to surface from turn 0 and
    demonstrates the ``PLAN`` memory kind. We do not seed the persona text into
    memory, since the agent layer already injects it into every prompt.

    When ``relationships_csv`` and/or ``base_personas_dir`` point at the upstream
    bootstrap assets, each persona is *also* seeded at t=0 (issue #79): its
    pre-seeded relationships fold into agent memory, and its partial known-places
    tree becomes beliefs in the character's knowledge (see :mod:`seed`). Both are
    optional -- the assets are git-ignored and absent on a fresh checkout, so an
    unset (or missing) path simply skips that seeding and leaves the agent
    byte-identical to before.

    Pass a ``planner_client`` (an engine ``LlmClient``) to plan each day with a
    real model (:class:`~backend.planner.LLMPlanner`, issue #83). With none -- the
    offline default -- each agent gets a :class:`~backend.planner.MockPlanner` that
    replays the authored schedule, so the replay stays byte-identical. The agent
    and its memory are built and seeded *before* the planner runs, so a generative
    planner reasons over the same t=0 memory the agent will. If the model returns
    nothing usable, the agent falls back to the static schedule.

    Pass an ``llm_client`` (NEXT-STEPS Phase A) to make each agent's travel/perform
    *decisions* through a real model: it becomes the agent's brain (``agent.decide``
    -> ``llm_client``), while a deterministic ``SmallvilleMockClient`` stays on
    ``agent.schedule`` to pace the day (``advance``/``steps``/``emoji``). With none,
    that same mock client is *also* the brain -- ``agent.llm_client is
    agent.schedule`` -- so decisions are deterministic and the replay is
    byte-identical."""
    # Load the relationship table once (returns {} if the path is unset/missing).
    relationships = (
        seed.load_relationships(relationships_csv) if relationships_csv else {}
    )
    for spec in personas:
        char = characters[spec["name"]]
        # The schedule driver: a deterministic SmallvilleMockClient that owns the
        # day's pacing (advance()/steps/emoji and the current stop). The decision
        # brain is a real LLM client when one is supplied (Phase A), else the
        # schedule client itself -- so by default agent.llm_client IS agent.schedule
        # (one object), keeping decisions deterministic and the replay byte-identical.
        schedule = SmallvilleMockClient(spec["schedule"], ledger=ledger)
        brain = llm_client if llm_client is not None else schedule
        # Build the agent first so its memory exists and can be seeded before a
        # planner reasons over it. The planner (below) commits the schedule it wants.
        agent = LLMAgent(brain, persona=char.persona, embedding_client=embedding_client)
        # The verbs the structured tool may offer; the mock ignores the enum but a
        # well-formed schema keeps the seam honest for a real brain.
        agent.action_names = ["travel", "perform"]
        char.set_agent(agent)
        # The step loop reads pacing (advance/steps/emoji/stop_index) from
        # agent.schedule, whether or not the brain is a real model.
        agent.schedule = schedule
        # Bind the private memory to this character and seed the day's plan: the
        # whole itinerary, so retrieval has the agent's intentions to surface from
        # turn 0 (and the first stop still mentions destination + activity, which
        # the seeding tests assert on).
        agent.memory.owner = char.name
        itinerary = ", then ".join(
            f"{stop['activity']} at {stop['place']}" for stop in spec["schedule"]
        )
        agent.memory.add_plan(
            f"Plan: go to {spec['destination']} and {spec['activity']}. "
            f"Today's stops: {itinerary}.",
            turn=0,
            importance=5.0,
        )
        # Seed t=0 social structure (memory) and partial world knowledge
        # (knowledge) when the upstream assets are available (issue #79). Done
        # before planning so a generative planner can reason over them.
        seed.seed_relationships(agent.memory, relationships.get(char.name, []))
        if base_personas_dir:
            tree = seed.load_spatial_memory(base_personas_dir, char.name)
            seed.seed_spatial_knowledge(char, tree)

        # Choose the planner: a real LLMPlanner when a model client is supplied,
        # else the deterministic MockPlanner that replays the authored schedule.
        # The mock path is byte-identical -- generate() returns the same stops and
        # replace_schedule re-commits the same list. An LLM that returns nothing
        # usable (empty plan) falls back to the static schedule so the sim is safe.
        if planner_client is not None:
            planner = LLMPlanner(
                planner_client, LOCATION_NAMES, clock=clock, num_steps=num_steps
            )
            plan = planner.generate(persona=spec, memory=agent.memory)
            if plan.stops:
                source = "llm"
            else:
                # The model produced nothing usable -> safe static fallback.
                planner = MockPlanner(spec)
                plan = planner.generate(persona=spec)
                source = "static"
        else:
            planner = MockPlanner(spec)
            plan = planner.generate(persona=spec, memory=agent.memory)
            source = "mock"
        # Record where each agent's plan came from so the caller can report how many
        # were genuinely model-generated vs. fell back (run_simulation.main prints it).
        if out_planner_sources is not None:
            out_planner_sources[spec["name"]] = source
        # Hand back the generated plan (as JSON-safe primitives) so the run can
        # persist it -- the exporter writes personas/<Name>/daily_plan.json.
        if out_plans is not None:
            out_plans[spec["name"]] = plan.to_primitive()
        # Keep the planner + current plan on the agent so the step loop can revise
        # the unstarted tail at a trigger (see maybe_revise_plan), and commit the
        # plan's stops as the schedule the client drives.
        agent.planner = planner
        agent.plan = plan
        agent.schedule.replace_schedule(
            [stop.to_schedule_entry() for stop in plan.stops]
        )


def observe_and_decide(game, char, step: int):
    """Build ``char``'s observation, fold in memory, and ask its agent to decide.

    The Smallville step loop (``run_simulation.simulate``) calls the engine's
    decision seam directly rather than going through ``react_behavior``, so the
    perceive -> retrieve -> augment wiring that the ReAct loop does for free
    (issue #75) is reproduced here, composing the same public memory API:

    1. **Perceive** any visible world events since this agent last looked --
       ``ingest_events`` folds co-located residents' actions (already logged by
       ``parse_command``) into private observations, skipping the agent's own.
    2. **Retrieve** the memories most relevant to the current observation.
    3. **Augment** the observation with that retrieved block (appended *after*
       the environment text, so it never changes what the mock brain reads off
       the first line -- the decision stays deterministic).

    Returns the chosen command string, or ``None``.
    """
    agent = char.agent
    if not agent.memory.owner:
        agent.memory.owner = char.name
    agent.memory.ingest_events(game, char)
    base = game.describe_for(char)
    relevant = agent.memory.retrieve(query=base, turn=step)
    # Stash the retrieved block on the agent so the step loop can surface it in
    # the replay's per-agent card (run_simulation -> exporter). This is a plain
    # attribute on our own LLMAgent instance -- the engine class is untouched.
    agent.last_retrieved = relevant
    observation = format_observation_with_memories(base, relevant)
    return agent.decide(observation)


def maybe_revise_plan(char, trigger, clock=None) -> bool:
    """Offer the agent's planner a chance to re-plan the rest of its day.

    The step loop calls this at a revision trigger (issue #83, design doc §8): an
    action that failed the precondition gate, or the agent running behind its
    schedule. It hands the trigger to ``planner.revise``; if that proposes a
    *changed* plan, it commits the revised tail onto the running schedule and
    stashes the new plan on the agent. Returns ``True`` iff the plan changed.

    **The executed/current stop is never disturbed** (design invariant §8). The
    loop, not the planner, is the authority on how far the agent has got: this
    re-anchors the kept prefix to the client's real ``stop_index`` and grafts only
    the planner's proposed stops *beyond* it, so a planner that mistakenly rewrote
    a past stop cannot desync the schedule from the on-screen replay.

    A no-op planner (today's :class:`~backend.planner.MockPlanner`) returns the
    same plan unchanged, so this commits nothing and the exported replay stays
    byte-identical. That is what lets the revision seam be wired into the loop now,
    ahead of the real ``LLMPlanner`` that will actually rewrite the tail.
    """
    agent = char.agent
    planner = getattr(agent, "planner", None)
    plan = getattr(agent, "plan", None)
    if planner is None or plan is None:
        return False
    proposed = planner.revise(plan, trigger, agent.memory, clock)
    if proposed is plan or proposed == plan:
        return False
    # Re-anchor: keep the stops the agent has executed or is performing (ground
    # truth from the schedule driver), take only the planner's stops past the
    # current one. Pacing lives on agent.schedule -- the mock client that drives
    # advance()/steps even when a real LLM is the decision brain (Phase A).
    after = getattr(agent.schedule, "stop_index", -1)
    guarded = replace(
        proposed,
        stops=plan.stops[: after + 1] + proposed.stops[after + 1 :],
        revision=plan.revision + 1,
    )
    if guarded.stops == plan.stops:
        return False  # only higher-level reasoning moved; schedule is unchanged
    agent.plan = guarded
    agent.schedule.replace_schedule(
        [stop.to_schedule_entry() for stop in guarded.stops]
    )
    return True


def memories_for_frame(records) -> list[dict]:
    """Format retrieved memory records as UI-ready dicts for a replay frame.

    ``observe_and_decide`` stashes the records it retrieved on ``agent`` as
    ``last_retrieved``; this turns them into the small JSON shape the frontend's
    agent card renders, so the viewer can watch which memories surfaced for each
    decision:

    * ``kind`` -- observation / plan / reflection (the card colour-codes it),
    * ``importance`` -- the 1-10 poignancy, kept quiet next to the text,
    * ``text`` -- the memory itself,
    * ``created_turn`` -- the step the memory was formed; the exporter turns this
      into a wall-clock ``time`` so the card can show *when* it entered the stream.

    Returns ``[]`` for an empty/None list.
    """
    return [
        {
            "kind": r.kind.value,
            "importance": round(float(r.importance), 1),
            "text": r.text,
            "created_turn": r.created_turn,
        }
        for r in (records or [])
    ]


def memory_stream_for_persona(agent) -> list[dict]:
    """Format an agent's *entire* memory stream as UI-ready dicts.

    Same shape as :func:`memories_for_frame`, but over ``agent.memory.records``
    -- every memory the agent has formed, not just the handful retrieved for one
    decision. The exporter writes this per persona so the State Details panel can
    show the full stream alongside a step's retrieved set (the same records the
    card surfaces are a subset of these). Returns ``[]`` if the agent has no
    memory bound.
    """
    memory = getattr(agent, "memory", None)
    records = memory.records if memory is not None else []
    return memories_for_frame(records)


def remember_outcome(char, command: str, step: int) -> None:
    """Record ``char``'s own successful action as a first-person memory.

    Only the *actor's own* memory is added here. The :class:`GameEvent` that
    other, co-located residents perceive was already logged by
    ``parser.parse_command`` on success -- ``ingest_events`` deliberately skips
    an agent's own actions, so adding a private first-person record is what
    keeps the actor's own history from being lost (and avoids double-logging).

    (The logical move happens the instant ``travel`` resolves, while the sprite
    is still walking the tile path -- memory and the on-screen animation run on
    different clocks. Harmless: memory never renders to the frontend here.)
    """
    agent = char.agent
    verb, _, rest = command.partition(" ")
    if verb == "travel":
        text = f"I traveled to {char.location.name}."
        importance = 2.0
    elif verb == "perform":
        activity = char.get_property("activity") or rest.strip()
        text = f"I am {activity}."
        importance = 2.0
    else:
        text = f'I did "{command}".'
        importance = 1.0
    agent.memory.add_observation(text, turn=step, importance=importance)
