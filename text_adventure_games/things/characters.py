from __future__ import annotations

from dataclasses import dataclass
from enum import Enum

from .base import Thing
from .items import Item
from .locations import Location
from ..enums import Property

# Hard cap on actions one NPC may take in a single turn, regardless of budget.
# Guards against a behavior that keeps reporting cheap actions from looping far
# more than is sensible when minutes_per_turn is large (issue #24).
MAX_ACTIONS_PER_TURN = 100


class GoalType(str, Enum):
    """
    An enum that defines the type of goal, whether that be short, medium, or long-term
    Can be accessed via . notation, i.e., GoalType.SHORT == "short"
    """

    SHORT = "short"
    MEDIUM = "medium"
    LONG = "long"


@dataclass
class Goal:
    description: str
    type: GoalType
    done: bool = False


class Character(Thing):
    """
    This class represents the player and non-player characters (NPC).
    Characters have:
    * A name (cab be general like "gravedigger")
    * A description ('You might want to talk to the gravedigger, specially if
      your looking for a friend, he might be odd but you will find a friend in
      him.')
    * A persona written in the first person ("I am low paid labor in this town.
      I do a job that many people shun because of my contact with death. I am
      very lonely and wish I had someone to talk to who isn't dead.")
    * A location (the place in the game where they currently are)
    * An inventory of items the character is carrying (a dictionary mapping
      item name to Item instance)
    * ``worn`` and ``wielded``: same shape as ``inventory``, for items
      currently equipped. The three dicts are mutually exclusive -- an item
      lives in exactly one of them at a time. Moving an item between slots
      is done with ``wear``/``take_off``/``wield``/``unwield``.
    """

    def __init__(
        self, name: str, description: str, persona: str, goals: list[Goal] | None = None
    ):
        super().__init__(name, description)
        self.set_property(Property.CHARACTER_TYPE, "notset")
        self.set_property(Property.IS_DEAD, False)
        self.persona = persona
        self.inventory = {}
        self.worn = {}
        self.wielded = {}
        self.location = None
        self.behavior = None
        self.agent = None
        self.goals = goals if goals else []

    def to_primitive(self):
        """
        Converts this object into a dictionary of values the can be safely
        serialized to JSON.

        Notice that object instances are replaced with their name. This
        prevents circular references that interfere with recursive
        serialization.
        """
        thing_data = super().to_primitive()
        thing_data["persona"] = self.persona

        def _serialize(slot):
            out = {}
            for k, v in slot.items():
                out[k] = v.to_primitive() if hasattr(v, "to_primitive") else v
            return out

        thing_data["inventory"] = _serialize(self.inventory)
        thing_data["worn"] = _serialize(self.worn)
        thing_data["wielded"] = _serialize(self.wielded)

        if self.location and hasattr(self.location, "name"):
            thing_data["location"] = self.location.name
        elif self.location:
            thing_data["location"] = self.location
        thing_data["goals"] = [
            {"description": g.description, "type": g.type.value, "done": g.done}
            for g in self.goals
        ]
        return thing_data

    @classmethod
    def from_primitive(cls, data):
        """
        Converts a dictionary of primitive values into a character instance.

        Notice that the from_primitive method is called for items.
        """
        instance = cls(data["name"], data["description"], data["persona"])
        super().from_primitive(data, instance=instance)
        instance.location = data.get("location", None)
        instance.inventory = {
            k: Item.from_primitive(v) for k, v in data["inventory"].items()
        }
        instance.worn = {
            k: Item.from_primitive(v) for k, v in data.get("worn", {}).items()
        }
        instance.wielded = {
            k: Item.from_primitive(v) for k, v in data.get("wielded", {}).items()
        }
        instance.goals = [
            Goal(d["description"], GoalType(d["type"]), d.get("done", False))
            for d in data.get("goals", [])
        ]
        return instance

    def add_to_inventory(self, item):
        """
        Add an item to the character's inventory.
        """
        if item.location is not None:
            item.location.remove_item(item)
            item.location = None
        self.inventory[item.name] = item
        item.owner = self

    def is_in_inventory(self, item):
        """
        Checks if a character has the item in their inventory
        """
        return item.name in self.inventory

    def remove_from_inventory(self, item):
        """
        Removes an item to a character's inventory.
        """
        item.owner = None
        self.inventory.pop(item.name)

    def wear(self, item):
        """Move an item from ``inventory`` into ``worn``."""
        self.inventory.pop(item.name)
        self.worn[item.name] = item

    def take_off(self, item):
        """Move an item from ``worn`` back into ``inventory``."""
        self.worn.pop(item.name)
        self.inventory[item.name] = item

    def wield(self, item):
        """Move an item from ``inventory`` into ``wielded``."""
        self.inventory.pop(item.name)
        self.wielded[item.name] = item

    def unwield(self, item):
        """Move an item from ``wielded`` back into ``inventory``."""
        self.wielded.pop(item.name)
        self.inventory[item.name] = item

    def is_worn(self, item) -> bool:
        return item.name in self.worn

    def is_wielded(self, item) -> bool:
        return item.name in self.wielded

    def set_behavior(self, fn):
        """
        Assign a behavior function that will be called each turn.
        fn should be a callable with signature (character, game) -> None.
        """
        self.behavior = fn

    def set_agent(self, agent):
        """
        Attach an Agent (see npc.py) as this character's decision-maker.

        In the simultaneous turn mode (issue #25, turns.py) the game loop
        calls agent.decide(observation) directly during the gather phase, so
        the agent must be reachable here rather than hidden inside a behavior
        closure. A character may have an agent, a legacy behavior, or neither.
        Like `behavior`, the agent is runtime-only and is not serialized.
        """
        self.agent = agent

    def take_turn(self, game):
        """
        Called by Game.end_turn() for each living NPC. Runs the character's
        behavior within a per-turn time budget (issue #24).

        The budget equals the clock's minutes_per_turn. A behavior reports the
        in-game minutes it spent by returning that number; the character keeps
        acting while the budget lasts. A behavior that returns None/falsy is
        done for the turn — this is how legacy behaviors (which return None)
        stay at exactly one action per turn. The first action always runs, even
        if it overruns the budget, so an NPC is never starved.

        With no clock there is no budget, so exactly one action runs, as before.
        """
        if self.behavior is None:
            return

        budget = game.clock.minutes_per_turn if game.clock is not None else None
        remaining = budget
        for _ in range(MAX_ACTIONS_PER_TURN):
            spent = self.behavior(self, game)
            if not spent:  # None/0/False -> nothing more to do this turn
                break
            if remaining is None:  # no clock -> single action per turn
                break
            if game.is_game_over() or self.get_property(Property.IS_DEAD):
                break
            remaining -= spent
            if remaining <= 0:
                break

    def add_goal(self, description: str, type: GoalType) -> Goal:
        goal = Goal(description, type)
        self.goals.append(goal)
        return goal

    def complete_goal(self, goal: Goal) -> None:
        goal.done = True

    def goals_by_type(self, goal_type: GoalType) -> list[Goal]:
        """
        Gets all the goals stored in `self.goals` that are incomplete
        and of the specified type (i.e., GoalType.SHORT).
        """
        return [g for g in self.goals if g.type == goal_type and not g.done]

    def replace_goals(self, type: GoalType, descriptions: list[str]) -> None:
        """
        Drops all goals of the tier for when some event occurs (i.e., guard blocking
        castle door is dead).
        """
        self.goals = [g for g in self.goals if g.type != type]
        self.goals.extend(Goal(d, type) for d in descriptions)
