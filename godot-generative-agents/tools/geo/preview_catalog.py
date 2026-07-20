#!/usr/bin/env python3
"""Render a labeled contact sheet of furniture_catalog.json so you can SEE that
every (col,row) actually points at the object its label claims.

    uv run --with pillow python godot-generative-agents/tools/geo/preview_catalog.py
    # writes godot-generative-agents/tools/geo/out/furniture_catalog_preview.png

Why this exists: the catalog's coordinates were read off the Franuka sheets by
eye. Entries marked "verified": false should be checked here before you trust
them in furnish_building.py — a wrong (col,row) is instantly obvious as a
mislabeled crop. Entries flagged unverified get a "?" badge.

This is a dev/QA tool (Pillow only); it is NOT imported by the game or the
furnishing step, so Pillow stays an optional dependency.
"""

from __future__ import annotations

import json
import os

from PIL import Image, ImageDraw  # type: ignore

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.dirname(os.path.dirname(os.path.dirname(HERE)))
SHEET_DIR = os.path.join(REPO, "godot-generative-agents", "godot", "maps")
TILE = 16


def main() -> None:
    catalog = json.load(open(os.path.join(HERE, "furniture_catalog.json")))
    sheets = {
        name: Image.open(os.path.join(SHEET_DIR, meta["file"])).convert("RGBA")
        for name, meta in catalog["sheets"].items()
    }

    # Group objects by (category, room) so the sheet reads like the catalog.
    # Keys beginning "_" are human-readable section comments, not tile entries.
    objs = {k: v for k, v in catalog["objects"].items() if not k.startswith("_")}
    groups: dict[str, list[str]] = {}
    for name, o in objs.items():
        key = (
            o["category"]
            if o["category"] != "furniture"
            else f"furniture/{o.get('room','?')}"
        )
        groups.setdefault(key, []).append(name)

    SCALE = 4  # tile px -> preview px for the crop
    CELL_W, CELL_H = 150, 150  # one catalog entry's box
    PAD, HEADER = 10, 28
    COLS = 6

    # Pre-compute layout height.
    rows_total = 0
    for names in groups.values():
        rows_total += 1 + (len(names) + COLS - 1) // COLS  # 1 header row + tile rows
    W = COLS * CELL_W + 2 * PAD
    H = rows_total * 0  # filled below; just allocate generously
    H = (
        sum(
            HEADER + ((len(names) + COLS - 1) // COLS) * CELL_H
            for names in groups.values()
        )
        + 2 * PAD
    )

    canvas = Image.new("RGBA", (W, H), (24, 24, 30, 255))
    d = ImageDraw.Draw(canvas)
    y = PAD
    for group, names in sorted(groups.items()):
        d.rectangle([PAD, y, W - PAD, y + HEADER - 4], fill=(48, 48, 60, 255))
        d.text((PAD + 6, y + 7), f"{group}  ({len(names)})", fill=(255, 255, 255, 255))
        y += HEADER
        for i, name in enumerate(sorted(names)):
            o = objs[name]
            cx = PAD + (i % COLS) * CELL_W
            cy = y + (i // COLS) * CELL_H
            sheet = sheets[o["sheet"]]
            crop = sheet.crop(
                (
                    o["col"] * TILE,
                    o["row"] * TILE,
                    (o["col"] + o["w"]) * TILE,
                    (o["row"] + o["h"]) * TILE,
                )
            )
            bg = Image.new("RGBA", crop.size, (40, 40, 50, 255))
            crop = Image.alpha_composite(bg, crop)
            crop = crop.resize(
                (o["w"] * TILE * SCALE, o["h"] * TILE * SCALE), Image.NEAREST
            )
            # center the crop in the upper part of the cell
            px = cx + (CELL_W - crop.size[0]) // 2
            py = cy + 8
            canvas.paste(crop, (px, max(py, cy + 8)))
            badge = "" if o.get("verified") else "  ?"
            d.text(
                (cx + 6, cy + CELL_H - 36),
                f"{name}{badge}",
                fill=(
                    (230, 230, 120, 255)
                    if not o.get("verified")
                    else (160, 230, 160, 255)
                ),
            )
            d.text(
                (cx + 6, cy + CELL_H - 22),
                f'{o["sheet"]} ({o["col"]},{o["row"]}) {o["w"]}x{o["h"]}',
                fill=(170, 170, 180, 255),
            )
        y += ((len(names) + COLS - 1) // COLS) * CELL_H

    out_dir = os.path.join(HERE, "out")
    os.makedirs(out_dir, exist_ok=True)
    out = os.path.join(out_dir, "furniture_catalog_preview.png")
    canvas.save(out)
    n_unverified = sum(1 for o in objs.values() if not o.get("verified"))
    print(
        f"wrote {out}  ({len(objs)} objects, {n_unverified} unverified — check the '?' badges)"
    )


if __name__ == "__main__":
    main()
