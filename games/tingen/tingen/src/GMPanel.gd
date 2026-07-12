extends CanvasLayer
## GM digest panel (autoload `GMPanel`, toggle: G) — the first artifact of the future GM/orchestrator.
##
## Every DIGEST_INTERVAL_SEC wall-clock seconds a Timer fires `_digest_tick()`: the EventBus events
## logged since the last consumed seq are folded by GMDigest.build_digest into a deterministic,
## human-readable entry (timestamp header + story lines + aggregated noise counts). Digests
## accumulate whether or not the panel is open (last MAX_DIGESTS kept).
##
## HYBRID narration: the deterministic digest ALWAYS renders immediately. If the active
## SidecarClient's `narrate()` returns a summary (only HttpSidecar does, when the live LLM sidecar
## is connected; MockSidecar can script one for tests), that paragraph is appended to its entry when
## it lands. The call runs on a background Thread (HttpSidecar.narrate blocks for the HTTP
## round-trip) and the reply comes back through a mutex-guarded buffer + call_deferred — the same
## worker pattern as HttpSidecar's beat transport, so a slow LLM never stalls a frame. Offline
## clients return {} instantly and the entry simply stays digest-only: absence of narration is a
## normal outcome, never an error.
##
## Built in code (no .tscn) so it ships with the autoload, like ModelPanel. All autoload access goes
## through get_node_or_null("/root/X") so the panel degrades quietly under partial test harnesses.

const DIGEST_INTERVAL_SEC: float = 30.0
const MAX_DIGESTS: int = 20

var _root: PanelContainer = null
var _list: VBoxContainer = null
var _timer: Timer = null

# The digest log: [{id, stamp, lines: Array[String], narration: String}], oldest first.
var _entries: Array = []
var _next_id: int = 1
var _last_seq: int = 0   # EventBus seq cursor — each tick consumes only events past it

# Narration transport (one worker at a time, like HttpSidecar's beat thread).
var _thread: Thread = null
var _mutex: Mutex = Mutex.new()
var _busy: bool = false
var _pending: Array = []   # [{id, summary}] filled by the worker, drained on the main thread

func _ready() -> void:
	process_mode = Node.PROCESS_MODE_ALWAYS   # the 30s cadence is WALL-CLOCK, pause or not
	layer = 85
	_root = PanelContainer.new()
	# Right-side column, anchored to the viewport (Controls under a CanvasLayer anchor to it).
	_root.anchor_left = 0.62
	_root.anchor_top = 0.05
	_root.anchor_right = 0.98
	_root.anchor_bottom = 0.85
	add_child(_root)
	var margin := MarginContainer.new()
	for side in ["left", "right", "top", "bottom"]:
		margin.add_theme_constant_override("margin_" + side, 12)
	_root.add_child(margin)
	var body := VBoxContainer.new()
	body.add_theme_constant_override("separation", 8)
	margin.add_child(body)
	var title := Label.new()
	title.text = "GM log — a digest every %ds (G to toggle)" % int(DIGEST_INTERVAL_SEC)
	body.add_child(title)
	var scroll := ScrollContainer.new()
	scroll.size_flags_vertical = Control.SIZE_EXPAND_FILL
	body.add_child(scroll)
	_list = VBoxContainer.new()
	_list.size_flags_horizontal = Control.SIZE_EXPAND_FILL
	_list.add_theme_constant_override("separation", 10)
	scroll.add_child(_list)
	_root.visible = false
	_timer = Timer.new()
	_timer.wait_time = DIGEST_INTERVAL_SEC
	_timer.autostart = true
	_timer.timeout.connect(_digest_tick)
	add_child(_timer)

func _exit_tree() -> void:
	if _thread != null and _thread.is_started():
		_thread.wait_to_finish()
	_thread = null

## B4 (M21): stop the wall-clock digest timer while the game is PAUSED (pause menu up / Clock paused)
## and resume it on unpause — so a paused game issues no auto digest ticks and, with the narration gate,
## zero LLM calls. The panel keeps PROCESS_MODE_ALWAYS so this runs during pause. A manual _digest_tick()
## (tests) is unaffected.
func _process(_delta: float) -> void:
	if _timer == null:
		return
	var paused := _is_paused()
	if paused and not _timer.is_stopped():
		_timer.stop()
	elif not paused and _timer.is_stopped():
		_timer.start()

## True while the game is paused, by either the SceneTree pause (the pause menu, M10) or Clock.paused.
func _is_paused() -> bool:
	var tree := get_tree()
	if tree != null and tree.paused:
		return true
	var clk := _al("Clock")
	return clk != null and bool(clk.paused)

## B4: whether an LLM narration call may fire right now. NEVER while paused; otherwise only when the
## panel is OPEN (you are reading it) or the player opted into background narration (Settings.gm_narration).
func narration_gate_open() -> bool:
	if _is_paused():
		return false
	if is_open():
		return true
	var st := _al("Settings")
	return st != null and st.has_method("get_bool") and bool(st.get_bool("gm_narration"))

func _unhandled_input(event: InputEvent) -> void:
	if event.is_action_pressed("toggle_gm"):
		toggle()
		get_viewport().set_input_as_handled()
	elif is_open() and event.is_action_pressed("ui_cancel"):
		_root.visible = false
		get_viewport().set_input_as_handled()

func toggle() -> void:
	_root.visible = not _root.visible
	if _root.visible:
		_refresh()

func is_open() -> bool:
	return _root != null and _root.visible

## One digest period: fold every EventBus event past the seq cursor into an entry, then ask the
## active sidecar client for a narration of it (async; appended when/if it lands).
func _digest_tick() -> void:
	var eb := _al("EventBus")
	if eb == null:
		return
	var fresh: Array = []
	for e in eb.events():
		if int((e as Dictionary).get("seq", 0)) > _last_seq:
			fresh.append(e)
	if fresh.is_empty():
		return   # a quiet period logs nothing
	_last_seq = int((fresh.back() as Dictionary).get("seq", 0))   # consume the window
	var digest: Dictionary = GMDigest.build_digest(fresh)
	var lines: Array = digest.get("lines", [])
	if lines.is_empty():
		return   # only un-narrated event types this period — cursor advanced, no entry
	var entry: Dictionary = {"id": _next_id, "stamp": _stamp(), "lines": lines.duplicate(), "narration": ""}
	_next_id += 1
	_entries.append(entry)
	if _entries.size() > MAX_DIGESTS:
		_entries = _entries.slice(_entries.size() - MAX_DIGESTS)
	if is_open():
		_refresh()
	_request_narration(int(entry["id"]), lines)

## Wall clock + game clock, so the header reads in both frames of reference.
func _stamp() -> String:
	var wall := Time.get_time_string_from_system()
	var clk := _al("Clock")
	if clk == null:
		return wall
	return "%s · day %d %s · beat %d" % [wall, int(clk.day), String(clk.hhmm()), int(clk.beat_index)]

# --- LLM narration (async seam) -----------------------------------------------------------------
## Ask the active client to narrate this digest, on a worker thread. Whatever the client — the base
## no-op, Ambient/Mock ({} unless scripted), or HttpSidecar (blocking POST /narrate) — the worker
## just calls narrate() and publishes the reply; only a non-empty summary is ever appended.
func _request_narration(entry_id: int, lines: Array) -> void:
	# B4 (M21): the deterministic digest above ALWAYS renders; the LLM narration is gated. A PAUSED
	# game makes ZERO LLM calls, and an unopened panel only narrates if the player opted in — so an
	# idle background panel never bills. The offline/ambient path is unaffected (narrate returns {}).
	if not narration_gate_open():
		return
	# B4 finding #1: once the session budget ceiling is hit, narration degrades with the rest of LLM
	# spend — no /narrate POST fires, we just keep the deterministic digest. Belt-and-suspenders with
	# _client() (which already returns the ambient fallback over budget): this skips even spawning the
	# worker, so a live over-budget session with an open panel bills nothing every 30s.
	var sb := _al("SidecarBridge")
	if sb != null and sb.has_method("budget_exceeded") and bool(sb.budget_exceeded()):
		return
	var client: Object = _client()
	if client == null or not client.has_method("narrate"):
		return
	# The GM model is stamped HERE, on the main thread — the worker must never touch the scene
	# tree (ModelConfig is an autoload node; /root access off a thread is unsafe), so narrate()
	# consumes the pre-stamped value instead of looking it up itself.
	var request: Dictionary = {"events": lines.duplicate(), "world": _world_state()}
	var mc := _al("ModelConfig")
	if mc != null:
		request["model"] = mc.model_for("gm")
	_mutex.lock()
	var busy := _busy
	if not busy:
		_busy = true
	_mutex.unlock()
	if busy:
		return   # one narration in flight at a time; this entry just stays digest-only
	if _thread != null and _thread.is_started():
		_thread.wait_to_finish()
	_thread = Thread.new()
	_thread.start(_narrate_worker.bind(client, entry_id, request))

## The compact world context the narrator sees — mirrors Perception's pressures block so the GM
## and the agent brains describe the same world.
func _world_state() -> Dictionary:
	var out: Dictionary = {"beat": 0, "phase": "", "pressures": {}}
	var clk := _al("Clock")
	if clk != null:
		out["beat"] = int(clk.beat_index)
		out["phase"] = String(clk.phase)
	var ws := _al("WorldState")
	if ws != null:
		out["pressures"] = {
			"corruption": ws.corruption,
			"cult_readiness": ws.cult_readiness,
			"panic": ws.panic,
			"attention": ws.attention,
		}
	return out

## Worker thread: pure client call (HTTP + JSON at most) — touches no engine state; the reply goes
## back through the mutex-guarded buffer and a thread-safe call_deferred wakes the main thread.
func _narrate_worker(client: Object, entry_id: int, request: Dictionary) -> void:
	var out: Variant = client.narrate(request)
	var summary := ""
	# B4 finding #1: a live /narrate reply carries a "cost" key — capture it (and whether it was
	# present) so the MAIN thread can bill it to the budget guard. The worker never touches the scene
	# tree, so it only records the numbers; note_llm_spend runs in _drain_narrations.
	var cost := 0.0
	var billed := false
	if out is Dictionary:
		var od := out as Dictionary
		summary = String(od.get("summary", ""))
		if od.has("cost"):
			cost = float(od.get("cost", 0.0))
			billed = true
	_mutex.lock()
	_pending.append({"id": entry_id, "summary": summary, "cost": cost, "billed": billed})
	_busy = false
	_mutex.unlock()
	call_deferred("_drain_narrations")

## Main thread: append every landed narration to the entry it narrates (matched by id — the entry
## may have been pruned meanwhile, which is fine). An empty summary is the offline/declined case:
## the digest simply stays deterministic-only, no error surfaced.
func _drain_narrations() -> void:
	_mutex.lock()
	var batch: Array = _pending.duplicate(true)
	_pending.clear()
	_mutex.unlock()
	# B4 finding #1: bill every REALIZED /narrate call (billed==true) to the session budget guard here
	# on the main thread — even one that returned an empty summary still cost money. This makes GM
	# narration count toward the SAME ceiling as propose/converse, so it can trip the degrade latch.
	var sb := _al("SidecarBridge")
	if sb != null and sb.has_method("note_llm_spend"):
		for p in batch:
			if bool((p as Dictionary).get("billed", false)):
				sb.note_llm_spend(float((p as Dictionary).get("cost", 0.0)))
	var touched := false
	for p in batch:
		var summary := String((p as Dictionary).get("summary", ""))
		if summary == "":
			continue
		var id := int((p as Dictionary).get("id", 0))
		for e in _entries:
			if int((e as Dictionary).get("id", -1)) == id:
				(e as Dictionary)["narration"] = summary
				touched = true
				break
	if touched and is_open():
		_refresh()

# --- Rendering ------------------------------------------------------------------------------------
func _refresh() -> void:
	# free() synchronously (not queue_free), like DebugLogPanel: a deferred free would let a second
	# refresh in the same frame stack duplicates onto unreaped children.
	for c in _list.get_children():
		c.free()
	if _entries.is_empty():
		var empty := Label.new()
		empty.text = "No digests yet. The GM takes stock every %d seconds." % int(DIGEST_INTERVAL_SEC)
		empty.modulate = Color(0.6, 0.6, 0.65)
		_list.add_child(empty)
		return
	for i in range(_entries.size() - 1, -1, -1):   # newest first
		var e: Dictionary = _entries[i]
		var head := Label.new()
		head.text = "— %s —" % String(e.get("stamp", ""))
		head.modulate = Color(0.78, 0.72, 0.5)
		_list.add_child(head)
		for line in (e.get("lines", []) as Array):
			var l := Label.new()
			l.text = "• " + String(line)
			l.autowrap_mode = TextServer.AUTOWRAP_WORD_SMART
			_list.add_child(l)
		var narration := String(e.get("narration", ""))
		if narration != "":
			var n := Label.new()
			n.text = narration
			n.autowrap_mode = TextServer.AUTOWRAP_WORD_SMART
			n.modulate = Color(0.7, 0.88, 0.95)   # the LLM's voice, tinted like npc dialogue
			_list.add_child(n)

# --- Lookups ---------------------------------------------------------------------------------------
func _client() -> Object:
	var sb := _al("SidecarBridge")
	if sb == null:
		return null
	# B4 finding #1: route narration through the SAME budget guard as propose/converse instead of the
	# raw live client — over budget this hands back the ambient brain (whose narrate() returns {}), so
	# GM narration can never be the one LLM path that keeps billing after the ceiling is reached.
	if sb.has_method("_active_client"):
		return sb._active_client()
	return sb.client

func _al(autoload_name: String) -> Node:
	var tree := get_tree()
	return tree.root.get_node_or_null("/root/" + autoload_name) if tree != null else null

# --- Test/debug seams -------------------------------------------------------------------------------
func entry_count() -> int:
	return _entries.size()

## A deep copy of the i-th digest entry (oldest first): {id, stamp, lines, narration}.
func entry(i: int) -> Dictionary:
	if i < 0 or i >= _entries.size():
		return {}
	return (_entries[i] as Dictionary).duplicate(true)

func rendered_line_count() -> int:
	return _list.get_children().size()

## Join any in-flight narration worker and apply its reply NOW — makes the async seam deterministic
## for tests (and safe to call when nothing is in flight).
func flush_narration() -> void:
	if _thread != null and _thread.is_started():
		_thread.wait_to_finish()
	_thread = null
	_drain_narrations()

## Clear the log and rewind the seq cursor (tests; pairs with EventBus.clear()).
func reset() -> void:
	flush_narration()
	_mutex.lock()
	_pending.clear()
	_busy = false
	_mutex.unlock()
	_entries.clear()
	_next_id = 1
	_last_seq = 0
	if is_open():
		_refresh()
