# Live-mode Clip Export Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a live-mode "Export last N steps" affordance to the Godot viewer that grabs the most recent N frames of elapsed history as a GIF (and, on desktop, an MP4 + high-quality GIF via ffmpeg), reusing #488's capture loop and `clip_export.gd` unchanged.

**Architecture:** A pure span-arithmetic helper (`live_clip_span.gd`) computes the `[from, to]` window ending at the live head; `agent_panel.gd` grows a live clip row (count SpinBox + two export buttons) shown only in live mode; `viewer.gd` routes the existing `clip_export_requested` signal on `_is_live`, and its capture loop gains a `_capturing` guard that suspends live socket polling during the ~1–3 s offscreen render and resumes the playhead at the (grown) live head afterward.

**Tech Stack:** GDScript, Godot 4.6. Headless `SceneTree` tests (not GUT), wired into `run_smoke_test.sh`.

## Global Constraints

- **Godot-only change; targets `godot-ga-main`** (viewer-only). No backend, engine, or Python changes.
- **Reuse #488 verbatim:** the capture loop `viewer.gd:_capture_span`, `gif_encoder.gd`, and `clip_export.gd` are not modified except for the `_capturing`/restore-to-head change to `_capture_span`.
- **`min_n = 2`:** the smallest clip is 2 frames; below that, export is disabled and the span helper returns `{}`.
- **The backend sim is never touched during capture** — only local socket polling pauses.
- **Headless test convention:** `extends SceneTree`, static-method logic modules `extends RefCounted`, sentinel print `test_<name>: all checks passed`, `quit(1 if _failures > 0 else 0)`, wired into `run_smoke_test.sh` gated by `grep -q "all checks passed"`.
- **Commit trailer on every commit:** `Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>`. Never `git add -A` / `git add .` — stage named paths.
- **All paths below are relative to the repo root.** The Godot project lives at `godot-generative-agents/godot/`; run headless tests with `--path godot-generative-agents/godot`.

---

### Task 1: Pure last-N span helper + headless test

**Files:**
- Create: `godot-generative-agents/godot/scripts/live_clip_span.gd`
- Test: `godot-generative-agents/godot/tests/test_live_clip_span.gd`
- Modify: `godot-generative-agents/run_smoke_test.sh` (append one test invocation)

**Interfaces:**
- Consumes: nothing (pure, no dependencies).
- Produces: `LiveClipSpan.span_last_n(head: int, n: int, min_n := 2) -> Dictionary` returning `{"from": int, "to": int}` or `{}` (empty = too little history / n below min). `to` always equals `head`; `from` is `maxi(0, head - n + 1)`.

- [ ] **Step 1: Write the failing test**

Create `godot-generative-agents/godot/tests/test_live_clip_span.gd`:

```gdscript
extends SceneTree
## Headless unit tests for scripts/live_clip_span.gd (issue #548). Run:
##   godot --headless --path godot-generative-agents/godot \
##     --script res://tests/test_live_clip_span.gd
## Exit 0 = all checks pass; run_smoke_test.sh runs this and greps the sentinel.

const LiveClipSpan := preload("res://scripts/live_clip_span.gd")

var _failures := 0


func _check(cond: bool, name: String) -> void:
	if cond:
		print("  ok: %s" % name)
	else:
		_failures += 1
		push_error("FAIL: %s" % name)


func _span_eq(got: Dictionary, from: int, to: int) -> bool:
	return not got.is_empty() and int(got["from"]) == from and int(got["to"]) == to


func _initialize() -> void:
	# --- too little history -> {} ---
	_check(LiveClipSpan.span_last_n(0, 60).is_empty(), "head 0 (1 frame) -> {}")
	# --- exactly min_n frames (head 1) -> whole run ---
	_check(_span_eq(LiveClipSpan.span_last_n(1, 60), 0, 1), "head 1, N 60 -> {0,1}")
	# --- exact N well inside history ---
	_check(_span_eq(LiveClipSpan.span_last_n(100, 60), 41, 100), "head 100, N 60 -> {41,100}")
	# --- N exceeds history -> whole run so far ---
	_check(_span_eq(LiveClipSpan.span_last_n(10, 60), 0, 10), "head 10, N 60 -> {0,10}")
	# --- n below min_n -> {} ---
	_check(LiveClipSpan.span_last_n(100, 1).is_empty(), "N 1 (< min_n) -> {}")
	# --- n at the min_n boundary ---
	_check(_span_eq(LiveClipSpan.span_last_n(100, 2), 99, 100), "head 100, N 2 -> {99,100}")
	# --- custom min_n honored ---
	_check(LiveClipSpan.span_last_n(3, 60, 5).is_empty(), "head 3, min_n 5 -> {} (too little)")
	_check(_span_eq(LiveClipSpan.span_last_n(4, 60, 5), 0, 4), "head 4, min_n 5 -> {0,4}")

	# --- invariant sweep: to == head, 0 <= from <= to, over many heads/Ns ---
	var ok := true
	for head in range(1, 200, 7):
		for n in [2, 5, 60, 500]:
			var s := LiveClipSpan.span_last_n(head, n)
			if s.is_empty():
				continue
			if int(s["to"]) != head or int(s["from"]) < 0 or int(s["from"]) > int(s["to"]):
				ok = false
	_check(ok, "invariant: to==head and 0<=from<=to across sweep")

	if _failures == 0:
		print("test_live_clip_span: all checks passed")
	quit(1 if _failures > 0 else 0)
```

- [ ] **Step 2: Run the test to verify it fails**

Run:
```bash
godot --headless --path godot-generative-agents/godot --script res://tests/test_live_clip_span.gd
```
Expected: FAIL — parse/load error because `res://scripts/live_clip_span.gd` does not exist yet (the `preload` cannot resolve). No `all checks passed` line printed.

- [ ] **Step 3: Write the minimal implementation**

Create `godot-generative-agents/godot/scripts/live_clip_span.gd`:

```gdscript
extends RefCounted
## Pure "last N steps" span arithmetic for live-mode clip export (issue #548).
## No rendering, no HTTP -- headless-testable (tests/test_live_clip_span.gd).


static func span_last_n(head: int, n: int, min_n := 2) -> Dictionary:
	# The clip covers [from, to] over ELAPSED history, ending at the live head:
	#   to   = head
	#   from = max(0, head - n + 1)   (N frames, clamped to the start of history)
	# Returns {} (too little history / n below min) when n < min_n or head < min_n - 1.
	if n < min_n or head < min_n - 1:
		return {}
	var to := head
	var from := maxi(0, head - n + 1)
	return {"from": from, "to": to}
```

- [ ] **Step 4: Run the test to verify it passes**

Run:
```bash
godot --headless --path godot-generative-agents/godot --script res://tests/test_live_clip_span.gd
```
Expected: PASS — prints `  ok: …` for each check and finally `test_live_clip_span: all checks passed`; exit code 0.

- [ ] **Step 5: Wire the test into the smoke script**

In `godot-generative-agents/run_smoke_test.sh`, immediately after the `test_live_pacer.gd` block (the last existing headless-test block), append:

```bash
"$GODOT" --headless --path "$PROJECT_DIR" --script res://tests/test_live_clip_span.gd 2>&1 \
  | tee /dev/stderr | grep -q "all checks passed"
```

- [ ] **Step 6: Run the smoke script to confirm the new test is picked up**

Run:
```bash
./godot-generative-agents/run_smoke_test.sh
```
Expected: exit 0; the output includes `test_live_clip_span: all checks passed`.

- [ ] **Step 7: Commit**

```bash
git add godot-generative-agents/godot/scripts/live_clip_span.gd \
        godot-generative-agents/godot/tests/test_live_clip_span.gd \
        godot-generative-agents/run_smoke_test.sh
git commit -m "$(cat <<'EOF'
feat(viewer): last-N clip span helper + headless test (#548)

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

### Task 2: Live clip row in the sidebar panel

**Files:**
- Modify: `godot-generative-agents/godot/scripts/agent_panel.gd` (member vars near line 238; constructor row after the baked clip row ~line 402; `set_live` ~line 617; two new methods)

**Interfaces:**
- Consumes: the existing `signal clip_export_requested(kind: String)` (declared ~line 31); the existing `_clip_status` label and `_clip_reveal_btn` button (reused verbatim via `set_clip_status`).
- Produces:
  - `live_clip_count() -> int` — the SpinBox value (default 60), for the viewer to read on export.
  - `set_live_clip_ready(ready: bool)` — enables/disables both live clip buttons.
  - Live-mode side effect: `clip_export_requested("gif")` / `clip_export_requested("frames")` now also fire from the live buttons (the viewer routes on `_is_live` in Task 3).

**Context:** `agent_panel.gd` builds its sidebar in the constructor. The baked clip row (`_clip_gif_btn`, `_clip_frames_btn`, `_clip_reveal_btn`) is created ~lines 377–402, followed by `_clip_status` ~line 404. `set_live(live)` (~line 617) toggles replay-only controls off and the live badge/status on. There is no headless test harness for the panel (it builds a full `Control` tree); this task's gate is the smoke test (every scene parses + loads its script) plus the parse check below.

- [ ] **Step 1: Declare the live-row member variables**

In `agent_panel.gd`, find the existing clip-member declarations (~lines 238–241):

```gdscript
var _clip_gif_btn: Button           # export the marked span as a GIF (#488)
var _clip_frames_btn: Button        # export PNG frames for ffmpeg (desktop only)
var _clip_status: Label             # where the last export went
var _clip_reveal_btn: Button        # Reveal in Finder for the last export
```

Immediately after them, add:

```gdscript
# Live-mode "export last N" row (#548): shown only in live mode, mutually
# exclusive with the baked marker buttons above. Reuses _clip_status +
# _clip_reveal_btn for the result line.
var _live_clip_row: HBoxContainer   # the whole live clip row (toggled by set_live)
var _clip_n_spin: SpinBox           # how many recent steps to grab (default 60)
var _live_clip_gif_btn: Button      # export the last N steps as a GIF
var _live_clip_frames_btn: Button   # export the last N steps as MP4+GIF (desktop)
```

- [ ] **Step 2: Build the live clip row in the constructor**

In `agent_panel.gd`, find the end of the baked clip row — the `_clip_reveal_btn` block that ends with `clip_row.add_child(_clip_reveal_btn)` (~line 402), directly before `_clip_status = Label.new()` (~line 404). Insert this block between them (after `clip_row.add_child(_clip_reveal_btn)`, before `_clip_status = Label.new()`):

```gdscript
	# Live-mode clip export (issue #548): no scrubber to mark a span, so grab the
	# last N elapsed steps instead. Built here (below the baked marker row), hidden
	# until set_live(true). Reuses _clip_reveal_btn + _clip_status below for results.
	_live_clip_row = HBoxContainer.new()
	_live_clip_row.add_theme_constant_override("separation", 6)
	_live_clip_row.visible = false
	col.add_child(_live_clip_row)

	_clip_n_spin = SpinBox.new()
	_clip_n_spin.min_value = 2
	_clip_n_spin.max_value = 2000
	_clip_n_spin.value = 60
	_clip_n_spin.step = 1
	_clip_n_spin.tooltip_text = "How many recent steps to export"
	_live_clip_row.add_child(_clip_n_spin)

	_live_clip_gif_btn = Button.new()
	_live_clip_gif_btn.text = "Export last N GIF"
	_live_clip_gif_btn.tooltip_text = "Export the last N elapsed steps as an animated GIF"
	_live_clip_gif_btn.focus_mode = Control.FOCUS_NONE
	_live_clip_gif_btn.disabled = true
	_live_clip_gif_btn.pressed.connect(func() -> void: clip_export_requested.emit("gif"))
	_live_clip_row.add_child(_live_clip_gif_btn)

	_live_clip_frames_btn = Button.new()
	_live_clip_frames_btn.text = "Export last N MP4 + GIF"
	_live_clip_frames_btn.tooltip_text = "Render the last N steps to clip.mp4 + a high-quality clip.gif via ffmpeg (falls back to PNG frames + a printed command if ffmpeg is missing)"
	_live_clip_frames_btn.focus_mode = Control.FOCUS_NONE
	_live_clip_frames_btn.disabled = true
	_live_clip_frames_btn.visible = not OS.has_feature("web")
	_live_clip_frames_btn.pressed.connect(func() -> void: clip_export_requested.emit("frames"))
	_live_clip_row.add_child(_live_clip_frames_btn)
```

- [ ] **Step 3: Toggle the live row in `set_live`**

In `agent_panel.gd`, find the visibility block at the top of `set_live(live)` (~lines 622–628):

```gdscript
	_scrubber.visible = not live
	_markers_strip.visible = not live
	_clip_gif_btn.visible = not live
	_clip_frames_btn.visible = not live and not OS.has_feature("web")
	_clip_reveal_btn.visible = false
	_clip_status.visible = not live
	_speed_row.visible = not live
```

Replace those seven lines with (only two lines change — `_clip_status` and the new `_live_clip_row`):

```gdscript
	_scrubber.visible = not live
	_markers_strip.visible = not live
	_clip_gif_btn.visible = not live
	_clip_frames_btn.visible = not live and not OS.has_feature("web")
	_clip_reveal_btn.visible = false
	_clip_status.visible = true  # shared by both modes now (#548)
	_speed_row.visible = not live
	_live_clip_row.visible = live  # live "export last N" row (#548)
```

(The live frames button keeps its own constructor `visible = not OS.has_feature("web")`, so on the web build it stays hidden even when the row is shown.)

- [ ] **Step 4: Add the two accessor methods**

In `agent_panel.gd`, immediately after the `set_clip_status(...)` method (the one that ends by rewiring `_clip_reveal_btn.pressed`, ~line 713), add:

```gdscript
func live_clip_count() -> int:
	# The live "export last N" count from the SpinBox (issue #548).
	return int(_clip_n_spin.value)


func set_live_clip_ready(ready: bool) -> void:
	# Enable the live clip buttons once enough history exists to make a clip (#548);
	# the viewer calls this per step with _frames.size() >= LIVE_CLIP_MIN_N.
	_live_clip_gif_btn.disabled = not ready
	_live_clip_frames_btn.disabled = not ready
```

- [ ] **Step 5: Parse-check the script**

Run (Godot reports GDScript parse/type errors on import):
```bash
godot --headless --path godot-generative-agents/godot --editor --quit 2>&1 | grep -iE "SCRIPT ERROR|Parse Error|agent_panel" || echo "no agent_panel parse errors"
```
Expected: `no agent_panel parse errors` (no `SCRIPT ERROR` / `Parse Error` mentioning `agent_panel.gd`).

- [ ] **Step 6: Run the smoke test to confirm scenes still load**

Run:
```bash
./godot-generative-agents/run_smoke_test.sh
```
Expected: exit 0 (every scene loads and paints its campus; `agent_panel.gd` is loaded by the viewer scene, so a parse error here would fail this).

- [ ] **Step 7: Commit**

```bash
git add godot-generative-agents/godot/scripts/agent_panel.gd
git commit -m "$(cat <<'EOF'
feat(viewer): live "export last N" clip row in the sidebar (#548)

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

### Task 3: Viewer capture/live reconciliation + export dispatch

**Files:**
- Modify: `godot-generative-agents/godot/scripts/viewer.gd`
  - const block (~line 122–127): add the `LiveClipSpan` preload.
  - const block (~line 227): add `const LIVE_CLIP_MIN_N := 2`.
  - state fields (~line 224, near `var _is_live := false`): add `var _capturing := false`.
  - signal connect (~line 295): route `clip_export_requested` through a new handler.
  - `_capture_span` (~line 1520): add `_capturing` guard + live restore-to-head.
  - `_export_clip` (~line 1547): keep guards; delegate body to `_render_and_save_clip`.
  - add `_on_clip_export_requested`, `_export_live_clip`, `_render_and_save_clip`.
  - `_process` (~line 1694): guard `_poll_ws()` on `not _capturing`; per-step block: call `set_live_clip_ready`.

**Interfaces:**
- Consumes: `LiveClipSpan.span_last_n(head, n, min_n)` (Task 1); `_panel.live_clip_count()` and `_panel.set_live_clip_ready(ready)` (Task 2); existing `_panel.set_clip_status(text, reveal_path)`, `_capture_span`, `GifEncoder.encode`, `ClipExport.*` (#488).
- Produces: nothing consumed downstream (leaf integration).

**Context:** In live mode `_frames[]` grows as socket records arrive (`_apply_live_frame`); `_process` calls `_poll_ws()` each frame, then advances/clamps `_t`. `_capture_span(from, to, sink)` renders each step offscreen by pinning `_t` and hiding `$UI`, awaiting `RenderingServer.frame_post_draw` (which yields, so `_process` keeps running during capture). `_export_clip` currently early-returns `if _is_live`. The signal is connected at line 295: `_panel.clip_export_requested.connect(_export_clip)`.

- [ ] **Step 1: Add the preload, the constant, and the capture flag**

In `viewer.gd`, in the `const … preload` block (after `const ClipExport := preload("res://scripts/clip_export.gd")`, ~line 125), add:

```gdscript
const LiveClipSpan := preload("res://scripts/live_clip_span.gd")
```

Near `const THINKING_STALL_MS := 1500` (~line 227), add:

```gdscript
# Live clip export (issue #548): the smallest exportable clip is 2 frames; the
# live buttons stay disabled and span_last_n returns {} below this.
const LIVE_CLIP_MIN_N := 2
```

Near `var _is_live := false` (~line 224), add:

```gdscript
# True only during an offscreen clip capture (issue #548): while set, _process
# suspends live socket polling so _frames/last hold still for the render.
var _capturing := false
```

- [ ] **Step 2: Route the export signal through a mode dispatcher**

In `viewer.gd`, change the connect at ~line 295:

```gdscript
	_panel.clip_export_requested.connect(_export_clip)
```

to:

```gdscript
	_panel.clip_export_requested.connect(_on_clip_export_requested)
```

- [ ] **Step 3: Add the dispatcher + live export + shared render helper; slim `_export_clip`**

In `viewer.gd`, replace the entire existing `_export_clip` function (from `func _export_clip(kind: String) -> void:` ~line 1547 through the end of its `else:  # "frames"` block, ~line 1590) with the following four functions:

```gdscript
func _on_clip_export_requested(kind: String) -> void:
	# The sidebar's clip buttons fire in both modes (#488 marked span in replay,
	# #548 last-N in live). Route on mode.
	if _is_live:
		await _export_live_clip(kind)
	else:
		await _export_clip(kind)


func _export_clip(kind: String) -> void:
	# Replay: export the marked [ … ] span (issue #488). Baked replay only.
	if _is_live or _frames.is_empty():
		return
	if _clip_in < 0 or _clip_out < 0:
		_panel.set_clip_status("Mark a clip span first: [ sets start, ] sets end.", "")
		return
	var a := mini(_clip_in, _clip_out)
	var b := maxi(_clip_in, _clip_out)
	await _render_and_save_clip(a, b, kind)


func _export_live_clip(kind: String) -> void:
	# Live: export the last N elapsed steps, ending at the live head (issue #548).
	if not _is_live or _frames.is_empty():
		return
	var head := _frames.size() - 1
	var span := LiveClipSpan.span_last_n(head, _panel.live_clip_count(), LIVE_CLIP_MIN_N)
	if span.is_empty():
		_panel.set_clip_status("Not enough history yet — let the sim run a moment.", "")
		return
	await _render_and_save_clip(int(span["from"]), int(span["to"]), kind)


func _render_and_save_clip(a: int, b: int, kind: String) -> void:
	# Shared clip render+save for both modes (issue #488 body, factored out for #548).
	# _capture_span suspends live polling while it renders (see its _capturing guard).
	_panel.set_clip_status("Exporting %d frames…" % (b - a + 1), "")
	if kind == "gif":
		var frames: Array = []
		await _capture_span(a, b, func(_i: int, img: Image) -> void:
			frames.append(_downscale(img)))
		var bytes := GifEncoder.encode(frames, 10)
		var path := ClipExport.save_gif(bytes, a, b)
		if path == "":
			_panel.set_clip_status("GIF export failed — see console.", "")
		else:
			_panel.set_clip_status("saved → %s" % path,
				"" if OS.has_feature("web") else path)
	else:  # "frames"
		var dir := ClipExport.make_frame_dir(a, b)
		if dir == "":
			_panel.set_clip_status("Frame export failed — see console.", "")
			return
		var count := [0]
		await _capture_span(a, b, func(i: int, img: Image) -> void:
			if ClipExport.save_frame(img, dir, i):
				count[0] += 1)
		var gdir := ProjectSettings.globalize_path(dir)
		_panel.set_clip_status("Encoding %d frames with ffmpeg…" % count[0], "")
		await get_tree().process_frame
		var res := ClipExport.run_ffmpeg(dir)
		if res.get("ok", false):
			_panel.set_clip_status("saved → %s\n(+ clip.gif in the same folder)" % res["mp4"], gdir)
		elif String(res.get("error", "")) == "ffmpeg not found":
			_panel.set_clip_status("%d frames → %s\nffmpeg not found — run:\n%s" % [
				count[0], gdir, ClipExport.ffmpeg_command(dir)], gdir)
		else:
			_panel.set_clip_status("ffmpeg failed — see console; frames → %s" % gdir, gdir)
```

- [ ] **Step 4: Add the `_capturing` guard + live restore-to-head to `_capture_span`**

In `viewer.gd`, replace the body of `_capture_span` (the part from `var saved_t := _t` through the final `_paused = saved_paused`, ~lines 1528–1538) so it sets/clears `_capturing` and, in live mode, resumes at the grown head. The full function becomes:

```gdscript
func _capture_span(from_step: int, to_step: int, sink: Callable) -> void:
	# Render each step in [from,to] offscreen and hand (seq_index, Image) to sink.
	# _paused stops _process advancing _t, so setting _t to an exact step multiple
	# renders that step with zero interpolation (see _process). UI chrome is hidden
	# so grabs are the bare campus; everything is restored on the way out. In live
	# mode _capturing also freezes socket polling so _frames/last hold still, and we
	# resume at the (grown) live head rather than the pre-capture _t (issue #548).
	var last := maxi(_frames.size() - 1, 0)
	from_step = clampi(from_step, 0, last)
	to_step = clampi(to_step, from_step, last)
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
		# Frames kept arriving on the socket during the freeze; the next _process
		# drains the buffered records. Resume at the current head, not saved_t.
		_t = float(maxi(_frames.size() - 1, 0)) * step_seconds
	else:
		_t = saved_t
	_capturing = false
```

- [ ] **Step 5: Suspend polling during capture + keep the live buttons' ready-state honest in `_process`**

In `viewer.gd`, find the top of `_process` (~lines 1694–1695):

```gdscript
	if _is_live:
		_poll_ws()
```

Change to:

```gdscript
	if _is_live and not _capturing:
		_poll_ws()
```

Then find the per-step sidebar block (~lines 1792–1793):

```gdscript
	if i != _last_status_step:
		_last_status_step = i
		for name in _names:
```

Insert the ready-state push right after `_last_status_step = i` (before the `for name in _names:` loop):

```gdscript
	if i != _last_status_step:
		_last_status_step = i
		if _is_live:
			_panel.set_live_clip_ready(_frames.size() >= LIVE_CLIP_MIN_N)
		for name in _names:
```

- [ ] **Step 6: Parse-check the viewer script**

Run:
```bash
godot --headless --path godot-generative-agents/godot --editor --quit 2>&1 | grep -iE "SCRIPT ERROR|Parse Error|viewer" || echo "no viewer parse errors"
```
Expected: `no viewer parse errors`.

- [ ] **Step 7: Run the headless smoke test**

Run:
```bash
./godot-generative-agents/run_smoke_test.sh
```
Expected: exit 0; output includes `test_live_clip_span: all checks passed` and every scene paints its campus.

- [ ] **Step 8: Manual live-mode verification**

The suspend/restore-to-head and button-enable wiring need HTTP + a live head + rendering, so they are verified manually (not headless-unit-testable). In two terminals from the repo root:

```bash
# Terminal 1 — serve a mock live sim (real requests, no keys, no spend):
uv run python godot-generative-agents/backend/penn/serve_penn.py --tick-seconds 0.1

# Terminal 2 — point the viewer at it:
SIM_API_URL=http://127.0.0.1:8080 ./godot-generative-agents/run.sh
```

In the viewer: let ~120 steps elapse, set the SpinBox to 60, click **Export last N GIF** (and, on desktop, **Export last N MP4 + GIF**). Confirm:
1. The status line shows `saved → …/penn-clips/penn-clip-<from>-<to>.gif` with `to - from + 1 == 60` and `to` equal to the step count reached at the click.
2. After export the playhead resumes at the live head — no backward snap, no frozen clock.
3. **Reveal** opens the folder (desktop) and the GIF plays back the last 60 steps; the MP4 path additionally produced `clip.mp4` + `clip.gif`.
4. Before enough history exists (first < 2 steps), the buttons are disabled.

- [ ] **Step 9: Commit**

```bash
git add godot-generative-agents/godot/scripts/viewer.gd
git commit -m "$(cat <<'EOF'
feat(viewer): live "export last N" dispatch + capture/poll reconciliation (#548)

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

## Self-Review

**1. Spec coverage:**
- Pure last-N span helper (`span_last_n`, `{from,to}`/`{}`, clamps, `min_n`) → Task 1. ✓
- Headless test wired into `run_smoke_test.sh` → Task 1 Steps 1, 5. ✓
- Live clip row (SpinBox min 2 / max 2000 / default 60; GIF + MP4+GIF buttons; web-gates frames button; disabled until ready; reuses `_clip_status`/`_clip_reveal_btn`; `live_clip_count`; `set_live_clip_ready`) → Task 2. ✓
- `set_live` visibility: baked row `not live`, live row `live`, `_clip_status` shared → Task 2 Step 3. ✓
- `_capturing` guard + `_process` poll suspension + restore-to-head → Task 3 Steps 4–5. ✓
- Export dispatch routes on `_is_live`; `_export_live_clip` uses helper; DRY `_render_and_save_clip` shared by both entry points → Task 3 Steps 2–3. ✓
- Per-step button-ready push → Task 3 Step 5. ✓
- Edge cases (N > history, too little history, ffmpeg missing, web, backend untouched) → helper (Task 1) + `_export_live_clip` guard + reused #488 paths. ✓

**2. Placeholder scan:** No TBD/TODO/"handle edge cases"/"similar to". Every code step carries full code; every command has expected output. ✓

**3. Type consistency:** `span_last_n(head, n, min_n)` → `Dictionary` with int `"from"`/`"to"` keys, consumed as `int(span["from"])` in Task 3. `live_clip_count() -> int` and `set_live_clip_ready(ready: bool)` defined in Task 2, called identically in Task 3. `LIVE_CLIP_MIN_N := 2` matches the helper's default `min_n := 2`. Signal `clip_export_requested(kind: String)` emitted in Task 2, connected via `_on_clip_export_requested(kind: String)` in Task 3. ✓
