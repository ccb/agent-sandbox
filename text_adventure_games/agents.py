from __future__ import annotations

"""First-class Agent objects for NPC cognition (issue #3).

An Agent is a cognitive object *attached to* a Character (composition). It owns
the character's goals and an append-only memory log; persona is read from the
Character. The public entry point is ``take_turn(character, game)``; internally
the work is split into small, independently testable units:

    observe -> decide -> act -> remember -> reflect (on failure, retry)

Subclasses:
    LLMAgent      -- decide() asks an LlmClient.
    ScriptedAgent -- adapts a legacy (character, game) -> None behavior closure.
"""


class Agent:
    """Base cognitive object attached to a Character via composition."""

    def __init__(self, goals=None, max_retries=1, memory_window=5):
        self.goals = list(goals) if goals else []
        self.max_retries = max_retries
        self.memory_window = memory_window
        self.memory = []  # list of {"turn", "observation", "command", "ok"}

    # --- public entry point -------------------------------------------------

    def take_turn(self, character, game):
        """Run one turn: observe, then decide/act with bounded retries."""
        observation = self.observe(character, game)
        for _ in range(1 + self.max_retries):
            command = self.decide(observation, character)
            if not command:
                break
            command = self._route_name(command, character)
            ok = self.act(command, game)
            self.remember(character, game, observation, command, ok)
            if ok:
                return
            observation = self.reflect(observation, command)
        self._on_turn_exhausted(character, game)

    # --- pipeline units -----------------------------------------------------

    def observe(self, character, game) -> str:
        """Build the observation string from world state, goals, and memory."""
        lines = [game.describe_for(character)]
        if self.goals:
            lines += ["", "Your goals: " + "; ".join(self.goals)]
        history = getattr(game.parser, "command_history", [])[-10:]
        if history:
            lines += ["", "Recent events:"]
            for entry in history:
                prefix = "  Player:" if entry.get("role") == "user" else "  Game:"
                lines.append(f"{prefix} {entry.get('content', '')[:200]}")
        recent = self.memory[-self.memory_window:]
        if recent:
            lines += ["", "Your recent actions:"]
            for e in recent:
                status = "ok" if e["ok"] else "failed"
                lines.append(f"  [turn {e['turn']}] {e['command']} ({status})")
        return "\n".join(lines)

    def decide(self, observation, character) -> str:
        """Return a single command string. Subclasses implement this."""
        raise NotImplementedError

    def act(self, command, game) -> bool:
        """Route a fully-formed command through the parser. Returns success."""
        return bool(game.parser.parse_command(command))

    def remember(self, character, game, observation, command, ok):
        """Append one entry to the append-only memory log."""
        self.memory.append(
            {
                "turn": getattr(game, "turn", 0),
                "observation": observation,
                "command": command,
                "ok": ok,
            }
        )

    def reflect(self, observation, command) -> str:
        """Thread the failure back into the next observation (seam for #4)."""
        return (
            f"{observation}\n\n"
            f"Your previous command '{command}' failed. Choose a different action."
        )

    # --- helpers ------------------------------------------------------------

    def _route_name(self, command, character) -> str:
        command = command.strip()
        if command and not command.lower().startswith(character.name.lower()):
            command = f"{character.name} {command}"
        return command

    def _on_turn_exhausted(self, character, game):
        """Hook for subclasses (e.g. scripted fallback). Default: no-op."""
        pass


class LLMAgent(Agent):
    """An Agent whose decide() consults an LlmClient (or a plain callable)."""

    def __init__(
        self,
        llm_client,
        fallback=None,
        goals=None,
        max_retries=1,
        memory_window=5,
        max_tokens=64,
        temperature=0.7,
    ):
        super().__init__(
            goals=goals, max_retries=max_retries, memory_window=memory_window
        )
        self.llm_client = llm_client
        self.fallback = fallback
        self.max_tokens = max_tokens
        self.temperature = temperature

    def decide(self, observation, character) -> str:
        response = self._call_llm(observation, character)
        if not response:
            return ""
        return response.strip().split("\n")[0].strip()

    def _on_turn_exhausted(self, character, game):
        if self.fallback is not None:
            self.fallback.take_turn(character, game)

    # --- prompt construction ------------------------------------------------

    def _build_system_message(self, character) -> str:
        lines = [f"You are {character.name}, an NPC in a text adventure game."]
        if character.persona:
            lines.append(f"Persona: {character.persona}")
        if self.goals:
            lines.append("Goals: " + "; ".join(self.goals))
        lines.append(
            "Based on your persona and the current situation, choose a single game "
            "command to execute. Respond with ONLY the command, nothing else. "
            "Examples: 'attack player', 'go north', 'take sword'."
        )
        return "\n".join(lines)

    def _call_llm(self, observation, character):
        client = self.llm_client
        if hasattr(client, "chat"):
            messages = [
                {"role": "system", "content": self._build_system_message(character)},
                {"role": "user", "content": observation},
            ]
            return client.chat(
                messages, max_tokens=self.max_tokens, temperature=self.temperature
            )
        # Legacy callable: (str) -> str
        persona = f"Persona: {character.persona}" if character.persona else ""
        full_prompt = (
            f"You are {character.name}.\n{persona}\n\n{observation}\n\n"
            "Based on your persona and the current situation, what single game "
            "command would you like to execute? Respond with ONLY the command, "
            "nothing else.\nCommand:"
        )
        return client(full_prompt)


class ScriptedAgent(Agent):
    """Adapter that wraps a legacy ``(character, game) -> None`` behavior closure.

    Existing scripted behaviors hold their own state and drive the parser
    directly, so this agent overrides ``take_turn`` to call the closure rather
    than routing through ``decide``. It still carries goals/memory for
    uniformity, but does not populate memory automatically.
    """

    def __init__(self, script, goals=None):
        super().__init__(goals=goals)
        self.script = script

    def decide(self, observation, character) -> str:  # pragma: no cover - unused
        return ""

    def take_turn(self, character, game):
        self.script(character, game)
