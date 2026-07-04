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


class Checker:
    def __init__(self, world: World):
        self.w = world
        self.findings: list[Finding] = []

    def add(self, severity, category, building, code, message):
        self.findings.append(Finding(severity, category, building, code, message))

    def errors(self):
        return [f for f in self.findings if f.severity == "error"]

    # ---- tmj internal integrity -------------------------------------------- #
    def _gid_ranges(self):
        return [
            (ts["firstgid"], ts["firstgid"] + ts.get("tilecount", 0))
            for ts in self.w.tilesets
            if "tilecount" in ts
        ]

    def check_gids_resolve(self):
        ranges = self._gid_ranges()
        bad = 0
        total = 0
        for layer in self.w.tile_layers.values():
            for raw in layer.get("data", []):
                gid = raw & GID_MASK
                if gid == 0:
                    continue
                total += 1
                if not any(lo <= gid < hi for lo, hi in ranges):
                    bad += 1
        if bad:
            self.add(
                "error",
                "INTEGRITY",
                "",
                "gid_out_of_range",
                f"{bad} tile gids resolve to no tileset",
            )
        else:
            self.add(
                "ok",
                "INTEGRITY",
                "",
                "gids_resolve",
                f"all {total} non-empty tiles resolve to a tileset",
            )

    def check_dimensions(self):
        W, H, N = self.w.W, self.w.H, self.w.W * self.w.H
        bad = False
        for name, layer in self.w.tile_layers.items():
            if len(layer.get("data", [])) != N:
                self.add(
                    "error",
                    "INTEGRITY",
                    "",
                    "layer_dim_mismatch",
                    f"tile layer '{name}' has {len(layer['data'])} cells, want {N}",
                )
                bad = True
        for name, arr in (
            ("collision", self.w.collision),
            ("arena", self.w.arena),
            ("sector", self.w.sector),
        ):
            if len(arr) != N:
                self.add(
                    "error",
                    "INTEGRITY",
                    "",
                    "maze_len_mismatch",
                    f"{name}_maze has {len(arr)} cells, want {N}",
                )
                bad = True
        if self.w.meta.get("maze_width") != W or self.w.meta.get("maze_height") != H:
            self.add(
                "error",
                "INTEGRITY",
                "",
                "meta_dim_mismatch",
                f"meta {self.w.meta.get('maze_width')}x{self.w.meta.get('maze_height')} "
                f"!= tmj {W}x{H}",
            )
            bad = True
        if not bad:
            self.add(
                "ok",
                "INTEGRITY",
                "",
                "dimensions",
                f"all layers & maze arrays are {N} cells; meta matches {W}x{H}",
            )

    def check_arena_rects_and_names(self):
        names = sector_name_by_id(self.w)
        for layer_name, group in self.w.object_groups.items():
            if not layer_name.endswith("_arenas"):
                continue
            seen = defaultdict(int)
            for obj in group.get("objects", []):
                nm = obj.get("name", "")
                if is_decoy(nm):
                    continue
                cells = object_cells(obj, self.w.W, self.w.H)
                sid = dominant_sector(cells, self.w)
                # any cell landing on a different, non-zero sector = bleed
                bleed = {
                    self.w.sector[self.w.idx(x, y)]
                    for (x, y) in cells
                    if self.w.sector[self.w.idx(x, y)] not in ("0", sid)
                }
                if bleed:
                    self.add(
                        "error",
                        "INTEGRITY",
                        names.get(sid, layer_name),
                        "arena_rect_out_of_footprint",
                        f"'{nm}' ({layer_name}) spills into sector(s) {sorted(bleed)}",
                    )
                seen[nm] += 1
            for nm, n in seen.items():
                if n > 1:
                    self.add(
                        "warn",
                        "INTEGRITY",
                        layer_name,
                        "arena_name_duplicate",
                        f"'{nm}' appears {n}x in {layer_name}",
                    )

    def check_referential_integrity(self):
        sectors = {r[-1] for r in self.w.sector_blocks if len(r) >= 3}
        worlds = {r[-1] for r in self.w.world_blocks if len(r) >= 2}
        ok = True
        for r in self.w.arena_blocks:
            if len(r) >= 4 and r[2] not in sectors:
                self.add(
                    "error",
                    "MATRIX_TMJ",
                    r[2],
                    "arena_sector_unknown",
                    f"arena_blocks row {r[0]} names sector '{r[2]}' absent from sector_blocks",
                )
                ok = False
        for r in self.w.sector_blocks:
            if len(r) >= 3 and r[1] not in worlds:
                self.add(
                    "error",
                    "INTEGRITY",
                    r[-1],
                    "sector_world_unknown",
                    f"sector_blocks row {r[0]} names world '{r[1]}' absent from world_blocks",
                )
                ok = False
        if ok:
            self.add(
                "ok",
                "INTEGRITY",
                "",
                "referential_integrity",
                "arena/sector/world block tables are internally consistent",
            )

    def run(self):
        self.check_gids_resolve()
        self.check_dimensions()
        self.check_arena_rects_and_names()
        self.check_referential_integrity()
        return self
