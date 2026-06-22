extends Panel
## Prayer panel (toggle: P). Pick a god from the focused Tingen pantheon, offer a prayer in
## your own words, and read the god's adjudicated answer — Granted (应允), Cryptic (神秘应答),
## Ignored (无应) or Punished (惩罚) — coloured by outcome. Wires to PrayerService.pray()
## (Plan E); each god button shows current standing.

const OUTCOME_COLORS: Dictionary = {
	"granted": Color(0.55, 0.85, 0.55),
	"cryptic": Color(0.72, 0.5, 0.9),
	"ignored": Color(0.6, 0.6, 0.65),
	"punished": Color(0.9, 0.4, 0.4),
}

@onready var _gods_box: VBoxContainer = $Margin/Body/Cols/Left/Gods
@onready var _prayer_edit: TextEdit = $Margin/Body/Cols/Right/PrayerEdit
@onready var _pray_btn: Button = $Margin/Body/Cols/Right/PrayButton
@onready var _selected_label: Label = $Margin/Body/Cols/Right/SelectedGod
@onready var _response: RichTextLabel = $Margin/Body/Cols/Right/Response

var _selected: String = ""
var _last_outcome: String = ""

func _ready() -> void:
	visible = false
	_pray_btn.pressed.connect(_on_pray)
	_build_gods()

func toggle() -> void:
	visible = not visible
	if visible:
		_build_gods()
		_refresh_selected()

func god_button_count() -> int:
	return _gods_box.get_child_count()

func selected_god() -> String:
	return _selected

func last_outcome() -> String:
	return _last_outcome

## Headless-testable entry: select a god, offer a prayer, render the response. Returns the
## PrayerService outcome dict.
func submit_prayer(god_id: String, text: String) -> Dictionary:
	_selected = god_id
	var res: Dictionary = PrayerService.pray(god_id, text)
	_render_response(res)
	return res

func _build_gods() -> void:
	# Synchronous free() (not queue_free): offering a prayer fires _render_response -> _build_gods
	# in the same frame the panel may already be rebuilding (the test offers two prayers back to
	# back). queue_free defers to end-of-frame, stacking duplicate god buttons — the B4/C2/D2 bug.
	for c in _gods_box.get_children():
		c.free()
	# One shared ButtonGroup makes the gods a radio set: selecting another clears the previous,
	# and re-clicking the active one can't deselect it into an orphaned visual state.
	var group := ButtonGroup.new()
	for god in GodDB.all():
		var id := String(god["id"])
		var standing := PrayerService.get_standing(id)
		var btn := Button.new()
		btn.text = "%s (%s)   ·   standing %+d" % [
			String(god.get("name", "?")), String(god.get("name_zh", "")), int(round(standing))]
		btn.tooltip_text = String(god.get("blurb", ""))
		btn.toggle_mode = true
		btn.button_group = group
		btn.button_pressed = (id == _selected)
		btn.pressed.connect(func() -> void: _select(id))
		_gods_box.add_child(btn)
	if _selected == "" and _gods_box.get_child_count() > 0:
		_select(String(GodDB.ids()[0]))

func _select(id: String) -> void:
	_selected = id
	_refresh_selected()

func _refresh_selected() -> void:
	if _selected == "":
		_selected_label.text = "Choose a god to petition."
		return
	var god: Dictionary = GodDB.get_def(_selected)
	_selected_label.text = "%s · %s\n%s" % [
		String(god.get("name", "?")), String(god.get("name_zh", "")), String(god.get("blurb", ""))]

func _on_pray() -> void:
	if _selected == "":
		return
	submit_prayer(_selected, _prayer_edit.text)

func _render_response(res: Dictionary) -> void:
	if not bool(res.get("ok", false)):
		_last_outcome = ""
		_response.text = "[i]%s[/i]" % String(res.get("reason", "The prayer falters."))
		return
	_last_outcome = String(res.get("outcome", ""))
	var color: Color = OUTCOME_COLORS.get(_last_outcome, Color.WHITE)
	var header := "%s (%s)" % [_last_outcome.capitalize(), String(res.get("outcome_zh", ""))]
	_response.text = "[color=#%s][b]%s[/b][/color]\n%s" % [
		color.to_html(false), header, String(res.get("message", ""))]
	_build_gods()   # standing may have changed -> refresh the buttons

func _unhandled_input(event: InputEvent) -> void:
	if visible and event.is_action_pressed("ui_cancel"):
		visible = false
		get_viewport().set_input_as_handled()
