# Live-Mode Thinking Indicator Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Show a global "thinking…" cue (an on-view badge + the sidebar status line) while a live backend's decision tick stalls, so the sim reads as working rather than frozen — without touching the already-working interpolation or the baked-replay path.

**Architecture:** A pure decision predicate (`thinking_indicator.gd`, headless-tested) decides *whether* to show the cue and *what text* it reads this frame; a small overlay `Control` (`thinking_badge.gd`) renders it; `viewer.gd` measures the stall (time since the live head last grew) and drives both the badge and the sidebar status. Everything is gated on `_is_live`, so baked replay is byte-identical.

**Tech Stack:** Godot 4.6 / GDScript. No new dependencies. Tests are `extends SceneTree` scripts run headlessly via `--script`, registered in `run_smoke_test.sh`.

## Global Constraints

- **Targets `godot-ga-main`** (godot-only). Branch `feat/live-thinking-372` (already created off `godot-ga-main`).
- **Gated on `_is_live`.** Baked-replay behavior must stay byte-identical; the badge is inactive/hidden whenever `_is_live` is false.
- **Global cue, not per-agent** (stall inference can't attribute to one agent; per-agent bubbles are #551). Do NOT add per-agent bubbles or any backend change.
- **Do NOT modify interpolation / add a lead buffer** — catch-up already works via the shared `_t` render. This plan only adds the cue.
- **Stall threshold:** `THINKING_STALL_MS = 1500`. Cue reads `"thinking…"`; when it clears while running, the sidebar restores to the exact existing string `"following backend"`.
- **Test convention:** each test `extends SceneTree`, defines `_check(cond, name)`, prints `<test_name>: all checks passed` on success, `quit(1 if _failures > 0 else 0)`; registered in `run_smoke_test.sh` with the `| tee /dev/stderr | grep -q "all checks passed"` idiom.
- New `.gd` files generate a committed `.uid` on first import (`godot --headless --path godot-generative-agents/godot --import`) — commit the `.uid` alongside the script.
- Commits end with `Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>`. Run git from the repo root `/Users/yh/Documents/GitHub/agent-sandbox`.
- Godot binary: `godot` on PATH, else `/Applications/Godot.app/Contents/MacOS/Godot`. `PROJECT=godot-generative-agents/godot`.

---

### Task 1: `thinking_indicator.gd` — pure decision logic

**Files:**
- Create: `godot-generative-agents/godot/scripts/thinking_indicator.gd`
- Test: `godot-generative-agents/godot/tests/test_thinking_indicator.gd`
- Modify: `godot-generative-agents/run_smoke_test.sh` (register the test)

**Interfaces:**
- Produces: `ThinkingIndicator.should_show(is_live: bool, run_state: String, playhead_at_head: bool, ms_since_last_frame: int, threshold_ms: int) -> bool` and `ThinkingIndicator.ellipsis(now_ms: int) -> String` — both consumed by Task 2 (`thinking_badge.gd` and `viewer.gd`).

- [ ] **Step 1: Write the failing test**

Create `godot-generative-agents/godot/tests/test_thinking_indicator.gd`:

```gdscript
extends SceneTree
## Headless unit tests for scripts/thinking_indicator.gd (issue #372). Run:
##   godot --headless --path godot-generative-agents/godot \
##     --script res://tests/test_thinking_indicator.gd
## Exit 0 = all checks pass; run_smoke_test.sh runs this and greps the sentinel.

const ThinkingIndicator := preload("res://scripts/thinking_indicator.gd")

var _failures := 0


func _check(cond: bool, name: String) -> void:
	if cond:
		print("  ok: %s" % name)
	else:
		_failures += 1
		push_error("FAIL: %s" % name)


func _initialize() -> void:
	# --- should_show truth table (threshold 1500ms) ---
	_check(not ThinkingIndicator.should_show(false, "running", true, 9999, 1500),
		"not live -> never shows")
	_check(ThinkingIndicator.should_show(true, "running", true, 1600, 1500),
		"live + running + at head + stale -> shows")
	_check(not ThinkingIndicator.should_show(true, "running", true, 1000, 1500),
		"fresh frame (under threshold) -> no show")
	_check(not ThinkingIndicator.should_show(true, "running", false, 9999, 1500),
		"still easing (not at head) -> no show")
	_check(not ThinkingIndicator.should_show(true, "paused", true, 9999, 1500),
		"paused -> no show")
	_check(not ThinkingIndicator.should_show(true, "finished", true, 9999, 1500),
		"finished -> no show")
	_check(not ThinkingIndicator.should_show(true, "waiting", true, 9999, 1500),
		"waiting -> no show")

	# --- ellipsis cycles one dot per 400ms, wrapping after 3 dots ---
	_check(ThinkingIndicator.ellipsis(0) == "thinking", "0ms -> no dots")
	_check(ThinkingIndicator.ellipsis(400) == "thinking.", "400ms -> 1 dot")
	_check(ThinkingIndicator.ellipsis(800) == "thinking..", "800ms -> 2 dots")
	_check(ThinkingIndicator.ellipsis(1200) == "thinking...", "1200ms -> 3 dots")
	_check(ThinkingIndicator.ellipsis(1600) == "thinking", "1600ms -> wraps to 0 dots")

	if _failures == 0:
		print("test_thinking_indicator: all checks passed")
	quit(1 if _failures > 0 else 0)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `godot --headless --path godot-generative-agents/godot --script res://tests/test_thinking_indicator.gd`
Expected: FAIL — `thinking_indicator.gd` does not exist (preload error), no `"all checks passed"`.

- [ ] **Step 3: Write the implementation**

Create `godot-generative-agents/godot/scripts/thinking_indicator.gd`:

```gdscript
extends RefCounted
## Pure decision logic for the live "thinking" cue (issue #372): whether the
## indicator should show, and its label text this frame. No scene, no sim
## knowledge -- viewer.gd feeds it live state and thinking_badge.gd renders the
## result. Global, not per-agent (stall inference can't attribute to one agent;
## per-agent bubbles are #551). Headless-tested (tests/test_thinking_indicator.gd).

const DOT_PERIOD_MS := 400  # one dot added every this many ms
const MAX_DOTS := 3


static func should_show(is_live: bool, run_state: String, playhead_at_head: bool,
		ms_since_last_frame: int, threshold_ms: int) -> bool:
	# True only when a live, RUNNING backend has caught the head (nothing left to
	# ease toward) and no new frame has landed for longer than threshold_ms.
	# Any other state -- not live, paused/finished/stopped/waiting, still easing
	# through buffered frames, or a frame arrived recently -- returns false.
	return (
		is_live
		and run_state == "running"
		and playhead_at_head
		and ms_since_last_frame > threshold_ms
	)


static func ellipsis(now_ms: int) -> String:
	# "thinking" -> "thinking." -> ".." -> "..." -> wrap, one dot per DOT_PERIOD_MS.
	var dots := int(now_ms / DOT_PERIOD_MS) % (MAX_DOTS + 1)
	return "thinking" + ".".repeat(dots)
```

- [ ] **Step 4: Run test to verify it passes**

Run: `godot --headless --path godot-generative-agents/godot --script res://tests/test_thinking_indicator.gd 2>&1 | tail -20`
Expected: every `ok:` line, then `test_thinking_indicator: all checks passed`, exit 0.

- [ ] **Step 5: Register the test in the smoke runner**

In `godot-generative-agents/run_smoke_test.sh`, after the `test_snapshot_export.gd` block (the last unit-test line before the `exec` line that runs the scene smoke), add:

```bash
"$GODOT" --headless --path "$PROJECT_DIR" --script res://tests/test_thinking_indicator.gd 2>&1 \
  | tee /dev/stderr | grep -q "all checks passed"
```

- [ ] **Step 6: Commit**

```bash
cd /Users/yh/Documents/GitHub/agent-sandbox
godot --headless --path godot-generative-agents/godot --import >/dev/null 2>&1 || true  # generate .uid
git add godot-generative-agents/godot/scripts/thinking_indicator.gd \
        godot-generative-agents/godot/scripts/thinking_indicator.gd.uid \
        godot-generative-agents/godot/tests/test_thinking_indicator.gd \
        godot-generative-agents/godot/tests/test_thinking_indicator.gd.uid \
        godot-generative-agents/run_smoke_test.sh
git commit -m "feat(viewer): thinking-indicator decision logic (#372)

Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>"
```

---

### Task 2: `thinking_badge.gd` + `viewer.gd` wiring

The overlay cue and the stall measurement that drives it. Scene-coupled (the badge is a `Control`; the stall wiring reads live playback state), so it is verified by `run_smoke_test.sh` exit 0 plus manual acceptance against a live backend — NOT a headless unit test (that boundary is stated in the spec).

**Files:**
- Create: `godot-generative-agents/godot/scripts/thinking_badge.gd`
- Modify: `godot-generative-agents/godot/scripts/viewer.gd`

**Interfaces:**
- Consumes: `ThinkingIndicator.should_show(...)` and `ThinkingIndicator.ellipsis(...)` (Task 1); the existing `_panel.set_live_status(text: String)`, `_backend_run_state`, `_apply_live_frame`, and the `_process` render locals `i` / `last`.

- [ ] **Step 1: Write the badge Control**

Create `godot-generative-agents/godot/scripts/thinking_badge.gd`:

```gdscript
extends Control
## A small "thinking…" pill shown at the top of the view while a live decision
## tick stalls (issue #372) -- tells the user the sim is working, not frozen.
## Global, not per-agent (per-agent bubbles are #551). Styled distinctly from the
## #245 speech bubbles (a dark status pill, not a white speech balloon). Pure UI,
## live-only; viewer.gd flips it via set_active(). Only ticks while active.

const ThinkingIndicator := preload("res://scripts/thinking_indicator.gd")

const INK := Color(0.96, 0.95, 0.90)

var _label: Label


func _ready() -> void:
	# Top of the view, above the world; ignore mouse so it never eats a pan/click;
	# start hidden and inert (set_active(true) wakes it).
	set_anchors_and_offsets_preset(Control.PRESET_TOP_WIDE)
	mouse_filter = Control.MOUSE_FILTER_IGNORE
	visible = false

	var center := CenterContainer.new()
	center.set_anchors_and_offsets_preset(Control.PRESET_TOP_WIDE)
	center.mouse_filter = Control.MOUSE_FILTER_IGNORE
	center.offset_top = 12
	add_child(center)

	var pill := PanelContainer.new()
	pill.mouse_filter = Control.MOUSE_FILTER_IGNORE
	pill.add_theme_stylebox_override("panel", _pill_style())
	center.add_child(pill)

	var margin := MarginContainer.new()
	margin.add_theme_constant_override("margin_left", 14)
	margin.add_theme_constant_override("margin_right", 14)
	margin.add_theme_constant_override("margin_top", 6)
	margin.add_theme_constant_override("margin_bottom", 6)
	pill.add_child(margin)

	_label = Label.new()
	_label.add_theme_color_override("font_color", INK)
	_label.add_theme_font_size_override("font_size", 15)
	_label.text = "thinking"
	margin.add_child(_label)

	set_process(false)  # only animate while active


func set_active(active: bool) -> void:
	visible = active
	set_process(active)
	if active:
		_label.text = ThinkingIndicator.ellipsis(Time.get_ticks_msec())


func _process(_delta: float) -> void:
	_label.text = ThinkingIndicator.ellipsis(Time.get_ticks_msec())


func _pill_style() -> StyleBoxFlat:
	var sb := StyleBoxFlat.new()
	sb.bg_color = Color(0.10, 0.11, 0.15, 0.88)
	sb.set_corner_radius_all(12)
	sb.set_border_width_all(1)
	sb.border_color = Color(1.0, 0.97, 0.86, 0.30)
	return sb
```

- [ ] **Step 2: Add the preload, constant, and state to `viewer.gd`**

Locate the preload block near `const ReplayMarkers := preload("res://scripts/replay_markers.gd")` (~line 123) and add after it:

```gdscript
const ThinkingIndicator := preload("res://scripts/thinking_indicator.gd")
```

Near the live-state fields (by `var _is_live := false`, ~line 222) add:

```gdscript
# Live "thinking" cue (issue #372): wall-clock ms when the live head last grew,
# and whether the cue is currently showing (so the sidebar text flips on edges).
const THINKING_STALL_MS := 1500
var _last_frame_ms := 0
var _thinking := false
var _thinking_badge: Control
```

- [ ] **Step 3: Instantiate the badge in `_ready`**

In `_ready`, right after the panel's signals are connected (by `_panel.snapshot_requested.connect(_take_snapshot)`, ~line 299), add:

```gdscript
	# The live "thinking…" overlay (issue #372) lives on the same UI layer as the
	# sidebar so it draws in screen space above the world; hidden until a stall.
	_thinking_badge = preload("res://scripts/thinking_badge.gd").new()
	$UI.add_child(_thinking_badge)
```

- [ ] **Step 4: Stamp the head-growth time in `_apply_live_frame`**

In `_apply_live_frame` (the function beginning `func _apply_live_frame(step: int, agents: Variant) -> void:`, ~line 728), capture the frame count before the mutation and stamp the clock only when the head actually grew. Change the body from:

```gdscript
	while _frames.size() < step:
		_frames.append(_frames[-1] if not _frames.is_empty() else agents)
	if step == _frames.size():
		_frames.append(agents)
	else:
		_frames[step] = agents
	_register_frame_buildings(agents as Dictionary)
```

to:

```gdscript
	var prev_size := _frames.size()
	while _frames.size() < step:
		_frames.append(_frames[-1] if not _frames.is_empty() else agents)
	if step == _frames.size():
		_frames.append(agents)
	else:
		_frames[step] = agents
	# A genuinely new step (the head grew) resets the stall clock; a backfill
	# rewrite of an existing index does not (issue #372).
	if _frames.size() > prev_size:
		_last_frame_ms = Time.get_ticks_msec()
	_register_frame_buildings(agents as Dictionary)
```

- [ ] **Step 5: Drive the cue from `_process`**

In `_process`, just after `_panel.set_progress(i, last)` (~line 1688), add:

```gdscript
	# Live "thinking" cue (issue #372): while the backend is running but the head
	# hasn't grown for a beat and we've caught it, flag that it's deciding. Gated
	# on _is_live, so baked replay never shows it. Edge-triggered so the sidebar
	# text is only rewritten on change.
	if _is_live:
		var stalled := ThinkingIndicator.should_show(
			_is_live, _backend_run_state, i >= last,
			Time.get_ticks_msec() - _last_frame_ms, THINKING_STALL_MS)
		if stalled != _thinking:
			_thinking = stalled
			_thinking_badge.set_active(stalled)
			if _backend_run_state == "running":
				_panel.set_live_status("thinking…" if stalled else "following backend")
```

- [ ] **Step 6: Verify everything loads (headless smoke)**

Run: `./godot-generative-agents/run_smoke_test.sh`
Expected: all unit tests pass (including `test_thinking_indicator` from Task 1) AND every scene loads/paints (exit 0). This confirms `thinking_badge.gd` and the modified `viewer.gd` parse and instantiate — the badge node is created in `_ready` when the viewer scene loads.

- [ ] **Step 7: Manual acceptance (needs a live backend — deferred to the user's acceptance pass)**

Do NOT attempt this in an automated/headless run; it needs a windowed viewer following a live backend with decision stalls. Record in the report that it is deferred. The acceptance the user will run:

```bash
# Terminal 1 — serve a live sim (real-LLM stalls, or a mock brain with injected delay):
uv run python godot-generative-agents/backend/penn/serve_penn.py --tick-seconds 0.1
# Terminal 2 — follow it:
SIM_API_URL=http://127.0.0.1:8080 ./godot-generative-agents/run.sh
```
Expect: during a 5–10 s decision stall the badge + sidebar show "thinking…"; agents still glide/catch up; both clear when frames resume; baked replay unaffected.

- [ ] **Step 8: Commit**

```bash
cd /Users/yh/Documents/GitHub/agent-sandbox
godot --headless --path godot-generative-agents/godot --import >/dev/null 2>&1 || true
git add godot-generative-agents/godot/scripts/thinking_badge.gd \
        godot-generative-agents/godot/scripts/thinking_badge.gd.uid \
        godot-generative-agents/godot/scripts/viewer.gd
git commit -m "feat(viewer): live-mode thinking badge + stall wiring (#372)

Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>"
```

---

## Notes for the implementer

- **Why `i >= last` is "playhead at head":** in `_process`, `last = _frames.size() - 1` and `i = int(_t/step_seconds)` clamped so `i >= last` means the playhead has reached the newest frame — there is nothing further to ease toward, so a lack of new frames is a real visual stall (not just buffered easing).
- **Edge-triggering:** `_thinking` guards so `set_live_status`/`set_active` fire only when the state flips, not every frame. When the stall clears because the run left "running" (e.g. paused), `should_show` returns false and the `run_state == "running"` guard skips the text restore, leaving the paused/finished message the status handler already set.
- **Startup:** `_last_frame_ms` starts at 0, but `_process` returns early while `_frames` is empty and `should_show` requires `run_state == "running"`, so no false badge before the first frame.
- **Replay safety:** with `_is_live` false the `_process` block is skipped entirely and the badge is never activated, so baked replay is byte-identical.

## Self-review

- **Spec coverage:** pure `should_show`/`ellipsis` (spec §Design 1) → Task 1; the badge Control (§Design 2) → Task 2 Step 1; `_last_frame_ms` head-growth stamp + `THINKING_STALL_MS` + `_process` stall drive + sidebar flip + `_is_live` gating (§Design 3) → Task 2 Steps 2–5; headless truth-table test (§Verification) → Task 1; smoke + manual acceptance (§Verification) → Task 2 Steps 6–7; out-of-scope (no interpolation change, no per-agent, no backend) honored (no such tasks). All covered.
- **Type consistency:** `should_show(is_live, run_state, playhead_at_head, ms_since_last_frame, threshold_ms) -> bool` and `ellipsis(now_ms) -> String` and `set_active(active)` are used identically in the test, the badge, and the viewer wiring. `_backend_run_state`, `set_live_status`, `_apply_live_frame`, `$UI` all match the existing `viewer.gd`.
- **Placeholder scan:** no TBD/TODO; every code step carries complete code or an exact quoted anchor with the full snippet.
