#!/usr/bin/env python3
"""Tile-usage presets — the seam between "what a human curated" and "what the LLM
sees". A preset is a named subset of furniture_catalog.json: the tiles you want
Claude (or any LLM) to use when furnishing or parsing the tilemap, plus optional
per-tile placement hints.

Presets are created/edited visually in the web UI (catalog_web.py) and saved to
tile_presets.json. This module loads them and renders the **LLM-facing menu** —
the compact, budget-aware tile list you paste into (or feed) a furnishing prompt.

    uv run python tools/geo/tile_presets.py --list            # all presets
    uv run python tools/geo/tile_presets.py --menu            # active preset -> LLM menu
    uv run python tools/geo/tile_presets.py --menu classroom  # a specific preset
    uv run python tools/geo/tile_presets.py --use classroom   # set the active preset
    uv run python tools/geo/tile_presets.py --delete classroom

In furnishing code, `objects(name)` returns the filtered catalog dict (only the
preset's tiles), so block_named()/tile_named() can be restricted to the preset.
"""

from __future__ import annotations

import argparse
import collections
import json
import os

HERE = os.path.dirname(os.path.abspath(__file__))
CATALOG_PATH = os.path.join(HERE, "furniture_catalog.json")
PRESETS_PATH = os.path.join(HERE, "tile_presets.json")


# --------------------------------------------------------------------------- #
# Storage
# --------------------------------------------------------------------------- #
def load_presets() -> dict:
    """The presets file as {active, presets}, tolerant of a missing/empty/corrupt file."""
    try:
        with open(PRESETS_PATH) as fh:
            data = json.load(fh)
    except (FileNotFoundError, json.JSONDecodeError):
        return {"active": None, "presets": {}}
    data.setdefault("active", None)
    data.setdefault("presets", {})
    return data


def write_presets(data: dict) -> None:
    """Persist {active, presets}, keeping the _README banner."""
    out = {
        "_README": load_presets_readme(),
        "active": data.get("active"),
        "presets": data.get("presets", {}),
    }
    with open(PRESETS_PATH, "w") as fh:
        json.dump(out, fh, indent=2)
        fh.write("\n")


def load_presets_readme() -> str:
    try:
        with open(PRESETS_PATH) as fh:
            return json.load(fh).get("_README", "")
    except Exception:  # noqa: BLE001
        return ""


def load_catalog() -> dict:
    with open(CATALOG_PATH) as fh:
        return json.load(fh)


def catalog_objects(catalog: dict | None = None) -> dict:
    """Catalog objects minus the `_`-prefixed comment keys."""
    catalog = catalog or load_catalog()
    return {k: v for k, v in catalog["objects"].items() if not k.startswith("_")}


# --------------------------------------------------------------------------- #
# Resolution
# --------------------------------------------------------------------------- #
def resolve(name: str | None = None) -> tuple[str | None, dict]:
    """(name, preset) for the requested preset, or the active one if name is None."""
    data = load_presets()
    name = name or data.get("active")
    if name is None:
        return None, {}
    preset = data["presets"].get(name)
    if preset is None:
        raise SystemExit(f"no such preset: {name!r} (have: {list(data['presets'])})")
    return name, preset


def objects(name: str | None = None) -> dict:
    """Catalog objects restricted to a preset's tiles (existing ones only)."""
    _, preset = resolve(name)
    catalog = catalog_objects()
    return {k: catalog[k] for k in preset.get("tiles", []) if k in catalog}


# --------------------------------------------------------------------------- #
# LLM-facing menu
# --------------------------------------------------------------------------- #
def menu(name: str | None = None) -> str:
    """Markdown tile menu for an LLM: only the preset's tiles, grouped by category,
    with sizes, labels and any per-tile notes, plus the option-budget reminder."""
    catalog = load_catalog()
    guidance = catalog.get("_llm_guidance", {})
    per_cat = guidance.get("options_per_category", 12)
    per_prompt = guidance.get("max_per_prompt", 30)

    name, preset = resolve(name)
    objs = catalog_objects(catalog)
    tiles = [k for k in preset.get("tiles", []) if k in objs]
    missing = [k for k in preset.get("tiles", []) if k not in objs]
    notes = preset.get("notes", {})

    lines = [f"# Tile menu — preset: {name or '(none)'}"]
    if preset.get("description"):
        lines.append(preset["description"])
    lines += [
        "",
        "Use ONLY these tiles when furnishing/parsing the tilemap; reference each "
        "by its `name`. Coordinates live in furniture_catalog.json.",
        f"Option budget: ≤ {per_cat} per category, ≤ {per_prompt} total.",
        "",
    ]
    by_cat: dict[str, list[str]] = collections.defaultdict(list)
    for k in tiles:
        by_cat[objs[k]["category"]].append(k)
    if not tiles:
        lines.append("_(no tiles in this preset yet)_")
    for cat in sorted(by_cat):
        ks = by_cat[cat]
        flag = f"  ⚠ over the {per_cat}/category budget" if len(ks) > per_cat else ""
        lines.append(f"## {cat} ({len(ks)}){flag}")
        for k in ks:
            o = objs[k]
            note = f"  | note: {notes[k]}" if notes.get(k) else ""
            lines.append(f"- {k} [{o['w']}x{o['h']}] — {o.get('label','')}{note}")
        lines.append("")
    if len(tiles) > per_prompt:
        lines.append(
            f"> NOTE: {len(tiles)} tiles exceeds the {per_prompt}-per-prompt budget — "
            "split by room/category before handing to an LLM."
        )
    if missing:
        lines.append(f"> dropped (not in catalog): {', '.join(missing)}")
    return "\n".join(lines)


# --------------------------------------------------------------------------- #
# CLI
# --------------------------------------------------------------------------- #
def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--list", action="store_true", help="list presets")
    ap.add_argument(
        "--menu",
        nargs="?",
        const="\x00",
        metavar="NAME",
        help="print the LLM tile menu (active preset if no NAME)",
    )
    ap.add_argument("--use", metavar="NAME", help="set the active preset")
    ap.add_argument("--delete", metavar="NAME", help="delete a preset")
    a = ap.parse_args()

    if a.use is not None:
        data = load_presets()
        if a.use not in data["presets"]:
            raise SystemExit(f"no such preset: {a.use!r}")
        data["active"] = a.use
        write_presets(data)
        print(f"active preset -> {a.use}")
        return
    if a.delete is not None:
        data = load_presets()
        if data["presets"].pop(a.delete, None) is None:
            raise SystemExit(f"no such preset: {a.delete!r}")
        if data.get("active") == a.delete:
            data["active"] = None
        write_presets(data)
        print(f"deleted preset {a.delete}")
        return
    if a.menu is not None:
        print(menu(None if a.menu == "\x00" else a.menu))
        return
    # default / --list
    data = load_presets()
    active = data.get("active")
    if not data["presets"]:
        print("no presets yet — create one in the web UI (catalog_web.py --serve)")
        return
    print(f"active: {active}")
    cat = catalog_objects()
    for nm, p in data["presets"].items():
        n = sum(1 for k in p.get("tiles", []) if k in cat)
        star = "*" if nm == active else " "
        print(f" {star} {nm:20} {n:3d} tiles  {p.get('description','')}")


if __name__ == "__main__":
    main()
