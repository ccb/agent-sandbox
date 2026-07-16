extends Node
## Player settings authority (autoload singleton `Settings`) — M10 polish.
##
## A tiny persisted preferences store, SEPARATE from the run save and the meta slot: it survives
## every run and every restart in its own user:// file. Everything here is COSMETIC / accessibility
## only — nothing on this node ever reaches the deterministic combat_sim (the shake/hit-flash toggles
## gate cosmetic feedback; the palette/text-scale re-skin the HUD). It NEVER alters combat resolution.
##
## Fields:
##   master_volume  (0..1)  drives the Master audio bus (audio is deferred; the bus wiring is ready).
##   screen_shake   (bool)  gates CombatFeedback.shake() — off makes the shake helper a no-op.
##   hit_flash      (bool)  gates CombatFeedback.flash() + the struck-enemy whiten — off = no-op.
##   hit_stop       (bool)  gates CombatFeedback.hitstop() — off makes the live-only time_scale dip a no-op.
##   text_scale     (float) multiplies HUD/dialogue font sizes (accessibility text size).
##   colorblind     (bool)  swaps the meter/telegraph palette to a colorblind-safe set.
##
## Consumers read the live value (get_bool/get_number) or the derived palette (meter_color /
## telegraph_color) and refresh on the `changed` signal, so a toggle takes effect immediately.

signal changed(key: String)

const SETTINGS_PATH: String = "user://settings.json"
const SETTINGS_VERSION: int = 1

## N1 (sprint safety): the ACTIVE settings slot — REDIRECTABLE so test harnesses never overwrite
## the real player's user://settings.json (every settings-toggle test used to write straight into
## it via set_value's save_to()). Live play never touches this default; harnesses redirect it into
## user://test_sandbox/<run>/ via src/TestSandbox.gd `activate()`, whose write guard also REFUSES
## out-of-sandbox writes while a harness is running.
var settings_path: String = SETTINGS_PATH
const _TSandbox := preload("res://src/TestSandbox.gd")

## Normal (default) palette — mirrors the M4/M5 HUD + telegraph colors the game shipped with.
const _PALETTE_NORMAL: Dictionary = {
	"doom": Color(0.85, 0.20, 0.20),      # red — the world clock
	"madness": Color(0.60, 0.25, 0.80),   # violet — losing control
	"notice": Color(0.90, 0.75, 0.20),    # amber — being seen
	"heat": Color(0.95, 0.45, 0.15),      # orange — the law closing in
	"telegraph": Color(0.95, 0.30, 0.25), # red-warning wind-up line
}
## Colorblind-safe palette — an Okabe-Ito-derived set (distinguishable under deuter/protanopia):
## blue / bluish-green / orange / yellow, with a vermillion telegraph reserved for the danger cue.
const _PALETTE_CB: Dictionary = {
	"doom": Color(0.00, 0.45, 0.70),      # blue
	"madness": Color(0.00, 0.62, 0.45),   # bluish-green
	"notice": Color(0.94, 0.89, 0.26),    # yellow
	"heat": Color(0.90, 0.62, 0.00),      # orange
	"telegraph": Color(0.84, 0.37, 0.00), # vermillion
}

var _values: Dictionary = {}
var _loaded: bool = false

func _ready() -> void:
	_load_or_default()
	# Apply the loaded audio setting once the bus exists (audio deferred; wiring ready).
	_apply_master_volume()

func _default() -> Dictionary:
	return {
		"version": SETTINGS_VERSION,
		"master_volume": 1.0,
		"screen_shake": true,
		"hit_flash": true,
		# M24: gates the LIVE-ONLY combat hit-stop (a brief Engine.time_scale dip on a player-landed
		# hit / a kill). Cosmetic + accessibility (some players dislike time-stutter) — never reaches
		# the deterministic combat_sim, which steps its own fixed dt and ignores time_scale entirely.
		"hit_stop": true,
		"text_scale": 1.0,
		"colorblind": false,
		# B4 (M21): when false, the GM panel only spends an LLM narration call while the panel is OPEN
		# (you are reading it). Set true to keep the GM narrating in the background. Either way, a PAUSED
		# game never narrates. Default off so an idle/closed panel bills nothing.
		"gm_narration": false,
	}

# --- Accessors --------------------------------------------------------------------------------
func get_bool(key: String) -> bool:
	_ensure_loaded()
	return bool(_values.get(key, _default().get(key, false)))

func get_number(key: String) -> float:
	_ensure_loaded()
	return float(_values.get(key, _default().get(key, 0.0)))

## Set a value, persist it, apply any live side-effect (audio bus), and announce the change.
func set_value(key: String, value: Variant) -> void:
	_ensure_loaded()
	_values[key] = value
	if key == "master_volume":
		_apply_master_volume()
	save_to()
	changed.emit(key)

func reset_defaults() -> void:
	_values = _default()
	_loaded = true
	_apply_master_volume()
	changed.emit("")

# --- Palette (colorblind toggle) --------------------------------------------------------------
## The active palette table (safe set when colorblind is on).
func _palette() -> Dictionary:
	return _PALETTE_CB if get_bool("colorblind") else _PALETTE_NORMAL

## The color a meter row / telegraph should draw with under the active palette.
func meter_color(meter: String) -> Color:
	return _palette().get(meter, Color.WHITE)

func telegraph_color() -> Color:
	return _palette().get("telegraph", Color(0.95, 0.30, 0.25))

# --- Text size --------------------------------------------------------------------------------
## Scale a Control's font size by the active text_scale, off a caller-supplied BASE size (so repeated
## applies never compound). Accepts any Control that honours a "font_size" theme override (Label,
## Button, etc.). Cosmetic accessibility only.
func apply_text_scale(control: Control, base_font_size: int) -> void:
	if control == null:
		return
	var scaled := int(round(float(base_font_size) * get_number("text_scale")))
	control.add_theme_font_size_override("font_size", maxi(1, scaled))

func text_scale() -> float:
	return get_number("text_scale")

# --- Audio bus (deferred audio; wiring ready) -------------------------------------------------
func _apply_master_volume() -> void:
	var bus := AudioServer.get_bus_index("Master")
	if bus < 0:
		return
	var v := clampf(get_number("master_volume"), 0.0, 1.0)
	if v <= 0.0:
		AudioServer.set_bus_mute(bus, true)
	else:
		AudioServer.set_bus_mute(bus, false)
		AudioServer.set_bus_volume_db(bus, linear_to_db(v))

# --- Persistence ------------------------------------------------------------------------------
func save_to(path: String = "") -> bool:
	if path.is_empty():
		path = settings_path
	# N1: under an active test sandbox, a settings write outside user://test_sandbox/ is refused.
	if not _TSandbox.guard_write(path):
		return false
	_ensure_loaded()
	var f := FileAccess.open(path, FileAccess.WRITE)
	if f == null:
		push_warning("Settings: cannot write %s" % path)
		return false
	f.store_string(JSON.stringify(_values, "\t"))
	f.close()
	return true

func load_from(path: String = "") -> bool:
	if path.is_empty():
		path = settings_path
	if not FileAccess.file_exists(path):
		return false
	var parsed: Variant = JSON.parse_string(FileAccess.get_file_as_string(path))
	if not (parsed is Dictionary):
		return false
	# Merge onto defaults so a missing key (older file) degrades cleanly.
	var merged := _default()
	for k in (parsed as Dictionary).keys():
		merged[k] = (parsed as Dictionary)[k]
	_values = merged
	_loaded = true
	_apply_master_volume()
	changed.emit("")
	return true

func _load_or_default() -> void:
	if not load_from():
		_values = _default()
	_loaded = true

func _ensure_loaded() -> void:
	if not _loaded:
		_load_or_default()
