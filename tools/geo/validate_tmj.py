"""Validate the UPenn tmj against the generative-agents matrix (detect & report).

Compares the authored map (godot-generative-agents/maps/upenn_core_urban.tmj)
against the matrix the backend walks (sim/the_upenn/matrix): are the interior
rooms drawn in the tmj present in the matrix block map, do the ids follow the
add_entrances scheme, is the tmj internally well-formed? It never edits either
side -- it prints a grouped report and exits non-zero on un-baselined errors.

    uv run python tools/geo/validate_tmj.py            # human report
    uv run python tools/geo/validate_tmj.py --json     # findings as JSON
"""

from __future__ import annotations

import argparse
import json
import os
import re
from collections import Counter, defaultdict
from dataclasses import dataclass

from add_entrances import read_blocks, read_flat
from add_entrances import (  # noqa: E402  (grouped with other geo imports)
    INTERIOR_ARENA_BASE,
    ROOM_ARENA_BASE,
    ROOM_SUBDIVIDE,
    VAN_PELT,
)

GID_MASK = 0x1FFFFFFF  # strip Tiled's flip flags before range checks


@dataclass(frozen=True)
class Finding:
    severity: str  # "ok" | "info" | "warn" | "error"
    category: str  # "MATRIX_TMJ" | "INTEGRITY"
    building: str  # display name, or "" for map-wide
    code: str  # short stable code, used for baseline keying
    message: str


class World:
    """Everything both sides declare, loaded once."""

    def __init__(self, tmj_path: str, matrix_path: str):
        self.tmj = json.load(open(tmj_path))
        self.W = self.tmj["width"]
        self.H = self.tmj["height"]
        self.tile_layers = {
            l["name"]: l for l in self.tmj["layers"] if l.get("type") == "tilelayer"
        }
        self.object_groups = {
            l["name"]: l for l in self.tmj["layers"] if l.get("type") == "objectgroup"
        }
        self.tilesets = self.tmj.get("tilesets", [])
        maze = os.path.join(matrix_path, "maze")
        blocks = os.path.join(matrix_path, "special_blocks")
        self.collision = read_flat(os.path.join(maze, "collision_maze.csv"))
        self.arena = read_flat(os.path.join(maze, "arena_maze.csv"))
        self.sector = read_flat(os.path.join(maze, "sector_maze.csv"))
        self.arena_blocks = read_blocks(os.path.join(blocks, "arena_blocks.csv"))
        self.sector_blocks = read_blocks(os.path.join(blocks, "sector_blocks.csv"))
        self.world_blocks = read_blocks(os.path.join(blocks, "world_blocks.csv"))
        self.meta = json.load(open(os.path.join(matrix_path, "maze_meta_info.json")))

    def idx(self, x: int, y: int) -> int:
        return y * self.W + x


_DECOY_RE = re.compile(r"\b(rug|wall|brick)\b", re.IGNORECASE)


def is_decoy(name: str) -> bool:
    """tmj arena layers mix in decorative boxes (Rug, Brick Wall, Room 1: Wall);
    they are never rooms."""
    return bool(_DECOY_RE.search(name or ""))


def base_covered(obj_name: str, room_name: str) -> bool:
    """A tmj object 'covers' a matrix room if it is that room or a numbered
    fragment of it (Irvine 'Stage 1/2/3' -> matrix 'Stage')."""
    return obj_name == room_name or obj_name.startswith(room_name + " ")


def object_cells(obj: dict, W: int, H: int) -> set:
    x0 = int(obj["x"] // 16)
    y0 = int(obj["y"] // 16)
    x1 = int((obj["x"] + obj["width"] - 1) // 16)
    y1 = int((obj["y"] + obj["height"] - 1) // 16)
    return {
        (x, y)
        for y in range(max(0, y0), min(H - 1, y1) + 1)
        for x in range(max(0, x0), min(W - 1, x1) + 1)
    }


def sector_name_by_id(world: World) -> dict:
    return {r[0]: r[-1] for r in world.sector_blocks if len(r) >= 3}


def sector_id_by_name(world: World) -> dict:
    return {name: sid for sid, name in sector_name_by_id(world).items()}


def dominant_sector(cells: set, world: World) -> str:
    counts = Counter(
        world.sector[world.idx(x, y)]
        for (x, y) in cells
        if world.sector[world.idx(x, y)] != "0"
    )
    return counts.most_common(1)[0][0] if counts else "0"


def tmj_arenas_by_building(world: World) -> dict:
    names = sector_name_by_id(world)
    out = defaultdict(list)
    for layer_name, group in world.object_groups.items():
        if not layer_name.endswith("_arenas"):
            continue
        for obj in group.get("objects", []):
            nm = obj.get("name", "")
            if is_decoy(nm):
                continue
            cells = object_cells(obj, world.W, world.H)
            sid = dominant_sector(cells, world)
            building = names.get(sid, "")  # "" -> unresolved (flagged in check 11)
            out[building].append(
                {"name": nm, "layer": layer_name, "cells": cells, "dominant": sid}
            )
    return dict(out)


def matrix_rooms_by_building(world: World) -> dict:
    out = defaultdict(list)
    for row in world.arena_blocks:
        if len(row) < 4:
            continue
        aid, _world, sector, arena = row[0], row[1], row[2], row[3]
        if arena in ("grounds", "lobby"):
            continue
        out[sector].append({"id": aid, "name": arena})
    return dict(out)
