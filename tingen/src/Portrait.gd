extends Control
class_name Portrait
## M19 — the reusable NPC portrait widget + resolver seam.
##
## ONE seam for "show a face": resolves an NPC id -> its painterly portrait texture by the SAME
## convention the world body uses (NPC.resolve_sprite_path — assets/characters/<id>.png, honouring an
## explicit `sprite` override on the def), so the dialogue panel, the leads board and any future
## face-UI share this and never grow a per-NPC branch.
##
## As a NODE (this Control): a framed, headshot-cropped portrait box. show_npc(id) fills it; clear()
## empties it. When an id has NO art it shows a neutral silhouette (a dim "?" plate) rather than a
## broken/blank slot, and never crashes. clip_contents crops the full-body portrait down to a
## headshot: the image is laid full-width at its natural aspect and top-anchored, so only the head +
## shoulders sit inside the box.
##
## As a RESOLVER (static): Portrait.resolve_texture(id) / resolve_path(id) — pure, defensive, and
## usable from anywhere (tests call them directly). Cosmetic only: nothing here touches combat.

## The M16 seam lives on NPC.gd as a static. Resolved via load() (untyped) — a typed preload const of
## a class_name-less script can't dispatch its statics; load() returns the Script and dispatches fine
## (the same pattern the M16 tests use).
const NPC_SCRIPT_PATH := "res://src/NPC.gd"

var _image: TextureRect
var _silhouette: Control
var _base_min: Vector2 = Vector2(112, 148)

func _ready() -> void:
	clip_contents = true
	custom_minimum_size = _base_min
	# Build children in code so the widget is a single self-contained node wherever it is instanced.
	if _image == null:
		_build()
	_apply_text_scale()
	var s := get_node_or_null("/root/Settings")
	if s != null and s.has_signal("changed"):
		# Connect via a NAMED method (not a fresh lambda) + an is_connected guard so re-entering
		# _ready() — e.g. a Portrait re-parented into another panel — can't stack duplicate handlers.
		var cb := Callable(self, "_on_settings_changed")
		if not s.changed.is_connected(cb):
			s.changed.connect(cb)

## Settings.changed carries a key arg; the portrait only re-scales, so we ignore it. Named so the
## _ready() connect stays idempotent under is_connected.
func _on_settings_changed(_k) -> void:
	_apply_text_scale()

func _build() -> void:
	var frame := Panel.new()   # inherits the shared occult theme's panel stylebox (gilt border on ink)
	frame.name = "Frame"
	frame.set_anchors_preset(Control.PRESET_FULL_RECT)
	frame.mouse_filter = Control.MOUSE_FILTER_IGNORE
	add_child(frame)

	_silhouette = Label.new()
	_silhouette.name = "Silhouette"
	_silhouette.text = "?"
	_silhouette.set_anchors_preset(Control.PRESET_FULL_RECT)
	_silhouette.horizontal_alignment = HORIZONTAL_ALIGNMENT_CENTER
	_silhouette.vertical_alignment = VERTICAL_ALIGNMENT_CENTER
	_silhouette.add_theme_color_override("font_color", Color(0.45, 0.43, 0.38, 0.8))
	_silhouette.add_theme_font_size_override("font_size", 40)
	_silhouette.mouse_filter = Control.MOUSE_FILTER_IGNORE
	add_child(_silhouette)

	_image = TextureRect.new()
	_image.name = "Image"
	_image.stretch_mode = TextureRect.STRETCH_SCALE   # fill the rect we size it to; aspect kept by our sizing
	_image.mouse_filter = Control.MOUSE_FILTER_IGNORE
	_image.visible = false
	add_child(_image)

# --- Node API ------------------------------------------------------------------------------------
## Fill the slot with the NPC's portrait, or the neutral silhouette when the id has no art. Loads on
## the calling (main) thread — the texture is small + cached, so it never blocks the async dialogue.
func show_npc(id: String) -> void:
	if _image == null:
		_build()
	_set_texture(resolve_texture(id))

## Empty the slot (conversation closed / no speaker) — back to the neutral silhouette.
func clear() -> void:
	if _image == null:
		_build()
	_set_texture(null)

## The texture currently shown in the slot, or null when the silhouette is showing. Test seam.
func current_texture() -> Texture2D:
	return _image.texture if _image != null else null

func _set_texture(tex: Texture2D) -> void:
	if tex != null:
		_image.texture = tex
		_image.visible = true
		_silhouette.visible = false
		_frame_headshot(tex)
	else:
		_image.texture = null
		_image.visible = false
		_silhouette.visible = true

## Lay the full-body portrait full-width at its natural aspect, top-anchored, so clip_contents crops
## it to a head-and-shoulders headshot. Pure layout math — safe when the texture has zero size.
func _frame_headshot(tex: Texture2D) -> void:
	var w := custom_minimum_size.x
	var tw := float(tex.get_width())
	var th := float(tex.get_height())
	var h := w if tw <= 0.0 else w * (th / tw)
	_image.position = Vector2.ZERO
	_image.size = Vector2(w, h)

## Accessibility: scale the box (and thus the headshot) by the M10 text_scale, so the portrait grows
## with the rest of the UI. Re-frames the live texture to the new size.
func _apply_text_scale() -> void:
	var scale := 1.0
	var s := get_node_or_null("/root/Settings")
	if s != null and s.has_method("text_scale"):
		scale = maxf(0.1, s.text_scale())
	custom_minimum_size = _base_min * scale
	if _image != null and _image.texture != null:
		_frame_headshot(_image.texture)

# --- Resolver (static) ---------------------------------------------------------------------------
## Resolve an NPC id -> portrait resource path, reusing the M16 convention seam. Pulls the def from
## NpcDB (for an explicit `sprite` override) when the autoload is reachable, else resolves by the
## pure assets/characters/<id>.png convention. Returns "" when no art exists.
static func resolve_path(id: String) -> String:
	var npc_script = load(NPC_SCRIPT_PATH)
	return String(npc_script.resolve_sprite_path(id, _def_for(id)))

## Resolve an NPC id -> a loaded portrait Texture2D, or null when the id has no art (graceful fallback).
static func resolve_texture(id: String) -> Texture2D:
	var path := resolve_path(id)
	if path == "":
		return null
	var tex = load(path)
	return tex if tex is Texture2D else null

## Best-effort def lookup for the explicit-sprite override, without a hard NpcDB dependency (so the
## resolver works in isolated tests). Convention resolution still works with an empty def.
static func _def_for(id: String) -> Dictionary:
	var loop := Engine.get_main_loop()
	if loop is SceneTree:
		var db = (loop as SceneTree).root.get_node_or_null("/root/NpcDB")
		if db != null and db.has_method("get_def"):
			var d = db.get_def(id)
			if d is Dictionary:
				return d
	return {}
