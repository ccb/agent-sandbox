"""Tests for the shared Tiled-map writer (#641)."""

import json
import os
import shutil
import subprocess
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


def test_write_tmj_returns_backup_path_only_on_first_run(tmp_path):
    """First-run-wins: write_tmj returns the .bak path when it takes a backup,
    None on a re-run -- so a caller's log doesn't falsely claim a fresh backup."""
    p = tmp_path / "map.tmj"
    p.write_text("seed")
    assert tmj_io.write_tmj(str(p), _fixture()) == str(p) + ".bak"
    # second run: .bak already exists, so no backup is taken this call
    assert tmj_io.write_tmj(str(p), _fixture()) is None


def test_dump_tiled_indents_nested_bare_dict_value():
    """A bare dict-valued property (e.g. Tiled's tileoffset on a tileset) must
    round-trip exactly and stay pretty: its keys nest one level deeper than
    the parent key, and its closing brace sits at the parent's indent -- not
    at column 0 (#641 review fix)."""
    fx = _fixture()
    fx["tilesets"] = [{"name": "t", "firstgid": 1, "tileoffset": {"x": 0, "y": -8}}]

    out = tmj_io.dump_tiled(fx)
    assert json.loads(out) == fx

    lines = out.splitlines()
    tileoffset_idx = next(i for i, l in enumerate(lines) if '"tileoffset":{' in l)
    tileoffset_indent = len(lines[tileoffset_idx]) - len(
        lines[tileoffset_idx].lstrip(" ")
    )
    x_line = lines[tileoffset_idx + 1]
    assert '"x":0' in x_line
    x_indent = len(x_line) - len(x_line.lstrip(" "))
    assert x_indent > tileoffset_indent, "nested dict keys must indent deeper"

    close_line = lines[tileoffset_idx + 3]
    assert close_line.strip() == "}"
    assert close_line != "}", "nested dict's closing brace must not sit at column 0"


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


def test_committed_map_is_serializer_canonical():
    """After the one-time reformat, the committed map is byte-identical to
    dump_tiled of itself -- so a script re-run changes only the cells it edits."""
    text = open(COMMITTED_TMJ).read()
    assert tmj_io.dump_tiled(json.loads(text)) == text


def test_furnish_script_output_stays_pretty(tmp_path):
    """Issue #641 bullet 3: run a furnish script on a copy of the committed map
    and assert the result is pretty (has newlines, not minified) and stable
    under re-serialization (already in canonical form)."""
    dst = tmp_path / "map.tmj"
    shutil.copy2(COMMITTED_TMJ, dst)
    matrix = os.path.join(GGA, "backend", "penn", "the_upenn", "matrix")
    r = subprocess.run(
        [
            sys.executable,
            os.path.join(HERE, "furnish_van_pelt.py"),
            "--tmj",
            str(dst),
            "--matrix",
            matrix,
        ],
        capture_output=True,
        text=True,
    )
    assert r.returncode == 0, r.stderr
    text = dst.read_text()
    assert text.count("\n") > 1000, "output was minified"
    # canonical/stable: re-serializing the written file is a no-op
    assert tmj_io.dump_tiled(json.loads(text)) == text
    # first-run-wins backup exists and is the pristine committed map
    assert open(str(dst) + ".bak").read() == open(COMMITTED_TMJ).read()
