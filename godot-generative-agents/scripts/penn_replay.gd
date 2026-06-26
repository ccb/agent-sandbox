extends Node2D
## Plays a UPenn agent-simulation replay on the campus map.
##
## The Python sim (sim/generate_penn_replay.py) writes maps/penn_replay.json:
## per step, each persona's tile (x, y) + current activity + emoji. This scene
## renders the campus (a sibling TileMapLayer running tiled_map.gd) and animates
## one Cute Fantasy sprite per persona, easing it tile-to-tile along its path —
## so you watch Maya, Professor Ellis and Diego walk the real campus. No agent
## logic here; this is purely the viewer (the sim already decided everything).

@export_file("*.json") var replay_path: String = "res://maps/penn_replay.json"
@export var player_sheet: Texture2D  # Cute_Fantasy_Free/Player/Player.png
## Real seconds spent replaying one sim step (smaller = faster playback).
@export var step_seconds: float = 0.10
## Start the clock this many steps in — handy for screenshots mid-walk. 0 = start.
@export var preview_step: int = 0

# The Cute Fantasy player sheet is a 6x10 grid; row 0 is a 6-frame walk cycle.
const SHEET_HFRAMES := 6
const SHEET_VFRAMES := 10
const WALK_ROW := 0
const WALK_LEN := 6
const ANIM_FPS := 8.0
# A 32px character frame at this scale is ~4 tiles tall, so a person reads as
# clearly smaller than a campus building (which span ~10-20 tiles) rather than
# towering over it. The whole-campus camera (zoom ~0.5) still keeps it visible,
# and the name label above each sprite makes agents easy to find regardless.
const SPRITE_SCALE := 2.0
# The character art is centred in its frame, so the sprite's head sits this far
# above the node origin; the nameplate is parked just above that.
const SPRITE_HALF_PX := 16.0 * SPRITE_SCALE
# A distinct tint per persona so they're easy to tell apart at a glance.
const TINTS := [
	Color(1.0, 0.95, 0.95),  # Maya  - warm white
	Color(0.70, 0.82, 1.0),  # Ellis - blue
	Color(0.80, 1.0, 0.78),  # Diego - green
	Color(1.0, 0.86, 0.70),  # spare - orange
]

var _tile_px := 16
var _frames: Array = []
var _names: Array = []
var _agents := {}  # name -> {sprite, label}
var _t := 0.0
var _anim_t := 0.0


func _ready() -> void:
	var f := FileAccess.open(replay_path, FileAccess.READ)
	if f == null:
		push_error("penn_replay: cannot open %s" % replay_path)
		return
	var data: Variant = JSON.parse_string(f.get_as_text())
	if typeof(data) != TYPE_DICTIONARY:
		push_error("penn_replay: %s is not valid replay JSON" % replay_path)
		return

	var meta: Dictionary = data["meta"]
	_tile_px = int(meta["tile_px"])
	_frames = data["frames"]
	for i in meta["personas"].size():
		_names.append(meta["personas"][i]["name"])
		_spawn_agent(meta["personas"][i]["name"], i)

	# Place everyone on their first frame, then optionally fast-forward the clock.
	_t = preview_step * step_seconds
	_anim_t = 0.0
	print("penn_replay: %d steps, %d personas" % [_frames.size(), _names.size()])


func _spawn_agent(name: String, index: int) -> void:
	# One container per agent (moved as a unit); the sprite is scaled up inside it
	# while the name label stays at normal size above it.
	var node := Node2D.new()
	add_child(node)

	var spr := Sprite2D.new()
	spr.texture = player_sheet
	spr.hframes = SHEET_HFRAMES
	spr.vframes = SHEET_VFRAMES
	spr.frame = WALK_ROW * SHEET_HFRAMES
	spr.scale = Vector2(SPRITE_SCALE, SPRITE_SCALE)
	spr.modulate = TINTS[index % TINTS.size()]
	node.add_child(spr)

	var label := Label.new()
	label.text = name
	label.add_theme_font_size_override("font_size", 32)
	label.add_theme_color_override("font_color", Color.WHITE)
	label.add_theme_color_override("font_outline_color", Color.BLACK)
	label.add_theme_constant_override("outline_size", 10)
	label.horizontal_alignment = HORIZONTAL_ALIGNMENT_CENTER
	# Park the two-line nameplate just above the sprite's head (the ~90px covers
	# the two text lines), so it tracks the sprite size instead of overlapping it.
	label.position = Vector2(-110, -(SPRITE_HALF_PX + 90.0))
	label.custom_minimum_size = Vector2(220, 0)
	node.add_child(label)

	_agents[name] = {"node": node, "sprite": spr, "label": label}


func _tile_to_world(x: int, y: int) -> Vector2:
	# Tile centre in the map's pixel space (the campus TileMapLayer is unscaled).
	return Vector2((x + 0.5) * _tile_px, (y + 0.5) * _tile_px)


func _process(delta: float) -> void:
	if _frames.is_empty():
		return
	_t += delta
	_anim_t += delta

	var last := _frames.size() - 1
	var fpos := _t / step_seconds
	var i := int(fpos)
	var looped := false
	if i >= last:
		i = last
		looped = true
	var frac: float = 0.0 if looped else fpos - float(i)
	var j: int = i if looped else i + 1

	for name in _names:
		var a: Dictionary = _frames[i][name]
		var b: Dictionary = _frames[j][name]
		var pa := _tile_to_world(int(a["x"]), int(a["y"]))
		var pb := _tile_to_world(int(b["x"]), int(b["y"]))
		var agent: Dictionary = _agents[name]
		agent["node"].position = pa.lerp(pb, frac)

		var moving: bool = a["x"] != b["x"] or a["y"] != b["y"]
		if moving and b["x"] != a["x"]:
			agent["sprite"].flip_h = int(b["x"]) < int(a["x"])
		var frame_in_row: int = (int(_anim_t * ANIM_FPS) % WALK_LEN) if moving else 0
		agent["sprite"].frame = WALK_ROW * SHEET_HFRAMES + frame_in_row

		# "<activity> @ UPenn:Building:grounds" -> just the activity for the label.
		var act := String(a["act"]).split(" @ ")[0]
		agent["label"].text = "%s\n%s %s" % [name, a["e"], act]
