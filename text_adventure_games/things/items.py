from .base import Thing
from ..enums import Property


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
        self.set_property(Property.GETTABLE, True)

        # It might be at a location
        self.location = None

        # It might be in a character's inventory
        self.owner = None

        # Container support (issue #43). A plain item is not a container.
        # When `is_container` is True, `contents` holds items by name and
        # `capacity` is the max item count (None means unlimited).
        self.capacity = None
        self.contents = {}

        # The container Item currently holding this one (None if held in hands
        # or sitting at a location).
        self.container = None

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

    def make_container(self, capacity=None):
        """Declare this item a container that holds up to `capacity` items
        (None = unlimited). Returns self so authors can chain."""
        self.set_property("is_container", True)
        self.capacity = capacity
        return self

    def current_count(self):
        """Number of items currently inside this container."""
        return len(self.contents)

    def has_space(self):
        """True if another item can be added (always True when unlimited)."""
        return self.capacity is None or self.current_count() < self.capacity

    def is_full(self):
        return not self.has_space()

    def add_item(self, item):
        """Put `item` inside this container. Removes it from any location and
        records the back-reference and carrying owner."""
        if item.location is not None and hasattr(item.location, "remove_item"):
            item.location.remove_item(item)
            item.location = None
        self.contents[item.name] = item
        item.container = self
        item.owner = self.owner

    def remove_item(self, item):
        """Take `item` out of this container, clearing its back-reference."""
        self.contents.pop(item.name, None)
        item.container = None
