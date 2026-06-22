from . import base
from .consume import Drink, Eat
from .rose import Smell_Rose
from ..enums import ActionName, Property


class Get(base.Action):
    ACTION_NAME = ActionName.GET
    ACTION_DESCRIPTION = "Get something and add it to the inventory"
    ACTION_ALIASES = ["take"]

    def __init__(self, game, command: str, actor=None):
        super().__init__(game, actor=actor)
        self.character = self.acting_character(command, hint="wants to get something")
        self.location = self.character.location
        # You can pick up items lying in the room, items inside an OPEN holder
        # sitting in the room -- a container (blanket in a boat) or a surface
        # (candle on a table) -- and items inside an OPEN holder the character
        # is carrying (gear stowed in a backpack). Track the source holder so
        # apply_effects removes the item from there.
        self.holders = [
            it for it in self.location.items.values() if it.accessible_contents()
        ] + [it for it in self.character.inventory.values() if it.accessible_contents()]
        scope = dict(self.location.items)
        for h in self.holders:
            for cname, citem in h.accessible_contents().items():
                scope.setdefault(cname, citem)
        self.item = self.parser.match_item(command, scope, hint="thing to get")
        self.source_holder = None
        if self.item is not None and self.item.name not in self.location.items:
            for h in self.holders:
                if self.item.name in h.contents:
                    self.source_holder = h
                    break

    def claimed_resource(self):
        """Two characters grabbing for the same item contend over it (#42)."""
        return self.item

    def check_preconditions(self) -> bool:
        """
        Preconditions:
        * The item must be matched.
        * The character must be at the location
        * The item must be at the location
        * The item must be gettable
        """
        if not self.was_matched(self.item, "I don't see it."):
            message = "I don't see it."
            self.parser.fail(message)
            return False
        if not self.at(self.character, self.location):
            return False
        # The item is reachable if it lies in the room, or sits in an open
        # holder (container or surface) that is in the room.
        if self.source_holder is None and not self.at(self.item, self.location):
            return False
        if not self.has_property(
            self.item,
            "gettable",
            error_message="{name} is not gettable.".format(
                name=self.item.name.capitalize()
            ),
        ):
            return False
        if not self.character.can_accept_item():
            self.parser.fail(
                "Your hands are full and you have nothing with room to stow it."
            )
            return False
        return True

    def apply_effects(self):
        """
        Get's an item from the location (or an open holder in the room) and
        adds it to the character's inventory or, if their hands are full, a
        carried container with space.
        """
        if self.source_holder is not None:
            self.source_holder.remove_item(self.item)
        self.character.accept_item(self.item)
        description = "{character_name} got the {item_name}.".format(
            character_name=self.character.name, item_name=self.item.name
        )
        self.parser.ok(description)


class Drop(base.Action):
    ACTION_NAME = ActionName.DROP
    ACTION_DESCRIPTION = "Drop something from the character's inventory"
    ACTION_ALIASES = ["toss", "get rid of"]

    def __init__(
        self,
        game,
        command: str,
        actor=None,
    ):
        super().__init__(game, actor=actor)
        self.character = self.acting_character(command, hint="wants to drop something")
        self.location = self.character.location
        self.item = self.parser.match_item(
            command, self.character.carried_items(), hint="thing being dropped"
        )

    def check_preconditions(self) -> bool:
        """
        Preconditions:
        * The item must be carried by the character (in hand or in a
          container), and not worn or wielded.
        """
        if not self.was_matched(self.item, "I don't see it."):
            return False
        if self.character.is_worn(self.item):
            self.parser.fail(
                f"{self.character.name.capitalize()} is wearing the "
                f"{self.item.name}. Take it off first."
            )
            return False
        if self.character.is_wielded(self.item):
            self.parser.fail(
                f"{self.character.name.capitalize()} is wielding the "
                f"{self.item.name}. Stow it first."
            )
            return False
        if self.item.name not in self.character.carried_items():
            self.parser.fail("You aren't carrying that.")
            return False
        return True

    def apply_effects(self):
        """
        Drop removes an item from wherever the character holds it (hand or a
        carried container) and adds it to the current location.
        """
        self.character.discard_item(self.item)
        self.item.location = self.location
        self.location.add_item(self.item)
        d = "{character_name} dropped the {item_name} in the {location}."
        description = d.format(
            character_name=self.character.name.capitalize(),
            item_name=self.item.name,
            location=self.location.name,
        )
        self.parser.ok(description)


class Inventory(base.Action):
    ACTION_NAME = ActionName.INVENTORY
    ACTION_DESCRIPTION = "Check the character's inventory"
    ACTION_ALIASES = ["i"]
    DURATION = 1  # a quick glance in one's pockets (issue #24)

    def __init__(
        self,
        game,
        command: str,
        actor=None,
    ):
        super().__init__(game, actor=actor)
        self.character = self.acting_character(command)

    def check_preconditions(self) -> bool:
        if not self.was_matched(self.character, "No character was matched."):
            return False
        return True

    def apply_effects(self):
        if len(self.character.inventory) == 0:
            description = f"{self.character.name}'s inventory is empty."
            self.parser.ok(description)
        else:
            description = f"{self.character.name}'s inventory contains:\n"
            for item_name in self.character.inventory:
                item = self.character.inventory[item_name]
                if item.get_property("is_container"):
                    if item.capacity is None:
                        gauge = "({count})".format(count=item.current_count())
                    else:
                        gauge = "({count}/{cap})".format(
                            count=item.current_count(), cap=item.capacity
                        )
                    description += "* {item} {gauge}\n".format(
                        item=item.description, gauge=gauge
                    )
                    for inner_name in item.contents:
                        inner = item.contents[inner_name]
                        description += "    - {item}\n".format(item=inner.description)
                else:
                    description += "* {item}\n".format(item=item.description)
            self.parser.ok(description)


class Examine(base.Action):
    ACTION_NAME = ActionName.EXAMINE
    ACTION_DESCRIPTION = "Examine an item"
    ACTION_ALIASES = ["look at", "x"]
    DURATION = 1  # a quick look (issue #24)

    def __init__(
        self,
        game,
        command: str,
        actor=None,
    ):
        super().__init__(game, actor=actor)
        self.character = self.acting_character(command, hint="looker")
        self.matched_item = self.parser.match_item(
            command,
            self.parser.get_items_in_scope(self.character),
            hint="thing being looked at",
        )
        # EXAMINE also works on people. If no item matched, look for a character
        # in the room whose name appears in the command, so "examine <npc>"
        # describes them instead of falling through to "nothing special".
        self.matched_character = (
            None
            if self.matched_item
            else self.character_in_room(command, self.character)
        )

    def check_preconditions(self) -> bool:
        if not self.was_matched(self.character, "No character was matched."):
            return False
        return True

    @staticmethod
    def _contents_sentence(item):
        """For an OPEN, non-empty holder, a sentence listing what's inside (a
        container) or what rests on it (a surface) -- so 'examine boat' reads
        '... It contains a warm wool blanket.' and 'examine table' reads
        '... On it you see a candle.'."""
        contents = item.accessible_contents()
        if not contents:
            return ""
        descs = [c.description for c in contents.values()]
        if len(descs) == 1:
            listed = descs[0]
        elif len(descs) == 2:
            listed = f"{descs[0]} and {descs[1]}"
        else:
            listed = ", ".join(descs[:-1]) + f", and {descs[-1]}"
        if item.get_property("is_surface"):
            return f" On it you see {listed}."
        return f" It contains {listed}."

    def apply_effects(self):
        """The player wants to examine an item or a character."""
        if self.matched_item:
            base_text = self.matched_item.examine_text or self.matched_item.description
            self.parser.ok(base_text + self._contents_sentence(self.matched_item))
        elif self.matched_character is not None:
            other = self.matched_character
            # Characters may carry an optional richer ``examine_text``; otherwise
            # fall back to their one-line description.
            self.parser.ok(
                getattr(other, "examine_text", "")
                or other.description
                or f"It's {other.name}."
            )
        else:
            self.parser.ok("You don't see anything special.")


class Give(base.Action):
    ACTION_NAME = ActionName.GIVE
    ACTION_DESCRIPTION = "Give something to someone"
    ACTION_ALIASES = ["hand"]

    def __init__(self, game, command: str, actor=None):
        super().__init__(game, actor=actor)
        give_words = ["give", "hand"]
        self.giver = self.acting_character(
            command, hint="giver", split_words=give_words, position="before"
        )
        self.recipient = self.target_character(
            command,
            hint="recipient",
            split_words=give_words,
            position="after",
            exclude=self.giver,
        )
        giver_held = {
            **self.giver.carried_items(),
            **self.giver.worn,
            **self.giver.wielded,
        }
        self.item = self.parser.match_item(command, giver_held, hint="item being given")

    def claimed_resource(self):
        """Two characters giving to the same recipient contend for them (#42)."""
        return self.recipient

    def check_preconditions(self) -> bool:
        """
        Preconditions:
        * The item must be carried by the giver (in hand or a container),
          and not worn or wielded.
        * The giver must be at the same location as the recipient
        * The recipient must have room to receive the item
        """
        if not self.was_matched(self.item, "I don't see it."):
            return False
        if self.giver.is_worn(self.item):
            self.parser.fail(
                f"{self.giver.name.capitalize()} is wearing the "
                f"{self.item.name}. Take it off first."
            )
            return False
        if self.giver.is_wielded(self.item):
            self.parser.fail(
                f"{self.giver.name.capitalize()} is wielding the "
                f"{self.item.name}. Stow it first."
            )
            return False
        if self.item.name not in self.giver.carried_items():
            self.parser.fail("You aren't carrying that.")
            return False
        if not self.was_matched(self.recipient, "Give it to whom?"):
            return False
        if not self.at(self.recipient, self.giver.location):
            return False
        if not self.recipient.can_accept_item():
            self.parser.fail(
                "{recipient} has no room to carry the {item}.".format(
                    recipient=self.recipient.name.capitalize(), item=self.item.name
                )
            )
            return False
        return True

    def apply_effects(self):
        """The giver hands the item to the recipient.

        The item is removed from wherever the giver holds it (hand or a carried
        container) and placed on the recipient via hands-first routing, with
        overflow into a carried container if the recipient's hands are full.

        If the recipient is hungry and the item is food, they will eat it.
        If the recipient is thirsty and the item is drink, they will drink it.
        """
        self.giver.discard_item(self.item)
        self.recipient.accept_item(self.item)
        description = "{giver} gave the {item_name} to {recipient}".format(
            giver=self.giver.name.capitalize(),
            item_name=self.item.name,
            recipient=self.recipient.name.capitalize(),
        )
        self.parser.ok(description)

        if self.recipient.get_property(Property.IS_HUNGRY) and self.item.get_property(
            Property.EDIBLE
        ):
            command = "{name} eat {food}".format(
                name=self.recipient.name, food=self.item.name
            )
            eat = Eat(self.game, command)
            eat()

        if self.recipient.get_property(Property.IS_THIRSTY) and self.item.get_property(
            Property.DRINKABLE
        ):
            command = "{name} drink {drink}".format(
                name=self.recipient.name, drink=self.item.name
            )
            drink = Drink(self.game, command)
            drink()

        if self.item.get_property(Property.SCENT):
            command = "{name} smell {thing}".format(
                name=self.recipient.name, thing=self.item.name
            )
            smell = Smell_Rose(self.game, command)
            smell()


class Put(base.Action):
    """Put a held item into a container or onto a surface.

    Grammar: ``put <item> in <container>`` / ``put <item> on <surface>``. The
    relation must match the holder (you can't put things *in* a table), and a
    container must be open and have room.
    """

    ACTION_NAME = ActionName.PUT
    ACTION_DESCRIPTION = "Put something into a container or onto a surface"
    ACTION_ALIASES = ["place", "set"]

    def __init__(self, game, command: str, actor=None):
        super().__init__(game, actor=actor)
        self.character = self.acting_character(command, hint="wants to put something")
        cmd = command.lower()
        self.relation = None
        item_phrase = holder_phrase = ""
        # split on the first " in "/" on " into (item) <rel> (holder)
        for rel, kw in (("in", " in "), ("on", " on ")):
            if kw in cmd:
                self.relation = rel
                left, _, right = cmd.partition(kw)
                for verb in ("put", "place", "set"):  # drop the leading verb
                    if verb in left:
                        left = left.split(verb, 1)[1]
                        break
                item_phrase, holder_phrase = left.strip(), right.strip()
                break
        self.item = (
            self.parser.match_item(
                item_phrase, self.character.carried_items(), hint="thing to put"
            )
            if item_phrase
            else None
        )
        scope = {**self.character.location.items, **self.character.inventory}
        self.holder = (
            self.parser.match_item(holder_phrase, scope, hint="where to put it")
            if holder_phrase
            else None
        )

    def check_preconditions(self) -> bool:
        if self.relation is None:
            self.parser.fail('Put it where? Try "put X in Y" or "put X on Y".')
            return False
        if not self.was_matched(self.item, "You aren't holding that."):
            return False
        if not self.was_matched(self.holder, "You don't see that here."):
            return False
        if self.holder is self.item or not self.holder.is_holder():
            self.parser.fail(
                f"You can't put things {self.relation} the {self.holder.name}."
            )
            return False
        if self.relation != self.holder.preposition():
            self.parser.fail(
                f"You can't put things {self.relation} the {self.holder.name}."
            )
            return False
        if not self.holder.is_open():
            self.parser.fail(f"The {self.holder.name} is closed.")
            return False
        if not self.holder.has_space():
            self.parser.fail(f"The {self.holder.name} is full.")
            return False
        return True

    def apply_effects(self):
        self.character.discard_item(self.item)
        self.holder.add_item(self.item)
        self.parser.ok(
            f"{self.character.name.capitalize()} puts the {self.item.name} "
            f"{self.holder.preposition()} the {self.holder.name}."
        )


class Open(base.Action):
    ACTION_NAME = ActionName.OPEN
    ACTION_DESCRIPTION = "Open a container"

    def __init__(self, game, command: str, actor=None):
        super().__init__(game, actor=actor)
        self.character = self.acting_character(command, hint="wants to open something")
        scope = {**self.character.location.items, **self.character.inventory}
        self.item = self.parser.match_item(command, scope, hint="thing to open")

    def check_preconditions(self) -> bool:
        if not self.was_matched(self.item, "I don't see it."):
            return False
        if not self.item.get_property("is_container"):
            self.parser.fail(f"You can't open the {self.item.name}.")
            return False
        if not self.item.get_property("is_closed"):
            self.parser.fail(f"The {self.item.name} is already open.")
            return False
        return True

    def apply_effects(self):
        self.item.set_property("is_closed", False)
        self.parser.ok(
            f"{self.character.name.capitalize()} opens the {self.item.name}."
        )


class Close(base.Action):
    ACTION_NAME = ActionName.CLOSE
    ACTION_DESCRIPTION = "Close a container"
    ACTION_ALIASES = ["shut"]

    def __init__(self, game, command: str, actor=None):
        super().__init__(game, actor=actor)
        self.character = self.acting_character(command, hint="wants to close something")
        scope = {**self.character.location.items, **self.character.inventory}
        self.item = self.parser.match_item(command, scope, hint="thing to close")

    def check_preconditions(self) -> bool:
        if not self.was_matched(self.item, "I don't see it."):
            return False
        if not self.item.get_property("is_container"):
            self.parser.fail(f"You can't close the {self.item.name}.")
            return False
        if self.item.get_property("is_closed"):
            self.parser.fail(f"The {self.item.name} is already closed.")
            return False
        return True

    def apply_effects(self):
        self.item.set_property("is_closed", True)
        self.parser.ok(
            f"{self.character.name.capitalize()} closes the {self.item.name}."
        )


class Unlock_Door(base.Action):
    ACTION_NAME = ActionName.UNLOCK_DOOR
    ACTION_DESCRIPTION = "Unlock a door"

    def __init__(self, game, command, actor=None):
        super().__init__(game, actor=actor)
        self.command = command
        self.character = self.acting_character(command)
        self.key = self.parser.match_item(
            "key", self.parser.get_items_in_scope(self.character), hint="key"
        )
        self.door = self.parser.match_item(
            "door", self.parser.get_items_in_scope(self.character), hint="door"
        )

    def check_preconditions(self) -> bool:
        if not self.was_matched(self.door, "There's no door here."):
            return False
        if not self.was_matched(self.key, "There's no key here."):
            return False
        if self.has_property(
            self.door, Property.IS_LOCKED, error_message="The door is not locked."
        ):
            return False
        return True

    def apply_effects(self):
        self.door.set_property(Property.IS_LOCKED, False)
        self.parser.ok("Door is unlocked")
