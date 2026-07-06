import json
import os
import shutil
import subprocess
import sys

import block_furniture as bf

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.dirname(os.path.dirname(HERE))
SRC_MATRIX = os.path.join(REPO, "godot-generative-agents", "sim", "the_upenn", "matrix")
SRC_MAP = os.path.join(REPO, "godot-generative-agents", "maps", "upenn_core_urban.tmj")
W, H = 245, 279


def _tmj():
    with open(SRC_MAP) as fh:
        return json.load(fh)


def _collision():
    return (
        open(os.path.join(SRC_MATRIX, "maze", "collision_maze.csv"))
        .read()
        .strip()
        .split(", ")
    )


def _furniture_cells(tmj):
    cells = set()
    for layer in tmj["layers"]:
        if layer.get("type") == "tilelayer" and bf.is_solid_layer(layer["name"]):
            for i, g in enumerate(layer["data"]):
                if g:
                    cells.add(i)
    return cells


def _blank_collision(tmj):
    """All-zero collision: every cell walkable. Used by unit tests that need to
    verify sealing logic independent of the committed matrix state."""
    return ["0"] * (tmj["width"] * tmj["height"])


def test_furniture_cells_become_solid_with_empty_allowlist():
    tmj = _tmj()
    # use a blank collision so furniture cells are guaranteed walkable at the start
    coll = _blank_collision(tmj)
    new_coll, sealed = bf.solid_cells(tmj, coll, walkable_gids=set())
    fcells = _furniture_cells(tmj)
    assert sealed > 0
    for i in fcells:
        assert new_coll[i] == "1", f"furniture cell {i} not sealed"


def test_allowlisted_gid_stays_walkable():
    tmj = _tmj()
    # use a blank collision so furniture cells start as walkable
    coll = _blank_collision(tmj)
    # pick the most common furniture gid and allowlist it
    counts = bf.furniture_gid_counts(tmj)
    seat_gid, _ = counts.most_common(1)[0]
    # cells painted ONLY with seat_gid that were walkable before must stay walkable
    seat_cells = set()
    for layer in tmj["layers"]:
        if layer.get("type") == "tilelayer" and bf.is_solid_layer(layer["name"]):
            for i, g in enumerate(layer["data"]):
                if g and (g & bf.GID_MASK) == seat_gid and coll[i] == "0":
                    seat_cells.add(i)
    new_coll, _ = bf.solid_cells(tmj, coll, walkable_gids={seat_gid})
    for i in seat_cells:
        assert new_coll[i] == "0", f"allowlisted seat cell {i} was sealed"


def test_rug_cells_untouched():
    tmj, coll = _tmj(), _collision()
    # cells that have a furniture tile on top are legitimately sealed; only check
    # rug-only cells (no furniture layer covers them)
    furniture_cells = _furniture_cells(tmj)
    rug_cells = set()
    for layer in tmj["layers"]:
        if layer.get("type") == "tilelayer" and layer["name"].endswith("_rugs"):
            for i, g in enumerate(layer["data"]):
                if g and coll[i] == "0" and i not in furniture_cells:
                    rug_cells.add(i)
    new_coll, _ = bf.solid_cells(tmj, coll, walkable_gids=set())
    for i in rug_cells:
        assert new_coll[i] == "0", f"rug cell {i} was sealed"


def test_idempotent_via_cli(tmp_path):
    mdir = os.path.join(tmp_path, "matrix")
    shutil.copytree(SRC_MATRIX, mdir)
    tmap = os.path.join(tmp_path, "map.tmj")
    shutil.copy2(SRC_MAP, tmap)
    args = [
        sys.executable,
        os.path.join(HERE, "block_furniture.py"),
        "--tmj",
        tmap,
        "--matrix",
        mdir,
    ]
    subprocess.run(args, check=True, cwd=HERE)
    first = open(os.path.join(mdir, "maze", "collision_maze.csv")).read()
    subprocess.run(args, check=True, cwd=HERE)
    second = open(os.path.join(mdir, "maze", "collision_maze.csv")).read()
    assert first == second
