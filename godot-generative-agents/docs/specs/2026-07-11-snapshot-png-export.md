# Snapshot PNG Export (#488, PNG half)

**Issue:** #488 · **Branch:** `feat/snapshot-png-export-488` off `godot-ga-main` ·
**Review track:** godot-ga-main (viewer GDScript + smoke script only; no Python).

## Goal

PR #487's snapshot gallery captures the campus view into an in-memory pop-up —
deliberately with no file export. This ships the export half of #488: a saved
snapshot can leave the viewer as a PNG on disk (desktop) or as a browser
download (web build). The clip-export half (GIF/MP4 of a step span) stays in
#488 — out of scope here.

## Current state (verified)

- The gallery (`scripts/snapshot_gallery.gd`) stores one entry per capture:
  `{texture: Texture2D, label: String}` — full-resolution `ImageTexture`s, so
  the `Image` is recoverable via `texture.get_image()`. Its docstring notes
  "no file export yet" (line 9-10).
- Capture (`viewer.gd:1441`) hides the UI chrome, reads the viewport, and
  hands `ImageTexture.create_from_image(img)` plus a world-time label to
  `add_snapshot`. The label format (`_format_sim_time`, `viewer.gd:1015`) is
  `"Jul 9, 2026, 09:12:00"` (month day, year, HH:MM:SS).
- Gallery views: a thumbnail grid with a title row (Close button), and a
  detail (enlarged) view with a caption and a "Back to all" button
  (`_show_grid` / `_show_detail`).
- `scripts/snapshot.gd` (the dev screenshot utility) shows the
  `Image.save_png()` idiom.
- The web build is real: `export_presets.cfg` has a Web preset, and
  `viewer.gd` already branches on `OS.has_feature("web")` (`_is_web`,
  line 354) and calls `JavaScriptBridge` (line 1671). Godot 4 provides
  `JavaScriptBridge.download_buffer(buffer, name, mime)` — the browser
  download path the issue calls for.
- `run_smoke_test.sh` runs two headless unit-test scripts, each gated by the
  `tee /dev/stderr | grep -q "all checks passed"` sentinel (lines 39-41);
  this feature adds a third.

## Design

### 1. Export helper — `scripts/snapshot_export.gd` (new)

A static helper (no scene node), the `replay_markers.gd`/`day_plan_model.gd`
pattern:

- `static func file_name(index: int, label: String) -> String` — pure,
  testable. Returns `penn-snapshot-%02d-<slug>.png` where slug = the label
  lowercased with every non-alphanumeric run collapsed to a single `-` and
  trimmed (e.g. index 3 + `"Jul 9, 2026, 09:12:00"` →
  `penn-snapshot-03-jul-9-2026-09-12-00.png`). Deterministic per
  (index, label), so re-saving the same shot overwrites instead of
  duplicating; the zero-padded index keeps a directory listing in capture
  order.
- `static func save(texture: Texture2D, index: int, label: String,
  dir_override := "") -> String` — the one IO seam:
  - **Web** (`OS.has_feature("web")`, and only when `dir_override` is
    empty): `texture.get_image().save_png_to_buffer()` →
    `JavaScriptBridge.download_buffer(buf, file_name(...), "image/png")`;
    returns the file name (the browser owns the destination).
  - **Desktop:** target directory =
    `OS.get_system_dir(OS.SYSTEM_DIR_PICTURES) + "/penn-snapshots"`, falling
    back to `user://snapshots` when the OS reports no Pictures dir (some
    minimal Linux setups); `dir_override` (used by the headless test)
    replaces the whole directory choice. Ensure it exists
    (`DirAccess.make_dir_recursive_absolute`), `save_png` the image, and
    return the **globalized absolute path** for display.
  - Any failure (`make_dir_recursive_absolute` / `save_png` error, null
    image): `push_error` with the error code and return `""`.

### 2. Gallery buttons — `snapshot_gallery.gd`

- **Detail view:** a "Save PNG" button beside "Back to all". On success the
  caption area shows `saved → <returned path>` and, desktop only, a
  "Reveal in Finder" button appears next to it
  (`OS.shell_show_in_file_manager(path)` for the last saved path); on web
  the reveal button never shows (the browser surfaces the download). On
  failure the caption shows `save failed — see console`.
- **Grid view:** a "Save all" button in the title row before Close, desktop
  only (N programmatic `download_buffer` calls trip browser popup blockers,
  so the web build hides it — per-shot saving covers it there). Saves every
  shot through the same helper; the title-row status shows
  `N saved → <directory>` (or `M of N saved — see console` if any failed).
  Hidden while the gallery is empty.
- The saved-status texts reset when the view switches (grid ↔ detail) or a
  new snapshot arrives — stale "saved" claims must not linger over a
  different shot.
- Update the docstring: "no file export yet" → describes PNG save + the
  clip-export follow-up staying in #488.

### 3. No viewer.gd changes

Capture, hotkeys, and modal behavior are untouched; the feature is
gallery-internal plus the new helper.

### 4. Out of scope

- Clip export (GIF/MP4) — remains the other half of #488.
- A native save dialog or per-shot custom naming (auto-save to Pictures was
  the chosen UX).
- Any capture-path change (resolution, chrome hiding, world overlays).

## Verification

- New headless unit test `godot/tests/test_snapshot_export.gd`
  (`SceneTree`-script pattern from #508): `file_name` cases (slugging,
  zero-padding, determinism, empty label) and an end-to-end save — build a
  small `Image` (e.g. 4×4 filled), wrap in `ImageTexture`, call
  `save(..., dir_override="user://test_snapshots")`, assert the file exists
  and `Image.load` reads it back; clean up after. Prints
  `test_snapshot_export: all checks passed` and `quit(0)` on success.
- `run_smoke_test.sh`: add the third sentinel-guarded line running that
  script.
- `./godot-generative-agents/run_smoke_test.sh` passes end-to-end.
- Manual, desktop: capture two shots → detail Save PNG lands the file in
  `~/Pictures/penn-snapshots/` with the expected name, Reveal opens Finder
  on it, Save all writes both, re-saving overwrites (no duplicates).
- Web build behavior (download path, hidden Save all/Reveal) is
  code-reviewed but not manually gated — no web build in the local loop.
