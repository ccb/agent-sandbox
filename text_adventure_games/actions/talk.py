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
        """Return ``(recipient_or_None, message)``.

        The text after the ``say``/``speak`` verb is the message. A leading
        ``to <name>`` that names a known character makes the speech directed at
        that character (and the name is removed from the message); otherwise the
        speech is a broadcast and the whole text after the verb is the message.

        Recipient names are matched one whole word at a time, so the character
        "thief" is not matched by the word "thiefery".
        """
        # ``command`` arrives lowercased: parse_action lowercases every command
        # so keyword matching is case-insensitive. To keep the speaker's
        # original capitalization in the spoken message, recover the untouched
        # text from the command history, where parse_command recorded it
        # verbatim just before parse_action lowercased it.
        original = command
        for entry in reversed(self.parser.command_history):
            if entry.get("role") == "user":
                original = entry["content"]
                break

        words = original.split()
        # Drop the leading verb ("say" or "speak").
        if words and words[0].lower() in ("say", "speak"):
            words = words[1:]

        recipient = None
        # An optional leading "to <name>" makes the speech directed.
        if words and words[0].lower() == "to":
            after_to = words[1:]
            for name in self.game.characters:
                name_words = name.lower().split()
                head = [w.lower() for w in after_to[: len(name_words)]]
                if name_words and head == name_words:
                    recipient = self.game.characters[name]
                    words = after_to[len(name_words) :]
                    break
            # If no known character followed "to", leave the words untouched so
            # the message is broadcast and simply starts with the word "to".

        message = " ".join(words).strip()
        return recipient, message

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
