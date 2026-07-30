from text_adventure_games.actions.base import Action


class Nap(Action):
    ACTION_NAME = "nap"
    ACTION_DESCRIPTION = "Rest on a bench for a while"
    REQUIRED_AFFORDANCES = ("bench",)

    def __init__(self, game, command: str, actor=None):
        super().__init__(game, actor=actor)
        self.character = self.acting_character(command, hint="who is resting")

    def check_preconditions(self) -> bool:
        if not self.has_affordance_in_scope(self.character, "There's no bench here."):
            return False
        if self.character.get_property("is_resting"):
            self.parser.fail(f"{self.character.name} is already resting.")
            return False
        return True

    def apply_effects(self):
        self.character.set_property("is_resting", True)
        self.parser.ok(f"{self.character.name} sits down on the bench.")
