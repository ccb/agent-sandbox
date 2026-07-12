extends Panel
## Rituals & occult practices panel (toggle: R). Two sections:
##   1. Your occult practices — every player tool with its usage, requirements and costs, and
##      a Use button enabled only when it can be used right now (OccultToolManager.tool_views).
##   2. The Descent — a read-only reference for the cult's summoning rite (recipe + steps),
##      loaded from data/rituals.json.

const RITUALS_PATH: String = "res://data/rituals.json"

@onready var _tools_box: VBoxContainer = $Margin/Body/Scroll/List/Tools
@onready var _rite_box: VBoxContainer = $Margin/Body/Scroll/List/Rite

var _rituals: Dictionary = {}
var _tool_rows: int = 0
var _rite_steps: int = 0

func _ready() -> void:
	visible = false
	_load_rituals()
	Inventory.item_added.connect(func(_i, _c): if visible: refresh())
	Inventory.item_removed.connect(func(_i, _c): if visible: refresh())

func _load_rituals() -> void:
	if not FileAccess.file_exists(RITUALS_PATH):
		push_error("RitualPanel: missing %s" % RITUALS_PATH)
		return
	var parsed: Variant = JSON.parse_string(FileAccess.get_file_as_string(RITUALS_PATH))
	if typeof(parsed) == TYPE_DICTIONARY:
		_rituals = parsed

func toggle() -> void:
	visible = not visible
	if visible:
		refresh()

func tool_row_count() -> int:
	return _tool_rows

func rite_step_count() -> int:
	return _rite_steps

func refresh() -> void:
	_build_tools()
	_build_rite()

func _build_tools() -> void:
	# free() synchronously, not queue_free: a single tool Use can fire item_removed AND
	# item_added (a tool that spends one ingredient and produces another) plus the explicit
	# refresh in _on_use — several refreshes in one frame. queue_free defers removal to end-of-
	# frame, so a later same-frame refresh would stack duplicate rows on children not yet reaped.
	for c in _tools_box.get_children():
		c.free()
	_tool_rows = 0
	for v in OccultToolManager.tool_views():
		_tools_box.add_child(_tool_row(v))
		_tool_rows += 1

func _tool_row(v: Dictionary) -> Control:
	var box := VBoxContainer.new()
	box.add_theme_constant_override("separation", 2)
	_label(box, String(v["name"]), Color(0.7, 0.45, 0.85), 16)
	_label(box, String(v["description"]), Color(0.82, 0.82, 0.86))
	var req := "Requires: %s" % _humanize(String(v["requires_item"]))
	var ing: Dictionary = (v["cost"] as Dictionary).get("items", {})
	for k in ing.keys():
		req += ", %s ×%d" % [_humanize(String(k)), int(ing[k])]
	_label(box, req, Color(0.7, 0.7, 0.75))
	var cost: Dictionary = v["cost"]
	var uses := "unlimited" if int(v["uses_left"]) < 0 else "%d left" % int(v["uses_left"])
	_label(box, "Cost: fatigue +%d, attention +%d   ·   uses: %s" % [
		int(cost["fatigue"]), int(cost["attention"]), uses], Color(0.7, 0.7, 0.75))
	var use_btn := Button.new()
	use_btn.text = "Use"
	use_btn.disabled = not bool(v["can_use"])
	var id := String(v["id"])
	use_btn.pressed.connect(func(): _on_use(id))
	box.add_child(use_btn)
	box.add_child(HSeparator.new())
	return box

func _on_use(id: String) -> void:
	var res: Dictionary = OccultToolManager.use(id)
	WorldState.thought_requested.emit(String(res.get("text", "Nothing comes.")))
	# Refresh explicitly: use() can change a tool's uses-left / can-use WITHOUT touching the
	# Inventory (a limited-use tool that spends no ingredient), so the item_added/removed signals
	# aren't a reliable trigger on their own. Synchronous free() (see _build_tools) makes the
	# resulting same-frame rebuilds idempotent, so overlap with any signal-driven refresh is safe.
	refresh()

func _build_rite() -> void:
	# Synchronous free() for the same same-frame double-refresh reason as _build_tools.
	for c in _rite_box.get_children():
		c.free()
	_rite_steps = 0
	# M28: the player COUNTER-RITE action sits at the top of the rite section (the only player verb that
	# pushes Doom DOWN) — rendered into the SAME _rite_box (no .tscn change), and it does NOT count toward
	# rite_step_count() (that stays the descent's authored steps).
	_build_counter_rite()
	var rite: Dictionary = _rituals.get("summoning_descent", {})
	if rite.is_empty():
		return
	_label(_rite_box, String(rite.get("name", "The Descent")), Color(0.85, 0.45, 0.45), 16)
	_label(_rite_box, String(rite.get("description", "")), Color(0.82, 0.82, 0.86))
	var ing: Dictionary = rite.get("ingredients", {})
	var recipe := "Requires: "
	var parts: PackedStringArray = []
	for k in ing.keys():
		parts.append("%s ×%d" % [_humanize(String(k)), int(ing[k])])
	_label(_rite_box, recipe + ", ".join(parts), Color(0.7, 0.7, 0.75))
	_label(_rite_box, "Steps:", Color(0.85, 0.8, 0.6))
	var i := 1
	for step in rite.get("steps", []):
		_label(_rite_box, "  %d. %s" % [i, String(step)], Color(0.82, 0.82, 0.86))
		i += 1
		_rite_steps += 1

## M28 — render the player COUNTER-RITE block (name, cost/effect summary, and a Use button that works
## the rite through the CounterRite autoload). Disabled unless the ingredients are in hand. All content
## is DATA (CounterRite.rite_def); the panel knows no item id or number.
func _build_counter_rite() -> void:
	var cr := get_node_or_null("/root/CounterRite")
	if cr == null:
		return
	var d: Dictionary = cr.rite_def()
	if d.is_empty():
		return
	_label(_rite_box, String(d.get("name", "The Unbinding Rite")), Color(0.55, 0.75, 0.95), 16)
	_label(_rite_box, String(d.get("description", "")), Color(0.82, 0.82, 0.86))
	var ing: Dictionary = d.get("ingredients", {})
	var parts: PackedStringArray = []
	for k in ing.keys():
		parts.append("%s ×%d" % [_humanize(String(k)), int(ing[k])])
	_label(_rite_box, "Requires: " + ", ".join(parts), Color(0.7, 0.7, 0.75))
	_label(_rite_box, "Turns the descent back (Doom −%d) · draws the Beyond's eye (Notice +%d)"
		% [int(d.get("doom_reduction", 0)), int(d.get("notice_cost", 0))], Color(0.7, 0.7, 0.75))
	var use_btn := Button.new()
	use_btn.text = "Work the Unbinding Rite"
	use_btn.disabled = not bool(cr.can_perform().get("ok", false))
	use_btn.pressed.connect(func(): _on_counter_rite())
	_rite_box.add_child(use_btn)
	_rite_box.add_child(HSeparator.new())

func _on_counter_rite() -> void:
	var cr := get_node_or_null("/root/CounterRite")
	if cr == null:
		return
	var res: Dictionary = cr.perform()
	if bool(res.get("ok", false)):
		WorldState.thought_requested.emit("You work the unbinding rite. The descent falters — and something vast turns to look at you.")
	else:
		WorldState.thought_requested.emit("You lack what the unbinding rite demands.")
	refresh()

func _label(box: VBoxContainer, text: String, color: Color, font_size: int = 0) -> void:
	var l := Label.new()
	l.text = text
	l.autowrap_mode = TextServer.AUTOWRAP_WORD_SMART
	l.add_theme_color_override("font_color", color)
	if font_size > 0:
		l.add_theme_font_size_override("font_size", font_size)
	box.add_child(l)

func _humanize(id: String) -> String:
	return id.replace("_", " ") if id != "" else "—"

func _unhandled_input(event: InputEvent) -> void:
	if visible and event.is_action_pressed("ui_cancel"):
		visible = false
		get_viewport().set_input_as_handled()
