extends Node
## Game clock (autoload singleton `Clock`). Tracks game day / minute-of-day / phase
## and advances in real time. Drives `WorldState.time_phase`, the day-night tint and
## (via `phase_changed`) NPC schedules and the world manager.
##
## Canonical 6-phase day (GDD §14 / gap-analysis M1) with the documented boundaries.

signal phase_changed(phase: String, day: int)
signal day_rolled(day: int)
signal minute_ticked(minute_of_day: int, day: int)
signal beat_ticked(beat_index: int, day: int)

const DAY_MINUTES: int = 1440

## [boundary_minute, phase] sorted ascending. A minute maps to the last phase whose
## boundary it is >=. Late-night wraps both ends of the day.
const PHASE_BOUNDS: Array = [
	[0, "late-night"],
	[300, "early-morning"],   # 05:00
	[480, "morning"],         # 08:00
	[720, "afternoon"],       # 12:00
	[1020, "dusk"],           # 17:00
	[1140, "night"],          # 19:00
	[1380, "late-night"],     # 23:00
]

var day: int = 1
var minute_of_day: int = 480   # 08:00
var phase: String = "morning"
var real_seconds_per_game_minute: float = 1.0
var paused: bool = false
var minutes_per_beat: int = 15
var beat_index: int = 0
var _beat_accum_minutes: int = 0

var _accum: float = 0.0

func _ready() -> void:
	phase = phase_for_minute(minute_of_day)
	WorldState.time_phase = _display_phase()

func _process(delta: float) -> void:
	if paused or real_seconds_per_game_minute <= 0.0:
		return
	_accum += delta
	while _accum >= real_seconds_per_game_minute:
		_accum -= real_seconds_per_game_minute
		_advance_one_minute()

func _advance_one_minute() -> void:
	var prev_phase := phase
	minute_of_day += 1
	if minute_of_day >= DAY_MINUTES:
		minute_of_day = 0
		day += 1
		day_rolled.emit(day)
	phase = phase_for_minute(minute_of_day)
	minute_ticked.emit(minute_of_day, day)
	if phase != prev_phase:
		WorldState.time_phase = _display_phase()
		phase_changed.emit(phase, day)
	_beat_accum_minutes += 1
	if _beat_accum_minutes >= minutes_per_beat:
		_beat_accum_minutes = 0
		beat_index += 1
		beat_ticked.emit(beat_index, day)

static func phase_for_minute(minute: int) -> String:
	var result: String = "late-night"
	for entry in PHASE_BOUNDS:
		if minute >= int(entry[0]):
			result = String(entry[1])
		else:
			break
	return result

## Advance the clock by whole game minutes immediately (dev console / scripted beats).
func advance_minutes(n: int) -> void:
	for _i in range(maxi(0, n)):
		_advance_one_minute()

func set_time(new_day: int, new_minute: int) -> void:
	day = maxi(1, new_day)
	minute_of_day = clampi(new_minute, 0, DAY_MINUTES - 1)
	var prev := phase
	phase = phase_for_minute(minute_of_day)
	WorldState.time_phase = _display_phase()
	if phase != prev:
		phase_changed.emit(phase, day)

func hhmm() -> String:
	var h := minute_of_day / 60
	var m := minute_of_day % 60
	return "%02d:%02d" % [h, m]

func _display_phase() -> String:
	return "%s - %s" % [phase.capitalize(), hhmm()]

func to_dict() -> Dictionary:
	return {
		"day": day,
		"minute_of_day": minute_of_day,
		"beat_index": beat_index,
		"minutes_per_beat": minutes_per_beat,
		"beat_accum_minutes": _beat_accum_minutes,
	}

func from_dict(d: Dictionary) -> void:
	set_time(int(d.get("day", 1)), int(d.get("minute_of_day", 480)))
	beat_index = int(d.get("beat_index", 0))
	minutes_per_beat = int(d.get("minutes_per_beat", 15))
	_beat_accum_minutes = int(d.get("beat_accum_minutes", 0))
