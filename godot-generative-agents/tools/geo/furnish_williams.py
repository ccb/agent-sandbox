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
