# Godot viewer: auto reset-follow on `POST /reset` (#393)

## Problem

When the backend broadcasts a `status` change-feed record with `reason: "reset"` (a
`POST /reset` restarted the run into a new day), the live viewer currently just tells
the user to reload: `viewer.gd:727` sets the status line to *"backend reset — reload
the viewer to follow the new run."* The backend keeps running the new day; the viewer
should follow it automatically. This was a documented v1 limitation when #380 landed.

(The issue references `scripts/penn_replay.gd ~L610`; the viewer was since restructured
— the live logic now lives in `godot-generative-agents/godot/scripts/viewer.gd`, and the
spawn path the issue calls `_apply_meta()` is there.)

## Why in-place (not a scene reload)

`POST /reset` **appends** a `reason:"reset"` status record to the change-feed and does
**not** clear it (`backend/api.py:1044`; "cursors stay monotonic across reset"). A fresh
viewer backfills `?since=0` (`_last_cursor` starts at `-1`), so a scene reload would
replay the whole retained feed — re-hitting the reset record (reload loop) and replaying
old-run then new-run frames into the same step-indexed `_frames` (mangled clock/frames).
Keeping the viewer alive and **keeping `_last_cursor`** sidesteps all of that: new-run
frames (cursor > reset) flow into a freshly-cleared `_frames` from step 0, on the same
open socket. (Decided in brainstorming, 2026-07-09.)

## Design

All in `godot-generative-agents/godot/`.

### `viewer.gd`

1. **Extract `_spawn_from_meta(meta)`** from the existing handshake block (currently
   inline at ~588–597: `_apply_meta(meta)` + `_heatmap.set_replay` + `_social_graph.set_replay`
   + `_hud_source.set_cast` + `_update_clock`). The handshake keeps its guard:
   `if _names.is_empty(): _spawn_from_meta(meta)`. Reused by the reset path so a reset
   spawns identically to a fresh join (DRY).

2. **`_reset_for_new_run()`**, called from the `"reset"` case of `_on_live_status`
   (replacing the reload message):
   - **Teardown** (order matters — release the camera before freeing its target):
     stop the camera follow and set `_tracked_name = ""`; `queue_free()` each
     `_agents[name]["node"]` and clear `_agents`, `_names`, `_persona_detail`,
     `_relationships`; `_minimap.clear()`; `_panel.clear_characters()`;
     `_frames.clear()` **in place** (preserves the heatmap/social by-reference handoff);
     reset `_live_buildings = {}`, `_live_started = false`, `_t = 0.0`,
     `_last_status_step = -1`.
   - **Keep** `_last_cursor` and the open WebSocket untouched.
   - **Re-fetch** `GET /live` on a dedicated one-shot `HTTPRequest`; on HTTP 200 with a
     dictionary `meta`, call `_spawn_from_meta(meta)` and set the status line to
     "following the new run". On non-200 / bad body, warn and leave the status informative
     (the socket keeps delivering; a retry can piggyback the existing handshake-retry
     helper if desired).

### `minimap.gd`

Add `clear()` → `_agents.clear()`. Dots are redrawn from `_agents` every `_process`, so
clearing the array removes them next frame.

### `agent_panel.gd`

Add `clear_characters()` → `queue_free()` each `_rows[name]["row"]`, clear `_rows`, and
reset `_active = ""`. (Distinct from the existing `clear_active()`, which only drops the
current selection.)

### Heatmap / social graph

No new API: `_spawn_from_meta` re-calls their existing `set_replay(_frames, _names, …)`,
which re-initializes them against the emptied-then-refilled `_frames` — the same call the
fresh join makes.

## Verification (offline, mock brain — no LLM, per the issue)

- `./godot-generative-agents/run_smoke_test.sh` — every scene still loads and its campus
  map paints (no regression / no crash from the new teardown + helper).
- Manual: serve `serve_penn.py --brain mock`, open the viewer in live mode, `POST /reset`,
  and confirm: the cast respawns **once** (no doubling), the clock resets to the new day,
  the run keeps following — with **no manual reload**.

## Risks

- **Incomplete teardown** → double cast or stale trails/dots. Mitigation: the holder list
  above is exhaustive (cast dicts, agent nodes, minimap, sidebar rows, frames, buildings,
  camera focus, playhead); the manual eyeball catches a miss the smoke test can't.
- **Freeing the camera's tracked node before releasing it** → dangling reference. Mitigation:
  the teardown releases the follow and clears `_tracked_name` first.

## Acceptance (from #393)

- After a `POST /reset`, the open viewer transitions to the new run automatically (agents
  respawn, clock resets) — no manual reload.
- Smoke test passes with and without a backend.
- Target branch: `godot-ga-main`.
