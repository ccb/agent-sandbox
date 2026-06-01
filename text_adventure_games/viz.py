from .things import Character, Item, Location
from . import actions
from .games import Game

from graphviz import Digraph
from IPython.display import Image
import queue


class Visualizer:
    """
    Our games are implemented as directed graphs, where the locations
    are nodes, and the connections are arcs.  Here we create a visualization
    using graphviz.
    """

    def __init__(self, game: Game, verbose=True):
        self.game = game
        self.verbose = verbose

    def visualize(self) -> Digraph:
        """Creates a visualization of the game with graphviz by doing
        a depth-first-search traversal of the locations in the game
        starting at the start location, and create a GraphViz graph
        to vizualize the connections between the locations, and the items
        that are located at each location."""
        graph = Digraph(node_attr={"color": "lightblue2", "style": "filled"})
        start_location = self.game.player.location
        frontier = queue.Queue()
        frontier.put(start_location)
        visited = {}
        visited[start_location.name] = True

        while not frontier.empty():
            current_location = frontier.get()
            self.game.player.location = current_location
            name = current_location.name
            if self.verbose:
                description = current_location.description
            else:
                description = ""
            items_html = self.describe_items(current_location)
            characters_html = self.describe_characters(current_location)
            html = "<<b>%s</b><br />%s<br />%s <br />%s>" % (
                name,
                description,
                items_html,
                characters_html,
            )
            #    html = "<<b>%s</b>>" % (name)
            # Create a new node in the graph for this location
            graph.node(name, label=html)

            connections = current_location.connections
            for direction in connections.keys():
                next_location = connections[direction]
                if not current_location.is_blocked(direction):
                    # Create an edge between the current location and its successor
                    graph.edge(name, next_location.name, label=direction.capitalize())
                else:
                    # Create a dotted edge for connected locations that are blocked
                    block_description = "%s\n%s" % (
                        direction.capitalize(),
                        current_location.get_block_description(direction),
                    )
                    graph.edge(
                        name,
                        next_location.name,
                        label=block_description,
                        style="dotted",
                    )
                if not next_location.name in visited:
                    visited[next_location.name] = True
                    frontier.put(next_location)
        return graph

    def describe_items(self, location, give_hints=True):
        """Describe what objects are in the current location."""
        items_html = ""
        if len(location.items.keys()) > 0 and self.verbose:
            items_html = "You see: "
            for item_name in location.items:
                item = location.items[item_name]
                items_html += item.description
                if give_hints:
                    special_commands = item.get_command_hints()
                    for cmd in special_commands:
                        items_html += "<br/><i>%s</i>" % cmd
        elif len(location.items.keys()) > 0:
            items_html = "Items: " + "<br />".join(list(location.items))

        return items_html

    def describe_characters(self, location, give_descriptions=False):
        """Describe what characters are in the current location."""
        characters_html = ""
        if len(location.characters.keys()) > 0:
            characters_html = "Characters: "
        for character_name in location.characters:
            character = location.characters[character_name]
            characters_html += character.name.capitalize()
            if give_descriptions and self.verbose:
                characters_html += "&mdash; <i>%s</i>" % character.description
        return characters_html
