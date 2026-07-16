extends SceneTree
## M32 — make the COUNTER-RITE USABLE (direction v2 §6). The rite is the ONLY player verb that pushes
## Doom DOWN, but a fresh-context playtest found it REACHABLE yet effectively UNUSABLE:
##   (1) nothing told the player it existed — no hint linked its ingredients to the anti-Doom rite;
##   (2) the ingredients only dropped from the cult supply cache, so a player who missed it was stuck.
## This harness pins the two fixes, each driven through a REAL live seam (not an internal helper):
##
##   (A) a once-per-run DIEGETIC discoverability HINT that fires EXACTLY once, at the first moment the
##       player holds BOTH counter-rite ingredients — driven through the real Inventory acquire seam
##       (Inventory.add -> item_added), surfaced on the HUD's existing thought channel. Not before the
##       second ingredient; not again on a later inventory change; re-armed by reset() (a fresh run).
##   (B) a reliable INGREDIENT SOURCE at Franky's counter: the shop stocks consecrated_chalk + candle at
##       an authored price; the REAL buy flow debits coin (proxy) and delivers the ingredient into the
##       ritual Inventory the counter-rite reads; after buying BOTH, CounterRite.can_perform() passes and
##       perform() reduces Doom. Buying is also the live end-to-end proof of (A): the shop buy funnels
##       through Inventory.add, so purchasing both ingredients ALSO surfaces the hint.
##
## Standalone: godot --headless --path tingen -s tests/test_counter_rite_usability.gd
## Folded into the suite via run_tests.gd `_test_counter_rite_usability` (SAME run_all() entry).

func _init() -> void:
	await process_frame
	await process_frame
	# B3 (retro): NEVER touch the player's REAL persistent profile (user://meta.json) — redirect
	# the meta slot to a test-scoped file before anything drives RunManager (tests/test_meta_isolation.gd).
	# N1 (sprint safety): sandbox EVERY persistent path (meta/save/settings/hints/playlog) into
	# user://test_sandbox/<run>/ and arm the write guard — see src/TestSandbox.gd.
	preload("res://src/TestSandbox.gd").activate(root)
	var r: Dictionary = run_all()
	print("\n=== test_counter_rite_usability: %d passed, %d failed ===" % [int(r["passed"]), int(r["failed"])])
	quit(1 if int(r["failed"]) > 0 else 0)

## The one entry point (returns {passed, failed}); folded into run_tests.gd.
static func run_all() -> Dictionary:
	var c := {"passed": 0, "failed": 0}
	var root: Node = (Engine.get_main_loop() as SceneTree).root
	_a_hint_fires_once_on_first_holding_both(c, root)
	_b_shop_sources_ingredients_and_makes_rite_usable(c, root)
	# LIVE-REACHABILITY layer (M32 review fix): the two deliverables must be reachable from the ACTUAL
	# live seams a player touches — not internal helpers. (C) drives the real world-pickup frame loop
	# (PlayerCombat._physics_process) so a ground gather of both ingredients bridges into the store the
	# rite reads (hint fires once + rite performable). (D) drives the real in-world counter node
	# (Interactable._use -> Shop.buy_ingredient). (E) proves Franky's hall actually WIRES that counter
	# for every authored ingredient. Each fails if its wire is removed.
	_c_world_gather_bridges_to_rite_store(c, root)
	_d_shop_ingredient_interactable_live_seam(c, root)
	_e_franky_scene_stocks_ingredient_counters(c, root)
	# Leave a clean world for whatever runs next in the shared suite.
	root.get_node("/root/RunManager").start_run()
	root.get_node("/root/Agents").rebuild()
	return c

# --- helpers ------------------------------------------------------------------------------------
static func _check(c: Dictionary, cond: bool, label: String) -> void:
	if cond:
		c["passed"] = int(c["passed"]) + 1
		print("  PASS  %s" % label)
	else:
		c["failed"] = int(c["failed"]) + 1
		printerr("  FAIL  %s" % label)

# (A) once-per-run discoverability hint, driven through the REAL Inventory acquire seam ----------
static func _a_hint_fires_once_on_first_holding_both(c: Dictionary, root: Node) -> void:
	print("[M32 (A): the discoverability hint fires EXACTLY once, at the first moment the player holds BOTH ingredients — via the real Inventory.add seam]")
	var CR: Object = root.get_node_or_null("/root/CounterRite")
	var INV: Object = root.get_node_or_null("/root/Inventory")
	var WS: Object = root.get_node_or_null("/root/WorldState")
	_check(c, CR != null and INV != null and WS != null, "CounterRite + Inventory + WorldState autoloads are present")
	if CR == null or INV == null or WS == null:
		return

	# The hint copy is DATA (rituals.json counter_rite.hint), not a literal in engine code.
	var hint_text := String(CR.rite_def().get("hint", ""))
	_check(c, hint_text != "", "the counter-rite authors a diegetic discoverability hint in data/rituals.json")

	# Arm a fresh run's hint latch + an empty ritual inventory.
	if CR.has_method("reset"):
		CR.reset()
	INV.clear()

	# Count how often the AUTHORED hint line reaches the HUD's thought channel (the real message seam).
	var seen := {"n": 0}
	var on_thought := func(t: String) -> void:
		if t == hint_text and hint_text != "":
			seen["n"] = int(seen["n"]) + 1
	WS.thought_requested.connect(on_thought)

	# Holding ONLY the first ingredient: the rite is not performable and the hint must NOT fire.
	INV.add("candle", 1)
	_check(c, not bool(CR.can_perform().get("ok", false)),
		"with only ONE ingredient the counter-rite is not yet performable")
	_check(c, int(seen["n"]) == 0, "the hint has NOT fired before the player holds BOTH ingredients")

	# Acquiring the SECOND ingredient makes it performable — the hint fires EXACTLY once, right here.
	INV.add("consecrated_chalk", 1)
	_check(c, bool(CR.can_perform().get("ok", false)),
		"holding BOTH ingredients the counter-rite is now performable")
	_check(c, int(seen["n"]) == 1,
		"the hint fired EXACTLY once, at the moment the player first holds both ingredients")

	# A LATER inventory change must NOT re-fire the once-per-run hint.
	INV.add("candle", 1)
	_check(c, int(seen["n"]) == 1, "a subsequent inventory change does NOT re-fire the once-per-run hint")
	WS.thought_requested.disconnect(on_thought)

	# Once-per-RUN: reset() (a fresh run) re-arms the hint so it fires again next run.
	if CR.has_method("reset"):
		CR.reset()
	INV.clear()
	var seen2 := {"n": 0}
	var on_thought2 := func(t: String) -> void:
		if t == hint_text and hint_text != "":
			seen2["n"] = int(seen2["n"]) + 1
	WS.thought_requested.connect(on_thought2)
	INV.add("candle", 1)
	INV.add("consecrated_chalk", 1)
	_check(c, int(seen2["n"]) == 1, "after reset() (a fresh run) the hint re-arms and fires once again")
	WS.thought_requested.disconnect(on_thought2)
	INV.clear()
	if CR.has_method("reset"):
		CR.reset()

# (C) LIVE world gather bridges to the rite's store — the real PlayerCombat pickup frame loop -----
## The M32 review's ship-blocker #2: live acquisition writes to the player-proxy inventory, never the
## ritual Inventory the rite reads, so a player who gathers the ingredients in the world could never
## work the rite (and never saw the hint). This drives the REAL frame seam — PlayerCombat._physics_process,
## exactly what the engine calls each physics frame — over ground ingredients placed via RoomItems, and
## asserts the gather (a) lands in the ritual Inventory, (b) fires the hint EXACTLY once on the second
## ingredient, and (c) makes CounterRite.can_perform() pass. Fails if the frame-loop bridge is removed.
static func _c_world_gather_bridges_to_rite_store(c: Dictionary, root: Node) -> void:
	print("[M32 (C): the LIVE world pickup (PlayerCombat._physics_process) of BOTH ground ingredients bridges into the ritual Inventory the rite reads — the hint fires once + the rite becomes performable]")
	var CR: Object = root.get_node_or_null("/root/CounterRite")
	var INV: Object = root.get_node_or_null("/root/Inventory")
	var WS: Object = root.get_node_or_null("/root/WorldState")
	var RI: Object = root.get_node_or_null("/root/RoomItems")
	var AG: Object = root.get_node_or_null("/root/Agents")
	_check(c, CR != null and INV != null and WS != null and RI != null and AG != null,
		"CounterRite + Inventory + WorldState + RoomItems + Agents autoloads are present")
	if CR == null or INV == null or WS == null or RI == null or AG == null:
		return

	AG.rebuild()
	INV.clear()
	RI.clear()
	if CR.has_method("reset"):
		CR.reset()

	# Stage the REAL player scene; its Combat child auto-picks up ground items every physics frame.
	var player: Node = (load("res://scenes/Player.tscn") as PackedScene).instantiate()
	root.add_child(player)
	var pc: Node = player.get_node("Combat")
	var room_id := "city"
	var pos := Vector2(400, 400)
	player.global_position = pos
	pc.proxy.room = room_id
	pc.proxy.position = pos

	# Count how often the AUTHORED hint reaches the HUD's thought channel.
	var hint_text := String(CR.rite_def().get("hint", ""))
	var seen := {"n": 0}
	var on_thought := func(t: String) -> void:
		if t == hint_text and hint_text != "":
			seen["n"] = int(seen["n"]) + 1
	WS.thought_requested.connect(on_thought)

	# Drop ONLY the first ingredient at the player's feet, then run ONE live physics frame.
	RI.place(room_id, "candle", pos, 1)
	pc._physics_process(1.0 / 60.0)
	_check(c, INV.count_of("candle") == 1,
		"the live world pickup delivered the candle into the ritual Inventory (world gather -> the store the rite reads)")
	_check(c, not bool(CR.can_perform().get("ok", false)),
		"with only one ground ingredient gathered the rite is not yet performable")
	_check(c, int(seen["n"]) == 0, "the hint has NOT fired on the first gathered ingredient")

	# Drop the SECOND ingredient, run another live physics frame — now both are in hand.
	RI.place(room_id, "consecrated_chalk", pos, 1)
	pc._physics_process(1.0 / 60.0)
	_check(c, INV.count_of("consecrated_chalk") == 1,
		"the live world pickup delivered the chalk into the ritual Inventory")
	_check(c, bool(CR.can_perform().get("ok", false)),
		"after gathering BOTH ground ingredients the counter-rite is performable (LIVE world path, no shop)")
	_check(c, int(seen["n"]) == 1,
		"the discoverability hint fired EXACTLY once off the LIVE world gather (not the direct autoload seam)")

	WS.thought_requested.disconnect(on_thought)
	player.free()
	INV.clear()
	RI.clear()
	if CR.has_method("reset"):
		CR.reset()

# (D) LIVE shop counter — the real Interactable interact path, not Shop.buy_ingredient directly ---
## The M32 review's ship-blocker #3: Shop.buy_ingredient had no live entry point (grep found only the
## test calling it). This drives the REAL in-world counter node — a bare Interactable carrying the
## generic shop_buy_ingredient flag + an authored item id, transacted through _use() (the ritual_interrupt
## pattern the whole shop is built on) — and asserts the interact DELIVERS the ingredient into the ritual
## Inventory the rite reads and DEBITS coin from the player proxy. Fails if the flag / _use dispatch is removed.
static func _d_shop_ingredient_interactable_live_seam(c: Dictionary, root: Node) -> void:
	print("[M32 (D): the REAL Franky ingredient counter (Interactable._use -> Shop.buy_ingredient) debits proxy coin + delivers into the ritual Inventory — not Shop.buy_ingredient called directly]")
	var CR: Object = root.get_node_or_null("/root/CounterRite")
	var INV: Object = root.get_node_or_null("/root/Inventory")
	var S: Object = root.get_node_or_null("/root/Shop")
	var AG: Object = root.get_node_or_null("/root/Agents")
	_check(c, CR != null and INV != null and S != null and AG != null,
		"CounterRite + Inventory + Shop + Agents autoloads are present")
	if CR == null or INV == null or S == null or AG == null:
		return
	if S.has_method("reset"):
		S.reset()
	AG.rebuild()
	var proxy: Object = AG.ensure_player_proxy(Vector2.ZERO, "mr_frankys_inner")
	INV.clear()
	if CR.has_method("reset"):
		CR.reset()

	var price := int(S.ingredient_prices().get("consecrated_chalk", 0)) if S.has_method("ingredient_prices") else 0
	proxy.inventory["shilling"] = price
	var coin_before: int = proxy.item_count("shilling")
	var chalk_before: int = INV.count_of("consecrated_chalk")

	# Build the REAL in-world counter node (the seam a live player triggers with E).
	var inter: Node = (load("res://scenes/Interactable.tscn") as PackedScene).instantiate()
	root.add_child(inter)
	_check(c, "shop_buy_ingredient" in inter,
		"the Interactable exposes the generic shop_buy_ingredient flag (a live counter node can carry it)")
	if not ("shop_buy_ingredient" in inter):
		inter.free()
		return
	inter.shop_buy_ingredient = true
	inter.shop_ingredient_item = "consecrated_chalk"
	inter._use()
	_check(c, INV.count_of("consecrated_chalk") == chalk_before + 1,
		"interacting with the counter DELIVERED chalk into the ritual Inventory the rite reads")
	_check(c, proxy.item_count("shilling") == coin_before - price,
		"…and DEBITED the authored price from the player proxy purse (costed, not free)")
	inter.free()
	INV.clear()
	if CR.has_method("reset"):
		CR.reset()

# (E) Franky's hall WIRES a live ingredient counter for every authored counter-rite ingredient ---
## Ship-blocker #3 continued: the source must exist in the shipped scene, not just as a method. This
## instantiates MrFrankysInner.tscn and asserts it carries a live shop_buy_ingredient counter for every
## ingredient the counter-rite authors (data-driven, no id literal). Fails if the counters are removed.
static func _e_franky_scene_stocks_ingredient_counters(c: Dictionary, root: Node) -> void:
	print("[M32 (E): Franky's hall (MrFrankysInner.tscn) wires a LIVE ingredient-buy counter for every counter-rite ingredient]")
	var CR: Object = root.get_node_or_null("/root/CounterRite")
	if CR == null:
		_check(c, false, "CounterRite autoload is present")
		return
	var room: Node = (load("res://scenes/MrFrankysInner.tscn") as PackedScene).instantiate()
	root.add_child(room)
	var stocked := {}
	for child in room.get_children():
		if not ("shop_buy_ingredient" in child):
			continue
		if bool(child.shop_buy_ingredient) and String(child.shop_ingredient_item) != "":
			stocked[String(child.shop_ingredient_item)] = true
	var ing: Dictionary = CR.ingredients()
	var all_wired := not ing.is_empty()
	for item_id in ing:
		if not stocked.has(String(item_id)):
			all_wired = false
	_check(c, all_wired,
		"MrFrankysInner wires a live shop_buy_ingredient counter for EVERY counter-rite ingredient (%s)" % [ing.keys()])
	_check(c, stocked.has("consecrated_chalk"), "…including a consecrated_chalk counter")
	_check(c, stocked.has("candle"), "…including a candle counter")
	room.free()

# (B) shop ingredient source + the REAL buy flow makes the rite usable ---------------------------
static func _b_shop_sources_ingredients_and_makes_rite_usable(c: Dictionary, root: Node) -> void:
	print("[M32 (B): Franky's counter stocks the counter-rite ingredients; the REAL buy flow debits coin and makes the rite performable (Doom drops)]")
	var CR: Object = root.get_node_or_null("/root/CounterRite")
	var INV: Object = root.get_node_or_null("/root/Inventory")
	var WS: Object = root.get_node_or_null("/root/WorldState")
	var S: Object = root.get_node_or_null("/root/Shop")
	var M: Object = root.get_node_or_null("/root/Meters")
	var AG: Object = root.get_node_or_null("/root/Agents")
	_check(c, S != null and CR != null and INV != null and AG != null and M != null,
		"Shop + CounterRite + Inventory + Agents + Meters autoloads are present")
	if S == null or CR == null or INV == null or AG == null or M == null:
		return

	# The shop authors a BUY price for each counter-rite ingredient.
	var prices: Dictionary = S.ingredient_prices() if S.has_method("ingredient_prices") else {}
	var chalk_price := int(prices.get("consecrated_chalk", 0))
	var candle_price := int(prices.get("candle", 0))
	_check(c, chalk_price > 0, "the shop stocks consecrated_chalk at a price (got %d)" % chalk_price)
	_check(c, candle_price > 0, "the shop stocks candle at a price (got %d)" % candle_price)

	# A fresh player proxy (holds the coin) + an empty ritual inventory + an armed hint.
	AG.rebuild()
	var proxy: Object = AG.ensure_player_proxy(Vector2.ZERO, "mr_frankys_inner")
	_check(c, proxy != null, "the player proxy exists (it carries the coin the buy debits)")
	if proxy == null:
		return
	INV.clear()
	if CR.has_method("reset"):
		CR.reset()

	# Watch the hint too: buying both ingredients is the end-to-end LIVE proof of (A).
	var hint_text := String(CR.rite_def().get("hint", ""))
	var seen := {"n": 0}
	var on_thought := func(t: String) -> void:
		if t == hint_text and hint_text != "":
			seen["n"] = int(seen["n"]) + 1
	WS.thought_requested.connect(on_thought)

	# Fund the purse for exactly both ingredients.
	proxy.inventory["shilling"] = chalk_price + candle_price
	var coin_before: int = proxy.item_count("shilling")

	# BUY the chalk — coin is debited (from the proxy), the ingredient lands in the ritual Inventory
	# the counter-rite reads (NOT the proxy: the two stores are bridged only here).
	var r1: Dictionary = S.buy_ingredient("consecrated_chalk") if S.has_method("buy_ingredient") else {}
	_check(c, bool(r1.get("ok", false)), "buying consecrated_chalk succeeds")
	_check(c, proxy.item_count("shilling") == coin_before - chalk_price,
		"coin was DEBITED by the chalk price (costed, not free)")
	_check(c, INV.count_of("consecrated_chalk") == 1,
		"the bought chalk landed in the ritual Inventory the counter-rite reads")
	_check(c, not bool(CR.can_perform().get("ok", false)),
		"with only chalk bought the rite is not yet performable")

	# BUY the candle — now both ingredients are in the ritual Inventory.
	var r2: Dictionary = S.buy_ingredient("candle") if S.has_method("buy_ingredient") else {}
	_check(c, bool(r2.get("ok", false)), "buying candle succeeds")
	_check(c, INV.count_of("candle") == 1, "the bought candle landed in the ritual Inventory")
	_check(c, proxy.item_count("shilling") == 0, "coin fully debited after buying both ingredients")

	# The whole point: after the REAL buy flow the counter-rite is performable and pushes Doom DOWN.
	_check(c, bool(CR.can_perform().get("ok", false)),
		"after buying BOTH ingredients the counter-rite passes its ingredient check")
	_check(c, int(seen["n"]) == 1,
		"buying both ingredients at the shop ALSO surfaced the discoverability hint (end-to-end live wire)")
	WS.thought_requested.disconnect(on_thought)

	M.set_meter("doom", 50.0)
	M.set_meter("notice", 0.0)
	var doom_before: float = M.get_meter("doom")
	var res: Dictionary = CR.perform()
	_check(c, bool(res.get("ok", false)), "the counter-rite performs off SHOP-bought ingredients")
	_check(c, M.get_meter("doom") < doom_before,
		"Doom went DOWN (%.1f -> %.1f) — the shop path makes the anti-Doom verb usable" % [doom_before, M.get_meter("doom")])

	# Refusals are clean: an item outside the ingredient table, and an unfunded buy.
	var bad: Dictionary = S.buy_ingredient("revolver") if S.has_method("buy_ingredient") else {}
	_check(c, not bool(bad.get("ok", false)) and String(bad.get("reason", "")) == "unknown_item",
		"buying an item outside the ingredient table refuses (unknown_item)")
	proxy.inventory["shilling"] = 0
	var candle_pre: int = INV.count_of("candle")
	var poor: Dictionary = S.buy_ingredient("candle") if S.has_method("buy_ingredient") else {}
	_check(c, not bool(poor.get("ok", false)) and String(poor.get("reason", "")) == "no_coin",
		"an unfunded ingredient buy refuses cleanly (no_coin)")
	_check(c, INV.count_of("candle") == candle_pre, "…and the refused buy delivered no ingredient")

	INV.clear()
	if CR.has_method("reset"):
		CR.reset()
