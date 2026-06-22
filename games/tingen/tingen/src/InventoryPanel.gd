extends Panel
## Player inventory panel (toggle: I). Lists every item the player carries, read from the
## Inventory autoload, refreshing live while open as items are added / removed / used. A
## read-only view for the slice -- actually using items happens through the ritual and
## occult-tool flows, not here.

@onready var _summary: Label = $Margin/Body/Summary
@onready var _list: VBoxContainer = $Margin/Body/Scroll/List

func _ready() -> void:
	visible = false
	Inventory.item_added.connect(func(_id, _c): if visible: refresh())
	Inventory.item_removed.connect(func(_id, _c): if visible: refresh())
	Inventory.item_used.connect(func(_id): if visible: refresh())

func toggle() -> void:
	visible = not visible
	if visible:
		refresh()

func refresh() -> void:
	var items: Array = Inventory.items()
	items.sort_custom(func(a, b): return String(a["id"]) < String(b["id"]))
	_summary.text = "%d item type%s carried" % [items.size(), "" if items.size() == 1 else "s"]
	# free() synchronously (not queue_free): add/remove can fire several times in one frame,
	# and a deferred free would let a second refresh stack duplicate rows onto unreaped children.
	for c in _list.get_children():
		c.free()
	if items.is_empty():
		var empty := Label.new()
		empty.text = "Empty. Pick something up out in the world."
		empty.modulate = Color(0.6, 0.6, 0.65)
		_list.add_child(empty)
		return
	for it in items:
		var l := Label.new()
		l.text = _row_text(it)
		l.autowrap_mode = TextServer.AUTOWRAP_WORD_SMART
		_list.add_child(l)

func _row_text(it: Dictionary) -> String:
	var def: ItemDef = it.get("def")
	var nm: String = def.name if def != null else String(it.get("id", "?"))
	var line: String = nm
	var count: int = int(it.get("count", 1))
	if count > 1:
		line += " ×%d" % count
	if def != null and def.description != "":
		line += "  —  " + def.description
	return line

# --- Test/debug seam ---------------------------------------------------------------------
func line_count() -> int:
	return _list.get_children().size()

func _unhandled_input(event: InputEvent) -> void:
	if visible and event.is_action_pressed("ui_cancel"):
		visible = false
		get_viewport().set_input_as_handled()
