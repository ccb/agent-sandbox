"""Perception verbs: READ and SEARCH (Tier 2 of the Parsely feature outline).

Both are generic, uniform interactions every game reuses, so they're built-in
always-registered actions (like ``Examine`` / ``Open``) rather than per-game
custom classes:

* **READ** prints an item's ``read_text`` -- a sign, a book, an inscription.
  Items become readable just by carrying that text; no custom action needed.
* **SEARCH** reveals *hidden* items. An item flagged ``is_hidden`` is concealed
  (not described, not in scope, not gettable) until a SEARCH of its location or
  holder clears the flag -- "search the straw, find a pendant."
"""

from __future__ import annotations

from . import base
from ..enums import ActionName, Property


def _comma_list(parts: list[str]) -> str:
    """ "a", "a and b", or "a, b, and c" -- for listing what a search turns up."""
    if len(parts) == 1:
        return parts[0]
    if len(parts) == 2:
        return f"{parts[0]} and {parts[1]}"
    return ", ".join(parts[:-1]) + f", and {parts[-1]}"


class Read(base.Action):
    """Read the writing on an item (its ``read_text``).

    An item is readable if it carries a ``read_text`` string (or is flagged
    ``is_readable``). The text can be set declaratively --
    ``item.set_property("read_text", "Beware the troll.")`` -- so a sign or book
    is first-class readable without a bespoke action.
    """

    ACTION_NAME = ActionName.READ
    ACTION_DESCRIPTION = "Read the writing on something"
    DURATION = 1  # a quick read (issue #24)

    def __init__(self, game, command: str, actor=None):
        super().__init__(game, actor=actor)
        self.character = self.acting_character(command, hint="reader")
        self.item = self.parser.match_item(
            command,
            self.parser.get_items_in_scope(self.character),
            hint="thing to read",
        )

    def check_preconditions(self) -> bool:
        if not self.was_matched(self.item, "I don't see it."):
            return False
        if not (
            self.item.get_property(Property.READ_TEXT)
            or self.item.get_property(Property.READABLE)
        ):
            self.parser.fail(f"There's nothing to read on the {self.item.name}.")
            return False
        return True

    def apply_effects(self):
        text = (
            self.item.get_property(Property.READ_TEXT)
            or self.item.examine_text
            or self.item.description
        )
        self.parser.ok(text)
        # A readable thing may carry a ``figure``: reading it deals the card,
        # forced -- poring over a document is as deliberate as examining it.
        # Player reads only: an NPC reading doesn't draw on the player's screen.
        if self.character is self.game.player:
            fig = self.item.get_property("figure")
            self.game.show_figure(
                fig(self.game) if callable(fig) else fig, force=True
            )


# Verb phrases SEARCH strips to find an optional target ("search the desk" ->
# "desk"). Longest first so "look inside" wins over a bare "look".
_SEARCH_VERBS = ("search through", "search", "look inside", "look in", "rummage")
_LEADING_WORDS = ("the ", "a ", "an ", "in ", "inside ", "through ", "my ")


class Search(base.Action):
    """Search a place or thing, revealing whatever is hidden there.

    With no target ("search", "search the cells") it reveals hidden items lying
    in the current location. With a target ("search the desk") it reveals hidden
    items inside that holder -- whether it's open or closed, since searching is
    the act of looking inside. Revealing clears each item's ``is_hidden`` flag,
    so it then describes, scopes, and gets normally.
    """

    ACTION_NAME = ActionName.SEARCH
    ACTION_DESCRIPTION = "Search a place or thing for something hidden"
    ACTION_ALIASES = ["look in", "look inside", "search through"]

    def __init__(self, game, command: str, actor=None):
        super().__init__(game, actor=actor)
        self.character = self.acting_character(command, hint="searcher")
        self.location = self.character.location
        target_phrase = self._target_phrase(command)
        self.target = (
            self.parser.match_item(
                target_phrase,
                self.parser.get_items_in_scope(self.character),
                hint=target_phrase,
            )
            if target_phrase
            else None
        )

    @staticmethod
    def _target_phrase(command: str) -> str:
        text = command.lower().strip()
        for verb in _SEARCH_VERBS:
            if text.startswith(verb):
                text = text[len(verb) :].strip()
                break
        for lead in _LEADING_WORDS:
            if text.startswith(lead):
                text = text[len(lead) :].strip()
        return text

    def check_preconditions(self) -> bool:
        # You can always search; whether you find anything is decided in effects.
        if not self.was_matched(self.character, "No character was matched."):
            return False
        return True

    def apply_effects(self):
        if self.target is not None:
            # Searching a specific holder is the act of looking inside it: it
            # reveals hidden contents AND reports what's plainly there -- a full
            # pack should never answer "nothing of interest". Rummaging also
            # opens a closed (unlocked) container, so what you found is
            # reachable by GET.
            if self.target.get_property(Property.IS_LOCKED):
                self.parser.ok(f"The {self.target.name} is locked.")
                return
            pool = self.target.contents
            for it in pool.values():
                if it.get_property(Property.IS_HIDDEN):
                    it.set_property(Property.IS_HIDDEN, False)
            if pool:
                if (
                    self.target.get_property("is_container")
                    and not self.target.is_open()
                ):
                    self.target.set_property("is_closed", False)
                listed = _comma_list([it.description for it in pool.values()])
                self.parser.ok(f"You search the {self.target.name} and find {listed}.")
            else:
                self.parser.ok("You search but find nothing of interest.")
            return
        pool = self.location.items if self.location is not None else {}
        found = [it for it in pool.values() if it.get_property(Property.IS_HIDDEN)]
        if not found:
            self.parser.ok("You search but find nothing of interest.")
            return
        for it in found:
            it.set_property(Property.IS_HIDDEN, False)
        listed = _comma_list([it.description for it in found])
        self.parser.ok(f"You search around and find {listed}.")
