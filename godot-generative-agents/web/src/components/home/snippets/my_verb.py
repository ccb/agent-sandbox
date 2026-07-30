from text_adventure_games.actions.base import Action


class MyVerb(Action):
    # What the parser matches on, and what the agent's tool is called.
    ACTION_NAME = "my_verb"
    # The one line the model sees when this verb appears in its menu.
    ACTION_DESCRIPTION = "what this verb does, in a short phrase"
    # Optional. Offer the verb only where the world affords it: some thing in
    # scope -- an item, or the room itself -- must carry this property.
    REQUIRED_AFFORDANCES = ("my_affordance",)

    def __init__(self, game, command: str, actor=None):
        super().__init__(game, actor=actor)
        # Who is acting. Action's helpers match names against what this
        # character can actually see, so nothing off-screen can be referenced.
        self.character = self.acting_character(command, hint="who is acting")

    def check_preconditions(self) -> bool:
        # The gate. Return False and the world does not change. Whatever you
        # pass to parser.fail becomes a memory the agent can retry against,
        # so say why, specifically.
        if not self.has_affordance_in_scope(self.character, "Not possible here."):
            return False
        return True

    def apply_effects(self):
        # Runs only if the gate opened. Change state, then narrate it -- the
        # narration is what other characters can perceive.
        self.character.set_property("my_state", True)
        self.parser.ok(f"{self.character.name} does the thing.")
