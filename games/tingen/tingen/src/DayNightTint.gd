extends CanvasModulate
## Tints the whole 2D canvas per day phase — day/night mood with zero art.
## Attach to a CanvasModulate node in a world scene; it follows `Clock.phase_changed`.

const PHASE_TINTS: Dictionary = {
	"late-night": Color(0.42, 0.46, 0.66),
	"early-morning": Color(0.66, 0.66, 0.78),
	"morning": Color(1.0, 0.98, 0.93),
	"afternoon": Color(1.0, 1.0, 1.0),
	"dusk": Color(0.95, 0.74, 0.62),
	"night": Color(0.55, 0.57, 0.74),
}

@export var lerp_speed: float = 1.5
var _target: Color = Color.WHITE

func _ready() -> void:
	_target = PHASE_TINTS.get(Clock.phase, Color.WHITE)
	color = _target
	Clock.phase_changed.connect(_on_phase_changed)

func _on_phase_changed(phase: String, _day: int) -> void:
	_target = PHASE_TINTS.get(phase, Color.WHITE)

func _process(delta: float) -> void:
	color = color.lerp(_target, clampf(delta * lerp_speed, 0.0, 1.0))
