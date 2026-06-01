from . import base
from .things import Drop


class Attack(base.Action):
    ACTION_NAME = "attack"
    ACTION_DESCRIPTION = "Attack someone with a weapon"
    ACTION_ALIASES = ["hit"]

    def __init__(self, game, command: str):
        super().__init__(game)
        attack_words = ["attack", "hit"]
        self.attacker = self.parser.get_character(
            command, hint="attacker", split_words=attack_words, position="before"
        )
        self.victim = self.parser.get_character(
            command, hint="victim", split_words=attack_words, position="after"
        )
        self.weapon = self.parser.match_item(
            command, self.attacker.inventory, hint="weapon"
        )

    def check_preconditions(self) -> bool:
        """
        Preconditions:
        * There must be an attacker and a victim
        * They must be in the same location
        * There must be a matched weapon
        * The attacker must have the weapon in their inventory
        * The weapon have the property 'is_weapon'
        * The victim must not already be dead or unconscious
        """
        if not self.was_matched(self.attacker):
            description = "The attacker couldn't be found."
            self.parser.fail(description)
            return False
        if not self.was_matched(self.victim):
            description = "The character to attack wasn't matched."
            self.parser.fail(description)
            return False
        if not self.attacker.location.here(self.victim):
            description = "The two characters must be in the same location."
            self.parser.fail(description)
            return False
        if not self.was_matched(
            self.weapon,
            error_message="{name} doesn't have a weapon.".format(
                name=self.attacker.name
            ),
        ):
            return False
        if not self.attacker.is_in_inventory(self.weapon):
            description = "{name} doesn't have the {weapom}.".format(
                name=self.attacker.name, weapon=self.weapon.name
            )
            self.parser.fail(description)
            return False
        if not self.weapon.get_property("is_weapon"):
            description = "{item} is not a weapon".format(item=self.weapon.name)
            self.parser.fail(description)
            return False
        if self.victim.get_property("is_unconscious"):
            description = "{name} is already unconscious".format(name=self.victim.name)
            self.parser.fail(description)
            return False
        if self.victim.get_property("is_dead"):
            description = "{name} is already dead".format(name=self.victim.name)
            self.parser.fail(description)
            return False
        return True

    def apply_effects(self):
        """
        Effects:
        * If the victim is not invulerable to attacks
        ** Knocks the victim unconscious
        ** The victim drops all items in their inventory
        * If the weapon is fragile then it breaks
        """
        description = "{attacker} attacked {victim} with the {weapon}.".format(
            attacker=self.attacker.name,
            victim=self.victim.name,
            weapon=self.weapon.name,
        )
        self.parser.ok(description)

        if self.weapon.get_property("is_fragile"):
            description = "The fragile weapon broke into pieces."
            self.attacker.remove_from_inventory(self.weapon)
            self.parser.ok(description)

        if self.victim.get_property("is_invulerable"):
            description = "The attack has no effect on {name}.".format(
                name=self.victim.name
            )
            self.parser.ok(description)
        else:
            # the victim is knocked unconscious
            self.victim.set_property("is_unconscious", True)
            description = "{name} was knocked unconscious.".format(
                name=self.victim.name.capitalize()
            )
            self.parser.ok(description)

            # the victim drops their inventory
            items = list(self.victim.inventory.keys())
            for item_name in items:
                item = self.victim.inventory[item_name]
                command = "{victim} drop {item}".format(
                    victim=self.victim.name, item=item_name
                )
                drop = Drop(self.game, command)
                if drop.check_preconditions():
                    drop.apply_effects()
