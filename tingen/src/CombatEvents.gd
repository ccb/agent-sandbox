class_name CombatEvents
extends RefCounted
## Telegraph event emitters (combat plan §M1). The ONE place the ability-cast lifecycle events
## are shaped — M2's executor, the player's combat node, and the tests all emit through these
## helpers, so the payload contract can never fork. Every cast that can hurt someone announces
## itself first (`ability_cast_started` IS the telegraph; Stimulus fans it to eyes that can see
## it), then resolves (`finished`) or breaks (`interrupted` — stagger, silence, a downing).
##
## Thin wrapper over the EventBus. `dir` travels as a JSON-safe [x, y] array so the event log
## round-trips through the SaveManager unchanged.

## Resolve an autoload singleton by name. Direct `Autoload.` references fail to compile in a
## class_name script under the headless -s harness (autoloads register after class_name scripts
## are parsed); the /root lookup is ordering-independent.
static func _al(autoload_name: String) -> Node:
	return (Engine.get_main_loop() as SceneTree).root.get_node("/root/" + autoload_name)

static func cast_started(caster: String, ability: String, target: String, dir: Vector2, cast_time: float) -> void:
	_al("EventBus").emit_event("ability_cast_started", {
		"caster": caster, "ability": ability, "target": target,
		"dir": [dir.x, dir.y], "cast_time": cast_time,
	})

static func cast_finished(caster: String, ability: String) -> void:
	_al("EventBus").emit_event("ability_cast_finished", {"caster": caster, "ability": ability})

static func cast_interrupted(caster: String, ability: String, reason: String) -> void:
	_al("EventBus").emit_event("ability_cast_interrupted", {
		"caster": caster, "ability": ability, "reason": reason,
	})
