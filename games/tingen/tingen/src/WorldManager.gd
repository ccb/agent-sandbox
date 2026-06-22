extends Node
## World Manager (autoload singleton `WorldManager`) — the hidden director (GDD §8).
##
## Owns the 6-stage story machine, runs the city pressure simulation on the GDD's
## 60-second "strategic refresh", crosses pressure thresholds, and resolves dynamic
## slots (which site/NPC fills each story role this playthrough) via a SEEDED RNG so
## save/load is deterministic.
##
## Pressures themselves live in WorldState; this node mutates them through
## WorldState.adjust so there is a single source of truth.

signal stage_advanced(from_stage: String, to_stage: String)
signal pressure_threshold_crossed(pressure_name: String, value: float)
signal refreshed(refresh_count: int)
signal slots_resolved(slots: Dictionary)

const STRATEGIC_REFRESH_SECONDS: float = 60.0
const OFFSCREEN_TICK_EVERY_REFRESHES: int = 1

## Sequential stage machine. `enter_when` conditions must ALL pass to advance.
const STAGES: Array = [
	{"id": "disturbance", "enter_when": []},
	{"id": "awakening", "enter_when": [
		{"type": "clue_count_gte", "value": 1},
	]},
	{"id": "investigation", "enter_when": [
		{"type": "clue_count_gte", "value": 3},
	]},
	{"id": "confrontation", "enter_when": [
		{"type": "pressure_gte", "target": "cult_readiness", "value": 50},
	]},
	{"id": "ritual_night", "enter_when": [
		{"type": "pressure_gte", "target": "cult_readiness", "value": 80},
	]},
	{"id": "resolution", "enter_when": [
		{"type": "pressure_gte", "target": "cult_readiness", "value": 100},
	]},
]

## How fast cult plans advance per refresh while sitting in each stage.
const STAGE_ACTIVITY: Dictionary = {
	"disturbance": 0.6,
	"awakening": 1.0,
	"investigation": 1.4,
	"confrontation": 2.2,
	"ritual_night": 3.5,
	"resolution": 0.0,
}

## Weighted candidate pools resolved at the listed time. Placeholder ids.
const SLOT_DEFS: Array = [
	{"id": "primary_ritual_site", "resolve_at": "world-start", "candidates": [
		{"value": "iron_cross_warehouse", "weight": 3.0},
		{"value": "st_selena_crypt", "weight": 2.0},
		{"value": "harbor_customs_house", "weight": 1.0},
	]},
	{"id": "decoy_courier", "resolve_at": "world-start", "candidates": [
		{"value": "lamplighter_orin", "weight": 2.0},
		{"value": "fishwife_dalia", "weight": 2.0},
		{"value": "clerk_voss", "weight": 1.0},
	]},
	{"id": "first_corrupted_civilian", "resolve_at": "stage-enter:awakening", "candidates": [
		{"value": "dockhand_pell", "weight": 2.0},
		{"value": "widow_carrow", "weight": 1.5},
		{"value": "boy_tomas", "weight": 1.0},
	]},
]

var current_stage_id: String = "disturbance"
var refresh_count: int = 0
var stage_entered_at: int = 0
var last_offscreen_tick: int = 0
var seed_value: int = 0
var slots: Dictionary = {}

var _rng := RandomNumberGenerator.new()
var _last_quarter: Dictionary = {}   # pressure name -> last crossed quarter (0..4)
var _timer: Timer

func _ready() -> void:
	if seed_value == 0:
		seed_value = randi()
	_start_run(false)
	_timer = Timer.new()
	_timer.wait_time = STRATEGIC_REFRESH_SECONDS
	_timer.autostart = true
	_timer.timeout.connect(refresh)
	add_child(_timer)

## (Re)initialise the run. When `keep_state` is false, resets stage/slots/pressures
## bookkeeping; the seed is preserved so slots are reproducible.
func _start_run(keep_state: bool) -> void:
	_rng.seed = seed_value
	if not keep_state:
		current_stage_id = STAGES[0]["id"]
		refresh_count = 0
		stage_entered_at = 0
		last_offscreen_tick = 0
		slots = {}
		_last_quarter.clear()
		for v in WorldState.PRESSURE_VARS:
			_last_quarter[String(v)] = int(WorldState.get_pressure(v) / 25.0)
	_resolve_slots("world-start")

func stage_index() -> int:
	for i in STAGES.size():
		if STAGES[i]["id"] == current_stage_id:
			return i
	return 0

## One strategic refresh: simulate pressures, fire thresholds, advance the stage,
## resolve offscreen progress. Also fired manually by the dev console.
func refresh() -> void:
	refresh_count += 1
	_simulate_pressures()
	_offscreen_tick()
	_check_stage_advance()
	refreshed.emit(refresh_count)

func _simulate_pressures() -> void:
	var coeff: float = STAGE_ACTIVITY.get(current_stage_id, 1.0)
	_adjust_tracked(&"panic", -1.5)
	_adjust_tracked(&"corruption", 0.5 + WorldState.cult_readiness * 0.02)
	_adjust_tracked(&"cult_readiness", coeff)
	_adjust_tracked(&"fatigue", 0.8)
	# Attention of the Beyond trails corruption.
	_adjust_tracked(&"attention", (WorldState.corruption - WorldState.attention) * 0.05)

func _offscreen_tick() -> void:
	if refresh_count - last_offscreen_tick < OFFSCREEN_TICK_EVERY_REFRESHES:
		return
	last_offscreen_tick = refresh_count
	# Stub deterministic offscreen progression: cult work continues unseen.
	_adjust_tracked(&"cult_readiness", STAGE_ACTIVITY.get(current_stage_id, 1.0) * 0.4)

## Adjust a pressure and emit a threshold-crossed signal when it moves into a new
## quarter (0-25-50-75-100), matching the extensibility-plan example.
func _adjust_tracked(var_name: StringName, delta: float) -> void:
	var before: float = WorldState.get_pressure(var_name)
	WorldState.adjust(var_name, delta)
	var after: float = WorldState.get_pressure(var_name)
	var key := String(var_name)
	var q_before: int = int(before / 25.0)
	var q_after: int = int(after / 25.0)
	if q_after != q_before:
		_last_quarter[key] = q_after
		pressure_threshold_crossed.emit(key, after)

func _check_stage_advance() -> void:
	var idx := stage_index()
	if idx + 1 >= STAGES.size():
		return
	var next: Dictionary = STAGES[idx + 1]
	if _conditions_met(next["enter_when"]):
		var from := current_stage_id
		current_stage_id = next["id"]
		stage_entered_at = refresh_count
		_resolve_slots("stage-enter:%s" % current_stage_id)
		stage_advanced.emit(from, current_stage_id)

func _conditions_met(conditions: Array) -> bool:
	for c in conditions:
		if not _condition_met(c):
			return false
	return true

func _condition_met(c: Dictionary) -> bool:
	match String(c.get("type", "")):
		"clue_count_gte":
			return ClueDB.collected_count() >= int(c.get("value", 0))
		"pressure_gte":
			return WorldState.get_pressure(StringName(c.get("target", ""))) >= float(c.get("value", 0))
		"stage_duration_gte":
			return (refresh_count - stage_entered_at) >= int(c.get("value", 0))
		_:
			return false

func _resolve_slots(when: String) -> void:
	var changed := false
	for def in SLOT_DEFS:
		if String(def["resolve_at"]) != when:
			continue
		if slots.has(def["id"]):
			continue
		slots[def["id"]] = _weighted_pick(def["candidates"])
		changed = true
	if changed:
		slots_resolved.emit(slots)

func _weighted_pick(candidates: Array) -> String:
	var total: float = 0.0
	for c in candidates:
		total += float(c["weight"])
	var roll: float = _rng.randf() * total
	for c in candidates:
		roll -= float(c["weight"])
		if roll <= 0.0:
			return String(c["value"])
	return String(candidates[-1]["value"])

## Force the next stage regardless of conditions (dev console).
func force_advance_stage() -> void:
	var idx := stage_index()
	if idx + 1 >= STAGES.size():
		return
	var from := current_stage_id
	current_stage_id = STAGES[idx + 1]["id"]
	stage_entered_at = refresh_count
	_resolve_slots("stage-enter:%s" % current_stage_id)
	stage_advanced.emit(from, current_stage_id)

func to_dict() -> Dictionary:
	return {
		"current_stage_id": current_stage_id,
		"refresh_count": refresh_count,
		"stage_entered_at": stage_entered_at,
		"last_offscreen_tick": last_offscreen_tick,
		"seed_value": seed_value,
		"slots": slots.duplicate(true),
		"last_quarter": _last_quarter.duplicate(true),
	}

func from_dict(d: Dictionary) -> void:
	seed_value = int(d.get("seed_value", seed_value))
	_rng.seed = seed_value
	current_stage_id = String(d.get("current_stage_id", "disturbance"))
	refresh_count = int(d.get("refresh_count", 0))
	stage_entered_at = int(d.get("stage_entered_at", 0))
	last_offscreen_tick = int(d.get("last_offscreen_tick", 0))
	slots = (d.get("slots", {}) as Dictionary).duplicate(true)
	_last_quarter = (d.get("last_quarter", {}) as Dictionary).duplicate(true)
