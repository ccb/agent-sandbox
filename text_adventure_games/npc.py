"""Agent decision layer for LLM-driven (and scripted) NPC behavior.

The seam is ``Agent.decide(observation) -> command``: a pure function from an
observation string to a single raw command string. An ``Agent`` owns the
character's *mind* -- its persona and goals (memory is Phase 2). Two backends
sit behind the same seam and are interchangeable:

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

from .enums import ReActLabel, Role
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


_DECISION_INSTRUCTION = (
    "Based on your persona, goals, and the current situation, choose a single "
    "game command to execute. Reply with exactly three lines:\n"
    f"{ReActLabel.REASONING} <one short sentence explaining your choice>\n"
    f"{ReActLabel.ACTION} <the command, e.g. 'attack player', 'go north', 'take sword'>\n"
    f"{ReActLabel.DURATION} <estimated in-game minutes this action takes, e.g. 5>"
)


def _parse_duration(text: str) -> int | None:
    """Pull an in-game-minute count out of a "Duration:" line's value.

    Extracts the first integer (so "about 30 minutes" -> 30), rejects
    non-positive values as invalid, and clamps anything larger than
    :data:`_MAX_DURATION`. Returns ``None`` when no usable number is present.
    """
    match = re.search(r"-?\d+", text)
    if match is None:
        return None
    value = int(match.group())
    if value <= 0:
        return None
    return min(value, _MAX_DURATION)


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


def _parse_decision(text: str) -> tuple[str | None, str | None, int | None]:
    """Split an LLM reply into ``(reasoning, command, duration)``.

    Understands the labeled format requested by ``_DECISION_INSTRUCTION``
    ("Reasoning: ...\\nAction: ...\\nDuration: ..."; "Thought:" is accepted as a
    synonym for the reasoning line). ``duration`` is the estimated in-game
    minutes for the action, or ``None`` when the line is absent or unusable.
    Falls back to treating the first non-empty line as a bare command, so
    models (and tests) that reply with just the command keep working.
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
            duration = _parse_duration(line.split(":", 1)[1])
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

    Owns the character's mind: ``persona`` (a first-person string) and
    ``goals`` (what it wants). Memory is deferred to Phase 2. The single
    required behavior is :meth:`decide`: given an observation string, return one
    raw command string, or ``None`` to act on nothing this turn. Subclasses
    supply the backend.
    """

    def __init__(self, persona: str = "", goals: list[Goal] | None = None):
        self.persona = persona
        self.goals: list[Goal] = list(goals) if goals else []
        # Why the agent chose its last command. Subclasses may set this in
        # decide(); the ReAct loop logs it next to the chosen action.
        self.last_reasoning: str | None = None
        # The agent's estimate (in-game minutes) for its last command, or None
        # if it gave no estimate. The turn loop prefers this over the action's
        # declared DURATION when charging the per-turn budget (issue #24).
        self.last_duration: int | None = None

    def decide(self, observation: str) -> str | None:
        """Return a single command string for *observation* (or ``None``)."""
        raise NotImplementedError("Agent subclasses must implement decide().")


class LLMAgent(Agent):
    """Agent that decides by asking an LLM.

    Accepts either an :class:`LlmClient` (anything with a ``chat()`` method) or
    a legacy ``(str) -> str`` callable. The persona and goals are sent as the
    system message; the observation is the user message. ``decide()`` returns
    the command from the reply's "Action:" line (or, for unlabeled replies,
    its first line), and records the "Reasoning:" line in ``last_reasoning``.
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
    ):
        super().__init__(persona=persona, goals=goals)
        self.llm_client = llm_client
        self.max_tokens = max_tokens
        self.temperature = temperature

    def decide(self, observation: str) -> str | None:
        self.last_reasoning = None
        self.last_duration = None
        response = self._call(observation)
        if response is None:
            return None
        reasoning, command, duration = _parse_decision(response)
        self.last_reasoning = reasoning
        self.last_duration = duration
        return command

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

    def _system_message(self) -> str:
        # The character's name is deliberately left out of this prompt: an
        # agent's identity rides on its first-person persona string (and the
        # observation already names the scene and the other characters in it),
        # so the model speaks as "I" without being told its own name. Add the
        # name here only if a future persona needs the model to refer to itself
        # by name.
        lines = ["You are an NPC in a text adventure game."]
        if self.persona:
            lines.append(f"Persona: {self.persona}")
        formatted = self._format_goals()
        if formatted:
            lines.append("Goals:")
            lines.append(formatted)
        lines.append(_DECISION_INSTRUCTION)
        return "\n".join(lines)

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
    """

    def __init__(self, rule, persona: str = "", goals: list[Goal] | None = None):
        super().__init__(persona=persona, goals=goals)
        self.rule = rule

    def decide(self, observation: str) -> str | None:
        return self.rule(observation)


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

    return "\n".join(lines)


def _route(character, game, command: str) -> bool:
    """Route a command through the parser (and its precondition gate),
    attributed to *character* via the explicit actor seam. The name-prefix
    hack is gone: with the actor explicit, prepending the name would let the
    target scan mis-hit the actor's own name. Returns whether it succeeded."""
    return game.parser.parse_command(command, actor=character)


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

    for _ in range(1 + max_retries):
        command = agent.decide(observation)
        if not command:
            return False
        _log_decision(character, game, agent, command)
        if _route(character, game, command):
            return True
        failure_reason = (
            getattr(game.parser, "last_fail_message", None) or "action failed"
        )
        game.parser.agent_reflection(character.name, failure_reason)
        observation = _reflect(base, command, failure_reason)

    return False


def react_behavior(character, game, agent: Agent, max_retries: int = 1) -> bool:
    """Run one turn of the Observe -> Act -> Reflect loop around *agent*.

    Observe (build the observation), trace it (verbose-only), then hand off to
    :func:`decide_and_route` for the decide/route/reflect cycle. Returns
    ``True`` if a command succeeded, else ``False``.
    """
    observation = build_npc_context(character, game)
    # The full observation is traced too, but only shows at verbose verbosity.
    game.parser.agent_observation(character.name, observation)
    return decide_and_route(character, game, agent, observation, max_retries)


def route_with_retry(
    character, game, agent: Agent, first_command: str, max_retries: int = 1
) -> bool:
    """Route an already-decided *first_command*; on failure, reflect and retry.

    Used by the simultaneous resolve phase (issue #25, turns.py): the first
    command was chosen during the gather phase against the turn-start
    snapshot, but is resolved later — so when it fails, the reflection
    observation is rebuilt against the *live* world, letting the agent see why
    the action failed *now* (e.g. another character got there first). The
    retry tail goes through :func:`decide_and_route`, keeping the total at
    ``1 + max_retries`` attempts, consistent with :func:`react_behavior`.
    """
    _log_decision(character, game, agent, first_command)
    if _route(character, game, first_command):
        return True
    if max_retries <= 0:
        return False
    failure_reason = getattr(game.parser, "last_fail_message", None) or "action failed"
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


def _resolve_duration(agent: Agent, game) -> int | None:
    """Minutes the agent's last successful action should cost the turn budget.

    Precedence (issue #24): the agent's own estimate if it gave one, else the
    executed action's declared ``DURATION``, else ``None`` (no declared cost ->
    the turn loop treats it as a full budget, i.e. one action this turn).
    """
    if agent.last_duration is not None:
        return agent.last_duration
    last_action = getattr(game.parser, "last_action", None)
    if last_action is not None:
        return last_action.get_duration()
    return None


def make_react_behavior(llm_client, max_retries: int = 1):
    """Return a behavior that drives a character with an :class:`LLMAgent`.

    The character owns its persona and goals; the agent reads them. Persona is
    adopted once (it rarely changes); goals are re-read every turn so any
    in-game ``character.add_goal()`` / ``complete_goal()`` lands in the next
    decision prompt without re-wiring anything.

    Args:
        llm_client: An ``LlmClient`` (with ``chat()``) or a ``(str) -> str``
            callable.
        max_retries: How many times to retry on a failed command.

    Returns:
        A callable ``(character, game) -> None`` for ``Character.set_behavior``.
    """
    # One agent is created per factory call and captured by the returned
    # closure, so this agent (its persona today, its memory in Phase 2) belongs
    # to a single character. Attach the result to ONE character; to drive
    # several NPCs, call this factory once per character rather than sharing a
    # behavior, or they would share an identity.
    agent = LLMAgent(llm_client)

    def behavior(character, game):
        if not agent.persona:
            agent.persona = character.persona or ""
        agent.goals = character.goals
        if not react_behavior(character, game, agent, max_retries=max_retries):
            return None
        return _resolve_duration(agent, game)

    return behavior


def make_hybrid_behavior(llm_client, scripted_behavior, max_retries: int = 1):
    """Return a behavior that tries the LLM agent, then falls back to scripted.

    Persona and goals are sourced from the character, same as
    :func:`make_react_behavior`.

    Args:
        llm_client: An ``LlmClient`` (with ``chat()``) or a ``(str) -> str``
            callable.
        scripted_behavior: A ``(character, game) -> None`` callable used when
            the LLM produces nothing usable (e.g. an API failure).
        max_retries: How many times to retry the LLM on a failed command.

    Returns:
        A callable ``(character, game) -> None`` for ``Character.set_behavior``.
    """
    # As in make_react_behavior, this single agent belongs to one character;
    # call the factory once per NPC rather than sharing the returned behavior.
    agent = LLMAgent(llm_client)

    def behavior(character, game):
        if not agent.persona:
            agent.persona = character.persona or ""
        agent.goals = character.goals
        if react_behavior(character, game, agent, max_retries=max_retries):
            return _resolve_duration(agent, game)
        # LLM produced nothing usable: fall back to the scripted behavior, whose
        # return value (None for legacy behaviors) decides whether the turn loop
        # continues — legacy scripted behaviors stay at one action per turn.
        return scripted_behavior(character, game)

    return behavior
