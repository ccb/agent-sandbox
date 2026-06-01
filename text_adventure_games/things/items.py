from .base import Thing


class Item(Thing):
    """Items are objects that a player can get, or scenery that a player can
    examine."""

    def __init__(
        self,
        name: str,
        description: str,
        examine_text: str = "",
    ):
        super().__init__(name, description)

        # The detailed description of the player examines the object.
        self.examine_text = examine_text

        # If an item is gettable, then the player can get it and put it in
        # their inventory.
        self.set_property("gettable", True)

        # It might be at a location
        self.location = None

        # It might be in a character's inventory
        self.owner = None

    def to_primitive(self):
        """
        Converts this object into a dictionary of values the can be safely
        serialized to JSON.

        Notice that object instances are replaced with their name. This
        prevents circular references that interfere with recursive
        serialization.
        """
        thing_data = super().to_primitive()

        if not "examine_text" in thing_data:
            thing_data["examine_text"] = thing_data["description"]

        thing_data["examine_text"] = self.examine_text

        if self.location and hasattr(self.location, "name"):
            thing_data["location"] = self.location.name
        elif self.location and isinstance(self.location, str):
            thing_data["location"] = self.location

        if self.owner and hasattr(self.owner, "name"):
            thing_data["owner"] = self.owner.name
        elif self.owner and isinstance(self.owner, str):
            thing_data["owner"] = self.owner

        return thing_data

    @classmethod
    def from_primitive(cls, data):
        """
        Converts a dictionary of primitive values into an item instance.
        """
        instance = cls(data["name"], data["description"], data["examine_text"])
        super().from_primitive(data, instance)
        if "location" in data:
            instance.location = data["location"]
        if "owner" in data:
            instance.owner = data["owner"]
        return instance
