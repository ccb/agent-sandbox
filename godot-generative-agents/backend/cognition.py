"""LLM brains for the generative-agents cast.

By default the sim uses no live LLM: each persona is driven by a
:class:`ScheduleMockClient` -- a subclass of the engine's
``MockReActClient`` (provider ``"mock"``) that keeps the same client interface
the agent layer calls (``chat`` / ``call_tool``) but swaps the Action-Castle
decision logic for a tiny, deterministic schedule-following brain:

* If the agent is not yet at its destination, it decides ``"travel to <dest>"``.
* Once there, it decides ``"perform <activity>"``.

The "where am I now" signal is read straight from the observation the engine
hands the agent (``describe_for`` puts the current location name on the first
line), so the decision genuinely flows through the engine's observe -> decide
seam -- it's just a stand-in for a model, exactly as ``MockReActClient`` is.

A real model can take over those decisions: pass an ``llm_client`` to
:func:`attach_agents` and it becomes each agent's brain, while a
``ScheduleMockClient`` stays on ``agent.schedule`` to pace the day. With none, the
mock is both brain and schedule driver and the replay is byte-identical.
"""

import json
import time
from dataclasses import replace

from text_adventure_games import conversation as convo
from text_adventure_games.llm_client import MockReActClient, run_tool_loop
from text_adventure_games.planning import RevisionTrigger
from text_adventure_games.npc import (
    COGNITION_BUDGET,
    LLMAgent,
    cognition_toolset,
    command_from_tool_call,
    format_observation_with_memories,
    maybe_reflect,
    tools_for,
)
from text_adventure_games.reflection import LLMReflector
from text_adventure_games.usage import UsageLedger, record_call

# Conversation pacing (issue #86). A settled pair talks at most once per this many
# steps, so co-located residents don't re-converse every tick of a long stay; and
# a single meeting is capped at this many lines.
CONVERSATION_COOLDOWN_STEPS = 90
CONVERSATION_MAX_EXCHANGES = 6

# Conversation consequences (issue #582). A backend-local revision reason -- the
# engine's RevisionTrigger.reason is a plain string (planning.py), so an
# agreement reached in dialogue needs no engine change to reach a planner.
CONVERSATION = "conversation"

# The relationship note a notable meeting leaves behind is momentous on the 1-10
# poignancy scale (same weight as the #300 "I got sick" signal), so it survives
# retrieval ranking and pushes the agent toward reflection.
RELATIONSHIP_NOTE_IMPORTANCE = 8.0

# The post-conversation outcome tool (#582): one structured call per participant
# after a meeting. plans_changed gates a plan revision; the two strings are
# optional (small talk fills neither). Normalized {name, description, parameters}
# -- the shape llm_client.call_tool translates per provider, like the planner's
# tools.
CONVERSATION_OUTCOME_TOOL = {
    "name": "conversation_outcome",
    "description": (
        "Record the outcome of the conversation you just had: whether it "
        "changed your plans for the rest of the day, and anything about the "
        "other person worth remembering."
    ),
    "parameters": {
        "type": "object",
        "properties": {
            "plans_changed": {
                "type": "boolean",
                "description": (
                    "True if this conversation changed what you will do for the "
                    "rest of the day (e.g. an agreement to meet somewhere)."
                ),
            },
            "commitment": {
                "type": "string",
                "description": (
                    "If plans changed, the concrete thing you agreed to -- where "
                    "and when. Omit if nothing changed."
                ),
            },
            "relationship_note": {
                "type": "string",
                "description": (
                    "A durable note about the other person worth remembering, or "
                    "omit if the exchange was just small talk."
                ),
            },
        },
        "required": ["plans_changed"],
    },
}

from . import seed
from .actions import Travel
from .planner import LLMPlanner, MockPlanner
from .prompt_templates import render

# How far a resident perceives, in map tiles (issue #82). 8 matches the upstream
# Generative Agents ``vision_r`` cognition knob (their per-agent scratch.json).
# Paired with a TiledGame (build_world(world_map=...)), this turns map proximity
# into co-presence: residents within 8 tiles perceive each other and nearby
# objects. A persona may override it with a ``vision_r`` key in the world YAML.
DEFAULT_VISION_R = 8

# Per-action decide (issue #485): the cap on how many location names travel's
# ``destination`` enum may list. Mirrors the engine's discipline for scope
# enums (``npc._MAX_SCOPE_ENUM``): past the cap the enum is DROPPED, never
# truncated -- truncating would make a valid venue unnameable -- and the slot
# degrades to free text. The Penn campus has 14 named locations, comfortably
# under it; a world with more venues should raise this at the call site (tool
# definitions count against context, so don't raise it casually) rather than
# silently lose the enum.
DECIDE_MAX_ENUM = 20


def first_line_location(observation: str) -> str:
    """The current location as the mock/scripted brains read it: ``describe_for``
    puts the location name (UPPERCASE) on the first non-empty line; return it
    lowercased for comparison. Shared by
    :meth:`ScheduleMockClient._current_location` and the Penn scripted brain
    (issue #563) so the first-line convention lives in one place and can't drift
    if ``describe_for``'s format changes."""
    for line in (observation or "").splitlines():
        if line.strip():
            return line.strip().lower()
    return ""


class ScheduleMockClient(MockReActClient):
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

    # Artificial per-decision latency in seconds (#366): lets an offline run
    # feel like a real provider -- serve_penn's --mock-latency stamps it, the
    # parallel-decide tests assert wall-clock against it, and it drives the
    # #372 "thinking" stall demo. 0.0 = today's instant mock, byte-identical.
    latency_s = 0.0

    def __init__(self, schedule: list[dict], config=None, ledger=None):
        super().__init__(config, ledger=ledger)
        self.schedule = schedule
        self.stop_index = 0
        # How many of the current stop's authored commands have been issued.
        self._commands_used = 0

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

    @property
    def furniture(self):
        """Furniture the agent should occupy at the current stop, or ``None``
        (#559). Read at travel time by run_simulation to bias walk_path."""
        return self._stop.get("furniture")

    def advance(self) -> bool:
        """Move to the next scheduled stop. Returns ``False`` if none remain."""
        if self.stop_index + 1 < len(self.schedule):
            self.stop_index += 1
            self._commands_used = 0
            return True
        return False

    def replace_schedule(self, schedule: list[dict]) -> None:
        """Swap in a revised schedule, keeping the current ``stop_index``.

        A revised plan (``planning.replace_tail``) preserves the stops the agent
        has already executed or is performing -- everything up to and including
        ``stop_index`` -- so the index stays valid and only the upcoming tail
        differs. The mock never calls this (its day is static); it exists for the
        revision seam a real planner drives (``cognition.maybe_revise_plan``).

        Carrying over authored ``commands`` (#300) and ``furniture`` (#559): the
        engine's ``planning.Stop`` has neither field, so any schedule that has
        been through a ``Stop`` round-trip (``to_schedule_entry`` /
        ``from_schedule_entry``, e.g. every ``MockPlanner``/``LLMPlanner`` plan --
        which ``attach_agents`` commits for every agent, mock included) silently
        drops both the per-stop commands and the per-stop furniture hint an author
        put in ``world_data.yaml`` / persona schedule.
        Rather than teach the engine's ``Stop`` about these backend-only fields
        (upstreaming tracked in #464), we patch the loss back in here: for each
        incoming entry that lines up positionally with the *current* schedule's
        entry at the same index (same ``place`` and ``activity``) and itself
        carries no ``commands``/``furniture``, we carry over the current stop's
        value. An entry that differs in ``place`` or ``activity`` is a genuinely
        revised/new stop (e.g. a future LLM planner's tail-replace) and gets no
        carry-over -- it has no authored value to inherit. This does not touch
        ``_commands_used``: the current stop (index
        ``stop_index``), if it matched, is the *same* authored stop the agent may
        already be partway through, so its progress must survive the swap.
        """
        current = self.schedule
        patched = []
        for i, entry in enumerate(schedule):
            # Carry backend-only per-stop fields the engine's Stop round-trip
            # drops (#300 `commands`, #559 `furniture`) back onto a positionally
            # matching entry -- same `place` and `activity`, i.e. the same
            # authored stop, just stripped by the round-trip -- that lost them.
            # An entry that still carries the field keeps its own; a genuinely
            # revised/new stop (different place/activity) inherits nothing.
            if i < len(current):
                prior = current[i]
                matches = prior.get("place") == entry.get("place") and prior.get(
                    "activity"
                ) == entry.get("activity")
                if matches and not entry.get("commands") and prior.get("commands"):
                    entry = {**entry, "commands": list(prior["commands"])}
                if matches and not entry.get("furniture") and prior.get("furniture"):
                    entry = {**entry, "furniture": prior["furniture"]}
            patched.append(entry)
        self.schedule = patched

    def _current_location(self, observation: str) -> str:
        return first_line_location(observation)

    def _choose(self, observation: str) -> str:
        if self.latency_s:
            time.sleep(self.latency_s)  # the single funnel both routes share
        if self._current_location(observation) != self.destination.lower():
            return f"travel to {self.destination}"
        queued = self._stop.get("commands") or []
        if self._commands_used < len(queued):
            command = queued[self._commands_used]
            self._commands_used += 1
            return command
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
        if verb == "travel":
            reasoning = f"I'm on my way to {self.destination}."
        elif verb == "perform":
            reasoning = f"I've arrived, so I'll get on with {self.activity}."
        else:
            reasoning = f"While I'm here: {command}."
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
    vision_r: int = DEFAULT_VISION_R,
    planner_client=None,
    location_names=None,
    reflector_client=None,
    llm_client=None,
    clock=None,
    num_steps: int | None = None,
    out_planner_sources: dict | None = None,
    out_plans: dict | None = None,
    extra_action_names: list[str] | None = None,
    cognition_tools: bool = False,
) -> None:
    """Wire one mock-driven :class:`LLMAgent` onto each persona character.

    ``characters`` maps name -> Character (from :func:`build_world.build_world`);
    ``personas`` is the normalized metadata list (from
    :func:`build_world.load_world_data`). Pass a shared
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
    nothing usable, the agent falls back to the static schedule. The planner
    validates its stops against ``location_names`` (the world's valid places);
    pass the set explicitly, or leave it ``None`` to derive it from the personas'
    homes + scheduled places.

    Pass an ``llm_client`` (NEXT-STEPS Phase A) to make each agent's travel/perform
    *decisions* through a real model: it becomes the agent's brain (``agent.decide``
    -> ``llm_client``), while a deterministic ``ScheduleMockClient`` stays on
    ``agent.schedule`` to pace the day (``advance``/``steps``/``emoji``). With none,
    that same mock client is *also* the brain -- ``agent.llm_client is
    agent.schedule`` -- so decisions are deterministic and the replay is
    byte-identical.

    Pass a ``reflector_client`` (an engine ``LlmClient``) to give each agent an
    :class:`~text_adventure_games.reflection.LLMReflector` for periodic memory
    synthesis (issue #84): the step loop runs a reflection pass once an agent's
    accumulated memory importance crosses its threshold, turning recent memories
    into higher-level thoughts written back into the stream. With none -- the
    offline default -- no reflector is wired on, so reflection never fires and the
    replay stays byte-identical. ``run_simulation`` supplies one only for a real
    (non-mock) provider, the same gate as the brain and planner.

    Pass ``extra_action_names`` (spec §3, #300) to widen every attached agent's
    ``action_names`` beyond the authored-command verbs discovered on its own
    schedule -- e.g. Penn's ``["get", "drink", "activate", "deactivate"]`` -- so a
    *real* brain (a closed tool-calling enum) can choose those verbs even for a
    persona whose schedule never authors a matching ``commands:`` entry. With
    none -- the default, and what every Smallville caller still passes -- the verb
    set is derived from authored commands alone, unchanged from before.

    Pass ``cognition_tools=True`` (issue #512, mirroring the engine's
    ``AgentConfig.cognition_tools``, #358) to stamp the engine flag on every
    agent: a real supplied brain may then ``recall`` / ``query_knowledge`` /
    ``read_plan`` before picking its action (:func:`decide_with_action_tools`)
    and before each dialogue line (the engine's converse path picks the flag up
    with no further wiring here). The default ``False`` -- and the mock brain,
    which never reaches either tool loop -- keeps the run byte-identical."""
    # Load the relationship table once (returns {} if the path is unset/missing).
    relationships = (
        seed.load_relationships(relationships_csv) if relationships_csv else {}
    )
    for spec in personas:
        char = characters[spec["name"]]
        # The schedule driver: a deterministic ScheduleMockClient that owns the
        # day's pacing (advance()/steps/emoji and the current stop). The decision
        # brain is a real LLM client when one is supplied, else the schedule client
        # itself -- so by default agent.llm_client IS agent.schedule (one object),
        # keeping decisions deterministic and the replay byte-identical.
        schedule = ScheduleMockClient(spec["schedule"], ledger=ledger)
        brain = llm_client if llm_client is not None else schedule
        # Build the agent first so its memory exists and can be seeded before a
        # planner reasons over it. The planner (below) commits the schedule it wants.
        agent = LLMAgent(brain, persona=char.persona, embedding_client=embedding_client)
        # Cognition tools (issue #512): the engine flag both the decide seam
        # below and the engine's converse path read. Stamped (not passed to the
        # constructor) to match how the rest of this function decorates the
        # agent (schedule, planner, plan).
        if cognition_tools:
            agent.cognition_tools = True
        # Periodic reflection (issue #84): an LLMReflector when a real client is
        # supplied, else None -- so the offline mock run never reflects and the
        # replay stays byte-identical. The threshold rides on AgentConfig's default.
        if reflector_client is not None:
            agent.reflector = LLMReflector(reflector_client)
        # The verbs the structured tool may offer; the mock ignores the enum but a
        # well-formed schema keeps the seam honest for a real brain. Order:
        # the base travel/perform, then any caller-supplied extra_action_names
        # (spec §3, #300 -- e.g. Penn's device/drink verbs, so a real brain's
        # closed enum can choose them even without an authored commands: stop),
        # then whatever authored-command verbs remain (sorted), deduplicating
        # while preserving that order.
        authored_verbs = sorted(
            {
                verb
                for stop in spec["schedule"]
                for cmd in stop.get("commands") or []
                # "wait" is an idle spacer deliberately excluded from
                # PENN_ACTION_VERBS; never promote it to a real-brain tool -- a
                # Wait schema on every decide is recurring token spend and
                # invites the model to sit idle.
                if (verb := cmd.split(" ", 1)[0]) != "wait"
            }
        )
        ordered = ["travel", "perform", *(extra_action_names or []), *authored_verbs]
        seen: set[str] = set()
        agent.action_names = [v for v in ordered if not (v in seen or seen.add(v))]
        char.set_agent(agent)
        # The step loop reads pacing (advance/steps/emoji/stop_index) from
        # agent.schedule, whether or not the brain is a real model.
        agent.schedule = schedule
        # Scripted brain (#563): a distinct client that follows the authored
        # schedule reads it from here. Guarded so real clients / None / the
        # default mock path are untouched (byte-identical).
        register = getattr(llm_client, "register_schedule", None)
        if callable(register):
            register(char.name, schedule)
        # How far this resident perceives, in tiles (issue #82). The TiledGame's
        # perceivable_locations reads this to fold nearby residents/objects into
        # memory; with the vanilla Game (no world_map) it just means the room.
        char.vision_r = spec.get("vision_r", vision_r)
        # Bind the private memory to this character and seed the day's plan: the
        # whole itinerary, so retrieval has the agent's intentions to surface from
        # turn 0 (and the first stop still mentions destination + activity, which
        # the seeding tests assert on).
        agent.memory.owner = char.name
        itinerary = ", then ".join(
            f"{stop['activity']} at {stop['place']}" for stop in spec["schedule"]
        )
        agent.memory.add_plan(
            render(
                "plan_memory",
                destination=spec["destination"],
                activity=spec["activity"],
                itinerary=itinerary,
            ),
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
            plan_locations = location_names or frozenset(
                {p["home"] for p in personas}
                | {stop["place"] for p in personas for stop in p["schedule"]}
            )
            planner = LLMPlanner(
                planner_client, plan_locations, clock=clock, num_steps=num_steps
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
        # were genuinely model-generated vs. fell back.
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


def _use_action_tools(agent) -> bool:
    """True when a decide tick should take the per-action tool path (#485).

    Two conditions, both required:

    * **A real brain was supplied.** :func:`attach_agents` wires ``brain =
      llm_client if llm_client is not None else schedule`` -- so with no
      supplied client the brain IS the pacing :class:`ScheduleMockClient` (the
      very same object). Checking identity against ``agent.schedule`` is
      therefore exactly "was an ``llm_client`` passed", the same real-client
      gate ``serve_penn.resolve_llm`` applies to the reflector. A naive
      ``hasattr(brain, "call_tools")`` alone would NOT do: ScheduleMockClient
      *inherits* ``call_tools`` from ``MockReActClient`` but only scripts the
      singular ``call_tool``, so the default offline run would wander onto a
      route its brain doesn't drive -- and the mock replay must stay
      byte-identical.
    * **The brain speaks the plural route.** A chat-only client or a legacy
      callable keeps the classic ``agent.decide()`` path unchanged.
    """
    brain = getattr(agent, "llm_client", None)
    return (
        brain is not None
        and brain is not getattr(agent, "schedule", None)
        and hasattr(brain, "call_tools")
    )


def action_tools_for(game, char, max_enum: int = DECIDE_MAX_ENUM):
    """One typed tool per verb this agent may choose, scoped to *char* (#485).

    The engine derives the tools (``npc.tools_for``, issue #356): each verb in
    the agent's ``action_names`` becomes its own tool, typed by the action's
    ``ARGUMENTS_SCHEMA``. One port-specific enrichment on top: the engine's
    scope kinds (item / character / direction) can't describe travel's "any
    named location in town" -- the campus is wired hub-and-spoke purely so the
    engine discovers every location, not as a compass maze -- so the enum of
    destinations is filled in here, from the same ``game.locations`` the
    :class:`~backend.actions.Travel` action matches a command against. The
    menu and the precondition gate can therefore never disagree about which
    venues exist.
    """
    agent = char.agent
    tools = tools_for(
        game.parser, actor=char, names=agent.action_names, max_enum=max_enum
    )
    destinations = sorted(game.locations)
    if len(destinations) > max_enum:
        return tools  # too many venues to enumerate: the slot stays free text
    for tool in tools:
        if tool["name"] == Travel.ACTION_NAME:
            prop = tool["parameters"]["properties"].get("destination")
            if prop is not None:
                prop["enum"] = destinations
    return tools


def _take_pacing_args(agent, args: dict, *, stash: bool = True) -> None:
    """Pop the #581 pacing meta-args off a per-action tool call and (when
    ``stash``) stash them on the agent, so they drive pacing but never reach
    ``command_from_tool_call`` (``npc.command_from_args`` skips absent slots, so
    a popped key is dropped from the routed command). Light validation: a
    non-positive/garbage duration or a blank emoji is ignored (left as the None
    the caller reset).

    ``stash=False`` still pops both keys (never leak them into the command) but
    ignores them -- for a verb that did *not* advertise the slots. Only ``perform``
    (and any future duration-bearing #446 verb whose ``ARGUMENTS_SCHEMA`` opts in)
    advertises them; a model that hallucinates ``duration_minutes`` onto a #300
    one-tick verb (get/drink/activate) must not make that verb settle, so the
    caller passes ``stash`` = "this tool advertised the pacing slots"."""
    minutes = args.pop("duration_minutes", None)
    emoji = args.pop("emoji", None)
    if not stash:
        return
    if (
        isinstance(minutes, (int, float))
        and not isinstance(minutes, bool)
        and minutes > 0
    ):
        agent.last_duration_minutes = minutes
    if isinstance(emoji, str) and emoji.strip():
        agent.last_emoji = emoji.strip()


def decide_with_action_tools(game, char, observation: str) -> str | None:
    """One per-action tool-calling round: the #485 decide path for a real brain.

    Offers the per-verb tools with ``tool_choice="any"`` (the model must pick a
    verb) and reassembles the returned call into a command string via the
    engine's ``command_from_tool_call`` -- which then re-enters the parser's
    precondition gate in the step loop exactly as a free-text decision would.
    Deliberately a single round (no ``run_tool_loop`` retry): the step loop
    already owns failure handling (plan revision on a gate miss), and one
    request per decide keeps the live tick's call count, latency, and ledger
    attribution (one ``role: decide`` row per persona per tick) identical to
    the ``choose_action`` path this replaces.

    With ``agent.cognition_tools`` on (issue #512; stamped by
    :func:`attach_agents`, mirroring the engine's #358 flag), the single round
    becomes a bounded ``run_tool_loop``: the engine's ``recall`` /
    ``query_knowledge`` / ``read_plan`` are offered alongside the action tools,
    so the brain can consult its own memory / beliefs / plan *before* picking a
    verb instead of only seeing the engine-pushed retrieve-on-observation paste
    (which stays -- a deliberate double-pay, documented on the engine flag).
    The first action-tool call is terminal and takes the same
    ``command_from_tool_call`` route below, so the precondition gate is never
    bypassed; each retrieval is an extra ``role: decide`` request inside this
    tick (up to ``COGNITION_BUDGET`` of them, refused past the budget), billed
    to the same ambient attribution the step loop stamped.

    Returns the command string, or ``None`` when the model declined or errored
    -- the caller then falls back to ``agent.decide()``.
    """
    agent = char.agent
    # Same reset contract as LLMAgent.decide(): reasoning is per-call. This
    # resets the engine's own turns-based `last_duration`, distinct from the
    # port's `last_duration_minutes`, which `_take_pacing_args` now populates
    # from the `perform` tool's optional `duration_minutes` slot (#581).
    agent.last_reasoning = None
    agent.last_duration = None
    messages = [
        # The same system message LLMAgent's structured path sends (persona +
        # goals, no free-text format instruction -- the tool schema is the
        # output contract), so swapping tool shapes never changes the prompt.
        {"role": "system", "content": agent._structured_system_message()},
        {"role": "user", "content": observation},
    ]
    tools = action_tools_for(game, char)
    # Which verbs opted into brain-authoritative pacing (#581): only these get
    # a model duration/emoji stashed. Any other tool's stray pacing args are
    # popped (never leak into the command) but ignored -- verb-agnostic, so a
    # future #446 verb that adds the slots to its ARGUMENTS_SCHEMA is included
    # automatically, while a #300 one-tick verb stays one-tick.
    pacing_tools = {
        t["name"]
        for t in tools
        if "duration_minutes" in t["parameters"]["properties"]
        or "emoji" in t["parameters"]["properties"]
    }
    if getattr(agent, "cognition_tools", False):
        cog_tools, cognition_execute = cognition_toolset(
            agent,
            knowledge=getattr(char, "knowledge", None),
            turn=getattr(game, "turn", 0),
            trace=lambda text: game.parser.agent_reasoning(char.name, text),
        )
        # A registered action verb keeps priority over a same-named cognition
        # tool (duplicate tool names would be rejected by real providers) --
        # the same collision filter as the engine's _decide_and_route_loop.
        offered = {t["name"] for t in tools}
        cog_tools = [t for t in cog_tools if t["name"] not in offered]
        if cog_tools:
            cog_names = {t["name"] for t in cog_tools}
            state = {"command": None}

            def execute(name, args):
                if name in cog_names:
                    # A cognition call continues the loop (done=False); the
                    # toolset's execute owns the result, including the
                    # over-budget is_error refusal.
                    return cognition_execute(name, args)
                if state["command"] is None:
                    # The first action pick is the decision (providers list
                    # calls in the order the model made them).
                    picked = dict(args or {})
                    agent.last_reasoning = (
                        picked.get("reasoning") or ""
                    ).strip() or None
                    # #581: pop before routing; stash only if this verb opted in.
                    _take_pacing_args(agent, picked, stash=name in pacing_tools)
                    state["command"] = command_from_tool_call(name, picked, game.parser)
                # Terminal: the step loop owns routing + failure handling,
                # exactly as on the single-round path below.
                return ("Done.", False, True)

            run_tool_loop(
                agent.llm_client,
                messages,
                tools + cog_tools,
                execute,
                max_rounds=1 + COGNITION_BUDGET,
                tool_choice="any",
                max_tokens=agent.max_tokens,
                temperature=agent.temperature,
            )
            return state["command"] or None
    result = agent.llm_client.call_tools(
        messages,
        tools,
        tool_choice="any",
        max_tokens=agent.max_tokens,
        temperature=agent.temperature,
    )
    if result is None or not result.tool_calls:
        return None
    # One action per tick: if the model called several tools, the first is its
    # primary pick (providers list calls in the order the model made them).
    call = result.tool_calls[0]
    args = dict(call.get("arguments") or {})
    agent.last_reasoning = (args.get("reasoning") or "").strip() or None
    # #581: pop pacing meta-args before routing; stash only if this verb opted in.
    _take_pacing_args(agent, args, stash=call["name"] in pacing_tools)
    command = command_from_tool_call(call["name"], args, game.parser)
    return command or None


def decide_context_block(agent, step: int, clock, stop_since: int = 0) -> str:
    """Render the always-on decide context (issue #580), or ``""``.

    Sim time of day, the plan's current stop, and how long the agent has been
    on it (``stop_since`` is the step the stop began -- stamped when the
    schedule advances and re-anchored on arrival, so once the agent is at the
    place ``elapsed`` counts time *at* the stop, commensurate with the planned
    minutes) -- the always-relevant slice a live brain needs on every decision
    without spending a ``read_plan`` tool round. Needs a clock (the bake and
    the offline tests thread none, so their prompts are unchanged) and a
    schedule (every attach_agents persona has one; a bare engine agent
    yields "").
    """
    schedule = getattr(agent, "schedule", None)
    if clock is None or schedule is None:
        return ""
    steps = schedule.steps
    return render(
        "decide_context",
        time=clock.time_at(step).strftime("%A %I:%M %p"),
        place=schedule.destination,
        activity=schedule.activity,
        minutes=clock.minutes_for_steps(steps) if steps is not None else None,
        elapsed=clock.minutes_for_steps(max(0, step - stop_since)),
    )


def observe_and_decide(
    game, char, step: int, retrieval=None, *, clock=None, stop_since=0
):
    """Build ``char``'s observation, fold in memory, and ask its agent to decide.

    The step loop (``run_simulation.simulate``) calls the engine's
    decision seam directly rather than going through ``react_behavior``, so the
    perceive -> retrieve -> augment wiring that the ReAct loop does for free
    (issue #75) is reproduced here, composing the same public memory API:

    1. **Perceive** the nearby world since this agent last looked --
       ``perceive`` folds visible residents' actions (already logged by
       ``parse_command``) into private observations, skipping the agent's own,
       plus -- within the character's vision radius (issue #80) -- the agents
       and objects in view. At the default ``vision_r == 0`` this is just the
       co-located event perception the port had before, so the replay is
       unchanged until personas opt into a wider radius.
    2. **Retrieve** the memories most relevant to the current observation.
    3. **Augment** the observation with that retrieved block (appended *after*
       the environment text, so it never changes what the mock brain reads off
       the first line -- the decision stays deterministic).
    4. **Contextualize** (#580): when the loop threads a ``clock``, append the
       decide-context block -- sim time, current plan stop, elapsed -- after
       the environment text (never read by the deterministic mock).

    Pass a ``retrieval`` (:class:`sim_config.RetrievalConfig`) to tune the
    retrieval scoring (weights / decay / how many memories surface); ``None``
    uses :meth:`AgentMemory.retrieve`'s defaults -- identical to today.

    The decide itself takes one of two routes: a real supplied brain gets the
    per-action typed tools (:func:`decide_with_action_tools`, issue #485),
    while the default mock -- and any fallback -- goes through the classic
    ``agent.decide()`` seam. Returns the chosen command string, or ``None``.
    """
    agent = char.agent
    # Brain-authoritative pacing (#581): reset the per-decision pacing hints
    # here -- the single entry both the action-tools path and the classic
    # decide() fallback pass through -- so a value from an earlier tick can
    # never leak into this one. decide_with_action_tools sets them below when
    # the model fills the optional slots; the mock leaves them None.
    agent.last_duration_minutes = None
    agent.last_emoji = None
    if not agent.memory.owner:
        agent.memory.owner = char.name
    agent.memory.perceive(game, char)
    base = game.describe_for(char)
    if retrieval is None:
        relevant = agent.memory.retrieve(query=base, turn=step)
    else:
        relevant = agent.memory.retrieve(
            query=base,
            turn=step,
            max_records=retrieval.max_records,
            token_budget=retrieval.token_budget,
            decay=retrieval.recency_decay,
            alpha_recency=retrieval.alpha_recency,
            alpha_importance=retrieval.alpha_importance,
            alpha_relevance=retrieval.alpha_relevance,
        )
    # Stash the retrieved block on the agent so the step loop can surface it in
    # the replay's per-agent card (run_simulation -> exporter). This is a plain
    # attribute on our own LLMAgent instance -- the engine class is untouched.
    agent.last_retrieved = relevant
    # Decide-context block (#580): sim time + current stop + elapsed. Appended
    # AFTER the environment text (the mock brain reads only the first line)
    # and AFTER the retrieve above ran on the plain `base` -- the block must
    # never shift which memories surface, because frames embed that list.
    context = decide_context_block(agent, step, clock, stop_since)
    if context:
        base = f"{base}\n\n{context}"
    observation = format_observation_with_memories(base, relevant)
    # Per-action tools (issue #485): a real supplied brain picks between typed
    # per-verb tools -- travel's destination an enum of real venue names --
    # instead of filling the single free-text choose_action schema. A decline
    # (or an API error) falls back to the classic decide() path below, so an
    # outage degrades exactly as before. The default mock run never enters
    # this branch (see _use_action_tools) and stays byte-identical.
    if _use_action_tools(agent):
        command = decide_with_action_tools(game, char, observation)
        if command:
            return command
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


def kind_counts_for_persona(agent) -> dict[str, int]:
    """Tally an agent's memories by kind (observation / plan / reflection / chat).

    A cheap activity summary for the ``/agents`` roster (#344): the per-kind
    counts over the *same* records :func:`memory_stream_for_persona` returns, so
    a roster tally and the full stream a client then fetches can never disagree.
    Returns ``{}`` for an agent with no memory bound.
    """
    counts: dict[str, int] = {}
    for entry in memory_stream_for_persona(agent):
        counts[entry["kind"]] = counts.get(entry["kind"], 0) + 1
    return counts


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

    # The #300 water arc marks the sicken/recover *transition* with one-shot
    # properties set inside DrinkPenn.apply_effects. Consume them by their
    # presence, NOT by the command's first-token verb: a comma ActionSequence
    # ("get ..., drink ...") parses as verb "get", and free brain text ("have a
    # drink of ...") as "have", so gating on verb == "drink" would leave the
    # marker set to leak into a later drink -- and the boiled-water drink would
    # then record BOTH sickened and recovered, inverting the arc's payoff. A
    # marker being set means DrinkPenn just ran and this outcome is the drink to
    # remember (the sick=8.0 signal the #299 experiment retrieves, or its 5.0
    # feel-better mirror). Consume the marker either way so it can't re-fire.
    sick = bool(char.get_property("just_sickened"))
    if sick:
        char.set_property("just_sickened", False)
    recovered = bool(char.get_property("just_recovered"))
    if recovered:
        char.set_property("just_recovered", False)

    if sick or recovered:
        # Render as the drink outcome regardless of the literal verb token.
        text = render(
            "reflection",
            verb="drink",
            item=rest.strip(),
            sick=sick,
            recovered=recovered,
        )
        importance = 8.0 if sick else 5.0
    elif verb == "travel":
        text = render("reflection", verb=verb, location=char.location.name)
        importance = 2.0
    elif verb == "perform":
        activity = char.get_property("activity") or rest.strip()
        text = render("reflection", verb=verb, activity=activity)
        importance = 2.0
    elif verb == "boil" or (verb == "make" and "boil" in rest):
        # The corrective hinge of the #300 arc: the agent made the water safe.
        # Boiling is now the crafting recipe `make boiled water` (verb "make"),
        # so match that too; render as the canonical "boil" reflection either way.
        # Ranked above the passive recovery drink (5.0) and well above a plain
        # get (2.0) so importance-weighted retrieval surfaces this causal
        # "I fixed it" step -- the exact signal the #299/#301 choose-to-boil
        # experiment reads -- instead of losing it to the 1.0 filler bucket.
        text = render("reflection", verb="boil", command=command)
        importance = 6.0
    elif verb == "drink":
        # A drink with no transition marker: safe water while healthy (or a
        # still-sick agent whose drink changed nothing). Normal importance.
        text = render("reflection", verb=verb, item=rest.strip())
        importance = 2.0
    elif verb in ("get", "activate", "deactivate"):
        # World-mutating one-shot verbs (#300): worth a normal-importance
        # memory, unlike the 1.0 catch-all below.
        text = render("reflection", verb=verb, command=command)
        importance = 2.0
    elif verb == "wait":
        # Idle filler (#300 spacers, or a live brain choosing to wait): not
        # worth a memory at all. Skip it so a run doesn't accrue identical 1.0
        # "I did wait" entries that crowd the agent's card and feed
        # maybe_reflect's importance accumulator with noise.
        return
    else:
        text = render("reflection", verb=verb, command=command)
        importance = 1.0
    agent.memory.add_observation(text, turn=step, importance=importance)


def maybe_converse(
    game,
    chars,
    state,
    frame,
    step,
    cooldowns,
    order,
    *,
    cooldown_steps: int = CONVERSATION_COOLDOWN_STEPS,
    max_exchanges: int = CONVERSATION_MAX_EXCHANGES,
) -> int:
    """Run conversations between co-located, settled residents this step (#86).

    Called once per step *after* movement resolves. A pair is eligible when both
    are *settled into an activity* (standing still, not walking) and co-located --
    decided by the engine's ``audience_for`` seam via
    :func:`conversation.find_conversation_pairs`. The same pair is throttled to one
    conversation per :data:`CONVERSATION_COOLDOWN_STEPS`, so residents sharing a
    cafe for an hour chat once, not every tick.

    Each conversation runs the engine turn-taking loop
    (:func:`conversation.converse`), which writes every line into *both* agents'
    memory streams as ``MemoryKind.CHAT`` and surfaces the last line on both
    participants' replay cards (``state``/``frame`` ``"chat"``).

    **Gated by the caller**: only invoked when a real brain is driving. With the
    deterministic mock brain, ``Agent.converse`` returns nothing anyway (its tool
    answer carries no ``utterance``), so even an accidental call is a no-op -- the
    mock replay stays byte-identical. Returns how many conversations happened.
    """
    settled = [
        chars[name]
        for name in order
        if state[name]["performing"] and not state[name]["path"]
    ]
    happened = 0
    # An agent can hold only one conversation per step. In a room of 3+ settled
    # residents find_conversation_pairs reports every eligible pair, so the same
    # agent shows up in several (A-B and A-C) -- the engine deliberately leaves
    # the pick to the caller. Take a first-come matching: once someone has
    # conversed this step, skip any later pair that includes them, so no agent
    # double-writes its memory / chat frame in one tick (#187).
    spoken: set[str] = set()
    for a, b in convo.find_conversation_pairs(game, settled):
        if a.name in spoken or b.name in spoken:
            continue
        key = frozenset((a.name, b.name))
        if step - cooldowns.get(key, -(10**9)) < cooldown_steps:
            continue
        # Attribute the meeting's LLM calls per speaker: converse() alternates
        # speakers through each speaker's OWN client, so when the two clients
        # are separate instances (#366 per-agent brains) each gets its owner's
        # name and GET /usage's by_actor splits the dialogue correctly. Under
        # the classic SHARED client both `ctx` are the same dict, so only the
        # initiator is stamped -- the pre-#366 behavior, byte-identical. The
        # "role" key labels the terminal request monitor's line (llm_monitor).
        ctx_a = getattr(a.agent.llm_client, "context", None)
        ctx_b = getattr(b.agent.llm_client, "context", None)
        if ctx_b is ctx_a:
            ctx_b = None  # classic shared client: stamp once, initiator wins
        for char, ctx in ((a, ctx_a), (b, ctx_b)):
            if ctx is not None:
                ctx.update(
                    {"actor": char.name, "turn": step, "attempt": 0, "role": "converse"}
                )
        conversation = convo.converse(
            game, a, b, turn=step, max_exchanges=max_exchanges
        )
        if not conversation.happened:
            continue
        cooldowns[key] = step
        happened += 1
        spoken.update((a.name, b.name))  # both are now busy for this step (#187)
        # The frontend renders chat as a list of [speaker, line] pairs (see
        # main_script.html), so hand it the whole transcript. It persists (like
        # desc/reasoning) on state until the agent's next conversation.
        lines = [[speaker, text] for speaker, text in conversation.lines]
        for nm in (a.name, b.name):
            state[nm]["chat"] = lines
            if nm in frame:
                frame[nm]["chat"] = lines
    return happened
