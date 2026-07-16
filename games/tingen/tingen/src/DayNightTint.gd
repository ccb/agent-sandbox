extends CanvasModulate
## Tints the whole 2D canvas per day phase — day/night mood with zero art.
## Attach to a CanvasModulate node in a world scene; it follows `Clock.phase_changed`.
##
## P5 (experiential wave): wired into the LIVE City.tscn — it had only ever ridden the orphaned
## CityBlocks demo, so the real streets never changed with the clock. Occult-noir palette:
## neutral day, a warm amber dusk, cold blue-grey nights that deepen after 23:00.
##
## PRESENTATION ONLY. Live it eases between tints (_process lerp); headless it applies the
## mapping INSTANTLY on phase_changed and never processes — the state-level phase->tint mapping
## is pinned by tests/test_city_place.gd, the rendered pixels by tests/screenshot_probe.gd, and
## the deterministic gates run headless where a CanvasModulate draws nothing anyway.

const PHASE_TINTS: Dictionary = {
	"late-night": Color(0.38, 0.42, 0.62),
	"early-morning": Color(0.66, 0.66, 0.78),
	"morning": Color(1.0, 0.98, 0.93),
	"afternoon": Color(1.0, 1.0, 1.0),
	"dusk": Color(0.95, 0.74, 0.60),
	"night": Color(0.50, 0.53, 0.72),
}

@export var lerp_speed: float = 1.5
var _target: Color = Color.WHITE

## Pure: the authored tint for a phase — white for anything unknown (never a black screen).
static func tint_for_phase(phase: String) -> Color:
	return PHASE_TINTS.get(phase, Color.WHITE)

func _ready() -> void:
	_target = tint_for_phase(Clock.phase)
	color = _target
	Clock.phase_changed.connect(_on_phase_changed)
	if DisplayServer.get_name() == "headless":
		set_process(false)   # no per-frame easing headless; _on_phase_changed applies instantly

func _on_phase_changed(phase: String, _day: int) -> void:
	_target = tint_for_phase(phase)
	if not is_processing():
		color = _target   # headless (or eased-off) — state-level instant apply

func _process(delta: float) -> void:
	color = color.lerp(_target, clampf(delta * lerp_speed, 0.0, 1.0))
