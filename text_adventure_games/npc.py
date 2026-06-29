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
from .config import AgentConfig
from .enums import ReActLabel, Role
from .memory import AgentMemory, render_memories
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
        default offline run silent and byte-identical."""
        self.last_dialogue_done = False
        spoken = self._converse_structured(observation)
        if spoken is not None:
            return spoken
        return self._converse_freetext(observation)

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

    # Recent command history (last 5 exchanges)
    # "Last 5" is a bit misleading, since llm_parser and parser respond differently to failure
    # Could be something to look into
    history = game.parser.command_history[-10:]
    if history:
        lines.append("")
        lines.append("Recent events:")
        for entry in history:
            role = entry["role"]
            content = entry["content"]
            prefix = "  Player:" if role == Role.USER else "  Game:"
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
