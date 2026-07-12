#!/usr/bin/env python3
"""Faithful building upscale — the Tingen_Map_Tutorial step-3b flow, headless.

Per building: (1) EDITS call with input_fidelity=HIGH: 'a more detailed, full screen
image of X, true to the provided image' with the map crop as the ONLY reference —
high fidelity keeps the map's actual painted building (low fidelity, used by the first
failed batch, let the model invent new compounds); (2) EDITS call on the step-1 result:
keep only the building, background=transparent. Outputs land in out_image2/buildings/faithful/.

Placement is then DETERMINISTIC: output = crop upscaled, so
  world_scale  = (CROP_PX / OUT_PX) * 5          # map px -> world px is x5
  world_pos    = (crop_origin + opaque_center / (OUT_PX / CROP_PX)) * 5

Usage:
  python3 upscale_city_buildings.py --env-file '/path/.env' --only laughing_eel
  python3 upscale_city_buildings.py --env-file '/path/.env'          # all missing
Never prints the API key. Budget cap shared via _budget.json (40 images).
"""
from __future__ import annotations

import argparse
import base64
import io
import json
import mimetypes
import os
import sys
import urllib.request
import uuid
from pathlib import Path

from PIL import Image

HERE = Path(__file__).resolve().parent
MAP = HERE / "my_assets" / "map_v3.png"
OUT = HERE / "out_image2" / "buildings"
FAITHFUL = OUT / "faithful"
KEYED = FAITHFUL / "keyed"
BUDGET_FILE = OUT / "_budget.json"
BUDGET_CAP = 40
API = "https://api.openai.com/v1/images/edits"
MODEL = "gpt-image-2"   # the ChatGPT in-app "image 2" tool — the tutorial's model
OUT_PX = 1024   # square output so the crop->output mapping is uniform

# name -> (label center on map_v3, crop half-size px, short description for the prompt)
BUILDINGS: dict[str, tuple[tuple[int, int], int, str]] = {
    "laughing_eel": ((428, 694), 200, "the corner tavern building at the center"),
    "iron_cross_market": ((627, 610), 200, "the market square with its stalls at the center"),
    "raphael_cemetery": ((445, 1160), 200, "the walled cemetery with its gate at the center"),
    "selena_almshouse": ((560, 209), 200, "the almshouse building at the center"),
    "tingen_docks": ((110, 1024), 200, "the dockside warehouse and pier at the center"),
    "river_wharves": ((1114, 1091), 200, "the wharf sheds at the center"),
    "police_station": ((763, 811), 200, "the police station building at the center"),
    "mr_frankys": ((951, 658), 200, "the lodging house at the center"),
    "coal_yard": ((199, 130), 200, "the coal yard with its heaps and shed at the center"),
    "ironworks": ((1056, 136), 200, "the ironworks factory with chimneys at the center"),
    "globe_works": ((88, 610), 200, "the workshop building at the center"),
    "rowhouse_a": ((500, 420), 200, "the row-house block at the center"),
    "rowhouse_b": ((850, 950), 200, "the row-house block at the center"),
    "rowhouse_c": ((300, 560), 200, "the row-house block at the center"),
}

DETAIL_PROMPT = (
    "generate a more detailed, full screen image of {desc}, true to the provided image. "
    "Keep the same hand-painted style, same top-down angle, same layout, same colours and "
    "lighting — this is the SAME place from the same city map, only larger and more detailed. "
    "Do NOT redraw, move, add or remove any building or street. No text, no lettering, no labels."
)
CUTOUT_PROMPT = (
    "remove everything outside of {desc_short}. only keep {desc_short} and its immediate "
    "yard or fence, exactly as drawn, on a plain pure white background."
)


def read_key(env_file: str | None) -> str:
    key = os.environ.get("OPENAI_API_KEY", "")
    if not key and env_file:
        for line in Path(env_file).read_text().splitlines():
            if line.startswith("OPENAI_API_KEY="):
                key = line.split("=", 1)[1].strip().strip('"')
                break
    if not key:
        sys.exit("no OPENAI_API_KEY in env or --env-file")
    return key


def budget() -> dict:
    if BUDGET_FILE.exists():
        return json.loads(BUDGET_FILE.read_text())
    return {"used": 0}


def spend(n: int = 1) -> None:
    b = budget()
    b["used"] = int(b.get("used", 0)) + n
    BUDGET_FILE.write_text(json.dumps(b))


def check_budget() -> None:
    used = int(budget().get("used", 0))
    if used >= BUDGET_CAP:
        sys.exit(f"budget cap reached ({used}/{BUDGET_CAP}) — raise --budget-cap deliberately if needed")


def edits_call(key: str, image_path: Path, prompt: str, transparent: bool) -> bytes:
    """One /v1/images/edits call (multipart). Returns decoded PNG bytes."""
    check_budget()
    boundary = uuid.uuid4().hex
    parts: list[bytes] = []

    def field(name: str, value: str) -> None:
        parts.append(
            (f"--{boundary}\r\nContent-Disposition: form-data; name=\"{name}\"\r\n\r\n{value}\r\n").encode()
        )

    field("model", MODEL)
    field("prompt", prompt)
    field("size", f"{OUT_PX}x{OUT_PX}")
    field("quality", "high")
    if MODEL.startswith("gpt-image-1"):
        field("input_fidelity", "high")   # image-1's faithfulness lever; image-2 rejects the param
        # (invalid_input_fidelity_model) — the newer model keeps reference content natively.
    if transparent and MODEL.startswith("gpt-image-1"):
        field("background", "transparent")   # image-2 rejects it; its cutouts come back on white
        # and key_building.py (the tutorial's own step) does the alpha instead.
    mime = mimetypes.guess_type(str(image_path))[0] or "image/png"
    parts.append(
        (f"--{boundary}\r\nContent-Disposition: form-data; name=\"image[]\"; "
         f"filename=\"{image_path.name}\"\r\nContent-Type: {mime}\r\n\r\n").encode()
        + image_path.read_bytes() + b"\r\n"
    )
    parts.append(f"--{boundary}--\r\n".encode())
    body = b"".join(parts)
    req = urllib.request.Request(API, data=body, method="POST")
    req.add_header("Authorization", f"Bearer {key}")
    req.add_header("Content-Type", f"multipart/form-data; boundary={boundary}")
    try:
        try:
            with urllib.request.urlopen(req, timeout=600) as resp:
                out = json.loads(resp.read())
        except (TimeoutError, OSError) as e:
            if isinstance(e, urllib.error.HTTPError):
                raise
            print(f"  transient {type(e).__name__}, retrying once...", flush=True)
            req2 = urllib.request.Request(API, data=body, method="POST")
            req2.add_header("Authorization", f"Bearer {key}")
            req2.add_header("Content-Type", f"multipart/form-data; boundary={boundary}")
            with urllib.request.urlopen(req2, timeout=600) as resp:
                out = json.loads(resp.read())
    except urllib.error.HTTPError as e:
        # Surface the API's own error message (param mismatches differ per model); never the key.
        detail = e.read().decode("utf-8", "replace")[:500]
        sys.exit(f"API {e.code} for model {MODEL}: {detail}")
    spend()
    return base64.b64decode(out["data"][0]["b64_json"])


def crop_for(name: str) -> tuple[Path, tuple[int, int, int, int]]:
    (cx, cy), half, _ = BUILDINGS[name]
    m = Image.open(MAP).convert("RGB")
    x0, y0 = max(0, cx - half), max(0, cy - half)
    x1, y1 = min(m.width, cx + half), min(m.height, cy + half)
    FAITHFUL.mkdir(parents=True, exist_ok=True)
    p = FAITHFUL / f"{name}_crop.png"
    m.crop((x0, y0, x1, y1)).save(p)
    return p, (x0, y0, x1, y1)


def run(name: str, key: str) -> dict:
    _, _, desc = BUILDINGS[name]
    crop_path, box = crop_for(name)
    # Step 1 — detail/upscale, true to the image.
    detailed = edits_call(key, crop_path, DETAIL_PROMPT.format(desc=desc), transparent=False)
    detailed_path = FAITHFUL / f"{name}_detailed.png"
    detailed_path.write_bytes(detailed)
    # Step 2 — cutout on transparency.
    short = desc.replace(" at the center", "")
    cut = edits_call(key, detailed_path, CUTOUT_PROMPT.format(desc_short=short), transparent=True)
    cut_path = FAITHFUL / f"{name}_cut.png"
    cut_path.write_bytes(cut)
    # No native alpha from image-2: key the white background out (tutorial step: KEY->ERODE->BLEED).
    im = Image.open(io.BytesIO(cut)).convert("RGBA")
    if im.getchannel("A").getbbox() == (0, 0, im.width, im.height):
        import subprocess
        KEYED.mkdir(parents=True, exist_ok=True)
        keyed_path = KEYED / f"{name}.png"
        subprocess.run([sys.executable, str(HERE / "key_building.py"), str(cut_path), str(keyed_path),
                        "--white", "222", "--erode", "2"], check=True, capture_output=True)
        im = Image.open(keyed_path).convert("RGBA")
        cut_path = keyed_path
    alpha = im.getchannel("A")
    bbox = alpha.getbbox()
    corners_clear = all(alpha.getpixel(p) < 16 for p in [(0, 0), (im.width - 1, 0), (0, im.height - 1), (im.width - 1, im.height - 1)])
    crop_w = box[2] - box[0]
    ratio = OUT_PX / crop_w                      # output px per crop map-px
    meta = {
        "name": name, "crop_box": box, "out_px": OUT_PX, "ratio": ratio,
        "opaque_bbox": bbox, "corners_clear": corners_clear,
        # Deterministic scene transform (world = map px * 5):
        "world_scale": round(5.0 / ratio, 4),
        "world_center": [
            round((box[0] + ((bbox[0] + bbox[2]) / 2) / ratio) * 5.0, 1),
            round((box[1] + ((bbox[1] + bbox[3]) / 2) / ratio) * 5.0, 1),
        ] if bbox else None,
    }
    (FAITHFUL / f"{name}_meta.json").write_text(json.dumps(meta, indent=1))
    return meta


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--env-file")
    ap.add_argument("--only", action="append")
    args = ap.parse_args()
    key = read_key(args.env_file)
    names = args.only or list(BUILDINGS)
    for n in names:
        if (KEYED / f"{n}.png").exists():
            print(f"[{n}] already keyed — skipped", flush=True)
            continue
        print(f"[{n}] ...", flush=True)
        meta = run(n, key)
        print(f"[{n}] done: opaque={meta['opaque_bbox']} corners_clear={meta['corners_clear']} "
              f"world_scale={meta['world_scale']} world_center={meta['world_center']}", flush=True)
    print(f"budget used: {budget()['used']}/{BUDGET_CAP}")


if __name__ == "__main__":
    main()
