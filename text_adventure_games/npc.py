"""Agent decision layer for LLM-driven (and scripted) NPC behavior.

The seam is ``Agent.decide(observation) -> command``: a pure function from an
observation string to a single raw command string. An ``Agent`` owns the
character's *mind* -- its persona, goals, and a private :class:`~text_adventure_games.memory.AgentMemory`
stream (issue #75). Two backends sit behind the same seam and are interchangeable:

* ``LLMAgent`` -- real reasoning via an :class:`LlmClient` (or a legacy
  ``(str) -> str`` callable).
* ``ScriptedAgent`` -- a deterministic rule ``(observation) -> command``, for
  tests and cheap NPCs that don't need an LLM.

The surrounding Observe -> Act -> Reflect cycle (building the observation,
routing the command through the parser's precondition gate, and feeding a
failure back on retry) lives *outside* ``decide()`` in :func:`react_behavior`.
That loop is bridged onto a character two ways: via the legacy
``set_behavior`` hook through :func:`make_react_behavior` /
:func:`make_hybrid_behavior` (sequential mode), or via
``Character.set_agent``, which lets the simultaneous gather -> resolve loop
in ``turns.py`` (issue #25) call ``decide()`` directly. Keeping ``decide()``
free of ``game`` is what lets the agent layer be unit-tested offline with
``MockLlmClient``.

See ``docs/design/multi-character-play.md`` (issue #3).

Usage::

    from text_adventure_games.npc import make_react_behavior, make_hybrid_behavior

    troll.set_behavior(make_react_behavior(llm_client))
    troll.set_behavior(make_hybrid_behavior(llm_client, make_troll_behavior()))
"""

from __future__ import annotations

import re

from . import prompt_templates
from .actions.base import HIDDEN_ACTIONS, registered_action_entries
from .config import AgentConfig
from .enums import ReActLabel, Role
from .llm_client import run_tool_loop
from .memory import AgentMemory, render_memories
from .planning import plan_memory_lines
from .reflection import DEFAULT_REFLECTION_THRESHOLD, reflect, should_reflect
from .things.characters import Goal, GoalType

# Lowercase label tokens used by _parse_decision. Built from ReActLabel so the
# prompt template, the parser, and any future label additions stay in sync.
# either "thought" or "reasoning" get categorized as "_REASONING_TOKENS"
_REASONING_TOKENS = (
    ReActLabel.REASONING.lower(),
    ReActLabel.THOUGHT.lower(),
)
_ACTION_TOKEN = ReActLabel.ACTION.lower()
_DURATION_TOKEN = ReActLabel.DURATION.lower()

# Upper bound for an LLM-estimated action duration: one in-game day. Guards
# against a model returning an absurd number that would let one action soak up
# many turns' worth of budget.
_MAX_DURATION = 24 * 60


# Dialogue seam (issue #86). A conversation asks the agent for one line at a
# time; `done` lets it bow out gracefully after a closing line. The dialogue
# system message (persona/goals + the one-line instruction) is rendered from the
# npc_dialogue template; see LLMAgent._dialogue_system_message.


def build_speak_tool() -> dict:
    """Normalized ``speak`` tool: one line of dialogue plus a wrap-up flag.

    ``utterance`` is what the agent says next; an empty string means "say nothing
    and end the conversation." ``done`` lets the agent signal this is its closing
    line so the loop stops after delivering it (a goodbye still gets heard)."""
    return {
        "name": "speak",
        "description": "Say the next line in the conversation, or end it.",
        "parameters": {
            "type": "object",
            "properties": {
                "utterance": {
                    "type": "string",
                    "description": (
                        "what you say next, in character; '' to say nothing and "
                        "end the conversation"
                    ),
                },
                "done": {
                    "type": "boolean",
                    "description": "true if this is your final line (wrapping up)",
                },
            },
            "required": ["utterance"],
        },
    }


def _parse_duration(text: str, max_duration: int = _MAX_DURATION) -> int | None:
    """Pull an in-game-minute count out of a "Duration:" line's value.

    Extracts the first integer (so "about 30 minutes" -> 30), rejects
    non-positive values as invalid, and clamps anything larger than
    *max_duration* (the agent's configured cap, defaulting to
    :data:`_MAX_DURATION`). Returns ``None`` when no usable number is present.
    """
    match = re.search(r"-?\d+", text)
    if match is None:
        return None
    value = int(match.group())
    if value <= 0:
        return None
    return min(value, max_duration)


def build_choose_action_tool(action_names: list[str]) -> dict:
    """Build the normalized `choose_action` tool schema for the agent.

    When *action_names* is non-empty, the `action` field is a closed ``enum``
    over those verbs, so a tool-calling model can only pick a command the parser
    knows. When empty (e.g. a direct ``decide()`` caller that never set them),
    `action` is a plain string -- the seam still works, just less constrained.
    `arguments` is free text (the rest of the command); the engine's existing
    resolver and precondition gate turn it into entities.
    """
    action_property = {"type": "string", "description": "the verb to perform"}
    if action_names:
        action_property["enum"] = list(action_names)
    return {
        "name": "choose_action",
        "description": "Choose the single game command to perform this turn.",
        "parameters": {
            "type": "object",
            "properties": {
                "reasoning": {
                    "type": "string",
                    "description": "one short sentence explaining the choice",
                },
                "action": action_property,
                "arguments": {
                    "type": "string",
                    "description": (
                        "the rest of the command, e.g. 'player with club'; "
                        "'' if none"
                    ),
                },
            },
            "required": ["action"],
        },
    }


# ----------------------------------------------------------------------
# Per-action tool schemas, derived from the action registry (issue #356)
#
# The idiomatic N-tools shape: one tool per registered verb (used with
# tool_choice="any"), instead of a single choose_action whose `action` is an
# enum. build_choose_action_tool above stays the fallback for clients without
# multi-tool support and for the free-text path.
# ----------------------------------------------------------------------

# Scope categories a tool argument slot may declare (Action.ARGUMENTS_SCHEMA):
# each is filled at decision time with an enum of the entities the actor can
# currently see -- the same scope game.describe_for() renders as prose.
_SCOPE_KINDS = ("item", "character", "direction")
# JSON primitives a slot may declare directly (anything else falls back to string).
_JSON_TYPES = ("string", "integer", "number", "boolean")
# Cap on how many entities a scope enum may list. Past it we DROP the enum and
# leave the slot free text: truncating would make a valid entity unnameable, and
# a very long enum bloats the tool definition -- which counts against context and
# is NOT trimmed by limit_context_length. Games with big rooms can tune this.
_MAX_SCOPE_ENUM = 20


def _tool_name(verb: str) -> str:
    """Sanitize a registry verb into a provider-valid tool name (issue #356).

    Anthropic and OpenAI require tool names to match ``^[A-Za-z0-9_-]{1,64}$`` --
    no spaces -- but multi-word verbs are keyed WITH spaces ("adopt goal", "ghost
    touch", "take off"). Left as-is these would 400 the moment an agent runs on a
    real key (the very mode #356 targets), even though the offline mock never
    validates them. So each run of disallowed characters becomes ``_`` and the
    result is length-capped. Registry keys never contain ``_`` themselves
    (``action_name()`` strips it and explicit names use spaces), so
    :func:`command_from_tool_call` recovers the original verb by matching the
    registry key whose sanitized form equals the tool name."""
    safe = re.sub(r"[^A-Za-z0-9_-]+", "_", verb).strip("_")
    return safe[:64] or "action"


def _scope_enum(kind: str, parser, actor) -> list[str] | None:
    """In-scope entity names for a scope-category slot, or ``None`` when *kind*
    is a plain JSON type (not a scope category) or there's no actor to scope to.

    Reuses the parser's own scope resolution so the enum and ``describe_for()``
    never disagree about what's here: items the actor can see or carry, other
    characters in the room, or exits."""
    if kind not in _SCOPE_KINDS or actor is None:
        return None
    loc = getattr(actor, "location", None)
    if kind == "item":
        return sorted(parser.get_items_in_scope(actor).keys())
    if loc is None:
        return []
    if kind == "character":
        return sorted(name for name in loc.characters if name != actor.name)
    return list(loc.connections.keys())  # direction


def _slot_property(slot: dict, parser, actor, max_enum: int | None) -> dict:
    """Translate one ARGUMENTS_SCHEMA slot into a JSON-schema property.

    A scope slot becomes a string constrained to an enum of the actor's in-scope
    entities (dropped when there are none, or too many to list within
    *max_enum*); a plain-typed slot passes its JSON type through."""
    kind = slot.get("type", "string")
    prop = {"type": "string", "description": slot.get("description", "")}
    enum = _scope_enum(kind, parser, actor)
    if enum is None:
        prop["type"] = kind if kind in _JSON_TYPES else "string"
    elif enum and (max_enum is None or len(enum) <= max_enum):
        prop["enum"] = enum
    return prop


def _build_action_tool(name, action, description, aliases, parser, actor, max_enum):
    """Build one normalized per-action tool. The tool NAME is the verb;
    ``reasoning`` is always offered (so the trace still shows *why*). A declared
    ``ARGUMENTS_SCHEMA`` becomes typed slots (with scope enums where the actor's
    view allows); an undeclared action falls back to a single free-text
    ``arguments`` field -- the same contract ``choose_action`` used, so no
    built-in action needs migrating."""
    desc = description or f"Perform the '{name}' action."
    if aliases:
        desc += f" (aliases: {', '.join(aliases)})"
    properties = {
        "reasoning": {
            "type": "string",
            "description": "one short sentence explaining the choice",
        }
    }
    required: list[str] = []
    schema = getattr(action, "ARGUMENTS_SCHEMA", None) if action is not None else None
    if schema:
        for slot_name, slot in schema.items():
            properties[slot_name] = _slot_property(slot, parser, actor, max_enum)
            if slot.get("required"):
                required.append(slot_name)
    else:
        properties["arguments"] = {
            "type": "string",
            "description": "the rest of the command, e.g. 'player with club'; '' if none",
        }
    return {
        # Sanitized so multi-word verbs ("adopt goal") are valid provider tool
        # names; command_from_tool_call recovers the registry verb from it.
        "name": _tool_name(name),
        "description": desc,
        "parameters": {
            "type": "object",
            "properties": properties,
            "required": required,
        },
    }


def tools_for(parser, actor=None, names=None, max_enum: int | None = _MAX_SCOPE_ENUM):
    """Derive one normalized tool per registered action (issue #356).

    The N-tools counterpart to :func:`build_choose_action_tool`: instead of one
    ``choose_action`` whose ``action`` is an enum of verbs, each verb becomes its
    own tool (offered with ``tool_choice="any"``), typed by its
    ``ARGUMENTS_SCHEMA`` and -- when *actor* is given -- narrowed with scope enums
    drawn from what that actor can currently see.

    *names* limits which verbs are exposed (pass the agent's ``action_names``;
    ``None`` or empty means every registered verb -- "unconstrained", mirroring
    the legacy ``build_choose_action_tool([])``, NOT "no tools". A game that
    wants an agent to have no menu must keep it off this path rather than pass
    ``[]``). The comma-sequence wrapper is always dropped. A name with no
    registered action still gets a generic free-text tool, so ``action_names``
    stays the authoritative menu even when it lists a verb the parser hasn't
    registered.

    Token budget: tool definitions count against context and are NOT trimmed by
    :func:`~text_adventure_games.llm_client.limit_context_length`, so scope enums
    are capped (see :data:`_MAX_SCOPE_ENUM`) and a caller may pass a narrower
    *names* to curate the set per decision.
    """
    entries = {
        name: (action, desc, aliases)
        for name, action, desc, aliases in registered_action_entries(parser)
    }
    wanted = list(names) if names else list(entries)
    tools = []
    seen = set()
    verb_by_tool_name: dict[str, str] = {}
    for name in wanted:
        if name in HIDDEN_ACTIONS or name in seen:
            continue
        seen.add(name)
        action, desc, aliases = entries.get(name, (None, "", []))
        tool = _build_action_tool(name, action, desc, aliases, parser, actor, max_enum)
        clash = verb_by_tool_name.get(tool["name"])
        if clash is not None:
            # Two verbs sanitizing (or 64-capping) to one tool name would ship
            # duplicate tools and 400 at the provider; fail at build time with
            # the colliding verbs named instead.
            raise ValueError(
                f"per-action tool name collision: verbs {clash!r} and {name!r} "
                f"both sanitize to tool name {tool['name']!r}"
            )
        verb_by_tool_name[tool["name"]] = name
        tools.append(tool)
    return tools


def command_from_args(verb: str, args: dict, schema: dict | None) -> str:
    """Reassemble a raw command string from a per-action tool call's arguments.

    An undeclared action carries a single free-text ``arguments`` slot, so the
    command is just ``"<verb> <arguments>"``. A declared ``ARGUMENTS_SCHEMA``
    lists its slots in order; each present value is appended after its optional
    ``connector`` word, so ``{"target": "player", "weapon": "club"}`` on an attack
    whose weapon slot declares connector ``"with"`` assembles ``"attack player
    with club"``. The parser's matchers then resolve those names to entities
    exactly as for typed human input -- and the precondition gate still decides."""
    if not schema:
        rest = (args.get("arguments") or "").strip()
        return f"{verb} {rest}".strip()
    parts = [verb]
    for slot_name, slot in schema.items():
        value = args.get(slot_name)
        if value is None or value == "":
            continue
        connector = slot.get("connector")
        if connector:
            parts.append(str(connector))
        parts.append(str(value))
    return " ".join(parts).strip()


def command_from_tool_call(name: str, args: dict, parser) -> str:
    """Turn a single tool call into a raw command string for the parser.

    Backward-compatible with the single ``choose_action`` tool -- where the verb
    rides in ``args['action']`` and the rest is free text -- and with the #356
    per-action tools, where the verb IS the tool name and the slots come from the
    action's ``ARGUMENTS_SCHEMA``. Either shape becomes a command string routed
    through the same precondition gate; schemas only shrink the space of invalid
    *phrasings*, never the gate's authority over invalid *acts*."""
    if name == "choose_action":
        verb = (args.get("action") or "").strip()
        return command_from_args(verb, args, None)
    verb, action = _registry_verb(name, parser)
    schema = getattr(action, "ARGUMENTS_SCHEMA", None) if action is not None else None
    return command_from_args(verb, args, schema)


def _registry_verb(tool_name: str, parser):
    """Recover ``(verb, action)`` for a per-action tool name (issue #356).

    The name may be a registry verb verbatim, or its sanitized form (see
    :func:`_tool_name`) when the verb had spaces ("adopt_goal" for "adopt goal").
    We match the registry key whose sanitized form equals *tool_name* so the
    reassembled command uses the SPOKEN verb the parser routes on. Falls back to
    ``(tool_name, None)`` when nothing matches, so an unregistered name still
    assembles a best-effort command (the gate then rejects it)."""
    if parser is None:
        return tool_name, None
    action = parser.actions.get(tool_name)
    if action is not None:
        return tool_name, action
    for key, act in parser.actions.items():
        if _tool_name(key) == tool_name:
            return key, act
    return tool_name, None


# ----------------------------------------------------------------------
# Cognition tools: agentic memory/knowledge/plan retrieval (issue #358)
#
# Optional tools offered ALONGSIDE the action tools in the bounded tool loop,
# so an agent can consult its own memory / beliefs / plan when IT decides it
# needs to, instead of the engine guessing (the fixed retrieve-then-prompt
# pipeline in react_behavior, which remains the default and is kept even when
# these are on). Opt-in via AgentConfig.cognition_tools; each tool is an
# in-process call on the agent's own state -- no HTTP, no other agent's data.
# ----------------------------------------------------------------------

# How many cognition (retrieval) calls an agent may make per decision episode
# before further ones are refused and it must act. run_tool_loop offers one
# fixed toolset for every round, so the budget is enforced inside the execute
# callback (an is_error "budget exhausted" tool_result) rather than by
# narrowing the offered tools mid-loop -- the smaller diff given the loop's
# actual shape.
COGNITION_BUDGET = 2


def build_recall_tool() -> dict:
    """Normalized ``recall`` tool: search the agent's own episodic memory."""
    return {
        "name": "recall",
        "description": (
            "Search your own memories for what you know about something. "
            "Returns your most relevant memories."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "query": {
                    "type": "string",
                    "description": "what to search your memory for",
                },
                "k": {
                    "type": "integer",
                    "description": (
                        "how many memories to return (optional; defaults to a "
                        "small handful)"
                    ),
                },
            },
            "required": ["query"],
        },
    }


def build_query_knowledge_tool() -> dict:
    """Normalized ``query_knowledge`` tool: look up the agent's own beliefs."""
    return {
        "name": "query_knowledge",
        "description": "Look up what you believe about a topic.",
        "parameters": {
            "type": "object",
            "properties": {
                "topic": {
                    "type": "string",
                    "description": "the topic to look up in your beliefs",
                },
            },
            "required": ["topic"],
        },
    }


def build_read_plan_tool() -> dict:
    """Normalized ``read_plan`` tool: read the agent's plan for today."""
    return {
        "name": "read_plan",
        "description": "Read your plan for today (outline, hours, and stops).",
        "parameters": {"type": "object", "properties": {}, "required": []},
    }


def cognition_toolset(agent, knowledge=None, turn=None, trace=None):
    """Build ``(tools, execute)`` for the agent's cognition tools (issue #358).

    Each tool is offered only when its source is attached AND non-empty (never
    offer a tool that can only come back empty): ``recall`` reads the agent's
    own :class:`~text_adventure_games.memory.AgentMemory`, ``query_knowledge``
    the passed *knowledge* (the character's beliefs -- the caller passes it
    because knowledge lives on the character, not the agent), and ``read_plan``
    the sim-builder convention ``agent.plan`` (a
    :class:`~text_adventure_games.planning.DailyPlan`).

    ``execute(name, args)`` returns the run_tool_loop 3-tuple for a cognition
    call -- ``(formatted result, False, False)`` so the loop continues and the
    agent still acts -- or ``None`` when *name* is not a cognition tool (route
    it as an action). After :data:`COGNITION_BUDGET` calls, further ones get an
    ``is_error`` "budget exhausted" result; any exception inside a tool becomes
    an ``is_error`` result too, never a crash of the turn. *trace* (optional,
    ``(str) -> None``) receives one summary line per successful call for the
    private AGENT_* channels. *turn* stamps retrieval recency; ``None`` falls
    back to the newest memory's turn (the conversation path has no game clock).
    """
    memory = getattr(agent, "memory", None)
    plan = getattr(agent, "plan", None)
    if turn is None:
        records = getattr(memory, "records", None)
        turn = records[-1].created_turn if records else 0
    handlers = {}
    tools = []

    if memory is not None and memory.records:

        def _recall(args):
            query = str(args.get("query") or "").strip()
            kwargs = {}
            k = args.get("k")
            if isinstance(k, int) and not isinstance(k, bool) and k > 0:
                kwargs["max_records"] = k
            found = memory.retrieve(query=query, turn=turn, **kwargs)
            text = render_memories(found) or "No relevant memories."
            return text, f"recall({query!r}) -> {len(found)} memories"

        handlers["recall"] = _recall
        tools.append(build_recall_tool())

    if knowledge is not None and getattr(knowledge, "beliefs", None):

        def _query_knowledge(args):
            topic = str(args.get("topic") or "").strip()
            needle = topic.lower()
            matched = [
                b
                for b in knowledge.beliefs
                if (b.topic and b.topic.lower() == needle) or needle in b.text.lower()
            ]
            summary = f"query_knowledge({topic!r}) -> {len(matched)} beliefs"
            if not matched:
                return f"You hold no beliefs about '{topic}'.", summary
            # Same bullet shape as Knowledge.render, narrowed to the topic.
            lines = [f"What you know about {topic}:"]
            lines.extend(f" - {b.text}" for b in matched)
            return "\n".join(lines), summary

        handlers["query_knowledge"] = _query_knowledge
        tools.append(build_query_knowledge_tool())

    if plan is not None and (plan.stops or plan.hours or plan.day):

        def _read_plan(args):
            lines = plan_memory_lines(plan)
            return "\n".join(lines), f"read_plan() -> {len(lines)} lines"

        handlers["read_plan"] = _read_plan
        tools.append(build_read_plan_tool())

    state = {"used": 0}

    def execute(name, args):
        handler = handlers.get(name)
        if handler is None:
            return None
        if state["used"] >= COGNITION_BUDGET:
            return (
                "Retrieval budget exhausted -- you must act now.",
                True,
                False,
            )
        state["used"] += 1
        try:
            result, summary = handler(args or {})
        except Exception as exc:  # never crash the turn on a retrieval bug
            return (f"{name} failed: {exc}", True, False)
        if trace is not None:
            trace(summary)
        return (result, False, False)

    return tools, execute


def _parse_decision(
    text: str, max_duration: int = _MAX_DURATION
) -> tuple[str | None, str | None, int | None]:
    """Split an LLM reply into ``(reasoning, command, duration)``.

    Understands the labeled format requested by the ``npc_decision`` prompt
    template ("Reasoning: ...\\nAction: ...\\nDuration: ..."; "Thought:" is accepted as a
    synonym for the reasoning line). ``duration`` is the estimated in-game
    minutes for the action (clamped to *max_duration*), or ``None`` when the
    line is absent or unusable. Falls back to treating the first non-empty line
    as a bare command, so models (and tests) that reply with just the command
    keep working.
    """
    reasoning = None
    command = None
    duration = None
    first_line = None
    for raw in text.splitlines():
        line = raw.strip()
        if not line:
            continue
        if first_line is None:
            first_line = line
        lowered = line.lower()
        if reasoning is None and lowered.startswith(_REASONING_TOKENS):
            reasoning = line.split(":", 1)[1].strip() or None
        elif command is None and lowered.startswith(_ACTION_TOKEN):
            command = line.split(":", 1)[1].strip() or None
        elif duration is None and lowered.startswith(_DURATION_TOKEN):
            duration = _parse_duration(line.split(":", 1)[1], max_duration)
    if command is None and first_line is not None:
        # No "Action:" label anywhere: treat the first line as the command,
        # unless it was a reasoning line (then there is no action this turn).
        if not first_line.lower().startswith(_REASONING_TOKENS):
            command = first_line
    return reasoning, command, duration


# ----------------------------------------------------------------------
# The decision seam: Agent.decide(observation) -> command
# ----------------------------------------------------------------------


class Agent:
    """Decision-maker attached to a non-human character.

    Owns the character's mind: ``persona`` (a first-person string), ``goals``
    (what it wants), and ``memory`` (a private append-only
    :class:`~text_adventure_games.memory.AgentMemory` stream, issue #75). The
    single required behavior is :meth:`decide`: given an observation string,
    return one raw command string, or ``None`` to act on nothing this turn.
    Subclasses supply the backend.
    """

    def __init__(
        self,
        persona: str = "",
        goals: list[Goal] | None = None,
        embedding_client=None,
        reflector=None,
        reflection_threshold: float = DEFAULT_REFLECTION_THRESHOLD,
    ):
        self.persona = persona
        self.goals: list[Goal] = list(goals) if goals else []
        # Private, append-only episodic memory (issue #75). Per-agent: the ReAct
        # loop fills in the owner the first time the agent acts. Empty by default
        # and only ever read into this agent's own prompt, so an agent that
        # never accrues memories behaves exactly as before. An optional
        # embedding_client (issue #76) upgrades retrieval relevance from keyword
        # overlap to semantic similarity; None keeps the deterministic default.
        self.memory = AgentMemory(owner="", embedding_client=embedding_client)
        # Optional periodic-reflection backend (issue #84). With none (the
        # default), the ReAct loop never synthesizes reflections and behavior is
        # byte-identical to before; pass a Reflector (see ``reflection.py``) to
        # have the agent turn recent memories into higher-level thoughts once
        # accumulated importance crosses ``reflection_threshold``.
        self.reflector = reflector
        self.reflection_threshold = reflection_threshold
        # Why the agent chose its last command. Subclasses may set this in
        # decide(); the ReAct loop logs it next to the chosen action.
        self.last_reasoning: str | None = None
        # The agent's estimate (in-game minutes) for its last command, or None
        # if it gave no estimate. The turn loop prefers this over the action's
        # declared DURATION when charging the per-turn budget (issue #24).
        self.last_duration: int | None = None
        # The verbs this agent may choose from, used to build the closed-enum
        # `action` field of the choose_action tool. Set per-turn by the behavior
        # factories / turns.py from game.parser.actions; empty means
        # unconstrained (the enum is omitted). Only LLMAgent's structured path
        # reads it; ScriptedAgent ignores it.
        self.action_names: list[str] = []
        # Dialogue seam (issue #86): set True by converse() when the agent's last
        # line was a wrap-up, so the conversation loop can stop after it. Reset at
        # the start of each converse() call.
        self.last_dialogue_done: bool = False

    def decide(self, observation: str) -> str | None:
        """Return a single command string for *observation* (or ``None``)."""
        raise NotImplementedError("Agent subclasses must implement decide().")

    def converse(self, observation: str, partner_name: str) -> str | None:
        """Return the next line this agent says to *partner_name* (issue #86).

        ``observation`` carries who the agent is talking with and the dialogue so
        far. Return the utterance, or ``None`` to say nothing and end the
        conversation. The base implementation is silent (``None``) so an agent
        with no dialogue backend -- or a non-conversational mock brain -- simply
        never starts or sustains a conversation, leaving existing behavior
        unchanged. Subclasses that can talk override this.
        """
        return None


class LLMAgent(Agent):
    """Agent that decides by asking an LLM.

    Accepts either an :class:`LlmClient` (anything with a ``chat()`` method) or
    a legacy ``(str) -> str`` callable. The persona and goals are sent as the
    system message; the observation is the user message.

    ``decide()`` prefers a structured tool call when the client supports one
    (``call_tool``): the model fills the ``choose_action`` schema and the agent
    assembles ``"<action> <arguments>"``. When tool calling is unavailable or
    returns nothing, it falls back to the free-text path -- parsing the command
    from the reply's "Action:" line (or, for unlabeled replies, its first
    line). Either way the "Reasoning:" is recorded in ``last_reasoning``.
    Returns ``None`` if the client failed or said nothing.
    """

    _TIER_LABELS = {
        GoalType.SHORT: "Short-term",
        GoalType.MEDIUM: "Medium-term",
        GoalType.LONG: "Long-term",
    }

    def __init__(
        self,
        llm_client,
        persona: str = "",
        goals: list[Goal] | None = None,
        max_tokens: int = 128,
        temperature: float = 0.7,
        max_duration: int = _MAX_DURATION,
        embedding_client=None,
        reflector=None,
        reflection_threshold: float = DEFAULT_REFLECTION_THRESHOLD,
        cognition_tools: bool = False,
    ):
        super().__init__(
            persona=persona,
            goals=goals,
            embedding_client=embedding_client,
            reflector=reflector,
            reflection_threshold=reflection_threshold,
        )
        self.llm_client = llm_client
        self.max_tokens = max_tokens
        self.temperature = temperature
        self.max_duration = max_duration
        # Cognition tools (issue #358): when True (and the client supports
        # call_tools), recall / query_knowledge / read_plan are offered
        # alongside the action tools so the agent can consult its own state
        # before acting. Default False keeps every path byte-identical.
        self.cognition_tools = cognition_tools
        # One summary line per cognition call the agent made while producing
        # its last dialogue line (the dialogue seam has no parser reference, so
        # conversation.converse reads this buffer and emits the AGENT_* trace).
        self.last_cognition_trace: list[str] = []

    def decide(self, observation: str) -> str | None:
        self.last_reasoning = None
        self.last_duration = None
        structured = self._decide_structured(observation)
        if structured is not None:
            return structured
        return self._decide_freetext(observation)

    def _decide_structured(self, observation: str) -> str | None:
        """Tool-calling path: ask the model to fill the choose_action schema and
        assemble '<action> <arguments>'. Returns None when tool calling is
        unavailable or produced nothing, so decide() falls back to free text.
        The closed `action` enum guarantees a verb the parser knows; the
        command still re-enters the precondition gate via decide_and_route."""
        if not hasattr(self.llm_client, "call_tool"):
            return None
        tool = build_choose_action_tool(self.action_names)
        messages = [
            {"role": "system", "content": self._structured_system_message()},
            {"role": "user", "content": observation},
        ]
        result = self.llm_client.call_tool(
            messages, tool, max_tokens=self.max_tokens, temperature=self.temperature
        )
        if not result:
            return None
        self.last_reasoning = (result.get("reasoning") or "").strip() or None
        action = (result.get("action") or "").strip()
        arguments = (result.get("arguments") or "").strip()
        command = f"{action} {arguments}".strip()
        return command or None

    def _decide_freetext(self, observation: str) -> str | None:
        """The original chat()+_parse_decision path, used as a graceful fallback
        when structured tool calling is unavailable or returns nothing."""
        response = self._call(observation)
        if response is None:
            return None
        reasoning, command, duration = _parse_decision(
            response, max_duration=self.max_duration
        )
        self.last_reasoning = reasoning
        self.last_duration = duration
        return command

    def converse(self, observation: str, partner_name: str) -> str | None:
        """Ask the model for the next line of dialogue (issue #86).

        Prefers the structured ``speak`` tool (``utterance`` + ``done``) and falls
        back to a single free-text line, mirroring how :meth:`decide` prefers
        ``choose_action`` then free text. Returns the utterance, or ``None`` to
        end the conversation; sets :attr:`last_dialogue_done` when the model
        flags this as its closing line. A client that can't fill the tool *and*
        returns nothing from chat (e.g. the non-conversational schedule mock)
        yields ``None``, so no conversation happens -- which is what keeps the
        default offline run silent and byte-identical.

        With :attr:`cognition_tools` on (issue #358) and a ``call_tools``-capable
        client, the agent first gets a bounded chance to ``recall`` /
        ``read_plan`` before speaking (see :meth:`_converse_with_cognition`);
        with the flag off, this path is byte-identical to before."""
        self.last_dialogue_done = False
        self.last_cognition_trace = []
        if self.cognition_tools and hasattr(self.llm_client, "call_tools"):
            spoken = self._converse_with_cognition(observation)
            if spoken is not None:
                return spoken
        spoken = self._converse_structured(observation)
        if spoken is not None:
            return spoken
        return self._converse_freetext(observation)

    def _converse_with_cognition(self, observation: str) -> str | None:
        """Dialogue grounded in what the agent chose to recall (issue #358).

        Offers the cognition tools alongside ``speak`` in a bounded
        :func:`~text_adventure_games.llm_client.run_tool_loop`, so the agent can
        consult its own memory/plan (up to :data:`COGNITION_BUDGET` calls)
        before its line. ``query_knowledge`` is not offered here: beliefs live
        on the character, which the dialogue seam cannot reach. Returns the
        utterance, or ``None`` to fall back to the plain structured/free-text
        paths (a declining client, no cognition sources, or no usable line).
        Each retrieval is buffered in :attr:`last_cognition_trace` for the
        conversation loop to emit on the private AGENT_* channels.
        """
        cog_tools, cognition_execute = cognition_toolset(
            self, trace=self.last_cognition_trace.append
        )
        if not cog_tools:
            # Nothing to consult -- the plain single-speak path costs less.
            return None
        tools = cog_tools + [build_speak_tool()]
        messages = [
            {"role": "system", "content": self._structured_system_message()},
            {"role": "user", "content": observation},
        ]
        state: dict = {}

        def execute(name, args):
            consulted = cognition_execute(name, args)
            if consulted is not None:
                return consulted
            if name == "speak":
                state["utterance"] = (args.get("utterance") or "").strip()
                state["done"] = bool(args.get("done"))
                return ("Done.", False, True)
            return (f"Unknown tool '{name}'. Use speak.", True, False)

        run_tool_loop(
            self.llm_client,
            messages,
            tools,
            execute,
            max_rounds=1 + COGNITION_BUDGET,
            tool_choice="any",
            max_tokens=self.max_tokens,
            temperature=self.temperature,
        )
        utterance = state.get("utterance") or ""
        if not utterance:
            return None
        self.last_dialogue_done = bool(state.get("done"))
        return utterance

    def _converse_structured(self, observation: str) -> str | None:
        """Tool-calling path: fill the ``speak`` schema. Returns ``None`` (so
        converse() falls back to free text) when tool calling is unavailable or
        the result carries no usable ``utterance`` -- the latter is also how a
        mock brain answering with a non-dialogue schema stays silent."""
        if not hasattr(self.llm_client, "call_tool"):
            return None
        messages = [
            {"role": "system", "content": self._structured_system_message()},
            {"role": "user", "content": observation},
        ]
        result = self.llm_client.call_tool(
            messages,
            build_speak_tool(),
            max_tokens=self.max_tokens,
            temperature=self.temperature,
        )
        if not isinstance(result, dict) or "utterance" not in result:
            return None
        self.last_dialogue_done = bool(result.get("done"))
        return (result.get("utterance") or "").strip() or None

    def _converse_freetext(self, observation: str) -> str | None:
        """Free-text fallback: take the model's reply as the spoken line."""
        if not hasattr(self.llm_client, "chat"):
            return None
        messages = [
            {"role": Role.SYSTEM, "content": self._dialogue_system_message()},
            {"role": Role.USER, "content": observation},
        ]
        response = self.llm_client.chat(
            messages, max_tokens=self.max_tokens, temperature=self.temperature
        )
        return (response or "").strip() or None

    def _dialogue_system_message(self) -> str:
        # Free-text dialogue path: persona/goals plus the one-line instruction,
        # rendered from the npc_dialogue template (issue #145).
        return prompt_templates.render(
            "npc_dialogue",
            persona=self.persona,
            goals_block=self._format_goals() or "",
        )

    def _format_goals(self) -> str | None:
        """Render incomplete goals grouped by tier, in SHORT/MEDIUM/LONG order.
        Empty tiers are skipped so the prompt never shows a bare header with
        nothing under it. Returns None when there are no active goals at all."""
        sections = []
        for tier in GoalType:
            active = [g for g in self.goals if g.type == tier and not g.done]
            if not active:
                continue
            bullets = "\n".join(f"  - {g.description}" for g in active)
            sections.append(f"{self._TIER_LABELS[tier]}:\n{bullets}")
        return "\n".join(sections) if sections else None

    def _render_system(self, include_instruction: bool) -> str:
        """Render the decision system message from the ``npc_decision`` template.

        The persona line and the Goals section drop out when empty (the template
        trims them). ``include_instruction`` selects the path: the free-text
        path appends the labeled Reasoning/Action/Duration instruction, while the
        structured (tool-calling) path omits it because the tool schema is the
        output contract. The ReAct labels are passed in (rather than hard-coded
        in the template) so ``ReActLabel`` stays the single source of truth for
        both this prompt and the reply parser (``_parse_decision``).
        """
        return prompt_templates.render(
            "npc_decision",
            persona=self.persona,
            goals_block=self._format_goals() or "",
            include_instruction=include_instruction,
            reasoning_label=ReActLabel.REASONING,
            action_label=ReActLabel.ACTION,
            duration_label=ReActLabel.DURATION,
        )

    def _system_message(self) -> str:
        # Free-text path: persona/goals plus the labeled instruction.
        return self._render_system(include_instruction=True)

    def _structured_system_message(self) -> str:
        # Structured path: the tool schema IS the output contract, so the
        # Reasoning/Action/Duration instruction is omitted.
        return self._render_system(include_instruction=False)

    def _call(self, observation: str) -> str | None:
        """Call the backend, supporting both the chat protocol and callables."""
        if hasattr(self.llm_client, "chat"):
            messages = [
                {"role": Role.SYSTEM, "content": self._system_message()},
                {"role": Role.USER, "content": observation},
            ]
            return self.llm_client.chat(
                messages, max_tokens=self.max_tokens, temperature=self.temperature
            )
        # Legacy callable: (str) -> str
        prompt = f"{self._system_message()}\n\n{observation}\n\nCommand:"
        return self.llm_client(prompt)


class ScriptedAgent(Agent):
    """Deterministic backend behind the same :meth:`decide` seam.

    Wraps a rule ``(observation) -> command``, e.g.::

        ScriptedAgent(lambda obs: "take shovel" if "churchyard" in obs else "look")

    Because it implements the same seam as :class:`LLMAgent`, the surrounding
    loop, tests, and games can't tell which backend is driving a character.

    An optional ``converse_rule`` ``(observation, partner_name) -> str | None``
    supplies dialogue lines (issue #86); with none, the agent stays silent
    (inheriting :meth:`Agent.converse`'s ``None``), so a scripted NPC never talks
    unless told how.
    """

    def __init__(
        self,
        rule,
        persona: str = "",
        goals: list[Goal] | None = None,
        embedding_client=None,
        reflector=None,
        reflection_threshold: float = DEFAULT_REFLECTION_THRESHOLD,
        converse_rule=None,
    ):
        super().__init__(
            persona=persona,
            goals=goals,
            embedding_client=embedding_client,
            reflector=reflector,
            reflection_threshold=reflection_threshold,
        )
        self.rule = rule
        self.converse_rule = converse_rule

    def decide(self, observation: str) -> str | None:
        return self.rule(observation)

    def converse(self, observation: str, partner_name: str) -> str | None:
        self.last_dialogue_done = False
        if self.converse_rule is None:
            return None
        return self.converse_rule(observation, partner_name)


# ----------------------------------------------------------------------
# Observe / Act / Reflect: the loop around the seam
#
# These are game-coupled (they touch describe_for and the parser) and stay
# OUTSIDE decide(). A later issue folds this loop into the turn loop itself.
# ----------------------------------------------------------------------


def build_npc_context(character, game) -> str:
    """Assemble an observation prompt describing what the NPC can perceive.

    Combines game.describe_for() (location, exits, items, other characters,
    inventory, and available actions) with recent command history.

    Returns a string suitable as the observation passed to ``Agent.decide()``.
    """
    lines = []

    # Full environment observation from the game engine
    lines.append(game.describe_for(character))

    # Recent command history, scoped and attributed (issue #629): a command
    # only appears if it was issued where this character now stands, and it is
    # labeled with the name of whoever issued it ("You:" for the character's
    # own commands). Unattributed entries (trigger-fired/scripted commands,
    # actor=None) keep the legacy "Player:" label and are never filtered, and
    # game narrations ("Game:") stay unscoped.
    here = character.location.name if character.location else None
    history = []
    for entry in game.parser.command_history:
        where = entry.get("location")
        if entry["role"] == Role.USER and None not in (where, here) and where != here:
            continue
        history.append(entry)
    history = history[-10:]
    if history:
        lines.append("")
        lines.append("Recent events:")
        for entry in history:
            content = entry["content"]
            if entry["role"] != Role.USER:
                prefix = "  Game:"
            elif entry.get("actor") == character.name:
                prefix = "  You:"
            elif entry.get("actor"):
                prefix = f"  {entry['actor']}:"
            else:
                prefix = "  Player:"
            lines.append(f"{prefix} {content[:200]}")

    # What the character has recently heard. This is scoped per-character: only
    # utterances delivered to this character's `heard` buffer appear, so speech
    # in other rooms never leaks in. The note reminds the agent that heard
    # speech is optional input -- it may be irrelevant or contrary to the
    # persona -- so persuasion stays a deliberate, in-character choice.
    heard = getattr(character, "heard", None)
    if heard:
        lines.append("")
        lines.append("You recently heard:")
        for line in heard:
            lines.append(f"  - {line}")
        lines.append(
            "Not everything you hear matters. Speech may be irrelevant, idle, "
            "or contrary to who you are -- only adopt or drop a goal if it "
            "genuinely fits your persona and what you already want. Otherwise, "
            "ignore it and act normally."
        )

    return "\n".join(lines)


def format_observation_with_memories(base: str, records) -> str:
    """Append a retrieved-memory block to *base*, or return *base* unchanged.

    The block is added *after* the whole environment observation (issue #75), so
    when an agent has no relevant memories the observation is byte-identical to
    before memory existed -- and even when it does, the block sits well below the
    "Characters here:" / "Inventory:" lines the mock client scans, so it can't
    perturb that parsing. Privacy stays intact: only this agent's own retrieved
    records are passed in, and they never reach ``command_history``.
    """
    block = render_memories(records)
    return base if not block else f"{base}\n\n{block}"


def _route(character, game, command: str) -> bool:
    """Route a command through the parser (and its precondition gate),
    attributed to *character* via the explicit actor seam. The name-prefix
    hack is gone: with the actor explicit, prepending the name would let the
    target scan mis-hit the actor's own name. Returns whether it succeeded."""
    return game.parser.parse_command(command, actor=character)


def _set_attribution(agent: Agent, actor: str, turn, attempt: int = 0) -> None:
    """Tag the agent's LLM client with who/when, so each recorded LLM call is
    attributed (usage.py). No-op for clients without a ``context`` attribute
    (e.g. a legacy callable or a non-LLM agent), so this is always safe to call.
    """
    ctx = getattr(getattr(agent, "llm_client", None), "context", None)
    if ctx is not None:
        ctx["actor"] = actor
        ctx["turn"] = turn
        ctx["attempt"] = attempt


def _reflect(observation: str, command: str, failure_reason: str) -> str:
    """Append the parser's failure reason to the observation so the next
    decide() sees *why* the action was rejected, not just that it was."""
    return (
        f"{observation}\n\n"
        f"Your previous command '{command}' failed: {failure_reason}\n"
        "Reflect on why it failed and choose a different action."
    )


def _log_decision(character, game, agent: Agent, command: str):
    """Trace the agent's decision on its own channels, e.g.::

        troll [reasoning] My growl didn't scare the player off -- escalate.
        troll [action] snarl player

    These go through ``parser.agent_reasoning`` / ``parser.agent_action`` (the
    AGENT_* channels), which a terminal renderer groups under the actor and a
    web renderer tags ``npc_log``. They are deliberately kept OUT of
    command_history -- an NPC's reasoning is private and must never leak into
    other characters' observations.
    """
    if agent.last_reasoning:
        game.parser.agent_reasoning(character.name, agent.last_reasoning)
    game.parser.agent_action(character.name, command)


def _use_tool_loop(agent: Agent) -> bool:
    """True when *agent* can drive the native tool loop (issue #355): an
    :class:`LLMAgent` whose client exposes ``call_tools``. Chat-only clients,
    legacy callables, and non-LLM agents fall back to the legacy
    string-reflection path in :func:`decide_and_route`."""
    client = getattr(agent, "llm_client", None)
    return isinstance(agent, LLMAgent) and hasattr(client, "call_tools")


def _decide_and_route_loop(
    character, game, agent: "LLMAgent", observation: str, max_rounds: int
) -> tuple[bool, bool]:
    """Decide -> Act -> Reflect as a native tool loop (issue #355).

    The model calls ``choose_action``; we route the command through the parser's
    precondition gate; a failure comes back as an ``is_error`` tool_result IN THE
    SAME conversation -- so the model reflects on its own prior tool call rather
    than on a rebuilt observation string, and the byte-stable system+tools prefix
    stays prompt-cacheable across rounds. The ``execute`` closure replicates
    :func:`decide_and_route`'s per-attempt side effects (``_log_decision``, the
    success/failure memory writes, the ``agent_reflection`` trace, and
    ``_set_attribution``), so the AGENT_* trace is byte-for-byte unchanged.

    Termination (see :func:`~text_adventure_games.llm_client.run_tool_loop`): a
    successful route is a *terminal* action -> ``done=True`` ends the episode with
    no wasted round-trip; a failed precondition -> ``is_error=True`` retries in
    conversation; ``max_rounds`` caps total model calls at the historical
    ``1 + max_retries`` budget.

    Returns ``(handled, acted)``. ``handled`` is ``False`` when the client made no
    tool call at all (a declining or chat-only client), so the caller falls
    through to the legacy path.

    When ``agent.cognition_tools`` is on (issue #358), the cognition tools are
    offered alongside the action tools and handled in the same ``execute``
    callback; each successful retrieval is traced on the AGENT_REASONING
    channel (never ``command_history``, so one agent's recall can't leak into
    another's observation).
    """
    # Same single-shot reset contract as LLMAgent.decide(): the structured tool
    # carries no duration, so last_duration stays None (-> _resolve_duration uses
    # the executed action's declared DURATION), and last_reasoning is per-call.
    agent.last_reasoning = None
    agent.last_duration = None
    mem = getattr(agent, "memory", None)
    turn = getattr(game, "turn", 0)
    # Per-action tools (issue #356): one tool per verb the agent may choose,
    # typed and scope-narrowed to this actor. Fall back to the single
    # choose_action tool only if the registry yields nothing (a degenerate game).
    tools = tools_for(game.parser, actor=character, names=agent.action_names)
    if not tools:
        tools = [build_choose_action_tool(agent.action_names)]
    # Cognition tools (issue #358, opt-in): offer recall / query_knowledge /
    # read_plan alongside the action tools, each gated on its source existing.
    # Their rounds ride ON TOP of the historical act/retry budget, so consulting
    # memory never eats an action attempt; after COGNITION_BUDGET calls the
    # execute callback refuses further ones (see cognition_toolset).
    cog_names: set = set()
    cognition_execute = None
    if getattr(agent, "cognition_tools", False):
        cog_tools, cognition_execute = cognition_toolset(
            agent,
            knowledge=getattr(character, "knowledge", None),
            turn=turn,
            trace=lambda text: game.parser.agent_reasoning(character.name, text),
        )
        # A registered action verb keeps priority over a same-named cognition
        # tool (duplicate tool names would be rejected by real providers).
        offered = {t["name"] for t in tools}
        cog_tools = [t for t in cog_tools if t["name"] not in offered]
        if cog_tools:
            cog_names = {t["name"] for t in cog_tools}
            tools = tools + cog_tools
            max_rounds += COGNITION_BUDGET
    messages = [
        {"role": Role.SYSTEM, "content": agent._structured_system_message()},
        {"role": Role.USER, "content": observation},
    ]
    state = {"acted": False, "calls": 0, "attempt": 1}

    def execute(name, args):
        if state["acted"]:
            # A real provider may emit several tool calls in one assistant turn
            # (parallel tool use), but an NPC gets ONE act per game turn: the
            # first successful route wins and the rest are refused here. Each
            # refusal still returns a tool_result -- the wire protocol requires
            # one per tool_use. The adapters also ask providers not to
            # parallelize (disable_parallel_tool_use / parallel_tool_calls),
            # but that is best-effort; this guard is the authority.
            return ("Already acted this turn; extra tool call ignored.", True, True)
        state["calls"] += 1
        if name in cog_names:
            # An in-process read of the agent's own state: the loop continues
            # (done=False) so the agent still acts this episode.
            return cognition_execute(name, args)
        agent.last_reasoning = (args.get("reasoning") or "").strip() or None
        # `name` is the verb for a per-action tool, or "choose_action" for the
        # fallback; command_from_tool_call handles both and assembles the string.
        command = command_from_tool_call(name, args, game.parser)
        if not command:
            # The model called the tool but named no action: nothing to route.
            # Terminal (no retry) so the loop ends, mirroring decide()'s "no
            # command -> stop" and leaving `acted` False.
            return ("No action was chosen.", False, True)
        _log_decision(character, game, agent, command)
        if _route(character, game, command):
            state["acted"] = True
            if mem is not None:
                mem.add_observation(
                    f'I tried "{command}" and succeeded.', turn=turn, importance=3
                )
            return ("Done.", False, True)
        failure_reason = (
            getattr(game.parser, "last_fail_message", None) or "action failed"
        )
        if mem is not None:
            # "but it failed because ..." avoids the "' failed:'" substring the
            # mock troll brain keys on -- a private memory must never spoof a
            # decision (same guard as decide_and_route's legacy path).
            mem.add_observation(
                f'I tried "{command}" but it failed because {failure_reason}',
                turn=turn,
                importance=4,
            )
        game.parser.agent_reflection(character.name, failure_reason)
        # Attribute the NEXT round's call to the upcoming attempt index.
        _set_attribution(
            agent, character.name, getattr(game, "turn", None), state["attempt"]
        )
        state["attempt"] += 1
        return (failure_reason, True, False)

    _set_attribution(agent, character.name, getattr(game, "turn", None), 0)
    run_tool_loop(
        agent.llm_client,
        messages,
        tools,
        execute,
        max_rounds=max_rounds,
        tool_choice="any",
        max_tokens=agent.max_tokens,
        temperature=agent.temperature,
    )
    if state["calls"] == 0:
        return (False, False)
    return (True, state["acted"])


def decide_and_route(
    character, game, agent: Agent, observation: str, max_retries: int = 1
) -> bool:
    """The Decide -> Act -> Reflect core: decide a command for *observation*,
    route it through the parser's precondition gate, and on failure trace the
    reason as a Reflect step, feed it back via :func:`_reflect`, and retry, up
    to ``1 + max_retries`` attempts in total. Each step is traced on its
    AGENT_* channel (see :func:`_log_decision`). Returns ``True`` if a command
    succeeded, ``False`` if the agent declined or every attempt failed.

    Shared by :func:`react_behavior` (sequential mode) and the simultaneous
    resolve phase (:func:`route_with_retry`, issue #25).
    """
    base = observation
    # Lazily bind this agent's memory to the character (issue #75). Done here --
    # not only in react_behavior -- because the simultaneous resolve phase
    # (route_with_retry) reaches this function without having bound the owner.
    # getattr-guarded so a hypothetical agent without .memory can't crash.
    mem = getattr(agent, "memory", None)
    if mem is not None and not mem.owner:
        mem.owner = character.name
    turn = getattr(game, "turn", 0)

    # Native tool loop (issue #355): when the client supports call_tools, retries
    # ride in the same conversation as an is_error tool_result. `handled` is False
    # if the client made no tool call, so we fall through to the legacy loop.
    if _use_tool_loop(agent):
        handled, acted = _decide_and_route_loop(
            character, game, agent, observation, max_rounds=1 + max_retries
        )
        if handled:
            return acted

    for attempt in range(1 + max_retries):
        _set_attribution(agent, character.name, getattr(game, "turn", None), attempt)
        command = agent.decide(observation)
        if not command:
            return False
        _log_decision(character, game, agent, command)
        if _route(character, game, command):
            if mem is not None:
                mem.add_observation(
                    f'I tried "{command}" and succeeded.', turn=turn, importance=3
                )
            return True
        failure_reason = (
            getattr(game.parser, "last_fail_message", None) or "action failed"
        )
        if mem is not None:
            # "but it failed because ..." is worded to avoid the "' failed:'"
            # substring the mock troll brain keys on -- a private memory must
            # never spoof another agent's decision.
            mem.add_observation(
                f'I tried "{command}" but it failed because {failure_reason}',
                turn=turn,
                importance=4,
            )
        game.parser.agent_reflection(character.name, failure_reason)
        observation = _reflect(base, command, failure_reason)

    return False


def react_behavior(character, game, agent: Agent, max_retries: int = 1) -> bool:
    """Run one turn of the Observe -> Act -> Reflect loop around *agent*.

    Observe (build the observation, augmented with retrieved memories), trace it
    (verbose-only), then hand off to :func:`decide_and_route` for the
    decide/route/reflect cycle. Returns ``True`` if a command succeeded, else
    ``False``.

    Memory (issue #75) is woven in here, in the Observe step: first perceive the
    nearby world -- events plus, within the character's vision radius, the agents
    and objects in view (issue #80) -- then retrieve the memories most relevant to
    the current situation and fold them into the prompt. The simultaneous gather
    phase runs the same perceive -> retrieve steps against its own snapshot.
    """
    if not agent.memory.owner:
        agent.memory.owner = character.name
    agent.memory.perceive(game, character)

    base = build_npc_context(character, game)
    relevant = agent.memory.retrieve(query=base, turn=getattr(game, "turn", 0))
    observation = format_observation_with_memories(base, relevant)
    # The full observation is traced too, but only shows at verbose verbosity.
    game.parser.agent_observation(character.name, observation)
    acted = decide_and_route(character, game, agent, observation, max_retries)
    # Periodic memory synthesis (issue #84): after acting, if enough importance
    # has accrued, turn recent memories into higher-level thoughts. A no-op unless
    # a reflector is wired onto the agent, so games without one are unchanged.
    maybe_reflect(agent, game)
    return acted


def maybe_reflect(agent: Agent, game) -> list:
    """Run a periodic reflection pass if one is due (issue #84).

    Distinct from the failure-Reflect in :func:`decide_and_route`: that reacts to
    one rejected command; this is the paper's *periodic memory synthesis* --
    fired on a salience cadence (:func:`~text_adventure_games.reflection.
    should_reflect`) and reasoning over the whole recent stream.

    A no-op (returns ``[]``) unless the agent has a ``reflector`` and accumulated
    importance has crossed its ``reflection_threshold``. Each thought it produces
    is appended to the agent's own memory (by
    :func:`~text_adventure_games.reflection.reflect`) and traced on the private
    AGENT_REFLECTION channel, the same channel the failure-Reflect uses -- so a
    reflection never leaks into ``command_history`` or another agent's prompt.
    """
    reflector = getattr(agent, "reflector", None)
    memory = getattr(agent, "memory", None)
    if reflector is None or memory is None:
        return []
    threshold = getattr(agent, "reflection_threshold", DEFAULT_REFLECTION_THRESHOLD)
    if not should_reflect(memory, threshold):
        return []
    created = reflect(memory, reflector, getattr(game, "turn", 0))
    trace = getattr(game.parser, "agent_reflection", None)
    if trace is not None:
        for record in created:
            trace(memory.owner, record.text)
    return created


def route_first_workable(character, game, agent: Agent, commands) -> bool:
    """Route ranked fallback *commands* in order; run the first that passes the
    precondition gate (issue #42, stage 4).

    The cheap arm of contention handling: when an agent supplied a backup at
    gather time (``decide`` returned ``["take gem", "take coin"]``), the loser of
    the gem takes the coin immediately — no second LLM round-trip. Each attempt
    is traced as an action; returns ``True`` on the first success, ``False`` if
    none of the fallbacks work.
    """
    for command in commands:
        if not command:
            continue
        game.parser.agent_action(character.name, command)
        if _route(character, game, command):
            return True
    return False


def route_with_retry(
    character,
    game,
    agent: Agent,
    first_command: str,
    max_retries: int = 1,
    conflict_reason: str = None,
) -> bool:
    """Route an already-decided *first_command*; on failure, reflect and retry.

    Used by the simultaneous resolve phase (issue #25, turns.py): the first
    command was chosen during the gather phase against the turn-start
    snapshot, but is resolved later — so when it fails, the reflection
    observation is rebuilt against the *live* world, letting the agent see why
    the action failed *now* (e.g. another character got there first). The
    retry tail goes through :func:`decide_and_route`, keeping the total at
    ``1 + max_retries`` attempts, consistent with :func:`react_behavior`.

    ``conflict_reason`` (issue #42) is the informed-retry arm of contention
    handling: when a higher-priority character already took the contested
    resource, ``first_command`` is *known* to be doomed, so we skip routing it
    (no wasted attempt, no phantom "I don't see it.") and reflect directly on the
    true reason — "they got there first" — before re-deciding.
    """
    if conflict_reason is None:
        _log_decision(character, game, agent, first_command)
        if _route(character, game, first_command):
            return True
        if max_retries <= 0:
            return False
        failure_reason = (
            getattr(game.parser, "last_fail_message", None) or "action failed"
        )
    else:
        failure_reason = conflict_reason
    game.parser.agent_reflection(character.name, failure_reason)
    base = build_npc_context(character, game)
    observation = _reflect(base, first_command, failure_reason)
    return decide_and_route(character, game, agent, observation, max_retries - 1)


# ----------------------------------------------------------------------
# Behavior factories (the legacy set_behavior bridge)
#
# These keep the existing (character, game) -> None behavior contract so NPCs
# wire up via Character.set_behavior() exactly as before -- now built on the
# decide() seam underneath.
# ----------------------------------------------------------------------


def _resolve_duration(agent: Agent, game, character) -> int | None:
    """Minutes the agent's last successful action should cost the turn budget.

    Precedence (issue #24): the agent's own estimate if it gave one, else the
    executed action's declared ``DURATION``, else ``None`` (no declared cost ->
    the turn loop treats it as a full budget, i.e. one action this turn).

    Reads the duration off *this character's* last action, not a single global
    parser field -- so it stays correct when several characters act in a round
    (a switch to per-agent turns can't make it read someone else's move).
    """
    if agent.last_duration is not None:
        return agent.last_duration
    last_action = getattr(character, "last_action", None)
    if last_action is not None:
        return last_action.get_duration()
    return None


def make_react_behavior(
    llm_client,
    max_retries: int | None = None,
    config=None,
    embedding_client=None,
    reflector=None,
):
    """Return a behavior that drives a character with an :class:`LLMAgent`.

    The character owns its persona and goals; the agent reads them. Persona is
    adopted once (it rarely changes); goals are re-read every turn so any
    in-game ``character.add_goal()`` / ``complete_goal()`` lands in the next
    decision prompt without re-wiring anything.

    Args:
        llm_client: An ``LlmClient`` (with ``chat()``) or a ``(str) -> str``
            callable.
        max_retries: How many times to retry on a failed command. ``None`` uses
            ``config.max_retries`` (a passed integer overrides the config).
        config: An :class:`~text_adventure_games.config.AgentConfig` supplying
            the agent's temperature, max_tokens, max_retries, and max_duration.
            Defaults to ``AgentConfig()`` (the engine's historical values).
        embedding_client: Optional ``EmbeddingClient`` (issue #76) for semantic
            memory relevance. ``None`` keeps keyword-overlap relevance.
        reflector: Optional ``Reflector`` (issue #84) for periodic memory
            synthesis. ``None`` (the default) keeps reflection off, so behavior is
            byte-identical to before; pass one to have the agent form higher-level
            thoughts once accumulated importance crosses
            ``config.reflection_threshold``.

    Returns:
        A callable ``(character, game) -> None`` for ``Character.set_behavior``.
    """
    config = config if config is not None else AgentConfig()
    retries = max_retries if max_retries is not None else config.max_retries
    # One agent is created per factory call and captured by the returned
    # closure, so this agent -- its persona, goals, and private memory stream
    # (issue #75) -- belongs to a single character. Attach the result to ONE
    # character; to drive several NPCs, call this factory once per character
    # rather than sharing a behavior, or they would share an identity (and a
    # memory).
    agent = LLMAgent(
        llm_client,
        max_tokens=config.max_tokens,
        temperature=config.temperature,
        max_duration=config.max_duration,
        embedding_client=embedding_client,
        reflector=reflector,
        reflection_threshold=config.reflection_threshold,
        cognition_tools=config.cognition_tools,
    )

    def behavior(character, game):
        if not agent.persona:
            agent.persona = character.persona or ""
        agent.goals = character.goals
        agent.action_names = list(game.parser.actions)
        if not react_behavior(character, game, agent, max_retries=retries):
            return None
        return _resolve_duration(agent, game, character)

    return behavior


def make_hybrid_behavior(
    llm_client,
    scripted_behavior,
    max_retries: int | None = None,
    config=None,
    embedding_client=None,
    reflector=None,
):
    """Return a behavior that tries the LLM agent, then falls back to scripted.

    Persona and goals are sourced from the character, same as
    :func:`make_react_behavior`.

    Args:
        llm_client: An ``LlmClient`` (with ``chat()``) or a ``(str) -> str``
            callable.
        scripted_behavior: A ``(character, game) -> None`` callable used when
            the LLM produces nothing usable (e.g. an API failure).
        max_retries: How many times to retry the LLM on a failed command.
            ``None`` uses ``config.max_retries`` (a passed integer overrides it).
        config: An :class:`~text_adventure_games.config.AgentConfig` supplying
            the agent's temperature, max_tokens, max_retries, and max_duration.
        embedding_client: Optional ``EmbeddingClient`` (issue #76) for semantic
            memory relevance. ``None`` keeps keyword-overlap relevance.
        reflector: Optional ``Reflector`` (issue #84) for periodic memory
            synthesis. ``None`` (the default) keeps reflection off.

    Returns:
        A callable ``(character, game) -> None`` for ``Character.set_behavior``.
    """
    config = config if config is not None else AgentConfig()
    retries = max_retries if max_retries is not None else config.max_retries
    # As in make_react_behavior, this single agent belongs to one character;
    # call the factory once per NPC rather than sharing the returned behavior.
    agent = LLMAgent(
        llm_client,
        max_tokens=config.max_tokens,
        temperature=config.temperature,
        max_duration=config.max_duration,
        embedding_client=embedding_client,
        reflector=reflector,
        reflection_threshold=config.reflection_threshold,
        cognition_tools=config.cognition_tools,
    )

    def behavior(character, game):
        if not agent.persona:
            agent.persona = character.persona or ""
        agent.goals = character.goals
        agent.action_names = list(game.parser.actions)
        if react_behavior(character, game, agent, max_retries=retries):
            return _resolve_duration(agent, game, character)
        # LLM produced nothing usable: fall back to the scripted behavior, whose
        # return value (None for legacy behaviors) decides whether the turn loop
        # continues — legacy scripted behaviors stay at one action per turn.
        return scripted_behavior(character, game)

    return behavior
