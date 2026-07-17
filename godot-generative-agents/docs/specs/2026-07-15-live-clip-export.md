# Live-mode clip export — "export last N steps" (#548)

**Date:** 2026-07-15
**Branch:** `feat/live-clip-export-548` → `godot-ga-main`
**Follows:** #488 (baked-replay clip export)

## Goal

Give the live viewer an **"Export last N steps"** affordance that grabs the most
recent N frames of elapsed history as a GIF (and, on desktop, an MP4 + high-quality
GIF via ffmpeg) — reusing #488's capture loop and `clip_export.gd` unchanged.

## Motivation

#488 shipped clip export for **baked replay only**. It marks an in/out span on the
timeline scrubber, but that scrubber is disabled in live mode (`agent_panel.gd`:
you can't scrub toward frames that haven't arrived). Live clips are still feasible
and worthwhile: live mode appends ticks to the **same `_frames[]` array** the baked
path fills (the playhead is just clamped to the live head), so past frames genuinely
exist in memory. "Something cool just happened in the live run — grab it" is a real
demo use case.

Because the span can only cover elapsed steps (bounded by "now"), the affordance is
**"last N"** — a button plus a count input — rather than replay's arbitrary in/out
markers.

## Scope

Godot-only. ~60–80 lines on top of #488. No backend, engine, or Python changes.
Targets `godot-ga-main` (viewer-only change).

**In scope:** a live-mode clip row (count SpinBox + GIF button + MP4+GIF button +
Reveal + status), a pure last-N span helper, and the suspend-polling /
restore-to-head reconciliation that lets the capture loop run without the live poll
snapping the playhead backward.

**Out of scope:** changing the baked-replay clip UI, exporting future/not-yet-arrived
frames, pausing or otherwise touching the backend sim during capture.

## Architecture

Three units, each with one responsibility:

### 1. `godot/scripts/live_clip_span.gd` — pure span arithmetic (NEW)

`extends RefCounted`, static-only, no HTTP or rendering — so it is headless-unit-
testable in isolation, matching the `thinking_indicator.gd` / `live_pacer.gd`
convention.

```gdscript
extends RefCounted
## Pure "last N steps" span arithmetic for live-mode clip export (issue #548).
## No rendering, no HTTP -- headless-testable (tests/test_live_clip_span.gd).

static func span_last_n(head: int, n: int, min_n := 2) -> Dictionary:
    # The clip covers [from, to] over ELAPSED history, ending at the live head.
    #   to   = head
    #   from = max(0, head - n + 1)   (N frames, clamped to the start of history)
    # Returns {} (invalid -- too little history) when head < min_n - 1 or n < min_n.
    if n < min_n or head < min_n - 1:
        return {}
    var to := head
    var from := maxi(0, head - n + 1)
    return {"from": from, "to": to}
```

**Contract:** `head` is the highest valid frame index (`_frames.size() - 1`). `n` is
the requested count. `to` always equals `head`. `from` never goes below 0, so when N
exceeds available history the clip is the whole run. Returns `{}` when there is too
little history to make even a `min_n`-frame clip, or when the requested `n` is below
`min_n`; callers treat `{}` as "not enough yet — do nothing."

### 2. `agent_panel.gd` — the live clip row

Today `set_live(true)` hides the entire baked clip row. Instead, build a **live clip
row** in the constructor immediately after the baked clip row (hidden until
`set_live(true)`, so it sits directly below the baked row in sidebar order), and
toggle it with the existing `visible = live` / `visible = not live` mechanism so
live and replay rows are mutually exclusive. It reuses the baked row's
`_clip_reveal_btn` and the `_clip_status` label below it.

Live clip row layout:

```
[ 60 ▲▼ ]  [ Export last N GIF ]  [ Export last N MP4+GIF ]  [ Reveal ]
saved → …/penn-clips/penn-clip-0340-0400.gif
```

- **`_clip_n_spin: SpinBox`** — `min_value = 2`, `max_value = 2000`, `value = 60`,
  `step = 1`. Its value is the requested N; no clamping-to-history here (the helper
  clamps `from`).
- **`_live_clip_gif_btn: Button`** ("Export last N GIF") — always present. Emits the
  existing `clip_export_requested("gif")` signal.
- **`_live_clip_frames_btn: Button`** ("Export last N MP4+GIF") —
  `visible = not OS.has_feature("web")`. Emits `clip_export_requested("frames")`.
- Both buttons **start disabled** (`disabled = true` in the constructor) and are
  enabled by the viewer once `_frames.size() >= min_n` (piggybacks the per-step
  sidebar update). A new method `set_live_clip_ready(ready: bool)` flips both
  `disabled` flags.
- **Reuses `_clip_status` (Label) and `_clip_reveal_btn` (Button) verbatim** — the
  same "saved → path" line and Reveal-in-Finder button as replay, made `visible` in
  live mode. `set_clip_status(text, reveal_path)` is unchanged.
- **New accessor `live_clip_count() -> int`** returns `int(_clip_n_spin.value)` for
  the viewer to read on export.

`set_live(live)` visibility rules extend the existing block:
- baked clip row (`_clip_gif_btn`, `_clip_frames_btn`): `visible = not live` (today's
  behavior, unchanged).
- live clip row (spin + both live buttons): `visible = live` (built lazily, like the
  live badge).
- `_clip_status`: `visible = true` in both modes (was `not live`; now shared).
- `_clip_reveal_btn`: visibility stays driven by `set_clip_status`'s `reveal_path`.

### 3. `viewer.gd` — capture / live reconciliation

**Preload the helper:** `const LiveClipSpan := preload("res://scripts/live_clip_span.gd")`.

**A capture guard field:** `var _capturing := false`.

**`_capture_span` gains a live restore-to-head path.** Today it does:

```gdscript
var saved_t := _t
var saved_paused := _paused
_paused = true
$UI.visible = false
for step in range(from_step, to_step + 1):
    _t = float(step) * step_seconds
    await RenderingServer.frame_post_draw
    sink.call(step - from_step, get_viewport().get_texture().get_image())
$UI.visible = true
_t = saved_t
_paused = saved_paused
```

Change: set `_capturing = true` at entry and `false` at exit; on exit in live mode,
restore `_t` to the **current live head** rather than `saved_t`, because live frames
kept arriving on the socket during the freeze:

```gdscript
_capturing = true
var saved_t := _t
var saved_paused := _paused
_paused = true
$UI.visible = false
for step in range(from_step, to_step + 1):
    _t = float(step) * step_seconds
    await RenderingServer.frame_post_draw
    sink.call(step - from_step, get_viewport().get_texture().get_image())
$UI.visible = true
_paused = saved_paused
if _is_live:
    _t = float(maxi(_frames.size() - 1, 0)) * step_seconds  # resume at live head
else:
    _t = saved_t
_capturing = false
```

**`_process` skips polling while capturing.** The live branch guards `_poll_ws()`:

```gdscript
if _is_live and not _capturing:
    _poll_ws()
```

Socket records that arrive during the freeze are not lost — the WebSocket buffers
them and the next `_poll_ws()` after the guard lifts drains them; the cursor guard in
`_apply_record` dedups anything that overlaps the HTTP backfill.

**Per-step: keep the live buttons' enabled state honest.** In the per-step sidebar
block (guarded by `i != _last_status_step`), when `_is_live`, call
`_panel.set_live_clip_ready(_frames.size() >= LIVE_CLIP_MIN_N)`. (`const
LIVE_CLIP_MIN_N := 2`.)

**Export dispatch routes on mode.** `clip_export_requested(kind)` now fires in both
modes. The connected handler routes:

```gdscript
func _on_clip_export_requested(kind: String) -> void:
    if _is_live:
        _export_live_clip(kind)
    else:
        _export_clip(kind)  # existing #488 path (marked span), guards on _is_live
```

New `_export_live_clip(kind)`:

```gdscript
func _export_live_clip(kind: String) -> void:
    if not _is_live or _frames.is_empty():
        return
    var head := _frames.size() - 1
    var span := LiveClipSpan.span_last_n(head, _panel.live_clip_count(), LIVE_CLIP_MIN_N)
    if span.is_empty():
        _panel.set_clip_status("Not enough history yet — let the sim run a moment.", "")
        return
    var a: int = span["from"]
    var b: int = span["to"]
    # ... identical to _export_clip's gif / frames bodies, using a and b ...
```

The GIF and frames bodies are the **same** `_capture_span` + `GifEncoder` +
`ClipExport.save_gif` / `make_frame_dir` / `run_ffmpeg` calls #488 already uses.
Factor the shared body of `_export_clip` and `_export_live_clip` into a private
`_render_and_save_clip(a, b, kind)` so the two entry points do not duplicate the ~30
lines of gif/frames/ffmpeg logic (DRY). `_export_clip` keeps its `_is_live` guard and
its "mark a span first" message; `_export_live_clip` keeps the "not enough history"
message; both then call `_render_and_save_clip`.

## Data flow

```
SpinBox value (N)
    │  live_clip_count()
    ▼
_export_live_clip(kind) ──> LiveClipSpan.span_last_n(head, N) ──> {from, to}
    │                                                                │
    │  _capturing = true; _process stops _poll_ws()                  │
    ▼                                                                ▼
_render_and_save_clip(from, to, kind) ──> _capture_span(from, to, sink)
    │                                          (pins _t per step, hides UI)
    ▼
GifEncoder.encode / ClipExport.save_gif|make_frame_dir|run_ffmpeg
    │
    ▼
_panel.set_clip_status("saved → <path>", <reveal_path>)
    │
    ▼  _capturing = false; next _process drains buffered socket records,
       _t resumes at the (grown) live head
```

## Error handling & edge cases

- **N exceeds elapsed history:** `from` clamps to 0 → the clip is the whole run so
  far. No error.
- **Too little history:** helper returns `{}`; buttons are disabled below `min_n`
  frames anyway, and `_export_live_clip` shows a "not enough history yet" status as a
  belt-and-suspenders guard.
- **Frames arriving mid-capture:** polling is suspended (`_capturing`), so `_frames`
  and `last` hold still during the ~1–3 s capture. On resume, buffered socket records
  drain and the playhead jumps to the new head — no backward snap.
- **ffmpeg missing (frames path):** unchanged from #488 — falls back to PNG frames +
  a printed `ffmpeg_command`.
- **Web build:** MP4+GIF button hidden (`OS.has_feature("web")`); GIF button uses the
  browser download flow already in `ClipExport.save_gif`.
- **Backend sim is never touched:** only local polling pauses; the sim keeps ticking
  on its own clock.

## Testing

- **`godot/tests/test_live_clip_span.gd`** (headless `SceneTree`, sentinel
  `test_live_clip_span: all checks passed`, `quit(1 if _failures>0 else 0)`, wired
  into `run_smoke_test.sh`). Table:
  - `span_last_n(0, 60)` → `{}` (head < min_n-1 with default min_n=2? head=0,
    min_n=2 → head < 1 → `{}`).
  - `span_last_n(1, 60)` → `{from:0, to:1}` (exactly min_n frames).
  - `span_last_n(100, 60)` → `{from:41, to:100}` (exact N).
  - `span_last_n(10, 60)` → `{from:0, to:10}` (N exceeds history → whole run).
  - `span_last_n(100, 1)` → `{}` (n below min_n).
  - `span_last_n(100, 2)` → `{from:99, to:100}` (n at min_n boundary).
  - Monotonicity sweep: for head in a range and several N, assert `to == head` and
    `from >= 0` and `from <= to`.
- **Integration (manual):** suspend/restore-to-head and button-enable wiring need
  HTTP + a live head + rendering, so they are not headless-unit-testable. Verify by
  serving a mock live sim (`serve_penn.py --tick-seconds 0.1`), letting ~120 steps
  elapse, clicking **Export last N** (N=60), and confirming: (a) the file lands with a
  `penn-clip-<from>-<to>` name matching the reported span; (b) the playhead resumes at
  the live head afterward (no backward snap); (c) frames that arrived during capture
  are present on resume.
- **`run_smoke_test.sh`** still loads every scene and checks the campus painted
  (exit 0), and now also runs `test_live_clip_span.gd`.

## Files

- **Create:** `godot/scripts/live_clip_span.gd`
- **Create:** `godot/tests/test_live_clip_span.gd`
- **Modify:** `godot/scripts/agent_panel.gd` (live clip row + accessors)
- **Modify:** `godot/scripts/viewer.gd` (helper preload, `_capturing`, capture
  restore-to-head, `_process` poll guard + button-ready, dispatch router,
  `_export_live_clip`, `_render_and_save_clip` refactor)
- **Modify:** `run_smoke_test.sh` (wire the new headless test)
