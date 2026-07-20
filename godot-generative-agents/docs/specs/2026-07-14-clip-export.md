# Clip Export — GIF (one-click, web) + PNG-frames/ffmpeg (desktop) for a step span (#488)

**Issue:** #488 (second half) · **Branch:** `feat/clip-export-488` off `godot-ga-main` ·
**Review track:** godot-ga-main (godot-only — viewer scripts + godot tests).
**Follow-up:** #548 (live-mode "export last N steps"), out of scope here.

## Goal

PR #516 shipped #488's PNG half (one-click Save PNG on a single snapshot). This
spec is the **clip** half: from the **baked-replay** viewer, mark an in/out span
on the timeline and export it as a shareable animated clip — a **one-click
animated GIF** (works on desktop *and* the web build) plus a desktop-only
**"export frames for ffmpeg"** escape hatch for MP4-quality output. Godot has no
built-in video encoder, so the GIF is encoded in pure GDScript and MP4 is handed
off to an external `ffmpeg` command.

## Decisions (locked in brainstorming)

- **Both outputs:** GIF is the one-click default (all platforms); PNG-frames +
  an `ffmpeg` command is a desktop-only option.
- **Span selection:** mark in/out on the existing timeline scrubber.
- **Cadence:** exactly **one captured frame per sim step** (faithful to the data,
  smallest files, fastest capture). Anyone wanting buttery motion uses the
  ffmpeg path.
- **Baked-replay only.** Live-mode clips are filed as #548.

## Current state (verified)

- **Frame-grab primitive** (`viewer.gd:_take_snapshot`, PR #487/#516): hides
  `$UI` chrome, `await RenderingServer.frame_post_draw`, then
  `get_viewport().get_texture().get_image()`. This is exactly the per-frame grab
  a clip needs.
- **Seek-while-paused** (`viewer.gd:_on_seek`): sets `_t = step * step_seconds`;
  `_process` re-renders agent positions from `_frames[]` every frame (tween
  interpolated via `_anim_t`). Guarded `if _is_live: return` — the scrubber is
  disabled in live mode, which is why v1 is baked-only.
- **The IO-seam pattern** (`scripts/snapshot_export.gd`): a scene-free static
  helper owning naming + one IO seam — desktop writes `<Pictures>/penn-snapshots/`,
  web calls `JavaScriptBridge.download_buffer(...)`. Unit-tested headlessly
  (`tests/test_snapshot_export.gd`). The web/desktop `OS.has_feature("web")`
  gate and the "Save all" desktop-only affordance already live in
  `snapshot_gallery.gd`.
- **Playback + timeline UI** live in `agent_panel.gd` (`$UI/AgentPanel`; owns
  `seek_requested`, `set_playing`, `set_timeline_markers`); the timeline strip is
  rendered by `timeline_markers.gd`. This is where in/out handles and the Export
  control go.

## Design

Three new units (each one purpose, well-bounded) + edits to `viewer.gd` and
`agent_panel.gd`.

### 1. `godot/scripts/gif_encoder.gd` (new) — pure encoder, no IO, no scene

`static func encode(frames: Array[Image], delay_cs: int) -> PackedByteArray`.
Bytes-in / bytes-out so it tests in complete isolation. Internals:

- **Global palette.** Median-cut quantization to a *single* ≤256-color palette
  shared across all frames (a per-frame palette would flicker as colors shift
  frame to frame). Pixels are sampled across all frames (every Nth pixel) to
  bound cost.
- **Index mapping.** Each frame's pixels map to the nearest palette entry. **No
  dithering** in v1 (nearest color); banding is an accepted limitation — the
  ffmpeg path is the quality escape hatch.
- **LZW.** Standard GIF variable-width LZW (code width 2..12, clear + end-of-info
  codes, table reset at 4096).
- **GIF89a assembly.** Header, logical screen descriptor, global color table,
  Netscape 2.0 loop extension (loop forever), then per frame a graphic-control
  extension carrying `delay_cs` + an image descriptor, and the `0x3B` trailer.

Callers pass already-downscaled frames; the encoder does not resize (keeps it a
pure codec). ~350 lines.

### 2. `godot/scripts/clip_export.gd` (new) — IO seam + naming (mirrors `snapshot_export.gd`)

Scene-free static helper. Owns where files go and what they're named:

- `save_gif(bytes: PackedByteArray, span_label: String, dir_override := "") -> String`
  — desktop writes `<Pictures>/penn-clips/penn-clip-<start>-<end>.gif`; web hands
  the buffer to `JavaScriptBridge.download_buffer(bytes, fname, "image/gif")`.
  Returns the absolute path (desktop), the download file name (web), or `""` on
  failure with a pushed error — same contract as `snapshot_export.save`.
- `save_frame(img: Image, dir: String, index: int) -> bool` — writes one
  `frame_0000.png` (zero-padded) into an already-created clip dir. The frames
  sink calls this per grab so full-res frames are never all held in memory.
- `save_frames(frames: Array[Image], span_label: String, dir_override := "") -> String`
  — **desktop only**: creates `penn-clips/penn-clip-<start>-<end>/`, loops
  `save_frame` over the array, returns the directory (or `""` on failure). The
  batch wrapper is what the headless test drives (small synthetic arrays); the
  live sink uses `mk` + `save_frame` per grab.
- `ffmpeg_command(dir: String) -> String` — the ready-to-paste command(s): a GIF
  variant (palettegen/paletteuse) and an MP4 variant (libx264, yuv420p). Surfaced
  in the UI status line and echoed to the console.
- `file_name` / `dir_name` helpers zero-pad and slug the span the way
  `snapshot_export.file_name` does.

### 3. Capture loop in `viewer.gd`

`_capture_span(from_step: int, to_step: int, sink: Callable) -> void` (a
coroutine):

1. Suspend playback and remember the current `_t`; hide `$UI` chrome (the
   `_take_snapshot` recipe).
2. For `step` in `[from_step, to_step]`: set `_t = step * step_seconds` with the
   tween forced to the step's end (no partial interpolation — one clean frame per
   step), `await RenderingServer.frame_post_draw`, grab
   `get_viewport().get_texture().get_image()`, and `sink.call(step, img)`.
3. Always restore chrome, `_t`, and playback (cleanup runs even on early return).

The **`sink` Callable** is the seam that keeps `viewer.gd` format-agnostic and
memory bounded:

- **GIF sink** downscales each grab to ≤640px wide (16:9 → 640×360) and appends
  to a local array (~100 frames ≈ ~90 MB, fine), then on completion calls
  `gif_encoder.encode(frames, 10)` → `clip_export.save_gif(...)`.
- **Frames sink** creates the clip dir once, then calls
  `clip_export.save_frame(img, dir, step)` on each grab (never holds the full-res
  array), and on completion reports the dir + `ffmpeg_command`.

Because chrome is hidden for the whole capture, there is no per-frame progress
overlay (it would land in the grab). The UI shows an "Exporting N frames…" status
before the loop and the result after (~1–3 s for a typical span).

### 4. UI (in `agent_panel.gd` / `timeline_markers.gd`)

- **In/out handles** on the timeline strip: **`[`** sets clip-start, **`]`** sets
  clip-end at the current playhead; the marked span highlights on the strip
  (reuses the `timeline_markers.gd` render path). Emits a signal the viewer reads
  for the export span.
- **Export control** on the playback row with two items: **Export GIF** (all
  platforms) and **Export frames for ffmpeg** (desktop only — hidden on web via
  the same `OS.has_feature("web")` gate as "Save all"). Disabled until a valid
  span (start ≤ end) is marked.
- **Feedback:** "Exporting N frames…" then "saved → \<path\>" with a
  Reveal-in-Finder button on desktop — the same status/Reveal idiom as the
  gallery detail view.
- **Defaults, no knobs (YAGNI):** GIF 10 fps (`delay_cs = 10`; browsers clamp
  sub-20 ms delays anyway), 640px wide, loop forever.

## Verification

Headless where possible (following `test_snapshot_export.gd`); the capture loop
itself needs a real renderer, so it rides the existing windowed smoke path.

- **`tests/test_gif_encoder.gd`** (headless): encode a few tiny synthetic
  `Image`s → assert `GIF89a` magic, a global color table of ≤256 entries, N
  graphic-control blocks for N frames, the Netscape loop extension present, the
  `0x3B` trailer; **LZW round-trip** — decode one frame's compressed stream back
  to the source index array; median-cut on a >256-color gradient collapses to
  ≤256 colors.
- **`tests/test_clip_export.gd`** (headless): span → `file_name` / `dir_name`
  shape; `save_frames` with `dir_override` writes N correctly-named, zero-padded
  PNGs; `ffmpeg_command` string shape (references the dir, emits both GIF and MP4
  variants). GIF byte-writing shares `save_gif` output with the encoder test.
- **Capture loop:** covered by the windowed smoke test (`run_smoke_test.sh`
  path), not a headless unit test — noted explicitly because `--headless`
  can't read the framebuffer. The spec does **not** claim headless coverage of
  `_capture_span`.
- **Full suites** + `uv run black .` (no Python changed here, but the geo/CI
  gate runs it) + headless smoke (scenes still load & paint).
- **User visual pass:** mark a span, Export GIF, confirm the `.gif` loops and
  reads well; Export frames + run the printed `ffmpeg` command → an MP4.

## Out of scope

- **MP4 encoding inside Godot** — handed off to the printed `ffmpeg` command.
- **Live-mode clip export** — #548 ("export last N steps" from elapsed history).
- Dithering; per-frame (vs global) palette; arbitrary fps/resolution/quality
  knobs; audio; any change to `snapshot_export.gd`, `snapshot_gallery.gd`, the
  sim, or the backend.
