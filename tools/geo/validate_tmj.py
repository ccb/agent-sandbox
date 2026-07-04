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
