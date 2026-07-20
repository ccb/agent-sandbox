# Day-Plans Pop-up (#251) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** A pop-up showing each agent's authored day plan as a ribbon beside what they actually did (planned vs. actual), per the approved spec `godot-generative-agents/docs/specs/2026-07-10-day-plan-ribbon.md`.

**Architecture:** Mirrors the #249 split that made headless testing possible: a pure static model (`day_plan_model.gd` — planned segments, place→address resolution learned from `"walking to "` frames, per-step actual classification) unit-tested headlessly, plus a pure-UI pop-up (`day_plan_panel.gd`) following the social-graph panel's skeleton (backdrop, `set_replay`, `show_up_to`, `close_requested`), plus wiring (sidebar button + T key, scene node on CanvasLayer 15, `_process` step pushes, click-to-seek through the existing `_on_seek`). The spec sketches everything inside `day_plan_panel.gd`; splitting the pure logic into `day_plan_model.gd` is a deliberate structural refinement so the tricky rules are unit-testable — same pattern #249 established.

**Tech Stack:** Godot 4.6 GDScript only. Headless unit tests via `godot --headless --script`, wired into `run_smoke_test.sh` with the sentinel-grep guard pattern.

## Global Constraints

- Branch: `feat/day-plan-ribbon-251` off `godot-ga-main`; PR targets `godot-ga-main`.
- GDScript style: **tabs** for indentation; `##` doc comments at file top, `#` inline; typed GDScript; scripts reference each other via `preload("res://scripts/...")` consts, not `class_name`.
- Replay shapes are pinned by `backend/contract.py` — consume, never change: `ScheduleStop = {place, activity, emoji, steps}` with `steps: null` = rest of the day; act = `"<activity> @ UPenn:<Building>:<area>"`; travel act = `"walking to <place> @ <destination address>"` (the place string is the schedule's exact place name; the address is the destination's — verified against a real bake).
- Actual-slot classification (spec): act starts with `"walking to <place>"` → **transit** toward that place (place color at 45% alpha); act address equals a resolved place address → **at** that place (solid); else **other** (neutral grey). Place→address resolution is learned from the frames' walking legs — no string heuristics.
- Reuse, don't duplicate: the act building parser already lives in `scripts/replay_markers.gd` (`static func building_of(act: String) -> String`) — the model preloads and calls it.
- New headless test scripts print the sentinel `"all checks passed"` on success and are wired into `run_smoke_test.sh` with the pipe-to-`grep -q` guard (Godot can exit 0 on `--script` PARSE errors).
- Every commit message ends with `Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>`.
- Working in the MAIN checkout: it has unrelated uncommitted changes (journal/frankie.md, *.png.import) and untracked noise — `git add` ONLY the files each task names; never `git add -A` / `git add .`.
- The Godot binary is `godot` on PATH. Run godot commands from the repo root with `--path godot-generative-agents/godot`.

---

### Task 1: The day-plan model + headless unit tests

**Files:**
- Create: `godot-generative-agents/godot/scripts/day_plan_model.gd`
- Create: `godot-generative-agents/godot/tests/test_day_plan_model.gd`
- Modify: `godot-generative-agents/run_smoke_test.sh` (second unit-test line beside the #249 one)

**Interfaces:**
- Consumes: `preload("res://scripts/replay_markers.gd").building_of(act)` (exists, from #249).
- Produces (Task 2 relies on these exact names):
  - `static func axis_len(frames_count: int, schedules: Array) -> int` — the shared time axis: `max(frames_count, largest per-schedule sum of explicit steps)`; `schedules` is an Array of schedule Arrays.
  - `static func planned_segments(schedule: Array, axis: int) -> Array` — `[{place: String, activity: String, start: int, len: int}]` laid end-to-end in step units; `null`-steps stops split the remaining axis equally (the last null absorbs integer-division leftover); empty/missing schedule → `[]`.
  - `static func actual_slots(frames: Array, name: String) -> Array` — one `{kind: String, place: String}` per frame; kind `"transit"` (place = the walking destination), `"at"` (place resolved via the learned place→address map), or `"other"` (place = the act's building, may be `""`).
  - `static func transit_place(act: String) -> String` — the `<place>` from `"walking to <place> @ ..."`, `""` if not a walking act.

- [ ] **Step 1: Write the failing test script**

Create `godot-generative-agents/godot/tests/test_day_plan_model.gd`:

```gdscript
extends SceneTree
## Headless unit tests for scripts/day_plan_model.gd (issue #251). Run:
##   godot --headless --path godot-generative-agents/godot \
##     --script res://tests/test_day_plan_model.gd
## Exit 0 = all checks pass; run_smoke_test.sh runs this before the scene smoke
## and also greps for the success sentinel (Godot can exit 0 on a parse error).

const DayPlanModel := preload("res://scripts/day_plan_model.gd")

var _failures := 0


func _check(cond: bool, name: String) -> void:
	if cond:
		print("  ok: %s" % name)
	else:
		_failures += 1
		push_error("FAIL: %s" % name)


func _frame(name: String, act: String) -> Dictionary:
	return {name: {"x": 0, "y": 0, "act": act, "e": "🙂", "chat": null}}


func _initialize() -> void:
	# --- transit_place ---
	_check(DayPlanModel.transit_place(
		"walking to Van Pelt — Kamin Gallery @ UPenn:Van Pelt Library:Kamin Gallery")
		== "Van Pelt — Kamin Gallery", "transit_place extracts the schedule place name")
	_check(DayPlanModel.transit_place("studying @ UPenn:X:y") == "",
		"transit_place empty for a non-walking act")

	# --- axis_len ---
	var sched_a := [{"place": "A", "activity": "x", "emoji": "🙂", "steps": 100},
		{"place": "B", "activity": "y", "emoji": "🙂", "steps": null}]
	var sched_b := [{"place": "C", "activity": "z", "emoji": "🙂", "steps": 300},
		{"place": "D", "activity": "w", "emoji": "🙂", "steps": 250}]
	_check(DayPlanModel.axis_len(400, [sched_a, sched_b]) == 550,
		"axis_len takes the larger of frames and explicit-step sums")
	_check(DayPlanModel.axis_len(800, [sched_a, sched_b]) == 800,
		"axis_len keeps frames when longer")

	# --- planned_segments ---
	var segs: Array = DayPlanModel.planned_segments(sched_a, 400)
	_check(segs.size() == 2, "one segment per stop")
	_check(int(segs[0]["start"]) == 0 and int(segs[0]["len"]) == 100,
		"explicit stop sized by its steps")
	_check(int(segs[1]["start"]) == 100 and int(segs[1]["len"]) == 300,
		"null-steps stop absorbs the remaining axis")
	var two_nulls := [{"place": "A", "activity": "x", "emoji": "🙂", "steps": null},
		{"place": "B", "activity": "y", "emoji": "🙂", "steps": null}]
	var segs2: Array = DayPlanModel.planned_segments(two_nulls, 401)
	_check(int(segs2[0]["len"]) == 200 and int(segs2[1]["len"]) == 201,
		"two nulls split the remainder; the last absorbs the leftover")
	_check(DayPlanModel.planned_segments([], 400).is_empty(),
		"empty schedule -> no segments")

	# --- actual_slots: transit / at (room-level!) / other ---
	var name := "Ada"
	var frames := [
		_frame(name, "walking to Van Pelt — Kamin Gallery @ UPenn:Van Pelt Library:Kamin Gallery"),
		_frame(name, "wandering exhibits @ UPenn:Van Pelt Library:Kamin Gallery"),
		_frame(name, "eating lunch @ UPenn:Houston Hall:lobby"),
	]
	var slots: Array = DayPlanModel.actual_slots(frames, name)
	_check(slots.size() == 3, "one slot per frame")
	_check(String(slots[0]["kind"]) == "transit"
		and String(slots[0]["place"]) == "Van Pelt — Kamin Gallery",
		"walking frame is transit toward the schedule place")
	_check(String(slots[1]["kind"]) == "at"
		and String(slots[1]["place"]) == "Van Pelt — Kamin Gallery",
		"perform at the learned address resolves to the ROOM-LEVEL place")
	_check(String(slots[2]["kind"]) == "other"
		and String(slots[2]["place"]) == "Houston Hall",
		"perform at an unlearned address is other, labeled by building")
	_check(DayPlanModel.actual_slots([], name).is_empty(), "no frames -> no slots")

	if _failures == 0:
		print("test_day_plan_model: all checks passed")
	quit(1 if _failures > 0 else 0)
```

- [ ] **Step 2: Run the test to verify it fails**

```bash
GODOT="$(command -v godot || echo /Applications/Godot.app/Contents/MacOS/Godot)"
"$GODOT" --headless --path godot-generative-agents/godot --script res://tests/test_day_plan_model.gd 2>&1 | tail -5
```

Expected: a SCRIPT ERROR / preload failure (`scripts/day_plan_model.gd` does not exist); no "all checks passed" line.

- [ ] **Step 3: Implement the model**

Create `godot-generative-agents/godot/scripts/day_plan_model.gd`:

```gdscript
extends RefCounted
## Pure logic for the day-plans pop-up (issue #251): turn a persona's authored
## schedule into planned ribbon segments, and classify each replay frame into
## what the agent was actually doing. Key insight (see the spec): a travel-leg
## act is "walking to <place> @ <destination address>" — it carries the
## schedule's EXACT place name with that place's resolved address, so the
## place→address mapping is learnable from the frames themselves. That is what
## lets a room-level place ("Van Pelt — Kamin Gallery", whose act building
## segment is just "Van Pelt Library") pair exactly with its planned segment.
## Pure functions over plain Arrays/Dictionaries — unit-tested headlessly
## (tests/test_day_plan_model.gd).

const ReplayMarkers := preload("res://scripts/replay_markers.gd")

const WALKING_PREFIX := "walking to "


static func axis_len(frames_count: int, schedules: Array) -> int:
	# The shared time axis: long enough for the frames we have AND the longest
	# explicitly-planned day, so live mode (frames still growing) gets a stable
	# width. `schedules` is an Array of schedule Arrays (one per persona).
	var longest := 0
	for schedule in schedules:
		var total := 0
		for stop in (schedule as Array):
			var steps: Variant = (stop as Dictionary).get("steps")
			if steps != null:
				total += int(steps)
		longest = maxi(longest, total)
	return maxi(frames_count, longest)


static func planned_segments(schedule: Array, axis: int) -> Array:
	# Lay the stops end-to-end in step units: explicit `steps` sized as
	# authored; null-steps stops split whatever the explicit ones leave,
	# the last null absorbing the integer-division leftover. (In authored
	# worlds only the final stop is null — "stay for the rest of the day".)
	if schedule.is_empty():
		return []
	var explicit := 0
	var nulls := 0
	for stop in schedule:
		var steps: Variant = (stop as Dictionary).get("steps")
		if steps == null:
			nulls += 1
		else:
			explicit += int(steps)
	var remainder := maxi(axis - explicit, 0)
	var null_share := remainder / nulls if nulls > 0 else 0
	var segments: Array = []
	var cursor := 0
	var nulls_seen := 0
	for stop in schedule:
		var steps: Variant = (stop as Dictionary).get("steps")
		var seg_len: int
		if steps == null:
			nulls_seen += 1
			# The last null takes the leftover so the ribbons end flush.
			seg_len = remainder - null_share * (nulls - 1) if nulls_seen == nulls \
				else null_share
		else:
			seg_len = int(steps)
		segments.append({"place": String((stop as Dictionary).get("place", "")),
			"activity": String((stop as Dictionary).get("activity", "")),
			"start": cursor, "len": seg_len})
		cursor += seg_len
	return segments


static func actual_slots(frames: Array, name: String) -> Array:
	# One {kind, place} per frame for this agent. Pass 1 learns place→address
	# from every walking leg; pass 2 classifies each frame: transit (toward a
	# named place), at (a learned address), or other (grey — off-plan).
	var place_by_addr := {}
	for frame in frames:
		var act := String(((frame as Dictionary).get(name, {}) as Dictionary).get("act", ""))
		if act.begins_with(WALKING_PREFIX):
			var addr := _address_of(act)
			if addr != "":
				place_by_addr[addr] = transit_place(act)
	var slots: Array = []
	for frame in frames:
		var act := String(((frame as Dictionary).get(name, {}) as Dictionary).get("act", ""))
		if act.begins_with(WALKING_PREFIX):
			slots.append({"kind": "transit", "place": transit_place(act)})
			continue
		var addr := _address_of(act)
		if place_by_addr.has(addr):
			slots.append({"kind": "at", "place": String(place_by_addr[addr])})
		else:
			slots.append({"kind": "other", "place": ReplayMarkers.building_of(act)})
	return slots


static func transit_place(act: String) -> String:
	# "walking to <place> @ <address>" -> "<place>"; "" for a non-walking act.
	if not act.begins_with(WALKING_PREFIX):
		return ""
	var rest := act.substr(WALKING_PREFIX.length())
	var at := rest.find(" @ ")
	return rest.substr(0, at) if at >= 0 else rest


static func _address_of(act: String) -> String:
	# The full address after " @ " ("" if the act has none). Kept as the raw
	# string: walking-leg and perform addresses match byte-for-byte per the
	# contract, so no normalization is needed (or wanted).
	var at := act.find(" @ ")
	return act.substr(at + 3) if at >= 0 else ""
```

**GDScript gotcha:** the conditional expression in `planned_segments` (`remainder - null_share * (nulls - 1) if nulls_seen == nulls else null_share`) spans a line break with `\` — if the parser complains, rewrite it as an explicit `if/else` block assigning `seg_len`.

- [ ] **Step 4: Run the test to verify it passes**

```bash
"$GODOT" --headless --path godot-generative-agents/godot --script res://tests/test_day_plan_model.gd 2>&1 | tail -5
```

Expected: all `ok:` lines, `test_day_plan_model: all checks passed`.

- [ ] **Step 5: Wire into the smoke script**

In `godot-generative-agents/run_smoke_test.sh`, directly below the existing `test_replay_markers.gd` guard line, add:

```bash
"$GODOT" --headless --path "$PROJECT_DIR" --script res://tests/test_day_plan_model.gd 2>&1 \
  | tee /dev/stderr | grep -q "all checks passed"
```

(The comment above the block already explains the sentinel-grep pattern; no comment change needed.)

- [ ] **Step 6: Run the full smoke script**

Run: `./godot-generative-agents/run_smoke_test.sh`
Expected: both unit-test runs' `ok:` lines, then the scene smoke, exit 0.

- [ ] **Step 7: Commit**

```bash
git add godot-generative-agents/godot/scripts/day_plan_model.gd \
  godot-generative-agents/godot/tests/test_day_plan_model.gd \
  godot-generative-agents/run_smoke_test.sh
git commit -m "feat(viewer): day-plan model — planned segments + actual classification (#251)

Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>"
```

---

### Task 2: The day-plans pop-up panel

**Files:**
- Create: `godot-generative-agents/godot/scripts/day_plan_panel.gd`

**Interfaces:**
- Consumes: `DayPlanModel.axis_len / planned_segments / actual_slots` (Task 1, exact signatures above).
- Produces (Task 4 relies on these exact names):
  - `func set_replay(frames: Array, names: Array, persona_detail: Dictionary) -> void` (frames held BY REFERENCE — live appends flow in; `persona_detail` is viewer's name→persona-meta dict)
  - `func show_up_to(step: int) -> void`
  - `signal close_requested`
  - `signal seek_requested(step: int)`

- [ ] **Step 1: Write the panel**

Create `godot-generative-agents/godot/scripts/day_plan_panel.gd`:

```gdscript
extends Control
## The day-plans pop-up (issue #251): each agent's authored day as a "plan"
## ribbon beside an "actual" ribbon on one shared time axis, so plan-vs-reality
## drift (travel time, contention, detours) is visible at a glance. The actual
## ribbon fills only up to the current playback step — same "up to now"
## philosophy as the heatmap, and spoiler-free; a faded slot is transit toward
## that place, grey is off-plan. Click a ribbon to seek (the viewer ignores it
## in live mode). Like the other pop-ups this is pure UI: viewer.gd hands it
## the replay via set_replay() (frames BY REFERENCE, so live appends flow in)
## and drives it with show_up_to(step).

## Emitted when the user asks to close (the Close button or a backdrop click).
signal close_requested
## The user clicked a ribbon: seek to `step`. Routed to viewer's _on_seek,
## which guards live mode.
signal seek_requested(step: int)

const DayPlanModel := preload("res://scripts/day_plan_model.gd")

# Same modal wash as the heatmap/social-graph pop-ups.
const BACKDROP_COLOR := Color(0.06, 0.07, 0.10, 0.82)
# Colors assigned to scheduled places in order of first appearance — hues that
# stay apart on the parchment panel (pack blue/green + warm accents).
const PLACE_PALETTE := [
	Color("0099db"), Color("3e8948"), Color("feae34"), Color("7b4fbe"),
	Color("f77622"), Color("2c6e8f"), Color("b13e53"), Color("5d853a"),
]
const OTHER_COLOR := Color(0.55, 0.53, 0.50)   # off-plan / unscheduled
const TRANSIT_ALPHA := 0.45                     # faded destination color
const BAR_H := 14        # ribbon height, px
const BAR_GAP := 4       # gap between an agent's plan and actual bars
const ROW_GAP := 14      # gap between agents
const NAME_W := 150.0    # left column for agent names
const CURSOR_COLOR := Color(0.95, 0.30, 0.20)

var _frames: Array = []          # by reference from the viewer
var _names: Array = []
var _detail := {}                # name -> persona meta (schedule lives here)
var _step := 0                   # current playback step (show_up_to)
var _place_color := {}           # place name -> Color, from schedule order
var _planned := {}               # name -> Array of planned segments
var _slots := {}                 # name -> cached actual_slots
var _slots_at := -1              # _frames.size() the cache was built at
var _panel: PanelContainer
var _canvas: Control
var _legend: Label


func _ready() -> void:
	set_anchors_preset(Control.PRESET_FULL_RECT)

	var backdrop := ColorRect.new()
	backdrop.color = BACKDROP_COLOR
	backdrop.set_anchors_preset(Control.PRESET_FULL_RECT)
	backdrop.gui_input.connect(_on_backdrop_input)
	add_child(backdrop)

	var center := CenterContainer.new()
	center.set_anchors_preset(Control.PRESET_FULL_RECT)
	# Clicks in the margin around the panel fall through to the backdrop.
	center.mouse_filter = Control.MOUSE_FILTER_IGNORE
	add_child(center)

	_panel = PanelContainer.new()
	center.add_child(_panel)

	var margin := MarginContainer.new()
	for side in ["left", "top", "right", "bottom"]:
		margin.add_theme_constant_override("margin_" + side, 14)
	_panel.add_child(margin)

	var col := VBoxContainer.new()
	col.add_theme_constant_override("separation", 10)
	margin.add_child(col)

	var title := Label.new()
	title.text = "Day plans — planned vs. actual, up to now"
	title.theme_type_variation = "TitleRibbon"
	title.horizontal_alignment = HORIZONTAL_ALIGNMENT_CENTER
	col.add_child(title)

	_canvas = Control.new()
	_canvas.draw.connect(_draw_canvas)
	_canvas.gui_input.connect(_on_canvas_input)
	col.add_child(_canvas)

	_legend = Label.new()
	_legend.add_theme_font_size_override("font_size", 16)
	_legend.autowrap_mode = TextServer.AUTOWRAP_WORD_SMART
	col.add_child(_legend)

	var close := Button.new()
	close.text = "Close"
	close.size_flags_horizontal = Control.SIZE_SHRINK_CENTER
	close.pressed.connect(func() -> void: close_requested.emit())
	col.add_child(close)


func set_replay(frames: Array, names: Array, persona_detail: Dictionary) -> void:
	# Hand-off from the viewer (baked load, live handshake, or reset respawn).
	# frames is held BY REFERENCE so live appends flow into the actual ribbons.
	_frames = frames
	_names = names
	_detail = persona_detail
	_slots.clear()
	_slots_at = -1
	# Palette: place -> color in order of first appearance across schedules,
	# shared by planned segments and actual slots so pairs read instantly.
	_place_color.clear()
	_planned.clear()
	for name in _names:
		for stop in _schedule_of(String(name)):
			var place := String((stop as Dictionary).get("place", ""))
			if not _place_color.has(place):
				_place_color[place] = PLACE_PALETTE[_place_color.size() % PLACE_PALETTE.size()]
	var legend := PackedStringArray()
	for place in _place_color:
		legend.append("■ %s" % place)
	legend.append("■ off-plan / other (grey); faded = walking there")
	_legend.text = "   ".join(legend)
	# Height: one name line + two bars per agent. Width: a wide fixed canvas
	# (the panel centers on screen; the campus window is 1280+ wide).
	var row_h := BAR_H * 2 + BAR_GAP + ROW_GAP + 18
	_canvas.custom_minimum_size = Vector2(860, _names.size() * row_h)
	queue_redraw_all()


func show_up_to(step: int) -> void:
	_step = step
	queue_redraw_all()


func queue_redraw_all() -> void:
	if _canvas != null:
		_canvas.queue_redraw()


func _schedule_of(name: String) -> Array:
	return (_detail.get(name, {}) as Dictionary).get("schedule", []) as Array


func _axis() -> int:
	var schedules: Array = []
	for name in _names:
		schedules.append(_schedule_of(String(name)))
	return maxi(DayPlanModel.axis_len(_frames.size(), schedules), 1)


func _bars_x() -> float:
	return NAME_W


func _bars_w() -> float:
	return maxf(_canvas.size.x - NAME_W, 1.0)


func _row_top(idx: int) -> float:
	var row_h := BAR_H * 2 + BAR_GAP + ROW_GAP + 18
	return idx * row_h


func _ensure_slots() -> void:
	# Cache actual_slots per agent; rebuild only when the frame buffer grew
	# (live) or was swapped (reset) — the pass over frames is cheap but not
	# free at every redraw.
	if _slots_at == _frames.size():
		return
	_slots_at = _frames.size()
	for name in _names:
		_slots[name] = DayPlanModel.actual_slots(_frames, String(name))


func _draw_canvas() -> void:
	if _names.is_empty():
		return
	_ensure_slots()
	var axis := _axis()
	var font := get_theme_default_font()
	var font_size := get_theme_default_font_size()
	for idx in _names.size():
		var name := String(_names[idx])
		var top := _row_top(idx)
		_canvas.draw_string(font, Vector2(0, top + 14), name,
			HORIZONTAL_ALIGNMENT_LEFT, NAME_W - 8, font_size)
		var plan_y := top + 18
		var actual_y := plan_y + BAR_H + BAR_GAP
		# Planned ribbon: full width, known up front.
		var segs: Array = _planned_of(name, axis)
		if segs.is_empty():
			_canvas.draw_rect(Rect2(_bars_x(), plan_y, _bars_w(), BAR_H),
				Color(OTHER_COLOR, 0.5))
			_canvas.draw_string(font, Vector2(_bars_x() + 6, plan_y + 12),
				"no authored plan", HORIZONTAL_ALIGNMENT_LEFT, -1, 12)
		for seg in segs:
			var x := _bars_x() + int(seg["start"]) / float(axis) * _bars_w()
			var w := int(seg["len"]) / float(axis) * _bars_w()
			_canvas.draw_rect(Rect2(x, plan_y, w, BAR_H),
				_color_for(String(seg["place"])))
		# Actual ribbon: only up to the current step, batched into runs of the
		# same color so a 1200-step day is a handful of rects, not 1200.
		var slots: Array = _slots.get(name, [])
		var upto := mini(_step, slots.size() - 1)
		var run_start := 0
		while run_start <= upto:
			var run_color := _slot_color(slots[run_start])
			var run_end := run_start
			while run_end + 1 <= upto and _slot_color(slots[run_end + 1]) == run_color:
				run_end += 1
			var x := _bars_x() + run_start / float(axis) * _bars_w()
			var w := (run_end - run_start + 1) / float(axis) * _bars_w()
			_canvas.draw_rect(Rect2(x, actual_y, w, BAR_H), run_color)
			run_start = run_end + 1
		# Now-cursor across both bars.
		var cx := _bars_x() + _step / float(axis) * _bars_w()
		_canvas.draw_rect(Rect2(cx - 1, plan_y - 2, 2, BAR_H * 2 + BAR_GAP + 4),
			CURSOR_COLOR)


func _planned_of(name: String, axis: int) -> Array:
	if not _planned.has(name):
		_planned[name] = DayPlanModel.planned_segments(_schedule_of(name), axis)
	return _planned[name]


func _color_for(place: String) -> Color:
	return _place_color.get(place, OTHER_COLOR)


func _slot_color(slot: Dictionary) -> Color:
	match String(slot["kind"]):
		"at":
			return _color_for(String(slot["place"]))
		"transit":
			var c: Color = _color_for(String(slot["place"]))
			return Color(c, TRANSIT_ALPHA)
		_:
			return OTHER_COLOR


func _on_canvas_input(event: InputEvent) -> void:
	if not (event is InputEventMouseButton and event.pressed
			and (event as InputEventMouseButton).button_index == MOUSE_BUTTON_LEFT):
		return
	var x := (event as InputEventMouseButton).position.x
	if x < _bars_x():
		return
	var step := clampi(roundi((x - _bars_x()) / _bars_w() * _axis()), 0,
		maxi(_frames.size() - 1, 0))
	seek_requested.emit(step)
	_canvas.accept_event()


func _get_tooltip(at_position: Vector2) -> String:
	# Anchored on the whole pop-up Control; translate into canvas space.
	var pos := at_position - _canvas.get_global_rect().position + get_global_rect().position
	return _canvas_tooltip(pos)


func _canvas_tooltip(pos: Vector2) -> String:
	if _names.is_empty() or pos.x < _bars_x():
		return ""
	_ensure_slots()
	var axis := _axis()
	var step := clampi(int((pos.x - _bars_x()) / _bars_w() * axis), 0, axis - 1)
	for idx in _names.size():
		var name := String(_names[idx])
		var top := _row_top(idx)
		var plan_y := top + 18
		var actual_y := plan_y + BAR_H + BAR_GAP
		if pos.y >= plan_y and pos.y < plan_y + BAR_H:
			var segs: Array = _planned_of(name, axis)
			for i in segs.size():
				var seg: Dictionary = segs[i]
				if step >= int(seg["start"]) and step < int(seg["start"]) + int(seg["len"]):
					return "%d. %s @ %s — %d steps" % [i + 1,
						String(seg["activity"]), String(seg["place"]), int(seg["len"])]
			return ""
		if pos.y >= actual_y and pos.y < actual_y + BAR_H:
			var slots: Array = _slots.get(name, [])
			if step >= slots.size() or step > _step:
				return ""
			var slot: Dictionary = slots[step]
			match String(slot["kind"]):
				"transit":
					return "walking to %s" % String(slot["place"])
				"at":
					return "at %s" % String(slot["place"])
				_:
					var b := String(slot["place"])
					return "off-plan: %s" % b if b != "" else "off-plan"
	return ""


func _on_backdrop_input(event: InputEvent) -> void:
	# A click on the dim outside the panel closes the pop-up (same contract as
	# the heatmap/social-graph backdrops).
	if event is InputEventMouseButton and event.pressed:
		close_requested.emit()
```

**GDScript gotchas for the implementer:**
- `Color(c, TRANSIT_ALPHA)` is the Color-with-new-alpha constructor — valid Godot 4.
- If `_get_tooltip`'s global-rect translation misbehaves (tooltips at wrong rows), move the `_get_tooltip` override onto a small `extends Control` inner pattern is NOT available — instead set `_canvas.tooltip_text` dynamically from `_on_canvas_input` mouse-motion events. Simpler fallback: connect `_canvas.mouse_entered`/motion via `_canvas.gui_input` for `InputEventMouseMotion` and set `_canvas.tooltip_text = _canvas_tooltip(motion.position)`. Either mechanism satisfies the spec ("hovering names the stop/slot"); prefer whichever you verify works headlessly-cleanly (no errors) and keep ONE of them, not both.
- The ternary in `_canvas_tooltip`'s last branch (`"off-plan: %s" % b if b != "" else "off-plan"`) — if the parser complains, split into an if/else.

- [ ] **Step 2: Syntax-check headlessly**

```bash
"$GODOT" --headless --path godot-generative-agents/godot --script res://tests/test_day_plan_model.gd 2>&1 | grep -E "SCRIPT ERROR|all checks passed"
```

Expected: only `test_day_plan_model: all checks passed` (a parse error in ANY res:// script would print SCRIPT ERROR lines). Also run `./godot-generative-agents/run_smoke_test.sh` — exit 0.

- [ ] **Step 3: Commit**

```bash
git add godot-generative-agents/godot/scripts/day_plan_panel.gd
git commit -m "feat(viewer): day-plans pop-up panel (#251)

Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>"
```

---

### Task 3: Sidebar button + signal (agent_panel.gd)

**Files:**
- Modify: `godot-generative-agents/godot/scripts/agent_panel.gd`

**Interfaces:**
- Produces (Task 4 relies on this exact name): `signal day_plans_requested` on the panel.

- [ ] **Step 1: Add the signal**

In `agent_panel.gd`, after the `social_graph_requested` signal declaration (~line 39), add:

```gdscript
# The "Day plans" button was pressed (open/close the planned-vs-actual pop-up,
# issue #251). Same contract as heatmap_requested: a toggle request (T does the same).
signal day_plans_requested
```

- [ ] **Step 2: Add the calendar glyph**

After the `GALLERY_ROWS` const block (~line 188), add (same hand-drawn treatment as the flame/graph/camera/gallery glyphs — the pack has no calendar):

```gdscript
# No calendar glyph in the pack either (issue #251): a little page-a-day
# calendar — two binding pegs, an amber header band, a dotted grid of days —
# in the pack's dark outline.
const CALENDAR_PALETTE := {
	"#": Color("181425"),  # outline + pegs
	"a": Color("feae34"),  # header band (pack amber)
	"w": Color("fff4b8"),  # page
	"d": Color("8b9bb4"),  # day dots
}
const CALENDAR_ROWS: PackedStringArray = [
	"................",
	"...##......##...",
	"...##......##...",
	".##############.",
	".#aaaaaaaaaaaa#.",
	".#aaaaaaaaaaaa#.",
	".##############.",
	".#wwwwwwwwwwww#.",
	".#wddwddwddwdw#.",
	".#wwwwwwwwwwww#.",
	".#wddwddwddwdw#.",
	".#wwwwwwwwwwww#.",
	".#wddwwddwwddw#.",
	".#wwwwwwwwwwww#.",
	".##############.",
	"................",
]
```

- [ ] **Step 3: Add the icon factory + button**

After `_gallery_icon()` (~line 406), add:

```gdscript
static func _calendar_icon() -> Texture2D:
	return _bitmap_icon(CALENDAR_ROWS, CALENDAR_PALETTE)
```

In `_ready()`, in the view-controls row right after the Social graph button (~line 281), add:

```gdscript
	# Day plans: the hand-drawn calendar glyph (see CALENDAR_ROWS).
	view_row.add_child(_icon_button(
		_calendar_icon(), "Day plans — planned vs. actual, up to now (T)",
		func() -> void: day_plans_requested.emit()))
```

- [ ] **Step 4: Verify + commit**

Run: `./godot-generative-agents/run_smoke_test.sh` — exit 0, and grep the output for "SCRIPT ERROR" (must be absent).

```bash
git add godot-generative-agents/godot/scripts/agent_panel.gd
git commit -m "feat(viewer): Day plans sidebar button + calendar glyph (#251)

Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>"
```

---

### Task 4: Scene node + viewer wiring

**Files:**
- Modify: `godot-generative-agents/godot/scenes/viewer.tscn` (header + a new CanvasLayer at the end of the pop-up nodes)
- Modify: `godot-generative-agents/godot/scripts/viewer.gd`

**Interfaces:**
- Consumes: `day_plan_panel.gd` (Task 2: `set_replay(frames, names, persona_detail)`, `show_up_to(step)`, `close_requested`, `seek_requested(step)`); `_panel.day_plans_requested` (Task 3).
- Produces: nothing new (end of the chain).

- [ ] **Step 1: Scene node**

In `godot-generative-agents/godot/scenes/viewer.tscn`:

1. Header line 1: bump `load_steps=14` → `load_steps=15`.
2. After the `13_snapgallery` ext_resource line, add:

```
[ext_resource type="Script" path="res://scripts/day_plan_panel.gd" id="14_dayplans"]
```

3. After the `SnapshotGallery` node block (the file's last pop-up), add:

```
; Day-plans pop-up (day_plan_panel.gd, issue #251): each agent's authored day
; plan beside what they actually did, on one shared time axis. On its OWN
; CanvasLayer above the other modals (heatmap 11, inspector 12, social graph 13,
; gallery 14) so its dim covers everything and Esc closes it first. Hidden until
; opened (the sidebar's Day plans button / T); viewer.gd feeds it the replay.
[node name="DayPlanLayer" type="CanvasLayer" parent="."]
layer = 15

[node name="DayPlanPanel" type="Control" parent="DayPlanLayer"]
visible = false
script = ExtResource("14_dayplans")
```

- [ ] **Step 2: Viewer members + connections**

In `viewer.gd`:

1. After `@onready var _gallery = ...` (~line 235):

```gdscript
@onready var _day_plans = $DayPlanLayer/DayPlanPanel  # day_plan_panel.gd pop-up (#251)
```

2. Next to `var _last_graph_step := -1` (~line 164):

```gdscript
# Step the day-plans pop-up last drew (same push-on-change contract as the
# heatmap/social graph, issue #251).
var _last_plan_step := -1
```

3. In `_ready()`, after the social-graph connections (~line 282):

```gdscript
	# Day-plans pop-up (issue #251): the sidebar calendar button (or T) toggles
	# it; ribbon clicks seek through the same path as the scrubber (_on_seek
	# already ignores seeks in live mode).
	_panel.day_plans_requested.connect(_toggle_day_plans)
	_day_plans.close_requested.connect(_close_day_plans)
	_day_plans.seek_requested.connect(_on_seek)
```

- [ ] **Step 3: Replay hand-offs**

1. In `_load_replay_from_text`, after the `_social_graph.set_replay(...)` call (~line 498):

```gdscript
	# And to the day-plans pop-up (issue #251): schedules from the meta's
	# persona detail, actuals derived from the same by-reference frame buffer.
	_day_plans.set_replay(_frames, _names, _persona_detail)
```

2. In `_spawn_from_meta`, after its `_social_graph.set_replay(...)` call (~line 545):

```gdscript
	# Day-plans pop-up: same by-reference hand-off, so live frames flow into
	# the actual ribbons as they arrive (planned is known from the meta now).
	_day_plans.set_replay(_frames, _names, _persona_detail)
```

- [ ] **Step 4: Toggle/open/close + key + Esc + snapshot guard + step push**

1. After `_close_social_graph()` (~line 1389), add:

```gdscript
func _toggle_day_plans() -> void:
	if _day_plans.visible:
		_close_day_plans()
	else:
		_open_day_plans()


func _open_day_plans() -> void:
	# Show plans against progress up to the step on screen right now; playback
	# keeps running behind the pop-up (it live-updates via _process). No
	# camera-keyboard suppression: this pop-up has no arrow-key views.
	if not _frames.is_empty():
		var last := maxi(_frames.size() - 1, 0)
		var i := mini(int(_t / step_seconds), last)
		_last_plan_step = i
		_day_plans.show_up_to(i)
	_day_plans.visible = true


func _close_day_plans() -> void:
	_day_plans.visible = false
```

2. In `_unhandled_input`'s `match` (~line 1291, beside KEY_G), add:

```gdscript
		KEY_T:
			# Toggle the day-plans pop-up (issue #251).
			_toggle_day_plans()
			get_viewport().set_input_as_handled()
```

(First `grep -n "KEY_T" godot-generative-agents/godot/scripts/*.gd` to confirm nothing else claims T; expected: no hits.)

3. In the `KEY_ESCAPE` branch, the day-plans pop-up is now the topmost layer (15) — add it FIRST, before the `_gallery.visible` check, and update the stacking-order comment:

```gdscript
		KEY_ESCAPE:
			# Close the topmost open modal first (their CanvasLayer stacking order:
			# day plans 15 > gallery 14 > social graph 13 > inspector 12 > heatmap 11).
			if _day_plans.visible:
				_close_day_plans()
				get_viewport().set_input_as_handled()
			elif _gallery.visible:
```

4. In `_take_snapshot`'s modal guard (~line 1395), extend the condition:

```gdscript
	if _heatmap.visible or _inspector.visible or _social_graph.visible \
			or _gallery.visible or _day_plans.visible:
		return
```

5. In `_process`, after the social-graph push block (~line 1562):

```gdscript
	# Same for the day-plans pop-up: the actual ribbons + cursor advance as the
	# playhead crosses each step while it's open.
	if _day_plans.visible and i != _last_plan_step:
		_last_plan_step = i
		_day_plans.show_up_to(i)
```

- [ ] **Step 5: Verify (smoke + data-driven)**

Run: `./godot-generative-agents/run_smoke_test.sh` — exit 0, no "SCRIPT ERROR" in output.

Data-driven check (do NOT commit the print): after the `_day_plans.set_replay(...)` line in `_load_replay_from_text`, temporarily add
`print("day_plans: axis=", _day_plans._axis(), " segs=", _day_plans._planned_of(_names[0], _day_plans._axis()).size())`
then:

```bash
LLM_PROVIDER=mock uv run python godot-generative-agents/backend/penn/generate_penn_replay.py --steps 400
timeout 15 "$GODOT" --headless --path godot-generative-agents/godot res://scenes/viewer.tscn 2>&1 | grep "day_plans:" || true
```

Expected: `day_plans: axis=400 segs=N` with N ≥ 1 (the cast's first persona has an authored multi-stop schedule). Remove the print; confirm `git diff` on viewer.gd shows no `print(` before committing.

- [ ] **Step 6: Commit**

```bash
git add godot-generative-agents/godot/scenes/viewer.tscn godot-generative-agents/godot/scripts/viewer.gd
git commit -m "feat(viewer): wire the day-plans pop-up — scene node, T key, step pushes (#251)

Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>"
```

---

### Task 5: End-to-end verification + PR

**Files:**
- No code changes (verification + push).

**Interfaces:** n/a.

- [ ] **Step 1: Full local gate**

```bash
./godot-generative-agents/run_smoke_test.sh
uv run pytest godot-generative-agents/tests/ -q
uv run black --check .
```

Expected: smoke exit 0 (both unit suites + scenes); backend suite green (nothing Python changed); black clean.

- [ ] **Step 2: Manual visual pass (ask the user)**

Launch `./godot-generative-agents/run.sh`, play the bundled replay, and confirm the spec's checklist: T and the calendar button open the pop-up; one plan/actual pair per agent; colors match between the pair (including the room-level Van Pelt places); the cursor tracks playback and actual ribbons stop at "now"; transit reads faded, off-plan grey; clicking a ribbon seeks; tooltips name stops/slots; Esc closes it first; in live mode ribbons grow and clicks don't seek. The user does the eyeballing — report the checklist and wait for their confirmation before merge (not before PR).

- [ ] **Step 3: Push + PR**

```bash
git -c credential.helper='!gh auth git-credential' push https://github.com/ccb/agent-sandbox.git feat/day-plan-ribbon-251
```

Then create the PR with `gh pr create --repo ccb/agent-sandbox --base godot-ga-main --head feat/day-plan-ribbon-251 --title "feat(viewer): day-plans pop-up — planned vs. actual ribbons (#251)" --body-file <file>`, where the body file contains:

```markdown
## What

A pop-up (sidebar calendar button / T) showing each agent's authored day plan
as a ribbon beside what they actually did, on one shared time axis with a
now-cursor — per `godot-generative-agents/docs/specs/2026-07-10-day-plan-ribbon.md`.
The issue asked for a bake change, but the plan is already in the replay
(`meta.personas[].schedule`, pinned by the #305 contract) — this is viewer-only.

## How

- `scripts/day_plan_model.gd` (new, pure + unit-tested): planned segments from
  the schedule (null-steps stops absorb the remaining day); place→address
  resolution learned from `"walking to <place> @ <address>"` travel legs — so
  room-level places ("Van Pelt — Kamin Gallery") pair exactly, no heuristics;
  per-step classification into at / transit / off-plan.
- `scripts/day_plan_panel.gd` (new, pure UI): the modal, following the
  social-graph skeleton; actual ribbons fill only up to "now" (spoiler-free,
  like the heatmap); transit draws as the faded destination color; clicks seek
  through the existing `_on_seek` (ignored live); frames held by reference so
  live ribbons grow.
- `agent_panel.gd`: hand-drawn calendar glyph + `day_plans_requested`.
- `viewer.tscn`/`viewer.gd`: CanvasLayer 15 (topmost; Esc closes it first),
  T key, per-step `show_up_to` pushes, snapshot-guard inclusion.
- `run_smoke_test.sh`: second headless unit suite (with the parse-error
  sentinel guard).

## Verification

Headless unit checks green (both suites); smoke PASS; backend pytest + black
untouched and green; fresh 400-step bake shows real planned segments flowing.
Manual visual pass pending before merge.

Closes #251.

🤖 Generated with [Claude Code](https://claude.com/claude-code)
```

Expected: PR URL printed; then `gh pr checks <n>` all green.

---

## Self-Review

- **Spec coverage:** pop-up skeleton + button/T + layer-15 modal (Tasks 2–4); planned ribbon rules incl. null-splitting and "no authored plan" (Task 1 model + Task 2 rendering); actual classification transit/at/other with learned place→address (Task 1, room-level case unit-tested); shared axis `max(frames, longest explicit plan)` (Task 1); up-to-now actual + cursor (Task 2); click-to-seek via `_on_seek` with its live guard, per-step pushes, Esc ordering, snapshot guard (Task 4); legend + tooltips (Task 2); live/reset re-hand-off via `_spawn_from_meta` (Task 4). Out-of-scope items from the spec (arena granularity, activity diffing, plan revisions) have no tasks — correct. ✓
- **Placeholder scan:** no TBDs; the one alternative offered (tooltip mechanism fallback) specifies both concrete options and instructs keeping exactly one. ✓
- **Type consistency:** `axis_len(frames_count: int, schedules: Array)`, `planned_segments(schedule, axis)` → `{place, activity, start, len}`, `actual_slots(frames, name)` → `{kind, place}` are identical in Tasks 1/2; `set_replay(frames, names, persona_detail)` / `show_up_to(step)` / `close_requested` / `seek_requested(step)` match between Tasks 2/4; `day_plans_requested` matches between Tasks 3/4. ✓
