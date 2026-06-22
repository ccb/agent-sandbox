# Inventory System — Design Spec (Foundation)

**Date:** 2026-06-08
**Status:** Approved design, ready for implementation planning
**Engine:** Godot 4.6 (GDScript, autoload singletons + data-driven JSON)
**Scope:** A general, data-driven player inventory: item definitions, runtime stacks,
add/remove/use, consume/produce, and save/load. **The ritual *engine* is out of scope** —
this spec only seeds the ritual-ready *ingredient taxonomy*. Occult-tool integration lives
in the companion spec (`2026-06-06-occult-tools-hypothesis-board-design.md`).

---

## 1. Intent

The GDD (§34.1 "inventory/tool UI", §22.4 "must persist … clue inventory") assumes a player
inventory; none exists yet (only `ClueDB` for clues). Build a foundation that:
- treats the four occult tools as **items**,
- lets tools/actions **consume** reagents and **produce** items,
- gives **food/water** a mechanical purpose (eases the `fatigue` pressure),
- is **ritual-ready** — the ingredient categories anticipate the later ritual engine
  (divination, potion-brewing, séance, prayer, gray-fog transit, summoning, warding)
  without building it now.

Grounding: item categories are drawn from LotM canon — Seer (占卜家) divination uses
foci like the spirit pendulum (灵摆), tarot/cartomancy, dowsing rod (探寻杖), scrying mirror;
potions (魔药) need a main Beyonder Characteristic (魔药特性) + supplementary materials;
prayer (祈祷) and Ritualistic Magic (仪式魔法) are step-based acts. (LotM wiki: Seer powers,
Potion System, Pathways.)

---

## 2. Architecture

| Unit | Kind | Responsibility |
|------|------|----------------|
| `Inventory` | autoload | Runtime holdings `{ item_id -> count }`; add/remove/use/has; emits signals; `to_dict()/from_dict()`. Stateless about *what* items mean beyond their def. |
| `ItemDB` | autoload (or a small static loader) | Loads `data/items.json` into `{ id -> ItemDef }`; read-only lookup of definitions. |
| `ItemDef` | `class_name`, plain data (RefCounted/Resource) | Typed wrapper over one JSON entry: `id, name, category, stackable, max_stack, tags, description, on_use`. |

Register in `project.godot` `[autoload]` after `ClueDB` (so it loads alongside the other
content DBs), before `WorldManager`:
```
ItemDB="*res://src/ItemDB.gd"
Inventory="*res://src/Inventory.gd"
```

**Why a separate `Inventory` from `ClueDB`:** clues are *knowledge* (collected once, never
consumed, drive dialogue/topics); items are *goods* (stack, get consumed, get produced). Same
`to_dict()/from_dict()` contract, different semantics. Keeping them separate avoids
overloading `ClueDB` and matches the GDD listing them as distinct ("clue inventory" vs
"inventory/tool UI").

---

## 3. Data model — `data/items.json`

Array of item defs. Example:

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

### 3.1 Categories (LotM-grounded)

| Category | Purpose | Stack? | Examples |
|----------|---------|--------|----------|
| `occult_tool` | the four tools (and future) live here as items | no | divination kit, spirit lens, dream draught, gray-fog focus |
| `divination_focus` | reusable foci for fortune-telling (Seer methods) | no | spirit pendulum, tarot deck, dowsing rod, scrying mirror |
| `ingredient` | consumed ritual reagents | yes | consecrated chalk, candles, salt, incense, herbs, monster-parts |
| `characteristic` | rare potion main material (魔药特性) | yes (rarely >1) | a Beyonder Characteristic |
| `medium` | targets a person/site for divination & séance | yes | a belonging, name slip, relic, corpse-token |
| `sustenance` | eases the `fatigue` pressure | yes | rye bread, water, coffee |
| `tool` | mundane gear | no (mostly) | lantern, lockpick |
| `key_item` | story / sealed artifacts | no | sealed artifacts |

`category` is a free string validated against this known set at load (warn on unknown, don't
crash) so future categories are cheap to add.

### 3.2 `on_use` (optional)
A small declarative effect so simple consumables work without bespoke code. Supported now:
- `{ "effect": "adjust_pressure", "var": "<pressure>", "delta": <float> }` → calls
  `WorldState.adjust(var, delta)` (food → fatigue). Unknown effects warn and no-op.

Anything more complex (a tool's actual behavior, a ritual) is **not** done through `on_use` —
that lives in code (occult tools) or the future ritual engine.

---

## 4. `Inventory` API

```
signal item_added(item_id: String, count: int)
signal item_removed(item_id: String, count: int)
signal item_used(item_id: String)

func add(item_id: String, count := 1) -> bool          # respects stackable/max_stack
func remove(item_id: String, count := 1) -> bool        # false if not enough
func has(item_id: String, count := 1) -> bool
func count_of(item_id: String) -> int
func use(item_id: String) -> bool                       # applies on_use, consumes 1 if consumable
func items() -> Array                                   # [{id, count, def}], for UI
func to_dict() -> Dictionary
func from_dict(d: Dictionary) -> void
```

- **Stacking:** `stackable:false` items cap at 1; stackable items cap at `max_stack`
  (overflow rejected or split across "stacks" — for the foundation, a single count capped at
  `max_stack`, extra add returns false; revisit if multi-stack UI is wanted).
- **Consume/produce contract used by other systems:** occult tools and (later) rituals call
  `Inventory.has(...)` to gate, `Inventory.remove(...)` to consume ingredients, and
  `Inventory.add(...)` to produce outputs. The inventory itself stays ignorant of *why*.

---

## 5. Acquisition (how items enter inventory)

Foundation supports two sources; richer economy (shops, NPC trade) deferred:
1. **Interactables** — a scene Interactable may carry `gives_item_id` (+ optional count);
   interacting adds it to `Inventory` (parallel to how examine adds a clue to `ClueDB`). An
   Interactable can give a clue, an item, or both.
2. **Event rewards** — `EventManager` events may grant items via the same `Inventory.add`.

(No starting-loadout design here beyond a small seed list for testing; balancing is later.)

---

## 6. Save / load

- `Inventory.to_dict()/from_dict()` persists `{ item_id -> count }`.
- Added to `SaveManager`'s payload under an `inventory` key and to its load path, following
  the existing `to_dict()/from_dict()` contract used by every subsystem. (Item *defs* are not
  saved — re-loaded from `items.json`.)

---

## 7. UI

- Minimal for the foundation: an inventory view reachable from the existing panel system
  (suggest input action `toggle_inventory`, **I** key), listing items grouped by category with
  count + description, and a "use" affordance for consumables. Mirrors `DistrictMap.tscn` /
  HUD conventions (a `Control` scene, signal-driven refresh on `item_added/removed`).
- Full drag-and-drop / tool-UI polish (GDD §34.2) is deferred.

---

## 8. Tests (headless, extend `tingen/tests/run_tests.gd`)

1. **Add/stack** — adding past `max_stack` is rejected; non-stackable caps at 1.
2. **Remove/has** — `remove` fails when count insufficient; `has(id, n)` correct.
3. **Use consumable** — using `rye_bread` lowers `fatigue` by its `on_use.delta` and
   decrements the count by 1.
4. **Use non-consumable** — using a `divination_focus` does not decrement it.
5. **Save/load round-trip** — `to_dict()`→`from_dict()` restores counts exactly.
6. **Unknown category/effect** — loads with a warning, does not crash.

---

## 9. Out of scope (later specs)

- The **ritual engine** (recipes, advancement rituals, séance, prayer, gray-fog transit,
  summoning). This spec only provides the ingredient/medium/characteristic/focus categories
  those rituals will draw on.
- Crafting, shops/economy, carry-weight/encumbrance, multi-stack UI, drag-and-drop polish.
- The endgame summoning ritual (cult side) — that's the Ritual-Night spec.

---

## 10. Decision references

Logged in `DESIGN_DECISIONS.md` → Occult/Inventory decision log: build a general data-driven
inventory; inventory foundation now / ritual engine later; unlimited capacity with stacking
reagents; the LotM-grounded category taxonomy; rituals as the deferred unifying primitive.
