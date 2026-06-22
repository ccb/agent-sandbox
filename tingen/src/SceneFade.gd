extends CanvasLayer
## Persistent scene-transition fade overlay (autoload `SceneFade`). It survives both the
## World-subtree swap (under Main) and a full change_scene_to_file (standalone), so EVERY
## transition gets a smooth fade. `go()` fades to black, performs the swap via
## WorldState.request_transition, then fades back in. When `flash` is set it plays a quick
## white "lit up" wash first — used when entering the cathedral from the city.

const FADE_SECS: float = 0.55   # fade-out + fade-in duration (each leg)
const FLASH_SECS: float = 0.45  # cathedral "lit up" white wash (rises over ×0.6, then darkens)

var _rect: ColorRect
var _busy: bool = false

func _ready() -> void:
	layer = 128  # above the HUD and everything else
	_rect = ColorRect.new()
	_rect.color = Color(0, 0, 0, 0)
	_rect.set_anchors_and_offsets_preset(Control.PRESET_FULL_RECT)
	_rect.mouse_filter = Control.MOUSE_FILTER_IGNORE
	add_child(_rect)

## Fade out -> swap -> fade in. `flash` plays a white "lit up" wash before darkening
## (cathedral entry). Safe to fire-and-forget; re-entrant calls are ignored while busy.
func go(scene_path: String, lead: String = "", flash: bool = false) -> void:
	if scene_path == "" or _busy:
		return
	_busy = true
	if flash:
		await _tween_to(Color(1, 1, 1, 1), FLASH_SECS * 0.6)  # lit up (white wash)
		await _tween_to(Color(0, 0, 0, 1), FLASH_SECS)        # ...then darken
	else:
		await _tween_to(Color(0, 0, 0, 1), FADE_SECS)         # fade out to black
	WorldState.request_transition(scene_path, lead)
	await get_tree().process_frame
	await get_tree().process_frame
	await _tween_to(Color(0, 0, 0, 0), FADE_SECS)             # fade back in
	_busy = false

func _tween_to(target: Color, secs: float) -> void:
	var tw: Tween = create_tween()
	tw.tween_property(_rect, "color", target, secs)
	await tw.finished
