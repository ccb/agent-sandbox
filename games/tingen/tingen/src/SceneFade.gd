extends CanvasLayer
## Persistent scene-transition fade overlay (autoload `SceneFade`). It survives both the
## World-subtree swap (under Main) and a full change_scene_to_file (standalone), so EVERY
## transition is a cinematic fade:
##   1) darken to black over FADE_OUT_SECS,
##   2) swap the scene (hidden under the black) via WorldState.request_transition,
##   3) let the new scene slowly light up from black over FADE_IN_SECS,
##   4) scene entered.

const FADE_OUT_SECS: float = 1.0   # 1) darken to black before the swap
const FADE_IN_SECS: float = 3.0    # 3) the new scene slowly lights up from black

var _rect: ColorRect
var _busy: bool = false

func _ready() -> void:
	layer = 128  # above the HUD and everything else
	_rect = ColorRect.new()
	_rect.color = Color(0, 0, 0, 0)
	_rect.set_anchors_and_offsets_preset(Control.PRESET_FULL_RECT)
	_rect.mouse_filter = Control.MOUSE_FILTER_IGNORE
	add_child(_rect)

## Darken -> swap -> light up. Safe to fire-and-forget; re-entrant calls are ignored while busy.
func go(scene_path: String, lead: String = "") -> void:
	if scene_path == "" or _busy:
		return
	_busy = true
	await _tween_to(Color(0, 0, 0, 1), FADE_OUT_SECS)     # 1) go dark over ~1s
	WorldState.request_transition(scene_path, lead)        # 2) swap, hidden under the black
	await get_tree().process_frame
	await get_tree().process_frame
	await _tween_to(Color(0, 0, 0, 0), FADE_IN_SECS)        # 3) new scene lights up from black over ~3s
	_busy = false                                          # 4) scene entered

func _tween_to(target: Color, secs: float) -> void:
	var tw: Tween = create_tween()
	tw.tween_property(_rect, "color", target, secs)
	await tw.finished
