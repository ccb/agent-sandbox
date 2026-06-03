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
        recipient and is stripped from the message.

        Detection and matching are done on a lowercased copy; the returned
        message is recovered from the most-recent command_history entry so
        that the player original capitalization is preserved.

        Recipient matching requires a whole-token (word-boundary) match:
        character name "thief" does NOT match the token "thiefery".
        """
        # Recover the original-cased command from history. parse_command()
        # stores it there before calling parse_action(), which lowercases
        # the command before passing it here.
        history = self.parser.command_history
        original = command  # fallback if history is empty
        for entry in reversed(history):
            if entry.get("role") == "user":
                original = entry["content"]
                break

        lower = command.lower()  # command is already lowercased by parse_action
        original_lower = original.lower()

        # Strip the verb; track the byte offset in the original string so we
        # can later slice the original-cased message.
        verb_end_lower = 0  # end index in lower
        verb_end_orig = 0  # corresponding end index in original
        for verb in ("say", "speak"):
            idx = lower.find(verb)
            if idx != -1:
                verb_end_lower = idx + len(verb)
                # Find the same verb in the original (case-insensitive).
                idx_orig = original_lower.find(verb, idx)
                verb_end_orig = (
                    (idx_orig + len(verb)) if idx_orig != -1 else verb_end_lower
                )
                break

        # after_lower: text after the verb, with leading spaces stripped.
        after_lower = lower[verb_end_lower:].lstrip()
        spaces_after_verb = len(lower[verb_end_lower:]) - len(after_lower)
        after_orig_start = verb_end_orig + spaces_after_verb

        recipient = None
        msg_orig_start = after_orig_start  # start of message in original

        if after_lower.startswith("to "):
            to_prefix = "to "
            after_to = after_lower[len(to_prefix) :]
            after_to_stripped = after_to.lstrip()
            spaces_after_to = len(after_to) - len(after_to_stripped)
            rest_lower = after_to_stripped
            # Corresponding start of rest in original string.
            rest_orig_start = after_orig_start + len(to_prefix) + spaces_after_to

            # Match a character name as whole tokens (word-boundary safe).
            rest_tokens = rest_lower.split()
            for name in self.game.characters:
                name_tokens = name.lower().split()
                if (
                    len(rest_tokens) >= len(name_tokens)
                    and rest_tokens[: len(name_tokens)] == name_tokens
                ):
                    recipient = self.game.characters[name]
                    # Advance past the matched tokens in rest_lower.
                    pos = 0
                    for tok in name_tokens:
                        pos = rest_lower.index(tok, pos) + len(tok)
                    after_name = rest_lower[pos:].lstrip()
                    spaces_after_name = len(rest_lower[pos:]) - len(after_name)
                    msg_orig_start = rest_orig_start + pos + spaces_after_name
                    break

        # Slice the message from the original string so casing is preserved.
        message = original[msg_orig_start:].strip()
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
