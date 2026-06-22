class_name OccultTool
extends RefCounted
## Abstract occult perception tool. `use()` is the fixed template: verify can_use, pay
## the cost (fatigue/attention via WorldState, ingredients via Inventory, plus any
## `produces`), call the subclass `_perform`, then `_apply_risk`. Subclasses override only
## `_perform` and `_apply_risk`. Result is a Dictionary:
##   { ok, kind, text, lead, mislead }.

## Resolve an autoload singleton by name. Direct `Autoload.` references fail to compile
## in a class_name script under the headless -s harness (autoloads register after
## class_name scripts are parsed); the /root lookup is ordering-independent.
static func _al(autoload_name: String) -> Node:
	return (Engine.get_main_loop() as SceneTree).root.get_node("/root/" + autoload_name)

var id: String = ""
var def: Dictionary = {}
var uses_left: int = -1   # -1 = unlimited

func _init(tool_id: String, tool_def: Dictionary) -> void:
	id = tool_id
	def = tool_def
	uses_left = int(def.get("uses_per_run", -1))

func can_use() -> bool:
	if uses_left == 0:
		return false
	var item_id := String(def.get("item_id", ""))
	if item_id != "" and not _al("Inventory").has(item_id):
		return false
	for ing in (def.get("ingredient_cost", {}) as Dictionary).keys():
		if not _al("Inventory").has(String(ing), int(def["ingredient_cost"][ing])):
			return false
	return true

func compute_cost() -> Dictionary:
	return {
		"fatigue": float(def.get("fatigue_cost", 0.0)),
		"attention": float(def.get("attention_cost", 0.0)),
		"items": (def.get("ingredient_cost", {}) as Dictionary).duplicate(true),
	}

## TEMPLATE METHOD — do not override. `rng` and `corruption` come from the manager.
func use(rng: RandomNumberGenerator, corruption: float) -> Dictionary:
	if not can_use():
		return {"ok": false, "kind": "blocked", "text": "Cannot use right now.", "lead": "", "mislead": false}
	var cost := compute_cost()
	_al("WorldState").adjust(&"fatigue", float(cost["fatigue"]))
	_al("WorldState").adjust(&"attention", float(cost["attention"]))
	for ing in (cost["items"] as Dictionary).keys():
		_al("Inventory").remove(String(ing), int(cost["items"][ing]))
	for prod in (def.get("produces", {}) as Dictionary).keys():
		_al("Inventory").add(String(prod), int(def["produces"][prod]))
	if uses_left > 0:
		uses_left -= 1
	var result := _perform()
	_apply_risk(result, rng, corruption)
	return result

## VIRTUAL — each subclass's actual effect.
func _perform() -> Dictionary:
	return {"ok": true, "kind": "noop", "text": "", "lead": "", "mislead": false}

## VIRTUAL — how this tool's risk manifests.
func _apply_risk(_result: Dictionary, _rng: RandomNumberGenerator, _corruption: float) -> void:
	pass
