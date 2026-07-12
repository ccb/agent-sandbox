extends CanvasLayer
## TEMPORARY debug panel (autoload `ModelPanel`) to pick the LLM model for the GM (default) and each
## character at runtime. Toggle with the `toggle_models` action (the `9` key). Selections write to
## ModelConfig; HttpSidecar stamps `model_for(agent_id)` onto each /decide + /converse request, so the
## chosen model reaches the LLM call. Built in code (no .tscn) so it ships with the autoload.
##
## TODO: replace this panel + ModelConfig with a proper engine interface + a per-character node once
## Tingen ships and we do the cognition refactor. This is a stopgap so the cult can run on a model
## strong enough for its emergent behavior to show.

var _center: CenterContainer = null
var _box: VBoxContainer = null

func _ready() -> void:
	process_mode = Node.PROCESS_MODE_ALWAYS   # usable even when the world is paused
	layer = 90
	# A full-rect CenterContainer keeps the panel CENTERED and fully on-screen regardless of the
	# viewport/camera (the previous top-right anchor grew the panel off the right edge).
	_center = CenterContainer.new()
	_center.set_anchors_preset(Control.PRESET_FULL_RECT)
	add_child(_center)
	var panel := PanelContainer.new()
	_center.add_child(panel)
	var margin := MarginContainer.new()
	for side in ["left", "right", "top", "bottom"]:
		margin.add_theme_constant_override("margin_" + side, 16)
	_box = VBoxContainer.new()
	_box.add_theme_constant_override("separation", 6)
	margin.add_child(_box)
	panel.add_child(margin)
	_center.visible = false

func _unhandled_input(event: InputEvent) -> void:
	if event.is_action_pressed("toggle_models"):
		_center.visible = not _center.visible
		if _center.visible:
			_populate()
		get_viewport().set_input_as_handled()

## Rebuild the rows from the live agent registry each time the panel opens (agents can change).
func _populate() -> void:
	for c in _box.get_children():
		c.queue_free()
	var title := Label.new()
	title.text = "Model selection (debug — '9' to toggle)"
	_box.add_child(title)
	_add_row("GM (default)", "", true)
	var ag := get_node_or_null("/root/Agents")
	if ag != null:
		for a in ag.all():
			if a.id == "player":
				continue
			_add_row(String(a.display_name), String(a.id), false)

## The ModelConfig autoload, via runtime lookup (an autoload referencing another by its global name can
## fail to resolve at parse time under the headless harness — match the codebase's get_node pattern).
func _mc() -> Node:
	return get_node_or_null("/root/ModelConfig")

## One label + dropdown. The GM row picks the default model; an agent row picks its override ("default"
## = clear the override and follow the GM model).
func _add_row(label_text: String, agent_id: String, is_default: bool) -> void:
	var mc := _mc()
	if mc == null:
		return
	var models: Array = mc.MODELS
	var row := HBoxContainer.new()
	row.add_theme_constant_override("separation", 10)
	var lbl := Label.new()
	lbl.text = label_text
	lbl.custom_minimum_size = Vector2(180, 0)
	row.add_child(lbl)
	var opt := OptionButton.new()
	if not is_default:
		opt.add_item("default")   # index 0
	for m in models:
		opt.add_item(String(m))
	if is_default:
		opt.select(maxi(0, models.find(String(mc.default_model))))
	else:
		var cur := String((mc.overrides as Dictionary).get(agent_id, ""))
		opt.select(0 if cur == "" else 1 + models.find(cur))
	opt.item_selected.connect(func(idx: int) -> void:
		var chosen := opt.get_item_text(idx)
		var mc2 := _mc()
		if mc2 == null:
			return
		if is_default:
			mc2.set_default(chosen)
		else:
			mc2.set_override(agent_id, chosen))
	row.add_child(opt)
	_box.add_child(row)
