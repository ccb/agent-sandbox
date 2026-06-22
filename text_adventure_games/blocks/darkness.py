from .base import Block
from ..enums import Property


class Darkness(Block):
    """Blocks travel in a direction while the location is dark and nobody
    present carries a lit light source.

    Construction flags the location ``is_dark`` (so other code can ask), and
    the block clears the moment any character in the room holds a lit item --
    in hand, worn, wielded, or inside an open carried container. That last case
    matters: a lantern stuffed in a backpack still lights the way once it's lit,
    so the player doesn't have to fish it out first.

    Wire it like any block::

        cave = Location("Cave", "...")
        entrance.add_block("in", Darkness(cave))   # the "in" exit is dark

    (Generalizes the per-game Darkness that previously lived in the Action
    Castle adventure; promoted here so every game can reuse it -- issue #110's
    sibling: each playtest finding becomes a reusable engine feature.)
    """

    def __init__(self, location, description: str = "It's too dark to see!"):
        super().__init__("Darkness blocks your way", description)
        self.location = location
        location.set_property(Property.IS_DARK, True)

    @staticmethod
    def _carries_light(character) -> bool:
        """True if *character* holds a lit item anywhere it would shed light:
        hands, worn, wielded, or an open carried container."""
        slots = (
            getattr(character, "inventory", {}),
            getattr(character, "worn", {}),
            getattr(character, "wielded", {}),
        )
        for slot in slots:
            for item in slot.values():
                if item.get_property(Property.IS_LIT):
                    return True
                # A lit light source inside an open container (e.g. a lantern in
                # an open backpack) still lights the room.
                for inner in item.accessible_contents().values():
                    if inner.get_property(Property.IS_LIT):
                        return True
        return False

    def is_blocked(self) -> bool:
        if not self.location.get_property(Property.IS_DARK):
            return False
        for character in self.location.characters.values():
            if self._carries_light(character):
                return False
        return True

    def to_primitive(self):
        data = super().to_primitive()
        if self.location and hasattr(self.location, "name"):
            data["location"] = self.location.name
        elif "location" in data:
            data["location"] = self.location
        data["description"] = self.description
        return data

    @classmethod
    def from_primitive(cls, data):
        # `location` is rehydrated to a name here; the game re-establishes the
        # live reference when blocks are re-wired (mirrors Locked_Door).
        instance = cls(data["location"], description=data.get("description"))
        return instance
