"""The web terminal's Python half (app/app_api.py, design §1.1).

app_api runs identically under plain CPython and Pyodide (the save store is
the only environment-sensitive piece, and it falls back to memory off-browser),
so everything except the WASM loader itself is testable here. The WASM run was
verified end-to-end via Node + pyodide (win route 100/100); the loader-level
guard we keep in CI is the blocked-imports audit -- the wheel must never grow
a hard dependency on the heavy packages Pyodide won't have.
"""

import json
import os
import subprocess
import sys

_REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(_REPO, "app"))

import app_api  # noqa: E402
from text_adventure_games.adventures import tomb_of_nassak_an_rah as tomb  # noqa: E402


def test_boot_returns_the_opening_scene():
    payload = json.loads(app_api.boot(0))
    assert payload["status"]["room"] == "The Caravan Wreck"
    assert payload["status"]["score"] == 0
    assert any("wreck" in e["text"].lower() for e in payload["events"])
    assert "north" in payload["suggestions"]["exits"]
    assert "wreck" in payload["suggestions"]["nouns"]


def test_the_win_route_plays_through_the_bridge():
    app_api.boot(0)
    last = None
    for cmd in tomb.WIN_WALKTHROUGH:
        last = json.loads(app_api.command(cmd))
        if last["status"]["game_over"]:
            break
    assert last["status"]["won"]
    assert last["status"]["score"] == last["status"]["max_score"] == 170


def test_events_carry_channels_not_prose_parsing():
    app_api.boot(0)
    payload = json.loads(app_api.command("frobnicate"))
    assert any(e["channel"] == "blocked" for e in payload["events"])


def test_suggestions_thin_out_in_the_dark():
    """Perception-honest UI: in a dark room the visible-noun well runs dry --
    only inventory (and exits) remain on the bar."""
    app_api.boot(0)
    game = app_api._game
    dark = game.locations["Hall of Youth"]
    game.relocate(game.player, dark)
    sug = json.loads(app_api.command("wait"))["suggestions"]
    room_only_nouns = [n for n in sug["nouns"] if n not in game.player.carried_items()]
    assert room_only_nouns == []  # nothing of the room is offered unseen


def test_revealed_contents_join_the_chips_only_once_seen():
    """Items inside things reach the noun chips exactly when the player could
    reach them -- after the SEARCH or OPEN that reveals them, never before
    (CCB: early chips are spoilers)."""
    app_api.boot(0)
    sug = json.loads(app_api.command("look"))["suggestions"]
    assert "glowstone" not in sug["nouns"]  # still hidden on the merchant
    sug = json.loads(app_api.command("search merchant"))["suggestions"]
    assert "glowstone" in sug["nouns"]  # the search revealed it
    assert "waterskin" in sug["nouns"]
    for cmd in ("take glowstone", "light glowstone", "in"):
        sug = json.loads(app_api.command(cmd))["suggestions"]
    assert "crates" in sug["nouns"]  # the lit hold shows the crates...
    assert "crate of dates" not in sug["nouns"]  # ...but not inside them
    sug = json.loads(app_api.command("open crates"))["suggestions"]
    assert "crate of dates" in sug["nouns"]  # opening reveals the goods
    assert "bolt of spider-silk" in sug["nouns"]


def test_restore_flows_through_the_bridge():
    """command() owns the RESTORE contract: SAVE 1, move on, RESTORE 1 -- the
    payload after the restore is back at the save point."""
    app_api.boot(41)
    app_api.command("look")
    app_api.command("save 1")
    moved = json.loads(app_api.command("go north"))
    assert moved["status"]["room"] != "The Caravan Wreck"
    back = json.loads(app_api.command("restore 1"))
    assert back["status"]["room"] == "The Caravan Wreck"
    assert back["status"]["turn"] == 1
    assert any("restored" in e["text"] for e in back["events"])


def test_every_turn_autosaves():
    app_api.boot(2)
    app_api.command("look")
    auto = app_api._store.read("auto")
    assert auto is not None and auto["commands"] == ["look"]
    app_api.command("go north")
    assert app_api._store.read("auto")["commands"] == ["look", "go north"]


def test_transcript_is_shareable_text():
    app_api.boot(3)
    app_api.command("look")
    app_api.command("go north")
    text = app_api.transcript()
    assert "seed 3" in text and "> go north" in text


def test_panel_data_maps_only_the_explored():
    """The swipe-left map (CCB): nodes are rooms the player has stood in,
    arcs carry the direction of travel, unexplored exits are stubs -- and
    nothing beyond the frontier leaks (no spoiler room names)."""
    app_api.boot(0)
    for cmd in ("north", "up"):
        app_api.command(cmd)
    data = json.loads(app_api.panel_data())
    m = data["map"]
    assert set(m["nodes"]) == {"The Caravan Wreck", "Tomb Exterior", "The Summit"}
    assert {
        "from": "The Caravan Wreck",
        "to": "Tomb Exterior",
        "dir": "north",
        "back": "south",
    } in m["edges"]
    assert m["here"] == "The Summit"
    assert any(st["dir"] == "in" for st in m["stubs"])  # the unexplored beckons
    all_names = " ".join(m["nodes"])
    assert "Hall of" not in all_names  # frontier rooms stay unspoiled


def test_map_edges_name_both_sides_of_a_passage():
    """Tap-to-walk needs the word each SIDE answers to (CCB: the map's
    routes must parse): the canopic stairs are RIGHT STAIRS going down but
    UP coming back, and the edge carries both."""
    app_api.boot(0)
    for cmd in (
        "search merchant",
        "take glowstone",
        "light glowstone",
        "north",
        "north",
        "north",
        "up",
        "right stairs",
    ):
        app_api.command(cmd)
    m = json.loads(app_api.panel_data())["map"]
    stairs = [
        e
        for e in m["edges"]
        if {e["from"], e["to"]} == {"Hall of the Canopic Jars", "Hall of Hounds"}
    ]
    assert len(stairs) == 1
    e = stairs[0]
    names = {e["dir"], e["back"]}
    assert "right stairs" in names and "up" in names  # asymmetric, both real


def test_panel_data_inventory_shape():
    app_api.boot(0)
    app_api.command("search merchant")
    app_api.command("take glowstone")
    data = json.loads(app_api.panel_data())
    inv = data["inventory"]
    assert any(i["name"] == "glowstone" for i in inv["carried"])
    assert inv["slots"] == "1/10"
    assert inv["wounds"] == []


def test_restore_rebuilds_the_explored_map():
    app_api.boot(5)
    for cmd in ("north", "save 1", "up"):
        app_api.command(cmd)
    app_api.command("restore 1")  # back to the exterior
    m = json.loads(app_api.panel_data())["map"]
    assert m["here"] == "Tomb Exterior"
    assert "The Caravan Wreck" in m["nodes"]  # the journey survived the rebuild


def test_the_dead_cannot_walk_but_can_restart():
    """Post-mortem, the bridge refuses world commands (engine gate) while
    the app-level RESTART confirmation still works."""
    app_api.boot(0)
    app_api._game.player.set_property("is_dead", True)
    payload = json.loads(app_api.command("go north"))
    assert payload["status"]["game_over"]
    assert any(e["channel"] == "blocked" for e in payload["events"])
    assert payload["status"]["room"] == "The Caravan Wreck"  # unmoved
    payload = json.loads(app_api.command("restart"))
    assert any("Begin a new expedition?" in e["text"] for e in payload["events"])
    payload = json.loads(app_api.command("y"))
    assert not payload["status"]["game_over"]  # a fresh expedition stands


def test_restart_begins_a_fresh_expedition():
    """CCB: 'reload' at the death screen did nothing. RESTART (and its
    aliases) now boots a new seed and clears the autosave, so the title
    screen doesn't offer the dead past back."""
    app_api.boot(0)
    app_api.command("north")
    assert app_api._store.read("auto") is not None
    ask = json.loads(app_api.command("restart"))
    assert any("(y / n)" in e["text"] for e in ask["events"])  # confirmed first
    assert ask["status"]["turn"] == 1  # nothing lost yet
    stay = json.loads(app_api.command("n"))
    assert any("continues" in e["text"] for e in stay["events"])
    assert stay["status"]["room"] == "Tomb Exterior"  # unharmed
    app_api.command("restart")
    payload = json.loads(app_api.command("y"))
    assert payload["status"]["turn"] == 0
    assert payload["status"]["room"] == "The Caravan Wreck"
    assert app_api._store.read("auto") is None
    assert any("new expedition" in e["text"] for e in payload["events"])


_AUDIT = r"""
import sys
from importlib.abc import MetaPathFinder

BLOCKED = ("rich", "jinja2", "prompty", "flask", "yaml", "graphviz", "jupyter")

class Blocker(MetaPathFinder):
    def find_spec(self, name, path=None, target=None):
        if name.split(".")[0] in BLOCKED:
            raise ImportError("[blocked for pyodide-audit] " + name)

sys.meta_path.insert(0, Blocker())
for m in list(sys.modules):
    if m.split(".")[0] in BLOCKED:
        del sys.modules[m]

sys.path.insert(0, {repo!r})
sys.path.insert(0, {app!r})
import json
import app_api
from text_adventure_games.adventures.tomb_of_nassak_an_rah import WIN_WALKTHROUGH

app_api.boot(0)
last = None
for c in WIN_WALKTHROUGH:
    last = json.loads(app_api.command(c))
    if last["status"]["game_over"]:
        break
assert last["status"]["won"], "win route failed under blocked imports"
print("AUDIT-OK")
"""


def test_the_wheel_needs_no_heavy_imports():
    """The Pyodide contract (design §4): the engine + bridge must play the
    whole game with rich/jinja2/prompty/flask/yaml/graphviz unimportable.
    A new hard dependency on any of them breaks the app -- loudly, here."""
    script = _AUDIT.format(repo=_REPO, app=os.path.join(_REPO, "app"))
    result = subprocess.run(
        [sys.executable, "-c", script], capture_output=True, text=True
    )
    assert "AUDIT-OK" in result.stdout, result.stderr[-2000:]
