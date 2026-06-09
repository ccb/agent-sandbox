from __future__ import annotations

from dataclasses import dataclass
from enum import Enum

from .base import Thing
from .items import Item
from .locations import Location


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
    * An inventory of items that they are carrying (a dictionary mapping from
      item name to Item instance)
    * TODO: A dictionary of items that they are currently wearing
    * TODO: A dictionary of items that they are currently weilding
    """

    def __init__(
        self, name: str, description: str, persona: str, goals: list[Goal] | None = None
    ):
        super().__init__(name, description)
        self.set_property("character_type", "notset")
        self.set_property("is_dead", False)
        self.persona = persona
        self.inventory = {}
        self.location = None
        self.behavior = None
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

        inventory = {}
        for k, v in self.inventory.items():
            if hasattr(v, "to_primitive"):
                inventory[k] = v.to_primitive()
            else:
                inventory[k] = v
        thing_data["inventory"] = inventory

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

    def set_behavior(self, fn):
        """
        Assign a behavior function that will be called each turn.
        fn should be a callable with signature (character, game) -> None.
        """
        self.behavior = fn

    def take_turn(self, game):
        """
        Called by Game.end_turn() for each living NPC. Delegates to the
        behavior function if one has been set.
        """
        if self.behavior is not None:
            self.behavior(self, game)

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
