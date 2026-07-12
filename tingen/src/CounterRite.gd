extends Node
## The player's COUNTER-RITE (autoload singleton `CounterRite`) — direction v2 §6.
##
## The ONLY player verb that pushes Doom DOWN. A warding rite worked against the cult's descent: it
## SPENDS occult ingredients (Inventory items), REDUCES Doom directly (Meters), ADDS impede to the
## cult's SummoningPlan (a weaker climax), and TAXES Notice ("the Beyond's eye turns to you") — the
## push-your-luck cost that keeps buying-time from being free. Data-driven: the rite (its ingredients,
## costs, and magnitudes) is authored in data/rituals.json under `counter_rite`; THIS engine node knows
## no item id or number of its own. RitualPanel drives perform() from a button; tests call it directly.
##
## Determinism / constraints: additive, OUT OF COMBAT, never touches combat resolution or RNG — the
## pinned combat sims never call it. The rite itself reads Inventory / Meters / SummoningPlan live each
## time (no cached state); the once-per-run discoverability HINT is now owned by the shared HintDirector
## framework (M35) under the `counter_rite` key, re-armed by reset() (RunManager._reset_run_world).
## Engine-neutral: no NPC/id branch; every string/number is data.
##
## M32 — DISCOVERABILITY: the rite was reachable but unusable because nothing told the player it existed.
## This node watches the real Inventory acquire seam (Inventory.item_added) and, the FIRST moment the
## player holds every authored ingredient this run, surfaces a single diegetic hint (data/rituals.json
## counter_rite.hint) on the HUD's thought channel (WorldState.thought_requested) — EXACTLY once per run.
## M35: the once-only dedup + surface + EventBus fact all route through HintDirector (ONE hint system,
## not two); CounterRite owns only the CONDITION (holding every ingredient) + the per-run re-arm.

const RITUALS_PATH: String = "res://data/rituals.json"
const RITE_ID: String = "counter_rite"

const HINT_KEY: String = "counter_rite"

var _rites: Dictionary = {}

func _ready() -> void:
	_load()
	# Watch the REAL acquire seam: any add to the ritual Inventory the rite reads. When that add first
	# makes the rite performable (every ingredient in hand), _maybe_hint surfaces the one-time hint.
	# Idempotent connect (safe across the headless -s harness / world swaps).
	var inv := _al("Inventory")
	if inv != null and inv.has_signal("item_added") and not inv.item_added.is_connected(_on_item_added):
		inv.item_added.connect(_on_item_added)

func _load() -> void:
	if not FileAccess.file_exists(RITUALS_PATH):
		push_error("CounterRite: missing %s" % RITUALS_PATH)
		return
	var parsed: Variant = JSON.parse_string(FileAccess.get_file_as_string(RITUALS_PATH))
	if parsed is Dictionary:
		_rites = parsed

## The authored rite def (a defensive copy), {} when unknown.
func rite_def(rite_id: String = RITE_ID) -> Dictionary:
	var d: Variant = _rites.get(rite_id, {})
	return (d as Dictionary).duplicate(true) if d is Dictionary else {}

## The rite's ingredient bill (item_id -> count).
func ingredients(rite_id: String = RITE_ID) -> Dictionary:
	var ing: Variant = rite_def(rite_id).get("ingredients", {})
	return (ing as Dictionary).duplicate(true) if ing is Dictionary else {}

## Can the counter-rite be performed right now? {ok, reason}. Requires EVERY authored ingredient in the
## player's Inventory. Pure — reads Inventory, mutates nothing.
func can_perform(rite_id: String = RITE_ID) -> Dictionary:
	if rite_def(rite_id).is_empty():
		return {"ok": false, "reason": "unknown_rite"}
	var inv := _al("Inventory")
	if inv == null:
		return {"ok": false, "reason": "no_inventory"}
	var ing := ingredients(rite_id)
	for item_id in ing:
		if not inv.has(String(item_id), int(ing[item_id])):
			return {"ok": false, "reason": "missing_ingredients"}
	return {"ok": true, "reason": ""}

## Perform the counter-rite (direction v2 §6). On success: CONSUME the ingredients, push Doom DOWN by
## the authored amount (the only verb that does), TAX Notice (the Beyond's eye), and ADD impede to the
## SummoningPlan (a weaker descent). Returns {ok, reason, spent, doom_before/after, notice_before/after,
## impede}. Refuses CLEANLY (no state change) without the ingredients. OUT OF COMBAT — the caller opens
## it only outside a fight.
func perform(rite_id: String = RITE_ID) -> Dictionary:
	var gate := can_perform(rite_id)
	if not bool(gate.get("ok", false)):
		return gate
	var d := rite_def(rite_id)
	var inv := _al("Inventory")
	var meters := _al("Meters")
	var plan := _al("SummoningPlan")
	# (a) spend the occult ingredients (consumed first — a refusal above never half-pays).
	var spent: Dictionary = {}
	var ing := ingredients(rite_id)
	for item_id in ing:
		var n := int(ing[item_id])
		inv.remove(String(item_id), n)
		spent[String(item_id)] = n
	var doom_before := float(meters.get_meter("doom")) if meters != null else 0.0
	var notice_before := float(meters.get_meter("notice")) if meters != null else 0.0
	var doom_cut := float(d.get("doom_reduction", 0.0))
	var notice_cost := float(d.get("notice_cost", 0.0))
	var impede := float(d.get("impede", 0.0))
	# (b) push Doom DOWN, (c) tax Notice (push-your-luck), (d) impede the rite (a weaker climax).
	if meters != null:
		if doom_cut > 0.0:
			meters.adjust("doom", -doom_cut, "counter_rite")
		if notice_cost > 0.0:
			meters.adjust("notice", notice_cost, "counter_rite")
	if plan != null and impede > 0.0 and plan.has_method("add_impede"):
		plan.add_impede(impede, "counter_rite")
	var eb := _al("EventBus")
	if eb != null:
		eb.emit_event("player_counter_rite",
			{"actor": "player", "doom_cut": doom_cut, "notice_cost": notice_cost, "impede": impede})
	return {
		"ok": true, "reason": "",
		"spent": spent, "impede": impede,
		"doom_before": doom_before, "doom_after": float(meters.get_meter("doom")) if meters != null else 0.0,
		"notice_before": notice_before, "notice_after": float(meters.get_meter("notice")) if meters != null else 0.0,
	}

## M32 — the once-per-run discoverability hint (direction v2 §6). Fired off the real Inventory acquire
## seam: whenever an item is added to the ritual Inventory, check whether the rite JUST became
## performable and, if so and not yet hinted this run, surface the authored hint. Latched so a later
## inventory change never re-fires it.
func _on_item_added(_item_id: String, _count: int) -> void:
	_maybe_hint()

## Surface the diegetic discoverability hint EXACTLY once per run, at the first moment the player holds
## every authored ingredient (can_perform().ok). The line is DATA (rituals.json counter_rite.hint), routed
## through the shared HintDirector framework (M35) under the stable `counter_rite` key — so the dedup, the
## surface (WorldState.thought_requested — the HUD's internal-thought channel), and the EventBus fact all
## live in ONE place, not a second parallel hint system. Passed persist=false so it stays once-per-RUN
## (re-armed by reset()), unlike the once-ever onboarding hints. A no-op when the rite is not yet
## performable or authors no hint; CounterRite owns only the CONDITION, HintDirector owns the once-only.
func _maybe_hint() -> void:
	if not bool(can_perform().get("ok", false)):
		return
	var hint := String(rite_def().get("hint", ""))
	if hint == "":
		return
	var hd := _al("HintDirector")
	if hd != null:
		hd.fire(HINT_KEY, hint, false)

## Re-arm the once-per-run hint latch — the seam RunManager._reset_run_world() calls so a fresh run's
## hint fires again with no carry (mirrors the GMOpening/Shop per-run reset manifest). Routes to the shared
## framework (HintDirector.rearm) so the counter-rite key re-arms through the ONE system. The hint is a
## re-derivable tutorial beat and intentionally does NOT ride the nightly checkpoint (a mid-run death
## restores the run, not the discovery moment, which has already passed).
func reset() -> void:
	var hd := _al("HintDirector")
	if hd != null:
		hd.rearm(HINT_KEY)

## Autoload lookup via /root (class_name-safe under the headless -s harness), tolerant of absence.
func _al(autoload_name: String) -> Node:
	var ml := Engine.get_main_loop()
	if ml == null or not (ml is SceneTree):
		return null
	return (ml as SceneTree).root.get_node_or_null(autoload_name)
