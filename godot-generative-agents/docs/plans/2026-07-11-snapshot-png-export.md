# Snapshot PNG Export (#488, PNG half) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Let a gallery snapshot leave the viewer as a PNG — auto-saved to `~/Pictures/penn-snapshots/` on desktop, a browser download on the web build.

**Architecture:** A new scene-free static helper `snapshot_export.gd` owns naming (`file_name`) and the one IO seam (`save`: desktop write vs. `JavaScriptBridge.download_buffer`). `snapshot_gallery.gd` grows a "Save PNG" + "Reveal in Finder" pair on the detail view and a desktop-only "Save all" on the grid's title row. `viewer.gd` is untouched.

**Tech Stack:** Godot 4.6 GDScript; headless `SceneTree`-script unit tests gated by `run_smoke_test.sh`'s success-sentinel grep.

**Spec:** `godot-generative-agents/docs/specs/2026-07-11-snapshot-png-export.md`

## Global Constraints

- Branch: `feat/snapshot-png-export-488` (off `godot-ga-main`); touch ONLY `godot-generative-agents/godot/scripts/snapshot_export.gd` (new), `godot-generative-agents/godot/tests/test_snapshot_export.gd` (new), `godot-generative-agents/godot/scripts/snapshot_gallery.gd`, and `godot-generative-agents/run_smoke_test.sh`.
- NEVER `git add -A` or `git add .` — the checkout carries unrelated uncommitted files (including auto-generated `.uid` files — do NOT stage those). Add exact paths only.
- Every commit message ends with: `Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>`
- GDScript files in this repo are **tab-indented** — use tabs, not spaces.
- File names must be deterministic per (index, label): `penn-snapshot-%02d-<slug>.png` — re-saving overwrites.
- Desktop destination: `OS.get_system_dir(OS.SYSTEM_DIR_PICTURES)` + `/penn-snapshots`, fallback `user://snapshots` when the OS reports no Pictures dir. Web (`OS.has_feature("web")`): `JavaScriptBridge.download_buffer(..., "image/png")`; "Save all" and "Reveal in Finder" never show on web.
- Run everything from the repo root: `/Users/yh/Documents/GitHub/agent-sandbox`. Godot is on PATH as `godot` (or the macOS app bundle — `run_smoke_test.sh` shows the lookup).

---

### Task 1: `snapshot_export.gd` + headless test + smoke wiring

**Files:**
- Create: `godot-generative-agents/godot/scripts/snapshot_export.gd`
- Create: `godot-generative-agents/godot/tests/test_snapshot_export.gd`
- Modify: `godot-generative-agents/run_smoke_test.sh` (after the `test_day_plan_model.gd` block, ~line 41)

**Interfaces:**
- Consumes: nothing project-specific (Godot built-ins only).
- Produces (Task 2 relies on these exact signatures):
  - `static func file_name(index: int, label: String) -> String`
  - `static func save(texture: Texture2D, index: int, label: String, dir_override := "") -> String` — returns the absolute path (desktop), the bare file name (web), or `""` on failure.

- [ ] **Step 1: Write the failing test**

Create `godot-generative-agents/godot/tests/test_snapshot_export.gd` (tabs!):

```gdscript
extends SceneTree
## Headless unit tests for scripts/snapshot_export.gd (issue #488). Run:
##   godot --headless --path godot-generative-agents/godot \
##     --script res://tests/test_snapshot_export.gd
## Exit 0 = all checks pass; run_smoke_test.sh runs this before the scene smoke
## and also greps for the success sentinel (Godot can exit 0 on a parse error).

const SnapshotExport := preload("res://scripts/snapshot_export.gd")

const TEST_DIR := "user://test_snapshots"

var _failures := 0


func _check(cond: bool, name: String) -> void:
	if cond:
		print("  ok: %s" % name)
	else:
		_failures += 1
		push_error("FAIL: %s" % name)


func _initialize() -> void:
	# --- file_name ---
	_check(SnapshotExport.file_name(3, "Jul 9, 2026, 09:12:00")
		== "penn-snapshot-03-jul-9-2026-09-12-00.png",
		"file_name slugs the world-time label")
	_check(SnapshotExport.file_name(3, "Jul 9, 2026, 09:12:00")
		== SnapshotExport.file_name(3, "Jul 9, 2026, 09:12:00"),
		"file_name is deterministic (re-save overwrites)")
	_check(SnapshotExport.file_name(0, "") == "penn-snapshot-00.png",
		"empty label -> index-only name")
	_check(SnapshotExport.file_name(12, "  ··weird—label!! ")
		== "penn-snapshot-12-weird-label.png",
		"non-alphanumeric runs collapse to single dashes, edges trimmed")

	# --- save(): a real end-to-end write via dir_override ---
	var img := Image.create(4, 4, false, Image.FORMAT_RGBA8)
	img.fill(Color(0.2, 0.6, 0.9))
	var tex := ImageTexture.create_from_image(img)
	var path := SnapshotExport.save(tex, 1, "Jul 9, 2026, 09:12:00", TEST_DIR)
	_check(path != "", "save returns a path")
	_check(path.ends_with("penn-snapshot-01-jul-9-2026-09-12-00.png"),
		"saved file carries the deterministic name")
	_check(FileAccess.file_exists(TEST_DIR.path_join(
		"penn-snapshot-01-jul-9-2026-09-12-00.png")), "the PNG exists on disk")
	var back := Image.new()
	_check(back.load(path) == OK and back.get_width() == 4,
		"the PNG loads back at the captured size")
	# The failure contract ("" + a console error). The ERROR line this prints
	# is expected output, not a test failure.
	_check(SnapshotExport.save(null, 2, "x", TEST_DIR) == "",
		"null texture -> empty path (failure signaled)")

	# Clean up the scratch dir so reruns start fresh.
	DirAccess.remove_absolute(TEST_DIR.path_join(
		"penn-snapshot-01-jul-9-2026-09-12-00.png"))
	DirAccess.remove_absolute(TEST_DIR)

	if _failures == 0:
		print("test_snapshot_export: all checks passed")
	quit(1 if _failures > 0 else 0)
```

- [ ] **Step 2: Run it to verify it fails**

Run:
```bash
godot --headless --path godot-generative-agents/godot --script res://tests/test_snapshot_export.gd 2>&1 | tee /dev/stderr | grep -q "all checks passed"; echo "exit=$?"
```
Expected: `exit=1` — Godot prints a load/parse error because `res://scripts/snapshot_export.gd` doesn't exist yet, and the success sentinel never appears. (Godot itself may still exit 0 on a script load error — that's exactly why the smoke gate greps the sentinel.)

- [ ] **Step 3: Write the implementation**

Create `godot-generative-agents/godot/scripts/snapshot_export.gd` (tabs!):

```gdscript
extends RefCounted
## Saves gallery snapshots as PNGs (issue #488, the PNG half). Scene-free
## static helper (the replay_markers.gd pattern): snapshot_gallery.gd owns the
## buttons, this file owns the naming and the one IO seam. Desktop builds
## write into <Pictures>/penn-snapshots/ (names are deterministic, so
## re-saving a shot overwrites its earlier file); the web build hands the
## encoded PNG to the browser's download flow instead. Unit-tested headlessly
## (tests/test_snapshot_export.gd).

const DIR_NAME := "penn-snapshots"


static func file_name(index: int, label: String) -> String:
	# penn-snapshot-<index>-<slug>.png. The label is the capture's world-time
	# caption ("Jul 9, 2026, 09:12:00"); every non-alphanumeric run collapses
	# to one dash. Zero-padding keeps a directory listing in capture order.
	var re := RegEx.create_from_string("[^a-z0-9]+")
	var slug := re.sub(label.to_lower(), "-", true).lstrip("-").rstrip("-")
	if slug == "":
		return "penn-snapshot-%02d.png" % index
	return "penn-snapshot-%02d-%s.png" % [index, slug]


static func save(texture: Texture2D, index: int, label: String, dir_override := "") -> String:
	# Returns where the PNG went: an absolute path on desktop, the download's
	# file name on web, or "" on failure (with the reason pushed as an error).
	# `dir_override` (the headless test) replaces the whole directory choice
	# and forces the disk path even under a web build.
	if texture == null:
		push_error("snapshot_export: no texture to save")
		return ""
	var img := texture.get_image()
	if img == null:
		push_error("snapshot_export: texture has no image")
		return ""
	var fname := file_name(index, label)
	if dir_override == "" and OS.has_feature("web"):
		# The browser owns the destination; it surfaces its own download UI.
		JavaScriptBridge.download_buffer(img.save_png_to_buffer(), fname, "image/png")
		return fname
	var dir := dir_override
	if dir == "":
		var pictures := OS.get_system_dir(OS.SYSTEM_DIR_PICTURES)
		# Some minimal Linux setups report no Pictures dir; fall back to the
		# app's own user:// space rather than failing the save.
		dir = pictures.path_join(DIR_NAME) if pictures != "" else "user://snapshots"
	var err := DirAccess.make_dir_recursive_absolute(dir)
	if err != OK and err != ERR_ALREADY_EXISTS:
		push_error("snapshot_export: cannot create %s (%d)" % [dir, err])
		return ""
	var path := dir.path_join(fname)
	err = img.save_png(path)
	if err != OK:
		push_error("snapshot_export: save failed for %s (%d)" % [path, err])
		return ""
	# user:// paths globalize to a real OS path for display/Reveal; an already
	# absolute Pictures path passes through unchanged.
	return ProjectSettings.globalize_path(path)
```

- [ ] **Step 4: Run the test to verify it passes**

Run:
```bash
godot --headless --path godot-generative-agents/godot --script res://tests/test_snapshot_export.gd
```
Expected: nine `  ok: …` lines, one expected `ERROR: snapshot_export: no texture to save` line (from the failure-contract check), then `test_snapshot_export: all checks passed`, exit 0.

- [ ] **Step 5: Wire it into the smoke gate**

In `godot-generative-agents/run_smoke_test.sh`, directly after the `test_day_plan_model.gd` two-line block, insert:

```bash
"$GODOT" --headless --path "$PROJECT_DIR" --script res://tests/test_snapshot_export.gd 2>&1 \
  | tee /dev/stderr | grep -q "all checks passed"
```

- [ ] **Step 6: Run the full smoke test**

Run:
```bash
./godot-generative-agents/run_smoke_test.sh
```
Expected: all three unit scripts' sentinels print, then `smoke_test: PASS — 4 scene(s) OK`, exit 0.

- [ ] **Step 7: Commit**

```bash
git add godot-generative-agents/godot/scripts/snapshot_export.gd godot-generative-agents/godot/tests/test_snapshot_export.gd godot-generative-agents/run_smoke_test.sh
git commit -m "feat(viewer): snapshot_export helper — deterministic PNG naming + save seam (#488)

Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>"
```

---

### Task 2: Save buttons in the snapshot gallery

**Files:**
- Modify: `godot-generative-agents/godot/scripts/snapshot_gallery.gd` (232 lines; edits anchored below)

**Interfaces:**
- Consumes (from Task 1): `SnapshotExport.save(texture: Texture2D, index: int, label: String, dir_override := "") -> String` — `""` means failure; on desktop the return is an absolute path suitable for `OS.shell_show_in_file_manager`.
- Produces: UI only — no new public API on the gallery.

- [ ] **Step 1: Apply the seven edits**

All edits are to `godot-generative-agents/godot/scripts/snapshot_gallery.gd` (tabs!).

**Edit A — docstring (lines 9-10).** Replace:

```gdscript
## knows nothing about the sim. Snapshots live only in memory for the session (there's
## no file export yet -- that's a separate, lower-priority follow-up).
```

with:

```gdscript
## knows nothing about the sim. Snapshots live in memory for the session; the detail
## view's Save PNG (and the grid's desktop-only Save all) export them via
## scripts/snapshot_export.gd (issue #488 -- desktop writes to Pictures/penn-snapshots,
## the web build downloads). Clip export (GIF/MP4) stays a #488 follow-up.
```

**Edit B — preload.** After the `const COLUMNS := 3` line, insert:

```gdscript

const SnapshotExport := preload("res://scripts/snapshot_export.gd")
```

**Edit C — state.** After the `var _detail_index := -1  # which snapshot ...` line, insert:

```gdscript
var _last_saved_path := ""  # the detail view's last successful save, for Reveal
```

**Edit D — widget vars.** Replace:

```gdscript
var _detail_image: TextureRect
var _detail_caption: Label
```

with:

```gdscript
var _detail_image: TextureRect
var _detail_caption: Label
var _save_btn: Button
var _reveal_btn: Button
var _save_status: Label
var _save_all_btn: Button
var _grid_status: Label
```

**Edit E — title row (grid's Save all + status).** Replace:

```gdscript
	title_row.add_child(_title)

	var close_btn := Button.new()
```

with:

```gdscript
	title_row.add_child(_title)

	# Grid-view export status ("3 saved -> ...") sits left of the buttons.
	_grid_status = Label.new()
	_grid_status.add_theme_color_override("font_color", INK_DIM)
	_grid_status.add_theme_font_size_override("font_size", 13)
	title_row.add_child(_grid_status)

	_save_all_btn = Button.new()
	_save_all_btn.text = "Save all"
	_save_all_btn.tooltip_text = "Save every snapshot as a PNG (Pictures/penn-snapshots)"
	_save_all_btn.focus_mode = Control.FOCUS_NONE
	_save_all_btn.pressed.connect(_save_all)
	title_row.add_child(_save_all_btn)

	var close_btn := Button.new()
```

**Edit F — detail-view buttons + status.** Replace:

```gdscript
	_detail_caption = Label.new()
	_detail_caption.add_theme_color_override("font_color", INK)
	_detail_caption.horizontal_alignment = HORIZONTAL_ALIGNMENT_CENTER
	_detail_caption.size_flags_horizontal = Control.SIZE_EXPAND_FILL
	_detail.add_child(_detail_caption)

	var back_btn := Button.new()
	back_btn.text = "‹  Back to all"
	back_btn.focus_mode = Control.FOCUS_NONE
	back_btn.size_flags_horizontal = Control.SIZE_SHRINK_CENTER
	back_btn.pressed.connect(_show_grid)
	_detail.add_child(back_btn)
```

with:

```gdscript
	_detail_caption = Label.new()
	_detail_caption.add_theme_color_override("font_color", INK)
	_detail_caption.horizontal_alignment = HORIZONTAL_ALIGNMENT_CENTER
	_detail_caption.size_flags_horizontal = Control.SIZE_EXPAND_FILL
	_detail.add_child(_detail_caption)

	# Save / Reveal / Back on one centered row; the status line under it says
	# where the PNG went (issue #488).
	var btn_row := HBoxContainer.new()
	btn_row.add_theme_constant_override("separation", 8)
	btn_row.alignment = BoxContainer.ALIGNMENT_CENTER
	_detail.add_child(btn_row)

	_save_btn = Button.new()
	_save_btn.text = "Save PNG"
	_save_btn.focus_mode = Control.FOCUS_NONE
	_save_btn.pressed.connect(_save_current)
	btn_row.add_child(_save_btn)

	_reveal_btn = Button.new()
	_reveal_btn.text = "Reveal in Finder"
	_reveal_btn.focus_mode = Control.FOCUS_NONE
	_reveal_btn.visible = false
	_reveal_btn.pressed.connect(_reveal_last)
	btn_row.add_child(_reveal_btn)

	var back_btn := Button.new()
	back_btn.text = "‹  Back to all"
	back_btn.focus_mode = Control.FOCUS_NONE
	back_btn.pressed.connect(_show_grid)
	btn_row.add_child(back_btn)

	_save_status = Label.new()
	_save_status.add_theme_color_override("font_color", INK_DIM)
	_save_status.add_theme_font_size_override("font_size", 13)
	_save_status.horizontal_alignment = HORIZONTAL_ALIGNMENT_CENTER
	_save_status.size_flags_horizontal = Control.SIZE_EXPAND_FILL
	_detail.add_child(_save_status)
```

(Note `back_btn` loses its `size_flags_horizontal` line — the row centers it now.)

**Edit G — `_show_grid` resets.** Replace:

```gdscript
func _show_grid() -> void:
	_detail_index = -1
	_detail.visible = false
	_grid_scroll.visible = not _shots.is_empty()
	_empty.visible = _shots.is_empty()
	_title.text = "Snapshots  (%d)" % _shots.size()
```

with:

```gdscript
func _show_grid() -> void:
	_detail_index = -1
	_detail.visible = false
	_grid_scroll.visible = not _shots.is_empty()
	_empty.visible = _shots.is_empty()
	_title.text = "Snapshots  (%d)" % _shots.size()
	# Save all is a grid-view, desktop-only affordance (N programmatic browser
	# downloads trip popup blockers). Statuses reset on every view switch and
	# new capture so a stale "saved" claim never lingers over a different shot.
	_save_all_btn.visible = not _shots.is_empty() and not OS.has_feature("web")
	_grid_status.text = ""
	_save_status.text = ""
	_reveal_btn.visible = false
```

**Edit H — `_show_detail` resets.** Replace:

```gdscript
	_grid_scroll.visible = false
	_empty.visible = false
	_detail.visible = true
	_title.text = "Snapshot  %d / %d" % [i + 1, _shots.size()]
```

with:

```gdscript
	_grid_scroll.visible = false
	_empty.visible = false
	_detail.visible = true
	_title.text = "Snapshot  %d / %d" % [i + 1, _shots.size()]
	# Entering the detail view (or arrowing to a different shot) drops any
	# stale save status: it described a different snapshot.
	_save_all_btn.visible = false
	_grid_status.text = ""
	_save_status.text = ""
	_reveal_btn.visible = false
```

**Edit I — the three handlers.** Directly after the whole `nav_detail` function (it ends `_show_detail((_detail_index + delta + _shots.size()) % _shots.size())`), insert:

```gdscript


func _save_current() -> void:
	# Export the shown snapshot (issue #488). The capture index keeps the file
	# name deterministic, so re-saving a shot overwrites its earlier file.
	if _detail_index == -1:
		return
	var shot: Dictionary = _shots[_detail_index]
	var path: String = SnapshotExport.save(
		shot["texture"], _detail_index, shot["label"])
	if path == "":
		_save_status.text = "save failed — see console"
		_reveal_btn.visible = false
		return
	_last_saved_path = path
	_save_status.text = "saved → %s" % path
	# The browser surfaces its own download UI; revealing is a desktop thing.
	_reveal_btn.visible = not OS.has_feature("web")


func _reveal_last() -> void:
	if _last_saved_path != "":
		OS.shell_show_in_file_manager(_last_saved_path)


func _save_all() -> void:
	# Export every shot through the same helper (desktop only; the button is
	# hidden on web). Partial failure names the count; details are on the
	# console via the helper's push_error.
	var saved := 0
	var dir := ""
	for i in _shots.size():
		var shot: Dictionary = _shots[i]
		var path: String = SnapshotExport.save(shot["texture"], i, shot["label"])
		if path != "":
			saved += 1
			dir = path.get_base_dir()
	if saved == _shots.size() and saved > 0:
		_grid_status.text = "%d saved → %s" % [saved, dir]
	else:
		_grid_status.text = "%d of %d saved — see console" % [saved, _shots.size()]
```

- [ ] **Step 2: Run the full smoke test**

Run:
```bash
./godot-generative-agents/run_smoke_test.sh
```
Expected: all three unit sentinels print; `snapshot_gallery: OK (2 snapshots)` still appears (the smoke exercises `add_snapshot` + `_show_grid`, so a parse or null error in the new code fails here); `smoke_test: PASS — 4 scene(s) OK`, exit 0.

- [ ] **Step 3: Commit**

```bash
git add godot-generative-agents/godot/scripts/snapshot_gallery.gd
git commit -m "feat(viewer): Save PNG / Reveal / Save all in the snapshot gallery (#488)

Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>"
```

---

## Self-Review

- **Spec coverage:** helper + naming + fallback + web branch (Task 1 Step 3), headless test incl. end-to-end write (Task 1 Step 1), smoke sentinel wiring (Task 1 Step 5), Save PNG/Reveal/save-status (Task 2 Edits F, I), desktop-only Save all + grid status (Edits E, G, I), status resets on view switch and new capture (`add_snapshot` refreshes via `_show_grid`, Edits G, H), docstring update (Edit A), no `viewer.gd` change (no task touches it). Out-of-scope items appear in no task. ✓
- **Placeholder scan:** none — every step carries exact code/commands. ✓
- **Type consistency:** `file_name(index: int, label: String)` and `save(texture, index, label, dir_override := "")` identical in Task 1's implementation, Task 1's tests, and Task 2's call sites (`_save_current` passes `_detail_index`; `_save_all` passes the loop index — both the capture index that `add_snapshot` implies by insertion order). Widget names (`_save_btn`, `_reveal_btn`, `_save_status`, `_save_all_btn`, `_grid_status`) match between Edits D, E, F, G, H, I. ✓
