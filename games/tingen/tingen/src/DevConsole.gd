extends CanvasLayer
## Dev console (autoload singleton `DevConsole`). Toggle with the backtick key.
##
## A dependency-free debug overlay that pokes the simulation directly: set/adjust
## pressures, force refreshes and stage advances, jump the clock, fire events, drop
## clues, and save/load. Builds its own UI at runtime so it needs no scene wiring.
## Intended for development only — not shipped UI.

const HISTORY_MAX: int = 200

var _root: Control
var _output: RichTextLabel
var _input: LineEdit
var _open: bool = false

func _ready() -> void:
	layer = 128
	process_mode = Node.PROCESS_MODE_ALWAYS
	_build_ui()
	_set_open(false)
	_log("Tingen dev console. Type 'help'.")

func _build_ui() -> void:
	_root = Control.new()
	_root.set_anchors_and_offsets_preset(Control.PRESET_FULL_RECT)
	_root.mouse_filter = Control.MOUSE_FILTER_IGNORE
	add_child(_root)

	var panel := PanelContainer.new()
	panel.set_anchors_and_offsets_preset(Control.PRESET_TOP_WIDE)
	panel.offset_bottom = 260.0
	var style := StyleBoxFlat.new()
	style.bg_color = Color(0.04, 0.05, 0.07, 0.94)
	panel.add_theme_stylebox_override("panel", style)
	_root.add_child(panel)

	var box := VBoxContainer.new()
	panel.add_child(box)

	_output = RichTextLabel.new()
	_output.size_flags_vertical = Control.SIZE_EXPAND_FILL
	_output.custom_minimum_size = Vector2(0, 210)
	_output.scroll_following = true
	box.add_child(_output)

	_input = LineEdit.new()
	_input.placeholder_text = "command…"
	_input.text_submitted.connect(_on_submit)
	box.add_child(_input)

func _unhandled_input(event: InputEvent) -> void:
	if event.is_action_pressed("toggle_console"):
		_set_open(not _open)
		get_viewport().set_input_as_handled()

func _set_open(open: bool) -> void:
	_open = open
	_root.visible = open
	_root.mouse_filter = Control.MOUSE_FILTER_STOP if open else Control.MOUSE_FILTER_IGNORE
	if open:
		_input.grab_focus()
		_input.clear()

func _on_submit(text: String) -> void:
	_input.clear()
	if text.strip_edges() == "":
		return
	_log("> " + text)
	_run(text.strip_edges())

func _run(line: String) -> void:
	var parts := line.split(" ", false)
	var cmd := parts[0].to_lower()
	var args := parts.slice(1)
	match cmd:
		"help":
			_log("commands: set <p> <v> | adjust <p> <d> | pressures | refresh | stage | advance | time <h> <m> | event | clue <id> | sabotage [item] | turn <agent> | toast <msg> | save | load")
		"set":
			if args.size() >= 2:
				WorldState.set_pressure(StringName(args[0]), float(args[1]))
				_log("%s = %s" % [args[0], args[1]])
		"adjust":
			if args.size() >= 2:
				WorldState.adjust(StringName(args[0]), float(args[1]))
				_log("%s now %.1f" % [args[0], WorldState.get_pressure(StringName(args[0]))])
		"pressures":
			for v in WorldState.PRESSURE_VARS:
				_log("  %s = %.1f" % [String(v), WorldState.get_pressure(v)])
			_log("  stability = %.1f" % WorldState.stability())
		"refresh":
			WorldManager.refresh()
			_log("refreshed (#%d), stage=%s" % [WorldManager.refresh_count, WorldManager.current_stage_id])
		"stage":
			_log("stage=%s refresh=%d slots=%s" % [WorldManager.current_stage_id, WorldManager.refresh_count, str(WorldManager.slots)])
		"advance":
			WorldManager.force_advance_stage()
			_log("stage -> %s" % WorldManager.current_stage_id)
		"time":
			if args.size() >= 2:
				Clock.set_time(Clock.day, int(args[0]) * 60 + int(args[1]))
				_log("time = %s (%s)" % [Clock.hhmm(), Clock.phase])
		"event":
			EventManager._on_refreshed(WorldManager.refresh_count)
			_log("forced an event roll")
		"clue":
			if args.size() >= 1:
				_log("collect %s: %s" % [args[0], str(ClueDB.collect(args[0]))])
		"sabotage":
			if args.size() >= 1:
				_log("sabotage %s: %s" % [args[0], str(PlayerActions.sabotage(args[0]))])
			else:
				var _item := PlayerActions.sabotage_any()
				_log("sabotaged rite cache: %s" % (_item if _item != "" else "(cache empty)"))
		"turn":
			if args.size() >= 1:
				_log("turn %s: %s" % [args[0], str(PlayerActions.social_influence(args[0]))])
			else:
				_log("usage: turn <agent_id>")
		"toast":
			_toast(" ".join(args))
		"save":
			_log("saved: %s" % str(SaveManager.save_game()))
		"load":
			_log("loaded: %s" % str(SaveManager.load_game()))
		_:
			_log("unknown command '%s'" % cmd)

func _toast(msg: String) -> void:
	var layers := get_tree().get_nodes_in_group("toasts")
	if layers.size() > 0:
		layers[0].push("Console", msg, "system")
	else:
		_log("(no toast layer) " + msg)

func _log(msg: String) -> void:
	_output.append_text(msg + "\n")
	if _output.get_line_count() > HISTORY_MAX:
		_output.remove_paragraph(0)
