extends SceneTree
## M18 harness — NPC combat costs are REAL + downed bodies are lootable. Run directly:
##   godot --headless --path tingen -s tests/test_npc_cost_loot.gd
##
## Proves the milestone end to end on the deterministic executor machinery (fixed dt, no RNG, no
## wall time — same cadence combat_sim uses):
##   (a) an NPC with an ammo-costed art + FINITE rounds fires until dry, then REFUSES (no_ammo),
##       burning NO cooldown (a refused cost never marks the ledger);
##   (b) an NPC with no granting weapon can't fire an ammo-costed art (no_weapon);
##   (c) monster forms (free kits) are UNAFFECTED — they cast their kit normally;
##   (d) downing a body makes its whole carried inventory lootable, the player loots it ONCE
##       (latch), the items transfer — a standing body yields nothing;
##   (e) NPC inventories re-hydrate per run + loot latches reset — no cross-run leak (probe restart).

const DT: float = 1.0 / 60.0

var _fails: int = 0
var _passes: int = 0

func _init() -> void:
	await process_frame
	await process_frame
	# N1 (sprint safety): sandbox EVERY persistent path (meta/save/settings/hints/playlog) into
	# user://test_sandbox/<run>/ and arm the write guard — see src/TestSandbox.gd.
	preload("res://src/TestSandbox.gd").activate(root)
	print("=== test_npc_cost_loot: NPC costs real + downed bodies lootable ===")
	_scenario_fire_until_dry()
	_scenario_no_weapon()
	_scenario_monster_free_kit()
	_scenario_loot_once()
	_scenario_reset_per_run()
	print("\n=== test_npc_cost_loot: %d passed, %d failed ===" % [_passes, _fails])
	root.get_node("/root/Agents").rebuild()
	root.get_node("/root/EventBus").clear()
	quit(1 if _fails > 0 else 0)

func _check(cond: bool, label: String) -> void:
	if cond:
		_passes += 1
		print("  PASS  %s" % label)
	else:
		_fails += 1
		printerr("  FAIL  %s" % label)

func _stage(id: String, form: String, room_id: String, pos: Vector2) -> Agent:
	var a := Agent.new(id)
	a.display_name = id
	a.room = room_id
	a.position = pos
	a.combat_form = form
	a.in_combat = true
	root.get_node("/root/Agents")._agents[id] = a
	return a

func _bound(agent: Agent) -> CombatExecutor:
	var ex := CombatExecutor.new()
	ex.bind(agent)
	ex.cost_provider = AgentCostProvider.new(agent)
	return ex

func _step(executors: Array, seconds: float) -> void:
	var steps := int(round(seconds * 60.0))
	for _i in steps:
		for ex in executors:
			ex.step_combat(DT)

## ---- (a) a gunman runs dry, then refuses no_ammo, burning no cooldown ----
func _scenario_fire_until_dry() -> void:
	print("\n--- (a) a human gunman fires until dry, then refuses no_ammo (no cooldown burned) ---")
	var gun := _stage("t_gunman", "wren_human", "t_arena_a", Vector2.ZERO)
	gun.add_item("revolver", 1)
	gun.add_item("revolver_round", 2)
	var ex := _bound(gun)

	# Drive the fight: cast revolver_shot whenever the executor is idle (try_cast gates readiness).
	var shots := 0
	var dry_reason := ""
	for _f in range(360):   # 6 simulated seconds — plenty for 2 shots + a dry attempt
		if ex.phase == "idle":
			var res: Dictionary = ex.try_cast("revolver_shot", "")
			if bool(res.get("ok", false)):
				shots += 1
			elif String(res.get("reason", "")) == "no_ammo":
				dry_reason = "no_ammo"
		ex.step_combat(DT)
	_check(shots == 2, "the gunman fired exactly its 2 carried rounds (fired %d)" % shots)
	_check(gun.item_count("revolver_round") == 0, "the magazine is empty after firing dry")
	_check(dry_reason == "no_ammo", "the dry gun refuses the ammo-costed art with 'no_ammo'")

	# Precise no-cooldown-burned proof: a fresh dry executor, ledger untouched by the refusal.
	var dry := _stage("t_dry", "wren_human", "t_arena_a2", Vector2.ZERO)
	dry.add_item("revolver", 1)   # a weapon but NO rounds
	var dex := _bound(dry)
	var before := CombatResolver.ledger_ready(dex.ledger, "revolver_shot", dex.now_ms())
	var r: Dictionary = dex.try_cast("revolver_shot", "")
	_check(not bool(r.get("ok", false)) and String(r.get("reason", "")) == "no_ammo",
		"a weapon with zero rounds refuses with 'no_ammo'")
	_check(dex.phase == "idle", "the refusal never entered windup (no cast in flight)")
	_check(before and CombatResolver.ledger_ready(dex.ledger, "revolver_shot", dex.now_ms()),
		"a refused ammo cost burns NO cooldown (ledger still ready)")
	_check(dry.item_count("revolver_round") == 0, "the refusal never half-pays (rounds still 0)")
	ex.free()
	dex.free()
	root.get_node("/root/Agents").rebuild()

## ---- (b) no granting weapon -> no_weapon ----
func _scenario_no_weapon() -> void:
	print("\n--- (b) no carried weapon can't fire an ammo-costed art (no_weapon) ---")
	var a := _stage("t_unarmed", "wren_human", "t_arena_b", Vector2.ZERO)
	a.add_item("revolver_round", 6)   # rounds in the pocket, but no revolver to fire them
	var ex := _bound(a)
	var r: Dictionary = ex.try_cast("revolver_shot", "")
	_check(not bool(r.get("ok", false)) and String(r.get("reason", "")) == "no_weapon",
		"rounds without the granting weapon refuse with 'no_weapon'")
	_check(ex.phase == "idle" and CombatResolver.ledger_ready(ex.ledger, "revolver_shot", ex.now_ms()),
		"…and the no_weapon refusal burns no cooldown")
	_check(a.item_count("revolver_round") == 6, "…and spends nothing")
	ex.free()
	root.get_node("/root/Agents").rebuild()

## ---- (c) monster free kits are unaffected ----
func _scenario_monster_free_kit() -> void:
	print("\n--- (c) monster forms (free kits) fight normally with a cost provider bound ---")
	var mon := _stage("t_monster", "bieber_monster", "t_arena_c", Vector2.ZERO)
	var dummy := _stage("t_dummy", "civilian", "t_arena_c", Vector2(30, 0))
	var mex := _bound(mon)         # a provider is bound, exactly like the live NPC seam
	var dex := CombatExecutor.new()
	dex.bind(dummy)
	var casts := 0
	for _f in range(600):
		if mex.phase == "idle" and bool(mex.try_cast("cleaver_swipe", "t_dummy").get("ok", false)):
			casts += 1
		mex.step_combat(DT)
		dex.step_combat(DT)
	_check(casts >= 2, "the monster cast its free cleaver_swipe repeatedly (%d casts) — cost provider never refuses a free art" % casts)
	_check(dummy.hp < 100.0, "…and the free-kit strikes actually landed on the dummy")
	mex.free()
	dex.free()
	root.get_node("/root/Agents").rebuild()

## ---- (d) a downed body is lootable ONCE ----
func _scenario_loot_once() -> void:
	print("\n--- (d) a downed body's carried items are lootable once (latch) ---")
	var looter := _stage("t_looter", "player", "t_arena_d", Vector2.ZERO)
	looter.inventory.clear()
	var body := _stage("t_corpse", "wren_human", "t_arena_d", Vector2(10, 0))
	body.inventory.clear()
	body.add_item("revolver", 1)
	body.add_item("revolver_round", 3)
	body.add_item("shilling", 5)

	# A STANDING body yields nothing (you loot corpses, not the living).
	var nope: Dictionary = PlayerCombat.loot_downed_body(looter, body)
	_check(nope.is_empty() and looter.inventory_count() == 0, "a STANDING body cannot be looted")

	body.downed = true
	var moved: Dictionary = PlayerCombat.loot_downed_body(looter, body)
	_check(int(moved.get("revolver", 0)) == 1 and int(moved.get("revolver_round", 0)) == 3
		and int(moved.get("shilling", 0)) == 5, "looting a downed body reports the whole inventory moved")
	_check(looter.item_count("revolver") == 1 and looter.item_count("revolver_round") == 3
		and looter.item_count("shilling") == 5, "the items transferred into the looter's inventory")
	_check(body.inventory_count() == 0, "the body's inventory is emptied by the loot")
	_check(body.looted, "the body is latched looted")

	var again: Dictionary = PlayerCombat.loot_downed_body(looter, body)
	_check(again.is_empty() and looter.item_count("revolver") == 1,
		"a looted body can't be looted a SECOND time (latch) — no duplication")
	root.get_node("/root/Agents").rebuild()

## ---- (e) per-run rehydrate + latch reset, no leak ----
func _scenario_reset_per_run() -> void:
	print("\n--- (e) NPC inventories re-hydrate per run + loot latches reset (no leak) ---")
	var reg: Object = root.get_node("/root/Agents")
	reg.rebuild()
	var wren: Agent = reg.get_agent("sable_wren")
	_check(wren != null, "sable_wren exists in the fresh roster")
	if wren == null:
		return
	_check(wren.item_count("revolver") == 1 and wren.item_count("revolver_round") == 6,
		"sable_wren re-hydrates her authored carried_items (revolver + 6 rounds)")
	_check(not wren.looted, "…and her loot latch starts clear")

	# Mutate mid-run: spend rounds, latch looted, add junk — then a fresh run must scrub it all.
	wren.remove_item("revolver_round", 6)
	wren.remove_item("revolver", 1)
	wren.looted = true
	wren.add_item("junk_leak", 9)
	reg.rebuild()
	var wren2: Agent = reg.get_agent("sable_wren")
	_check(wren2.item_count("revolver") == 1 and wren2.item_count("revolver_round") == 6,
		"a fresh run RE-HYDRATES the loadout (spent rounds restored)")
	_check(not wren2.looted, "a fresh run resets the loot latch")
	_check(wren2.item_count("junk_leak") == 0, "no cross-run inventory leak (the junk is gone)")

	# Runtime threat (nighthawk gunman) hydrates a loadout on spawn, and Agents.rebuild drops it.
	var mth: Object = root.get_node_or_null("/root/MeterThreats")
	if mth != null:
		mth.spawn_room = "t_arena_e"
		mth.spawn_pos = Vector2(500, 500)
		mth._spawn_threat("heat")
		var found: Agent = null
		for a in reg.all():
			if String(a.combat_form) == "nighthawk_pursuer":
				found = a
				break
		_check(found != null, "the runtime nighthawk threat spawned")
		if found != null:
			_check(found.item_count("revolver") >= 1 and found.item_count("revolver_round") >= 1,
				"the runtime gun-user threat hydrates a revolver + rounds (stays lethal, and lootable)")
		mth.spawn_room = ""
		mth.spawn_pos = Vector2.ZERO
		reg.rebuild()
		var still := false
		for a in reg.all():
			if String(a.combat_form) == "nighthawk_pursuer":
				still = true
		_check(not still, "a fresh run drops the runtime threat (no phantom hunter leak)")
	reg.rebuild()
