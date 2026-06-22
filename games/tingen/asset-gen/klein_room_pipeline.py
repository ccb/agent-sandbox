#!/usr/bin/env python3
"""Klein's-bedroom 3-step art pipeline (Mark's request).

A thin driver over generate_tingen_image2.py that produces a *cohesive* set for the
IntroRoom slice from one source image, so the floor and props share a single look:

  step 1 (room)  : reimagine the canon `kleinroom` ref as a flat top-down map (directly overhead).
  step 2 (floor) : take the generated room and strip it to the bare walkable floor
                   (a tileable texture for the TileMapLayer / a single floor sprite).
  step 3 (items) : take the generated room and cut each furniture piece out onto a
                   transparent sheet (sliced later into individual prop PNGs).

Steps 2 and 3 are conditioned on the step-1 room (NOT the canon ref) so all three
outputs share one palette/angle.  Run step 1 first and eyeball it before paying for
2-3 — they inherit whatever the room looks like.

Usage:
  python3 klein_room_pipeline.py 1     # or: room
  python3 klein_room_pipeline.py 2     # or: floor   (needs room.png)
  python3 klein_room_pipeline.py 3     # or: items   (needs room.png)

Cost: gpt-image-1 high ~= $0.25 / image.
"""

from __future__ import annotations

import sys
from pathlib import Path

import generate_tingen_image2 as g

OUT = g.OUT_DIR / "klein_room"
ROOM = OUT / "room.png"
FLOOR = OUT / "floor.png"
ITEMS = OUT / "items_sheet.png"
BARE = OUT / "room_bare.png"
BLOOD = OUT / "room_blood.png"

# Step 2b: the EMPTY room — remove furniture/rug but keep room.png's *exact* floor,
# walls, perspective and lighting (high fidelity).  This is "the floor from the image"
# Mark asked for, vs step 2 which was a fresh generic seamless tile.
BARE_PROMPT = (
    "Show this EXACT same room completely empty: remove ALL the furniture, the rug, "
    "the lamp and every object, so only the bare wood-plank floor, the walls, the "
    "window and the curtains remain. Keep the identical wood floor planks, the wall "
    "colour, the window, the exact same perspective, tilt and viewing angle and the warm "
    "gaslight lighting EXACTLY as in the reference image — change nothing except "
    "removing the furniture and rug. An empty room from the same overhead angle, "
    "no furniture, no rug, no objects, no people, no text, no border"
)

# Blood pass (Mark, v2 "less blood"): take the approved room.png and add ONE small,
# contained floor bloodstain in place at high fidelity — NO desk smears, NO soaked chair,
# NO spatter — while keeping every other pixel (furniture, layout, perspective) identical.
BLOOD_PROMPT = (
    "Show this EXACT same room, completely identical to the reference image in every "
    "detail: the same carved-wood bed, the writing desk and wooden chair by the window, "
    "the bookshelf, wardrobe, dresser, nightstands and oil lamps, the patterned rug, the "
    "wood-plank floor, the walls, window and curtains, all in the same positions, with the "
    "exact same overhead perspective, tilt and warm amber gaslight lighting. Change NOTHING "
    "except adding ONE small, contained pool of dark crimson blood on the bare wood floor "
    "beside the writing desk and chair — a single modest bloodstain about the size of a "
    "dinner plate, with a soft irregular edge. Keep it SMALL and restrained. There is NO "
    "other blood anywhere: none on the desk, none on the chair, none on the rug, the walls "
    "or any furniture, no smears, no spatter, no drips, no handprints. The single bloodstain "
    "is painted in the same warm painterly style as the room. Everything else stays exactly "
    "as in the reference image. No body, no people, no text, no border"
)

# Step 1: feed the pipeline's own background/topdown machinery (lead/tail + BG_TOPDOWN,
# canon ref at low fidelity so the top-down reframe isn't overridden).
ROOM_SPEC = {
    "treatment": "topdown",
    "ref": "kleinroom",
    "prompt": (
        "Klein Moretti's warm cozy middle-class Victorian bedroom, an ornate "
        "carved-wood bed with a quilt set against the wall, a writing desk with a "
        "chair beside the window, a tall bookshelf, a wardrobe and a dresser, a "
        "patterned rug centered on a warm wood-plank floor, a bedside table with a "
        "lit oil lamp, warm amber gaslight, lived-in and tidy"
    ),
}

# Step 2: strip the generated room down to just its floor.  Conditioned on room.png.
FLOOR_PROMPT = (
    "the bare empty floor of this exact room with ALL furniture, rugs, walls and "
    "objects completely removed, leaving only the warm wood-plank floor surface, the "
    "same plank texture, color and warm lighting as the reference image, a clean even "
    "seamless top-down floor texture that fills the entire frame edge to edge, no "
    "furniture, no rug, no walls, no shadows of objects, no people, no text, no border"
)

# Step 3: cut the room's furniture onto a transparent sheet.  Conditioned on room.png.
# v2 (Mark): copy each piece EXACTLY as it appears in room.png (no restyling) and add
# the pieces v1 missed -- both lit oil lamps, the framed wall picture, the chest, the
# wall cabinet and the desk book.
ITEMS_PROMPT = (
    "a neat game sprite-sheet of the individual furniture pieces and objects from THIS "
    "EXACT room, each one COPIED EXACTLY as it appears in the reference image — keep the "
    "identical design, proportions, carved wood detail, colour and warm lighting of each "
    "piece, do NOT redesign or restyle them — each object cut out and isolated separately "
    "with empty space around it on a fully transparent background, laid out in an evenly "
    "spaced grid: the carved-wood bed with its green-and-tan patchwork quilt and two pale "
    "pillows; the writing desk; the lit oil lamp with a rounded glass shade glowing warm; "
    "the open book; the wooden chair with a slatted back; the tall open bookshelf full of "
    "books; the wall-mounted cabinet with two closed doors; the tall two-door wardrobe; "
    "the small bedside nightstand; a second lit oil lamp with a tall glass chimney and "
    "warm flame; the dresser with an oval swivel mirror on top; the low wooden chest or "
    "trunk; a small rectangular framed wall picture; the patterned rug — each kept at the "
    "EXACT same tilt, angle and perspective it has in the reference room (do NOT flatten or "
    "change its viewing angle), preserving each object's own soft cast shadow and every "
    "painted detail, in the same painted style, palette and warm gaslight lighting as the "
    "reference image, clean cut-out game assets, transparent background, no room, no floor, "
    "no walls, no text, no labels"
)


def _ensure_key() -> None:
    if not g.OPENAI_API_KEY:
        g.OPENAI_API_KEY = g.load_key(g.DEFAULT_ENV_FILE)
    if not g.OPENAI_API_KEY:
        sys.exit("ERROR: OPENAI_API_KEY not found (env or default env file)")
    print(f"  key loaded ({len(g.OPENAI_API_KEY)} chars)")


def step1_room() -> None:
    _ensure_key()
    OUT.mkdir(parents=True, exist_ok=True)
    ref_paths, hi = g.resolve_refs("backgrounds", "klein_room_topdown", ROOM_SPEC)
    prompt = g.build_prompt("backgrounds", "klein_room_topdown", ROOM_SPEC, True)
    print(
        f"  STEP 1 room  refs={[p.name for p in ref_paths]} fid={'high' if hi else 'low'}"
    )
    print(f"  prompt: {prompt}")
    img = g.generate(prompt, "1536x1024", "opaque", "high", ref_paths, hi)
    if not img:
        sys.exit("  STEP 1 FAILED")
    ROOM.write_bytes(img)
    print(f"  OK -> {ROOM} ({len(img)//1024}KB)")


def step2_floor() -> None:
    _ensure_key()
    if not ROOM.exists():
        sys.exit("  need room.png first (run step 1)")
    print("  STEP 2 floor  ref=room.png fid=high")
    print(f"  prompt: {FLOOR_PROMPT}")
    img = g.generate(FLOOR_PROMPT, "1536x1024", "opaque", "high", [ROOM], True)
    if not img:
        sys.exit("  STEP 2 FAILED")
    FLOOR.write_bytes(img)
    print(f"  OK -> {FLOOR} ({len(img)//1024}KB)")


def step2b_bare() -> None:
    """Inpaint room.png into the SAME room with furniture removed (keeps the exact
    floor/walls/window/perspective/lighting).  This is 'the floor from the image'
    Mark asked for, vs the rejected step-2 generic seamless tile."""
    _ensure_key()
    if not ROOM.exists():
        sys.exit("  need room.png first (run step 1)")
    print("  STEP 2b bare-room  ref=room.png fid=high")
    print(f"  prompt: {BARE_PROMPT}")
    img = g.generate(BARE_PROMPT, "1536x1024", "opaque", "high", [ROOM], True)
    if not img:
        sys.exit("  STEP 2b FAILED")
    BARE.write_bytes(img)
    print(f"  OK -> {BARE} ({len(img)//1024}KB)")


def step_blood() -> None:
    """Add the crime-scene blood to room.png in place (high fidelity), keeping the rest
    of the room pixel-identical.  Output room_blood.png becomes the IntroRoom backdrop.
    """
    _ensure_key()
    if not ROOM.exists():
        sys.exit("  need room.png first (run step 1)")
    print("  STEP blood  ref=room.png fid=high")
    print(f"  prompt: {BLOOD_PROMPT}")
    img = g.generate(BLOOD_PROMPT, "1536x1024", "opaque", "high", [ROOM], True)
    if not img:
        sys.exit("  STEP blood FAILED")
    BLOOD.write_bytes(img)
    print(f"  OK -> {BLOOD} ({len(img)//1024}KB)")


def step3_items() -> None:
    _ensure_key()
    if not ROOM.exists():
        sys.exit("  need room.png first (run step 1)")
    print("  STEP 3 items  ref=room.png fid=high")
    print(f"  prompt: {ITEMS_PROMPT}")
    img = g.generate(ITEMS_PROMPT, "1536x1024", "transparent", "high", [ROOM], True)
    if not img:
        sys.exit("  STEP 3 FAILED")
    ITEMS.write_bytes(img)
    print(f"  OK -> {ITEMS} ({len(img)//1024}KB)")


if __name__ == "__main__":
    arg = (sys.argv[1] if len(sys.argv) > 1 else "1").lower()
    if arg in ("1", "room"):
        step1_room()
    elif arg in ("2", "floor"):
        step2_floor()
    elif arg in ("2b", "bare"):
        step2b_bare()
    elif arg in ("blood",):
        step_blood()
    elif arg in ("3", "items"):
        step3_items()
    else:
        sys.exit(
            "usage: klein_room_pipeline.py [1|room | 2|floor | 2b|bare | blood | 3|items]"
        )
