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
    assert last["status"]["score"] == last["status"]["max_score"] == 100


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
    assert {"from": "The Caravan Wreck", "to": "Tomb Exterior", "dir": "north"} in m[
        "edges"
    ]
    assert m["here"] == "The Summit"
    assert any(st["dir"] == "in" for st in m["stubs"])  # the unexplored beckons
    all_names = " ".join(m["nodes"])
    assert "Hall of" not in all_names  # frontier rooms stay unspoiled


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
