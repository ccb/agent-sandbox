from . import base


class HintMenu(base.Action):
    """The Infocom-style hint menu (see :mod:`..hints`).

    ``HINT`` lists the open questions -- puzzles the player has met and not
    yet beaten -- numbered, with each topic's reveal progress. ``HINT 2`` or
    ``HINT TROLL`` reveals that topic's next level (and re-shows the levels
    already bought). A topic fully revealed simply re-reads in full.

    A hint costs no turn (consulting the booklet shouldn't get you mauled)
    but IS journaled, so a (seed, journal) replay -- the save system --
    rebuilds the same reveals. ``game.hints_taken`` counts levels bought,
    for games that want to stamp the final score.
    """

    ACTION_NAME = "hint"
    ACTION_DESCRIPTION = "Ask for a nudge (ask again for stronger hints)"
    ACTION_ALIASES = ["hints"]
    FREE_ACTION = True  # no turn tick, no NPC turns, no triggers
    JOURNALED = True  # ...but replays must remember what was revealed

    def __init__(self, game, command: str, actor=None):
        super().__init__(game, actor=actor)
        words = command.lower().split()
        while words and words[0] in ("hint", "hints"):
            words.pop(0)
        self.topic_words = words

    def check_preconditions(self) -> bool:
        if not getattr(self.game, "hints", None):
            self.parser.fail("This story keeps its own counsel: no hints here.")
            return False
        self.topic = None
        if self.topic_words:
            self.topic = self._match_topic(self._menu())
            if self.topic is None:
                # A miss is a FAIL: it prints, and never enters the journal.
                self.parser.fail(
                    "No open question matches that. Type HINT alone to see them."
                )
                return False
        return True

    def _menu(self):
        return [h for h in self.game.hints if h.is_open(self.game)]

    def apply_effects(self):
        menu = self._menu()
        if not self.topic_words:
            if not menu:
                self.parser.ok(
                    "Nothing you have met wants a hint right now. "
                    "(Solved puzzles leave the menu.)"
                )
                return
            lines = ["The questions worth asking, so far:"]
            for i, h in enumerate(menu, 1):
                done = self.game.hint_progress.get(h.key, 0)
                gauge = f"  ({done}/{len(h.levels)})" if done else ""
                lines.append(f"  {i}. {h.question}{gauge}")
            lines.append("(HINT <number> for a nudge; again for a stronger one.)")
            taken = getattr(self.game, "hints_taken", 0)
            if taken:
                lines.append(f"[{taken} hint{'s' if taken != 1 else ''} taken]")
            self.parser.ok("\n".join(lines))
            return

        topic = self.topic
        done = self.game.hint_progress.get(topic.key, 0)
        if done < len(topic.levels):
            done += 1
            self.game.hint_progress[topic.key] = done
            self.game.hints_taken += 1
        lines = [topic.question]
        for i in range(done):
            lines.append(f"  {i + 1}. {topic.levels[i]}")
        if done >= len(topic.levels):
            lines.append("(That is the whole of it.)")
        else:
            lines.append(f"(HINT {topic.key.upper()} again for more.)")
        self.parser.ok("\n".join(lines))

    def _match_topic(self, menu):
        """Resolve the player's words to an OPEN topic: menu number first,
        then key, then a word from the question itself."""
        text = " ".join(self.topic_words)
        if text.isdigit():
            n = int(text)
            if 1 <= n <= len(menu):
                return menu[n - 1]
            return None
        for h in menu:
            if text == h.key.lower():
                return h
        for h in menu:
            hay = (h.key + " " + h.question).lower()
            if all(w in hay for w in self.topic_words):
                return h
        return None
