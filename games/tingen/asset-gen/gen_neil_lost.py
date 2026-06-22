#!/usr/bin/env python3
"""Generate 失控 (lost-control) variants of Old Neil's home via gpt-image-1 edits.

Uses the CLEAN neil_home_normal.png as a high-fidelity reference so the room, layout,
top-down camera and painterly game art style are preserved; the 失控 transformation is
described in the prompt. Body-horror can trip moderation, so we send moderation=low and
fall back through progressively softer prompt variants whenever a request is blocked.

Usage:  python3 gen_neil_lost.py [N]      # N candidates, default 15
        python3 gen_neil_lost.py 15 medium
"""
from __future__ import annotations
import os, sys, time, base64
from pathlib import Path
import requests

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
REF = ROOT / "tingen" / "assets" / "backgrounds" / "neil_home_normal.png"
OUT = HERE / "out_neil_lost"
ENV_FILE = Path("/Users/markma/Desktop/Yumina Master/yumina/.env")
API_EDITS = "https://api.openai.com/v1/images/edits"


def load_key() -> str | None:
    k = os.environ.get("OPENAI_API_KEY")
    if k:
        return k.strip()
    try:
        for line in ENV_FILE.read_text().splitlines():
            line = line.strip()
            if line.startswith("#") or "=" not in line:
                continue
            key, _, val = line.partition("=")
            if key.strip() == "OPENAI_API_KEY":
                return val.strip().strip('"').strip("'")
    except OSError:
        pass
    return None


KEY = load_key()

# Keep the room + style; transform the state. Lead with a NON-gory wording (best chance
# past moderation) and escalate to ever-more-abstract/stylized wording if blocked.
_BASE = (
    "Keep the EXACT same room, layout, furniture, top-down camera and painterly video-game "
    "art style as the reference image — a Victorian alchemist's parlor (piano with a portrait "
    "above it, alchemy worktable, cabinet of vials, astrolabe, bookshelves, armchairs, window, "
    "door, wood-plank floor). Same scale, same style. "
)
_STYLE = (
    " Render it in the SAME painterly, slightly gritty top-down game-map style as the reference "
    "— NOT a glossy anime illustration, NOT photo-real; keep the eyes and tendrils STYLIZED and "
    "painterly. Keep the lighting even and readable, like a walkable game floor. No text, no "
    "frame, no border, no other people."
)
VARIANTS = [
    # V0 — evocative but no gore words
    _BASE + (
        "Transform the scene into an eerie occult corruption spreading from the center: a dark "
        "crimson wash creeps across the wood floor, and where the old man sat, a surreal growth "
        "of twisting deep-red tendrils studded with watching eye-like orbs rises into the room — "
        "a haunting dark-fantasy transformation."
    ) + _STYLE,
    # V1 — softer / more abstract
    _BASE + (
        "Transform it into a surreal dark-fantasy occult tableau: stylized deep-red tendrils and "
        "scattered painted eye motifs unfurl from the center of the room, deep crimson tones "
        "pooling across the floor, an unsettling otherworldly atmosphere."
    ) + _STYLE,
    # V2 — most abstract / clearly just stylized art
    _BASE + (
        "Add a stylized, surreal occult-horror motif to the room for a video game: painted "
        "crimson tendrils and abstract eye shapes radiating from the center, deep red shadow "
        "tones, an eerie haunted mood — clearly a stylized game illustration, nothing realistic."
    ) + _STYLE,
]


def gen(prompt: str, quality: str):
    """Return image bytes, the string 'BLOCKED', or None on hard failure."""
    data = {
        "model": "gpt-image-1", "prompt": prompt, "size": "1536x1024",
        "quality": quality, "output_format": "png", "n": "1",
        "input_fidelity": "high", "moderation": "low",
    }
    files = [("image[]", (REF.name, REF.read_bytes(), "image/png"))]
    for attempt in range(4):
        try:
            resp = requests.post(API_EDITS, headers={"Authorization": f"Bearer {KEY}"},
                                 files=files, data=data, timeout=400)
        except (requests.ConnectionError, requests.Timeout) as e:
            print(f"    net error ({e}); wait"); time.sleep(5 * (attempt + 1)); continue
        if resp.status_code == 429:
            print("    rate limited; wait"); time.sleep(15 * (attempt + 1)); continue
        if resp.status_code == 400:
            t = resp.text.lower()
            if any(w in t for w in ("moderation", "safety", "content_policy", "rejected", "blocked", "violat")):
                print(f"    BLOCKED: {resp.text[:140]}")
                return "BLOCKED"
            print(f"    400: {resp.text[:200]}"); return None
        if resp.status_code != 200:
            print(f"    {resp.status_code}: {resp.text[:140]}")
            if resp.status_code >= 500:
                time.sleep(5 * (attempt + 1)); continue
            return None
        try:
            return base64.b64decode(resp.json()["data"][0]["b64_json"])
        except Exception as e:
            print(f"    parse error: {e}"); return None
    return None


def main():
    n = int(sys.argv[1]) if len(sys.argv) > 1 else 15
    quality = sys.argv[2] if len(sys.argv) > 2 else "high"
    if not KEY:
        print(f"ERROR: OPENAI_API_KEY not found (env or {ENV_FILE})"); sys.exit(1)
    if not REF.exists():
        print(f"ERROR: reference not found: {REF}"); sys.exit(1)
    OUT.mkdir(parents=True, exist_ok=True)
    print(f"key loaded ({len(KEY)} chars); ref={REF.name}; target={n} @ {quality} -> {OUT}")
    done = 0; vi = 0; attempts = 0
    while done < n and attempts < n * 3:
        attempts += 1
        prompt = VARIANTS[min(vi, len(VARIANTS) - 1)]
        print(f"[{done + 1}/{n}] variant v{vi} (attempt {attempts})")
        t0 = time.time()
        res = gen(prompt, quality)
        if res == "BLOCKED":
            if vi < len(VARIANTS) - 1:
                vi += 1
                print(f"    -> escalating to softer variant v{vi}")
            else:
                print("    -> already softest variant; retrying")
            continue
        if res is None:
            print("    non-block failure; retrying"); continue
        fp = OUT / f"neil_lost_{done:02d}.png"
        fp.write_bytes(res)
        done += 1
        print(f"    OK {len(res) // 1024}KB {round(time.time() - t0)}s -> {fp.name}")
        time.sleep(0.3)
    print(f"\nDone: {done}/{n} generated in {OUT} (working variant: v{vi})")


if __name__ == "__main__":
    main()
