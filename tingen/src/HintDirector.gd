extends Node
## HintDirector (autoload singleton `HintDirector`) — M35 the REUSABLE once-only contextual-hint
## framework. Two playtests found systems "reachable but undiscoverable": onboarding was only progressive
## meters + the [H] legend, so a fresh player never learned the verbs. This generalizes M32's counter-rite
## discoverability hint (its own private per-run latch) into ONE small framework other systems route
## through — no second parallel hint system.
##
## Contract: given a hint KEY, `fire(key)` surfaces its diegetic copy EXACTLY ONCE and never again.
##   * COPY is DATA: data/hints.json for the onboarding beats, or a caller-supplied `text_override`
##     (the counter-rite passes its authored rituals.json line). The engine holds no hint literal.
##   * SURFACE: WorldState.thought_requested — the HUD's existing internal-thought channel (reused, not a
##     new toast) — plus a `hint_shown` EventBus fact for any later observer.
##   * DEDUP is per-KEY. `persist=true` (the once-EVER default) writes the key to user://hints_seen.json so
##     it never repeats across runs OR restarts (the onboarding verbs — you learn them once). `persist=false`
##     is once-per-RUN and re-armed by `rearm(key)` (the counter-rite's discovery beat, scrubbed each run).
##
## LIVE-ONLY auto-wiring / determinism: the connection to the world event log (so a REAL player fire /
## dash / an enemy telegraph fires a hint) is gated behind the headless check — under --headless (every
## deterministic harness: combat_sim, run_combat_vectors, full_run) this node NEVER auto-fires, emits
## nothing, and the pinned sims stay byte-identical. Tests drive `_on_event()` / `fire()` directly (the
## CombatFeedback pattern) and assert the LOGIC — the once-only dedup, the trigger mapping — never pixels.
## Engine-neutral: keys + copy are data; no NPC-identity branch.

const HINTS_PATH: String = "res://data/hints.json"
const PERSIST_PATH: String = "user://hints_seen.json"

## key -> {text, ...} loaded from data/hints.json (the onboarding manifest).
var _hints: Dictionary = {}
## key -> true : every latched key this session (run-scoped + once-ever).
var _fired: Dictionary = {}
## key -> true : the once-EVER subset mirrored to disk (survives restart).
var _persisted: Dictionary = {}

func _ready() -> void:
	_load_hints()
	reload()   # pull the persisted once-ever keys off disk into the live latch
	# LIVE-ONLY: connect to the world event log so real player/enemy actions surface first-time hints.
	# Headless never auto-fires (byte-identical pinned sims); the harness drives _on_event() directly.
	if _is_live():
		var eb := _al("EventBus")
		if eb != null and not eb.event_logged.is_connected(_on_event):
			eb.event_logged.connect(_on_event)

# --- data ---------------------------------------------------------------------------------------
func _load_hints() -> void:
	if not FileAccess.file_exists(HINTS_PATH):
		return
	var parsed: Variant = JSON.parse_string(FileAccess.get_file_as_string(HINTS_PATH))
	if parsed is Dictionary:
		var d: Dictionary = parsed
		_hints = (d.get("hints", {}) as Dictionary).duplicate(true) if d.has("hints") else d.duplicate(true)

## The authored copy for a key ("" when the key authors none).
func hint_text(key: String) -> String:
	var e: Variant = _hints.get(key, {})
	return String((e as Dictionary).get("text", "")) if e is Dictionary else ""

# --- the core once-only verb --------------------------------------------------------------------
## Surface a hint by KEY exactly once. Returns true IFF it surfaced on THIS call. A no-op (returns false,
## no latch) when the key was already fired, or when there is nothing authored to say (no data, no override).
func fire(key: String, text_override: String = "", persist: bool = true) -> bool:
	if key == "" or _fired.has(key):
		return false
	var text := text_override if text_override != "" else hint_text(key)
	if text == "":
		return false   # nothing to say — do NOT latch, so it can fire once copy exists
	_fired[key] = true
	if persist:
		_persisted[key] = true
		_save()
	var ws := _al("WorldState")
	if ws != null:
		ws.emit_signal("thought_requested", text)
	var eb := _al("EventBus")
	if eb != null:
		eb.emit_event("hint_shown", {"key": key})
	return true

## Has this key already surfaced (this session, or a prior run for a persisted key)?
func has_fired(key: String) -> bool:
	return _fired.has(key)

# --- re-arm / reset seams -----------------------------------------------------------------------
## Re-arm a SINGLE key so it can fire again — the counter-rite's once-per-run discovery beat routes here
## from CounterRite.reset() (RunManager's per-run reset manifest). Clears the persisted mirror too, so
## even a once-ever key can be deliberately re-armed.
func rearm(key: String) -> void:
	var changed := false
	if _fired.has(key):
		_fired.erase(key)
	if _persisted.has(key):
		_persisted.erase(key)
		changed = true
	if changed:
		_save()

## Scrub every NON-persisted (run-scoped) latch — a fresh run's defensive reset (the once-ever onboarding
## keys survive; the per-run keys re-arm). Safe to call from RunManager's reset manifest.
func reset_run() -> void:
	for k in _fired.keys():
		if not _persisted.has(k):
			_fired.erase(k)

## Test seam: clear EVERY latch and wipe the persisted store, for a deterministic slate.
func clear_for_test() -> void:
	_fired.clear()
	_persisted.clear()
	var dir := DirAccess.open("user://")
	if dir != null and dir.file_exists("hints_seen.json"):
		dir.remove("hints_seen.json")

# --- persistence (once-ever keys survive a restart) ---------------------------------------------
## Reload the persisted once-ever keys off disk into the live latch. Called on _ready and by tests; also
## the seam that lets a fresh HintDirector instance prove a key survived a restart.
func reload() -> void:
	_persisted.clear()
	if not FileAccess.file_exists(PERSIST_PATH):
		return
	var parsed: Variant = JSON.parse_string(FileAccess.get_file_as_string(PERSIST_PATH))
	if parsed is Dictionary and (parsed as Dictionary).has("seen"):
		for k in ((parsed as Dictionary)["seen"] as Array):
			_persisted[String(k)] = true
			_fired[String(k)] = true

func _save() -> void:
	var f := FileAccess.open(PERSIST_PATH, FileAccess.WRITE)
	if f != null:
		f.store_string(JSON.stringify({"seen": _persisted.keys()}))
		f.close()

# --- the live event seam: real player/enemy actions -> first-time hints --------------------------
## Map a world event to its first-time hint. The SAME handler live play connects to event_logged; the
## harness calls it directly. `ability_cast_started` IS both the player's cast and the enemy's telegraph:
##   * caster == player, ability == dash  -> first_dash
##   * caster == player, any other cast   -> first_fire (the primary strike)
##   * caster != player (an enemy winds up)-> first_telegraph
func _on_event(ev: Dictionary) -> void:
	var d: Dictionary = ev.get("data", {}) if ev.get("data") is Dictionary else {}
	match String(ev.get("type", "")):
		"ability_cast_started":
			var caster := String(d.get("caster", ""))
			var ability := String(d.get("ability", ""))
			if caster == "player":
				if ability == "dash":
					fire("first_dash")
				else:
					fire("first_fire")
			elif caster != "":
				fire("first_telegraph")

## The player's FIRST analog movement — Player.gd's live seam calls this once (there is no move event).
func notify_first_move() -> void:
	fire("first_move")

# --- helpers ------------------------------------------------------------------------------------
## True only with a real display (live play); false under --headless — where we NEVER auto-wire, keeping
## every deterministic harness byte-identical (the CombatFeedback._is_live pattern).
func _is_live() -> bool:
	return DisplayServer.get_name() != "headless"

## Autoload lookup via /root (class_name-safe under the headless -s harness), tolerant of absence.
func _al(autoload_name: String) -> Node:
	var ml := Engine.get_main_loop()
	if ml == null or not (ml is SceneTree):
		return null
	return (ml as SceneTree).root.get_node_or_null(autoload_name)
