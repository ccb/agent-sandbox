# Timeline Event Markers (#249) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Colored, clickable tick marks above the replay scrubber for interesting moments (game events, chat onsets, reflections, arrivals), per the approved spec `godot-generative-agents/docs/specs/2026-07-10-timeline-markers.md`.

**Architecture:** A pure static helper (`replay_markers.gd`) scans the loaded replay once and returns marker dictionaries; a small custom-draw Control (`timeline_markers.gd`) renders them above the existing `HSlider` in the sidebar and re-emits clicks as seeks; `agent_panel.gd`/`viewer.gd` gain only wiring. No Python, no replay-format change.

**Tech Stack:** Godot 4.6 GDScript only. Headless unit tests via `godot --headless --script` (new, wired into `run_smoke_test.sh`).

## Global Constraints

- Branch: `feat/timeline-markers-249` off `godot-ga-main`; PR targets `godot-ga-main`.
- GDScript style: **tabs** for indentation; `##` doc comments at file top, `#` inline; typed GDScript (`var x := ...`, typed params) matching the existing scripts; scripts reference each other via `preload("res://scripts/...")` consts, not `class_name`.
- Replay shapes are pinned by `backend/contract.py` — consume them, never change them: `EventState = {turn, actor, action, summary, payload}`, `MemoryRecord = {kind, importance, text, created_turn}`, `AgentFrame.chat = [[speaker, line], ...] | null`, act = `"<activity> @ UPenn:<Building>:<area>"`, travel act = `"walking to <place> @ <destination address>"`.
- Every commit message ends with `Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>`.
- The Godot binary resolves like `run_smoke_test.sh` does: `godot` on PATH, else `/Applications/Godot.app/Contents/MacOS/Godot`. Run all godot commands from the repo root with `--path godot-generative-agents/godot`.

---

### Task 1: Marker collection helper + headless unit tests

**Files:**
- Create: `godot-generative-agents/godot/scripts/replay_markers.gd`
- Create: `godot-generative-agents/godot/tests/test_replay_markers.gd`
- Modify: `godot-generative-agents/run_smoke_test.sh` (run the unit script before the scene smoke)

**Interfaces:**
- Consumes: nothing (pure functions over plain Arrays/Dictionaries).
- Produces (later tasks rely on these exact names):
  - `static func collect(frames: Array, names: Array, memory_streams: Dictionary, events: Array) -> Array` — returns marker Dictionaries `{step: int, kind: String, agent: String, label: String}`, sorted by step. Kinds: `"event"`, `"chat"`, `"reflection"`, `"arrival"`.
  - `static func building_of(act: String) -> String` — the `<Building>` segment of an act address, `""` if malformed (verbatim move of `viewer.gd:_building_of`'s logic).

- [ ] **Step 1: Write the failing test script**

Create `godot-generative-agents/godot/tests/test_replay_markers.gd` (new `tests/` dir):

```gdscript
extends SceneTree
## Headless unit tests for scripts/replay_markers.gd (issue #249). Run:
##   godot --headless --path godot-generative-agents/godot \
##     --script res://tests/test_replay_markers.gd
## Exit 0 = all checks pass; 1 = at least one failed (run_smoke_test.sh runs
## this before the scene smoke).

const ReplayMarkers := preload("res://scripts/replay_markers.gd")

var _failures := 0


func _check(cond: bool, name: String) -> void:
	if cond:
		print("  ok: %s" % name)
	else:
		_failures += 1
		push_error("FAIL: %s" % name)


func _frame(act_by_name: Dictionary, chat_by_name := {}) -> Dictionary:
	# Build one replay frame: name -> AgentFrame (only the fields collect reads).
	var frame := {}
	for name in act_by_name:
		frame[name] = {"x": 0, "y": 0, "act": act_by_name[name], "e": "🙂",
			"chat": chat_by_name.get(name)}
	return frame


func _of_kind(markers: Array, kind: String) -> Array:
	return markers.filter(func(m: Dictionary) -> bool: return m["kind"] == kind)


func _initialize() -> void:
	var names := ["Ada"]
	# A 4-step day: walk to the library (0), study there (1, 2), walk off (3).
	var frames := [
		_frame({"Ada": "walking to Van Pelt — Kamin Gallery @ UPenn:Van Pelt Library:Kamin Gallery"}),
		_frame({"Ada": "studying @ UPenn:Van Pelt Library:Kamin Gallery"}),
		_frame({"Ada": "studying @ UPenn:Van Pelt Library:Kamin Gallery"},
			{"Ada": [["Ada", "hello"]]}),
		_frame({"Ada": "walking to Houston Hall @ UPenn:Houston Hall:lobby"}),
	]

	# --- building_of ---
	_check(ReplayMarkers.building_of("studying @ UPenn:Van Pelt Library:lobby")
		== "Van Pelt Library", "building_of extracts the middle segment")
	_check(ReplayMarkers.building_of("gibberish") == "", "building_of malformed -> empty")

	# --- arrivals: the 'walking to ' prefix DISAPPEARING marks arrival ---
	var markers: Array = ReplayMarkers.collect(frames, names, {}, [])
	var arrivals := _of_kind(markers, "arrival")
	_check(arrivals.size() == 1, "exactly one arrival (step 3 is a departure, not an arrival)")
	_check(arrivals[0]["step"] == 1, "arrival at the first non-walking step")
	_check(arrivals[0]["agent"] == "Ada", "arrival carries the agent")
	_check("Van Pelt Library" in String(arrivals[0]["label"]), "arrival label names the building")

	# --- chat onsets: null -> non-empty is an onset; continuation is not ---
	var chats := _of_kind(markers, "chat")
	_check(chats.size() == 1 and chats[0]["step"] == 2, "one chat onset at step 2")
	var frames_chat0 := [
		_frame({"Ada": "a @ UPenn:X:y"}, {"Ada": [["Ada", "hi"]]}),
		_frame({"Ada": "a @ UPenn:X:y"}, {"Ada": [["Ada", "hi"], ["Bo", "yo"]]}),
	]
	var chats0 := _of_kind(ReplayMarkers.collect(frames_chat0, names, {}, []), "chat")
	_check(chats0.size() == 1 and chats0[0]["step"] == 0, "chat already active at step 0 is one onset at 0")

	# --- reflections come from memory_streams ---
	var streams := {"Ada": [
		{"kind": "reflection", "importance": 8, "text": "I study best in the morning.", "created_turn": 2},
		{"kind": "observation", "importance": 2, "text": "saw a bird", "created_turn": 1},
	]}
	var refl := _of_kind(ReplayMarkers.collect(frames, names, streams, []), "reflection")
	_check(refl.size() == 1 and refl[0]["step"] == 2, "one reflection marker at created_turn")

	# --- game events (the #476 run record) ---
	var events := [
		{"turn": 3, "actor": "Ada", "action": "drink", "summary": "drank unboiled water", "payload": {}},
		{"turn": 99, "actor": "Ada", "action": "x", "summary": "out of range", "payload": {}},
	]
	var evts := _of_kind(ReplayMarkers.collect(frames, names, {}, events), "event")
	_check(evts.size() == 1 and evts[0]["step"] == 3, "in-range event kept, out-of-range dropped")
	_check(String(evts[0]["label"]) == "Ada: drank unboiled water", "event label is 'actor: summary'")

	# --- robustness + ordering ---
	var all := ReplayMarkers.collect(frames, names, streams, events)
	var steps := all.map(func(m: Dictionary) -> int: return m["step"])
	var steps_sorted: Array = steps.duplicate()
	steps_sorted.sort()
	_check(steps == steps_sorted, "markers are sorted by step")
	_check(ReplayMarkers.collect([], [], {}, []).is_empty(), "empty replay -> no markers, no crash")

	if _failures == 0:
		print("test_replay_markers: all checks passed")
	quit(1 if _failures > 0 else 0)
```

- [ ] **Step 2: Run the test to verify it fails**

```bash
GODOT="$(command -v godot || echo /Applications/Godot.app/Contents/MacOS/Godot)"
"$GODOT" --headless --path godot-generative-agents/godot --script res://tests/test_replay_markers.gd; echo "exit=$?"
```

Expected: parse/preload error (`scripts/replay_markers.gd` does not exist), non-zero exit.

- [ ] **Step 3: Implement the helper**

Create `godot-generative-agents/godot/scripts/replay_markers.gd`:

```gdscript
extends RefCounted
## Pure marker collection for the timeline scrubber (issue #249): scan a loaded
## replay once and return the "interesting moments" as marker dictionaries
## {step, kind, agent, label}, sorted by step. Four sources, four kinds:
##   event      — the #476 game-event run record (replay top-level `events`)
##   chat       — a conversation onset (an agent's `chat` goes empty -> non-empty)
##   reflection — a reflection forming (memory_streams, kind == "reflection")
##   arrival    — a travel leg ending (the "walking to " act prefix disappears;
##                during travel the act address is already the DESTINATION's, so
##                an address change marks departure — the prefix is the signal,
##                same convention serve_penn.py keys on)
## Pure functions over plain Arrays/Dictionaries — no scene nodes, so the whole
## file is unit-testable headlessly (tests/test_replay_markers.gd).

# A travel-leg act reads "walking to <place> @ <destination address>"
# (run_simulation.py step()); everything else is "<activity> @ <address>".
const WALKING_PREFIX := "walking to "


static func collect(frames: Array, names: Array, memory_streams: Dictionary,
		events: Array) -> Array:
	var markers: Array = []
	var last := frames.size() - 1
	if last < 0:
		return markers

	# Game events: one marker per record; the record's `turn` is the frame index.
	for rec in events:
		var step := int((rec as Dictionary).get("turn", -1))
		if step < 0 or step > last:
			continue
		var actor := String((rec as Dictionary).get("actor", ""))
		markers.append({"step": step, "kind": "event", "agent": actor,
			"label": "%s: %s" % [actor, String((rec as Dictionary).get("summary", ""))]})

	# Reflections: from each persona's full memory stream, at the step it formed.
	for name in memory_streams:
		for rec in (memory_streams[name] as Array):
			if String((rec as Dictionary).get("kind", "")) != "reflection":
				continue
			var step := int((rec as Dictionary).get("created_turn", -1))
			if step < 0 or step > last:
				continue
			markers.append({"step": step, "kind": "reflection", "agent": String(name),
				"label": "%s reflects: %s" % [name, _trim(String((rec as Dictionary).get("text", "")))]})

	# Chat onsets + arrivals need frame-to-frame comparison per agent.
	for name in names:
		var was_chatting := false
		var was_walking := false
		for i in frames.size():
			var agent: Dictionary = (frames[i] as Dictionary).get(name, {})
			var act := String(agent.get("act", ""))
			var chat: Variant = agent.get("chat")
			var chatting := chat is Array and not (chat as Array).is_empty()
			if chatting and not was_chatting:
				markers.append({"step": i, "kind": "chat", "agent": String(name),
					"label": "%s starts a conversation" % name})
			var walking := act.begins_with(WALKING_PREFIX)
			if was_walking and not walking:
				var building := building_of(act)
				var where := " at %s" % building if building != "" else ""
				markers.append({"step": i, "kind": "arrival", "agent": String(name),
					"label": "%s arrives%s" % [name, where]})
			was_chatting = chatting
			was_walking = walking

	markers.sort_custom(func(a: Dictionary, b: Dictionary) -> bool:
		return int(a["step"]) < int(b["step"]))
	return markers


static func building_of(act: String) -> String:
	# The building an agent is in, from its `act` string. `act` is
	# "<activity> @ UPenn:<Building>:<area>"; we want the middle "<Building>"
	# segment. Returns "" if the address is missing or malformed. (Moved from
	# viewer.gd so marker labels and the viewer share one definition.)
	var halves := act.split(" @ ")
	if halves.size() < 2:
		return ""
	var addr := halves[1].split(":")
	return addr[1] if addr.size() > 1 else ""


static func _trim(text: String) -> String:
	# Keep tooltip lines readable: first 57 chars + ellipsis.
	return text if text.length() <= 58 else text.substr(0, 57) + "…"
```

**GDScript gotcha:** inside `static func`, the ternary is `value_a if cond else value_b` (as used above for `where`); check it parses — if the parser complains about the inline `%` + ternary combination, split it into an explicit `if building != "":` block.

- [ ] **Step 4: Run the test to verify it passes**

```bash
"$GODOT" --headless --path godot-generative-agents/godot --script res://tests/test_replay_markers.gd; echo "exit=$?"
```

Expected: every `ok:` line, `test_replay_markers: all checks passed`, `exit=0`.

- [ ] **Step 5: Wire the unit test into the smoke script**

In `godot-generative-agents/run_smoke_test.sh`, immediately before the final `exec` line, add:

```bash
# Headless unit tests (pure-GDScript helpers) run before the scene smoke; set -e
# makes a red unit test fail the whole script.
"$GODOT" --headless --path "$PROJECT_DIR" --script res://tests/test_replay_markers.gd
```

Also update the script's top comment ("load every content scene…") to mention it now also runs the headless GDScript unit tests.

- [ ] **Step 6: Run the full smoke script**

Run: `./godot-generative-agents/run_smoke_test.sh`
Expected: unit-test `ok:` lines, then the existing per-scene smoke output, exit 0.

- [ ] **Step 7: Commit**

```bash
git add godot-generative-agents/godot/scripts/replay_markers.gd \
  godot-generative-agents/godot/tests/test_replay_markers.gd \
  godot-generative-agents/run_smoke_test.sh
git commit -m "feat(viewer): marker collection helper for the timeline (#249)

Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>"
```

---

### Task 2: The marker strip control

**Files:**
- Create: `godot-generative-agents/godot/scripts/timeline_markers.gd`

**Interfaces:**
- Consumes: marker Dictionaries `{step, kind, agent, label}` from Task 1 (shape only — no import).
- Produces (Task 3 relies on these exact names):
  - `func set_markers(markers: Array, total: int) -> void`
  - `func set_filter(agent: String) -> void` (`""` = show all)
  - `signal marker_clicked(step: int)`

- [ ] **Step 1: Write the control**

Create `godot-generative-agents/godot/scripts/timeline_markers.gd`:

```gdscript
extends Control
## The event-marker strip above the timeline scrubber (issue #249): one thin
## colored tick per "interesting moment" (game event / chat onset / reflection /
## arrival), aligned to the scrubber's 0..total frame axis. Clicking seeks (the
## panel routes marker_clicked into its seek_requested); hovering names the
## nearest moments via the dynamic tooltip. Pure UI: agent_panel.gd feeds it via
## set_markers()/set_filter() and it knows nothing about the sim.

## The user clicked the strip: seek to `step` (nearest marker within SNAP_PX,
## else the step under the cursor).
signal marker_clicked(step: int)

# Tick colors by marker kind. Red matches the sidebar's LIVE-badge red; blue and
# green are the Cute Fantasy pack's own (the graph glyph's node blue, the gallery
# glyph's hill green) so the strip doesn't look foreign on the parchment theme.
const KIND_COLORS := {
	"event": Color(0.82, 0.20, 0.15),
	"chat": Color("0099db"),
	"reflection": Color("7b4fbe"),
	"arrival": Color("3e8948"),
}
const STRIP_HEIGHT := 10       # px; thin, sits directly above the HSlider
const TICK_HALF_WIDTH := 1     # ticks are 2px wide
const SNAP_PX := 4.0           # click/hover snap radius to the nearest marker

var _markers: Array = []       # all collected markers (replay_markers.gd shape)
var _visible_markers: Array = []  # after the agent filter
var _total := 0                # last frame index (the scrubber's max_value)
var _filter := ""              # "" = all agents; else only this agent's markers


func _ready() -> void:
	custom_minimum_size = Vector2(0, STRIP_HEIGHT)
	size_flags_horizontal = Control.SIZE_EXPAND_FILL
	mouse_default_cursor_shape = Control.CURSOR_POINTING_HAND


func set_markers(markers: Array, total: int) -> void:
	_markers = markers
	_total = total
	_apply_filter()


func set_filter(agent: String) -> void:
	if agent == _filter:
		return
	_filter = agent
	_apply_filter()


func _apply_filter() -> void:
	if _filter == "":
		_visible_markers = _markers
	else:
		_visible_markers = _markers.filter(func(m: Dictionary) -> bool:
			return String(m["agent"]) == _filter)
	queue_redraw()


func _draw() -> void:
	if _total <= 0:
		return
	for m in _visible_markers:
		var x := _step_to_x(int(m["step"]))
		draw_rect(Rect2(x - TICK_HALF_WIDTH, 0, TICK_HALF_WIDTH * 2, size.y),
			KIND_COLORS.get(String(m["kind"]), Color.WHITE))


func _gui_input(event: InputEvent) -> void:
	if not (event is InputEventMouseButton and event.pressed
			and (event as InputEventMouseButton).button_index == MOUSE_BUTTON_LEFT):
		return
	if _total <= 0:
		return
	var x := (event as InputEventMouseButton).position.x
	var nearest := _nearest_markers(x, 1)
	var step := int(nearest[0]["step"]) if not nearest.is_empty() \
		else clampi(roundi(x / size.x * _total), 0, _total)
	marker_clicked.emit(step)
	accept_event()


func _get_tooltip(at_position: Vector2) -> String:
	# Dynamic tooltip: the labels of up to 3 markers within snap range.
	var lines := PackedStringArray()
	for m in _nearest_markers(at_position.x, 3):
		lines.append("step %d — %s" % [int(m["step"]), String(m["label"])])
	return "\n".join(lines)


func _step_to_x(step: int) -> float:
	return step / float(_total) * size.x


func _nearest_markers(x: float, count: int) -> Array:
	# The visible markers within SNAP_PX of x, nearest first, at most `count`.
	var near := _visible_markers.filter(func(m: Dictionary) -> bool:
		return absf(_step_to_x(int(m["step"])) - x) <= SNAP_PX)
	near.sort_custom(func(a: Dictionary, b: Dictionary) -> bool:
		return absf(_step_to_x(int(a["step"])) - x) < absf(_step_to_x(int(b["step"])) - x))
	return near.slice(0, count)
```

- [ ] **Step 2: Syntax-check headlessly**

```bash
"$GODOT" --headless --path godot-generative-agents/godot --check-only \
  --script res://scripts/timeline_markers.gd; echo "exit=$?"
```

Expected: exit 0, no parse errors. (If `--check-only` is rejected in this Godot build, run the Task 1 unit test instead — it re-imports the project and surfaces parse errors in any script.)

- [ ] **Step 3: Commit**

```bash
git add godot-generative-agents/godot/scripts/timeline_markers.gd
git commit -m "feat(viewer): timeline marker strip control (#249)

Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>"
```

---

### Task 3: Panel wiring (strip above the scrubber, tracking filter, live hide)

**Files:**
- Modify: `godot-generative-agents/godot/scripts/agent_panel.gd` (build the strip in `_ready` at the scrubber, ~line 315; `set_live`, ~line 526; `_refresh`, ~line 647; new public setter)

**Interfaces:**
- Consumes: `timeline_markers.gd` from Task 2 (`set_markers`, `set_filter`, `marker_clicked`).
- Produces (Task 4 relies on this exact name): `func set_timeline_markers(markers: Array, total: int) -> void` on the panel.

- [ ] **Step 1: Build the strip and route its clicks into the existing seek signal**

In `agent_panel.gd`, add a preload const near the top (by the other consts, after `MISC_GLYPHS`):

```gdscript
# The event-marker strip that sits directly above the timeline (issue #249).
const TimelineMarkers := preload("res://scripts/timeline_markers.gd")
```

Add a member alongside `var _scrubber: HSlider` (~line 195):

```gdscript
var _markers_strip: Control            # event ticks above the timeline (#249)
```

In `_ready()`, immediately BEFORE the `_scrubber = HSlider.new()` block (~line 315), insert:

```gdscript
	# Event markers sit directly above the timeline they annotate (issue #249).
	# Clicks re-emit as ordinary seeks, so the viewer needs no new plumbing.
	_markers_strip = TimelineMarkers.new()
	_markers_strip.marker_clicked.connect(
		func(step: int) -> void: seek_requested.emit(step))
	col.add_child(_markers_strip)
```

(The strip is added to `col` right before the scrubber is, so it lands directly above it in the column.)

- [ ] **Step 2: Public setter, tracking filter, live hide**

Next to `set_progress` (~line 588) add:

```gdscript
func set_timeline_markers(markers: Array, total: int) -> void:
	# The replay's "interesting moments" (issue #249), collected once at load by
	# viewer.gd via replay_markers.gd. `total` is the last frame index, matching
	# the scrubber's max, so ticks align with the grabber's travel.
	_markers_strip.set_markers(markers, total)
```

In `set_live` (~line 531), extend the scrubber line:

```gdscript
	_scrubber.visible = not live
	_markers_strip.visible = not live
	_speed_row.visible = not live
```

In `_refresh()` (~line 647), add as the FIRST line of the function body (before the `for n in _rows:` loop):

```gdscript
	# Tracking narrows the marker strip to that agent's storyline (issue #249);
	# _refresh() is already the single place every tracking change funnels into.
	_markers_strip.set_filter(_active)
```

- [ ] **Step 3: Run the smoke script (panel builds with the strip, no data yet)**

Run: `./godot-generative-agents/run_smoke_test.sh`
Expected: exit 0 — unit tests pass, every scene loads (the strip exists, empty, invisible-when-live; no visual change without markers).

- [ ] **Step 4: Commit**

```bash
git add godot-generative-agents/godot/scripts/agent_panel.gd
git commit -m "feat(viewer): mount the marker strip above the scrubber (#249)

Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>"
```

---

### Task 4: Viewer wiring (collect at load; single building_of definition)

**Files:**
- Modify: `godot-generative-agents/godot/scripts/viewer.gd` (`_load_replay_from_text` ~line 458; `_building_of` ~line 1142; a preload const near the top)

**Interfaces:**
- Consumes: `ReplayMarkers.collect(...)` / `ReplayMarkers.building_of(...)` (Task 1); `_panel.set_timeline_markers(markers, total)` (Task 3).
- Produces: nothing new (end of the chain).

- [ ] **Step 1: Preload the helper**

Near viewer.gd's other preload consts at the top of the file, add:

```gdscript
# Marker collection for the timeline strip (issue #249) — also the single home
# of the act-address building parser (_building_of delegates to it).
const ReplayMarkers := preload("res://scripts/replay_markers.gd")
```

- [ ] **Step 2: Collect markers at replay load**

In `_load_replay_from_text`, right after the `_memory_streams = data.get("memory_streams", {})` line (~line 469), add:

```gdscript
	# The timeline's "interesting moments" (issue #249): game events (#476 —
	# this is the baked events key's first consumer), chat onsets, reflections,
	# arrivals. One scan at load; live mode never gets here (no scrubber).
	_panel.set_timeline_markers(
		ReplayMarkers.collect(_frames, _names, _memory_streams, data.get("events", [])),
		maxi(_frames.size() - 1, 0))
```

- [ ] **Step 3: Make `_building_of` a delegate**

Replace the body of `func _building_of(act: String) -> String:` (~line 1142) so the parsing logic lives in exactly one place:

```gdscript
func _building_of(act: String) -> String:
	# The building an agent is in, from its `act` string. The parsing moved to
	# replay_markers.gd (issue #249) so marker labels and the viewer can't drift.
	return ReplayMarkers.building_of(act)
```

- [ ] **Step 4: Full smoke + a data-driven sanity print**

Run: `./godot-generative-agents/run_smoke_test.sh`
Expected: exit 0.

Then confirm markers actually flow with the bundled replay (bake one if missing):

```bash
LLM_PROVIDER=mock uv run python godot-generative-agents/backend/penn/generate_penn_replay.py --steps 400
```

Temporarily (do NOT commit) add after the `set_timeline_markers` call in viewer.gd:
`print("markers: ", ReplayMarkers.collect(_frames, _names, _memory_streams, data.get("events", [])).size())`
— then run the replay scene headlessly for a few seconds and check the count is > 0:

```bash
timeout 15 "$GODOT" --headless --path godot-generative-agents/godot res://scenes/penn_replay.tscn 2>&1 | grep "markers:" || true
```

Expected: a `markers: N` line with N > 0 (the fresh 400-step bake has arrivals and chat at minimum; `events` appear if the bake includes game events). Remove the print afterwards. (If the replay scene file has a different name, find it with `ls godot-generative-agents/godot/scenes/`.)

- [ ] **Step 5: Commit**

```bash
git add godot-generative-agents/godot/scripts/viewer.gd
git commit -m "feat(viewer): collect + display timeline markers at replay load (#249)

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

Expected: smoke exit 0; backend suite green (nothing Python changed — this catches accidents); black clean.

- [ ] **Step 2: Manual visual pass (ask the user)**

Launch `./godot-generative-agents/run.sh`, play the bundled replay, and confirm the spec's manual checklist: ticks visible above the scrubber; four colors; click seeks; tracking filters to one agent; live mode hides the strip. The user does the eyeballing — report the checklist and wait for their confirmation before merge (not before PR).

- [ ] **Step 3: Push + PR**

```bash
git -c credential.helper='!gh auth git-credential' push https://github.com/ccb/agent-sandbox.git feat/timeline-markers-249
gh pr create --repo ccb/agent-sandbox --base godot-ga-main --head feat/timeline-markers-249 \
  --title "feat(viewer): event markers on the timeline scrubber (#249)" \
  --body-file <(cat <<'EOF'
## What

Colored, clickable tick marks above the replay scrubber for the moments worth
jumping to — game events (red), conversation onsets (blue), reflections
(purple), arrivals (green) — per the spec in
`godot-generative-agents/docs/specs/2026-07-10-timeline-markers.md`.

## How

- `scripts/replay_markers.gd` (new): pure static collection over the loaded
  replay — including the first consumer of the baked `events` key #476 added.
  Arrivals key on the `"walking to "` act prefix disappearing (during travel
  the act address is already the destination's, so an address change marks
  departure, not arrival).
- `scripts/timeline_markers.gd` (new): a 10px custom-draw strip above the
  `HSlider`; click = seek (routed through the panel's existing
  `seek_requested`), hover = tooltip, tracking an agent filters to their
  markers, live mode hides it with the scrubber.
- `agent_panel.gd` / `viewer.gd`: wiring only; `_building_of` now delegates to
  the helper (one definition).
- New: headless GDScript unit tests (`godot/tests/test_replay_markers.gd`),
  run by `run_smoke_test.sh` before the scene smoke.

## Verification

Headless unit tests green; smoke green; backend pytest + black untouched and
green; manual visual pass on a fresh 400-step mock bake.

Closes #249.

🤖 Generated with [Claude Code](https://claude.com/claude-code)
EOF
)
```

Expected: PR URL printed; then `gh pr checks <n>` all green.

---

## Self-Review

- **Spec coverage:** four marker kinds with exact rules (Task 1); strip above the slider, click-to-seek via `seek_requested`, hover tooltips, tracking filter through `_refresh`, live-mode hide (Tasks 2–3); `events`-key first consumer + `_building_of` single definition (Task 4); defensive rules (out-of-range skip, missing keys, malformed act) tested in Task 1. ✓
- **Placeholder scan:** no TBDs, no "add error handling" hand-waves; every code step shows complete code. ✓
- **Type consistency:** `collect(frames, names, memory_streams, events) -> Array` and marker shape `{step, kind, agent, label}` are identical in Tasks 1/2/4; `set_markers/set_filter/marker_clicked` names match between Tasks 2/3; `set_timeline_markers(markers, total)` matches between Tasks 3/4. ✓
