"""Tests for the shared Tiled-map writer (#641)."""

import json
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
# tools/geo -> godot-generative-agents
GGA = os.path.dirname(os.path.dirname(HERE))
COMMITTED_TMJ = os.path.join(GGA, "godot", "maps", "upenn_core_urban.tmj")

import tmj_io


def _fixture():
    """A tiny 3x2 map with one tile layer and one object layer."""
    return {
        "width": 3,
        "height": 2,
        "infinite": False,
        "type": "map",
        "layers": [
            {
                "type": "tilelayer",
                "name": "ground",
                "id": 1,
                "width": 3,
                "height": 2,
                "x": 0,
                "y": 0,
                "opacity": 1,
                "visible": True,
                "data": [1, 2, 3, 4, 5, 6],
            },
            {
                "type": "objectgroup",
                "name": "arenas",
                "id": 2,
                "draworder": "topdown",
                "x": 0,
                "y": 0,
                "opacity": 1,
                "visible": True,
                "objects": [
                    {
                        "id": 10,
                        "name": "Room",
                        "type": "classroom",
                        "x": 16,
                        "y": 32,
                        "width": 48.5,
                        "height": 64,
                        "rotation": 0,
                        "opacity": 1,
                        "visible": True,
                    }
                ],
            },
        ],
    }


def test_dump_tiled_is_not_minified():
    out = tmj_io.dump_tiled(_fixture())
    assert "\n" in out, "output must be pretty (contain newlines)"
    # data wrapped one map-row (width=3) per line: two rows -> the array spans lines
    assert "[1, 2, 3,\n" in out


def test_dump_tiled_round_trips_semantically():
    fx = _fixture()
    assert json.loads(tmj_io.dump_tiled(fx)) == fx


def test_dump_tiled_is_idempotent():
    fx = _fixture()
    once = tmj_io.dump_tiled(fx)
    twice = tmj_io.dump_tiled(json.loads(once))
    assert once == twice


def test_backup_once_first_run_wins(tmp_path):
    p = tmp_path / "map.tmj"
    p.write_text("original")
    bak = tmj_io.backup_once(str(p))
    assert bak == str(p) + ".bak"
    assert os.path.exists(bak)
    assert open(bak).read() == "original"
    # a second run must NOT clobber the pristine backup
    p.write_text("mutated")
    assert tmj_io.backup_once(str(p)) is None
    assert open(bak).read() == "original"


def test_write_tmj_writes_pretty_and_backs_up(tmp_path):
    p = tmp_path / "map.tmj"
    p.write_text("seed")
    tmj_io.write_tmj(str(p), _fixture())
    text = p.read_text()
    assert "\n" in text
    assert json.loads(text) == _fixture()
    assert open(str(p) + ".bak").read() == "seed"


def test_committed_map_round_trips_semantically():
    """dump_tiled preserves the committed map's content exactly (formatting
    aside) and keeps it pretty -- not minified, not element-per-line exploded."""
    tmj = json.load(open(COMMITTED_TMJ))
    out = tmj_io.dump_tiled(tmj)
    assert json.loads(out) == tmj
    committed_lines = open(COMMITTED_TMJ).read().count("\n")
    assert (
        abs(out.count("\n") - committed_lines) <= 5
    ), "serializer format drifted far from the committed Tiled layout"
