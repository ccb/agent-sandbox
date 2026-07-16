extends SceneTree
## M15 — Franky's shop: buy ammo + sell harvest (the coin loop made real). TDD harness.
## Run: godot --headless --path tingen -s tests/test_shop.gd
##
## Covers the M15 contract:
##   (a) BUY is costed + latched: coin -> rounds at the authored price; without coin it refuses
##       cleanly; the per-run stock latch caps restocks (no infinite tap — the M13 review warning
##       on the old free franky_buy() is closed) and resets next run.
##   (b) SELL is real coin: every carried characteristic in the authored sell table converts to
##       coin; selling the LAST hunter_characteristic genuinely forfeits the advance fuel
##       (Progression.can_advance flips false — the push-your-luck choice is real).
##   (c) Per-run reset + within-run snapshot/restore: the stock latch rides the nightly
##       checkpoint; coin rides the checkpoint TOO (N2 A2 — the player-proxy inventory is part of
##       the snapshot manifest now, so a death-restore wakes with the checkpointed purse, not the
##       day-1 loadout; the old "died-with-proxy" re-grant was the audited data-loss bug).
##   (d) The opening fork's SELL word leads somewhere real: GMOpening.choose_harvest("sell")
##       stores the choice + surfaces the authored shop hint (scenario `opening.sell_hint`).
##   (e) The counter is WIRED: MrFrankysInner.tscn carries the shop Interactables with the generic
##       shop_sell_harvest / shop_buy_ammo export flags (the ritual_interrupt pattern), split into
##       a SELL-only counter and a BUY-only shelf (review fix: a rounds run must never auto-sell
##       the carried advance fuel), and _use() transacts; AmmoSpawn.franky_buy() is no free tap.
##   (f) Determinism guard: coin never enters try_pay — an empty gun still refuses no_ammo no
##       matter how rich the player is (economy never touches combat semantics).
##   (g) The fork is PRESENTED live (review fix): the published agent_downed FACT for the staged
##       opening Beyonder presents the fork by itself — no manual on_butcher_downed() call — and
##       the narration surfaces the authored options + sell_hint, so a live player actually SEES
##       the SELL word that leads to Franky's coin.

var _passed: int = 0
var _failed: int = 0

## Authored TUNING numbers pinned by this harness (mirror data/scenario.json `shop`).
const COIN_ITEM := "shilling"
const START_COIN := 5
const BUY_QTY := 6
const BUY_PRICE := 3   # M26 BALANCE RETUNE #4: 4 -> 3 (one 6sh tainted sale now buys TWO round boxes)
const RESTOCKS_PER_RUN := 3
const SELL_TAINTED := 6
const SELL_HUNTER := 10

func _init() -> void:
	await process_frame
	await process_frame
	# B3 (retro): NEVER touch the player's REAL persistent profile (user://meta.json) — redirect
	# the meta slot to a test-scoped file before anything drives RunManager (tests/test_meta_isolation.gd).
	# N1 (sprint safety): sandbox EVERY persistent path (meta/save/settings/hints/playlog) into
	# user://test_sandbox/<run>/ and arm the write guard — see src/TestSandbox.gd.
	preload("res://src/TestSandbox.gd").activate(root)

	_test_a_buy_costed_and_latched()
	_test_b_sell_real_coin_and_fuel_forfeit()
	_test_c_per_run_reset_and_snapshot()
	_test_d_opening_fork_sell_leads_to_shop()
	_test_e_counter_interactable_wired()
	_test_f_coin_never_enters_try_pay()
	_test_g_live_fork_presentation()

	print("\n=== test_shop: %d passed, %d failed ===" % [_passed, _failed])
	quit(1 if _failed > 0 else 0)

func _ok(cond: bool, label: String) -> void:
	if cond:
		_passed += 1
		print("  PASS  %s" % label)
	else:
		_failed += 1
		printerr("  FAIL  %s" % label)

# ──────────────────────────────────────────────────────────────────────────────
# (a) BUY: coin -> rounds at the authored price; refuses without coin; stock latch
# ──────────────────────────────────────────────────────────────────────────────
func _test_a_buy_costed_and_latched() -> void:
	print("[a: buy is costed + stock-latched — no free infinite tap]")
	var S: Object = root.get_node_or_null("/root/Shop")
	_ok(S != null, "Shop autoload is registered")
	if S == null:
		return
	var p := _fresh_proxy()
	_ok(p.item_count(COIN_ITEM) == START_COIN,
		"the loadout grants %d starting shillings (got %d)" % [START_COIN, p.item_count(COIN_ITEM)])
	_ok(S.buy_price() == BUY_PRICE and S.buy_qty() == BUY_QTY,
		"authored buy price: %d rounds for %d shillings" % [BUY_QTY, BUY_PRICE])
	_ok(S.restocks_per_run() == RESTOCKS_PER_RUN,
		"authored stock: %d restocks per run" % RESTOCKS_PER_RUN)

	# A funded buy converts coin -> rounds at the authored price.
	var rounds_before := p.item_count("revolver_round")
	var r1: Dictionary = S.buy_ammo()
	_ok(bool(r1.get("ok", false)), "a funded buy succeeds")
	_ok(p.item_count("revolver_round") == rounds_before + BUY_QTY,
		"rounds +%d after the buy" % BUY_QTY)
	_ok(p.item_count(COIN_ITEM) == START_COIN - BUY_PRICE,
		"coin -%d after the buy (COSTED, not free)" % BUY_PRICE)
	_ok(S.restocks_left() == RESTOCKS_PER_RUN - 1, "stock latch ticked (restocks_left == %d)" % (RESTOCKS_PER_RUN - 1))

	# Without coin it refuses cleanly — nothing changes.
	p.inventory[COIN_ITEM] = BUY_PRICE - 1
	var rounds_mid := p.item_count("revolver_round")
	var r2: Dictionary = S.buy_ammo()
	_ok(not bool(r2.get("ok", false)) and String(r2.get("reason", "")) == "no_coin",
		"an unfunded buy refuses with no_coin")
	_ok(p.item_count("revolver_round") == rounds_mid and p.item_count(COIN_ITEM) == BUY_PRICE - 1,
		"…and neither rounds nor coin changed on the refusal")

	# The stock latch caps per-run restocks — the infinite tap is closed.
	p.inventory[COIN_ITEM] = 100
	var r3: Dictionary = S.buy_ammo()
	var r4: Dictionary = S.buy_ammo()
	_ok(bool(r3.get("ok", false)) and bool(r4.get("ok", false)),
		"buys 2 and 3 succeed while stock remains")
	_ok(S.restocks_left() == 0, "stock exhausted after %d buys" % RESTOCKS_PER_RUN)
	var rounds_capped := p.item_count("revolver_round")
	var coin_capped := p.item_count(COIN_ITEM)
	var r5: Dictionary = S.buy_ammo()
	_ok(not bool(r5.get("ok", false)) and String(r5.get("reason", "")) == "out_of_stock",
		"buy %d refuses with out_of_stock (per-run cap — NOT an infinite tap)" % (RESTOCKS_PER_RUN + 1))
	_ok(p.item_count("revolver_round") == rounds_capped and p.item_count(COIN_ITEM) == coin_capped,
		"…and the refused buy moved neither rounds nor coin")
	_teardown()

# ──────────────────────────────────────────────────────────────────────────────
# (b) SELL: carried characteristics -> coin; selling the last fuel forfeits advance
# ──────────────────────────────────────────────────────────────────────────────
func _test_b_sell_real_coin_and_fuel_forfeit() -> void:
	print("[b: sell pays real coin; selling the last hunter characteristic forfeits the climb]")
	var S: Object = root.get_node_or_null("/root/Shop")
	var PR: Object = root.get_node("/root/Progression")
	if S == null:
		_ok(false, "Shop autoload missing — cannot test sell")
		return
	var p := _fresh_proxy()
	p.inventory[COIN_ITEM] = 0

	# Authored sell table.
	var prices: Dictionary = S.sell_prices()
	_ok(int(prices.get("tainted_characteristic", 0)) == SELL_TAINTED,
		"authored sell price: tainted_characteristic == %d" % SELL_TAINTED)
	_ok(int(prices.get("hunter_characteristic", 0)) == SELL_HUNTER,
		"authored sell price: hunter_characteristic == %d (progression fuel priced ABOVE tainted)" % SELL_HUNTER)

	# Arm a genuine pending advance: Seq 9, one hunter characteristic, acting deed done.
	PR.reset()
	p.add_item("tainted_characteristic", 2)
	p.add_item("hunter_characteristic", 1)
	PR.mark_deed_done()
	_ok(bool(PR.can_advance().get("ok", false)),
		"BEFORE the sell the advance is live (fuel + deed in hand)")

	# Sell everything carried from the authored table.
	var s1: Dictionary = S.sell_harvest()
	var expected_coins := 2 * SELL_TAINTED + 1 * SELL_HUNTER
	_ok(bool(s1.get("ok", false)), "sell_harvest succeeds with characteristics in hand")
	_ok(int(s1.get("coins", -1)) == expected_coins,
		"paid the authored total: 2 tainted + 1 hunter == %d shillings (got %d)" % [expected_coins, int(s1.get("coins", -1))])
	_ok(p.item_count(COIN_ITEM) == expected_coins, "the coin is REAL — it landed in the inventory")
	_ok(p.item_count("tainted_characteristic") == 0 and p.item_count("hunter_characteristic") == 0,
		"every carried characteristic left the inventory")

	# M26 BALANCE RETUNE #1: the sold hunter characteristic WAS the advance fuel, but selling one fuel
	# now latches a pity margin — the advance stays reachable (the trap is gone). The deep margin proof
	# (sell one -> still reach Seq 7; sell BOTH -> still forfeits) lives in tests/test_balance.gd.
	var gate: Dictionary = PR.can_advance()
	_ok(bool(gate.get("ok", false)),
		"AFTER selling one fuel the advance stays reachable — the M15 sell-fork TRAP is gone (pity margin)")

	# Selling with nothing to sell refuses cleanly.
	var s2: Dictionary = S.sell_harvest()
	_ok(not bool(s2.get("ok", false)) and String(s2.get("reason", "")) == "nothing_to_sell",
		"an empty-handed sell refuses with nothing_to_sell")
	_ok(p.item_count(COIN_ITEM) == expected_coins, "…and coin is untouched by the refusal")
	PR.reset()
	_teardown()

# ──────────────────────────────────────────────────────────────────────────────
# (c) Per-run reset + within-run snapshot/restore (probe restart)
# ──────────────────────────────────────────────────────────────────────────────
func _test_c_per_run_reset_and_snapshot() -> void:
	print("[c: coin + stock reset per run; the stock latch rides the nightly checkpoint]")
	var S: Object = root.get_node_or_null("/root/Shop")
	var RM: Object = root.get_node("/root/RunManager")
	if S == null:
		_ok(false, "Shop autoload missing — cannot test reset/snapshot")
		return

	# Fresh run: full stock + loadout coin.
	RM.start_run()
	var p := _ensure_proxy()
	_ok(S.restocks_left() == RESTOCKS_PER_RUN, "a fresh run opens with full stock (%d)" % RESTOCKS_PER_RUN)
	_ok(p.item_count(COIN_ITEM) == START_COIN, "a fresh run opens with the loadout coin (%d)" % START_COIN)

	# Buy once, checkpoint, buy again + spend everything.
	S.buy_ammo()
	_ok(S.restocks_left() == RESTOCKS_PER_RUN - 1, "one restock used before the checkpoint")
	var coin_at_cp: int = p.item_count(COIN_ITEM)   # the purse the nightly snapshot records
	RM.checkpoint_night()
	p.inventory[COIN_ITEM] = 100
	S.buy_ammo()
	p.inventory[COIN_ITEM] = 0
	_ok(S.restocks_left() == RESTOCKS_PER_RUN - 2, "a second restock used after the checkpoint")

	# Death -> restore to the checkpoint: the stock latch comes back to its checkpointed value.
	RM.end_run("death")
	_ok(S.restocks_left() == RESTOCKS_PER_RUN - 1,
		"after the death restore the stock latch is back at the CHECKPOINT value (%d left)" % (RESTOCKS_PER_RUN - 1))
	# N2 (A2): coin rides the checkpoint like the rest of the proxy inventory — the restore wakes
	# with the CHECKPOINTED purse (the old "died-with-proxy" fresh-loadout re-grant was the audited
	# data-loss bug: every restore silently reset the player's shillings to day-1).
	var p2 := _ensure_proxy()
	_ok(p2.item_count(COIN_ITEM) == coin_at_cp,
		"after the restore the proxy carries the CHECKPOINTED purse (%d, not the day-1 loadout)" % coin_at_cp)

	# A brand-new run resets the latch fully.
	RM.start_run()
	_ok(S.restocks_left() == RESTOCKS_PER_RUN, "start_run() restores the FULL stock (%d) — no carry" % RESTOCKS_PER_RUN)
	var p3 := _ensure_proxy()
	_ok(p3.item_count(COIN_ITEM) == START_COIN, "start_run() resets coin to the loadout (%d)" % START_COIN)
	_teardown()

# ──────────────────────────────────────────────────────────────────────────────
# (d) The opening fork's SELL word leads to the shop
# ──────────────────────────────────────────────────────────────────────────────
func _test_d_opening_fork_sell_leads_to_shop() -> void:
	print("[d: the harvest fork's SELL option is honest — it stores the choice + points at the counter]")
	var GMO: Object = root.get_node("/root/GMOpening")
	var fork: Dictionary = GMO.harvest_fork()
	var opts: Array = fork.get("options", [])
	_ok(opts.has("sell"), "the authored fork still offers sell")
	_ok(GMO.has_method("choose_harvest"), "GMOpening.choose_harvest() exists — the fork verb has a seam")
	if not GMO.has_method("choose_harvest"):
		return
	var r: Dictionary = GMO.choose_harvest("sell")
	_ok(bool(r.get("ok", false)), "choose_harvest('sell') is accepted")
	_ok(String(r.get("hint", "")) != "",
		"…and returns the authored shop hint (scenario opening.sell_hint): '%s'" % String(r.get("hint", "")))
	_ok(String(GMO.harvest_choice()) == "sell", "the choice is stored for the run")
	var bad: Dictionary = GMO.choose_harvest("barter")
	_ok(not bool(bad.get("ok", false)), "an option outside the authored fork is refused")
	_ok(String(GMO.harvest_choice()) == "sell", "…and does not clobber the stored choice")
	GMO.reset()
	_ok(String(GMO.harvest_choice()) == "", "GMOpening.reset() scrubs the stored choice (per-run latch)")

# ──────────────────────────────────────────────────────────────────────────────
# (e) The counter Interactable is wired (generic export flags, no NPC-id branch)
# ──────────────────────────────────────────────────────────────────────────────
func _test_e_counter_interactable_wired() -> void:
	print("[e: MrFrankysInner splits the trade into a SELL-only counter + BUY-only shelf; _use() transacts; franky_buy is no free tap]")
	# The room splits the trade into TWO deliberate stops (review fix: with both flags on one
	# interactable, walking up just to buy rounds silently auto-sold the carried advance fuel).
	var packed: PackedScene = load("res://scenes/MrFrankysInner.tscn")
	var room: Node = packed.instantiate()
	root.add_child(room)
	var sell_only := 0
	var buy_only := 0
	var both := 0
	for child in room.get_children():
		if not ("shop_buy_ammo" in child):
			continue
		var s := bool(child.shop_sell_harvest)
		var b := bool(child.shop_buy_ammo)
		if s and b:
			both += 1
		elif s:
			sell_only += 1
		elif b:
			buy_only += 1
	_ok(sell_only == 1, "the room has exactly ONE sell-only interactable (selling fuel is a deliberate act)")
	_ok(buy_only == 1, "the room has exactly ONE buy-only interactable (the rounds shelf)")
	_ok(both == 0, "NO interactable in the room sets both flags — a buy stop can never auto-sell the fuel")
	room.free()

	# A bare Interactable with the flags transacts through _use() (the ritual_interrupt pattern).
	var S: Object = root.get_node_or_null("/root/Shop")
	if S == null:
		_ok(false, "Shop autoload missing — cannot test _use() transaction")
		return
	S.reset()
	var p := _fresh_proxy()
	p.inventory[COIN_ITEM] = 0
	p.add_item("tainted_characteristic", 1)
	var inter: Node = (load("res://scenes/Interactable.tscn") as PackedScene).instantiate()
	root.add_child(inter)
	if not ("shop_buy_ammo" in inter):
		_ok(false, "Interactable lacks the shop export flags")
		inter.free()
		_teardown()
		return
	inter.shop_sell_harvest = true
	inter.shop_buy_ammo = true
	var rounds_before := p.item_count("revolver_round")
	inter._use()
	# Sell-then-buy in ONE use: the tainted sale (6) funds the round box (4).
	_ok(p.item_count("tainted_characteristic") == 0, "_use() SOLD the carried characteristic")
	_ok(p.item_count("revolver_round") == rounds_before + BUY_QTY,
		"_use() then BOUGHT a box of rounds with the sale coin (+%d)" % BUY_QTY)
	_ok(p.item_count(COIN_ITEM) == SELL_TAINTED - BUY_PRICE,
		"coin after sell-then-buy == %d (sale %d - price %d)" % [SELL_TAINTED - BUY_PRICE, SELL_TAINTED, BUY_PRICE])
	inter.free()

	# Regression (review LOW — accidental fuel forfeit): a BUY-only stop must never sell the
	# carried advance fuel as a side effect of buying rounds.
	S.reset()
	var p2 := _fresh_proxy()
	p2.inventory[COIN_ITEM] = BUY_PRICE
	p2.add_item("hunter_characteristic", 1)
	var buy_stop: Node = (load("res://scenes/Interactable.tscn") as PackedScene).instantiate()
	root.add_child(buy_stop)
	buy_stop.shop_buy_ammo = true
	var rounds_pre := p2.item_count("revolver_round")
	buy_stop._use()
	_ok(p2.item_count("hunter_characteristic") == 1,
		"a buy-only use left the hunter_characteristic IN HAND (no accidental fuel forfeit)")
	_ok(p2.item_count("revolver_round") == rounds_pre + BUY_QTY and p2.item_count(COIN_ITEM) == 0,
		"…while the buy itself went through (+%d rounds, -%d coin)" % [BUY_QTY, BUY_PRICE])
	buy_stop.free()

	# The old dead verb is now honest: franky_buy() with no coin refuses (no free rounds).
	var AS: Object = root.get_node_or_null("/root/AmmoSpawn")
	S.reset()
	p.inventory[COIN_ITEM] = 0
	var rounds_pre_tap := p.item_count("revolver_round")
	var tap: Variant = AS.franky_buy()
	var tap_ok := tap is Dictionary and bool((tap as Dictionary).get("ok", false))
	_ok(not tap_ok, "AmmoSpawn.franky_buy() refuses without coin — the free tap is CLOSED")
	_ok(p.item_count("revolver_round") == rounds_pre_tap, "…and granted no rounds")
	_teardown()

# ──────────────────────────────────────────────────────────────────────────────
# (f) Determinism guard: coin never enters try_pay
# ──────────────────────────────────────────────────────────────────────────────
func _test_f_coin_never_enters_try_pay() -> void:
	print("[f: economy never enters combat — a rich player with no rounds still refuses no_ammo]")
	var player = load("res://scenes/Player.tscn").instantiate()
	root.add_child(player)
	var pc: Node = player.get_node("Combat")
	pc.proxy.room = "t_shop_arena"
	pc.proxy.position = Vector2.ZERO
	pc.proxy.inventory[COIN_ITEM] = 999
	pc.proxy.inventory.erase("revolver_round")
	var r: Dictionary = pc.on_attack_pressed(Vector2.RIGHT)
	_ok(not bool(r.get("ok", false)) and String(r.get("reason", "")) == "no_ammo",
		"999 shillings + 0 rounds -> no_ammo (coin is NOT ammo; try_pay semantics untouched)")
	_ok(pc.proxy.item_count(COIN_ITEM) == 999, "…and the refusal spent no coin")
	player.free()
	_teardown()

# ──────────────────────────────────────────────────────────────────────────────
# (g) The fork is PRESENTED live off the agent_downed fact (review fix)
# ──────────────────────────────────────────────────────────────────────────────
func _test_g_live_fork_presentation() -> void:
	print("[g: downing the butcher LIVE presents the fork + surfaces the sell hint — no manual director call]")
	var RM: Object = root.get_node("/root/RunManager")
	var GMO: Object = root.get_node("/root/GMOpening")
	var AG: Object = root.get_node("/root/Agents")
	var EB: Object = root.get_node("/root/EventBus")
	var WS: Object = root.get_node("/root/WorldState")
	RM.start_run()
	_ok(not GMO.harvest_presented(), "fresh run: the fork is not yet presented")
	var seen := {"forks": 0, "text": ""}
	var on_fork := func(_fork: Dictionary) -> void: seen["forks"] = int(seen["forks"]) + 1
	var on_thought := func(text: String) -> void: seen["text"] = String(seen["text"]) + " " + text
	GMO.harvest_fork_presented.connect(on_fork)
	WS.thought_requested.connect(on_thought)
	var kell: Agent = AG.get_agent("bram_kell")
	kell.downed = true
	EB.emit_event("agent_downed", {"actor": "player", "target": "bram_kell"})
	GMO.harvest_fork_presented.disconnect(on_fork)
	WS.thought_requested.disconnect(on_thought)
	_ok(GMO.harvest_presented(),
		"the published agent_downed FACT alone presented the fork (live path, no on_butcher_downed() call)")
	_ok(int(seen["forks"]) == 1, "harvest_fork_presented fired exactly once at the downing")
	var narration := String(seen["text"])
	var sell_hint := String(GMO.OPENING.get("sell_hint", ""))
	_ok(sell_hint != "" and narration.find(sell_hint) != -1,
		"the live presentation surfaces the authored sell_hint (the SELL word reaches a live player)")
	var opts: Array = GMO.harvest_fork().get("options", [])
	var all_named := not opts.is_empty()
	for o in opts:
		if narration.to_lower().find(String(o).to_lower()) == -1:
			all_named = false
	_ok(all_named, "the live presentation names every authored fork option: %s" % [opts])
	# Idempotent: a repeat downed fact does not re-present the fork.
	var again := {"n": 0}
	var cb2 := func(_f: Dictionary) -> void: again["n"] = int(again["n"]) + 1
	GMO.harvest_fork_presented.connect(cb2)
	EB.emit_event("agent_downed", {"actor": "player", "target": "bram_kell"})
	GMO.harvest_fork_presented.disconnect(cb2)
	_ok(int(again["n"]) == 0, "a repeat downed fact does not re-present (per-run latch holds)")
	GMO.reset()
	_teardown()

# ──────────────────────────────────────────────────────────────────────────────
# Helpers
# ──────────────────────────────────────────────────────────────────────────────
## A brand-new player proxy (rebuild clears the ephemeral proxy -> next ensure CREATES it fresh
## with the scenario loadout).
func _fresh_proxy() -> Agent:
	var AG: Object = root.get_node("/root/Agents")
	AG.rebuild()
	return AG.ensure_player_proxy(Vector2.ZERO, "mr_frankys_inner")

## Ensure (create-if-missing) the proxy WITHOUT clearing the roster first.
func _ensure_proxy() -> Agent:
	var AG: Object = root.get_node("/root/Agents")
	return AG.ensure_player_proxy(Vector2.ZERO, "mr_frankys_inner")

func _teardown() -> void:
	root.get_node("/root/Agents").rebuild()
	root.get_node("/root/EventBus").clear()
	var S: Object = root.get_node_or_null("/root/Shop")
	if S != null and S.has_method("reset"):
		S.reset()
