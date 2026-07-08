"""SAVE / RESTORE / SCRIPT: the Infocom trio, over (seed, journal) saves.

All three are FREE actions -- writing the expedition log down is the player
consulting their own record, not the character spending a turn (and a wound
should never land *because* you saved). They register in every game via the
actions package's auto-discovery, and fail politely until the host attaches a
store (``game.save_store``) -- see ``saves.py`` for the stores and the loop
contract.

RESTORE cannot rebuild the world from inside it: it stages the chosen blob on
``game.pending_restore`` and reports; the loop that owns the game object
(``saves.run_with_saves`` for the terminal, ``app_api`` for the iOS app)
performs the rebuild after the command returns.
"""

from . import base
from ..saves import SLOTS, snapshot


def _store(game):
    return getattr(game, "save_store", None)


def _slot_arg(command: str, verbs: tuple) -> str | None:
    """The slot named in the command ('save 2' -> '2'), or None to list."""
    words = command.lower().split()
    words = [w for w in words if w not in verbs and w not in ("to", "from", "game")]
    return words[0] if words else None


def _describe_slots(store) -> str:
    listed = store.list()
    lines = []
    for slot in SLOTS:
        meta = listed.get(slot)
        if meta:
            lines.append(
                f"  {slot}: {meta.get('room', '?')}, turn {meta.get('turn', '?')}, "
                f"score {meta.get('score', '?')}"
            )
        else:
            lines.append(f"  {slot}: (empty)")
    return "\n".join(lines)


class Save(base.Action):
    """SAVE [slot]: write the expedition log -- the seed and every
    turn-consuming command so far -- to a slot. Bare SAVE lists the slots."""

    ACTION_NAME = "save"
    FREE_ACTION = True  # writing the log down costs no turn
    ACTION_DESCRIPTION = "Save your expedition to a numbered position"
    ACTION_ALIASES = ["save game"]

    def __init__(self, game, command: str, actor=None):
        super().__init__(game, actor=actor)
        self.command = command

    def check_preconditions(self) -> bool:
        if _store(self.game) is None:
            self.parser.fail("There is nowhere here to keep an expedition log.")
            return False
        slot = _slot_arg(self.command, ("save",))
        if slot is not None and slot not in SLOTS:
            self.parser.fail(
                f"No such position. The log has positions {', '.join(SLOTS[:-1])}."
            )
            return False
        return True

    def apply_effects(self):
        store = _store(self.game)
        slot = _slot_arg(self.command, ("save",))
        if slot is None:
            self.parser.ok(
                "Save to which position? (SAVE 1, SAVE 2, ...)\n"
                + _describe_slots(store)
            )
            return
        store.write(slot, snapshot(self.game))
        self.parser.ok(f"Saved to position {slot}.")


class Restore(base.Action):
    """RESTORE [slot]: stage a saved expedition for the host loop to rebuild.
    Bare RESTORE lists the slots."""

    ACTION_NAME = "restore"
    FREE_ACTION = True
    ACTION_DESCRIPTION = "Restore a saved expedition"
    ACTION_ALIASES = ["restore game", "load", "load game"]

    def __init__(self, game, command: str, actor=None):
        super().__init__(game, actor=actor)
        self.command = command

    def check_preconditions(self) -> bool:
        store = _store(self.game)
        if store is None:
            self.parser.fail("There is no expedition log to restore from.")
            return False
        slot = _slot_arg(self.command, ("restore", "load"))
        if slot is not None and store.read(slot) is None:
            self.parser.fail(f"Position {slot} is empty.")
            return False
        return True

    def apply_effects(self):
        store = _store(self.game)
        slot = _slot_arg(self.command, ("restore", "load"))
        if slot is None:
            self.parser.ok(
                "Restore which position? (RESTORE 1, RESTORE 2, ...)\n"
                + _describe_slots(store)
            )
            return
        # Stage it; the loop that owns the game performs the rebuild.
        self.game.pending_restore = store.read(slot)
        self.parser.ok(f"Restoring position {slot}...")


class Script(base.Action):
    """SCRIPT: print the expedition log itself -- every turn-consuming command
    so far. This is also exactly what a save file contains."""

    ACTION_NAME = "script"
    FREE_ACTION = True
    ACTION_DESCRIPTION = "Print the log of every command this expedition"
    ACTION_ALIASES = ["transcript", "log"]

    def __init__(self, game, command: str, actor=None):
        super().__init__(game, actor=actor)

    def check_preconditions(self) -> bool:
        return True

    def apply_effects(self):
        if not self.game.journal:
            self.parser.ok("The expedition log is empty; nothing has happened yet.")
            return
        lines = [f"The expedition log ({len(self.game.journal)} commands):"]
        lines += [f"  > {c}" for c in self.game.journal]
        self.parser.ok("\n".join(lines))
