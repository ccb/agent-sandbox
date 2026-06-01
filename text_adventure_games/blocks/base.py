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
            # subclasses hardcode these
            # 'name': self.name,
            # 'description': self.description,
        }
        return data
