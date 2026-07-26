"""The #780 dialogue place-grounding wiring.

Pins that the sim accumulates each agent's real visit history and hands it,
with the world's place list, to the engine's dialogue seam. Offline -- the
"brain" here is a stub that records the observation it was given.

Run from the repo root::

    uv run pytest godot-generative-agents/tests/test_dialogue_place_grounding_780.py -v
"""

from text_adventure_games import conversation as convo
from text_adventure_games.games import Game
from text_adventure_games.npc import ScriptedAgent
from text_adventure_games.things import Character, Location

from backend import cognition


def _world():
    """Two agents standing together in the Plaza, with a Field they can reach."""
    plaza = Location("Plaza", "the plaza")
    field = Location("Field", "a field")
    plaza.add_connection("north", field)
    player = Character("player", "you", "")
    plaza.add_character(player)
    seen = {}

    def make(name):
        agent = ScriptedAgent(lambda obs: None)
        # _credit_stop_for_conversation (issue #778) reads agent.schedule
        # directly once a real conversation happens; a scripted test agent
        # has no schedule of its own, so give it an inert one.
        agent.schedule = None

        def rule(observation, partner_name):
            seen.setdefault(name, []).append(observation)
            agent.last_dialogue_done = True
            return "Hello."

        agent.converse_rule = rule
        ch = Character(name, name, "")
        ch.set_agent(agent)
        plaza.add_character(ch)
        return ch

    a, b = make("alice"), make("bob")
    game = Game(plaza, player, characters=[a, b])
    return game, a, b, seen


def _state(names):
    return {n: {"performing": True, "path": [], "conversing": False} for n in names}


def test_maybe_converse_records_visits_and_grounds_the_prompt():
    game, a, b, seen = _world()
    state = _state(["alice", "bob"])
    chars = {"alice": a, "bob": b}
    frame = {"alice": {}, "bob": {}}

    cognition.maybe_converse(
        game, chars, state, frame, 1, {}, ["alice", "bob"], active={}
    )

    # Visit history accumulated as a LIST (never a set -- cassette keys hash
    # the rendered prompt, so ordering must be stable).
    assert state["alice"]["visited"] == ["Plaza"]
    assert isinstance(state["alice"]["visited"], list)

    # The speaker's observation names the real world and where it stands.
    first = seen["alice"][0]
    assert first.split("\n")[0].startswith("You are talking with")
    assert "Places in this world you can walk to: Field, Plaza." in first
    assert "You are at Plaza." in first


def test_visited_accumulates_across_steps_without_duplicates():
    game, a, b, seen = _world()
    state = _state(["alice", "bob"])
    chars = {"alice": a, "bob": b}
    frame = {"alice": {}, "bob": {}}
    order = ["alice", "bob"]

    cognition.maybe_converse(game, chars, state, frame, 1, {}, order, active={})
    # Walk alice to the Field, then run another step.
    game.locations["Plaza"].remove_character(a)
    game.locations["Field"].add_character(a)
    cognition.maybe_converse(game, chars, state, frame, 2, {}, order, active={})

    assert state["alice"]["visited"] == ["Plaza", "Field"]  # first-visit order
