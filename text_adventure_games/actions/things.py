from . import base
from .consume import Drink, Eat
from .rose import Smell_Rose
from ..enums import ActionName, Property


def _qty_suffix(item) -> str:
    """' (xN)' for a stack of more than one (#134), else ''."""
    qty = getattr(item, "quantity", 1)
    return f" (x{qty})" if qty > 1 else ""


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
        # Hidden items can't be grabbed until a SEARCH reveals them.
        scope = {
            name: it
            for name, it in self.location.items.items()
            if not it.get_property("is_hidden")
        }
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
            # was_matched already reported the failure; don't double-report it.
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
        # Vaarn item slots (slots.py; only when the character opted in): past
        # the hard maximum you simply cannot take more.
        if not self.character.has_slot_space(self.item):
            self.parser.fail(
                "You cannot carry another thing -- something must be dropped, "
                "or left."
            )
            return False
        return True

    def apply_effects(self):
        """
        Get's an item from the location (or an open holder in the room) and
        adds it to the character's inventory or, if their hands are full, a
        carried container with space.
        """
        was_encumbered = self.character.is_encumbered()
        if self.source_holder is not None:
            self.source_holder.remove_item(self.item)
        self.character.accept_item(self.item)
        description = "{character_name} got the {item_name}.".format(
            character_name=self.character.name, item_name=self.item.name
        )
        # Warn once at the encumbered transition (slots.py): loaded past
        # comfort, you move loudly and cannot climb.
        if self.character.is_encumbered() and not was_encumbered:
            description += (
                " Your pack is full to the last slot: you move with a clatter "
                "now, and climbing is out of the question."
            )
        # Taking a thing with a card draws it (CCB): the acquisition is the
        # moment. Deduped -- a card already met (an ambush, an examine)
        # doesn't replay just for the pocketing; EXAMINE re-earns it.
        if self.character is self.game.player:
            fig = self.item.get_property("figure")
            self.game.show_figure(fig(self.game) if callable(fig) else fig)
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


class Break(base.Action):
    """Break an item that can be broken.

    A breakable item -- one flagged ``is_breakable``, or a fragile one like a
    glass bottle -- shatters when broken: it is removed from play, and anything
    it was holding spills out into the room first (so a smashed box leaves its
    contents behind rather than vanishing them).

    An item flagged ``break_keep`` is instead snapped free and KEPT rather than
    destroyed. This is Action Castle's dead branch: you BREAK it off the tall
    tree to carry away as a club (the canonical AC1 verb -- the source lets the
    player "EXAMINE, BREAK or TAKE the dead branch"). Anything not breakable
    refuses politely.

    Per-item narration can be set with a ``break_text`` property."""

    ACTION_NAME = "break"
    ACTION_DESCRIPTION = "Break something"
    ACTION_ALIASES = ["smash"]

    # A crash carries two rooms (issue #80 hearing): loud enough to set off a
    # startle reaction well beyond the room it happens in.
    AUDIBLE_RADIUS = 2

    def sound_description(self) -> str:
        return "the crash of something breaking"

    def __init__(self, game, command: str, actor=None):
        super().__init__(game, actor=actor)
        self.character = self.acting_character(command, hint="wants to break something")
        self.location = self.character.location
        scope = self.parser.get_items_in_scope(self.character)
        self.item = self.parser.match_item(command, scope, hint="thing to break")

    def claimed_resource(self):
        """Two characters reaching to break the same thing contend over it (#42)."""
        return self.item

    def check_preconditions(self) -> bool:
        """
        Preconditions:
        * The item must be matched (and so in scope).
        * The item must be breakable -- flagged ``is_breakable`` or fragile.
        """
        if not self.was_matched(self.item, "I don't see anything like that to break."):
            return False
        breakable = self.item.get_property("is_breakable") or self.item.get_property(
            Property.IS_FRAGILE
        )
        if not breakable:
            self.parser.fail(f"You can't break the {self.item.name}.")
            return False
        return True

    def apply_effects(self):
        item = self.item
        if item.get_property("break_keep"):
            # Snap it free and keep it (e.g. the dead branch off the tree). Take
            # it out of the room if that's where it sits, then add it to hand.
            if item.location is not None and item.name in item.location.items:
                item.location.remove_item(item)
                item.location = None
            if not self.character.is_in_inventory(item):
                self.character.add_to_inventory(item)
            message = item.get_property("break_text") or (
                f"You break {item.description} free and take it."
            )
            return self.parser.ok(message)

        # Otherwise the item shatters. Spill anything inside it into the room,
        # then remove the item from wherever it lived.
        for inner in list(getattr(item, "contents", {}).values()):
            item.remove_item(inner)
            inner.location = self.location
            self.location.add_item(inner)
        self._remove_from_world(item)
        message = (
            item.get_property("break_text") or f"The {item.name} breaks into pieces."
        )
        self.parser.ok(message)

    def _remove_from_world(self, item):
        """Take a broken item out of wherever it lives -- a character's hands or
        a carried container, a holder in the room, or the room floor."""
        if item.name in self.character.carried_items():
            self.character.discard_item(item)
        elif item.container is not None:
            item.container.remove_item(item)
        elif item.location is not None and item.name in item.location.items:
            item.location.remove_item(item)
            item.location = None


class Inventory(base.Action):
    ACTION_NAME = ActionName.INVENTORY
    ACTION_DESCRIPTION = "Check the character's inventory"
    ACTION_ALIASES = ["i"]
    DURATION = 1  # a quick glance in one's pockets (issue #24)
    # The list is for the player, not the character: free by default (see
    # config.engine.meta_actions_cost_turns).
    FREE_ACTION = True

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
        char = self.character
        # "Your inventory" for the player (named "you"); possessive for NPCs.
        whose = "Your" if char.name.lower() == "you" else f"{char.name}'s"

        def _slot_suffix(item):
            """ "(2 slots)" on multi-slot gear -- only when this character uses
            the slot gauge, and only past the default cost of 1."""
            if char.slot_capacity is None:
                return ""
            from ..slots import item_slot_cost

            cost = item_slot_cost(item)
            return f" ({cost} slots)" if cost > 1 else ""

        # Nothing carried, worn, wielded -- or suffered -- a single empty line.
        if (
            not char.inventory
            and not char.worn
            and not char.wielded
            and not char.wounds
        ):
            self.parser.ok(f"{whose} inventory is empty.")
            return

        # Three sections in order: what's carried, then worn, then wielded.
        # Only non-empty sections are shown (but "carried" always appears, as
        # "empty", when something is worn/wielded but nothing is in hand).
        sections = []
        if char.inventory:
            carried = f"{whose} inventory contains:\n"
            for item_name in char.inventory:
                item = char.inventory[item_name]
                if item.get_property("is_container"):
                    if item.capacity is None:
                        gauge = "({count})".format(count=item.current_count())
                    else:
                        gauge = "({count}/{cap})".format(
                            count=item.current_count(), cap=item.capacity
                        )
                    carried += "* {item}{slots} {gauge}\n".format(
                        item=item.description, slots=_slot_suffix(item), gauge=gauge
                    )
                    for inner_name in item.contents:
                        inner = item.contents[inner_name]
                        carried += "    - {item}{qty}\n".format(
                            item=inner.description, qty=_qty_suffix(inner)
                        )
                else:
                    carried += "* {item}{qty}{slots}\n".format(
                        item=item.description,
                        qty=_qty_suffix(item),
                        slots=_slot_suffix(item),
                    )
            sections.append(carried.rstrip("\n"))
        else:
            sections.append(f"{whose} inventory is empty.")

        def _listing(title, slot):
            body = "".join(
                "* {item}{qty}{slots}\n".format(
                    item=it.description, qty=_qty_suffix(it), slots=_slot_suffix(it)
                )
                for it in slot.values()
            )
            return f"{title}\n{body}".rstrip("\n")

        if char.worn:
            sections.append(_listing("Wearing:", char.worn))
        if char.wielded:
            sections.append(_listing("Wielding:", char.wielded))

        # Vaarn item slots (slots.py): wounds fill the same gauge as gear; the
        # slots line appears only for characters that opted in.
        if char.wounds:
            wounds = "Wounds:\n" + "".join(
                "* {name}{slots} - {desc}\n".format(
                    name=w.name,
                    slots=(
                        f" ({w.slots} slot{'s' if w.slots != 1 else ''})"
                        if w.slots
                        else ""
                    ),
                    desc=w.description,
                )
                for w in char.wounds
            )
            sections.append(wounds.rstrip("\n"))
        if char.slot_capacity is not None:
            gauge = f"Slots: {char.slots_used()}/{char.slot_capacity}"
            if char.get_property(Property.IS_DEAD):
                # The post-mortem ledger (CCB): a corpse is past encumbrance;
                # the gauge simply shows what filled it.
                gauge += " -- the wounds took the last of you"
            elif char.is_encumbered():
                gauge += " -- ENCUMBERED (you clatter when you move, and cannot climb)"
            sections.append(gauge)

        self.parser.ok("\n\n".join(sections))


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
        '... On it you see a candle.'.

        A holder may set ``contents_relation`` -- the full intro phrase -- to
        voice the listing naturally ("Under the stained mattress you see ...",
        "Behind the curtain hangs ..."), overriding the generic defaults.
        Because it's driven by the live contents, it's self-updating: take the
        last item and the sentence disappears (no stale text)."""
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
        relation = item.get_property("contents_relation")
        if relation:
            return f" {relation} {listed}."
        if item.get_property("is_surface"):
            return f" On it you see {listed}."
        return f" It contains {listed}."

    def _too_dark(self, target) -> None:
        """Examining something you can't see: fall back to the *passive* senses
        (hearing, smell) it offers; touch needs the active `feel` probe, so if
        it's only touch-perceptible, nudge toward feeling around."""
        from .. import perception

        parts = [
            t
            for s in (perception.Sense.HEARING, perception.Sense.SMELL)
            if (t := target.sense_text(s))
        ]
        if parts:
            self.parser.ok(" ".join(parts))
            return
        # Diegetic nudge, not a stage direction: if the thing can be felt, say
        # so through the fiction rather than a parenthetical instruction.
        hint = (
            " Your hands might do what your eyes cannot."
            if target.sense_text(perception.Sense.TOUCH)
            else ""
        )
        self.parser.ok("It's too dark to make anything out." + hint)

    def _dark_figure(self, target) -> None:
        """A dark examine deals only CALLABLE figures: the callable owns
        light-awareness (it can return a dark-appropriate card, or None),
        while a plain string figure -- always the lit litho -- stays
        suppressed so darkness never leaks what the eyes haven't earned."""
        if self.character is not self.game.player:
            return
        fig = target.get_property("figure")
        if callable(fig):
            self.game.show_figure(fig(self.game), force=True)

    def apply_effects(self):
        """The player wants to examine an item or a character."""
        # Perception gate: in pitch dark (or blind) you can't *see* to examine --
        # fall back to what other senses reach (perception.py, Layer 2). DIM/CLEAR
        # keep the normal visual examine, so lit games are unchanged.
        from .. import perception

        target = self.matched_item or self.matched_character
        if target is not None:
            sight, _ = perception.sight_for(self.character, self.character.location)
            if sight == perception.Sight.NONE:
                self._too_dark(target)
                self._dark_figure(target)
                return

        if self.matched_item:
            # A holder may opt in to ``reveals_on_examine``: a close look also
            # uncovers its hidden contents (a corpse's clasped hands, a niche) --
            # so EXAMINE and SEARCH both yield the find. Secret compartments
            # that should need a deliberate SEARCH simply don't set it.
            if self.matched_item.get_property("reveals_on_examine"):
                for inner in self.matched_item.contents.values():
                    if inner.get_property("is_hidden"):
                        inner.set_property("is_hidden", False)
            base_text = self.matched_item.examine_text or self.matched_item.description
            # Like talk_text, an examine_text may be a callable(game) -> str,
            # computed at look time -- for things whose close-up changes (a
            # memory lattice showing a different facet each look, a gauge).
            if callable(base_text):
                base_text = base_text(self.game)
            text = base_text + self._contents_sentence(self.matched_item)
            # A mirror reflects whoever looks into it -- compose the examiner's
            # live appearance (+ what they're wearing) rather than canned text
            # that goes stale (e.g. after a haircut). See Character.reflection.
            if self.matched_item.get_property("is_mirror"):
                text += " " + self.character.reflection(
                    include_room=bool(
                        self.matched_item.get_property("mirror_reflects_room")
                    )
                )
            self.parser.ok(text)
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
            return
        # A thing may carry a ``figure`` property: the key of an illustration
        # card that a close look cues. FORCED (CCB): an explicit examine
        # always re-earns the card, like LOOK does for rooms -- take/arrival/
        # ambush cues stay once-per-game. A callable(game) -> key|None picks
        # by live state (an autarch at rest draws differently than one
        # hollowed out). Player looks only: an NPC examining doesn't draw on
        # the player's screen.
        if self.character is self.game.player:
            fig = target.get_property("figure")
            self.game.show_figure(fig(self.game) if callable(fig) else fig, force=True)


class Throw(base.Action):
    """Throw a carried item in a direction: it leaves your hands and lands in
    the connected room, clattering -- a real sound, emitted where it LANDS.
    The classic noisemaker: anything that hunts by sound will go and see.

    Blocks don't stop a thrown object (they gate travel, not flight through an
    archway), but the exit must exist. A fragile item shatters where it lands.
    """

    ACTION_NAME = "throw"
    ACTION_DESCRIPTION = "Throw something in a direction, or at someone"
    ACTION_ALIASES = ["hurl", "lob"]

    def __init__(self, game, command: str, actor=None):
        super().__init__(game, actor=actor)
        self.character = self.acting_character(command, hint="thrower")
        self.location = self.character.location
        # "throw X at Y" targets a character (who catches it); otherwise a
        # direction ("throw X north") sends it into the next room.
        self.target = (
            self.character_in_room(command, self.character)
            if " at " in command.lower()
            else None
        )
        # A throw names its direction at the END ("throw purse north", "hurl
        # rock right stairs"): try the trailing two words, then one, as an
        # exact direction/exit name.
        self.direction = None
        if self.target is None:
            words = command.lower().strip().split()
            for take in (2, 1):
                if len(words) >= take:
                    cand = " ".join(words[-take:])
                    self.direction = self.parser.get_direction(cand, self.location)
                    if self.direction:
                        break
        self.item = self.parser.match_item(
            command, self.character.carried_items(), hint="thing to throw"
        )

    def check_preconditions(self) -> bool:
        if not self.was_matched(self.item, "I don't see it."):
            return False
        if self.character.is_worn(self.item) or self.character.is_wielded(self.item):
            self.parser.fail(f"The {self.item.name} is in use. Stow it first.")
            return False
        if self.target is not None:
            return True
        if self.direction is None:
            self.parser.fail("Throw it which way -- or at whom?")
            return False
        if not self.location or not self.location.get_connection(self.direction):
            self.parser.fail("There's nothing that way to throw at.")
            return False
        return True

    def apply_effects(self):
        self.character.discard_item(self.item)
        if self.target is not None:
            # A no_catch target (no hands: a coil, a swarm) deflects the throw
            # into the room instead -- what the impact DOES is a game trigger's
            # business (a splash, a splatter, a bounce).
            if self.target.get_property("no_catch"):
                if self.location is not None:
                    self.location.add_item(self.item)
                self.parser.ok(
                    f"You throw the {self.item.name} at {self.target.name}; "
                    "it strikes, and drifts free."
                )
                return
            # A catch: the item changes hands. What the catcher DOES with it
            # is theirs to decide (a game trigger: eat it, keep it, drop it).
            self.target.add_to_inventory(self.item)
            self.parser.ok(
                f"You throw the {self.item.name} at {self.target.name} -- "
                f"and {self.target.name} catches it."
            )
            return
        dest = self.location.connections[self.direction]
        if self.item.get_property(Property.IS_FRAGILE):
            description = (
                f"You throw the {self.item.name} {self.direction}; a beat "
                f"later, the sound of it shattering in {dest.name}."
            )
            sound = f"the shatter of a thrown {self.item.name}"
        else:
            dest.add_item(self.item)
            description = (
                f"You throw the {self.item.name} {self.direction}; a beat "
                f"later, a clatter from {dest.name}."
            )
            sound = f"the clatter of a thrown {self.item.name}"
        self.parser.ok(description)
        # The noise happens where it LANDS -- the tactical point.
        self.game.emit_sound(dest, 1, sound)


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
        # An unmatched recipient falls back to the player (parser default),
        # which for a player-issued give means giving to yourself. Refuse and
        # ask instead of narrating "You gave the X to You."
        if self.recipient is self.giver:
            self.parser.fail("Give it to whom?")
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
        description = "{giver} gave the {item_name} to {recipient}.".format(
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
            self.parser.fail(f"The {self.holder.name} {self.holder.to_be()} closed.")
            return False
        if not self.holder.has_space():
            self.parser.fail(f"The {self.holder.name} {self.holder.to_be()} full.")
            return False
        return True

    def apply_effects(self):
        self.character.discard_item(self.item)
        self.holder.add_item(self.item)
        verb = base.conjugate(self.character, "put", "puts")
        self.parser.ok(
            f"{self.character.name.capitalize()} {verb} the {self.item.name} "
            f"{self.holder.preposition()} the {self.holder.name}."
        )


class Open(base.Action):
    ACTION_NAME = ActionName.OPEN
    ACTION_DESCRIPTION = "Open a container"

    def __init__(self, game, command: str, actor=None):
        super().__init__(game, actor=actor)
        self.character = self.acting_character(command, hint="wants to open something")
        # Full parser scope, not just the room's top level: a jar standing
        # on a plinth (or a box in a carried bag) can be opened where it sits.
        scope = self.parser.get_items_in_scope(self.character)
        self.item = self.parser.match_item(command, scope, hint="thing to open")

    def check_preconditions(self) -> bool:
        if not self.was_matched(self.item, "I don't see it."):
            return False
        if not self.item.get_property("is_container"):
            self.parser.fail(f"You can't open the {self.item.name}.")
            return False
        if not self.item.get_property("is_closed"):
            self.parser.fail(f"The {self.item.name} {self.item.to_be()} already open.")
            return False
        return True

    def apply_effects(self):
        self.item.set_property("is_closed", False)
        # Item-subject phrasing reads right for any actor -- "You opens the
        # pack" (player named "you") was ungrammatical. Same fix as Light/Douse.
        message = f"The {self.item.name} {self.item.to_be()} open."
        # Reveal what's inside so the player learns what they can take, rather
        # than having to guess (the contents are now reachable by GET).
        contents = [
            inner
            for inner in self.item.contents.values()
            if not inner.get_property("is_hidden")
        ]
        if contents:
            prep = self.item.preposition()
            listed = ", ".join(inner.description for inner in contents)
            message += f" {prep.capitalize()} it you see: {listed}."
        self.parser.ok(message)


class Close(base.Action):
    ACTION_NAME = ActionName.CLOSE
    ACTION_DESCRIPTION = "Close a container"
    ACTION_ALIASES = ["shut"]

    def __init__(self, game, command: str, actor=None):
        super().__init__(game, actor=actor)
        self.character = self.acting_character(command, hint="wants to close something")
        scope = self.parser.get_items_in_scope(self.character)
        self.item = self.parser.match_item(command, scope, hint="thing to close")

    def check_preconditions(self) -> bool:
        if not self.was_matched(self.item, "I don't see it."):
            return False
        if not self.item.get_property("is_container"):
            self.parser.fail(f"You can't close the {self.item.name}.")
            return False
        if self.item.get_property("is_closed"):
            self.parser.fail(
                f"The {self.item.name} {self.item.to_be()} already closed."
            )
            return False
        return True

    def apply_effects(self):
        self.item.set_property("is_closed", True)
        # Item-subject phrasing, matching Open (and Light/Douse).
        self.parser.ok(f"The {self.item.name} {self.item.to_be()} closed.")


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


# Crafting verbs the parser routes to Craft (see Parser.determine_intent). The
# canonical name is "craft"; the rest are recognized phrasings.
CRAFT_VERBS = (
    "craft",
    "make",
    "cook",
    "brew",
    "forge",
    "mix",
    "combine",
    "assemble",
    "build",
    "braid",
)


class Craft(base.Action):
    """Combine ingredients into a new item per a registered recipe (crafting.py).

    Resolves a recipe three ways, friendliest first: by the output's name
    ("make stew"), by the named ingredients ("combine string and stick"), or --
    for a bare verb at a station ("cook") -- the first recipe whose ingredients,
    tools and location are all satisfied right now. Inputs are consumed from the
    crafter's held items; tools (a pot, a forge, a hammer) must be present but
    are not consumed; the output lands in hand (or an open carried container)."""

    ACTION_NAME = ActionName.CRAFT
    ACTION_DESCRIPTION = "Combine ingredients into something new"

    def __init__(self, game, command, actor=None):
        super().__init__(game, actor=actor)
        self.command = command.lower().strip()
        self.character = self.acting_character(command, hint="crafter")
        self.target = self._strip_verb(self.command)
        self.recipe = None
        self.named = False  # did the player name a recipe/ingredients?
        self._resolve()

    # -- resolution ----------------------------------------------------------

    def _strip_verb(self, command: str) -> str:
        first, _, rest = command.partition(" ")
        target = rest if first in CRAFT_VERBS else command
        for lead in ("a ", "an ", "the ", "some "):
            if target.startswith(lead):
                target = target[len(lead) :]
        return target.strip()

    def _recipes(self):
        """The recipes the crafter may currently use: those known from the start,
        plus any learned via ``Game.learn_recipe()`` (issue #135). Gating here
        covers all three resolution paths, and an unknown recipe falls through to
        the "you don't know how to make that" message, not the ingredient gap."""
        return [
            r for r in (getattr(self.game, "recipes", []) or []) if self._is_known(r)
        ]

    def _is_known(self, recipe) -> bool:
        if getattr(recipe, "known", True):
            return True
        learned = getattr(self.game, "learned_recipes", None) or set()
        return any(name in learned for name in recipe.names())

    def _held(self):
        """name -> item across the crafter's hands and open carried containers."""
        return self.character.carried_items()

    def _present(self):
        """Items the crafter could use as a tool: held + lying in the room."""
        scope = dict(self._held())
        loc = self.character.location
        if loc is not None:
            for name, item in loc.items.items():
                scope.setdefault(name, item)
        return scope

    def _available(self, ingredient, pool) -> int:
        """How many matching units *pool* (a name->item dict) holds -- summing
        item quantities, so a stack of 2 sticks counts as 2 (#134)."""
        return sum(
            getattr(it, "quantity", 1) for it in pool.values() if ingredient.matches(it)
        )

    def _consume(self, ingredient):
        """Remove ingredient.count matching units from the crafter's held items,
        decrementing stacks and discarding any that hit zero."""
        need = ingredient.count
        for it in list(self.character.carried_items().values()):
            if need <= 0:
                break
            if not ingredient.matches(it):
                continue
            qty = getattr(it, "quantity", 1)
            take = min(qty, need)
            it.quantity = qty - take
            need -= take
            if it.quantity <= 0:
                self.character.discard_item(it)

    def _satisfiable(self, recipe) -> bool:
        ok, _ = self._check(recipe)
        return ok

    def _check(self, recipe):
        """(ok, gap_message) for whether *recipe* can be made right now."""
        if recipe.location and (
            self.character.location is None
            or self.character.location.name != recipe.location
        ):
            return False, "You can't make that here."
        present = self._present()
        for tool in recipe.tools:
            if self._available(tool, present) < tool.count:
                return False, f"You need {tool.label()} to make that."
        held = self._held()
        for ing in recipe.inputs:
            if self._available(ing, held) < ing.count:
                return False, f"You need {ing.label()} to make that."
        if not self.character.can_accept_item():
            return False, "Your hands are full to make anything."
        return True, None

    def _resolve(self):
        recipes = self._recipes()
        if not recipes:
            return
        # 1) by output name / alias appearing in the target (longest wins).
        if self.target:
            best, best_len = None, -1
            for r in recipes:
                for n in r.names():
                    if n and n in self.target and len(n) > best_len:
                        best, best_len = r, len(n)
            if best is not None:
                self.recipe, self.named = best, True
                return
        # 2) by named ingredients: every input named in the target, and the
        #    target mentions nothing extra a smaller recipe wouldn't.
        if self.target:
            tokens = self.target
            for r in sorted(recipes, key=lambda r: len(r.inputs), reverse=True):
                if r.inputs and all(
                    (ing.name and ing.name in tokens) for ing in r.inputs
                ):
                    self.recipe, self.named = r, True
                    return
        # 3) bare verb: the first recipe satisfiable right here.
        for r in recipes:
            if self._satisfiable(r):
                self.recipe = r
                return

    # -- action --------------------------------------------------------------

    def check_preconditions(self) -> bool:
        if self.recipe is None:
            if self.target:
                self.parser.fail(f"You don't know how to make '{self.target}'.")
            else:
                self.parser.fail("There's nothing you can make here right now.")
            return False
        ok, gap = self._check(self.recipe)
        if not ok:
            self.parser.fail(gap)
            return False
        return True

    def apply_effects(self):
        recipe = self.recipe
        # Consume inputs from the crafter's held items (quantity-aware).
        for ing in recipe.inputs:
            self._consume(ing)
        # Produce the output(s).
        produced = recipe.output(self.game)
        outputs = produced if isinstance(produced, (list, tuple)) else [produced]
        names = []
        for item in outputs:
            self.character.accept_item(item)
            names.append(item.name)
        msg = recipe.result_text or "You make {}.".format(", ".join(names))
        self.parser.ok(msg)
        self.game.log_event(self.character.name, "craft", recipe.name or names[0])
