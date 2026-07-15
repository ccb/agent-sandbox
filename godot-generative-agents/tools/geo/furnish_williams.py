#!/usr/bin/env python3
"""Wire Williams Hall's already-painted rooms into the matrix: read the
`williams_arenas` object layer, relayer walls/windows onto `williams_walls`, and
provide the room rects + wall cells `add_entrances` subdivides from. The floor
and furniture art already exist (furnish_building.py) -- this does NOT repaint.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import shutil
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import furnish_building as fb

GID_MASK = 0x1FFFFFFF
WALL_GID = fb.WALL  # wall_brick (543)
WINDOW_GID = fb.WINDOW  # window 4-pane (737)
FLOOR_GID = fb.FLOOR  # floor_wood_light


def _group(name):
    """Room-group name: boxes differing only by a trailing number are one room
    ('Classroom B 1'/'Classroom B 2' -> 'Classroom B'). Mirrors furnish_irvine."""
    return re.sub(r"\s*\d+$", "", name).strip() or name


def _arenas_layer(tmj):
    return next(
        (
            L
            for L in tmj["layers"]
            if L.get("name") == "williams_arenas" and L.get("type") == "objectgroup"
        ),
        None,
    )


def _arena_objects(tmj):
    """Objects to splice into williams_arenas. The authored layer is the source
    of truth (edited in Tiled, checked in), so when it exists we re-emit its own
    objects. WILLIAMS_ARENA_OBJECTS is only a seed for a fresh bake that has no
    arenas layer yet (see #552)."""
    layer = _arenas_layer(tmj)
    if layer and layer.get("objects"):
        return layer["objects"]
    return WILLIAMS_ARENA_OBJECTS


def read_sections(tmj):
    """name -> (c0,r0,c1,r1) inclusive tile rect, from the williams_arenas object
    layer (px/16 rounded, same idiom as furnish_college_hall.read_sections)."""
    layer = _arenas_layer(tmj)
    secs = {}
    if not layer:
        return secs
    for o in layer["objects"]:
        name = o.get("name") or ""
        if not name:
            continue
        c0 = round(o["x"] / 16)
        r0 = round(o["y"] / 16)
        c1 = round((o["x"] + o["width"]) / 16) - 1
        r1 = round((o["y"] + o["height"]) / 16) - 1
        secs[name] = (c0, r0, c1, r1)
    return secs


def grouped_sections(tmj):
    """Merge numbered sub-boxes into one bbox per group (Irvine idiom) and drop
    the `Lobby*` group -- those cells stay the lobby arena (the general-seating
    atrium), like furnish_college_hall drops `rug` objects."""
    groups = {}
    for nm, (c0, r0, c1, r1) in read_sections(tmj).items():
        g = _group(nm)
        if g == "Lobby":
            continue
        if g in groups:
            a, b, cc, dd = groups[g]
            groups[g] = (min(a, c0), min(b, r0), max(cc, c1), max(dd, r1))
        else:
            groups[g] = (c0, r0, c1, r1)
    return groups


def _tile_layers(tmj):
    return {L["name"]: L for L in tmj["layers"] if L.get("type") == "tilelayer"}


def compute_relayer(tmj):
    """Return (new_walls, new_floor, new_furn) flat gid arrays: move wall_brick
    off williams_floor and window off williams_furniture onto williams_walls,
    painting floor under the moved walls. Windows win over walls on the walls
    layer. Idempotent -- an existing williams_walls layer seeds the geometry, so
    a second run (floor/furniture already cleaned) reproduces the same arrays."""
    layers = _tile_layers(tmj)
    floor = layers["williams_floor"]["data"]
    furn = layers["williams_furniture"]["data"]
    # Idempotency seed: on an already-relayered map the walls layer holds the
    # geometry, so a re-run reproduces it. The derive-fresh path (no walls layer)
    # is correct ONLY for a *faithful* pre-splice map -- wall_brick/window tiles
    # still on williams_floor/williams_furniture. A map with the walls layer merely
    # stripped is NOT faithful (the tiles aren't back on the floor), so it won't
    # round-trip -- do not write a test that assumes it does.
    existing = layers.get("williams_walls")
    new_walls = list(existing["data"]) if existing else [0] * len(floor)
    new_floor = list(floor)
    new_furn = list(furn)
    for i, g in enumerate(floor):
        if (g & GID_MASK) == WALL_GID:
            new_walls[i] = WALL_GID
            new_floor[i] = FLOOR_GID
    for i, g in enumerate(furn):
        if (g & GID_MASK) == WINDOW_GID:
            new_walls[i] = WINDOW_GID
            new_furn[i] = 0
    return new_walls, new_floor, new_furn


def williams_wall_cells(tmj):
    """The {(x,y)} cells on williams_walls -- the authoritative wall geometry
    (the tiles furnish_building painted, relayered). add_entrances seals the
    interior subset; the perimeter is sealed by the main carve loop."""
    W = tmj["width"]
    layers = _tile_layers(tmj)
    wl = layers.get("williams_walls")
    if not wl:
        return set()
    return {(i % W, i // W) for i, g in enumerate(wl["data"]) if g}


WILLIAMS_ARENA_OBJECTS = [
    {
        "name": "Classroom A",
        "type": "classroom",
        "x": 208,
        "y": 3648,
        "width": 158,
        "height": 224.666666666667,
    },
    {
        "name": "Classroom B 1",
        "type": "classroom",
        "x": 830.666666666667,
        "y": 3777.33333333333,
        "width": 242.666666666667,
        "height": 76.6666666666665,
    },
    {
        "name": "Office",
        "type": "office",
        "x": 224,
        "y": 3952,
        "width": 205.333333333333,
        "height": 145.333333333333,
    },
    {
        "name": "Restroom",
        "type": "restroom",
        "x": 493.333333333333,
        "y": 3981.33333333333,
        "width": 162.666666666667,
        "height": 114,
    },
    {
        "name": "Classroom C",
        "type": "classroom",
        "x": 897.333333333333,
        "y": 3954,
        "width": 174,
        "height": 141.333333333333,
    },
    {
        "name": "Classroom B 2",
        "type": "classroom",
        "x": 911.999833333333,
        "y": 3712.99998333333,
        "width": 159.333666666667,
        "height": 62.0000333333335,
    },
    {
        "name": "Lobby 1",
        "type": "",
        "x": 560.666666666667,
        "y": 3778,
        "width": 254,
        "height": 190.666666666667,
    },
    {
        "name": "Lobby 2",
        "type": "",
        "x": 674.666666666667,
        "y": 3971.33333333333,
        "width": 203.333333333333,
        "height": 138.666666666667,
    },
]


def _fmt_data(data, W, wrap_indent):
    """Render a flat gid array as Tiled does: W values per line (one map row),
    `, ` between values, `,\\n<wrap_indent>` between rows."""
    rows = [", ".join(str(g) for g in data[r : r + W]) for r in range(0, len(data), W)]
    return (",\n" + wrap_indent).join(rows)


def _wrap_indent(text, dstart):
    """The continuation indent Tiled uses inside a layer's data array."""
    nl = text.find("\n", dstart)
    j = nl + 1
    while j < len(text) and text[j] == " ":
        j += 1
    return text[nl + 1 : j]


def _layer_name_count(text, name):
    return text.count(f'"name":"{name}"')


def _find_block_bounds(text, name):
    """(start, end) byte offsets of the JSON object whose "name" is `name` — the
    enclosing `{` before the name key through its matching `}` (brace-depth walk,
    string-aware so braces inside string values don't miscount). Raises unless the
    name occurs exactly once."""
    n = _layer_name_count(text, name)
    if n != 1:
        raise ValueError(f"expected exactly one '{name}' layer, found {n}")
    nidx = text.find(f'"name":"{name}"')
    bstart = text.rfind("{", 0, nidx)
    depth, i, in_str, esc = 0, bstart, False, False
    while i < len(text):
        c = text[i]
        if in_str:
            if esc:
                esc = False
            elif c == "\\":
                esc = True
            elif c == '"':
                in_str = False
        elif c == '"':
            in_str = True
        elif c == "{":
            depth += 1
        elif c == "}":
            depth -= 1
            if depth == 0:
                return bstart, i + 1
        i += 1
    raise ValueError(f"unterminated layer block for {name}")


def _strip_layer(text, name):
    """Remove the one named layer's JSON block + one adjacent separator, leaving
    the layers array valid and Tiled-formatted. No-op if the layer is absent.
    Raises (via _find_block_bounds) if the name appears more than once."""
    if _layer_name_count(text, name) == 0:
        return text
    bstart, bend = _find_block_bounds(text, name)
    after = text[bend:]
    m = re.match(r",\s*", after)
    if m:  # not the last layer: drop block + trailing separator
        return text[:bstart] + after[m.end() :]
    before = text[:bstart]  # last layer: drop the leading separator instead
    m2 = re.search(r",\s*$", before)
    return (before[: m2.start()] if m2 else before) + after


def _replace_layer_data(text, layer_name, new_data, W):
    """Replace the data array of one named tile layer, preserving Tiled's
    W-per-line wrapping so unchanged rows stay byte-identical. Fails loudly if the
    name is not unique or the data array is not flat."""
    n = _layer_name_count(text, layer_name)
    if n != 1:
        raise ValueError(f"expected exactly one '{layer_name}' layer, found {n}")
    nidx = text.find(f'"name":"{layer_name}"')
    bstart = text.rfind("{", 0, nidx)
    dstart = text.find('"data":[', bstart)
    dend = text.find("]", dstart)
    # flat-array invariant: tile-layer data is a flat int array (no nested [...]),
    # which is what lets us stop at the first ']'.
    if "[" in text[dstart + len('"data":[') : dend]:
        raise ValueError(f"{layer_name} data is not a flat array")
    wi = _wrap_indent(text, dstart)
    return text[:dstart] + '"data":[' + _fmt_data(new_data, W, wi) + text[dend:]


def _bump_header(text, key, atleast):
    """Set a top-level header field to max(current, atleast) so ids never regress."""
    m = re.search(rf'"{key}":(\d+)', text)
    cur = int(m.group(1)) if m else 0
    return re.sub(rf'"{key}":\d+', f'"{key}":{max(cur, atleast)}', text, count=1)


def _tile_layer_block(data, layer_id, name, W, H, k9):
    """Tiled-format tile layer object text (alphabetical keys, inline W-wrapped
    data); k9 is the 9-space field indent from a sibling layer."""
    k8 = k9[:-1]
    arr = _fmt_data(data, W, k9 + "   ")
    return (
        "{\n"
        f'{k9}"data":[{arr}],\n'
        f'{k9}"height":{H},\n'
        f'{k9}"id":{layer_id},\n'
        f'{k9}"name":"{name}",\n'
        f'{k9}"opacity":1,\n'
        f'{k9}"type":"tilelayer",\n'
        f'{k9}"visible":true,\n'
        f'{k9}"width":{W},\n'
        f'{k9}"x":0,\n'
        f'{k9}"y":0\n'
        f"{k8}}}"
    )


def _object_layer_block(objects, layer_id, name, next_obj, k9):
    """Tiled-format objectgroup text with rectangle objects (matches the sibling
    *_arenas layers: objects indented 7 spaces past the layer fields)."""
    k8 = k9[:-1]
    ko = k9 + "       "
    kof = ko + " "
    parts = []
    oid = next_obj
    for o in objects:
        parts.append(
            "{\n"
            f'{kof}"height":{o["height"]},\n'
            f'{kof}"id":{oid},\n'
            f'{kof}"name":"{o["name"]}",\n'
            f'{kof}"opacity":1,\n'
            f'{kof}"rotation":0,\n'
            f'{kof}"type":"{o.get("type", "")}",\n'
            f'{kof}"visible":true,\n'
            f'{kof}"width":{o["width"]},\n'
            f'{kof}"x":{o["x"]},\n'
            f'{kof}"y":{o["y"]}\n'
            f"{ko}}}"
        )
        oid += 1
    objs = (", \n" + ko).join(parts)
    return (
        "{\n"
        f'{k9}"draworder":"topdown",\n'
        f'{k9}"id":{layer_id},\n'
        f'{k9}"name":"{name}",\n'
        f'{k9}"objects":[\n{ko}{objs}\n{k9}],\n'
        f'{k9}"opacity":1,\n'
        f'{k9}"type":"objectgroup",\n'
        f'{k9}"visible":true,\n'
        f'{k9}"x":0,\n'
        f'{k9}"y":0\n'
        f"{k8}}}"
    )


def apply_to_file(tmj_path):
    """Idempotently splice williams_walls + williams_arenas into the committed tmj
    and update williams_floor/williams_furniture data, preserving Tiled formatting.
    Strips any prior spliced layers first and reuses their exact ids, so a re-run
    (and a run on the already-spliced committed tmj) is byte-identical. Backs up to
    <path>.bak first."""
    tmj = json.load(open(tmj_path))
    W, H = tmj["width"], tmj["height"]
    new_walls, new_floor, new_furn = compute_relayer(tmj)

    # Capture-and-reuse ids: if a spliced layer already exists, reuse its id;
    # else derive from the max id among the OTHER layers. Never read the
    # nextlayerid/nextobjectid headers for this (a strip doesn't lower them).
    by_name = {L.get("name"): L for L in tmj["layers"]}
    other_max_layer = max(
        (
            L.get("id", 0)
            for L in tmj["layers"]
            if L.get("name") not in ("williams_walls", "williams_arenas")
        ),
        default=0,
    )
    walls_id = (
        by_name["williams_walls"]["id"]
        if "williams_walls" in by_name
        else other_max_layer + 1
    )
    arenas_id = (
        by_name["williams_arenas"]["id"]
        if "williams_arenas" in by_name
        else other_max_layer + 2
    )

    arenas_layer = by_name.get("williams_arenas")
    if arenas_layer and arenas_layer.get("objects"):
        obj_base = min(o["id"] for o in arenas_layer["objects"])
    else:
        other_obj_max = max(
            (
                o["id"]
                for L in tmj["layers"]
                if L.get("type") == "objectgroup" and L.get("name") != "williams_arenas"
                for o in L.get("objects", [])
            ),
            default=0,
        )
        obj_base = other_obj_max + 1

    text = open(tmj_path).read()
    shutil.copy2(tmj_path, tmj_path + ".bak")

    # Idempotency: remove any prior spliced layers before re-inserting.
    text = _strip_layer(text, "williams_walls")
    text = _strip_layer(text, "williams_arenas")
    text = _replace_layer_data(text, "williams_floor", new_floor, W)
    text = _replace_layer_data(text, "williams_furniture", new_furn, W)

    fidx = text.find('"name":"williams_furniture"')
    fstart = text.rfind("{", 0, fidx)
    line0 = text.rfind("\n", 0, fstart) + 1
    k8 = text[line0:fstart]
    k9 = k8 + " "
    walls_block = _tile_layer_block(new_walls, walls_id, "williams_walls", W, H, k9)
    arena_objects = _arena_objects(tmj)
    arenas_block = _object_layer_block(
        arena_objects, arenas_id, "williams_arenas", obj_base, k9
    )
    insertion = walls_block + ",\n" + k8 + arenas_block + ",\n" + k8
    text = text[:line0] + k8 + insertion + text[line0 + len(k8) :]

    text = _bump_header(text, "nextlayerid", max(walls_id, arenas_id) + 1)
    text = _bump_header(text, "nextobjectid", obj_base + len(arena_objects))
    with open(tmj_path, "w") as fh:
        fh.write(text)


def main():
    here = os.path.dirname(os.path.abspath(__file__))
    repo = os.path.dirname(os.path.dirname(os.path.dirname(here)))
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument(
        "--tmj",
        default=os.path.join(
            repo, "godot-generative-agents", "godot", "maps", "upenn_core_urban.tmj"
        ),
    )
    args = ap.parse_args()
    apply_to_file(args.tmj)
    print(f"spliced williams_walls + williams_arenas into {args.tmj}")


if __name__ == "__main__":
    main()
