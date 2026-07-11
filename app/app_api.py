"""The JS <-> Python bridge for the Tomb terminal (docs/design/ios-tomb-app.md §1.1).

The only new Python in the app. Loaded into Pyodide after the engine wheel;
JavaScript calls the four entry points and gets JSON strings back:

- ``boot(seed)`` -- build the Tomb (seeded: determinism is what makes saves
  work), attach the save store, render the opening look.
- ``command(text)`` -- one turn: the turn's channel events plus status. Also
  services a staged RESTORE (this module is the loop that owns the game
  object) and autosaves every turn to the "auto" slot.
- ``suggestions()`` -- verbs and the nouns the player could actually mean
  *here*, honoring perception: in the dark, the visible-noun well runs dry.
- ``transcript()`` -- the expedition log, for the share sheet.

Everything crosses as JSON so neither side holds live references to the other.
Runs identically under plain CPython (tests use it directly; the save store
falls back to memory when ``js.localStorage`` is absent).
"""

import json

from text_adventure_games import saves
from text_adventure_games.adventures import tomb_of_nassak_an_rah as tomb
from text_adventure_games.perception import Sight
from text_adventure_games.reporting import CaptureRenderer

_game = None
_cap = None
_store = None

#: The accessory bar's verb row: curated, not exhaustive (HELP lists all).
VERBS = [
    "look",
    "hint",
    "examine",
    "take",
    "drop",
    "open",
    "search",
    "read",
    "taste",
    "attack",
    "burn",
    "throw",
    "light",
    "drink",
    "talk to",
    "wear",
    "inventory",
    "wait",
]


class _LocalStorageStore:
    """The browser's save store: SLOTS in ``localStorage`` (design §2)."""

    PREFIX = "tomb_save_"

    def __init__(self):
        from js import localStorage  # present only under Pyodide in a browser

        self._ls = localStorage

    def read(self, slot):
        raw = self._ls.getItem(self.PREFIX + str(slot))
        return json.loads(raw) if raw else None

    def write(self, slot, blob):
        self._ls.setItem(self.PREFIX + str(slot), json.dumps(blob))

    def clear(self, slot):
        self._ls.removeItem(self.PREFIX + str(slot))

    def list(self):
        out = {}
        for slot in saves.SLOTS:
            blob = self.read(slot)
            if blob:
                out[slot] = blob.get("meta", {})
        return out


def _make_store():
    try:
        return _LocalStorageStore()
    except ImportError:
        return saves.MemorySaveStore()


def _events():
    return [{"channel": m.channel.value, "text": m.text} for m in _cap.drain()]


def _status():
    return {
        "room": _game.player.location.name if _game.player.location else None,
        "turn": _game.turn,
        "score": _game.score,
        "max_score": _game.max_score,
        "game_over": _game.is_game_over(),
        "won": _game.is_won(),
        "hints": _game.hints_taken,
    }


def _reachable_contents(holder):
    out, frontier = [], [holder]
    while frontier:
        for name, item in frontier.pop().accessible_contents().items():
            out.append(name)
            frontier.append(item)
    return out


def _suggestions():
    """Nouns the player could mean here -- perception-honest: room contents
    only when they can actually be seen; inventory and exits always."""
    loc = _game.player.location
    scene = _game.perceive(_game.player)
    nouns = []
    if scene.sight >= Sight.CLEAR:
        for i in loc.items.values():
            if i.get_property("is_hidden"):
                continue
            nouns.append(i.name)
            # What's visibly inside/on it -- accessible_contents is the
            # engine's own no-spoiler seam (CCB): closed holders yield
            # nothing, and hidden-until-SEARCH items stay off the bar
            # until the search actually reveals them. Recursive, matching
            # parser scope: an open jar on a plinth still offers its organ.
            nouns += _reachable_contents(i)
        nouns += [c.name for c in loc.characters.values() if c is not _game.player]
    for it in _game.player.carried_items().values():
        nouns.append(it.name)
        nouns += _reachable_contents(it)
    seen, deduped = set(), []
    for n in nouns:
        if n not in seen:
            seen.add(n)
            deduped.append(n)
    return {
        "verbs": VERBS,
        "nouns": deduped,
        "exits": sorted(loc.connections.keys()),
    }


_visited = set()


def _note_visited():
    if _game.player.location is not None:
        _visited.add(_game.player.location.name)


def _payload():
    _note_visited()
    return json.dumps(
        {"events": _events(), "status": _status(), "suggestions": _suggestions()}
    )


def panel_data():
    """The swipe panels (design: CCB): the INVENTORY as structure, and the
    MAP of explored rooms only -- nodes are rooms the player has stood in,
    arcs are their connections labeled with the direction of travel, and an
    exit into the unexplored shows as a stub to '?'. Replay-friendly: the
    visited set rebuilds from the journal on restore (rooms are re-stood-in)."""
    player = _game.player
    inventory = {
        "carried": [
            {"name": it.name, "description": it.description}
            for it in player.carried_items().values()
        ],
        "worn": [
            {"name": it.name, "description": it.description}
            for it in player.worn.values()
        ],
        "wounds": [
            {"name": w.name, "slots": w.slots, "description": w.description}
            for w in player.wounds
        ],
        "slots": (
            f"{player.slots_used()}/{player.slot_capacity}"
            if getattr(player, "slot_capacity", None)
            else None
        ),
    }
    here = player.location.name if player.location else None
    nodes = sorted(_visited)
    edges, stubs, seen_pairs = [], [], set()
    for name in nodes:
        room = _game.locations.get(name)
        if room is None:
            continue
        for direction, dest in room.connections.items():
            label = str(getattr(direction, "value", direction))
            if dest.name in _visited:
                pair = frozenset((name, dest.name))
                if pair in seen_pairs:
                    continue
                seen_pairs.add(pair)
                # Both sides of the passage, named exactly as each room
                # names it -- the canopic stairs go UP one way and RIGHT
                # STAIRS back, and the map's labels and click-to-walk
                # routes must use the word that actually parses. ``back``
                # is None for a one-way drop.
                back = dest.get_direction(room)
                back = str(getattr(back, "value", back)) if back else None
                edges.append(
                    {"from": name, "to": dest.name, "dir": label, "back": back}
                )
            else:
                stubs.append({"from": name, "dir": label})
    return json.dumps(
        {
            "inventory": inventory,
            "map": {"here": here, "nodes": nodes, "edges": edges, "stubs": stubs},
        }
    )


def boot(seed):
    """Build the Tomb (seeded) and return the opening scene's events."""
    global _game, _cap, _store, _pending_restart
    _pending_restart = False
    _game = tomb.build_game(seed=int(seed))
    _cap = CaptureRenderer()
    _game.parser.set_renderer(_cap)
    _store = _make_store()
    _game.save_store = _store
    _visited.clear()
    _game.show_figure("road")  # the Trail card opens every fresh expedition
    _game.parser.parse_command("look")
    return _payload()


RESTART_WORDS = {"restart", "reload", "new game", "start over", "begin anew"}


_pending_restart = False


def _do_restart():
    import time

    try:
        _store.clear("auto")
    except Exception:
        pass
    boot(int(time.time()) % 1000000)
    # boot()'s own payload (the look, the Trail card) is discarded above, so
    # re-cue the card for THIS response: a restart earns the title reel too.
    _game.show_figure("road", force=True)
    _game.parser.ok(
        "The sand takes the old story. A new expedition stands at the wreck."
    )
    return _payload()


def command(text):
    """One player turn. Owns the RESTORE contract, the every-turn autosave,
    and RESTART (confirmed with y/n -- CCB: an expedition should not die to
    a slipped word)."""
    global _game, _cap, _pending_restart
    t = str(text).strip().lower()
    if _pending_restart:
        _pending_restart = False
        if t in ("y", "yes"):
            return _do_restart()
        _game.parser.ok("The expedition continues.")
        return _payload()
    if t in RESTART_WORDS:
        _pending_restart = True
        _game.parser.ok(
            "Begin a new expedition? The one underway will be lost to the "
            "sand. (y / n)"
        )
        return _payload()
    _game.do_command(str(text))
    pending = getattr(_game, "pending_restore", None)
    if pending is not None:
        _game.pending_restore = None
        restored, drift = saves.restore(tomb.build_game, pending)
        _game = restored
        _rebuild_visited()
        _cap = CaptureRenderer()
        _game.parser.set_renderer(_cap)
        _game.save_store = _store
        if drift:
            _game.parser.ok(
                "This expedition was logged by an older tomb; the paths have "
                "shifted since, and the restore may not be faithful. The log "
                "itself survives (SCRIPT)."
            )
        _game.parser.ok(
            f"[restored: {_game.player.location.name}, turn {_game.turn}, "
            f"score {_game.score}/{_game.max_score}]"
        )
        _game.parser.parse_command("look")
    elif not _game.is_game_over():
        # The autosave slot: iOS may kill the process at any moment, and
        # backgrounding must never lose a turn (design §2).
        _store.write("auto", saves.snapshot(_game))
    return _payload()


def _rebuild_visited():
    """After a restore, recover the explored set by replaying the journal on
    a scratch build (deterministic, quiet, milliseconds)."""
    _visited.clear()
    scratch = tomb.build_game(seed=_game.rng_seed)
    _visited.add(scratch.player.location.name)
    from text_adventure_games.reporting import CaptureRenderer as _CR

    scratch.parser.set_renderer(_CR())
    for cmd in _game.journal:
        scratch.do_command(cmd)
        if scratch.player.location is not None:
            _visited.add(scratch.player.location.name)


def transcript():
    """The expedition log as text, for sharing."""
    lines = [f"TOMB OF NASSAK AN-RAH -- expedition log (seed {_game.rng_seed})"]
    lines += [f"> {c}" for c in _game.journal]
    return "\n".join(lines)
