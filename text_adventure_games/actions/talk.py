from . import base


class Say(base.Action):
    """A character speaks out loud; everyone in the room can hear it.

    Grammar:
        say <message>            -> broadcast to the room
        say to <name> <message>  -> directed at a co-located character
    """

    ACTION_NAME = "say"
    ACTION_DESCRIPTION = "Say something out loud; others in the room hear it"
    ACTION_ALIASES = ["speak"]

    def __init__(self, game, command, actor=None):
        super().__init__(game, actor=actor)
        # Resolve the speaker from the text BEFORE the verb so a player-issued
        # "say to guard ..." is not mis-attributed to the named recipient.
        self.speaker = self.acting_character(
            command, split_words=["say", "speak"], position="before"
        )
        self.recipient, self.message = self._parse(command)

    def _parse(self, command):
        """Return (recipient_or_None, message). The text after the verb is the
        message; a leading ``to <name>`` (a known character) is a directed
        recipient and is stripped from the message."""
        text = command.lower()
        for verb in ("say", "speak"):
            idx = text.find(verb)
            if idx != -1:
                text = text[idx + len(verb) :]
                break
        text = text.strip()

        recipient = None
        if text.startswith("to "):
            rest = text[3:].strip()
            for name in self.game.characters:
                if rest.startswith(name.lower()):
                    recipient = self.game.characters[name]
                    rest = rest[len(name) :].strip()
                    break
            if recipient is not None:
                text = rest
        return recipient, text.strip()

    def check_preconditions(self) -> bool:
        if not self.message:
            self.parser.fail("Say what?")
            return False
        if self.recipient is not None and not self.at(
            self.recipient, self.speaker.location, describe_error=False
        ):
            self.parser.fail(f"{self.recipient.name} isn't here.")
            return False
        return True

    def apply_effects(self):
        if self.recipient is not None:
            self.parser.ok(
                f"{self.speaker.name} says to {self.recipient.name}: {self.message}"
            )
        else:
            self.parser.ok(f"{self.speaker.name} says: {self.message}")
