extends Control
## Toast notification layer (GDD §19.4). A bottom-right stack of transient cards that
## surface the otherwise-invisible simulation: emergent events, pressure thresholds
## crossing a quarter, and story-stage advances. Cards queue, fade in, hold, fade out
## and self-free so the simulation can stay "hidden but legible".

const MAX_VISIBLE: int = 4
const HOLD_SECONDS: float = 4.0
const FADE_SECONDS: float = 0.35

## Per-channel accent colors so the player can read severity at a glance.
const CHANNEL_COLOR: Dictionary = {
	"ambient": Color(0.55, 0.6, 0.7),
	"lead": Color(0.55, 0.8, 0.95),
	"alert": Color(0.95, 0.55, 0.45),
	"stage": Color(0.8, 0.65, 0.95),
	"system": Color(0.7, 0.75, 0.6),
}

@onready var _stack: VBoxContainer = $Stack

func _ready() -> void:
	add_to_group("toasts")
	EventManager.event_fired.connect(_on_event)
	WorldManager.pressure_threshold_crossed.connect(_on_threshold)
	WorldManager.stage_advanced.connect(_on_stage)

func _on_event(ev: Dictionary) -> void:
	var channel := "ambient"
	for e in ev.get("effects", []):
		if String(e.get("type", "")) == "notify":
			channel = String(e.get("channel", "ambient"))
	push(String(ev.get("title", "Something happens")), String(ev.get("body", "")), channel)

func _on_threshold(pressure_name: String, value: float) -> void:
	var ch := "alert" if value >= 50.0 else "ambient"
	push("%s rising" % pressure_name.capitalize(), "Now at %d." % int(value), ch)

func _on_stage(_from_stage: String, to_stage: String) -> void:
	push("The situation shifts", "Stage: %s" % to_stage.capitalize().replace("_", " "), "stage")

## Public entry point (also used by the dev console).
func push(title: String, body: String = "", channel: String = "system") -> void:
	while _stack.get_child_count() >= MAX_VISIBLE:
		var oldest := _stack.get_child(0)
		_stack.remove_child(oldest)
		oldest.queue_free()
	_stack.add_child(_make_card(title, body, channel))

## Number of toast cards currently live in the stack. Observability / test helper.
func card_count() -> int:
	return _stack.get_child_count()

func _make_card(title: String, body: String, channel: String) -> Control:
	var accent: Color = CHANNEL_COLOR.get(channel, CHANNEL_COLOR["system"])
	var panel := PanelContainer.new()
	panel.custom_minimum_size = Vector2(300, 0)
	panel.modulate = Color(1, 1, 1, 0)

	var style := StyleBoxFlat.new()
	style.bg_color = Color(0.08, 0.09, 0.12, 0.92)
	style.border_color = accent
	style.set_border_width_all(1)
	style.border_width_left = 4
	style.set_corner_radius_all(3)
	style.content_margin_left = 12
	style.content_margin_right = 12
	style.content_margin_top = 8
	style.content_margin_bottom = 8
	panel.add_theme_stylebox_override("panel", style)

	var box := VBoxContainer.new()
	box.add_theme_constant_override("separation", 2)
	panel.add_child(box)

	var title_label := Label.new()
	title_label.text = title
	title_label.add_theme_color_override("font_color", accent)
	box.add_child(title_label)

	if body != "":
		var body_label := Label.new()
		body_label.text = body
		body_label.autowrap_mode = TextServer.AUTOWRAP_WORD_SMART
		body_label.add_theme_font_size_override("font_size", 12)
		box.add_child(body_label)

	var tween := panel.create_tween()
	tween.tween_property(panel, "modulate:a", 1.0, FADE_SECONDS)
	tween.tween_interval(HOLD_SECONDS)
	tween.tween_property(panel, "modulate:a", 0.0, FADE_SECONDS)
	tween.tween_callback(panel.queue_free)
	return panel
