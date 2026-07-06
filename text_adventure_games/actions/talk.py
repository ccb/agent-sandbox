from . import base
from ..enums import ActionName, Role


class Talk(base.Action):
    """Greet / talk to a co-located character, optionally about a topic.

    ``talk to X`` surfaces the character's default ``talk_text``; ``talk to X
    about <topic>`` / ``ask X about <topic>`` looks up a canned line in the
    character's ``talk_topics`` (the topic is resolved via ``parser.match_topic``
    -- by keyword in the exact-match parser, by meaning in the LLM parser).
    Lines are printed verbatim (author them as narration). We deliberately do
    NOT voice ``persona`` -- that's the character's private self-concept driving
    the LLM agent (npc.py), not dialogue. A game that wants richer scripted
    dialogue can still register its own ``talk to <name>`` action; the parser's
    specific-first pass routes there before this generic verb.
    """

    ACTION_NAME = ActionName.TALK
    ACTION_DESCRIPTION = "Talk to someone nearby, optionally about a topic"
    ACTION_ALIASES = ["talk to", "talk with", "chat with"]

    def __init__(self, game, command, actor=None):
        super().__init__(game, actor=actor)
        self.command = command
        self.character = self.acting_character(command, hint="talker")
        self.target = self.character_in_room(command, self.character)

    def check_preconditions(self) -> bool:
        if self.target is None:
            self.parser.fail("There's no one here to talk to.")
            return False
        return True

    def apply_effects(self):
        name = self.target.name.capitalize()
        topics = getattr(self.target, "talk_topics", None) or {}
        # "... about <topic>" asks about something specific; resolve which topic.
        if " about " in self.command.lower() and topics:
            topic = self.parser.match_topic(self.command, topics)
            if topic is not None:
                self.parser.ok(topics[topic])
            else:
                self.parser.ok(f"{name} has nothing to say about that.")
            return
        line = getattr(self.target, "talk_text", "")
        # A talk_text may be a callable(game) -> str, computed at speech time
        # (like travel_descriptions) -- so a character can answer to context
        # (whisper while a monster shares the room, say).
        if callable(line):
            line = line(self.game)
        self.parser.ok(line if line else f"{name} has nothing to say.")


class Follow(base.Action):
    """Ask a co-located character to follow the actor.

    Grammar: ``follow me`` / ``<npc> follow me`` / ``ask <npc> to follow``. The
    named character starts following the actor; thereafter the engine drags it
    along whenever the actor moves (Game.drag_followers). A character may decline
    by setting ``refuses_follow`` (with an optional ``follow_refusal_message``) --
    e.g. a companion who won't come until you've done something first.
    """

    ACTION_NAME = ActionName.FOLLOW
    ACTION_DESCRIPTION = "Ask someone to follow you"

    def __init__(self, game, command, actor=None):
        super().__init__(game, actor=actor)
        self.leader = self.acting_character(command, hint="leader")
        self.target = self.character_in_room(command, self.leader)
        # "follow me" with no one named: if exactly one other character is here,
        # that's who you mean.
        if self.target is None and self.leader.location is not None:
            others = [
                c
                for c in self.leader.location.characters.values()
                if c is not self.leader
            ]
            if len(others) == 1:
                self.target = others[0]

    def check_preconditions(self) -> bool:
        if self.target is None:
            self.parser.fail("Who should follow you?")
            return False
        if self.target.following is self.leader:
            self.parser.fail(
                f"{self.target.name.capitalize()} is already following you."
            )
            return False
        if self.target.get_property("refuses_follow"):
            self.parser.fail(
                self.target.get_property("follow_refusal_message")
                or f"{self.target.name.capitalize()} won't follow you."
            )
            return False
        return True

    def apply_effects(self):
        self.target.following = self.leader
        self.parser.ok(f"{self.target.name.capitalize()} agrees to follow you.")


class Unfollow(base.Action):
    """Tell a follower to wait / stop following.

    Grammar: ``stop following`` / ``wait here``. Clears following for the named
    character, or for every character currently following the actor here."""

    ACTION_NAME = ActionName.UNFOLLOW
    ACTION_DESCRIPTION = "Tell a follower to wait here"
    ACTION_ALIASES = ["wait here", "stop following me"]

    def __init__(self, game, command, actor=None):
        super().__init__(game, actor=actor)
        self.leader = self.acting_character(command, hint="leader")
        named = self.character_in_room(command, self.leader)
        if named is not None:
            self.targets = [named] if named.following is self.leader else []
        else:
            loc = self.leader.location
            here = loc.characters.values() if loc is not None else []
            self.targets = [c for c in here if c.following is self.leader]

    def check_preconditions(self) -> bool:
        if not self.targets:
            self.parser.fail("No one is following you.")
            return False
        return True

    def apply_effects(self):
        for c in self.targets:
            c.following = None
            self.parser.ok(f"{c.name.capitalize()} waits here.")


class Say(base.Action):
    """A character speaks out loud; everyone in the room can hear it.

    Grammar:
        say <message>            -> broadcast to the room
        say to <name> <message>  -> directed at a co-located character
    """

    ACTION_NAME = ActionName.SAY
    ACTION_DESCRIPTION = "Say something out loud; others in the room hear it"
    ACTION_ALIASES = ["speak"]

    # Speaking out loud carries one room (issue #80 hearing): a startle reaction
    # (the AC4 doe) keys on any sound it hears. Quiet "talk to" stays room-scoped.
    AUDIBLE_RADIUS = 1

    def sound_description(self) -> str:
        return "a raised voice"

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
            if entry.get("role") == Role.USER:
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
        # Deliver the utterance to whoever can perceive it. WHO hears is decided
        # by the game's audibility seam (room-based by default; override
        # Game.audience_for for a continuous/range-based world), so Say stays
        # ignorant of distance.
        for listener in self.game.audience_for(
            self.speaker, self.message, self.recipient
        ):
            listener.hear(self._heard_line(listener))

    def _heard_line(self, listener) -> str:
        """Render the spoken line from *listener*'s point of view, so a listener
        can tell speech directed at them ("said to you") from speech merely
        overheard ("said to <name>") or broadcast ("said:")."""
        if self.recipient is listener:
            return f"{self.speaker.name} said to you: {self.message}"
        if self.recipient is not None:
            return f"{self.speaker.name} said to {self.recipient.name}: {self.message}"
        return f"{self.speaker.name} said: {self.message}"
