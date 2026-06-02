from __future__ import annotations

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
Today that loop is bridged onto a character via the legacy ``set_behavior``
hook through :func:`make_react_behavior` / :func:`make_hybrid_behavior`; a
later issue moves it into the turn loop itself. Keeping ``decide()`` free of
``game`` is what lets the agent layer be unit-tested offline with
``MockLlmClient``.

See ``docs/design/multi-character-play.md`` (issue #3).

Usage::

    from text_adventure_games.npc import make_react_behavior, make_hybrid_behavior

    troll.set_behavior(make_react_behavior(llm_client))
    troll.set_behavior(make_hybrid_behavior(llm_client, make_troll_behavior()))
"""


_DECISION_INSTRUCTION = (
    "Based on your persona, goals, and the current situation, choose a single "
    "game command to execute. Respond with ONLY the command, nothing else. "
    "Examples: 'attack player', 'go north', 'take sword'."
)


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

    def __init__(self, persona: str = "", goals=None):
        self.persona = persona
        self.goals = list(goals) if goals else []

    def decide(self, observation: str) -> str | None:
        """Return a single command string for *observation* (or ``None``)."""
        raise NotImplementedError("Agent subclasses must implement decide().")


class LLMAgent(Agent):
    """Agent that decides by asking an LLM.

    Accepts either an :class:`LlmClient` (anything with a ``chat()`` method) or
    a legacy ``(str) -> str`` callable. The persona and goals are sent as the
    system message; the observation is the user message. ``decide()`` returns
    the first line of the reply (or ``None`` if the client failed or said
    nothing).
    """

    def __init__(
        self,
        llm_client,
        persona: str = "",
        goals=None,
        max_tokens: int = 64,
        temperature: float = 0.7,
    ):
        super().__init__(persona=persona, goals=goals)
        self.llm_client = llm_client
        self.max_tokens = max_tokens
        self.temperature = temperature

    def decide(self, observation: str) -> str | None:
        response = self._call(observation)
        if response is None:
            return None
        command = response.strip().split("\n")[0].strip()
        return command or None

    def _system_message(self) -> str:
        lines = ["You are an NPC in a text adventure game."]
        if self.persona:
            lines.append(f"Persona: {self.persona}")
        if self.goals:
            lines.append("Goals: " + "; ".join(self.goals))
        lines.append(_DECISION_INSTRUCTION)
        return "\n".join(lines)

    def _call(self, observation: str) -> str | None:
        """Call the backend, supporting both the chat protocol and callables."""
        if hasattr(self.llm_client, "chat"):
            messages = [
                {"role": "system", "content": self._system_message()},
                {"role": "user", "content": observation},
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

    def __init__(self, rule, persona: str = "", goals=None):
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
    history = game.parser.command_history[-10:]
    if history:
        lines.append("")
        lines.append("Recent events:")
        for entry in history:
            role = entry["role"]
            content = entry["content"]
            prefix = "  Player:" if role == "user" else "  Game:"
            lines.append(f"{prefix} {content[:200]}")

    return "\n".join(lines)


def _route(character, game, command: str) -> bool:
    """Prepend the character's name so the parser attributes the command to it,
    then route it through the parser (and its precondition gate). Returns
    whether the command succeeded."""
    if not command.lower().startswith(character.name.lower()):
        command = f"{character.name} {command}"
    return game.parser.parse_command(command)


def _reflect(observation: str, command: str, failure_reason: str) -> str:
    """Append the parser's failure reason to the observation so the next
    decide() sees *why* the action was rejected, not just that it was."""
    return (
        f"{observation}\n\n"
        f"Your previous command '{command}' failed: {failure_reason}\n"
        "Reflect on why it failed and choose a different action."
    )


def react_behavior(character, game, agent: Agent, max_retries: int = 1) -> bool:
    """Run one turn of the Observe -> Act -> Reflect loop around *agent*.

    Observe (build the observation), let the agent decide a command, route it
    through the parser; on failure, read the parser's last failure message and
    feed it back via :func:`_reflect`, then retry up to *max_retries* times.
    Returns ``True`` if a command succeeded, else ``False``.
    """
    base = build_npc_context(character, game)
    observation = base

    for _ in range(1 + max_retries):
        command = agent.decide(observation)
        if not command:
            return False
        if _route(character, game, command):
            return True
        failure_reason = (
            getattr(game.parser, "last_fail_message", None) or "action failed"
        )
        observation = _reflect(base, command, failure_reason)

    return False


# ----------------------------------------------------------------------
# Behavior factories (the legacy set_behavior bridge)
#
# These keep the existing (character, game) -> None behavior contract so NPCs
# wire up via Character.set_behavior() exactly as before -- now built on the
# decide() seam underneath.
# ----------------------------------------------------------------------


def make_react_behavior(llm_client, max_retries: int = 1, goals=None):
    """Return a behavior that drives a character with an :class:`LLMAgent`.

    Args:
        llm_client: An ``LlmClient`` (with ``chat()``) or a ``(str) -> str``
            callable.
        max_retries: How many times to retry on a failed command.
        goals: Optional list of goal strings for the agent.

    Returns:
        A callable ``(character, game) -> None`` for ``Character.set_behavior``.
    """
    agent = LLMAgent(llm_client, goals=goals)

    def behavior(character, game):
        if not agent.persona:
            agent.persona = character.persona or ""
        react_behavior(character, game, agent, max_retries=max_retries)

    return behavior


def make_hybrid_behavior(
    llm_client, scripted_behavior, max_retries: int = 1, goals=None
):
    """Return a behavior that tries the LLM agent, then falls back to scripted.

    Args:
        llm_client: An ``LlmClient`` (with ``chat()``) or a ``(str) -> str``
            callable.
        scripted_behavior: A ``(character, game) -> None`` callable used when
            the LLM produces nothing usable (e.g. an API failure).
        max_retries: How many times to retry the LLM on a failed command.
        goals: Optional list of goal strings for the agent.

    Returns:
        A callable ``(character, game) -> None`` for ``Character.set_behavior``.
    """
    agent = LLMAgent(llm_client, goals=goals)

    def behavior(character, game):
        if not agent.persona:
            agent.persona = character.persona or ""
        if not react_behavior(character, game, agent, max_retries=max_retries):
            scripted_behavior(character, game)

    return behavior
