extends Panel
## The LEADS board (direction v2 §5 — Rumors -> Leads). Repurposed from the old clue/deduction UI:
## it now renders what the city is WHISPERING — the active leads (subject + where_hint + freshness),
## not a forensic evidence gallery. Investigation-as-forensics is cut (§5); the open world is
## navigated by TALK, so the board is a tracker of leads surfaced through conversation/chatter, each
## pointing at a street or place NAME (never a map marker). The toggle key (Tab) is unchanged.
##
## A lead reads: its subject, "-> <where_hint>", and a freshness tag (HOT / open / on the trail) that
## makes the perishable lifecycle (§5) legible — an open lead left to cool goes cold (Doom +5) and
## re-emerges elsewhere, so the board is a to-do list with a running clock.

const STATE_COLOR: Dictionary = {
	"open": Color(0.9, 0.85, 0.6),
	"followed": Color(0.6, 0.85, 0.7),
}
const HOT_COLOR: Color = Color(0.95, 0.55, 0.4)

@onready var _list: VBoxContainer = $Margin/Body/Scroll/List

func _ready() -> void:
	var ls := get_node_or_null("/root/LeadSystem")
	if ls != null:
		ls.leads_changed.connect(_rebuild)
		ls.lead_surfaced.connect(func(_id): _rebuild())
		ls.lead_perished.connect(func(_c, _f): _rebuild())
	visibility_changed.connect(func(): if visible: _rebuild())
	_rebuild()

func _rebuild() -> void:
	if not is_instance_valid(_list):
		return
	for c in _list.get_children():
		c.queue_free()

	_add_label("Leads — what the city is whispering", Color(0.85, 0.8, 0.6), false, 18)
	_add_spacer()

	var ls := get_node_or_null("/root/LeadSystem")
	var leads: Array = ls.active_leads() if ls != null else []
	if leads.is_empty():
		_add_label("No leads yet. Talk to people — the city knows more than it says.",
			Color(0.8, 0.8, 0.8), true)
		return

	for lead in leads:
		var state := String(lead.get("state", "open"))
		var hot := bool(lead.get("hot", false))
		var tag := "HOT" if hot else ("on the trail" if state == "followed" else "open")
		var color: Color = HOT_COLOR if hot else STATE_COLOR.get(state, Color.WHITE)
		var mark := "*" if hot else "-"
		_add_lead_row(String(lead.get("source", "")),
			"  %s %s  [%s]" % [mark, lead.get("subject", "?"), tag], color,
			"      -> %s" % lead.get("where_hint", "somewhere in the city"))

## Render one lead. M19: when the lead's source is a known NPC we put their face beside it (a small
## headshot thumb) — reusing the ONE portrait seam (Portrait.resolve_texture). If the source has no
## art (or isn't an NPC) we fall back to the exact label-only layout the board always used.
func _add_lead_row(source_id: String, subject_line: String, subject_color: Color, hint_line: String) -> void:
	var tex: Texture2D = load("res://src/Portrait.gd").resolve_texture(source_id)
	if tex == null:
		_add_label(subject_line, subject_color)
		_add_label(hint_line, Color(0.72, 0.72, 0.76))
		return
	var row := HBoxContainer.new()
	row.add_theme_constant_override("separation", 8)
	var thumb := TextureRect.new()
	thumb.custom_minimum_size = Vector2(38, 38)
	thumb.stretch_mode = TextureRect.STRETCH_KEEP_ASPECT
	thumb.tooltip_text = "Heard from %s" % source_id
	# A top-square region of the full-body portrait = a headshot thumb.
	var at := AtlasTexture.new()
	at.atlas = tex
	var side := headshot_side(tex)
	at.region = Rect2(0, 0, side, side)
	thumb.texture = at
	row.add_child(thumb)
	var col := VBoxContainer.new()
	col.size_flags_horizontal = Control.SIZE_EXPAND_FILL
	col.add_theme_constant_override("separation", 2)
	_add_label_to(col, subject_line, subject_color)
	_add_label_to(col, hint_line, Color(0.72, 0.72, 0.76))
	row.add_child(col)
	_list.add_child(row)

## The side of the top-square headshot crop for a portrait thumb: clamped to the SHORTER side so a
## wider-than-tall portrait can't run its atlas region past the texture bounds (a taller-than-wide
## portrait — every shipped one — is unaffected: side == width). Static + pure so tests can drive it.
static func headshot_side(tex: Texture2D) -> float:
	return minf(float(tex.get_width()), float(tex.get_height()))

func _add_label_to(parent: Node, text: String, color: Color) -> void:
	var l := Label.new()
	l.text = text
	l.autowrap_mode = TextServer.AUTOWRAP_WORD_SMART
	l.add_theme_color_override("font_color", color)
	parent.add_child(l)

func _add_label(text: String, color: Color, italic: bool = false, font_size: int = 0) -> void:
	var l := Label.new()
	l.text = text
	l.autowrap_mode = TextServer.AUTOWRAP_WORD_SMART
	l.add_theme_color_override("font_color", color)
	if font_size > 0:
		l.add_theme_font_size_override("font_size", font_size)
	if italic:
		l.add_theme_color_override("font_color", color.darkened(0.1))
	_list.add_child(l)

func _add_spacer() -> void:
	var s := Control.new()
	s.custom_minimum_size = Vector2(0, 10)
	_list.add_child(s)
