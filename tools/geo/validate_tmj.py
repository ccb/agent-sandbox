"""Validate the UPenn tmj against the generative-agents matrix (detect & report).

Compares the authored map (godot-generative-agents/godot/maps/upenn_core_urban.tmj)
against the matrix the backend walks (backend/penn/the_upenn/matrix): are the interior
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
from collections import Counter, defaultdict, deque
from dataclasses import dataclass

from add_entrances import (
    INTERIOR_ARENA_BASE,
    ROOM_ARENA_BASE,
    ROOM_SUBDIVIDE,
    VAN_PELT,
    read_blocks,
    read_flat,
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
        with open(tmj_path) as _f:
            self.tmj = json.load(_f)
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
        self.game_object = read_flat(os.path.join(maze, "game_object_maze.csv"))
        self.game_object_blocks = read_blocks(
            os.path.join(blocks, "game_object_blocks.csv")
        )
        with open(os.path.join(matrix_path, "maze_meta_info.json")) as _f:
            self.meta = json.load(_f)

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

    def _painted_arena_ids(self):
        return {a for a in self.w.arena if a != "0"}

    def _arena_row_by_id(self):
        return {r[0]: r for r in self.w.arena_blocks if len(r) >= 4}

    def check_orphan_block_rows(self):
        painted = self._painted_arena_ids()
        bad = [r for r in self.w.arena_blocks if len(r) >= 4 and r[0] not in painted]
        for r in bad:
            self.add(
                "error",
                "MATRIX_TMJ",
                r[2],
                "arena_block_unpainted",
                f"arena '{r[3]}' (id {r[0]}) declared but never painted in arena_maze",
            )
        if not bad:
            self.add(
                "ok",
                "MATRIX_TMJ",
                "",
                "arena_blocks_painted",
                "every arena_blocks row is painted in arena_maze",
            )

    def check_orphan_paint(self):
        known = {r[0] for r in self.w.arena_blocks if r}
        unknown = sorted(self._painted_arena_ids() - known, key=lambda s: int(s))
        for aid in unknown:
            self.add(
                "error",
                "MATRIX_TMJ",
                "",
                "arena_paint_unknown",
                f"arena id {aid} painted in arena_maze but absent from arena_blocks",
            )
        # sectors too
        known_s = {r[0] for r in self.w.sector_blocks if r}
        for sid in sorted(
            {s for s in self.w.sector if s != "0"} - known_s, key=lambda s: int(s)
        ):
            self.add(
                "error",
                "MATRIX_TMJ",
                "",
                "sector_paint_unknown",
                f"sector id {sid} painted but absent from sector_blocks",
            )
        if not unknown:
            self.add(
                "ok",
                "MATRIX_TMJ",
                "",
                "arena_paint_known",
                "every painted arena id has a block row",
            )

    def check_id_scheme(self):
        sids = sector_id_by_name(self.w)
        bad = False
        for r in self.w.arena_blocks:
            if len(r) < 4:
                continue
            aid, sector, arena = int(r[0]), r[2], r[3]
            sid = sids.get(sector)
            if sid is None:
                continue  # referential check reports the missing sector
            sid = int(sid)
            if arena == "grounds":
                expect_ok = aid == sid
            elif arena == "lobby":
                expect_ok = aid == INTERIOR_ARENA_BASE + sid
            else:  # room
                base = ROOM_ARENA_BASE + sid * 100
                expect_ok = base <= aid < base + 100
            if not expect_ok:
                self.add(
                    "error",
                    "MATRIX_TMJ",
                    sector,
                    "arena_id_scheme",
                    f"'{arena}' id {aid} breaks the id scheme for sector {sid}",
                )
                bad = True
        if not bad:
            self.add(
                "ok",
                "MATRIX_TMJ",
                "",
                "arena_id_scheme_ok",
                "all arena ids follow grounds/lobby/room scheme",
            )

    def check_region_containment(self):
        names = sector_name_by_id(self.w)
        sids = sector_id_by_name(self.w)
        rows = self._arena_row_by_id()
        by_arena = defaultdict(list)
        for i, aid in enumerate(self.w.arena):
            if aid != "0":
                by_arena[aid].append(i)
        bad = False
        for aid, idxs in by_arena.items():
            row = rows.get(aid)
            if not row:
                continue  # orphan-paint check owns this
            sid = sids.get(row[2])
            if sid is None:
                continue
            stray = [i for i in idxs if self.w.sector[i] != sid]
            if stray:
                x, y = stray[0] % self.w.W, stray[0] // self.w.W
                self.add(
                    "error",
                    "MATRIX_TMJ",
                    row[2],
                    "arena_region_outside_sector",
                    f"'{row[3]}' (id {aid}) paints {len(stray)} cell(s) off sector "
                    f"{sid}, e.g. ({x},{y})",
                )
                bad = True
        if not bad:
            self.add(
                "ok",
                "MATRIX_TMJ",
                "",
                "arena_region_contained",
                "room/lobby arenas stay within their sector",
            )

    def check_drawn_vs_present(self):
        tmj = tmj_arenas_by_building(self.w)
        mtx = matrix_rooms_by_building(self.w)
        buildings = set(tmj) | set(mtx)
        for b in sorted(x for x in buildings if x):  # skip "" (unresolved)
            drawn = tmj.get(b, [])
            rooms = mtx.get(b, [])
            if drawn and not rooms:
                layer = drawn[0]["layer"]
                wired = b in ROOM_SUBDIVIDE
                extra = "" if wired else " — not in add_entrances.ROOM_SUBDIVIDE"
                self.add(
                    "error",
                    "MATRIX_TMJ",
                    b,
                    "arena_drawn_not_in_matrix",
                    f"{len(drawn)} arena objects in tmj ({layer}) but 0 room "
                    f"arenas in matrix{extra}",
                )
            elif rooms and not drawn:
                if b == VAN_PELT:
                    self.add(
                        "info",
                        "MATRIX_TMJ",
                        b,
                        "arena_matrix_no_tmj_layer",
                        f"{len(rooms)} matrix rooms, no tmj arena layer "
                        f"(sourced from van_pelt_interior.json)",
                    )
                else:
                    self.add(
                        "error",
                        "MATRIX_TMJ",
                        b,
                        "arena_matrix_no_tmj_layer",
                        f"{len(rooms)} matrix rooms but no tmj arena layer",
                    )
            elif drawn and rooms:
                room_names = [r["name"] for r in rooms]
                uncovered = [
                    o["name"]
                    for o in drawn
                    if not any(base_covered(o["name"], rn) for rn in room_names)
                ]
                if uncovered:
                    self.add(
                        "warn",
                        "MATRIX_TMJ",
                        b,
                        "arena_name_uncovered",
                        f"{len(uncovered)} tmj arena name(s) match no matrix room: "
                        f"{', '.join(sorted(uncovered)[:5])}",
                    )
                else:
                    self.add(
                        "ok",
                        "MATRIX_TMJ",
                        b,
                        "arena_names_match",
                        f"{len(rooms)} matrix rooms all backed by a tmj arena object",
                    )

    def check_arena_layer_resolved(self):
        tmj = tmj_arenas_by_building(self.w)
        orphans = tmj.get("", [])
        for o in orphans:
            self.add(
                "error",
                "MATRIX_TMJ",
                "",
                "arena_layer_unresolved",
                f"arena object '{o['name']}' ({o['layer']}) sits over no building "
                f"(dominant sector {o['dominant']})",
            )

    COLLISION_TOLERANCE = 0.60  # share of wall-drawn cells left walkable before we warn

    def _wall_cells(self) -> tuple[set[int], str]:
        """Indices of cells drawn as walls, and where they came from.

        The per-building ``*_walls`` layers are the truth on the real map: once
        ``add_entrances`` opens a building it zeroes that building's footprint in
        the ``buildings`` layer, so the old ``buildings``-only read found nothing
        and the collision check was a silent no-op (issue #391). We union every
        ``*_walls`` layer instead. The legacy ``buildings`` layer is kept only as
        a fallback for maps/fixtures that predate the split (no ``*_walls`` at
        all), so synthetic tests still exercise the tolerance logic."""
        wall_layers = [n for n in self.w.tile_layers if n.endswith("_walls")]
        if wall_layers:
            cells: set[int] = set()
            for name in wall_layers:
                data = self.w.tile_layers[name].get("data", [])
                cells.update(i for i, tile in enumerate(data) if tile)
            return cells, "*_walls layers"
        buildings = self.w.tile_layers.get("buildings", {}).get("data", [])
        return {i for i, tile in enumerate(buildings) if tile}, "buildings layer"

    def check_collision_vs_walls(self):
        cells, source = self._wall_cells()
        names = sector_name_by_id(self.w)
        walkable = 0
        per_sector = defaultdict(lambda: [0, 0])  # sid -> [drawn, walkable]
        for i in cells:
            sid = self.w.sector[i]
            per_sector[sid][0] += 1
            if self.w.collision[i] == "0":
                walkable += 1
                per_sector[sid][1] += 1
        drawn = len(cells)
        if drawn == 0:
            self.add(
                "info",
                "MATRIX_TMJ",
                "",
                "collision_walls_ok",
                "no wall-drawn cells to check (no `*_walls` layers and an empty "
                "`buildings` layer) — collision check was a no-op",
            )
            return
        warned = False
        for sid, (d, wk) in sorted(per_sector.items()):
            if d and wk / d > self.COLLISION_TOLERANCE:
                self.add(
                    "warn",
                    "MATRIX_TMJ",
                    names.get(sid, f"sector {sid}"),
                    "collision_wall_gap",
                    f"{wk}/{d} wall-drawn cells are walkable in collision_maze "
                    f"({wk/d:.0%}) — verify walls/doors",
                )
                warned = True
        if not warned:
            self.add(
                "ok",
                "MATRIX_TMJ",
                "",
                "collision_walls_ok",
                f"wall-drawn cells largely stay solid in collision_maze "
                f"({walkable}/{drawn} walkable overall, from {source})",
            )

    def check_furniture_solidity(self):
        """Every *_furniture cell must be collision=1 unless its base gid is in
        block_furniture.WALKABLE_FURNITURE (chair seats). Lock-step: the matrix
        must equal what block_furniture produces from the tmj.

        NOTE: this check is one-directional. It flags furniture that should be
        solid but isn't; it does NOT flag an allowlisted cell that is still
        solid. block_furniture.solid_cells only seals (walkable->wall), never
        re-opens, so adding a gid to WALKABLE_FURNITURE and re-running
        block_furniture alone leaves already-sealed cells solid. Regenerate from
        a furniture-free collision baseline (the full add_entrances -> block_grass
        -> block_furniture chain) after any allowlist addition."""
        try:
            import block_furniture as bf
        except Exception as exc:  # pragma: no cover - defensive
            self.add(
                "warn",
                "MATRIX_TMJ",
                "",
                "furniture-import",
                f"could not import block_furniture: {exc}",
            )
            return
        bad = 0
        for layer in self.w.tmj["layers"]:
            if layer.get("type") != "tilelayer" or not bf.is_solid_layer(layer["name"]):
                continue
            for i, g in enumerate(layer["data"]):
                if not g or (g & bf.GID_MASK) in bf.WALKABLE_FURNITURE:
                    continue
                if self.w.collision[i] != "1":
                    bad += 1
        if bad:
            self.add(
                "error",
                "MATRIX_TMJ",
                "",
                "furniture-not-solid",
                f"{bad} furniture tile cells are not solid in collision_maze "
                f"(run block_furniture.py)",
            )
        else:
            self.add(
                "ok",
                "MATRIX_TMJ",
                "",
                "furniture-solid",
                "all *_furniture cells are solid (or allowlisted)",
            )

    def check_walkable_allowlist_fresh(self):
        """Warn on any WALKABLE_FURNITURE gid no longer painted in a furniture
        layer -- the art changed out from under the allowlist."""
        try:
            import block_furniture as bf
        except Exception:  # pragma: no cover - defensive
            return
        present = set(bf.furniture_gid_counts(self.w.tmj))
        stale = sorted(g for g in bf.WALKABLE_FURNITURE if g not in present)
        for gid in stale:
            self.add(
                "warn",
                "MATRIX_TMJ",
                "",
                "allowlist-stale",
                f"WALKABLE_FURNITURE gid {gid} is not painted in any furniture layer",
            )

    def check_game_object_orphans(self):
        """Both directions: every game_object_blocks row has >=1 painted cell,
        and every painted game_object id has a block row."""
        painted = {g for g in self.w.game_object if g != "0"}
        row_ids = {r[0] for r in self.w.game_object_blocks}
        for rid in sorted(row_ids - painted):
            self.add(
                "error",
                "MATRIX_TMJ",
                "",
                "gobj-orphan-row",
                f"game_object_blocks id {rid} has no painted cell",
            )
        for pid in sorted(painted - row_ids):
            self.add(
                "error",
                "MATRIX_TMJ",
                "",
                "gobj-orphan-paint",
                f"game_object id {pid} painted but has no block row",
            )
        if not (row_ids - painted) and not (painted - row_ids):
            self.add(
                "ok",
                "MATRIX_TMJ",
                "",
                "gobj-orphans",
                f"{len(row_ids)} game objects: rows and paint agree",
            )

    def check_game_object_use_tiles_walkable(self):
        """Every cell carrying a game_object id must be walkable (collision=0)."""
        bad = [
            i
            for i, g in enumerate(self.w.game_object)
            if g != "0" and self.w.collision[i] != "0"
        ]
        if bad:
            self.add(
                "error",
                "MATRIX_TMJ",
                "",
                "gobj-use-tile-sealed",
                f"{len(bad)} game_object use-tiles are not walkable",
            )

    def check_game_object_containment(self):
        """Each game object's cells must lie in a single (non-zero) arena."""
        by_id = defaultdict(set)
        for i, g in enumerate(self.w.game_object):
            if g != "0":
                by_id[g].add(self.w.arena[i])
        for gid, arenas in sorted(by_id.items()):
            if "0" in arenas or len(arenas) != 1:
                self.add(
                    "error",
                    "MATRIX_TMJ",
                    "",
                    "gobj-containment",
                    f"game object {gid} spans arenas {sorted(arenas)} "
                    f"(must be exactly one non-zero arena)",
                )

    def check_game_object_reachable(self):
        """Every game_object use-tile must be BFS-reachable over collision from a
        map-border walkable cell."""
        goal = {i for i, g in enumerate(self.w.game_object) if g != "0"}
        if not goal:
            return
        reached = self._flood_from_border()
        stuck = sorted(goal - reached)
        if stuck:
            self.add(
                "error",
                "MATRIX_TMJ",
                "",
                "gobj-unreachable",
                f"{len(stuck)} game_object use-tiles are unreachable",
            )

    def _flood_from_border(self):
        W, H, coll = self.w.W, self.w.H, self.w.collision
        seen = [False] * (W * H)
        q = deque()
        for x in range(W):
            for y in (0, H - 1):
                i = y * W + x
                if coll[i] == "0" and not seen[i]:
                    seen[i] = True
                    q.append((x, y))
        for y in range(H):
            for x in (0, W - 1):
                i = y * W + x
                if coll[i] == "0" and not seen[i]:
                    seen[i] = True
                    q.append((x, y))
        while q:
            x, y = q.popleft()
            for dx, dy in ((1, 0), (-1, 0), (0, 1), (0, -1)):
                nx, ny = x + dx, y + dy
                if 0 <= nx < W and 0 <= ny < H:
                    j = ny * W + nx
                    if coll[j] == "0" and not seen[j]:
                        seen[j] = True
                        q.append((nx, ny))
        return {i for i, s in enumerate(seen) if s}

    def run(self):
        self.check_orphan_block_rows()
        self.check_orphan_paint()
        self.check_id_scheme()
        self.check_region_containment()
        self.check_gids_resolve()
        self.check_dimensions()
        self.check_arena_rects_and_names()
        self.check_referential_integrity()
        self.check_drawn_vs_present()
        self.check_arena_layer_resolved()
        self.check_collision_vs_walls()
        self.check_furniture_solidity()
        self.check_walkable_allowlist_fresh()
        self.check_game_object_orphans()
        self.check_game_object_use_tiles_walkable()
        self.check_game_object_containment()
        self.check_game_object_reachable()
        return self


_SEV_ORDER = {"error": 0, "warn": 1, "info": 2, "ok": 3}


def format_report(findings: list[Finding]) -> str:
    lines = []
    for cat in ("MATRIX_TMJ", "INTEGRITY"):
        group = [f for f in findings if f.category == cat]
        if not group:
            continue
        lines.append(f"== {cat} ==")
        for f in sorted(
            group, key=lambda f: (_SEV_ORDER.get(f.severity, 99), f.building, f.code)
        ):
            who = f" {f.building}:" if f.building else ""
            lines.append(f"  [{f.severity:>5}]{who} {f.message}")
    counts = Counter(f.severity for f in findings)
    summary = " · ".join(
        f"{counts.get(s, 0)} {s}" for s in ("ok", "info", "warn", "error")
    )
    lines.append("")
    lines.append(summary)
    return "\n".join(lines)


def _load_baseline(path):
    if path and os.path.exists(path):
        with open(path) as _f:
            return {tuple(e) for e in json.load(_f)}
    return set()


def main(argv=None) -> int:
    here = os.path.dirname(os.path.abspath(__file__))
    repo = os.path.dirname(os.path.dirname(here))
    ap = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    ap.add_argument(
        "--tmj",
        default=os.path.join(
            repo, "godot-generative-agents", "godot", "maps", "upenn_core_urban.tmj"
        ),
    )
    ap.add_argument(
        "--matrix",
        default=os.path.join(
            repo, "godot-generative-agents", "backend", "penn", "the_upenn", "matrix"
        ),
    )
    ap.add_argument(
        "--baseline", default=os.path.join(here, "validate_tmj_baseline.json")
    )
    ap.add_argument("--json", action="store_true", help="emit findings as JSON")
    args = ap.parse_args(argv)

    checker = Checker(World(args.tmj, args.matrix)).run()
    if args.json:
        print(json.dumps([f.__dict__ for f in checker.findings], indent=2))
    else:
        print(format_report(checker.findings))
    baseline = _load_baseline(args.baseline)
    new_errors = [
        f for f in checker.errors() if (f.category, f.building, f.code) not in baseline
    ]
    return 1 if new_errors else 0


if __name__ == "__main__":
    raise SystemExit(main())
