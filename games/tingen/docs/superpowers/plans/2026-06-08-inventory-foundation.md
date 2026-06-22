# Inventory Foundation Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a general, data-driven player inventory — item definitions, runtime stacks, add/remove/use, consume/produce, and save/load — that powers occult-tool costs and (later) sabotage. The ritual *engine* is out of scope; this only seeds the ingredient taxonomy.

**Architecture:** Two new autoloads + one data class, following the existing autoload + JSON pattern. `ItemDef` (RefCounted) wraps one JSON entry. `ItemDB` (autoload) loads `data/items.json` into `{id -> ItemDef}` for read-only lookup. `Inventory` (autoload) holds runtime counts `{id -> count}`, enforces stacking, applies declarative `on_use` effects, and persists through `SaveManager`. Inventory is ignorant of *why* items are consumed/produced — other systems call `has/remove/add`.

**Tech Stack:** Godot 4.6, GDScript, autoload singletons, JSON data files, the headless `SceneTree` test runner (`tingen/tests/run_tests.gd`).

**Source spec:** `docs/superpowers/specs/2026-06-08-inventory-system-design.md`.

---

## Conventions

- **Godot project root:** `Tingen-Game/tingen/`; `res://` paths are relative to it. Run commands from `Tingen-Game/`.
- **Run the suite:** `godot --headless --path tingen -s tests/run_tests.gd` (substitute your Godot binary name if needed). Success tail: `=== N passed, 0 failed ===`, exit 0.
- **Test pattern:** the runner is one `SceneTree` script. Each feature gets a `func _test_xxx()` using `_ok(cond, label)`, called inside `_init()` just above the final `print(...)` line.

## File Structure

- **Create** `tingen/src/ItemDef.gd` — `class_name ItemDef` (RefCounted). One job: typed view over one item JSON entry.
- **Create** `tingen/src/ItemDB.gd` — autoload `ItemDB`. One job: load `items.json`, expose `get_def(id)` / `has_def(id)`.
- **Create** `tingen/data/items.json` — the seed item set.
- **Create** `tingen/src/Inventory.gd` — autoload `Inventory`. One job: runtime holdings, add/remove/use, save/load.
- **Modify** `tingen/project.godot` — register `ItemDB` then `Inventory` after `ClueDB`.
- **Modify** `tingen/src/SaveManager.gd` — persist `Inventory`.
- **Modify** `tingen/tests/run_tests.gd` — add tests.

---

## Task 1: ItemDef + ItemDB (load item definitions)

**Files:**
- Create: `tingen/src/ItemDef.gd`
- Create: `tingen/src/ItemDB.gd`
- Create: `tingen/data/items.json`
- Modify: `tingen/project.godot`
- Test: `tingen/tests/run_tests.gd`

- [ ] **Step 1: Write the failing test**

In `tingen/tests/run_tests.gd`, add:

```gdscript
func _test_item_db() -> void:
	print("[item db]")
	var DB: Object = root.get_node("/root/ItemDB")
	_ok(DB.has_def("rye_bread"), "items.json loaded rye_bread")
	var d: ItemDef = DB.get_def("rye_bread")
	_ok(d != null, "get_def returns an ItemDef")
	_ok(d.category == "sustenance", "rye_bread is sustenance")
	_ok(d.stackable == true, "rye_bread is stackable")
	_ok(d.max_stack == 5, "rye_bread max_stack is 5")
	var pen: ItemDef = DB.get_def("spirit_pendulum")
	_ok(pen.stackable == false, "spirit_pendulum is not stackable")
	_ok(DB.get_def("does_not_exist") == null, "unknown id returns null")
```

Register in `_init()` above the final `print(...)`:

```gdscript
	_test_item_db()

	print("\n=== %d passed, %d failed ===" % [_passed, _failed])
```

- [ ] **Step 2: Run the suite to verify it fails**

Run: `godot --headless --path tingen -s tests/run_tests.gd`
Expected: parse/identifier error — `ItemDef` not defined and `/root/ItemDB` unresolved.

- [ ] **Step 3: Create ItemDef.gd**

Create `tingen/src/ItemDef.gd`:

```gdscript
class_name ItemDef
extends RefCounted
## Typed, read-only view over one entry in data/items.json. Plain data; no behavior
## beyond exposing the declarative `on_use` effect for the Inventory to apply.

const KNOWN_CATEGORIES: Array = [
	"occult_tool", "divination_focus", "ingredient", "characteristic",
	"medium", "sustenance", "tool", "key_item",
]

var id: String = ""
var name: String = ""
var category: String = "tool"
var stackable: bool = false
var max_stack: int = 1
var tags: Array = []
var description: String = ""
var on_use: Dictionary = {}   # empty = no effect

static func from_json(d: Dictionary) -> ItemDef:
	var it := ItemDef.new()
	it.id = String(d.get("id", ""))
	it.name = String(d.get("name", it.id))
	it.category = String(d.get("category", "tool"))
	if not KNOWN_CATEGORIES.has(it.category):
		push_warning("ItemDef: unknown category '%s' for item '%s'" % [it.category, it.id])
	it.stackable = bool(d.get("stackable", false))
	it.max_stack = maxi(1, int(d.get("max_stack", 1)))
	it.tags = (d.get("tags", []) as Array).duplicate()
	it.description = String(d.get("description", ""))
	var ou: Variant = d.get("on_use", null)
	it.on_use = (ou as Dictionary).duplicate(true) if typeof(ou) == TYPE_DICTIONARY else {}
	return it
```

Create `tingen/data/items.json`:

```json
[
	{
		"id": "spirit_pendulum",
		"name": "Spirit Pendulum",
		"category": "divination_focus",
		"stackable": false,
		"max_stack": 1,
		"tags": ["divination", "focus", "reusable"],
		"description": "A brass plumb on a fine chain; it leans toward what the spirit world notices.",
		"on_use": null
	},
	{
		"id": "divination_kit",
		"name": "Divination Kit",
		"category": "occult_tool",
		"stackable": false,
		"max_stack": 1,
		"tags": ["divination", "tool"],
		"description": "Cards, chalk, and a steady hand for reading the city's drift.",
		"on_use": null
	},
	{
		"id": "spirit_lens",
		"name": "Spirit Lens",
		"category": "occult_tool",
		"stackable": false,
		"max_stack": 1,
		"tags": ["residue", "tool"],
		"description": "A smoked glass that shows what lingers where a thing once happened.",
		"on_use": null
	},
	{
		"id": "dream_draught",
		"name": "Dream Draught",
		"category": "occult_tool",
		"stackable": false,
		"max_stack": 1,
		"tags": ["dream", "tool"],
		"description": "A bitter tincture that lets sleep do the connecting.",
		"on_use": null
	},
	{
		"id": "gray_fog_focus",
		"name": "Gray-Fog Focus",
		"category": "occult_tool",
		"stackable": false,
		"max_stack": 1,
		"tags": ["gray_fog", "tool"],
		"description": "A focus that briefly steadies a corner of the Gray Fog for reading.",
		"on_use": null
	},
	{
		"id": "consecrated_chalk",
		"name": "Consecrated Chalk",
		"category": "ingredient",
		"stackable": true,
		"max_stack": 9,
		"tags": ["ritual", "marking"],
		"description": "For drawing a ritual circle that holds its shape against the Gray Fog.",
		"on_use": null
	},
	{
		"id": "candle",
		"name": "Tallow Candle",
		"category": "ingredient",
		"stackable": true,
		"max_stack": 9,
		"tags": ["ritual", "light"],
		"description": "Cheap, smoky, and necessary for the smallest divinations.",
		"on_use": null
	},
	{
		"id": "dream_herb",
		"name": "Dream Herb",
		"category": "ingredient",
		"stackable": true,
		"max_stack": 9,
		"tags": ["ritual", "dream"],
		"description": "Dried gray leaves that thin the wall between waking and sleep.",
		"on_use": null
	},
	{
		"id": "dream_residue",
		"name": "Dream Residue",
		"category": "ingredient",
		"stackable": true,
		"max_stack": 9,
		"tags": ["ritual", "byproduct"],
		"description": "A faint condensate left after a dream-reading; still potent.",
		"on_use": null
	},
	{
		"id": "ritual_salt",
		"name": "Ritual Salt",
		"category": "ingredient",
		"stackable": true,
		"max_stack": 9,
		"tags": ["ritual", "summoning"],
		"description": "Coarse gray salt the cell hoards for the warehouse circle.",
		"on_use": null
	},
	{
		"id": "rye_bread",
		"name": "Rye Bread",
		"category": "sustenance",
		"stackable": true,
		"max_stack": 5,
		"tags": ["food"],
		"description": "Dense, sour, filling.",
		"on_use": { "effect": "adjust_pressure", "var": "fatigue", "delta": -12.0 }
	}
]
```

Create `tingen/src/ItemDB.gd`:

```gdscript
extends Node
## Item definitions (autoload singleton `ItemDB`). Loads data/items.json once into
## an id -> ItemDef map for read-only lookup. Definitions are static content; they are
## never saved (the Inventory saves only counts and re-resolves defs from here).

const ITEMS_PATH: String = "res://data/items.json"

var _defs: Dictionary = {}  # id -> ItemDef

func _ready() -> void:
	_load()

func _load() -> void:
	if not FileAccess.file_exists(ITEMS_PATH):
		push_error("ItemDB: missing %s" % ITEMS_PATH)
		return
	var parsed: Variant = JSON.parse_string(FileAccess.get_file_as_string(ITEMS_PATH))
	if typeof(parsed) != TYPE_ARRAY:
		push_error("ItemDB: %s is not a JSON array" % ITEMS_PATH)
		return
	for entry in parsed:
		if typeof(entry) != TYPE_DICTIONARY:
			continue
		var it: ItemDef = ItemDef.from_json(entry)
		if it.id == "":
			push_warning("ItemDB: item with no id skipped")
			continue
		_defs[it.id] = it

func has_def(id: String) -> bool:
	return _defs.has(id)

func get_def(id: String) -> ItemDef:
	return _defs.get(id, null)

func all_ids() -> Array:
	return _defs.keys()
```

Register both autoloads in `tingen/project.godot` — in the `[autoload]` block, add these two lines right after the `ClueDB` line (before `NpcDB`):

```
ClueDB="*res://src/ClueDB.gd"
ItemDB="*res://src/ItemDB.gd"
Inventory="*res://src/Inventory.gd"
NpcDB="*res://src/NpcDB.gd"
```

> Note: `Inventory` is registered now (so ordering is correct) even though `Inventory.gd` is created in Task 3. If you run the suite between Task 1 and Task 3 it will error on the missing `Inventory.gd` file — that is expected; Task 3 creates it. To keep Task 1 runnable on its own, you may temporarily omit the `Inventory` line and add it in Task 3; either way the final state has both lines.

- [ ] **Step 4: Run the suite to verify it passes**

Run: `godot --headless --path tingen -s tests/run_tests.gd`
Expected: `[item db]` shows seven PASS lines; suite exits 0.

- [ ] **Step 5: Commit**

```bash
git add tingen/src/ItemDef.gd tingen/src/ItemDB.gd tingen/data/items.json tingen/project.godot tingen/tests/run_tests.gd
git commit -m "feat(items): ItemDef + ItemDB autoload loading data/items.json"
```

---

## Task 2: Inventory add / stack / remove / has

**Files:**
- Create: `tingen/src/Inventory.gd`
- Modify: `tingen/project.godot` (only if you deferred the `Inventory` line in Task 1)
- Test: `tingen/tests/run_tests.gd`

- [ ] **Step 1: Write the failing test**

In `tingen/tests/run_tests.gd`, add:

```gdscript
func _test_inventory_add_remove() -> void:
	print("[inventory add/remove]")
	var INV: Object = root.get_node("/root/Inventory")
	INV.clear()
	_ok(INV.add("candle", 3), "add 3 candles succeeds")
	_ok(INV.count_of("candle") == 3, "count is 3")
	_ok(INV.add("candle", 100) == false, "add past max_stack (9) is rejected")
	_ok(INV.count_of("candle") == 3, "count unchanged after rejected add")
	_ok(INV.add("spirit_pendulum"), "add non-stackable succeeds")
	_ok(INV.add("spirit_pendulum") == false, "second non-stackable add rejected (cap 1)")
	_ok(INV.has("candle", 3), "has(candle,3) true")
	_ok(INV.has("candle", 4) == false, "has(candle,4) false")
	_ok(INV.remove("candle", 2), "remove 2 candles succeeds")
	_ok(INV.count_of("candle") == 1, "count is 1 after remove")
	_ok(INV.remove("candle", 5) == false, "remove more than held is rejected")
	_ok(INV.count_of("candle") == 1, "count unchanged after rejected remove")
```

Register in `_init()` above the final `print(...)`:

```gdscript
	_test_inventory_add_remove()

	print("\n=== %d passed, %d failed ===" % [_passed, _failed])
```

- [ ] **Step 2: Run the suite to verify it fails**

Run: `godot --headless --path tingen -s tests/run_tests.gd`
Expected: failure resolving `/root/Inventory` (autoload/file missing).

- [ ] **Step 3: Create Inventory.gd**

Create `tingen/src/Inventory.gd`:

```gdscript
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
```

If you deferred the `Inventory` autoload line in Task 1, add it now in `tingen/project.godot` right after the `ItemDB` line:

```
ItemDB="*res://src/ItemDB.gd"
Inventory="*res://src/Inventory.gd"
```

- [ ] **Step 4: Run the suite to verify it passes**

Run: `godot --headless --path tingen -s tests/run_tests.gd`
Expected: `[inventory add/remove]` shows eleven PASS lines; suite exits 0.

- [ ] **Step 5: Commit**

```bash
git add tingen/src/Inventory.gd tingen/project.godot tingen/tests/run_tests.gd
git commit -m "feat(inventory): runtime holdings with stacking add/remove/has"
```

---

## Task 3: Inventory.use (declarative on_use + consumable decrement)

**Files:**
- Modify: `tingen/src/Inventory.gd`
- Test: `tingen/tests/run_tests.gd`

- [ ] **Step 1: Write the failing test**

In `tingen/tests/run_tests.gd`, add:

```gdscript
func _test_inventory_use() -> void:
	print("[inventory use]")
	var INV: Object = root.get_node("/root/Inventory")
	var WS: Object = root.get_node("/root/WorldState")
	INV.clear()
	WS.set_pressure(&"fatigue", 50.0)
	INV.add("rye_bread", 2)
	_ok(INV.use("rye_bread"), "use rye_bread succeeds")
	_ok(abs(WS.get_pressure(&"fatigue") - 38.0) < 0.01, "fatigue dropped by on_use delta (12)")
	_ok(INV.count_of("rye_bread") == 1, "consumable decremented by 1")
	# Non-consumable (no on_use): use does not decrement.
	INV.add("spirit_pendulum")
	_ok(INV.use("spirit_pendulum"), "use non-consumable returns true")
	_ok(INV.count_of("spirit_pendulum") == 1, "non-consumable not decremented")
	# Unknown effect: warns, no-ops, still treated as used (not consumed by default).
	INV.clear()
	_ok(INV.use("candle") == false, "use of unheld item returns false")
```

Register in `_init()` above the final `print(...)`:

```gdscript
	_test_inventory_use()

	print("\n=== %d passed, %d failed ===" % [_passed, _failed])
```

- [ ] **Step 2: Run the suite to verify it fails**

Run: `godot --headless --path tingen -s tests/run_tests.gd`
Expected: `[inventory use]` FAILs — `use()` not defined yet (method missing).

- [ ] **Step 3: Add use() to Inventory.gd**

In `tingen/src/Inventory.gd`, add this method (e.g. after `remove`):

```gdscript
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
```

- [ ] **Step 4: Run the suite to verify it passes**

Run: `godot --headless --path tingen -s tests/run_tests.gd`
Expected: `[inventory use]` shows five PASS lines; suite exits 0.

- [ ] **Step 5: Commit**

```bash
git add tingen/src/Inventory.gd tingen/tests/run_tests.gd
git commit -m "feat(inventory): use() applies on_use effect, consumes consumables"
```

---

## Task 4: Persist Inventory through SaveManager

**Files:**
- Modify: `tingen/src/SaveManager.gd`
- Test: `tingen/tests/run_tests.gd`

- [ ] **Step 1: Write the failing test**

In `tingen/tests/run_tests.gd`, add:

```gdscript
func _test_inventory_save_load() -> void:
	print("[inventory save/load]")
	var INV: Object = root.get_node("/root/Inventory")
	var SM: Object = root.get_node("/root/SaveManager")
	INV.clear()
	INV.add("candle", 4)
	INV.add("spirit_pendulum")
	var tmp := "user://test_inventory.json"
	_ok(SM.save_game(tmp), "save_game writes file")
	INV.clear()
	_ok(INV.count_of("candle") == 0, "inventory cleared before load")
	_ok(SM.load_game(tmp), "load_game reads file")
	_ok(INV.count_of("candle") == 4, "candle count restored")
	_ok(INV.has("spirit_pendulum"), "pendulum restored")
	DirAccess.remove_absolute(ProjectSettings.globalize_path(tmp))
```

Register in `_init()` above the final `print(...)`:

```gdscript
	_test_inventory_save_load()

	print("\n=== %d passed, %d failed ===" % [_passed, _failed])
```

- [ ] **Step 2: Run the suite to verify it fails**

Run: `godot --headless --path tingen -s tests/run_tests.gd`
Expected: `[inventory save/load]` FAILs at "candle count restored" — the save payload doesn't include inventory yet, so load leaves it cleared.

- [ ] **Step 3: Add the inventory key to SaveManager**

In `tingen/src/SaveManager.gd`, in `save_game()`, add one entry to the `data` dictionary (after the `"clues": ClueDB.to_dict(),` line):

```gdscript
		"clues": ClueDB.to_dict(),
		"inventory": Inventory.to_dict(),
		"scene_path": gc.current_scene_path if gc else "",
```

In `load_game()`, add a restore call in the "Restore data-only subsystems first" block (after the `WorldState.from_dict(...)` line):

```gdscript
	WorldState.from_dict(data.get("world_state", {}))
	Inventory.from_dict(data.get("inventory", {}))
```

> If Plan 1 already added `event_bus`/`agents` keys here, just place `inventory` alongside them — order among the data-only restores doesn't matter.

- [ ] **Step 4: Run the suite to verify it passes**

Run: `godot --headless --path tingen -s tests/run_tests.gd`
Expected: `[inventory save/load]` shows five PASS lines; full suite ends `=== N passed, 0 failed ===`, exit 0.

- [ ] **Step 5: Commit**

```bash
git add tingen/src/SaveManager.gd tingen/tests/run_tests.gd
git commit -m "feat(save): persist Inventory counts in the save payload"
```

---

## Done criteria for this plan

- Full headless suite passes and includes: item db, inventory add/remove, inventory use, inventory save/load.
- `ItemDB` + `Inventory` are registered autoloads loaded after `ClueDB`.
- `data/items.json` seeds the occult tools, ritual ingredients (incl. `ritual_salt` for sabotage), and `rye_bread`.
- Inventory enforces stacking, applies `on_use` (food → fatigue), and round-trips through save/load.

## What this plan deliberately does NOT do (later plans)

- No ritual engine, crafting, shops, carry-weight, or multi-stack UI.
- No occult-tool behavior — tools are present only as `occult_tool` items the player owns; their `use()` logic is Plan 6.
- No inventory UI scene — the foundation is headless/logic only; a panel comes with the player-verbs/UI plan.
- No item acquisition wiring on Interactables/events yet — Plan 6 wires sabotage/pickup against this API.
