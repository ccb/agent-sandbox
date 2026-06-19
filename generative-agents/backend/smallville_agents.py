"""Mock-LLM brains for the Smallville cast.

The port uses no live LLM. Each persona is driven by a
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
"""

from text_adventure_games.llm_client import MockReActClient
from text_adventure_games.npc import LLMAgent, format_observation_with_memories


class SmallvilleMockClient(MockReActClient):
    """Deterministic mock LLM for one persona's morning routine."""

    def __init__(self, destination: str, activity: str, config=None):
        super().__init__(config)
        self.destination = destination
        self.activity = activity

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
        return {"reasoning": reasoning, "action": verb, "arguments": rest}


def attach_agents(characters: dict, personas: list[dict]) -> None:
    """Wire one mock-driven :class:`LLMAgent` onto each persona character.

    ``characters`` maps name -> Character (from :func:`build_world.build_world`);
    ``personas`` is the metadata list (``build_world.PERSONAS``).

    Each agent also starts the day with one *plan* memory (issue #75) -- "go to
    <destination> and <activity>" -- seeded from the persona spec. It is the
    agent's own private intention, distinct from its persona (already in the
    system prompt): it gives retrieval something to surface from turn 0 and
    demonstrates the ``PLAN`` memory kind. We do not seed the persona text into
    memory, since the agent layer already injects it into every prompt."""
    for spec in personas:
        char = characters[spec["name"]]
        client = SmallvilleMockClient(spec["destination"], spec["activity"])
        agent = LLMAgent(client, persona=char.persona)
        # The verbs the structured tool may offer; our client ignores the enum
        # but a well-formed schema keeps the seam honest.
        agent.action_names = ["travel", "perform"]
        char.set_agent(agent)
        # Bind the private memory to this character and seed the day's plan.
        agent.memory.owner = char.name
        agent.memory.add_plan(
            f"Plan: go to {spec['destination']} and {spec['activity']}.",
            turn=0,
            importance=5.0,
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
    observation = format_observation_with_memories(base, relevant)
    return agent.decide(observation)


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
