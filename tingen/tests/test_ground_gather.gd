extends SceneTree
## B1 (retro patch wave) — LIVE GROUND-GATHER reachability. Standalone headless harness; also folded
## into the main suite (run_tests.gd `_test_ground_gather`) via the SAME run_all() entry.
## Run: godot --headless --path tingen -s tests/test_ground_gather.gd
##
## THE FINDING (24-agent retrospective audit): a downed prey's Characteristic drops on the GROUND
## (Progression._on_event -> RoomItems.place) but NO live player seam could pick a ground
## characteristic up — the live pickups were walk-over ammo hard-coded to "revolver_round",
## walk-over counter-rite ingredients, and body-loot (which moves only a body's carried INVENTORY,
## and prey author none). So in LIVE play digest/advance could only refuse "no_characteristic" and
## the sell fork was dead code — the core advance loop of BOTH pathways was broken live, masked by
## e2e harnesses calling RoomItems.take_near(...,999.0) directly. SECONDARY: nothing live stocked
## the cult supply cache (the only placer was a dangling ext_resource in City.tscn).
##
## This harness proves the fixes from the REAL live seams (a green API-level test is NOT proof a
## player can get there):
##
##  G1  a downed Beyonder's dropped Characteristic is gathered by the LIVE walk-over pickup — a real
##      Player body mounted in the tree, the physics-frame proximity seam doing the gather (the same
##      radius/feel as ammo), NOT a naked RoomItems.take_near call. The gather set is DATA (the
##      "gatherable" tag in items.json): an untagged ground item is NOT hoovered up.
##  G2  after the live gather, digest/advance succeeds through the live Interactable verb (the §6
##      advance loop closes from the ground drop with no injected items).
##  G3  the cult supply cache (scenario.json summoning.cache_items) is stocked onto the city floor
##      at run start by a LIVE placement seam that actually runs (RunManager world build), replacing
##      the dead CitySummoning path; a second start_run does not double-stock.
##  G4  the sell fork works with a LIVE-gathered characteristic: gather off the ground via the
##      walk-over seam, sell at the live counter Interactable, coin lands at the authored price.

const DT: float = 1.0 / 60.0
const SCENARIO_PATH := "res://data/scenario.json"

func _init() -> void:
	await process_frame
	await process_frame
	# B3 (retro): NEVER touch the player's REAL persistent profile (user://meta.json) — redirect
	# the meta slot to a test-scoped file before anything drives RunManager (tests/test_meta_isolation.gd).
	root.get_node("/root/RunManager").set("meta_path", "user://meta_test.json")
	root.get_node("/root/RunManager").reload_meta()
	var r: Dictionary = await run_all()
	print("\n=== test_ground_gather: %d passed, %d failed ===" % [int(r["passed"]), int(r["failed"])])
	quit(1 if int(r["failed"]) > 0 else 0)

## The one entry point (returns {passed, failed}); folded into run_tests.gd. Coroutine (mounts a real
## Player body and lets physics frames run the walk-over seam), so callers must `await run_all()`.
static func run_all() -> Dictionary:
	var c := {"passed": 0, "failed": 0}
	var tree: SceneTree = Engine.get_main_loop() as SceneTree
	var root: Node = tree.root
	# A prior suite harness may have left an ending overlay up (EndGame PAUSES the tree on a climax
	# screen — e.g. the hermit full-run's win right before this file in run_tests.gd). A paused tree
	# never delivers _physics_process to the mounted Player body, so the walk-over seam under test
	# would be inert for the wrong reason. Dismiss it the way live play does (Continue).
	var eg: Object = root.get_node_or_null("/root/EndGame")
	if tree.paused and eg != null and eg.has_method("dismiss"):
		eg.dismiss()
	await _g1_walkover_gathers_dropped_characteristic(c, root)
	await _g2_live_digest_after_live_gather(c, root)
	_g3_cache_stocked_at_run_start(c, root)
	await _g4_sell_fork_with_live_gathered_characteristic(c, root)
	# Leave a clean world for whatever runs next in the shared suite.
	root.get_node("/root/RunManager").start_run()
	root.get_node("/root/Agents").rebuild()
	root.get_node("/root/RoomItems").clear()
	root.get_node("/root/EventBus").clear()
	return c

# --- helpers ------------------------------------------------------------------------------------
static func _check(c: Dictionary, cond: bool, label: String) -> bool:
	if cond:
		c["passed"] = int(c["passed"]) + 1
		print("  PASS  %s" % label)
	else:
		c["failed"] = int(c["failed"]) + 1
		printerr("  FAIL  %s" % label)
	return cond

static func _scenario_block(key: String) -> Dictionary:
	if not FileAccess.file_exists(SCENARIO_PATH):
		return {}
	var parsed: Variant = JSON.parse_string(FileAccess.get_file_as_string(SCENARIO_PATH))
	if not (parsed is Dictionary):
		return {}
	var block: Variant = (parsed as Dictionary).get(key, {})
	return block if block is Dictionary else {}

## Down a real roster Beyonder in `arena` at `pos` through the REAL drop seam: position it, flag it
## downed, publish agent_downed on the EventBus — Progression's listener drops its Characteristic on
## the ground where it fell (the same event live combat emits). Returns the agent.
static func _down_prey(root: Node, prey: String, arena: String, pos: Vector2) -> Object:
	var AG: Object = root.get_node("/root/Agents")
	var a: Object = AG.get_agent(prey)
	a.room = arena
	a.position = pos
	a.downed = true
	root.get_node("/root/EventBus").emit_event("agent_downed", {"actor": "player", "target": prey})
	return a

## Mount a REAL Player body standing at `pos` (its proxy already staged in `arena`) and let the tree
## run physics frames — the LIVE walk-over pickup seam (PlayerCombat._physics_process) does whatever
## gathering it does. Frees the body before returning. THE point of this harness: no take_near calls.
static func _walk_over(root: Node, pos: Vector2, frames: int = 8) -> void:
	var pbody: Node = (load("res://scenes/Player.tscn") as PackedScene).instantiate()
	root.add_child(pbody)
	(pbody as Node2D).global_position = pos
	for _i in frames:
		await root.get_tree().physics_frame
	pbody.free()

# (G1) ------------------------------------------------------------------------------------------
static func _g1_walkover_gathers_dropped_characteristic(c: Dictionary, root: Node) -> void:
	print("[G1: a downed prey's dropped Characteristic is gathered by the LIVE walk-over pickup seam (data-tagged, ammo-consistent radius)]")
	var RM: Object = root.get_node("/root/RunManager")
	var AG: Object = root.get_node("/root/Agents")
	var RI: Object = root.get_node("/root/RoomItems")
	var EB: Object = root.get_node("/root/EventBus")
	RM.start_run()
	AG.rebuild()

	var arena := "gather_arena"
	var spot := Vector2(400, 300)
	var proxy: Object = AG.ensure_player_proxy(spot, arena)
	var wren: Object = _down_prey(root, "sable_wren", arena, spot)
	_check(c, String(wren.pathway) == "hunter" and RI.count(arena, "hunter_characteristic") >= 1,
		"downing sable_wren DROPPED a hunter_characteristic where she fell (the real drop seam)")

	# A control pile: an item NOT tagged gatherable must survive the walk-over (the set is DATA).
	RI.place(arena, "rye_bread", spot, 1)
	# Ammo rides the SAME walk-over seam (radius/feel consistent): a ground round at the spot too.
	RI.place(arena, "revolver_round", spot, 1)
	var rounds_before: int = proxy.item_count("revolver_round")
	EB.clear()

	await _walk_over(root, spot)

	_check(c, proxy.item_count("hunter_characteristic") >= 1,
		"the LIVE walk-over pickup gathered the dropped Characteristic into the player's hands")
	_check(c, RI.count(arena, "hunter_characteristic") == 0,
		"…and the drop is GONE from the ground (the world item was consumed, not duplicated)")
	_check(c, RI.count(arena, "rye_bread") == 1,
		"an item NOT tagged gatherable is NOT hoovered up (the gather set is items.json data)")
	# (>=: sable_wren's authored loadout ALSO rides in via the body-loot seam on the same walk-over.)
	_check(c, proxy.item_count("revolver_round") >= rounds_before + 1 and RI.count(arena, "revolver_round") == 0,
		"ground ammo still gathers through the same walk-over seam (M13 behavior preserved)")
	_check(c, EB.events("ammo_picked_up").size() >= 1,
		"…and the ammo pickup still fires its distinct ammo_picked_up cue")
	RI.clear()

# (G2) ------------------------------------------------------------------------------------------
static func _g2_live_digest_after_live_gather(c: Dictionary, root: Node) -> void:
	print("[G2: after the LIVE gather, digest/advance succeeds via the live Interactable — no injected items]")
	var RM: Object = root.get_node("/root/RunManager")
	var AG: Object = root.get_node("/root/Agents")
	var P: Object = root.get_node("/root/Progression")
	RM.start_run()
	AG.rebuild()
	_check(c, P.pathway() == "hunter" and P.sequence() == 9, "a fresh Hunter run stands at Seq 9")

	var arena := "gather_arena"
	var spot := Vector2(400, 300)
	var proxy: Object = AG.ensure_player_proxy(spot, arena)
	_down_prey(root, "sable_wren", arena, spot)
	await _walk_over(root, spot)
	_check(c, proxy.item_count(P.characteristic_item()) >= 1,
		"the same-pathway Characteristic was gathered off the ground by the LIVE seam")

	# The LIVE digest/advance verb — the same Interactable flag the shipped digest station carries.
	var digest: Node = (load("res://scenes/Interactable.tscn") as PackedScene).instantiate()
	digest.digest_advance = true
	root.add_child(digest)
	await root.get_tree().process_frame
	digest._use()
	digest.free()
	_check(c, P.sequence() == 8,
		"the live digest verb advanced the Sequence 9 -> 8 fed ENTIRELY by the ground drop (no injection)")
	_check(c, proxy.item_count(P.characteristic_item()) == 0, "…consuming the gathered Characteristic")
	root.get_node("/root/RoomItems").clear()

# (G3) ------------------------------------------------------------------------------------------
static func _g3_cache_stocked_at_run_start(c: Dictionary, root: Node) -> void:
	print("[G3: the cult supply cache (scenario cache_items) is stocked onto the city floor by a LIVE run-start seam]")
	var RM: Object = root.get_node("/root/RunManager")
	var RI: Object = root.get_node("/root/RoomItems")
	var cache: Dictionary = _scenario_block("summoning").get("cache_items", {})
	_check(c, not cache.is_empty(), "scenario.json authors a summoning cache (%d offerings)" % cache.size())

	RM.start_run()
	for item_id in cache:
		_check(c, RI.count("city", String(item_id)) >= 1,
			"run start stocked '%s' onto the city floor (the LIVE placement — no CitySummoning node needed)" % String(item_id))
	# A second run re-stocks CLEAN (RoomItems.clear + re-place): exactly one of each, no accumulation.
	RM.start_run()
	for item_id in cache:
		_check(c, RI.count("city", String(item_id)) == 1,
			"a second start_run re-stocks exactly ONE '%s' (no double-stock, no carry)" % String(item_id))

# (G4) ------------------------------------------------------------------------------------------
static func _g4_sell_fork_with_live_gathered_characteristic(c: Dictionary, root: Node) -> void:
	print("[G4: the sell fork works with a LIVE-gathered characteristic — ground drop -> walk-over -> live counter -> coin]")
	var RM: Object = root.get_node("/root/RunManager")
	var AG: Object = root.get_node("/root/Agents")
	var RI: Object = root.get_node("/root/RoomItems")
	RM.start_run()
	AG.rebuild()

	var arena := "gather_arena"
	var spot := Vector2(400, 300)
	var proxy: Object = AG.ensure_player_proxy(spot, arena)
	_down_prey(root, "sable_wren", arena, spot)
	await _walk_over(root, spot)
	_check(c, proxy.item_count("hunter_characteristic") >= 1,
		"a hunter_characteristic was gathered off the ground by the LIVE walk-over seam")

	var price := int((_scenario_block("shop").get("sell_prices", {}) as Dictionary).get("hunter_characteristic", 0))
	_check(c, price > 0, "the shop authors a sell price for hunter_characteristic (%d coin)" % price)
	var coin_before: int = proxy.item_count("shilling")

	# The LIVE counter — the same Interactable flag Franky's counter carries in the scene.
	var counter: Node = (load("res://scenes/Interactable.tscn") as PackedScene).instantiate()
	counter.shop_sell_harvest = true
	root.add_child(counter)
	await root.get_tree().process_frame
	counter._use()
	counter.free()

	_check(c, proxy.item_count("hunter_characteristic") == 0,
		"the live counter SOLD the ground-gathered characteristic (the fork is reachable end-to-end)")
	_check(c, proxy.item_count("shilling") == coin_before + price,
		"…paying the authored price in coin (%d -> %d shillings)" % [coin_before, coin_before + price])
	RI.clear()
