from . import base
from ..things.characters import GoalType


class AdoptGoal(base.Action):
    """A character takes on a new goal (e.g. after being persuaded).

    Grammar: ``adopt goal <description>``. The new goal is SHORT-term -- an
    immediate intention prompted by the moment. This is a general-purpose
    goal-management verb available to anyone; what keeps persuasion in check is
    the deciding agent's persona, not a restriction on the action itself.
    """

    ACTION_NAME = "adopt goal"
    ACTION_DESCRIPTION = "Take on a new short-term goal"
    # Goals are an agent/simulation concern, not something a human player types;
    # keep them off the player-facing HELP list.
    PLAYER_VISIBLE = False

    def __init__(self, game, command, actor=None):
        super().__init__(game, actor=actor)
        self.character = self.acting_character(command)
        self.goal_text = self._parse_goal(command)

    def _parse_goal(self, command: str) -> str:
        """The text after the 'adopt goal' verb is the goal description."""
        lowered = command.lower()
        marker = "adopt goal"
        idx = lowered.find(marker)
        if idx != -1:
            return command[idx + len(marker) :].strip()
        return ""

    def check_preconditions(self) -> bool:
        if not self.goal_text:
            self.parser.fail("Adopt what goal?")
            return False
        for g in self.character.goals:
            if not g.done and g.description.lower() == self.goal_text.lower():
                self.parser.fail(f"{self.character.name} already has that goal.")
                return False
        return True

    def apply_effects(self):
        self.character.add_goal(self.goal_text, GoalType.SHORT)
        return self.parser.ok(
            f"{self.character.name} adopts a new goal: {self.goal_text}"
        )


class DropGoal(base.Action):
    """A character abandons one of its current goals.

    Grammar: ``drop goal <description>``. The matching incomplete goal is
    *removed* from the character's goal list (an abandoned goal is deleted, not
    marked done -- `done` means *completed*).
    """

    ACTION_NAME = "drop goal"
    ACTION_DESCRIPTION = "Abandon a current goal"
    PLAYER_VISIBLE = False

    def __init__(self, game, command, actor=None):
        super().__init__(game, actor=actor)
        self.character = self.acting_character(command)
        self.goal_text = self._parse_goal(command)
        self.match = self._find_goal()

    def _parse_goal(self, command: str) -> str:
        """The text after the 'drop goal' verb is the goal description."""
        lowered = command.lower()
        marker = "drop goal"
        idx = lowered.find(marker)
        if idx != -1:
            return command[idx + len(marker) :].strip()
        return ""

    def _find_goal(self):
        for g in self.character.goals:
            if not g.done and g.description.lower() == self.goal_text.lower():
                return g
        return None

    def check_preconditions(self) -> bool:
        if not self.goal_text:
            self.parser.fail("Drop what goal?")
            return False
        if self.match is None:
            self.parser.fail(f"{self.character.name} has no such goal to drop.")
            return False
        return True

    def apply_effects(self):
        self.character.goals.remove(self.match)
        return self.parser.ok(f"{self.character.name} drops the goal: {self.goal_text}")
