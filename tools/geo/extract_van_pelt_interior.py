#!/usr/bin/env python3
"""Freeze the hand-designed Van Pelt interior from commit f5219ce into
van_pelt_interior.json. One-time generator (provenance); the JSON is the
committed artifact the runtime tools read. Re-run only to re-extract."""
import json, math, os, subprocess

SRC = "f5219ce"
MAP = "godot-generative-agents/maps/upenn_core_urban.tmj"
LAYER_ORDER = [
    "westwing_floors", "eastwing_floors",
    "westwing_walls", "eastwing_walls",
    "westwing_furniture", "eastwing_furniture",
]
WALL_LAYERS = ["westwing_walls", "eastwing_walls"]


def git_show(ref, path):
    return subprocess.run(
        ["git", "show", f"{ref}:{path}"],
        capture_output=True, text=True, check=True,
    ).stdout


def main():
    here = os.path.dirname(os.path.abspath(__file__))
    m = json.loads(git_show(SRC, MAP))
    W, H = m["width"], m["height"]
    by_name = {L["name"]: L for L in m["layers"] if L.get("type") == "tilelayer"}

    asset = {
        "source_commit": SRC, "width": W, "height": H,
        "layer_order": LAYER_ORDER, "layers": {}, "wall_cells": [], "rooms": [],
    }
    for name in LAYER_ORDER:
        data = by_name[name]["data"]
        asset["layers"][name] = {str(i): v for i, v in enumerate(data) if v}

    wall = set()
    for name in WALL_LAYERS:
        for i, v in enumerate(by_name[name]["data"]):
            if v:
                wall.add(i)
    asset["wall_cells"] = sorted(wall)

    arenas = next(L for L in m["layers"] if L["name"] == "arenas")
    rooms = []
    for o in arenas["objects"]:
        if o.get("name") and o["width"] > 0 and o["height"] > 0:
            c0, r0 = int(o["x"] // 16), int(o["y"] // 16)
            c1 = math.ceil((o["x"] + o["width"]) / 16) - 1
            r1 = math.ceil((o["y"] + o["height"]) / 16) - 1
            rooms.append({"name": o["name"], "rect": [c0, r0, c1, r1]})
    asset["rooms"] = sorted(rooms, key=lambda r: r["name"])

    out = os.path.join(here, "van_pelt_interior.json")
    with open(out, "w") as fh:
        json.dump(asset, fh, indent=1)
    print(f"wrote {out}: {len(asset['layers'])} layers, "
          f"{len(asset['rooms'])} rooms, {len(asset['wall_cells'])} wall cells")


if __name__ == "__main__":
    main()
