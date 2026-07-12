class_name AgentCostProvider
extends RefCounted
## Generic per-agent ability-cost provider — the executor's cost_provider seam (combat plan §M5) for
## ANY bound agent, not just the player (combat plan §M18). NPC.gd binds one of these to a fighting
## NPC's executor when it enters combat, so a human gunman actually runs DRY instead of firing forever.
##
## It mirrors PlayerCombat.try_pay's AMMO path exactly, but pays from THE BOUND AGENT'S own per-agent
## inventory: `ammo` is NOT a built-in pool — ItemDB.weapon_for_ability finds a CARRIED weapon whose
## `grants` names the art, and the cost consumes that weapon's `ammo_item` rounds (data/items.json)
## from the same id->count inventory NPCs already use. Refusals (precedence no_weapon > no_ammo, the
## player's order): "no_weapon" (no carried granting weapon), "no_ammo" (too few rounds). Asked LAST
## in try_cast's refusal chain, so a refused cost burns NO cooldown and half-pays nothing.
##
## Stamina/spirituality stay FREE for NPCs BY DECISION (matching pre-M18 behavior): monster form kits
## are authored around free stamina, and an NPC carries no body stamina pool (that lives on Player.gd).
## A non-ammo cost (or a free art) therefore always pays ok here — only ammo is enforced. Documented
## scope, symmetric with the player (whose stamina leg is Player.gd's pool, not an item).
##
## Engine-neutral: zero NPC-identity branches — the whole check keys off the ability's `cost.ammo` and
## the DATA-resolved weapon/ammo item, so any agent (authored NPC, runtime threat, the player proxy)
## pays identically.

## The agent whose inventory this provider draws from (the executor's bound agent).
var agent: Object = null

func _init(agent_in: Object = null) -> void:
	agent = agent_in

func bind(agent_in: Object) -> void:
	agent = agent_in

## The executor's cost seam (duck-typed try_pay(ability) -> {ok, reason}). Check the ammo cost,
## then deduct — a refusal never half-pays. Only `ammo` is enforced (see class docs).
func try_pay(ability: Dictionary) -> Dictionary:
	var cost: Dictionary = ability.get("cost", {}) if ability.get("cost") is Dictionary else {}
	var ammo_cost := int(cost.get("ammo", 0))
	if ammo_cost <= 0:
		return {"ok": true, "reason": ""}   # free / non-ammo art: NPCs pay nothing else (documented)
	if agent == null or not agent.has_method("item_count"):
		return {"ok": false, "reason": "no_weapon"}
	var idb := _al("ItemDB")
	var weapon: Dictionary = idb.weapon_for_ability(agent, String(ability.get("id", ""))) if idb != null else {}
	if weapon.is_empty():
		return {"ok": false, "reason": "no_weapon"}
	var round_item := String(weapon.get("ammo_item", ""))
	if round_item == "" or int(agent.call("item_count", round_item)) < ammo_cost:
		return {"ok": false, "reason": "no_ammo"}
	agent.call("remove_item", round_item, ammo_cost)
	return {"ok": true, "reason": ""}

## Autoload lookup via /root (class_name-safe under the headless -s harness), tolerant of absence.
func _al(autoload_name: String) -> Node:
	var ml := Engine.get_main_loop()
	if ml == null or not (ml is SceneTree):
		return null
	return (ml as SceneTree).root.get_node_or_null(autoload_name)
