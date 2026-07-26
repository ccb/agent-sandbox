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
import re
import time
from dataclasses import dataclass, replace

from text_adventure_games import conversation as convo
from text_adventure_games.llm_client import MockReActClient, run_tool_loop
from text_adventure_games.memory import MemoryKind
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
# After its last line a conversation HOLDS both participants in place for the
# viewer's playback window -- this many steps per transcript line (issue #673).
# The Godot viewer shows each line for DIALOGUE_LINE_STEPS (viewer.gd) steps, so
# without the hold the pair would walk off mid-playback and the conversation
# link would stretch between them across the map. Keep in sync with viewer.gd's
# DIALOGUE_LINE_STEPS and penn_world.py's injector mirror of the same name.
CONVERSATION_LINE_PLAYBACK_STEPS = 14

# React-or-continue (issue #370): guards on the perception-driven interruption
# consult. Per-agent cooldown + a hard per-sim-hour cap, so a busy hallway is
# never an LLM storm; the hour window falls back to 360 steps (one hour at the
# default 10 s/step) when a run threads no clock.
REACT_COOLDOWN_STEPS = 90
REACT_HOUR_CAP = 4
REACT_HOUR_FALLBACK_STEPS = 360
# The encounter memory the cheap perceive pass writes -- same weight as a
# travel/perform outcome: notable enough to retrieve, not a reflection driver.
ENCOUNTER_IMPORTANCE = 2.0

_CONSULT_RE = re.compile(r"^(\w+)\((.*)\) -> (\d+)\b")


def _consult_entry(summary: str) -> dict:
    """A cognition_toolset summary ("recall('x') -> 3 memories") -> a compact
    trace entry (#359). Digest only -- the arg is the toolset's repr, never the
    retrieved payload. Falls back gracefully so a decide never crashes on it."""
    m = _CONSULT_RE.match(summary or "")
    if m:
        return {"kind": m.group(1), "arg": m.group(2), "hits": int(m.group(3))}
    kind = (summary or "").split("(", 1)[0].strip() or "consult"
    return {"kind": kind, "arg": "", "hits": 0}


# Conversation consequences (issue #582). A backend-local revision reason -- the
# engine's RevisionTrigger.reason is a plain string (planning.py), so an
# agreement reached in dialogue needs no engine change to reach a planner.
CONVERSATION = "conversation"

# React-or-continue (issue #370). A backend-local revision reason, like
# CONVERSATION/DEVIATED: an agent chose "replan" when it noticed someone
# mid-activity. RevisionTrigger.reason is a plain string, so no engine change.
REACTED = "reacted"

# Distinguishing substring of the engine's free-text dialogue system prompt
# (text_adventure_games/prompt_templates/npc_dialogue.prompty), used by
# ScheduleMockClient._decide to recognise -- and decline -- a "what do you say
# next" request so the mock never converses. This is a cross-package string
# coupling; test_conversation_consequences_582.py renders that engine template
# and asserts this marker is still present, so a reword there fails the backend
# suite loudly instead of silently breaking the guard.
_CONVERSING_MARKER = "you are in a conversation"

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

# The react tool (#370): one structured call when a walking agent newly
# notices another resident. Normalized {name, description, parameters}, the
# shape llm_client.call_tool translates per provider, like the outcome tool.
REACT_TOOL = {
    "name": "react",
    "description": (
        "You noticed someone while in the middle of what you were doing. "
        "Decide whether to keep going, stop to greet them, or change your "
        "plans for the rest of the day."
    ),
    "parameters": {
        "type": "object",
        "properties": {
            "choice": {
                "type": "string",
                "enum": ["continue", "greet", "replan"],
                "description": (
                    "continue: carry on as you were. greet: pause and say "
                    "hello (a short conversation starts). replan: what you "
                    "noticed changes the rest of your day."
                ),
            },
            "detail": {
                "type": "string",
                "description": (
                    "If replan: what should change and why. Omit otherwise."
                ),
            },
        },
        "required": ["choice"],
    },
}

# Memory importance scoring (issue #583). MemoryRecord.metadata keys the scorer
# reads/writes: _LOCKED marks a ground-truth importance the model must never
# re-guess (the #300 sickness signal, the #582 relationship note); _SCORED marks
# a record the scorer has already examined, so each is asked about at most once;
# _ATTEMPTS counts sends that came back malformed, so a persistent failure can
# retire the record instead of re-asking forever (issue #759).
_IMPORTANCE_LOCKED = "importance_locked"
_IMPORTANCE_SCORED = "importance_scored"
_IMPORTANCE_ATTEMPTS = "importance_score_attempts"

# Bounds on the scorer's retry loop (issue #759). The rescan deliberately has no
# cursor, so a malformed reply is retried next tick -- but unbounded, a brain
# that keeps failing (or one that never answers score_memories) would re-send an
# ever-growing batch every tick. Two bounds keep that failure mode flat: one
# send carries at most SCORE_BATCH_MAX records (a normal tick's new memories are
# far fewer, so the cap only engages once a failure backlog has built), and a
# record whose sends have all failed SCORE_MAX_ATTEMPTS times retires at its
# constant floor rather than riding every future batch.
SCORE_BATCH_MAX = 25
SCORE_MAX_ATTEMPTS = 3

# One structured call per acting agent per tick scores that agent's new memories
# 1-10 (Generative Agents "poignancy"), replacing the hardcoded importance
# constants. Batched: every unscored record in one request. Normalized
# {name, description, parameters}, the shape llm_client.call_tool translates per
# provider, like the planner's and the conversation-outcome tools.
IMPORTANCE_SCORE_TOOL = {
    "name": "score_memories",
    "description": (
        "Rate how significant (poignant) each memory is to you, from 1 "
        "(utterly mundane) to 10 (momentous), one score per memory id."
    ),
    "parameters": {
        "type": "object",
        "properties": {
            "scores": {
                "type": "array",
                "description": "One entry per memory: its id and a 1-10 importance.",
                "items": {
                    "type": "object",
                    "properties": {
                        "id": {
                            "type": "integer",
                            "description": "The memory's id, exactly as listed.",
                        },
                        "score": {
                            "type": "integer",
                            "description": "1 (mundane) to 10 (momentous).",
                        },
                    },
                    "required": ["id", "score"],
                },
            },
        },
        "required": ["scores"],
    },
}

from text_adventure_games.actions.things import CRAFT_VERBS
from text_adventure_games.enums import ActionName, Property

from . import seed
from .actions import TalkTo, Travel
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
        # Agent.converse's free-text fallback (_converse_freetext) also calls
        # chat() -- with the dialogue system message, not the decide one. This
        # brain only knows how to walk a schedule, not answer "what do you say
        # next", so it declines instead of echoing a stale travel/perform
        # command as a line of dialogue (issue #582): the mock never
        # converses, and maybe_converse's outcome pass is never reached.
        # Keys on _CONVERSING_MARKER, a substring of the engine's npc_dialogue
        # prompt; a test pins that coupling so a reword can't break it silently.
        if _CONVERSING_MARKER in system.lower():
            return None
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
    temperature: float | None = None,
    reflection_threshold: float | None = None,
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

    A world YAML's own ``relationships`` edges reach memory the same way (issue
    #779): a spec carrying ``relationship_edges`` -- the validated edges it is an
    endpoint of, attached by ``penn_world.build_penn_world`` -- gets one seeded
    memory per edge, naming the other person, the ``kind``, and the ``closeness``
    in words (:func:`seed.relationship_statements`). This is what the Penn path
    always lacked: the edges were validated and drawn in the viewer's
    social-graph card but never delivered to an agent, so authored rivals,
    siblings, and TAs behaved like strangers who happened to be standing nearby.
    No key -> nothing seeded, so a world without a social graph is unchanged.

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
    which never reaches either tool loop -- keeps the run byte-identical.

    Pass ``temperature`` / ``reflection_threshold`` (issue #564) to set each
    agent's sampling temperature and reflection trigger from a config (the
    live server's ``--config`` reads them off ``SimulationConfig.game.agent``).
    ``None`` -- the default, and what every existing caller passes -- keeps
    :class:`LLMAgent`'s own defaults, so behavior is unchanged."""
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
        # #564: forward temperature / reflection_threshold only when set, so
        # LLMAgent's own defaults stay the single source of the fallbacks.
        agent_kwargs = {}
        if temperature is not None:
            agent_kwargs["temperature"] = temperature
        if reflection_threshold is not None:
            agent_kwargs["reflection_threshold"] = reflection_threshold
        agent = LLMAgent(
            brain,
            persona=char.persona,
            embedding_client=embedding_client,
            **agent_kwargs,
        )
        # Cognition tools (issue #512): the engine flag both the decide seam
        # below and the engine's converse path read. Stamped (not passed to the
        # constructor) to match how the rest of this function decorates the
        # agent (schedule, planner, plan).
        if cognition_tools:
            agent.cognition_tools = True
        # Periodic reflection (issue #84): an LLMReflector when a real client is
        # supplied, else None -- so the offline mock run never reflects and the
        # replay stays byte-identical. The threshold is the agent's
        # reflection_threshold (LLMAgent's default unless #564's config passed one).
        if reflector_client is not None:
            agent.reflector = LLMReflector(reflector_client)
        # The verbs the structured tool may offer; the mock ignores the enum but a
        # well-formed schema keeps the seam honest for a real brain. Order:
        # the base travel/perform, then any caller-supplied extra_action_names
        # (spec §3, #300 -- e.g. Penn's device/drink verbs, so a real brain's
        # closed enum can choose them even without an authored commands: stop),
        # then whatever authored-command verbs remain (sorted), deduplicating
        # while preserving that order.
        # "wait" was once stripped here (a Wait tool on every decide invited
        # sitting idle at recurring token spend); #614 retires that -- WaitPenn's
        # required duration_minutes makes a chosen wait SETTLE like perform, so
        # authored wait spacers now promote like any other verb. NB: that safety
        # lives in the REGISTERED action, not here -- a world that offers the
        # engine's bare Wait (no duration slot) to a real brain re-opens the
        # idle trap; every Penn entry point registers WaitPenn (penn_world's
        # PENN_EXTRA_ACTIONS).
        authored_verbs = sorted(
            {
                cmd.split(" ", 1)[0]
                for stop in spec["schedule"]
                for cmd in stop.get("commands") or []
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
        # Opt-in thirst drive (#594): copy the per-persona rate/threshold onto the
        # character as properties the step loop's accrue_thirst reads. Absent keys
        # set nothing, so a normal persona never accrues -> byte-identical bake.
        if spec.get("thirst_rate"):
            char.set_property("thirst_rate", spec["thirst_rate"])
        if spec.get("thirst_threshold"):
            char.set_property("thirst_threshold", spec["thirst_threshold"])
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
        # Two sources, one seeder: the upstream Smallville CSV (above) and the
        # world YAML's own `relationships` edges, handed to each persona spec as
        # `relationship_edges` by penn_world.build_penn_world (#779 -- before
        # that these edges reached meta.relationships for the viewer's
        # social-graph card and NOWHERE else, so an authored `rivals` pair had
        # no idea they were rivals).
        statements = list(relationships.get(char.name, []))
        statements += seed.relationship_statements(
            char.name, spec.get("relationship_edges") or []
        )
        # #794: lock the seeded importance, matching the note/commitment
        # locks below -- score_new_memories would otherwise re-guess the
        # authored 3.0 (a deliberately-background social prior) as 6-8.
        for rec in seed.seed_relationships(agent.memory, statements):
            rec.metadata[_IMPORTANCE_LOCKED] = True
        # -- Opt-in seeded memories (#595): author t=0 observations (e.g. an aversive
        # -- "the unboiled water made me sick" memory) so a live brain can retrieve
        # -- and reason from them. Importance 5.0 matches the plan-memory seed so it
        # -- ranks highly. Absent key -> nothing added (byte-identical).
        for text in spec.get("seed_memories") or []:
            agent.memory.add_observation(text, turn=0, importance=5.0)
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

    The same enrichment (#635) covers the item-bearing verbs: without it a
    tool-calling brain must blind-guess the exact item string into the engine's
    generic free-text ``arguments`` slot, and the Penn boil items ship long,
    alias-thin names (``pot of murky water``) a model reliably mis-phrases
    (``water``) -- so the boil arc is unexpressible and #595 measures nothing.
    We fill each verb's ``arguments`` enum with the *routable argument string*:
    gettable / drinkable item names in scope for ``get`` / ``drink``, and recipe
    names for the craft verb (``make``). Every enum is guarded by ``max_enum``
    (too many candidates -> the slot stays free text, the model reads them off
    the observation instead). The precondition gate still owns validity -- e.g.
    Drink's carried-only check -- so enumerating a name never widens what's
    actually doable; it only makes the name *nameable*.
    """
    agent = char.agent
    tools = tools_for(
        game.parser, actor=char, names=agent.action_names, max_enum=max_enum
    )
    destinations = sorted(game.locations)
    # Per-verb enum of the exact argument string the model should emit. Keyed by
    # the verb (== tool name); the craft verbs are matched separately below since
    # any of CRAFT_VERBS ("make"/"cook"/...) may be the authored one.
    scope = game.parser.get_items_in_scope(char)
    arg_enums = {
        ActionName.GET: sorted(
            n for n, it in scope.items() if it.get_property(Property.GETTABLE)
        ),
        ActionName.DRINK: sorted(
            n for n, it in scope.items() if it.get_property(Property.DRINKABLE)
        ),
    }
    craftable = sorted({n for r in getattr(game, "recipes", []) for n in r.names()})
    for tool in tools:
        name = tool["name"]
        props = tool["parameters"]["properties"]
        if name == Travel.ACTION_NAME:
            if len(destinations) <= max_enum and "destination" in props:
                props["destination"]["enum"] = destinations
            continue
        values = craftable if name in CRAFT_VERBS else arg_enums.get(name)
        if values and len(values) <= max_enum and "arguments" in props:
            props["arguments"]["enum"] = values
            # Overwrite the engine's generic placeholder ("... e.g. 'player with
            # club'"), which actively misleads once the slot is a closed menu.
            props["arguments"]["description"] = "choose exactly one of the listed names"

    # Bespoke curation for talk_to (#614): "another living character is
    # co-located" is not expressible as a REQUIRED_AFFORDANCES tag -- the #612
    # helper's scope is items / inventory / the location itself, never its
    # characters (flagged on #612) -- so the toolset builder reads the same
    # facts TalkTo.check_preconditions reads, keeping offered <=> gate. The
    # third leg -- the target must have an ``agent`` -- is the same fact the
    # engine's conversation.can_converse requires of both sides; without it
    # build_world's silent "Observer" player (the engine's required player,
    # standing at the hub, never scripted with an agent) would be offered as
    # a talk target it can never actually converse with. The person slot's
    # enum comes from the same character dict the gate matches against, so
    # menu and gate cannot disagree about who is present. (TalkTo's slots are
    # ``person``/``topic``, never the engine's generic ``arguments``, so the
    # #635 enum loop above leaves it untouched.)
    others = sorted(
        c.name
        for c in (char.location.characters.values() if char.location else [])
        if c is not char
        and not c.get_property("is_dead")
        and getattr(c, "agent", None) is not None
    )
    talk_tool = next((t for t in tools if t["name"] == TalkTo.ACTION_NAME), None)
    if talk_tool is not None:
        if not others:
            tools.remove(talk_tool)
        elif len(others) <= max_enum:
            prop = talk_tool["parameters"]["properties"].get("person")
            if prop is not None:
                prop["enum"] = others
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
    agent.last_trace = []
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

        def _trace(text):
            game.parser.agent_reasoning(char.name, text)
            agent.last_trace.append(_consult_entry(text))

        cog_tools, cognition_execute = cognition_toolset(
            agent,
            knowledge=getattr(char, "knowledge", None),
            turn=getattr(game, "turn", 0),
            trace=_trace,
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


# Arena affordance tags surfaced in the nearby-affordances line (#613): the
# tags a visible-but-distant arena carries that a verb will key on -- `studyable`
# (the study verb, #615) and `dining` (Houston Hall meals, #615). An explicit
# tuple, NOT "every property on the location", so the line stays a curated hint
# rather than dumping the arena's whole bool bag. Later slices add their tag
# names here as they land.
ARENA_AFFORDANCE_TAGS = ("studyable", "dining")


def nearby_affordances_line(game, char) -> str:
    """Name visible-but-distant arenas and the affordance tags they carry
    (issue #613, spec decision 2) so a live brain can choose to *travel* toward
    one -- the perception half of desire -> travel -> act.

    Scans the character's perceivable arenas (``game.perceivable_locations``,
    the ``vision_r`` seam of #82), drops the arena it already stands in, and
    turns each remaining arena that carries any tag in
    :data:`ARENA_AFFORDANCE_TAGS` into a ``"name (tags)"`` fragment (sorted by
    name for a stable line). Returns ``""`` when nothing nearby is tagged, so no
    empty line is ever appended. This NEVER widens the toolset -- offers stay
    in-scope only (:func:`npc.tools_for`); the verb appears on arrival.
    """
    here = char.location
    fragments = []
    for loc in sorted(
        game.perceivable_locations(char), key=lambda location: location.name
    ):
        if loc is here:
            continue
        tags = [tag for tag in ARENA_AFFORDANCE_TAGS if loc.get_property(tag)]
        if tags:
            fragments.append(f"{loc.name} ({', '.join(tags)})")
    if not fragments:
        return ""
    return render("nearby_affordances", arenas="; ".join(fragments))


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
    5. **Nearby affordances** (#613): append the visible-but-distant tagged
       arenas (:func:`nearby_affordances_line`) so a live brain can choose to
       *travel* toward one. Gated on the same real-brain tool-path predicate
       (:func:`_use_action_tools`) as the decide route below, so the
       deterministic mock never reads this line and the bake stays
       byte-identical.

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
    # The decide prompt lists exactly the tools this agent is offered this tick
    # (#697), so the real brain isn't shown verbs it can't call. Retrieval, though,
    # runs on the FULL registered menu (agent_action_menu=False) -- byte-identical
    # to what describe_for produced before #697 -- so curating the prompt's menu
    # can't shift which memories surface. The mock reads only the first line of the
    # prompt, so the offered menu never reaches its decision; the byte-identical
    # bake is preserved (frames embed last_retrieved, not the observation text).
    base = game.describe_for(char)
    retrieval_query = game.describe_for(char, agent_action_menu=False)
    if retrieval is None:
        relevant = agent.memory.retrieve(query=retrieval_query, turn=step)
    else:
        relevant = agent.memory.retrieve(
            query=retrieval_query,
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
    # Perceivable needs (#594): surface thirst in the decide prompt so a live
    # brain can reason about it. Appended AFTER the retrieve above (like the
    # #580 block), so the line never shifts which memories surface -- the
    # mock/scripted bake stays byte-identical. Absent flag adds nothing.
    # (Sickness moved into describe_for itself -- the engine's #634 is_sick
    # self-line, worded via sick_self_description set in actions.py.)
    if char.get_property("is_thirsty"):
        base = base + "\n\nYou are thirsty."
    # Nearby-affordances line (#613): visible-but-distant tagged arenas, so the
    # brain can choose to travel toward one (offers stay in-scope only). Gated
    # on the real-brain tool path -- the SAME predicate that guards the tool
    # route below -- so the deterministic mock (and the byte-identical bake)
    # never read it. Appended after the environment text, like the #580 block.
    if _use_action_tools(agent):
        nearby = nearby_affordances_line(game, char)
        if nearby:
            base = f"{base}\n\n{nearby}"
    observation = format_observation_with_memories(base, relevant)
    agent.last_observation = observation
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


def apply_conversation_outcome(
    char, partner_name: str, transcript: str, step: int, clock=None
) -> bool:
    """One post-conversation outcome pass for a single participant (issue #582).

    After a meeting actually happened, ask *char*'s brain -- via the
    :data:`CONVERSATION_OUTCOME_TOOL` -- what the conversation changed:

    * ``plans_changed`` -> a plan revision (:func:`maybe_revise_plan`) tagged with
      the backend-local :data:`CONVERSATION` reason, the ``commitment`` (falling
      back to the transcript) carried as the trigger detail. The existing
      re-anchor guard protects executed/current stops; ``LLMPlanner.revise``
      already reads trigger detail, and ``MockPlanner.revise`` is a no-op. A
      non-blank ``commitment`` also becomes its own locked PLAN memory
      (issue #778) in *char*'s own stream -- written before the revision, so
      the intention survives regardless of what ``maybe_revise_plan`` returns;
      ``MockPlanner.revise`` being a no-op no longer means the commitment is
      dropped.
    * ``relationship_note`` -> a high-importance, partner-attributed CHAT memory
      in *char*'s own stream, so retrieval and reflection pick it up, and the
      record is partner-attributed for future social-graph work. Note this does
      NOT touch the #450 social graph card itself -- that reads
      ``meta.relationships``, which this function never mutates.

    Exactly one structured call, billed to *char* under ``role: "outcome"`` (the
    <=2-per-conversation cost bound, already throttled by the pair cooldown). Safe
    and inert when the brain can't tool-call, or returns nothing usable -- the
    same graceful contract the planner and decide paths follow -- which is also
    why the mock bake (no conversation, so this is never reached) is unchanged.
    Returns whether the plan changed.
    """
    agent = char.agent
    client = getattr(agent, "llm_client", None)
    call = getattr(client, "call_tool", None)
    if not callable(call):
        return False
    # Attribute the call to this speaker (usage.py); "role" labels the monitor
    # line. Stamped right before the (sequential) call, so a shared client is
    # attributed correctly per participant.
    ctx = getattr(client, "context", None)
    if ctx is not None:
        ctx.update({"actor": char.name, "turn": step, "attempt": 0, "role": "outcome"})
    messages = [
        # In character (same persona system message the decide path sends), so the
        # reflection is grounded in who this agent is.
        {"role": "system", "content": agent._structured_system_message()},
        {
            "role": "user",
            "content": render(
                "conversation_outcome", partner=partner_name, transcript=transcript
            ),
        },
    ]
    # No temperature passed -> call_tool's default 0.0, deliberately: this is a
    # structured yes/no + short-note classification, not free-text generation,
    # so it should stay deterministic -- unlike the decide/converse paths (which
    # pass agent.temperature). Don't "fix" this to agent.temperature.
    result = call(messages, CONVERSATION_OUTCOME_TOOL, max_tokens=agent.max_tokens)
    if not isinstance(result, dict):
        return False
    note = result.get("relationship_note")
    if isinstance(note, str) and note.strip():
        note_record = agent.memory.add_chat(
            note.strip(),
            turn=step,
            partner=partner_name,
            importance=RELATIONSHIP_NOTE_IMPORTANCE,
        )
        # #583: the relationship note is a deliberate high signal (#582), not a
        # guessable importance -- lock it so score_new_memories leaves it be.
        note_record.metadata[_IMPORTANCE_LOCKED] = True
    # Require a real boolean True -- not merely a truthy value. A lenient or
    # fake client that returns a stringy "false" or a 1 must not trip a
    # revision; the schema declares plans_changed as a required boolean, so a
    # strict provider always sends one.
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
    # block by its own partner-chatter.
    # The transcript fallback is deliberately NOT written: a whole transcript
    # stored as a "plan" is noise, so only a real commitment persists.
    #
    # The lock is INERT today, unlike the note's above: score_new_memories
    # filters to OBSERVATION/CHAT *before* it consults _IMPORTANCE_LOCKED, so a
    # PLAN record is already exempt (pinned by
    # test_reflection_and_plan_records_are_not_rescored). Written anyway so that
    # widening that kind filter can't silently re-guess an authored importance.
    #
    # Side effect: AgentMemory._add adds every new record's importance to
    # importance_since_reflection (memory.py:317), so this second 8.0 write
    # means a conversation now contributes 16.0 toward the 30.0 reflection
    # threshold instead of 8.0 -- conversation-heavy agents reflect roughly
    # twice as often from conversations alone, and reflection is a real LLM
    # call.
    if has_commitment:
        intent = agent.memory.add_plan(
            render("commitment_memory", other=partner_name, commitment=detail),
            turn=step,
            importance=RELATIONSHIP_NOTE_IMPORTANCE,
        )
        intent.metadata[_IMPORTANCE_LOCKED] = True
    return maybe_revise_plan(char, RevisionTrigger(CONVERSATION, step, detail), clock)


def score_new_memories(char, step: int) -> None:
    """Score ``char``'s newly-formed memories 1-10 with the model (issue #583).

    Replaces the hardcoded importance constants (``remember_outcome``'s per-verb
    numbers, ``add_chat``'s DEFAULT_CHAT_IMPORTANCE, perception's
    PRESENCE_IMPORTANCE) with the paper's model-scored *poignancy*, so reflection
    timing and retrieval ranking track what actually mattered rather than a flat
    schedule. Called once per acting agent per tick, right before ``maybe_reflect``
    (:mod:`run_simulation`), over every record not yet scored:

    * **One batched call.** All unscored, unlocked records go in a single
      ``score_memories`` tool request -- never one call per record, which would
      double live call volume. Each returned ``{id, score}`` overrides that
      record's importance (clamped to 1-10) and shifts
      ``importance_since_reflection`` by the delta, so ``should_reflect`` reads
      the *scored* accumulator.
    * **Constants are the floor.** A non-dict / malformed reply leaves the
      constants intact and does NOT mark records scored, so a transient failure
      simply retries next decide. A record the model omits keeps its constant but
      is marked scored (we asked; don't re-ask). Over-budget is inherited: this
      runs only after a successful decide, and decides are gated by the run's
      cost-ceiling kill-switch.
    * **Failure stays bounded (issue #759).** One send carries at most
      SCORE_BATCH_MAX records, and every failed send counts against the records
      it carried: after SCORE_MAX_ATTEMPTS failures a record retires at its
      constant floor (marked scored). A persistently failing brain therefore
      degrades to the constants instead of re-sending an ever-growing batch each
      tick, while a recovery before retirement still scores the whole backlog,
      cap-sized batch by batch.
    * **Ground-truth stays.** Records flagged ``_IMPORTANCE_LOCKED`` (the #300
      sickness outcome, the #582 relationship note) are skipped entirely -- event
      knowledge the model can't see from text, so it must not re-guess it.

    Mock byte-identical: gated on brain-identity. ``attach_agents`` wires the mock
    brain AS ``agent.schedule`` (same object), so ``brain is agent.schedule`` is
    exactly "no real client supplied" -- the same gate #485/#582 use. Checking
    ``callable(call_tool)`` alone would NOT do: ``ScheduleMockClient`` scripts
    ``call_tool``, so the default offline run would score and the bake would drift.
    """
    agent = char.agent
    brain = getattr(agent, "llm_client", None)
    # Real, tool-calling brain only -- identity gate first (see docstring).
    if (
        brain is None
        or brain is getattr(agent, "schedule", None)
        or not callable(getattr(brain, "call_tool", None))
    ):
        return

    memory = agent.memory
    # Mark any locked record examined so it drops out of future candidate scans,
    # and collect the unscored, unlocked ones to send.
    candidates = []
    for record in memory.records:
        if record.metadata.get(_IMPORTANCE_SCORED):
            continue
        # Only observations and chat carry the hardcoded importance constants
        # this pass replaces. Reflections and plans set their own salience, and
        # reflect() zeroes importance_since_reflection after writing REFLECTION
        # records -- re-scoring one on a later tick would leak its delta into the
        # fresh window and skew reflection cadence. Skip them (mark scored so the
        # scan stays bounded).
        if record.kind not in (MemoryKind.OBSERVATION, MemoryKind.CHAT):
            record.metadata[_IMPORTANCE_SCORED] = True
            continue
        if record.metadata.get(_IMPORTANCE_LOCKED):
            record.metadata[_IMPORTANCE_SCORED] = True
            continue
        # #759: every send this record rode came back malformed -- retire it at
        # its constant floor rather than re-asking forever. Distinct from the
        # transient-failure retry below: a record retires only after
        # SCORE_MAX_ATTEMPTS whole-batch failures, never on the first.
        if record.metadata.get(_IMPORTANCE_ATTEMPTS, 0) >= SCORE_MAX_ATTEMPTS:
            record.metadata[_IMPORTANCE_SCORED] = True
            continue
        candidates.append(record)
    if not candidates:
        return
    # #759: bound what one send carries. A normal tick's new memories are far
    # fewer than the cap, so the happy path is unchanged; only a failure backlog
    # engages it, keeping per-tick token cost flat. The overflow stays unscored
    # and rides the next tick's rescan (oldest first, memory-stream order).
    candidates = candidates[:SCORE_BATCH_MAX]

    # Attribute the call to this agent (usage.py); "role" labels the monitor line.
    ctx = getattr(brain, "context", None)
    if ctx is not None:
        ctx.update({"actor": char.name, "turn": step, "attempt": 0, "role": "score"})
    messages = [
        # In character (same persona system message the decide path sends), so
        # poignancy is judged from who this agent is.
        {"role": "system", "content": agent._structured_system_message()},
        {
            "role": "user",
            "content": render(
                "importance_score",
                memories=[{"id": r.id, "text": r.text} for r in candidates],
            ),
        },
    ]
    # No temperature -> call_tool's default 0.0, deliberately: this is a numeric
    # classification, not free-text generation, so it stays deterministic (like
    # apply_conversation_outcome; don't "fix" it to agent.temperature).
    result = brain.call_tool(
        messages, IMPORTANCE_SCORE_TOOL, max_tokens=agent.max_tokens
    )
    # Malformed / transient failure: leave everything unscored, floor stands,
    # retry next tick -- but count the failed ask against each record sent
    # (#759), so a persistent failure retires them (see the candidate scan)
    # instead of regrowing the batch every tick.
    scores = result.get("scores") if isinstance(result, dict) else None
    if not isinstance(scores, list):
        for record in candidates:
            record.metadata[_IMPORTANCE_ATTEMPTS] = (
                record.metadata.get(_IMPORTANCE_ATTEMPTS, 0) + 1
            )
        return

    by_id: dict[int, object] = {}
    for entry in scores:
        if not isinstance(entry, dict):
            continue
        eid = entry.get("id")
        # bool is an int subclass, so a boolean id would pass an isinstance int
        # check and then collide with real id 0/1 (hash(True) == hash(1)),
        # mis-scoring that record. Reject it (mirrors the score-side guard below).
        if isinstance(eid, int) and not isinstance(eid, bool):
            by_id[eid] = entry.get("score")
    for record in candidates:
        record.metadata[_IMPORTANCE_SCORED] = True  # asked; never re-ask
        raw = by_id.get(record.id)
        if not isinstance(raw, (int, float)) or isinstance(raw, bool):
            continue  # model omitted / non-numeric: keep the constant floor
        new = max(1.0, min(float(raw), 10.0))
        memory.importance_since_reflection += new - record.importance
        record.importance = new


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


def remember_outcome(
    char, command: str, step: int, fail_reason: str | None = None
) -> None:
    """Record ``char``'s own action outcome as a first-person memory.

    On a success (``fail_reason`` is ``None``) the per-verb branches below pick
    the phrasing; on a gate-blocked attempt (``fail_reason`` set) the failure
    branch renders once and returns (#636).

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

    # #636: a gate-blocked (or otherwise failed) attempt. Record it so the next
    # decide's retrieval can steer away instead of re-choosing the same blocked
    # action indefinitely. apply_effects never ran on a failure, so none of the
    # success-only one-shot markers below (just_sickened / just_studied_minutes)
    # were set -- safe to return before that logic. Modest importance (3.0):
    # above routine 2.0 successes so "what didn't work" surfaces in retrieval,
    # below the 6-8 causal signals; NOT locked, so #583's score_new_memories
    # re-scores it for a real brain -- this is only the pre-score floor. The
    # mock brain's authored commands always parse, so this branch is never taken
    # under the mock and the bundled replay stays byte-identical by vacuity.
    # ponytail: no write-time dedupe -- a real brain that re-picks the same
    # blocked non-talk action every tick accretes identical 3.0 records until
    # retrieval steers it away (talk misses already settle, #689). Add a
    # per-(actor, command) cooldown here if that noise shows up in live runs.
    if fail_reason is not None:
        text = render("reflection", failed=True, command=command, reason=fail_reason)
        agent.memory.add_observation(text, turn=step, importance=3.0)
        return

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
    elif verb == "study":
        # The one-shot delta Study.apply_effects just recorded (#615) -- the
        # brain's #581 duration pick or the action's default. Consume it (the
        # just_sickened pattern) so it can't leak into a later outcome.
        minutes = char.get_property("just_studied_minutes")
        char.set_property("just_studied_minutes", False)
        text = render(
            "reflection",
            verb=verb,
            topic=rest.strip(),
            minutes=int(minutes) if minutes else 0,
        )
        importance = 2.0
    elif verb == "eat":
        # Satiety is the memory (#615); hunger as an accumulating drive is #594.
        text = render("reflection", verb=verb, item=rest.strip())
        importance = 2.0
    elif verb == "check_out_book":
        # The #616 book loop's first half: taking custody unlocks read, so it
        # outranks a plain get (2.0).
        text = render("reflection", verb=verb, item=rest.strip())
        importance = 3.0
    elif verb == "read":
        # The loop's payoff: the content itself enters memory. parse_command
        # stamped the action it just ran on char.last_action, and Read already
        # matched the exact item (aliases, containers, worn -- the parser's
        # full scope rules); reuse that instead of re-deriving the match here.
        thing = getattr(getattr(char, "last_action", None), "item", None)
        content = thing.get_property("read_text") if thing else ""
        text = render(
            "reflection",
            verb=verb,
            item=thing.name if thing else rest.strip(),
            content=content or "",
        )
        importance = 3.0
    elif verb in ("get", "activate", "deactivate"):
        # World-mutating one-shot verbs (#300): worth a normal-importance
        # memory, unlike the 1.0 catch-all below.
        text = render("reflection", verb=verb, command=command)
        importance = 2.0
    elif verb == "talk_to":
        # #614: nothing at parse time. The intent memory ("I went to talk to
        # X ...") is written by maybe_converse's phase 1.5 IFF the conversation
        # actually opens -- a request that phase 1.5 drops (pair on cooldown,
        # target busy/walking) would otherwise stamp a false dialogue-tier
        # record, and the un-settled initiator can retry every tick for the
        # whole cooldown window.
        return
    elif verb == "wait":
        # Spacer / one-tick idle (#300 mock spacers, or a brain that omitted
        # the duration): still not worth a memory -- identical 1.0 "I did wait"
        # entries would crowd the card and feed maybe_reflect's accumulator
        # with noise, and the mock bake must stay byte-identical.
        # A SETTLED wait (#614: a real brain chose a duration this decide --
        # the stash is reset every observe_and_decide, so it can't leak from
        # an earlier tick) is an honest, legible decision: record it once.
        if getattr(agent, "last_duration_minutes", None) is None:
            return
        text = render("reflection", verb=verb)
        importance = 1.0
    else:
        text = render("reflection", verb=verb, command=command)
        importance = 1.0
    record = agent.memory.add_observation(text, turn=step, importance=importance)
    # #583: the sick/recovered drink outcome is event knowledge the model can't
    # derive from text (the #300 water arc's ground-truth 8.0/5.0), so lock it --
    # score_new_memories skips locked records rather than re-guessing them.
    if sick or recovered:
        record.metadata[_IMPORTANCE_LOCKED] = True


def remember_decide_timeout(char, step: int) -> None:
    """Record that ``char``'s decide blew its wall-clock budget (#758).

    The timeout counterpart of :func:`remember_outcome`'s #636 failure branch,
    deliberately deferred there: a decide that outlives ``decide_timeout``
    (the parallel-decide -> idle -> late-answer path, #366) chose nothing, so
    there is no command to remember -- but writing *nothing* leaves repeated
    timeouts on the same situation invisible to the agent's future reasoning.
    "I was thinking about what to do at <place> but couldn't decide in time."
    keys the memory to where the agent stood, so retrieval surfaces it exactly
    when the agent faces that situation again.

    Same conventions as the #636 failure memory: importance 3.0 (above routine
    2.0 successes, below the 6-8 causal signals) and NOT locked, so #583's
    score_new_memories re-scores it at the agent's next completed decide --
    its unscored-watermark scan picks the record up then; scoring *here* would
    send another synchronous call to the very brain that just blew its budget,
    stalling the tick the budget protects.
    """
    place = char.location.name if char.location is not None else ""
    text = render("reflection", timed_out=True, place=place)
    char.agent.memory.add_observation(text, turn=step, importance=3.0)


@dataclass
class ActiveConversation:
    """A conversation in progress across ticks (issue #371).

    Carried in the caller-owned ``active`` dict, keyed by the pair frozenset, so
    the sim loop can advance one line per tick. ``next_speaker`` alternates each
    line; ``convo`` accumulates the transcript-so-far. This record is also the
    seam a future third-party join/interruption (#370) hangs off.

    After the last line the record lingers as a **playback hold** (#673):
    ``hold_until`` is stamped with the step the viewer finishes playing the
    transcript back, and until then both participants stay pinned (and busy --
    the record still occupies the active set) so the map shows them standing
    together through the exchange.
    """

    a: str  # initiator name (stable pair ordering)
    b: str  # partner name
    convo: convo.Conversation
    next_speaker: str  # whose line the next advance generates
    started: int  # step the conversation began
    hold_until: int | None = None  # set on end: release step of the playback hold


def _stamp_convo_ctx(speaker, step: int) -> None:
    """Attribute this line's LLM call to *speaker* (usage.py); "role" labels the
    monitor line. Each multi-tick line is one speaker, so we stamp just that one
    (unlike the old whole-loop path, which stamped both up front)."""
    ctx = getattr(getattr(speaker.agent, "llm_client", None), "context", None)
    if ctx is not None:
        ctx.update(
            {"actor": speaker.name, "turn": step, "attempt": 0, "role": "converse"}
        )


def _publish_chat(state, frame, a_name: str, b_name: str, convo_obj) -> None:
    """Mirror the transcript-so-far onto both participants' cards. No-op when
    nothing has been said, so the mock (zero lines) never turns ``chat`` from
    ``None`` into ``[]`` -- the bake stays byte-identical."""
    if not convo_obj.lines:
        return
    lines = [[speaker, text] for speaker, text in convo_obj.lines]
    for nm in (a_name, b_name):
        state[nm]["chat"] = lines
        if nm in frame:
            frame[nm]["chat"] = lines


def _finish_conversation(a, b, convo_obj, step, cooldowns, clock) -> int:
    """End-of-conversation bookkeeping: record the pair cooldown and run the
    #582 outcome pass for each participant. Returns 1 if the conversation
    produced any lines (a real meeting), else 0 -- so a mock/empty conversation
    sets no cooldown and counts for nothing."""
    if not convo_obj.happened:
        return 0
    cooldowns[frozenset((a.name, b.name))] = step
    transcript = convo_obj.transcript()
    apply_conversation_outcome(a, b.name, transcript, step, clock=clock)
    apply_conversation_outcome(b, a.name, transcript, step, clock=clock)
    return 1


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
    This sets the pre-pass's own ``on_plan`` flag rather than inventing a second
    signal for it to consult. ``on_plan`` is read in exactly one place (that
    pre-pass) and is re-stamped by every path that sets ``perform_until`` --
    ``_settle_after_dead_talk`` and the decide-time perform branch -- so it is
    one-shot by construction: a credit written here is consumed by the settle it
    was earned at and cannot leak forward onto an unrelated stop.

    Place-match is the same rule the pre-pass already applies for ``on_plan``:
    standing at the scheduled stop means this completed it. Any real
    conversation there counts, social activity or not -- one authority, no new
    concept.

    ``performing`` is required so a conversation started mid-walk by
    ``maybe_react`` (#370), which pins a *walking* agent, cannot mark a stop the
    agent never reached as done. Every path that should credit still does:
    ``maybe_converse``'s own pairing already requires both agents settled.

    Deliberately does NOT write ``activity``. The scheduled activity is not
    necessarily what the agent did (under a real brain ``PerformPenn`` sets it
    from the model's own argument), and it would not clear the frame's
    ``"spending time"`` placeholder anyway -- ``st["desc"]`` is stamped only at
    decide time. What clears the placeholder is the advance this credit unlocks:
    the agent travels, arrives, and performs the next stop, stamping its own
    activity before the next desc is computed.

    Returns whether the stop was credited (for tests; callers ignore it).
    """
    if not st.get("performing"):
        return False
    schedule = char.agent.schedule
    place = getattr(schedule, "destination", None)
    if not place or char.location is None or char.location.name != place:
        return False
    st["on_plan"] = True
    return True


def _advance_conversation(
    game,
    ac,
    chars,
    state,
    frame,
    step,
    cooldowns,
    max_exchanges,
    clock,
    line_playback_steps,
) -> tuple[bool, int]:
    """Generate ONE line for active conversation *ac*, publish the transcript,
    and finish it if an end condition fired. Returns ``(ended, completed_delta)``:
    ``ended`` tells the caller to drop *ac* from the active set; ``completed_delta``
    (0/1) feeds the return count. Sets ``conversing`` True while it runs.

    A real exchange never returns ``ended`` on its end tick: the end-of-
    conversation bookkeeping (cooldown + #582 outcome pass) runs right here, but
    the record enters its **playback hold** (#673) -- ``hold_until`` stamped,
    ``conversing`` kept True -- so the pair stands together for the
    ``len(lines) * line_playback_steps`` steps the viewer needs to play the
    transcript back. Only an empty conversation (the mock's zero-line open)
    releases and ends immediately, exactly as before."""
    speaker = chars[ac.next_speaker]
    listener = chars[ac.b if ac.next_speaker == ac.a else ac.a]
    _stamp_convo_ctx(speaker, step)
    cont = convo.exchange(game, ac.convo, speaker, listener, turn=step)
    _publish_chat(state, frame, ac.a, ac.b, ac.convo)
    if cont and len(ac.convo.lines) < max_exchanges:
        ac.next_speaker = ac.b if ac.next_speaker == ac.a else ac.a
        state[ac.a]["conversing"] = True
        state[ac.b]["conversing"] = True
        return False, 0
    if ac.convo.happened:
        # #778: credit the scheduled stop this conversation just completed --
        # BEFORE the outcome pass below, whose plan revision can rewrite the very
        # schedule the place-match reads. (`replace_schedule` preserves the
        # current stop by contract, so this is ordering hygiene, not a live bug.)
        for nm in (ac.a, ac.b):
            _credit_stop_for_conversation(chars[nm], state[nm])
    delta = _finish_conversation(
        chars[ac.a], chars[ac.b], ac.convo, step, cooldowns, clock
    )
    if ac.convo.happened:
        ac.hold_until = step + len(ac.convo.lines) * line_playback_steps
        state[ac.a]["conversing"] = True
        state[ac.b]["conversing"] = True
        return False, delta
    state[ac.a]["conversing"] = False
    state[ac.b]["conversing"] = False
    return True, delta


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
    line_playback_steps: int = CONVERSATION_LINE_PLAYBACK_STEPS,
    clock=None,
    active: dict | None = None,
) -> int:
    """Advance and start co-located residents' conversations this step (#86, #371).

    Called once per step *after* movement resolves. A conversation is now a
    multi-tick activity (issue #371): ``active`` (a caller-owned dict keyed by the
    pair frozenset, persisted across ticks) holds each in-progress
    :class:`ActiveConversation`. Every step this function

    1. **advances** each in-progress conversation by exactly one
       :func:`conversation.exchange` line -- publishing the transcript-so-far on
       both cards. When an end condition fires (empty utterance, wrap-up flag, or
       ``max_exchanges`` lines) it records the pair cooldown and runs one
       :func:`apply_conversation_outcome` pass per participant (#582) -- but a
       real exchange is not removed yet: it enters a **playback hold** (#673) of
       ``len(lines) * line_playback_steps`` further steps, its participants still
       pinned (and busy), so the viewer can play the transcript back while the
       pair visibly stands together. The sweep here releases each held pair once
       its window elapses;
    2. **starts** a new conversation for each eligible settled, co-located pair
       (both ``performing`` and not walking, not already conversing, off cooldown),
       running its first line this same tick.

    Participants are marked ``state[name]["conversing"]`` while a conversation
    runs -- through its playback hold; :func:`run_simulation.step` reads that flag
    to keep them from walking or re-deciding. Returns how many conversations
    **completed** this step (counted on the end tick, not at release).

    **Gated by the caller / mock-inert**: only invoked under a real brain. The
    mock's ``Agent.converse`` returns nothing, so a started conversation dies on
    its first empty line with zero lines -- no chat write, no cooldown, no outcome
    -- and the bake stays byte-identical. ``active`` defaults to a throwaway dict
    for single-shot callers (e.g. tests that drive one tick directly).
    """
    active = active if active is not None else {}
    completed = 0

    # (1) Advance every in-progress conversation by one line, and release any
    # held pair whose playback window has elapsed (#673).
    # A participant whose conversation frees them this tick is captured into
    # finished_this_step (issue #187 fix): without it, phase 2's `busy` below --
    # computed after this loop's deletions -- would not see them as busy, and
    # they could immediately start (and finish) a second conversation with a
    # different resident in this same tick. Deferred instead to next tick.
    finished_this_step: set[str] = set()
    for key in list(active):
        ac = active[key]
        if ac.hold_until is not None:
            # Playback hold (#673): the exchange already completed (cooldown,
            # outcome pass and the completed count all ran on its end tick);
            # the pair just stands together while the viewer plays it back.
            if step >= ac.hold_until:
                state[ac.a]["conversing"] = False
                state[ac.b]["conversing"] = False
                del active[key]
                finished_this_step.update((ac.a, ac.b))
            continue
        ended, delta = _advance_conversation(
            game,
            ac,
            chars,
            state,
            frame,
            step,
            cooldowns,
            max_exchanges,
            clock,
            line_playback_steps,
        )
        completed += delta
        if ended:
            del active[key]
            finished_this_step.update((ac.a, ac.b))

    # Residents already conversing (or whose conversation just finished this
    # tick) are ineligible to start another one below (#187).
    busy = {
        name for ac in active.values() for name in (ac.a, ac.b)
    } | finished_this_step

    # (1.5) Agent-initiated requests (#614): a talk_to command earlier this
    # tick left a one-shot marker; open that conversation NOW, before the
    # proximity pair scan, so the explicit choice wins the tick and the first
    # line is spoken this same step (mirroring phase 2's start-and-advance).
    # The marker is consumed unconditionally: a request that cannot start
    # (target left / busy / mid-walk, pair on cooldown) is dropped and the
    # initiator -- unpinned, un-settled -- simply re-decides next tick. Mock
    # brains never emit talk_to, so this loop is inert offline.
    for name in order:
        char = chars[name]
        target_name = char.get_property("talk_request")
        if not target_name:
            continue
        char.set_property("talk_request", False)
        topic = char.get_property("talk_topic") or ""
        char.set_property("talk_topic", False)
        target = chars.get(target_name)
        if (
            name in busy
            or target is None
            or target_name in busy
            or target.location is not char.location
            or state[target_name]["path"]
            or state[target_name].get("conversing")
        ):
            continue
        key = frozenset((name, target_name))
        if key in active or step - cooldowns.get(key, -(10**9)) < cooldown_steps:
            continue
        # Record the intent only now that the conversation actually opens (a
        # dropped request must leave no false record -- the un-settled
        # initiator can retry every tick), and BEFORE the first line: the
        # opener's partner-name retrieval surfaces this fresh topic memory.
        # That's the #614 topic-threading seam, dialogue-tier importance.
        char.agent.memory.add_observation(
            render("reflection", verb="talk_to", person=target_name, topic=topic),
            turn=step,
            importance=convo.DEFAULT_CHAT_IMPORTANCE,
        )
        ac = ActiveConversation(
            a=name,
            b=target_name,
            convo=convo.Conversation(participants=(name, target_name)),
            # The initiator opens: its fresh topic memory (written just above)
            # surfaces in the opener's partner-name retrieval -- topic
            # threading with no new dialogue machinery.
            next_speaker=name,
            started=step,
        )
        active[key] = ac
        ended, delta = _advance_conversation(
            game,
            ac,
            chars,
            state,
            frame,
            step,
            cooldowns,
            max_exchanges,
            clock,
            line_playback_steps,
        )
        completed += delta
        if ended:
            del active[key]
            if not ac.convo.happened:
                continue  # opened with nothing -> reserve no one
        busy.update((name, target_name))

    settled = [
        chars[name]
        for name in order
        if state[name]["performing"] and not state[name]["path"] and name not in busy
    ]
    # First-come matching: once someone is conversing this step, skip any later
    # pair that includes them, so no agent double-writes in one tick (#187).
    spoken: set[str] = set(busy)
    for a, b in convo.find_conversation_pairs(game, settled):
        if a.name in spoken or b.name in spoken:
            continue
        key = frozenset((a.name, b.name))
        if step - cooldowns.get(key, -(10**9)) < cooldown_steps:
            continue
        ac = ActiveConversation(
            a=a.name,
            b=b.name,
            convo=convo.Conversation(participants=(a.name, b.name)),
            next_speaker=a.name,
            started=step,
        )
        active[key] = ac
        ended, delta = _advance_conversation(
            game,
            ac,
            chars,
            state,
            frame,
            step,
            cooldowns,
            max_exchanges,
            clock,
            line_playback_steps,
        )
        completed += delta
        if ended:
            del active[key]
            if not ac.convo.happened:
                continue  # opened with nothing (mock) -> nothing to reserve
        spoken.update((a.name, b.name))  # this pair is busy for the rest of the step

    return completed


def _tile_gap(a, b) -> int:
    """Chebyshev distance between two raw ``(x, y)`` tiles.

    Mid-walk proximity works off the live per-step tiles in ``state`` -- the
    engine's location-footprint distance can't apply here, because ``travel``
    moves ``char.location`` to the destination the instant the command
    resolves, while the sprite is still tiles away walking there."""
    return max(abs(int(a[0]) - int(b[0])), abs(int(a[1]) - int(b[1])))


def _doing(char, st) -> str:
    """What this agent is in the middle of, for the encounter/react prompts.

    Mid-walk the logical location IS the walk's destination (see
    :func:`_tile_gap`); settled, it's the current activity."""
    if st["path"]:
        where = char.location.name if char.location is not None else "somewhere"
        return f"walking to {where}"
    return char.get_property("activity") or "spending time"


def _consult_react(char, other_name: str, st, step: int, clock=None):
    """One ``react`` tool call for *char*: ``(attempted, choice, detail)``.

    Real, tool-calling brain only -- the same brain-identity gate as
    #485/#582/#583 (``attach_agents`` wires the mock brain AS ``agent.schedule``,
    so identity is exactly "no real client supplied"). Billed to *char* under
    ``role: "react"``. What the agent remembers about the other resident is
    retrieved locally (free) and folded into the prompt, so familiarity informs
    the choice without a recall round.

    ``attempted`` is False only when the gate itself failed (no real brain) --
    no call was made. It's True whenever a call was actually placed, whether
    or not the reply came back usable, so the caller can bill every real
    request against the cooldown/cap -- a persistently malformed brain must
    not become an uncapped call storm. A malformed reply degrades to
    ``(True, None, None)`` -- the rule tier alone, no behavior change."""
    agent = char.agent
    brain = getattr(agent, "llm_client", None)
    if (
        brain is None
        or brain is getattr(agent, "schedule", None)
        or not callable(getattr(brain, "call_tool", None))
    ):
        return False, None, None
    ctx = getattr(brain, "context", None)
    if ctx is not None:
        ctx.update({"actor": char.name, "turn": step, "attempt": 0, "role": "react"})
    remembered = agent.memory.retrieve(query=other_name, turn=step, max_records=3)
    messages = [
        {"role": "system", "content": agent._structured_system_message()},
        {
            "role": "user",
            "content": render(
                "react",
                partner=other_name,
                doing=_doing(char, st),
                time=(
                    clock.time_at(step).strftime("%A %I:%M %p")
                    if clock is not None
                    else None
                ),
                memories=[r.text for r in remembered],
            ),
        },
    ]
    # No temperature -> call_tool's default 0.0, deliberately: a three-way
    # classification, like the outcome/score passes (don't "fix" this).
    result = brain.call_tool(messages, REACT_TOOL, max_tokens=agent.max_tokens)
    if not isinstance(result, dict):
        return True, None, None
    choice = result.get("choice")
    if choice not in ("continue", "greet", "replan"):
        return True, None, None
    detail = result.get("detail")
    if isinstance(detail, str) and detail.strip():
        return True, choice, detail.strip()
    return True, choice, None


def maybe_react(
    chars,
    state,
    step,
    cooldowns,
    order,
    *,
    react_state: dict,
    active: dict,
    cooldown_steps: int = CONVERSATION_COOLDOWN_STEPS,
    react_cooldown_steps: int = REACT_COOLDOWN_STEPS,
    react_hour_cap: int = REACT_HOUR_CAP,
    clock=None,
) -> int:
    """Notice-and-maybe-interrupt, once per tick (issue #370).

    Runs in :func:`run_simulation.step` after movement and BEFORE
    :func:`maybe_converse`, so a greet's first line is spoken the same tick by
    the conversation pass's advance phase. Edge-triggered: a pair is handled
    only on the tick it newly comes within *mutual* sight (the smaller of the
    two ``vision_r``, Chebyshev tiles over the live ``state`` positions), and
    ``react_state`` -- caller-owned, persistent across ticks -- remembers who
    was already in range. Per new pair:

    1. **Cheap perceive:** each mid-activity member (walking or performing)
       writes one ``encounter`` observation -- the agent remembers who it
       passed even though no decision point fired. Idle agents are skipped
       (they perceive at their own decision points). At most one record per
       pair per ``react_cooldown_steps`` window, so re-crossings don't flood
       the memory stream with identical records.
    2. **Rule tier (free):** the reactor is the first *walking* member in
       ``order`` -- a fully settled pair is maybe_converse's job. Skipped when
       either member is conversing/busy, when the pair talked recently (the
       same conversation ``cooldowns``), when the reactor reacted recently
       (``react_cooldown_steps``), or past its hourly cap (``react_hour_cap``
       consults per sim hour; 360-step window with no clock). The issue's
       example "known persona" / "schedule has slack" rules are deliberately
       NOT hard gates: an unseeded run would then never react, so familiarity
       is instead retrieved into the react prompt (see
       :func:`_consult_react`) and the model weighs it -- along with the
       schedule context it carries in persona -- itself.
    3. **LLM gate:** one :data:`REACT_TOOL` call (:func:`_consult_react`),
       role ``"react"`` in the ledger. Inert under the mock brain (identity
       gate), so mechanics are testable offline with a scripted client.
    4. **Hand back to existing seams:** ``greet`` inserts a #371
       :class:`ActiveConversation` and pins both ``conversing`` (step()'s
       movement gate pauses a pinned walk; the untouched ``path`` resumes when
       the pin clears); ``replan`` fires :func:`maybe_revise_plan` with the
       backend-local :data:`REACTED` reason. ``continue`` changes nothing --
       the encounter memory already landed.

    Prior art consciously not reused (issue scope): the engine's
    ``npc.react_behavior`` is the per-turn ReAct loop for ``take_turn``-driven
    NPCs -- this loop never calls ``take_turn`` and already reproduces its
    perceive->retrieve->decide wiring in :func:`observe_and_decide`; and
    ``reactions.py``'s thing-owned reflexes are *scripted* gate->effect
    triggers evaluated by the engine's round phase, with no brain consult and
    no knowledge of this loop's path/performing state machine. What #370 needs
    is a rate-limited brain consult keyed on tile proximity mid-walk, which
    neither provides.

    Returns how many LLM react consults were made this tick.
    """
    idx = {n: i for i, n in enumerate(order)}
    # O(n^2) pair scan over live tiles -- fine at this sim's scale (~25 agents,
    # the same budget as tiled_game's perception scan).
    in_range: set[frozenset] = set()
    for i, a_name in enumerate(order):
        for b_name in order[i + 1 :]:
            radius = min(
                getattr(chars[a_name], "vision_r", 0),
                getattr(chars[b_name], "vision_r", 0),
            )
            if radius > 0 and (
                _tile_gap(state[a_name]["tile"], state[b_name]["tile"]) <= radius
            ):
                in_range.add(frozenset((a_name, b_name)))
    new_pairs = in_range - react_state.get("in_range", set())
    react_state["in_range"] = in_range

    last_react = react_state.setdefault("last_react", {})
    last_encounter = react_state.setdefault("last_encounter", {})
    consult_log = react_state.setdefault("consults", {})
    window = (
        clock.steps_for_seconds(3600)
        if clock is not None
        else REACT_HOUR_FALLBACK_STEPS
    )
    consults = 0
    for key in sorted(new_pairs, key=lambda k: sorted(idx[n] for n in k)):
        a_name, b_name = sorted(key, key=idx.get)
        # (1) Cheap perceive: mid-activity members remember the encounter --
        # at most once per pair per react-cooldown window, so two agents
        # pacing in and out of mutual range don't flood both memory streams
        # with identical records all day (PR #650 review).
        seen = last_encounter.get(key)
        if seen is None or step - seen >= react_cooldown_steps:
            for me, other in ((a_name, b_name), (b_name, a_name)):
                st = state[me]
                if not (st["path"] or st["performing"]):
                    continue
                chars[me].agent.memory.add_observation(
                    render("encounter", partner=other, doing=_doing(chars[me], st)),
                    turn=step,
                    importance=ENCOUNTER_IMPORTANCE,
                )
                last_encounter[key] = step
        # (2) Rule tier.
        reactor = next((n for n in (a_name, b_name) if state[n]["path"]), None)
        if reactor is None:
            continue
        other = b_name if reactor == a_name else a_name
        if state[reactor].get("conversing") or state[other].get("conversing"):
            continue
        busy = {n for ac in active.values() for n in (ac.a, ac.b)}
        if reactor in busy or other in busy:
            continue
        if step - cooldowns.get(key, -(10**9)) < cooldown_steps:
            continue  # they talked recently; crossing paths again isn't news
        last = last_react.get(reactor)
        if last is not None and step - last < react_cooldown_steps:
            continue
        recent = [s for s in consult_log.get(reactor, []) if step - s < window]
        if len(recent) >= react_hour_cap:
            consult_log[reactor] = recent  # prune while we're here
            continue
        # (3) The LLM gate. Cap/cooldown bookkeeping keys on the ATTEMPT --
        # every real request counts, usable reply or not, so a brain that
        # answers the react tool badly can't become an uncapped call storm.
        attempted, choice, detail = _consult_react(
            chars[reactor], other, state[reactor], step, clock=clock
        )
        if not attempted:
            continue  # no real tool-calling brain: rule tier only
        last_react[reactor] = step
        consult_log[reactor] = recent + [step]
        consults += 1
        if choice is None:
            continue  # reply unusable: billed + capped, but no behavior change
        # (4) Hand back to the existing seams.
        if choice == "greet":
            ac = ActiveConversation(
                a=reactor,
                b=other,
                convo=convo.Conversation(participants=(reactor, other)),
                next_speaker=reactor,
                started=step,
            )
            active[key] = ac
            state[reactor]["conversing"] = True
            state[other]["conversing"] = True
        elif choice == "replan":
            maybe_revise_plan(
                chars[reactor],
                RevisionTrigger(REACTED, step, detail or f"I noticed {other} nearby"),
                clock,
            )
    return consults
