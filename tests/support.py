"""Small test-only worlds and structured parsers shared by engine tests."""

from text_adventure_games import games, parsing, things
from text_adventure_games.llm_parser import LlmParser
from text_adventure_games.reporting import JSONRenderer


class BufferedParser(parsing.Parser):
    """A normal parser whose output is available as JSON event records."""

    def __init__(self, game, echo_commands=False):
        super().__init__(game, echo_commands=echo_commands, renderer=JSONRenderer())

    def get_messages(self):
        return self.renderer.drain()


class BufferedLlmParser(LlmParser):
    """An LLM parser whose output is available as JSON event records."""

    def __init__(self, game, llm_client, **kwargs):
        super().__init__(game, llm_client, **kwargs)
        self.set_renderer(JSONRenderer())

    def get_messages(self):
        return self.renderer.drain()


def tiny_agent_game(names=("resident",)):
    """Return a two-room game suitable for parser and agent integration tests."""
    plaza = things.Location("Plaza", "A busy campus plaza.")
    library = things.Location("Library", "A quiet library.")
    plaza.add_connection("north", library)
    player = things.Character("player", "a visitor", "I explore the campus.")
    residents = []
    for name in names:
        resident = things.Character(name, f"{name} is here", f"I am {name}.")
        plaza.add_character(resident)
        residents.append(resident)
    game = games.Game(plaza, player, characters=residents)
    game.set_parser(BufferedParser(game))
    game.parser.get_messages()
    return game
