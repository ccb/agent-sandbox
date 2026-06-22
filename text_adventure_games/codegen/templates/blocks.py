"""Block template emitters.

Each ``emit_*`` returns a Python source string defining one ``blocks.Block``
subclass. The patterns mirror the reference implementations in
``notebooks/hw1_solution/action_castle.py`` (Troll_Block, Guard_Block,
Door_Block, Darkness).
"""

from __future__ import annotations

from ._common import python_class_name, q as _q  # noqa: F401


def _condition_predicate(cond) -> str:
    """Render one BlockCondition as a Python expression.

    Targets:
      * ``obstacle`` -> ``self.obstacle`` (the troll, the door, the guards)
      * ``location`` -> ``self.location`` (a property of the room itself)
      * ``actor``    -> the ``actor`` argument threaded through
        ``is_blocked``; the predicate short-circuits when no actor is in
        hand (map visualisations, scenario probes pass ``actor=None``).
    """
    prop = _q(cond.property)
    if cond.target == "actor":
        if cond.equals is True:
            return f"(actor is not None and actor.get_property({prop}))"
        if cond.equals is False:
            return f"(actor is None or not actor.get_property({prop}))"
        return (
            f"(actor is not None and "
            f"actor.get_property({prop}) == {_q(cond.equals)})"
        )
    target_attr = {
        "obstacle": "self.obstacle",
        "location": "self.location",
    }.get(cond.target, "self.obstacle")
    if cond.equals is True:
        return f"{target_attr}.get_property({prop})"
    if cond.equals is False:
        return f"not {target_attr}.get_property({prop})"
    return f"{target_attr}.get_property({prop}) == {_q(cond.equals)}"


def emit_property_block(block) -> str:
    """Emit a Block subclass whose is_blocked() ANDs property predicates.

    Covers Action Castle's Troll_Block, Guard_Block, and Door_Block.
    """
    cls = python_class_name(block.name) if block.name else python_class_name(block.id)
    obstacle = block.obstacle
    obstacle_kind = obstacle.kind  # "character" | "item"
    obstacle_name = obstacle.name
    desc = block.description or "Your way is blocked"
    msg = block.block_message or desc
    lethal = getattr(block, "lethal", False)
    carries_prop = getattr(block, "unblocked_if_actor_carries_property", None)

    # Construct the predicates. The obstacle must be at the location (for
    # characters) or held by the location (for items) for the block to
    # apply; that matches the reference's guard.
    lines = [
        f"class {cls}(blocks.Block):",
        f'    """Auto-generated property block (target={obstacle_kind!r}={obstacle_name!r})."""',
        "",
        f"    def __init__(self, location, obstacle):",
        f"        super().__init__({_q(desc)}, {_q(msg)})",
        "        self.location = location",
        "        self.obstacle = obstacle",
    ]
    if lethal:
        # Crossing this block ends the run; Go reads self.lethal (see
        # actions/locations.py) and triggers game-over with the message.
        lines.append("        self.lethal = True")
    lines += [
        "",
        "    def is_blocked(self, actor=None) -> bool:",
        "        if not self.obstacle:",
        "            return False",
    ]
    if obstacle_kind == "character":
        # Character must be present at the location to block movement.
        lines.append("        if self.obstacle.location is not self.location:")
        lines.append("            return False")
    else:  # item
        lines.append("        if self.obstacle.name not in self.location.items:")
        lines.append("            return False")
    for cond in block.conditions:
        pred = _condition_predicate(cond)
        # The block is blocked iff every condition holds.
        lines.append(f"        if not ({pred}):")
        lines.append("            return False")
    if carries_prop:
        # Carrying the right item lets the traveller pass (e.g. a sharp weapon
        # past the catfish). Like the actor-target condition, this short-
        # circuits to "blocked" when there's no actor in hand (a None-actor
        # query can't be carrying anything).
        lines += [
            "        if actor is not None:",
            "            for item in actor.inventory.values():",
            f"                if item.get_property({_q(carries_prop)}):",
            "                    return False",
        ]
    lines.append("        return True")
    return "\n".join(lines) + "\n"


def emit_darkness_block(block) -> str:
    """Emit a Darkness-style block: unblocks if any character in the location
    carries an item with the named property (e.g. ``is_lit``).
    """
    cls = python_class_name(block.name) if block.name else python_class_name(block.id)
    desc = block.description or "Darkness blocks your way"
    msg = block.block_message or "It's too dark to go that way."
    unblock_prop = block.unblocked_if_inventory_has_property

    return f"""\
class {cls}(blocks.Block):
    \"\"\"Auto-generated darkness block: unblocks if any character carries an
    item with property {unblock_prop!r}.\"\"\"

    def __init__(self, location):
        super().__init__({_q(desc)}, {_q(msg)})
        self.location = location
        self.location.set_property("is_dark", True)

    def is_blocked(self, actor=None) -> bool:
        if not self.location.get_property("is_dark"):
            return False
        for character in self.location.characters.values():
            for item in character.inventory.values():
                if item.get_property({_q(unblock_prop)}):
                    return False
        return True
"""
