extends Node
## Franky's counter (autoload `Shop`) — M15: the coin economy loop made real.
##
## Two DATA verbs an in-world Interactable wires to via generic export flags
## (`shop_sell_harvest` / `shop_buy_ammo` — the same pattern M7 used for `ritual_interrupt`):
##
##   * buy_ammo():     coin -> rounds at the authored price, capped by a PER-RUN stock latch —
##                     the M13 review warning ("franky_buy as written has no cost and no latch
##                     = a free infinite tap if wired naively") is closed here: the buy costs
##                     coin and refuses after `restocks_per_run` boxes.
##   * sell_harvest(): every carried item listed in the authored sell table -> coin. Selling
##                     the LAST same-pathway characteristic genuinely forfeits the advance fuel
##                     (Progression.can_advance flips false) — the fork's push-your-luck choice.
##
## Engine-neutral (CLAUDE.md hard rule): the coin item, prices, quantities and the stock cap are
## all authored in data/scenario.json's `shop` block; no NPC-id branch lives here — the counter
## Interactable carries the flags, whichever shop it stands in. Determinism: pure inventory
## arithmetic, no RNG; combat untouched — coin NEVER enters PlayerCombat.try_pay (the `ammo`
## cost still resolves only through the carried weapon's ammo_item count).
##
## Run lifecycle (the sprint leak lesson): reset() restores the stock latch to full — called by
## RunManager._reset_run_world so a fresh run never inherits a spent shelf. The latch rides the
## nightly checkpoint via to_dict()/from_dict() (a death restore returns the shelf to its
## checkpointed state). Coin itself lives in the PLAYER PROXY's inventory, so it follows the
## proxy's died-with-proxy loadout semantics — exactly like the 12 starting rounds (M13 decision).

const SCENARIO_PATH := "res://data/scenario.json"

## The authored shop block, loaded once (static: identity data, same pattern as AmmoSpawn).
static var SHOP: Dictionary = _load_shop()

static func _load_shop() -> Dictionary:
	if not FileAccess.file_exists(SCENARIO_PATH):
		push_warning("Shop: missing %s" % SCENARIO_PATH)
		return {}
	var parsed: Variant = JSON.parse_string(FileAccess.get_file_as_string(SCENARIO_PATH))
	if not (parsed is Dictionary):
		return {}
	var block: Variant = (parsed as Dictionary).get("shop", {})
	return block if block is Dictionary else {}

## Per-run latch: ammo restocks bought THIS run. reset() scrubs it; it rides the snapshot.
var _restocks_used: int = 0

# --- authored reads (pure) ----------------------------------------------------------------------
func coin_item() -> String:
	return String(SHOP.get("coin_item", "shilling"))

func buy_item() -> String:
	return String((SHOP.get("buy_ammo", {}) as Dictionary).get("item", "revolver_round"))

func buy_qty() -> int:
	return int((SHOP.get("buy_ammo", {}) as Dictionary).get("qty", 6))

func buy_price() -> int:
	return int((SHOP.get("buy_ammo", {}) as Dictionary).get("price", 4))

func restocks_per_run() -> int:
	return int(SHOP.get("restocks_per_run", 3))

func restocks_left() -> int:
	return maxi(0, restocks_per_run() - _restocks_used)

## The authored sell table {item_id -> price in coin}, shape-guarded copy (read-only view).
func sell_prices() -> Dictionary:
	var raw: Variant = SHOP.get("sell_prices", {})
	if not (raw is Dictionary):
		return {}
	var out: Dictionary = {}
	for k in (raw as Dictionary):
		if typeof((raw as Dictionary)[k]) in [TYPE_INT, TYPE_FLOAT]:
			out[String(k)] = int((raw as Dictionary)[k])
	return out

## M32 — the authored counter-rite ingredient table {item_id -> buy price in coin}, shape-guarded copy
## (same numeric-only filter as sell_prices, so the authored `_doc` string key is dropped). Empty when
## the shop authors no ingredient stock.
func ingredient_prices() -> Dictionary:
	var raw: Variant = SHOP.get("buy_ingredients", {})
	if not (raw is Dictionary):
		return {}
	var out: Dictionary = {}
	for k in (raw as Dictionary):
		if typeof((raw as Dictionary)[k]) in [TYPE_INT, TYPE_FLOAT]:
			out[String(k)] = int((raw as Dictionary)[k])
	return out

# --- the verbs ------------------------------------------------------------------------------------
## BUY one box of rounds: check stock, check coin, then deduct coin + grant rounds (check-all-
## then-transact, mirroring try_pay's no-half-pay discipline). Returns
## {ok, reason, item, qty, cost, restocks_left}. Refusal precedence: out_of_stock > no_coin —
## a bare shelf refuses before the purse is even opened.
func buy_ammo() -> Dictionary:
	var proxy = _player_proxy()
	if proxy == null:
		return {"ok": false, "reason": "no_player"}
	if _restocks_used >= restocks_per_run():
		return {"ok": false, "reason": "out_of_stock", "restocks_left": 0}
	var price := buy_price()
	var coin := coin_item()
	if proxy.item_count(coin) < price:
		return {"ok": false, "reason": "no_coin", "restocks_left": restocks_left()}
	proxy.remove_item(coin, price)
	proxy.add_item(buy_item(), buy_qty())
	_restocks_used += 1
	var eb := _al("EventBus")
	if eb != null:
		eb.emit_event("ammo_purchased",
			{"item": buy_item(), "qty": buy_qty(), "cost": price, "source": "shop"})
	return {"ok": true, "reason": "", "item": buy_item(), "qty": buy_qty(),
		"cost": price, "restocks_left": restocks_left()}

## M32 — BUY one counter-rite ingredient: coin -> a ritual ingredient at the authored price, so the
## counter-rite (the only anti-Doom verb) is no longer locked behind the cult cache alone. Cross-store
## by design: coin is DEBITED from the player proxy (where the purse lives, like buy_ammo) but the
## ingredient is DELIVERED into the ritual Inventory autoload the counter-rite reads. Check-all-then-
## transact (no half-pay): an item outside the table refuses (unknown_item), an insufficient purse
## refuses before delivery (no_coin), and a capped ritual stack refuses before any coin is spent
## (inventory_full). No stock latch — ingredients are a coin-gated staple, not the per-run ammo shelf.
## Returns {ok, reason, item, cost}.
func buy_ingredient(item_id: String) -> Dictionary:
	var proxy = _player_proxy()
	if proxy == null:
		return {"ok": false, "reason": "no_player"}
	var prices := ingredient_prices()
	if not prices.has(item_id):
		return {"ok": false, "reason": "unknown_item"}
	var price := int(prices[item_id])
	var coin := coin_item()
	if proxy.item_count(coin) < price:
		return {"ok": false, "reason": "no_coin"}
	var inv := _al("Inventory")
	if inv == null:
		return {"ok": false, "reason": "no_inventory"}
	# Deliver into the ritual Inventory FIRST (a capped stack refuses here before any coin is spent),
	# THEN debit the purse (sufficiency already checked above) — no half-pay in either direction.
	if not inv.add(item_id, 1):
		return {"ok": false, "reason": "inventory_full"}
	proxy.remove_item(coin, price)
	var eb := _al("EventBus")
	if eb != null:
		eb.emit_event("ingredient_purchased", {"item": item_id, "cost": price, "source": "shop"})
	return {"ok": true, "reason": "", "item": item_id, "cost": price}

## SELL every carried item listed in the authored sell table (auto-transact — the whole harvest
## in one use, no menu). Coin in, items out. Returns {ok, reason, coins, sold: {item_id: {qty,
## coins}}}. Refuses (nothing_to_sell) with no state change when the table matches nothing
## carried. Deterministic: the table is iterated in SORTED item-id order.
func sell_harvest() -> Dictionary:
	var proxy = _player_proxy()
	if proxy == null:
		return {"ok": false, "reason": "no_player"}
	var prices := sell_prices()
	var ids := prices.keys()
	ids.sort()
	var total := 0
	var sold: Dictionary = {}
	for item_id in ids:
		var n: int = proxy.item_count(String(item_id))
		if n <= 0:
			continue
		proxy.remove_item(String(item_id), n)
		var coins: int = n * int(prices[item_id])
		sold[String(item_id)] = {"qty": n, "coins": coins}
		total += coins
	if total <= 0:
		return {"ok": false, "reason": "nothing_to_sell", "coins": 0, "sold": {}}
	proxy.add_item(coin_item(), total)
	var eb := _al("EventBus")
	if eb != null:
		eb.emit_event("harvest_sold", {"coins": total, "sold": sold})
	return {"ok": true, "reason": "", "coins": total, "sold": sold}

# --- run lifecycle ---------------------------------------------------------------------------------
## Scrub the per-run stock latch — the seam RunManager._reset_run_world calls so a fresh run
## opens with a full shelf (no carry — the sprint leak lesson).
func reset() -> void:
	_restocks_used = 0

func to_dict() -> Dictionary:
	return {"restocks_used": _restocks_used}

func from_dict(d: Dictionary) -> void:
	_restocks_used = int(d.get("restocks_used", 0))

# --- helpers ----------------------------------------------------------------------------------------
func _player_proxy():
	var reg := _al("Agents")
	if reg == null:
		return null
	return reg.get_agent("player")

## Autoload lookup via /root (safe under the headless -s harness parse ordering).
func _al(autoload_name: String) -> Node:
	var ml := Engine.get_main_loop()
	if ml == null or not (ml is SceneTree):
		return null
	return (ml as SceneTree).root.get_node_or_null(autoload_name)
