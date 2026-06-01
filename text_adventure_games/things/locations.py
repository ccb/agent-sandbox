"""
Locations

Locations are the places in the game that a player can visit.  They are
connected to other locations and contain items that the player can interact
with.  A connection to an adjacent location can be blocked (often introducing
a puzzle for the player to solve before making progress).
"""

from .base import Thing
from .items import Item


class Location(Thing):
    """
    Locations are the places in the game that a player can visit. Internally
    they are represented nodes in a graph.  Each location stores a description
    of the location, any items in the location, its connections to adjacent
    locations, and any blocks that prevent movement to an adjacent location.
    The connections is a dictionary whose keys are directions and whose values
    are the location that is the result of traveling in that direction. The
    travel_descriptions also has directions as keys, and its values are an
    optional short desciption of traveling to that location.
    """

    def __init__(self, name: str, description: str):
        super().__init__(name, description)
        # Dictionary mapping from directions to other Location objects
        self.connections = {}

        # Dictionary mapping from directions to text describing traveling in
        # that direction
        self.travel_descriptions = {}

        # Dictionary mapping from a direction to a Block.
        self.blocks = {}

        # Dictionary mapping from item name to Item objects present in this
        # location
        self.items = {}

        # Dictionary mapping from item name to Character objects present in
        # this location
        self.characters = {}

        # Flag that gets set to True once this location has been visited by
        # player
        self.has_been_visited = False

    def to_primitive(self):
        """
        Converts this object into a dictionary of values the can be safely
        serialized to JSON.

        Notice that object instances are replaced with their name. This
        prevents circular references that interfere with recursive
        serialization.
        """
        thing_data = super().to_primitive()

        blocks = {k: v.to_primitive() for k, v in self.blocks.items()}
        thing_data["blocks"] = blocks

        connections = {}
        for k, v in self.connections.items():
            if v and hasattr(v, "name"):
                connections[k] = v.name
            else:
                connections[k] = v
        thing_data["connections"] = connections

        if not "travel_descriptions" in thing_data:
            thing_data["travel_descriptions"] = {}
            for k in self.connections:
                thing_data["travel_descriptions"][k] = ""

        thing_data["travel_descriptions"] = self.travel_descriptions

        items = {k: Item.to_primitive(v) for k, v in self.items.items()}
        thing_data["items"] = items

        characters = {}
        for k, v in self.characters.items():
            if v and hasattr(v, "name"):
                characters[k] = v.name
            else:
                characters[k] = v
        thing_data["characters"] = characters

        thing_data["has_been_visited"] = self.has_been_visited

        return thing_data

    @classmethod
    def from_primitive(cls, data):
        """
        Converts a dictionary of primitive values into an item instance.

        Notice that the from_primitive method is called for items.
        """
        instance = cls(data["name"], data["description"])
        super().from_primitive(data, instance)
        instance.travel_descriptions = data["travel_descriptions"]
        instance.blocks = data["blocks"]  # skeleton doesnt instantiate blocks
        instance.connections = data["connections"]
        instance.items = {k: Item.from_primitive(v) for k, v in data["items"].items()}
        instance.characters = data["characters"]
        instance.has_been_visited = data["has_been_visited"]
        instance.properties = data["properties"]
        return instance

    def add_connection(
        self, direction: str, connected_location, travel_description: str = ""
    ):
        """
        Add a connection from the current location to a connected location.
        Direction is a string that the player can use to get to the connected
        location.  If the direction is a cardinal direction, then we also
        automatically make a connection in the reverse direction.
        """
        direction = direction.lower()
        self.connections[direction] = connected_location
        self.travel_descriptions[direction] = travel_description
        if direction == "north":
            connected_location.connections["south"] = self
            connected_location.travel_descriptions["south"] = ""
        if direction == "south":
            connected_location.connections["north"] = self
            connected_location.travel_descriptions["north"] = ""
        if direction == "east":
            connected_location.connections["west"] = self
            connected_location.travel_descriptions["west"] = ""
        if direction == "west":
            connected_location.connections["east"] = self
            connected_location.travel_descriptions["east"] = ""
        if direction == "up":
            connected_location.connections["down"] = self
            connected_location.travel_descriptions["down"] = ""
        if direction == "down":
            connected_location.connections["up"] = self
            connected_location.travel_descriptions["up"] = ""
        if direction == "in":
            connected_location.connections["out"] = self
            connected_location.travel_descriptions["out"] = ""
        if direction == "out":
            connected_location.connections["in"] = self
            connected_location.travel_descriptions["in"] = ""
        if direction == "inside":
            connected_location.connections["outside"] = self
            connected_location.travel_descriptions["outside"] = ""
        if direction == "outside":
            connected_location.connections["inside"] = self
            connected_location.travel_descriptions["inside"] = ""

    def get_connection(self, direction: str):
        return self.connections.get(direction, None)

    def get_direction(self, location):
        for k, v in self.connections.items():
            if v == location:
                return k
        else:
            return None

    def here(self, thing: Thing, describe_error: bool = True) -> bool:
        """
        Checks if the thing is at the location.
        """
        # The character must be at the location
        if not thing.location == self:
            return False
        else:
            return True

    def get_item(self, name: str):
        """
        Checks if the thing is at the location.
        """
        # The character must be at the location
        return self.items.get(name, None)

    def add_item(self, item):
        """
        Put an item in this location.
        """
        self.items[item.name] = item
        item.location = self
        item.owner = None

    def remove_item(self, item):
        """
        Remove an item from this location (for instance, if the player picks
        it up and puts it in their inventory).
        """
        self.items.pop(item.name)
        item.location = None

    def add_character(self, character):
        """
        Put a character in this location.
        """
        self.characters[character.name] = character
        character.location = self

    def remove_character(self, character):
        """
        Remove a character from this location.
        """
        self.characters.pop(character.name)
        character.location = None

    def is_blocked(self, direction: str) -> bool:
        """
        Check to if there is an obstacle in this direction.
        """
        if direction not in self.blocks:  # JD logical change
            return False
        block = self.blocks[direction]
        return block.is_blocked()

    def get_block_description(self, direction: str):
        """
        Check to if there is an obstacle in this direction.
        """
        if direction not in self.blocks:
            return ""
        else:
            block = self.blocks[direction]
            return block.description

    def add_block(self, blocked_direction: str, block):
        """
        Create an obstacle that prevents a player from moving in the blocked
        location until the preconditions are all met.
        """
        self.blocks[blocked_direction] = block

    def remove_block(self, block):
        for k, b in self.blocks.items():
            if b == block:
                del self.blocks[k]
                break
