extends Node
## Player inventory (autoload singleton `Inventory`). Holds runtime counts
## `{ item_id -> count }`, enforces per-item stacking from ItemDB, applies declarative
## `on_use` effects, and persists counts through SaveManager. Stays ignorant of *why*
## items are added/removed — occult tools and (later) rituals drive consume/produce.

signal item_added(item_id: String, count: int)
signal item_removed(item_id: String, count: int)
signal item_used(item_id: String)

var _counts: Dictionary = {}  # item_id -> int

func clear() -> void:
	_counts.clear()

func count_of(item_id: String) -> int:
	return int(_counts.get(item_id, 0))

func has(item_id: String, count: int = 1) -> bool:
	return count_of(item_id) >= count

## Add `count` of an item, respecting stackable/max_stack. Returns false (and adds
## nothing) if the resulting count would exceed the item's cap.
func add(item_id: String, count: int = 1) -> bool:
	if count <= 0:
		return false
	var def: ItemDef = ItemDB.get_def(item_id)
	if def == null:
		push_warning("Inventory.add: unknown item '%s'" % item_id)
		return false
	var cap: int = def.max_stack if def.stackable else 1
	var current: int = count_of(item_id)
	if current + count > cap:
		return false
	_counts[item_id] = current + count
	item_added.emit(item_id, count)
	return true

## Remove `count` of an item. Returns false (and removes nothing) if not enough held.
func remove(item_id: String, count: int = 1) -> bool:
	if count <= 0:
		return false
	if count_of(item_id) < count:
		return false
	var left: int = count_of(item_id) - count
	if left <= 0:
		_counts.erase(item_id)
	else:
		_counts[item_id] = left
	item_removed.emit(item_id, count)
	return true

## Use one of an item. Applies its declarative `on_use` effect (if any) and consumes
## one unit when the item is a consumable. Returns false if the item is not held.
## "Consumable" = stackable item that carries an on_use effect (food, reagents); a
## non-stackable tool/focus is reusable and never decremented by use().
func use(item_id: String) -> bool:
	if not has(item_id):
		return false
	var def: ItemDef = ItemDB.get_def(item_id)
	if def == null:
		return false
	_apply_on_use(def)
	item_used.emit(item_id)
	if def.stackable and not def.on_use.is_empty():
		remove(item_id, 1)
	return true

func _apply_on_use(def: ItemDef) -> void:
	if def.on_use.is_empty():
		return
	match String(def.on_use.get("effect", "")):
		"adjust_pressure":
			var pv := StringName(String(def.on_use.get("var", "")))
			WorldState.adjust(pv, float(def.on_use.get("delta", 0.0)))
		_:
			push_warning("Inventory.use: unknown on_use effect '%s' for '%s'" % [def.on_use.get("effect", ""), def.id])

## For UI: [{ id, count, def }] for every held item.
func items() -> Array:
	var out: Array = []
	for id in _counts.keys():
		out.append({ "id": id, "count": int(_counts[id]), "def": ItemDB.get_def(id) })
	return out

func to_dict() -> Dictionary:
	return { "counts": _counts.duplicate(true) }

func from_dict(d: Dictionary) -> void:
	_counts.clear()
	var c: Dictionary = d.get("counts", {})
	for id in c.keys():
		_counts[String(id)] = int(c[id])
