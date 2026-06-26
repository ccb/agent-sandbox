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

        # Stacking (issue #134). A plain item is a single unit. An item declared
        # `stackable` represents a quantity of identical, fungible units: a
        # holder keeps ONE name->item entry whose `quantity` is the count, and
        # same-named stackable items MERGE on add. Default items never stack, so
        # unique narrative objects (a lit lamp, a named sword) are unaffected.
        self.quantity = 1

    def make_stackable(self, quantity: int = 1):
        """Declare this item a stack of `quantity` identical units. Stackable
        items merge with same-named stackable items when added to a holder, and
        crafting/inventory count their `quantity`. Returns self for chaining.

        Stackable implies FUNGIBLE: don't mark something stackable if individual
        units carry their own state (a lit vs. unlit lantern), since merging
        treats them as interchangeable."""
        self.set_property("stackable", True)
        self.quantity = quantity
        return self

    def is_stackable(self) -> bool:
        return bool(self.get_property("stackable"))

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

        thing_data["capacity"] = self.capacity
        if self.quantity != 1:
            thing_data["quantity"] = self.quantity
        if self.contents:
            contents = {}
            for k, v in self.contents.items():
                contents[k] = v.to_primitive() if hasattr(v, "to_primitive") else v
            thing_data["contents"] = contents
        # `container` is a back-reference to the parent container item. It is
        # implied by membership in `contents` and would create a circular
        # reference if serialized recursively, so we store only the name.
        if self.container and hasattr(self.container, "name"):
            thing_data["container"] = self.container.name
        elif self.container and isinstance(self.container, str):
            thing_data["container"] = self.container

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
        instance.capacity = data.get("capacity", None)
        instance.quantity = data.get("quantity", 1)  # default 1 for pre-#134 saves
        if "contents" in data:
            instance.contents = {
                k: Item.from_primitive(v) for k, v in data["contents"].items()
            }
        # `container` is a runtime back-reference; we intentionally do not
        # restore it here (the field stays None) to avoid storing a stale
        # string reference and to match the test expectation.
        return instance

    def make_container(self, capacity=None):
        """Declare this item a container that holds up to `capacity` items
        (None = unlimited). Returns self so authors can chain."""
        self.set_property("is_container", True)
        self.capacity = capacity
        return self

    def set_owner(self, owner):
        """Set this item's carrying owner, propagating to any contained items
        so a whole loaded container changes hands at once."""
        self.owner = owner
        for item in self.contents.values():
            item.set_owner(owner)

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
        records the back-reference and carrying owner. A stackable item merges
        into a same-named stack already here (#134)."""
        if item.location is not None and hasattr(item.location, "remove_item"):
            item.location.remove_item(item)
            item.location = None
        existing = self.contents.get(item.name)
        if item.is_stackable() and existing is not None and existing.is_stackable():
            existing.quantity += item.quantity
            return
        self.contents[item.name] = item
        item.container = self
        item.set_owner(self.owner)

    def remove_item(self, item):
        """Take `item` out of this container, clearing its back-reference."""
        self.contents.pop(item.name, None)
        item.container = None

    def make_vehicle(self, ready: bool = True):
        """Declare this item a vehicle/mount the player can ride (see
        actions/vehicles.py). A vehicle that needs activation first -- a key for
        a motorcycle, taming for a horse -- starts ``ready=False``; a
        game-specific verb flips ``vehicle_ready`` true. Returns self for
        chaining."""
        self.set_property("is_vehicle", True)
        self.set_property("vehicle_ready", ready)
        return self

    def is_vehicle(self) -> bool:
        return bool(self.get_property("is_vehicle"))

    def vehicle_ready(self) -> bool:
        return bool(self.get_property("vehicle_ready"))

    def make_surface(self, capacity=None):
        """Declare this item a surface: things rest ON it and are always in
        view (no open/closed). A surface shares the container storage --
        ``contents`` / ``add_item`` / ``remove_item`` / ``capacity`` -- so it's a
        holder like a container; it differs only in the spatial relation ("on"
        vs "in") and in never being closed. Returns self so authors can chain."""
        self.set_property("is_surface", True)
        self.capacity = capacity
        return self

    def is_holder(self) -> bool:
        """True if this item can hold other items -- a container ("in") or a
        surface ("on")."""
        return bool(
            self.get_property("is_container") or self.get_property("is_surface")
        )

    def is_open(self) -> bool:
        """Whether a holder's contents are reachable/visible right now.
        Surfaces are always open; a container is open unless ``is_closed``."""
        return not (
            self.get_property("is_container") and self.get_property("is_closed")
        )

    def accessible_contents(self):
        """The held items reachable from outside right now: ``contents`` if this
        is an OPEN holder, else an empty dict. This is the single place the
        engine asks "what's inside/on this that I can see or take?" -- shared by
        scope resolution, Get, and Examine, so containers and surfaces are
        handled uniformly. Hidden items (concealed until a SEARCH reveals them)
        are excluded."""
        if not (self.is_holder() and self.is_open()):
            return {}
        return {
            name: it
            for name, it in self.contents.items()
            if not it.get_property("is_hidden")
        }

    def preposition(self) -> str:
        """ "on" for a surface, "in" for a container -- for listings/messages."""
        return "on" if self.get_property("is_surface") else "in"
