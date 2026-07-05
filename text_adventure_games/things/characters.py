from __future__ import annotations

from dataclasses import dataclass
from enum import Enum

from .base import Thing
from .items import Item
from .locations import Location
from ..enums import Property
from ..knowledge import Belief, Knowledge

# Hard cap on actions one NPC may take in a single turn, regardless of budget.
# Guards against a behavior that keeps reporting cheap actions from looping far
# more than is sensible when minutes_per_turn is large (issue #24).
MAX_ACTIONS_PER_TURN = 100

# How many recently-heard utterances a character retains. Kept small so the
# buffer stays bounded; older lines fall off FIFO.
HEARD_MAX = 5

# Default vision radius (issue #80): how far a character perceives, measured in
# room hops over the location graph. 0 means "only the current room" -- the same
# scope perception had before #80, so existing games stay byte-identical until a
# game opts in by setting a larger radius. Smallville maps its tile ``vision_r=8``
# onto this seam by overriding ``Game.perceivable_locations``.
DEFAULT_VISION_R = 0


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
    * A ``vision_r`` (issue #80): how far this character perceives, in room
      hops. 0 (the default) means just the current room. Read by
      ``Game.perceivable_locations`` when folding the nearby world into memory.
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
        # The last action this character successfully took (a runtime field, not
        # serialized). Per-actor so the turn loop can charge its duration without
        # a single global parser.last_action that the next actor would overwrite.
        self.last_action = None
        # Base hand limit (issue #43). None means unlimited so existing games
        # are unchanged. Container `contents` do not count against this; the
        # container item itself occupies one hand slot.
        self.carry_capacity = None
        # Vaarn item slots (see slots.py) -- the shared carrying/harm gauge.
        # None (default) = unlimited and wound-limitless, so existing games are
        # unchanged; a game opts in per character (player.slot_capacity = 10).
        # Capacity is a hard limit: GET refuses past it, a FULL gauge is
        # Encumbered (you clatter; you cannot climb), a new wound shoves random
        # gear out of the pack to make room, and wounds alone filling capacity
        # kill. Runtime-only (not serialized), like behavior/reactions.
        self.slot_capacity = None
        self.wounds: list = []
        self.location = None
        self.behavior = None
        self.agent = None
        # Following (issue #112): the character this one is currently following,
        # or None. When a character moves, the engine drags its followers along
        # (Game.drag_followers). `follow_filter`, if set, is a runtime callable
        # (location) -> bool that lets a follower refuse certain destinations
        # (e.g. a companion who won't enter the dungeon); like `behavior`, it is
        # not serialized.
        self.following = None
        self.follow_filter = None
        # The vehicle/mount this character is currently riding, or None (issue:
        # vehicles). When the rider moves, the engine brings the vehicle along
        # (Game.relocate). Runtime ref; serialized by name like `following`.
        self.riding = None
        # Canned dialogue surfaced by the Talk action (player-facing, authored;
        # runtime-only like `behavior`). `talk_text` is the default line for
        # "talk to X"; `talk_topics` maps a topic keyword to a line for
        # "talk to X about <topic>" / "ask X about <topic>". Lines are printed
        # verbatim (write them as full narration, with any quotes included).
        self.talk_text = ""
        self.talk_topics: dict[str, str] = {}
        self.goals = goals if goals else []
        # Recently perceived utterances (e.g. speech heard this round). Scoped
        # per-character: only lines delivered here are visible to this
        # character, so dialogue never leaks across rooms. Runtime-only --
        # like `behavior` and `agent`, it is not serialized.
        self.heard: list[str] = []
        # What this character believes about the world (issue #45). Empty by
        # default, so existing games/characters are unchanged. Distinct from
        # memory (#37): knowledge is the current world-model; memory is the log.
        self.knowledge = Knowledge(owner=name)
        # How far this character perceives, in room hops (issue #80). 0 keeps
        # perception to the current room, byte-identical to before #80.
        self.vision_r = DEFAULT_VISION_R
        # Physical appearance for a mirror's reflection: an ordered mapping of
        # feature -> an authored clause about it ({"hair": "Your hair is long."}).
        # The key lets a game update one trait live (cut hair -> rewrite "hair")
        # without canned, going-stale examine text. Empty by default; clothing is
        # NOT stored here -- the mirror reads `worn` directly. See `reflection`.
        self.appearance: dict[str, str] = {}

    def reflection(self, include_room: bool = False) -> str:
        """What this character sees of themselves in a mirror, composed live:
        their `appearance` clauses, then a "You're wearing ..." line built from
        `worn`, with a non-descript fallback when they have neither. Optionally
        appends the room, reflected. (Used by Examine on an ``is_mirror`` item.)"""

        def _join(phrases):
            phrases = list(phrases)
            if len(phrases) <= 1:
                return "".join(phrases)
            if len(phrases) == 2:
                return f"{phrases[0]} and {phrases[1]}"
            return ", ".join(phrases[:-1]) + f", and {phrases[-1]}"

        parts = []
        clauses = [c for c in self.appearance.values() if c]
        if clauses:
            parts.append(" ".join(clauses))
        worn = [it.description for it in self.worn.values()]
        if worn:
            parts.append("You're wearing " + _join(worn) + ".")
        if not parts:
            parts.append("You see yourself and the room reflected back at you.")
        if include_room and self.location is not None:
            parts.append(
                f"Behind you, the {self.location.name} is reflected, reversed."
            )
        return " ".join(parts)

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
        thing_data["carry_capacity"] = self.carry_capacity

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
        # `following` is a back-reference to another character; store the name
        # only (the runtime ref is re-established by the game, like `behavior`).
        if self.following is not None:
            thing_data["following"] = getattr(self.following, "name", self.following)
        if self.riding is not None:
            thing_data["riding"] = getattr(self.riding, "name", self.riding)
        thing_data["goals"] = [
            {"description": g.description, "type": g.type.value, "done": g.done}
            for g in self.goals
        ]
        thing_data["knowledge"] = self.knowledge.to_primitive()
        thing_data["vision_r"] = self.vision_r
        thing_data["appearance"] = dict(self.appearance)
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
        instance.carry_capacity = data.get("carry_capacity", None)
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
        # .get default keeps save files written before issue #45 loadable.
        instance.knowledge = Knowledge.from_primitive(
            data.get("knowledge", {"owner": data["name"], "beliefs": []})
        )
        # .get default keeps save files written before issue #80 loadable.
        instance.vision_r = data.get("vision_r", DEFAULT_VISION_R)
        instance.appearance = dict(data.get("appearance", {}))
        return instance

    def add_to_inventory(self, item):
        """
        Add an item to the character's inventory. A stackable item merges into a
        same-named stack already held (#134).
        """
        if item.location is not None:
            item.location.remove_item(item)
            item.location = None
        existing = self.inventory.get(item.name)
        if item.is_stackable() and existing is not None and existing.is_stackable():
            existing.quantity += item.quantity
            existing.set_owner(self)
            return
        self.inventory[item.name] = item
        item.set_owner(self)

    def is_in_inventory(self, item):
        """
        Checks if a character has the item in their inventory
        """
        return item.name in self.inventory

    def remove_from_inventory(self, item):
        """
        Removes an item to a character's inventory.
        """
        item.set_owner(None)
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

    def has_hand_space(self):
        """True if the character can hold another item directly in hand."""
        return self.carry_capacity is None or len(self.inventory) < self.carry_capacity

    def available_container(self):
        """The first carried container with room, or None."""
        for item in self.inventory.values():
            if item.get_property("is_container") and item.has_space():
                return item
        return None

    def can_accept_item(self):
        """True if a newly picked-up item could go somewhere (hands or a
        carried container)."""
        return self.has_hand_space() or self.available_container() is not None

    def accept_item(self, item):
        """Place `item` in hands if there is room, else into a carried
        container. Returns True if placed, False if there is no room."""
        if self.has_hand_space():
            self.add_to_inventory(item)
            return True
        container = self.available_container()
        if container is not None:
            container.add_item(item)
            return True
        return False

    def visible_description(self) -> str:
        """The one-liner shown in room listings, honoring state: a dead or
        unconscious character shouldn't still read as swaying and listening.
        Games may author ``dead_description`` / ``unconscious_description``;
        otherwise a plain flat default is derived from the name."""
        if self.get_property("is_dead"):
            return self.get_property("dead_description") or f"{self.name}, dead"
        if self.get_property("is_unconscious"):
            return (
                self.get_property("unconscious_description") or f"{self.name}, out cold"
            )
        return self.description

    def carried_items(self):
        """A flat name->Item view of everything carried: top-level inventory
        plus the contents of any carried containers. Used for matching items
        the character can act on (drop, give)."""
        result = {}
        for name, item in self.inventory.items():
            result[name] = item
            if item.get_property("is_container"):
                for cname, citem in item.contents.items():
                    result[cname] = citem
        return result

    def discard_item(self, item):
        """Remove `item` from wherever the character holds it -- their hands or
        a carried container -- clearing ownership."""
        if self.inventory.get(item.name) is item:
            self.remove_from_inventory(item)
        elif item.container is not None:
            item.container.remove_item(item)
            item.set_owner(None)

    # --- Vaarn item slots (see slots.py; all no-ops until slot_capacity set) --

    def item_slots_used(self) -> int:
        """Slots occupied by carried gear: inventory + worn + wielded (each item
        costs its ``slots`` property, default 1; a container's contents ride
        free -- the container declares its own loaded cost if it matters)."""
        from ..slots import item_slot_cost

        seen = []
        for slot in (self.inventory, self.worn, self.wielded):
            for item in slot.values():
                if item not in seen:
                    seen.append(item)
        return sum(item_slot_cost(it) for it in seen)

    def wound_slots(self) -> int:
        """Slots occupied by wounds."""
        return sum(w.slots for w in self.wounds)

    def slots_used(self) -> int:
        return self.item_slots_used() + self.wound_slots()

    def is_encumbered(self) -> bool:
        """The gauge is FULL: movement clatters, and exits a game marks as
        climbs (``climb_exits``) are beyond you."""
        return (
            self.slot_capacity is not None and self.slots_used() >= self.slot_capacity
        )

    def has_slot_space(self, item) -> bool:
        """Whether *item* fits -- capacity is a hard limit. Unlimited when no
        capacity is set."""
        if self.slot_capacity is None:
            return True
        from ..slots import item_slot_cost

        return self.slots_used() + item_slot_cost(item) <= self.slot_capacity

    def add_wound(self, wound, rng=None):
        """Add *wound*. Returns ``(fatal, dropped)``:

        - *fatal*: wounds alone fill capacity (Vaarn: 'if a character fills
          [their] item slots with Wounds they will die') -- IS_DEAD is set.
        - *dropped*: gear the wound displaced. A wound always fits: while the
          gauge overflows, random non-wound items are shed to the character's
          location (inventory first, then worn, then wielded).

        With no capacity set, wounds are tracked but displace nothing and are
        never fatal by accumulation."""
        import random as _random

        self.wounds.append(wound)
        dropped = []
        if self.slot_capacity is None:
            return False, dropped
        if self.wound_slots() >= self.slot_capacity:
            self.set_property(Property.IS_DEAD, True)
            return True, dropped
        rng = rng or _random
        while self.slots_used() > self.slot_capacity:
            pool = (
                list(self.inventory.values())
                or list(self.worn.values())
                or list(self.wielded.values())
            )
            if not pool:
                break
            item = rng.choice(pool)
            for slot in (self.inventory, self.worn, self.wielded):
                if slot.get(item.name) is item:
                    slot.pop(item.name)
                    break
            if self.location is not None:
                self.location.add_item(item)
            dropped.append(item)
        return False, dropped

    def heal_wound(self):
        """Remove and return the most recent wound (None if unhurt) -- the hook
        a game's rest/water/medicine mechanic calls."""
        return self.wounds.pop() if self.wounds else None

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

    def hear(self, utterance: str) -> None:
        """Record something this character perceived. The buffer keeps only the
        most recent entries (FIFO) so it stays bounded. The cap is
        ``self.heard_max`` -- set from config when the character is added to a
        game -- falling back to the module default HEARD_MAX otherwise."""
        cap = getattr(self, "heard_max", HEARD_MAX)
        self.heard.append(utterance)
        if len(self.heard) > cap:
            self.heard = self.heard[-cap:]

    def clear_heard(self) -> None:
        """Forget everything recently heard."""
        self.heard = []

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
        max_actions = getattr(game, "_max_actions_per_turn", MAX_ACTIONS_PER_TURN)
        for _ in range(max_actions):
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

    def add_belief(
        self, text: str, topic: str | None = None, learned_turn: int | None = None
    ) -> Belief:
        """Add a belief to this character's knowledge (mirrors add_goal).

        See text_adventure_games/knowledge.py. ``topic`` doubles as a key that
        unlocks perception of a Thing flagged with a matching ``secret_topic``.
        """
        return self.knowledge.add(text, topic=topic, learned_turn=learned_turn)
