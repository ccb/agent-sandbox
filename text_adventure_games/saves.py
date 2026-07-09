"""(seed, journal) saves: the expedition log as the save file.

A seeded game is deterministic (guarded by tests/test_journal_replay.py), so a
save is not a pickle of the world -- it is the RNG seed plus
:attr:`~text_adventure_games.games.Game.journal`, and restore is rebuild +
:meth:`~text_adventure_games.games.Game.replay`. A few KB of human-readable
JSON, robust to engine refactors, and the transcript falls out for free
(docs/design/ios-tomb-app.md §2).

The pieces:

- :func:`snapshot` / :func:`restore` -- blob <-> game.
- :class:`MemorySaveStore` / :class:`FileSaveStore` -- where blobs live. The
  iOS app implements the same three methods over ``localStorage``.
- The SAVE / RESTORE / SCRIPT player commands live in ``actions/saves.py``;
  they appear in every game and fail politely until a store is attached
  (``game.save_store = FileSaveStore(path)``). RESTORE can't rebuild the world
  from inside it, so it stages the blob on ``game.pending_restore`` for the
  loop that owns the game object -- :func:`run_with_saves` is that loop for
  the terminal, ``app_api`` is it for the app.
"""

from __future__ import annotations

import datetime
import json
import os

SAVE_FORMAT_VERSION = 1

#: Slot names shown by SAVE/RESTORE. "auto" is written by hosts that autosave
#: (the iOS app writes it every turn); the numbered slots are the player's.
SLOTS = ("1", "2", "3", "auto")


def _engine_version() -> str:
    from . import __version__

    return __version__


def snapshot(game) -> dict:
    """The save blob for *game*: seed + journal + a fingerprint for the
    version guard. Requires the game to have been built with a seed."""
    return {
        "v": SAVE_FORMAT_VERSION,
        "engine": _engine_version(),
        "seed": getattr(game, "rng_seed", None),
        "commands": list(game.journal),
        "meta": {
            "room": game.player.location.name if game.player.location else None,
            "turn": game.turn,
            "score": game.score,
            "saved_at": datetime.datetime.now().isoformat(timespec="seconds"),
        },
    }


def restore(build_fn, blob) -> tuple:
    """Rebuild a game from *blob*: ``build_fn(seed=...)`` + replay.

    Returns ``(game, drift)`` where *drift* is True when the replayed state no
    longer matches the blob's fingerprint -- the game content changed since the
    save was written (the honest failure: offer the transcript, not a corrupt
    resume)."""
    game = build_fn(seed=blob.get("seed"))
    game.replay(blob.get("commands", []))
    meta = blob.get("meta", {})
    drift = (
        meta.get("room") is not None
        and game.player.location is not None
        and (
            game.player.location.name != meta.get("room")
            or game.turn != meta.get("turn")
            or game.score != meta.get("score")
        )
    )
    return game, drift


class MemorySaveStore:
    """Slots in a dict: the default for tests and short-lived hosts."""

    def __init__(self):
        self._slots: dict = {}

    def read(self, slot: str):
        return self._slots.get(str(slot))

    def write(self, slot: str, blob: dict) -> None:
        self._slots[str(slot)] = blob

    def clear(self, slot: str) -> None:
        self._slots.pop(str(slot), None)

    def list(self) -> dict:
        return {s: b.get("meta", {}) for s, b in self._slots.items()}


class FileSaveStore:
    """Slots in one JSON file (e.g. ``~/.tomb_saves.json``) for the CLI."""

    def __init__(self, path: str):
        self.path = os.path.expanduser(path)

    def _load(self) -> dict:
        try:
            with open(self.path) as fh:
                return json.load(fh)
        except (FileNotFoundError, json.JSONDecodeError):
            return {}

    def read(self, slot: str):
        return self._load().get(str(slot))

    def write(self, slot: str, blob: dict) -> None:
        data = self._load()
        data[str(slot)] = blob
        with open(self.path, "w") as fh:
            json.dump(data, fh, indent=1)

    def clear(self, slot: str) -> None:
        data = self._load()
        if data.pop(str(slot), None) is not None:
            with open(self.path, "w") as fh:
                json.dump(data, fh, indent=1)

    def list(self) -> dict:
        return {s: b.get("meta", {}) for s, b in self._load().items()}


def run_with_saves(build_fn, store, seed: int = 0):
    """An interactive loop that owns the game object, so RESTORE can actually
    happen: build seeded, attach *store*, and service ``pending_restore`` after
    each command by swapping in the rebuilt game. The terminal counterpart of
    the app's ``app_api`` loop."""
    game = build_fn(seed=seed)
    game.save_store = store
    game.parser.parse_command("look")
    while True:
        command = input("\n> ")
        game.do_command(command)
        pending = getattr(game, "pending_restore", None)
        if pending is not None:
            game.pending_restore = None
            game, drift = restore(build_fn, pending)
            game.save_store = store
            if drift:
                game.parser.ok(
                    "This expedition was logged by an older tomb; the paths "
                    "have shifted since. The log survives (SCRIPT), but the "
                    "restore may not be faithful."
                )
            game.parser.ok(
                f"[restored: {game.player.location.name}, turn {game.turn}, "
                f"score {game.score}/{game.max_score}]"
            )
            game.parser.parse_command("look")
        if game.is_game_over():
            break
    return game
