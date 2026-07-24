"""Blocks

Blocks are things that prevent movement in a direction - for examlpe a locked
door may prevent you from entering a room, or a hungry troll might block you
from crossing the drawbridge.  We implement them similarly to how we did
Special Actions.

CCB - todo - consider refacoring Block to be Connection that join two
locations.  Connection could support the is_blocked() method, and also be a
subtype of Item which might make it easier to create items that are shared
between two locations (like doors).
"""


class Block:
    """Blocks are things that prevent movement in a direction."""

    def __init__(self, name, description):
        self.name = name
        self.description = description

    def is_blocked(self) -> bool:
        return True

    def to_primitive(self):
        cls_type = self.__class__.__name__
        data = {
            "_type": cls_type,
            # The defining module, so Game.from_primitive can re-import a
            # game-specific block class even when the loader wasn't handed
            # it via custom_blocks (issue #744).
            "_module": self.__class__.__module__,
            # subclasses hardcode these
            # 'name': self.name,
            # 'description': self.description,
        }
        return data

    @classmethod
    def from_primitive(cls, data):
        """
        Recreate a block from its primitive data. By the time this is called,
        Game.from_primitive has already swapped saved thing names back to the
        live instances, so `data` maps constructor arguments to real objects.

        This default assumes the keys a subclass saved in its to_primitive
        match its constructor's arguments (as they do for the blocks in this
        package). A block that saves extra state should override this.
        """
        return cls(**data)
