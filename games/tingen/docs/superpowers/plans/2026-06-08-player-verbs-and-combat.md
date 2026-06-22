# Player Verbs + Combat Climax Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Give the player teeth. Occult tools become perception verbs that yield directional leads (never naming the site). `sabotage` strips the cell's ingredients and `social_influence` turns the waverer — both feed a hidden **impede** score that, together with the cell's remaining ingredients, sets the summoning's strength. A minimal deterministic combat resolver scales the climax to that strength. All headless-testable, no LLM.

**Architecture:** `SummoningPlan` (autoload) owns the cult's countdown, ingredient stock, and impede score, and derives `manifestation_strength()`. The occult toolkit is the surviving OOP hierarchy from the occult spec — `OccultTool` base (template `use()`), four subclasses, `OccultToolManager` (seeded RNG, roster, gating), `OccultRisk` (seeded primitives) — demoted to emit directional leads via `WorldState.set_lead`. `PlayerActions` (autoload) exposes `sabotage` and `social_influence` as first-class `EventBus` events (so the overseer reacts to the player exactly like an agent). `CombatEncounter` (class) resolves the climax against `manifestation_strength()`. `SaveManager` persists the new state.

**Tech Stack:** Godot 4.6, GDScript, autoloads + `class_name` libs, seeded RNG, headless `SceneTree` test runner.

**Depends on:** Plans 1–5 (`EventBus`, `Agents`, `WorldState`, `WorldManager`, `Inventory`/`ItemDB`, `Overseer`).

**Source specs:** vertical-slice §E/§F/§5; occult-tools spec §2/§5/§8 (board parts cut).

---

## Conventions

- **Godot project root:** `Tingen-Game/tingen/`. Run from `Tingen-Game/`.
- **Run the suite:** `godot --headless --path tingen -s tests/run_tests.gd`. Success tail: `=== N passed, 0 failed ===`, exit 0.
- **Test pattern:** one `SceneTree` script; each feature gets `func _test_xxx()` using `_ok(cond, label)`, called in `_init()` above the final `print(...)`.

## File Structure

- **Create** `tingen/src/SummoningPlan.gd` — autoload `SummoningPlan`. One job: countdown + ingredient stock + impede → manifestation strength.
- **Create** `tingen/src/OccultRisk.gd` — `class_name OccultRisk`. One job: seeded mislead/noise primitives.
- **Create** `tingen/src/OccultTool.gd` — `class_name OccultTool`. One job: abstract tool (template `use()`, cost, gating).
- **Create** `tingen/src/DivinationTool.gd`, `ResidueSightTool.gd`, `DreamFragmentsTool.gd`, `GrayFogTool.gd` — the four subclasses.
- **Create** `tingen/src/OccultToolManager.gd` — autoload `OccultToolManager`. One job: roster, seeded RNG, gating, routing.
- **Create** `tingen/data/occult_tools.json` — per-tool cost/cooldown/uses.
- **Create** `tingen/src/PlayerActions.gd` — autoload `PlayerActions`. One job: sabotage + social_influence verbs.
- **Create** `tingen/src/CombatEncounter.gd` — `class_name CombatEncounter`. One job: deterministic climax resolution.
- **Modify** `tingen/project.godot` — register `SummoningPlan`, `OccultToolManager`, `PlayerActions`.
- **Modify** `tingen/src/SaveManager.gd` — persist the new state.
- **Modify** `tingen/tests/run_tests.gd` — add tests.

---

## Task 1: SummoningPlan (countdown + impede → strength)

**Files:**
- Create: `tingen/src/SummoningPlan.gd`
- Modify: `tingen/project.godot`
- Test: `tingen/tests/run_tests.gd`

- [ ] **Step 1: Write the failing test**

In `tingen/tests/run_tests.gd`, add:

```gdscript
func _test_summoning_plan() -> void:
	print("[summoning plan]")
	var SP: Object = root.get_node("/root/SummoningPlan")
	SP.reset()
	var base: float = SP.manifestation_strength()
	# Impede weakens the manifestation.
	SP.add_impede(20.0, "test")
	_ok(SP.manifestation_strength() < base, "impede lowers manifestation strength")
	_ok(SP.impede_score == 20.0, "impede accumulates")
	# Removing an ingredient weakens it further AND sets back the countdown.
	var cd_before: int = SP.countdown_beats
	var strength_before: float = SP.manifestation_strength()
	_ok(SP.remove_ingredient("ritual_salt", 1), "ritual_salt removed from cult stock")
	_ok(SP.manifestation_strength() < strength_before, "fewer ingredients -> weaker")
	_ok(SP.countdown_beats > cd_before, "removing an ingredient sets back the countdown")
	# Removing more than held fails and changes nothing.
	var cd_now: int = SP.countdown_beats
	_ok(SP.remove_ingredient("ritual_salt", 999) == false, "cannot remove more than held")
	_ok(SP.countdown_beats == cd_now, "failed removal does not set back the countdown")
	# Strength is clamped to a floor.
	SP.add_impede(1000.0, "overkill")
	_ok(SP.manifestation_strength() >= SP.MIN_STRENGTH, "strength never drops below the floor")
```

Register in `_init()` above the final `print(...)`:

```gdscript
	_test_summoning_plan()

	print("\n=== %d passed, %d failed ===" % [_passed, _failed])
```

- [ ] **Step 2: Run the suite to verify it fails**

Run: `godot --headless --path tingen -s tests/run_tests.gd`
Expected: failure resolving `/root/SummoningPlan` (autoload missing).

- [ ] **Step 3: Create SummoningPlan.gd + register autoload**

Create `tingen/src/SummoningPlan.gd`:

```gdscript
extends Node
## The cult's summoning attempt (autoload `SummoningPlan`). Holds the beat countdown to
## the ritual, the cell's gathered ingredient stock, and the hidden `impede_score` that
## the player drives down through interference. `manifestation_strength()` combines the
## two: fewer ingredients and more impede mean a weaker descent (an easier climax). The
## score is never shown as a number — the player feels it through how the world reacts.

const BASE_STRENGTH: float = 100.0
const MIN_STRENGTH: float = 8.0
const COUNTDOWN_SETBACK_PER_INGREDIENT: int = 3

## Default countdown to the summoning, in beats.
var countdown_beats: int = 40
var impede_score: float = 0.0
## What the cell has gathered. Sabotage strips from here.
var ingredients: Dictionary = {"ritual_salt": 3, "consecrated_chalk": 2, "candle": 3}

var _initial_total: int = 8   # sum of starting ingredients, for the strength fraction

func reset() -> void:
	countdown_beats = 40
	impede_score = 0.0
	ingredients = {"ritual_salt": 3, "consecrated_chalk": 2, "candle": 3}
	_initial_total = _total_ingredients()

func _total_ingredients() -> int:
	var t := 0
	for k in ingredients.keys():
		t += int(ingredients[k])
	return t

func add_impede(amount: float, reason: String = "") -> void:
	impede_score += maxf(0.0, amount)

## Strip ingredients from the cell. Returns false if the cell doesn't hold that many.
## Success also sets the summoning back (the cell must re-gather).
func remove_ingredient(item_id: String, count: int = 1) -> bool:
	if int(ingredients.get(item_id, 0)) < count:
		return false
	ingredients[item_id] = int(ingredients[item_id]) - count
	if int(ingredients[item_id]) <= 0:
		ingredients.erase(item_id)
	countdown_beats += COUNTDOWN_SETBACK_PER_INGREDIENT * count
	return true

func add_ingredient(item_id: String, count: int = 1) -> void:
	ingredients[item_id] = int(ingredients.get(item_id, 0)) + count

## Strength of the descent at the climax. Scales with remaining-ingredient fraction,
## reduced by impede, clamped to [MIN_STRENGTH, BASE_STRENGTH].
func manifestation_strength() -> float:
	var frac: float = float(_total_ingredients()) / float(maxi(1, _initial_total))
	return clampf(BASE_STRENGTH * frac - impede_score, MIN_STRENGTH, BASE_STRENGTH)

func to_dict() -> Dictionary:
	return {
		"countdown_beats": countdown_beats,
		"impede_score": impede_score,
		"ingredients": ingredients.duplicate(true),
		"initial_total": _initial_total,
	}

func from_dict(d: Dictionary) -> void:
	countdown_beats = int(d.get("countdown_beats", 40))
	impede_score = float(d.get("impede_score", 0.0))
	ingredients = (d.get("ingredients", {}) as Dictionary).duplicate(true)
	_initial_total = int(d.get("initial_total", _total_ingredients()))
```

Register the autoload in `tingen/project.godot` — add `SummoningPlan` after `Overseer`:

```
Overseer="*res://src/Overseer.gd"
SummoningPlan="*res://src/SummoningPlan.gd"
EventManager="*res://src/EventManager.gd"
```

- [ ] **Step 4: Run the suite to verify it passes**

Run: `godot --headless --path tingen -s tests/run_tests.gd`
Expected: `[summoning plan]` shows nine PASS lines; suite exits 0.

- [ ] **Step 5: Commit**

```bash
git add tingen/src/SummoningPlan.gd tingen/project.godot tingen/tests/run_tests.gd
git commit -m "feat(summoning): countdown + impede -> manifestation strength"
```

---

## Task 2: Occult toolkit core + Divination (perception verb)

**Files:**
- Create: `tingen/src/OccultRisk.gd`
- Create: `tingen/src/OccultTool.gd`
- Create: `tingen/src/DivinationTool.gd`
- Create: `tingen/src/OccultToolManager.gd`
- Create: `tingen/data/occult_tools.json`
- Modify: `tingen/project.godot`
- Test: `tingen/tests/run_tests.gd`

- [ ] **Step 1: Write the failing test**

In `tingen/tests/run_tests.gd`, add:

```gdscript
func _test_occult_divination() -> void:
	print("[occult divination]")
	var OTM: Object = root.get_node("/root/OccultToolManager")
	var INV: Object = root.get_node("/root/Inventory")
	var WS: Object = root.get_node("/root/WorldState")
	OTM.rebuild()
	INV.clear()
	WS.set_pressure(&"fatigue", 0.0)
	WS.set_pressure(&"attention", 0.0)
	WS.set_pressure(&"corruption", 0.0)   # no mislead at zero corruption
	# Gating: cannot use without owning the kit + the candle ingredient.
	_ok(OTM.can_use("divination") == false, "divination blocked without tool item")
	INV.add("divination_kit")
	_ok(OTM.can_use("divination") == false, "divination blocked without candle ingredient")
	INV.add("candle", 1)
	_ok(OTM.can_use("divination") == true, "divination usable once kit + candle present")
	# Use: pays cost, consumes the candle, yields a directional lead.
	var res: Dictionary = OTM.use("divination")
	_ok(res.get("ok", false), "divination returns ok")
	_ok(String(res.get("lead", "")) != "", "divination yields a directional lead")
	_ok(WS.get_pressure(&"fatigue") > 0.0, "divination spent fatigue")
	_ok(INV.count_of("candle") == 0, "divination consumed the candle")
	# No-name guarantee: the lead never contains the true resolved site id.
	var true_site: String = String(WorldManager.slots.get("primary_ritual_site", ""))
	_ok(true_site == "" or not String(res["lead"]).contains(true_site), "lead never names the true site")
```

Register in `_init()` above the final `print(...)`:

```gdscript
	_test_occult_divination()

	print("\n=== %d passed, %d failed ===" % [_passed, _failed])
```

- [ ] **Step 2: Run the suite to verify it fails**

Run: `godot --headless --path tingen -s tests/run_tests.gd`
Expected: failure resolving `/root/OccultToolManager` (autoload missing) + `OccultTool` undefined.

- [ ] **Step 3: Create the occult core, Divination, manager, and data**

Create `tingen/data/occult_tools.json`:

```json
{
	"divination": {
		"name": "Divination",
		"item_id": "divination_kit",
		"fatigue_cost": 8.0,
		"attention_cost": 4.0,
		"ingredient_cost": { "candle": 1 },
		"uses_per_run": -1
	},
	"residue_sight": {
		"name": "Residue Sight",
		"item_id": "spirit_lens",
		"fatigue_cost": 6.0,
		"attention_cost": 2.0,
		"ingredient_cost": {},
		"uses_per_run": -1
	},
	"dream_fragments": {
		"name": "Dream Fragments",
		"item_id": "dream_draught",
		"fatigue_cost": 12.0,
		"attention_cost": 0.0,
		"ingredient_cost": { "dream_herb": 1 },
		"uses_per_run": -1,
		"produces": { "dream_residue": 1 }
	},
	"gray_fog": {
		"name": "Gray-Fog Reconstruction",
		"item_id": "gray_fog_focus",
		"fatigue_cost": 15.0,
		"attention_cost": 8.0,
		"ingredient_cost": { "consecrated_chalk": 1 },
		"uses_per_run": 3
	}
}
```

Create `tingen/src/OccultRisk.gd`:

```gdscript
class_name OccultRisk
extends RefCounted
## Seeded RNG primitives the occult tools call. Does NOT decide how risk manifests (each
## tool's _apply_risk does that) — it only rolls deterministically so tests are stable.

## True when this use should mislead. Probability rises with corruption above a floor.
static func roll_mislead(rng: RandomNumberGenerator, corruption: float) -> bool:
	if corruption <= 40.0:
		return false
	var p: float = clampf((corruption - 40.0) / 60.0, 0.0, 0.9)
	return rng.randf() < p

## Symmetric noise in [-magnitude, magnitude].
static func noise(rng: RandomNumberGenerator, magnitude: float) -> float:
	return (rng.randf() * 2.0 - 1.0) * magnitude
```

Create `tingen/src/OccultTool.gd`:

```gdscript
class_name OccultTool
extends RefCounted
## Abstract occult perception tool. `use()` is the fixed template: verify can_use, pay
## the cost (fatigue/attention via WorldState, ingredients via Inventory, plus any
## `produces`), call the subclass `_perform`, then `_apply_risk`. Subclasses override only
## `_perform` and `_apply_risk`. Result is a Dictionary:
##   { ok, kind, text, lead, mislead }.

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
	if item_id != "" and not Inventory.has(item_id):
		return false
	for ing in (def.get("ingredient_cost", {}) as Dictionary).keys():
		if not Inventory.has(String(ing), int(def["ingredient_cost"][ing])):
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
	WorldState.adjust(&"fatigue", float(cost["fatigue"]))
	WorldState.adjust(&"attention", float(cost["attention"]))
	for ing in (cost["items"] as Dictionary).keys():
		Inventory.remove(String(ing), int(cost["items"][ing]))
	for prod in (def.get("produces", {}) as Dictionary).keys():
		Inventory.add(String(prod), int(def["produces"][prod]))
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
```

Create `tingen/src/DivinationTool.gd`:

```gdscript
class_name DivinationTool
extends OccultTool
## Divination (占卜): a vague directional hint biased toward the district that actually
## holds the true primary_ritual_site — never the site's name. At high corruption the
## bias can flip to a wrong district (mislead).

## Site -> a directional line that does NOT contain the site id.
const SITE_HINTS: Dictionary = {
	"iron_cross_warehouse": "Cold iron and rust — look where cargo waits unclaimed.",
	"st_selena_crypt": "Old stone and older prayers — look beneath the cathedral.",
	"harbor_customs_house": "Salt and ledgers — look where the harbor counts its dead.",
}

func _perform() -> Dictionary:
	var true_site := String(WorldManager.slots.get("primary_ritual_site", "iron_cross_warehouse"))
	var lead := String(SITE_HINTS.get(true_site, "The city's drift is hard to read."))
	return {"ok": true, "kind": "divination", "text": lead, "lead": lead, "mislead": false}

func _apply_risk(result: Dictionary, rng: RandomNumberGenerator, corruption: float) -> void:
	if not OccultRisk.roll_mislead(rng, corruption):
		return
	# Mislead: point at a different site's hint.
	var true_site := String(WorldManager.slots.get("primary_ritual_site", ""))
	for site in SITE_HINTS.keys():
		if site != true_site:
			result["lead"] = String(SITE_HINTS[site])
			result["text"] = result["lead"]
			result["mislead"] = true
			return
```

Create `tingen/src/OccultToolManager.gd`:

```gdscript
extends Node
## Occult toolkit coordinator (autoload `OccultToolManager`). Builds the tool instances
## from data/occult_tools.json, owns the SEEDED RNG (from WorldManager.seed_value) so risk
## rolls are deterministic, gates/uses tools, and surfaces directional leads through
## WorldState. The only thing the HUD talks to.

const TOOLS_PATH: String = "res://data/occult_tools.json"

## Maps a tool id to its subclass script.
const TOOL_SCRIPTS: Dictionary = {
	"divination": "res://src/DivinationTool.gd",
	"residue_sight": "res://src/ResidueSightTool.gd",
	"dream_fragments": "res://src/DreamFragmentsTool.gd",
	"gray_fog": "res://src/GrayFogTool.gd",
}

var _tools: Dictionary = {}   # id -> OccultTool
var _rng := RandomNumberGenerator.new()

func _ready() -> void:
	rebuild()

func rebuild() -> void:
	_tools.clear()
	_rng.seed = WorldManager.seed_value
	if not FileAccess.file_exists(TOOLS_PATH):
		push_error("OccultToolManager: missing %s" % TOOLS_PATH)
		return
	var parsed: Variant = JSON.parse_string(FileAccess.get_file_as_string(TOOLS_PATH))
	if typeof(parsed) != TYPE_DICTIONARY:
		push_error("OccultToolManager: %s is not a JSON object" % TOOLS_PATH)
		return
	for id in parsed.keys():
		var script_path := String(TOOL_SCRIPTS.get(id, ""))
		if script_path == "" or not ResourceLoader.exists(script_path):
			continue
		var script: GDScript = load(script_path)
		_tools[id] = script.new(String(id), parsed[id])

func has_tool(id: String) -> bool:
	return _tools.has(id)

func can_use(id: String) -> bool:
	var t: OccultTool = _tools.get(id, null)
	return t != null and t.can_use()

## Use a tool; returns its result dict and surfaces any lead through WorldState.
func use(id: String) -> Dictionary:
	var t: OccultTool = _tools.get(id, null)
	if t == null:
		return {"ok": false, "kind": "unknown", "text": "No such tool.", "lead": "", "mislead": false}
	var res: Dictionary = t.use(_rng, WorldState.corruption)
	if res.get("ok", false) and String(res.get("lead", "")) != "":
		WorldState.set_lead(String(res["lead"]))
		EventBus.emit_event("player_occult", {"actor": "player", "tool": id, "mislead": res.get("mislead", false)})
	return res

func to_dict() -> Dictionary:
	var uses: Dictionary = {}
	for id in _tools.keys():
		uses[id] = (_tools[id] as OccultTool).uses_left
	return {"uses_left": uses}

func from_dict(d: Dictionary) -> void:
	var uses: Dictionary = d.get("uses_left", {})
	for id in uses.keys():
		if _tools.has(id):
			(_tools[id] as OccultTool).uses_left = int(uses[id])
```

> The three other subclass scripts referenced in `TOOL_SCRIPTS` are created in Task 3. Until then, `rebuild()` skips ids whose script doesn't exist (the `ResourceLoader.exists` guard), so Task 2 runs with only Divination present.

Register the autoload in `tingen/project.godot` — add `OccultToolManager` after `SummoningPlan`:

```
SummoningPlan="*res://src/SummoningPlan.gd"
OccultToolManager="*res://src/OccultToolManager.gd"
EventManager="*res://src/EventManager.gd"
```

- [ ] **Step 4: Run the suite to verify it passes**

Run: `godot --headless --path tingen -s tests/run_tests.gd`
Expected: `[occult divination]` shows nine PASS lines; suite exits 0.

- [ ] **Step 5: Commit**

```bash
git add tingen/src/OccultRisk.gd tingen/src/OccultTool.gd tingen/src/DivinationTool.gd tingen/src/OccultToolManager.gd tingen/data/occult_tools.json tingen/project.godot tingen/tests/run_tests.gd
git commit -m "feat(occult): OocultTool hierarchy + Divination perception verb (no-name lead)"
```

---

## Task 3: Remaining occult subclasses (residue / dream / gray-fog)

**Files:**
- Create: `tingen/src/ResidueSightTool.gd`
- Create: `tingen/src/DreamFragmentsTool.gd`
- Create: `tingen/src/GrayFogTool.gd`
- Test: `tingen/tests/run_tests.gd`

- [ ] **Step 1: Write the failing test**

In `tingen/tests/run_tests.gd`, add:

```gdscript
func _test_occult_other_tools() -> void:
	print("[occult other tools]")
	var OTM: Object = root.get_node("/root/OccultToolManager")
	var INV: Object = root.get_node("/root/Inventory")
	var WS: Object = root.get_node("/root/WorldState")
	OTM.rebuild()
	INV.clear()
	WS.set_pressure(&"fatigue", 0.0)
	WS.set_pressure(&"corruption", 0.0)
	# Residue sight: owns lens, no ingredient cost.
	INV.add("spirit_lens")
	_ok(OTM.can_use("residue_sight"), "residue sight usable with just the lens")
	var r1: Dictionary = OTM.use("residue_sight")
	_ok(r1.get("ok", false), "residue sight returns ok")
	# Dream fragments: produces dream_residue.
	INV.add("dream_draught")
	INV.add("dream_herb", 1)
	var r2: Dictionary = OTM.use("dream_fragments")
	_ok(r2.get("ok", false), "dream fragments returns ok")
	_ok(INV.count_of("dream_residue") == 1, "dream fragments produces dream_residue")
	_ok(INV.count_of("dream_herb") == 0, "dream fragments consumes dream_herb")
	# Gray fog: hard-capped at 3 uses per run.
	INV.add("gray_fog_focus")
	INV.add("consecrated_chalk", 9)
	_ok(OTM.use("gray_fog").get("ok", false), "gray fog use 1 ok")
	OTM.use("gray_fog")
	OTM.use("gray_fog")
	_ok(OTM.can_use("gray_fog") == false, "gray fog refused after 3 uses")
	_ok(OTM.use("gray_fog").get("ok", false) == false, "gray fog 4th use blocked")
```

Register in `_init()` above the final `print(...)`:

```gdscript
	_test_occult_other_tools()

	print("\n=== %d passed, %d failed ===" % [_passed, _failed])
```

- [ ] **Step 2: Run the suite to verify it fails**

Run: `godot --headless --path tingen -s tests/run_tests.gd`
Expected: parse/load error — the three subclass scripts don't exist; `OccultToolManager.rebuild()` skipped them so `use()` returns "unknown".

- [ ] **Step 3: Create the three subclasses**

Create `tingen/src/ResidueSightTool.gd`:

```gdscript
class_name ResidueSightTool
extends OccultTool
## Residue Sight / Spirit Vision (灵视): reveals what lingers at the current place — for
## the slice, a local directional impression about recent agent activity. (Hidden-clue
## reveal on Interactables is wired in the scene-integration plan.)

func _perform() -> Dictionary:
	var lead := "Something was done here recently — the air still flinches."
	return {"ok": true, "kind": "residue", "text": lead, "lead": lead, "mislead": false}

func _apply_risk(result: Dictionary, rng: RandomNumberGenerator, corruption: float) -> void:
	if OccultRisk.roll_mislead(rng, corruption):
		result["text"] = "You sense residue — but it may be your own dread echoing back."
		result["mislead"] = true
```

Create `tingen/src/DreamFragmentsTool.gd`:

```gdscript
class_name DreamFragmentsTool
extends OccultTool
## Dream Fragments (梦境碎片): a soft cross-association nudging toward the thread, paid in
## exhaustion (high fatigue, zero attention). Produces a dream_residue reagent on success.

func _perform() -> Dictionary:
	var lead := "In the dream, two strangers carried the same gray salt to the same dark door."
	return {"ok": true, "kind": "dream", "text": lead, "lead": lead, "mislead": false}

func _apply_risk(result: Dictionary, rng: RandomNumberGenerator, corruption: float) -> void:
	if OccultRisk.roll_mislead(rng, corruption):
		result["lead"] = "In the dream, the wrong face wears the cult's mark."
		result["text"] = result["lead"]
		result["mislead"] = true
```

Create `tingen/src/GrayFogTool.gd`:

```gdscript
class_name GrayFogTool
extends OccultTool
## Gray-Fog Reconstruction (灰雾重构): the precious, hard-capped reading. Surfaces the
## single most useful directional lead — never the answer. (The Gray-Fog Hypothesis Board
## is cut; this survives as a costed perception verb.)

func _perform() -> Dictionary:
	var lead := "Through the fog, the threads converge on the iron district — but not on which door."
	return {"ok": true, "kind": "gray_fog", "text": lead, "lead": lead, "mislead": false}

func _apply_risk(result: Dictionary, rng: RandomNumberGenerator, corruption: float) -> void:
	if OccultRisk.roll_mislead(rng, corruption):
		result["lead"] = "Through the fog, a false convergence pulls you the wrong way."
		result["text"] = result["lead"]
		result["mislead"] = true
```

- [ ] **Step 4: Run the suite to verify it passes**

Run: `godot --headless --path tingen -s tests/run_tests.gd`
Expected: `[occult other tools]` shows nine PASS lines; suite exits 0.

- [ ] **Step 5: Commit**

```bash
git add tingen/src/ResidueSightTool.gd tingen/src/DreamFragmentsTool.gd tingen/src/GrayFogTool.gd tingen/tests/run_tests.gd
git commit -m "feat(occult): residue/dream/gray-fog perception verbs"
```

---

## Task 4: Player action verbs — sabotage + social_influence

**Files:**
- Create: `tingen/src/PlayerActions.gd`
- Modify: `tingen/project.godot`
- Test: `tingen/tests/run_tests.gd`

- [ ] **Step 1: Write the failing test**

In `tingen/tests/run_tests.gd`, add:

```gdscript
func _test_player_actions() -> void:
	print("[player actions]")
	var PA: Object = root.get_node("/root/PlayerActions")
	var SP: Object = root.get_node("/root/SummoningPlan")
	var OV: Object = root.get_node("/root/Overseer")
	var EB: Object = root.get_node("/root/EventBus")
	var AG: Object = root.get_node("/root/Agents")
	AG.rebuild(); SP.reset(); OV.reset(); EB.clear()

	# Sabotage: strips a cult ingredient, raises impede, sets back the countdown, and
	# marks the player involved (so the overseer will now allow exposure).
	var cd_before: int = SP.countdown_beats
	var impede_before: float = SP.impede_score
	_ok(PA.sabotage("ritual_salt"), "sabotage of a held ingredient succeeds")
	_ok(SP.countdown_beats > cd_before, "sabotage sets back the summoning countdown")
	_ok(SP.impede_score > impede_before, "sabotage raises impede")
	_ok(EB.events("player_sabotage").size() == 1, "sabotage logs a player event")
	_ok(OV.allows_exposure(), "sabotage marks the player involved")
	# Sabotage of an absent ingredient fails and changes nothing.
	_ok(PA.sabotage("does_not_exist") == false, "sabotage of an unheld ingredient fails")

	# Social influence: turning the waverer flips his faction and raises impede.
	var orin: Agent = AG.get_agent("lamplighter_orin")
	_ok(orin.faction == "cult", "orin starts in the cult")
	var impede2: float = SP.impede_score
	_ok(PA.social_influence("lamplighter_orin"), "turning the waverer succeeds")
	_ok(orin.faction == "ally", "the waverer is turned to an ally")
	_ok(SP.impede_score > impede2, "turning the waverer raises impede")
	_ok(EB.events("player_social").size() == 1, "social influence logs a player event")
	# A non-waverer cannot be turned.
	_ok(PA.social_influence("clerk_voss") == false, "the committed leader cannot be turned")
```

Register in `_init()` above the final `print(...)`:

```gdscript
	_test_player_actions()

	print("\n=== %d passed, %d failed ===" % [_passed, _failed])
```

- [ ] **Step 2: Run the suite to verify it fails**

Run: `godot --headless --path tingen -s tests/run_tests.gd`
Expected: failure resolving `/root/PlayerActions` (autoload missing).

- [ ] **Step 3: Create PlayerActions.gd + register autoload**

Create `tingen/src/PlayerActions.gd`:

```gdscript
extends Node
## The player's interference verbs (autoload `PlayerActions`). Each is a first-class
## EventBus event — identical in shape to an agent action — so the overseer reacts to the
## player exactly as it reacts to agents (and marks the player "involved", lifting the
## no-chance-exposure guard). Both verbs feed the hidden impede score.

const SABOTAGE_IMPEDE: float = 10.0
const SOCIAL_IMPEDE: float = 12.0

## Strip one of an ingredient from the cell's stock. Returns false if the cell lacks it.
func sabotage(item_id: String, count: int = 1) -> bool:
	if not SummoningPlan.remove_ingredient(item_id, count):
		return false
	SummoningPlan.add_impede(SABOTAGE_IMPEDE * count, "sabotage")
	EventBus.emit_event("player_sabotage", {"actor": "player", "item": item_id, "count": count})
	return true

## Turn a waverer (role "scout_waverer") into an ally. Returns false for anyone else.
func social_influence(agent_id: String) -> bool:
	var a: Agent = Agents.get_agent(agent_id)
	if a == null or a.role != "scout_waverer":
		return false
	a.faction = "ally"
	a.remember("chose to turn against the cell")
	SummoningPlan.add_impede(SOCIAL_IMPEDE, "turned waverer")
	EventBus.emit_event("player_social", {"actor": "player", "agent": agent_id, "result": "turned"})
	return true
```

Register the autoload in `tingen/project.godot` — add `PlayerActions` after `OccultToolManager`:

```
OccultToolManager="*res://src/OccultToolManager.gd"
PlayerActions="*res://src/PlayerActions.gd"
EventManager="*res://src/EventManager.gd"
```

- [ ] **Step 4: Run the suite to verify it passes**

Run: `godot --headless --path tingen -s tests/run_tests.gd`
Expected: `[player actions]` shows twelve PASS lines; suite exits 0.

- [ ] **Step 5: Commit**

```bash
git add tingen/src/PlayerActions.gd tingen/project.godot tingen/tests/run_tests.gd
git commit -m "feat(player): sabotage + social_influence verbs feeding impede"
```

---

## Task 5: Combat climax (deterministic, impede-scaled)

**Files:**
- Create: `tingen/src/CombatEncounter.gd`
- Test: `tingen/tests/run_tests.gd`

- [ ] **Step 1: Write the failing test**

In `tingen/tests/run_tests.gd`, add:

```gdscript
func _test_combat_scaled_by_impede() -> void:
	print("[combat]")
	var SP: Object = root.get_node("/root/SummoningPlan")

	# Strong manifestation (no impede): hard fight.
	SP.reset()
	var hard := CombatEncounter.new(SP.manifestation_strength())
	var hard_result: Dictionary = hard.auto_resolve()

	# Weakened manifestation (heavy impede + stripped ingredients): easy fight.
	SP.reset()
	SP.add_impede(70.0, "test")
	SP.remove_ingredient("ritual_salt", 3)
	var easy := CombatEncounter.new(SP.manifestation_strength())
	var easy_result: Dictionary = easy.auto_resolve()

	_ok(easy.enemy_max_hp < hard.enemy_max_hp, "more impede -> weaker enemy")
	_ok(easy_result["player_hp_left"] > hard_result["player_hp_left"], "more impede -> player ends with more HP")
	_ok(easy_result["win"] == true, "a heavily-impeded summoning is winnable")
	_ok(hard_result.has("rounds"), "result reports the round count")
	# The occult ability hits harder than a basic attack.
	var enc := CombatEncounter.new(50.0)
	_ok(enc.OCCULT_DAMAGE > enc.ATTACK_DAMAGE, "occult ability beats a basic attack")
```

Register in `_init()` above the final `print(...)`:

```gdscript
	_test_combat_scaled_by_impede()

	print("\n=== %d passed, %d failed ===" % [_passed, _failed])
```

- [ ] **Step 2: Run the suite to verify it fails**

Run: `godot --headless --path tingen -s tests/run_tests.gd`
Expected: parse/identifier error — `CombatEncounter` not defined.

- [ ] **Step 3: Create CombatEncounter.gd**

Create `tingen/src/CombatEncounter.gd`:

```gdscript
class_name CombatEncounter
extends RefCounted
## Minimal but real climax resolution. The player has HP, two attacks (a basic strike and
## a stronger occult ability), against a manifestation whose HP and damage scale with
## SummoningPlan.manifestation_strength(). `auto_resolve` plays a deterministic exchange
## used by tests and as the headless backbone of the real-time fight (the scene/UI wraps
## this in a later plan). Higher impede -> weaker enemy -> the player ends with more HP.

const PLAYER_MAX_HP: float = 100.0
const ATTACK_DAMAGE: float = 18.0
const OCCULT_DAMAGE: float = 30.0
const OCCULT_EVERY: int = 3   # the occult ability lands every 3rd round

var enemy_max_hp: float
var enemy_damage: float
var player_hp: float

func _init(strength: float) -> void:
	enemy_max_hp = strength                 # strength IS the enemy's HP pool
	enemy_damage = strength * 0.12          # and how hard it hits back
	player_hp = PLAYER_MAX_HP

## Deterministic exchange: each round the player strikes (occult every OCCULT_EVERY),
## then the enemy strikes back if still alive. Returns { win, rounds, player_hp_left }.
func auto_resolve() -> Dictionary:
	var enemy_hp := enemy_max_hp
	var rounds := 0
	while enemy_hp > 0.0 and player_hp > 0.0:
		rounds += 1
		var dmg := OCCULT_DAMAGE if rounds % OCCULT_EVERY == 0 else ATTACK_DAMAGE
		enemy_hp -= dmg
		if enemy_hp <= 0.0:
			break
		player_hp -= enemy_damage
	player_hp = maxf(player_hp, 0.0)
	return {"win": player_hp > 0.0, "rounds": rounds, "player_hp_left": player_hp}
```

- [ ] **Step 4: Run the suite to verify it passes**

Run: `godot --headless --path tingen -s tests/run_tests.gd`
Expected: `[combat]` shows five PASS lines; suite exits 0.

- [ ] **Step 5: Commit**

```bash
git add tingen/src/CombatEncounter.gd tingen/tests/run_tests.gd
git commit -m "feat(combat): deterministic climax resolver scaled by impede"
```

---

## Task 6: Persist the new state through SaveManager

**Files:**
- Modify: `tingen/src/SaveManager.gd`
- Test: `tingen/tests/run_tests.gd`

- [ ] **Step 1: Write the failing test**

In `tingen/tests/run_tests.gd`, add:

```gdscript
func _test_player_state_save_load() -> void:
	print("[player state save/load]")
	var SP: Object = root.get_node("/root/SummoningPlan")
	var OV: Object = root.get_node("/root/Overseer")
	var OTM: Object = root.get_node("/root/OccultToolManager")
	var SM: Object = root.get_node("/root/SaveManager")
	SP.reset(); OV.reset(); OTM.rebuild()
	SP.add_impede(33.0, "test")
	SP.remove_ingredient("candle", 1)
	OV.player_involved = true
	var tmp := "user://test_player_state.json"
	_ok(SM.save_game(tmp), "save_game writes file")
	SP.reset(); OV.reset()
	_ok(SP.impede_score == 0.0, "impede cleared before load")
	_ok(SM.load_game(tmp), "load_game reads file")
	_ok(abs(SP.impede_score - 33.0) < 0.01, "impede restored")
	_ok(SP.ingredients.get("candle", 0) == 2, "cult ingredient stock restored")
	_ok(OV.player_involved == true, "overseer player-involvement restored")
	DirAccess.remove_absolute(ProjectSettings.globalize_path(tmp))
```

Register in `_init()` above the final `print(...)`:

```gdscript
	_test_player_state_save_load()

	print("\n=== %d passed, %d failed ===" % [_passed, _failed])
```

- [ ] **Step 2: Run the suite to verify it fails**

Run: `godot --headless --path tingen -s tests/run_tests.gd`
Expected: `[player state save/load]` FAILs at "impede restored" — these systems aren't in the save payload yet.

- [ ] **Step 3: Add the keys to SaveManager**

In `tingen/src/SaveManager.gd`, in `save_game()`, add three entries to the `data` dictionary (after the `"inventory": Inventory.to_dict(),` line from the inventory plan; if that line isn't present, add after `"clues": ClueDB.to_dict(),`):

```gdscript
		"summoning_plan": SummoningPlan.to_dict(),
		"overseer": Overseer.to_dict(),
		"occult_tools": OccultToolManager.to_dict(),
```

In `load_game()`, add three restore calls in the "Restore data-only subsystems first" block (after `WorldState.from_dict(...)`):

```gdscript
	SummoningPlan.from_dict(data.get("summoning_plan", {}))
	Overseer.from_dict(data.get("overseer", {}))
	OccultToolManager.from_dict(data.get("occult_tools", {}))
```

- [ ] **Step 4: Run the suite to verify it passes**

Run: `godot --headless --path tingen -s tests/run_tests.gd`
Expected: `[player state save/load]` shows six PASS lines; the full suite ends `=== N passed, 0 failed ===`, exit 0.

- [ ] **Step 5: Commit**

```bash
git add tingen/src/SaveManager.gd tingen/tests/run_tests.gd
git commit -m "feat(save): persist summoning plan, overseer, and occult tool state"
```

---

## Done criteria for this plan

- Full headless suite passes and includes: summoning plan, occult divination, occult other tools, player actions, combat, player-state save/load.
- Occult tools work as perception verbs that emit directional leads and never name the true site; they cost fatigue/attention and consume/produce reagents via `Inventory`.
- `sabotage` and `social_influence` are first-class `EventBus` events that raise impede, set back the countdown / turn the waverer, and mark the player involved.
- Combat is deterministic and demonstrably scales with impede (more impede → weaker enemy → easier fight).
- New state round-trips through save/load.

## What this plan deliberately does NOT do (later plans)

- No real-time combat scene/input, enemy variety, party-of-2 tactics, or ability trees — only the deterministic resolver the scene will wrap.
- No occult/inventory UI panels or input actions — headless logic only; panels (`OccultPanel`, inventory view) and on-screen agents land in the scene-integration/UI plan.
- No Gray-Fog Hypothesis Board (cut) and no hidden-clue reveal wiring on Interactables (scene-integration plan).
- No live LLM director/critic — the deterministic systems from Plans 3–5 remain in force.
