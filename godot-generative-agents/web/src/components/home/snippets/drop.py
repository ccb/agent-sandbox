class Drop(base.Action):
    ACTION_NAME = ActionName.DROP
    ACTION_DESCRIPTION = "Drop something from the character's inventory"

    def check_preconditions(self) -> bool:
        if not self.was_matched(self.item, "I don't see it."):
            return False
        if self.character.is_worn(self.item):
            self.parser.fail(
                f"{self.character.name.capitalize()} is wearing the "
                f"{self.item.name}. Take it off first."
            )
            return False
        if self.item.name not in self.character.carried_items():
            self.parser.fail("You aren't carrying that.")
            return False
        return True

    def apply_effects(self):
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
