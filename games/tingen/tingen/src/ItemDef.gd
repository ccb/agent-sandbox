class_name ItemDef
extends RefCounted
## Typed, read-only view over one entry in data/items.json. Plain data; no behavior
## beyond exposing the declarative `on_use` effect for the Inventory to apply.

const KNOWN_CATEGORIES: Array = [
	"occult_tool", "divination_focus", "ingredient", "characteristic",
	"medium", "sustenance", "tool", "key_item", "weapon", "ammo",
]

var id: String = ""
var name: String = ""
var category: String = "tool"
var stackable: bool = false
var max_stack: int = 1
var tags: Array = []
var description: String = ""
var on_use: Dictionary = {}   # empty = no effect
## Weapon/tool combat wiring (category "weapon"): the ability ids a CARRIED copy of this
## item grants, and the item id its `ammo` cost consumes from the carrier's inventory.
## The executor cost seam resolves `ammo` through these — never through a built-in pool.
var grants: Array = []        # ability ids (Strings)
var ammo_item: String = ""    # "" = the weapon costs no ammo

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
	# Shape-guarded (a String where an Array belongs degrades to empty, never hard-errors).
	var g: Variant = d.get("grants", [])
	it.grants = (g as Array).duplicate() if g is Array else []
	it.ammo_item = String(d.get("ammo_item", ""))
	return it
