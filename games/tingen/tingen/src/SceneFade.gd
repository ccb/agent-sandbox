extends CanvasLayer
## Persistent scene-transition fade overlay (autoload `SceneFade`). It survives both the
## World-subtree swap (under Main) and a full change_scene_to_file (standalone), so EVERY door
## gets a clean fade: darken to black over FADE_OUT_SECS, swap the scene (hidden under the
## black) via WorldState.request_transition, then fade the new scene in over FADE_IN_SECS.
##
## The cathedral's cinematic establishing shot is a SEPARATE, chapel-only thing (the IntroCard
## in CathedralNave.tscn, which sits above this overlay and plays its own light-up/hold/reveal).

const FADE_OUT_SECS: float = 1.0   # darken to black before the swap
const FADE_IN_SECS: float = 1.0    # fade the new scene in after the swap

var _rect: ColorRect
var _busy: bool = false

func _ready() -> void:
	layer = 128  # above the HUD
	_rect = ColorRect.new()
	_rect.color = Color(0, 0, 0, 0)
	_rect.set_anchors_and_offsets_preset(Control.PRESET_FULL_RECT)
	_rect.mouse_filter = Control.MOUSE_FILTER_IGNORE
	add_child(_rect)

## Darken -> swap -> fade in. Safe to fire-and-forget; re-entrant calls ignored while busy.
func go(scene_path: String, lead: String = "") -> void:
	if scene_path == "" or _busy:
		return
	_busy = true
	await _tween_to(Color(0, 0, 0, 1), FADE_OUT_SECS)     # darken to black
	WorldState.request_transition(scene_path, lead)        # swap, hidden under the black
	await get_tree().process_frame
	await get_tree().process_frame
	await _tween_to(Color(0, 0, 0, 0), FADE_IN_SECS)        # fade the new scene in
	_busy = false

func _tween_to(target: Color, secs: float) -> void:
	var tw: Tween = create_tween()
	tw.tween_property(_rect, "color", target, secs)
	await tw.finished
