# godot-generative-agents

A tiny [Godot 4.6](https://godotengine.org) sandbox that proves we can pull the
**Cute Fantasy** sprite pack into Godot and drive characters around. Right now the
characters just **wander on their own** — no player controls. The name signals where
this is headed: the same auto-moving sprites are the substrate that LLM-driven agents
(the rest of this repo) could later steer.

## What's in the scene

`scenes/main.tscn` puts four sprites on a grass-green background, each running
`scripts/wanderer.gd`:

| Node     | Sheet                                  | What it does                     |
|----------|----------------------------------------|----------------------------------|
| Player   | `Cute_Fantasy_Free/Player/Player.png`  | walks to random points           |
| Skeleton | `Cute_Fantasy_Free/Enemies/Skeleton.png` | walks to random points         |
| Pig      | `Cute_Fantasy_Free/Animals/Pig/Pig.png` | trots to random points          |
| Slime    | `Cute_Fantasy_Free/Enemies/Slime_Green.png` | hops to random points       |

Each one eases toward a random target, picks a new one on arrival, flips to face its
direction of travel, and plays a walk/hop animation by stepping through one row of its
sprite sheet.

## How it works (the one script)

A sprite sheet is a grid of small frames. `wanderer.gd` hangs off a plain `Sprite2D`
and is configured per-character in the scene via exported variables:

- `sheet_hframes` / `sheet_vframes` — the sheet's grid (columns × rows)
- `walk_row` / `walk_len` — which row is the walk cycle and how many frames it has
- `anim_fps`, `move_speed`, `arrive_dist` — animation/movement tuning

In `_ready()` it slices the sheet (`hframes`/`vframes`) and picks a first target; in
`_process()` it moves, flips, and advances the animation frame. No `AnimationPlayer`
or `SpriteFrames` resource — it's all a few lines of readable code, so it's easy to
follow and easy to extend (e.g. replace `_pick_target()` with an agent's decision).

## Running it

Open the project folder in the Godot 4.6 editor and press **Play** (F5), or from a
terminal:

```bash
# Windowed (watch them wander):
/Applications/Godot.app/Contents/MacOS/Godot --path .

# Headless smoke test (imports + runs ~300 frames, then quits):
/Applications/Godot.app/Contents/MacOS/Godot --headless --path . --import
/Applications/Godot.app/Contents/MacOS/Godot --headless --path . --quit-after 300
```

The first run regenerates the `.godot/` import cache (git-ignored); the committed
`*.import` / `*.uid` sidecars let Godot recognize the assets without re-importing
everything.

## Assets & license

Art is the **Cute Fantasy (Free)** pack by Kenmi, kept under `Cute_Fantasy_Free/`
with its original `read_me.txt`. Per that license it is **free for non-commercial use
and may be modified, but not redistributed or resold**. It lives here only for this
private research repo.
