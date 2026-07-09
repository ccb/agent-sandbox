"""Custom parser for the UPenn boil-water simulation.

The engine's Parser.determine_intent has a substring check for "ate " to match
EAT commands (e.g. "ate apple", "eats bread"). However, this matches custom
verbs like "activate" on word boundaries, incorrectly routing them to EAT before
the word-boundary fallback in the else clause can match them.

This parser fixes that by using word-boundary matching for "ate" and adding
"activate" / "deactivate" to the early keyword chain so they win.
"""

import re
from text_adventure_games.parsing import Parser
from text_adventure_games.enums import ActionName


class PennParser(Parser):
    """Extends the engine Parser to fix "ate" false positives and add device verbs."""

    def determine_intent(self, command: str, actor=None):
        """Override to add device verbs before the buggy 'ate' check."""
        # Resolve the acting character (the actor, else a player-default scan).
        character = actor if actor is not None else self.get_character(command)
        command = command.lower()
        if "," in command:
            return ActionName.SEQUENCE

        # Specific-first: multi-word action names
        specific = self._match_specific_action(command)
        if specific is not None:
            return specific

        # Crafting verbs
        if getattr(self.game, "recipes", None):
            first = command.split(" ", 1)[0]
            if first in (
                "make",
                "cook",
                "craft",
                "combine",
                "prepare",
                "build",
                "create",
            ):
                return ActionName.CRAFT

        # Device verbs (boil-water #300): added before EAT to avoid "ate" false positive
        if command.startswith("activate ") or command == "activate":
            return "activate"
        elif command.startswith("deactivate ") or command == "deactivate":
            return "deactivate"

        # Speech
        if (
            command.startswith("say ")
            or command.startswith("speak ")
            or command in ("say", "speak")
        ):
            return ActionName.SAY
        elif command.split(" ", 1)[0] in ("throw", "hurl", "lob"):
            return "throw"
        elif command.startswith("adopt goal"):
            return "adopt goal"
        elif command.startswith("drop goal"):
            return "drop goal"
        elif command.startswith("ask ") and " about " in command:
            return ActionName.TALK
        elif self.get_direction(command, character.location):
            return ActionName.GO
        elif (
            command == "dismount"
            or command.startswith("dismount")
            or command.startswith("get off")
        ):
            return ActionName.DISMOUNT
        elif command.split(" ", 1)[0] in (
            "ride",
            "mount",
            "board",
        ) or command.startswith(("get on", "hop on", "climb aboard")):
            return ActionName.MOUNT
        elif command == "look" or command == "l":
            return ActionName.DESCRIBE
        elif command.startswith("look ") or command.startswith("l "):
            rest = command.split(" ", 1)[1].strip()
            if rest.startswith("at "):
                rest = rest[3:].strip()
            if rest in ("around", "round", "here", ""):
                return ActionName.DESCRIBE
            if self.get_direction(rest, character.location):
                return ActionName.DESCRIBE
            return ActionName.EXAMINE
        elif "examine " in command or command.startswith("x "):
            return ActionName.EXAMINE
        elif command.startswith("take off") or command.startswith("remove "):
            return ActionName.TAKE_OFF
        elif command.startswith("stow ") or command.startswith("unequip "):
            return ActionName.UNWIELD
        elif "take " in command or "get " in command:
            return ActionName.GET
        elif "light" in command:
            return ActionName.LIGHT
        elif "drop " in command:
            return ActionName.DROP
        elif command.startswith("break") or command.startswith("smash"):
            return ActionName.BREAK
        # FIX: Use word-boundary match for "eat" to avoid matching "activate" on "ate"
        elif re.search(r"\b(eat|eats|ate|eating)\b", command):
            return ActionName.EAT
        elif "drink" in command:
            return ActionName.DRINK
        elif "give" in command or command.startswith("hand "):
            return self._match_give_action(command) or ActionName.GIVE
        elif "attack" in command or "hit " in command or "hits " in command:
            return ActionName.ATTACK
        elif "inventory" in command or command == "i":
            return ActionName.INVENTORY
        elif command == "wait" or command == "z":
            return ActionName.WAIT
        elif command in ("help", "h", "commands", "?") or command.startswith("help"):
            return ActionName.HELP
        elif "quit" in command:
            return ActionName.QUIT
        else:
            # Longest registered action name or single-word alias
            best_name, best_len = None, -1
            for _, action in self.actions.items():
                phrases = [action.action_name()] + list(
                    getattr(action, "ACTION_ALIASES", []) or []
                )
                for phrase in phrases:
                    if phrase and re.search(rf"\b{re.escape(phrase)}\b", command):
                        if len(phrase) > best_len:
                            best_name, best_len = action.action_name(), len(phrase)
            return best_name
