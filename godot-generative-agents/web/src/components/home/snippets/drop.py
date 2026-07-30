class Drop(base.Action):
    ACTION_NAME = ActionName.DROP
    ACTION_DESCRIPTION = "Drop something from the character's inventory"

    def check_preconditions(self) -> bool:
        if not self.was_matched(self.item, "I don't see it."):
            return False
        if self.character.is_worn(self.item):
            self.parser.fail(f"{self.character.name} is wearing it.")
            return False
        if self.item.name not in self.character.carried_items():
            self.parser.fail("You aren't carrying that.")
            return False
        return True

    def apply_effects(self):
        self.character.discard_item(self.item)
        self.item.location = self.location
        self.location.add_item(self.item)
        self.parser.ok(f"{self.character.name} dropped the {self.item.name}.")
