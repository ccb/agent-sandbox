class_name PlayerCombat
extends Node
## The player's hands on the SAME combat machinery NPCs fight with (combat plan §M5) — a
## child node of Player.tscn that binds ONE CombatExecutor to the player PROXY agent
## (Agents.ensure_player_proxy's "player") + this player body. No parallel implementation:
## attack/dash/use_charm are just try_cast("revolver_shot"/"dash"/"paper_charm") on that
## executor, so telegraphs (ability_cast_started, caster "player"), cooldowns, i-frames,
## projectiles/zones and damage all ride the exact pipes M2/M3 built.
##
## ALWAYS ARMED: the proxy is exempt from the damage→combat-mode flip (review M1 #4 — it has
## no brain to fight with), so this executor lives, and may fire, for as long as this node
## does. Combat-mode semantics are for NPCs; the player simply acts.
##
## Costs (the executor's M5 cost_provider seam — this node is the provider):
##   * `ammo` is NOT a built-in pool — it resolves through the weapon/tool ITEM system:
##     ItemDB.weapon_for_ability finds a CARRIED weapon in the proxy's inventory whose
##     `grants` names the art, and the cost consumes that weapon's `ammo_item` rounds
##     (data/items.json) from the SAME per-agent inventory NPCs use. Refusals: "no_weapon"
##     (no carried granting weapon), "no_ammo" (too few rounds). The starting revolver +
##     rounds arrive as scenario.json's player_loadout when Agents.ensure_player_proxy
##     CREATES the proxy, so they survive room swaps (each room re-instances Player.tscn
##     but the proxy persists) and reset with the proxy on a run restart;
##   * dash pays `stamina` from Player.gd's EXISTING sprint pool — refusal "no_stamina";
##   * M31: `spirituality` pays from THIS node's own regenerating pool (MAX_SPIRIT, refilled by
##     step_spirituality each frame) — refusal "no_spirit". This is the Hermit's star/ritual scarcity;
##     it is a PLAYER pool only (enemies keep paying via AgentCostProvider, where spirituality is free),
##     so the pinned combat sims never see it.
##
## Body vs data authority: while walking, the BODY leads (Player.gd's move_and_slide) — this
## node mirrors body → proxy.position and steps the executor AFTER the mirror each physics
## frame (the executor's own _physics_process is disabled), so the executor's _sync_body
## write-back is always a no-op unless a combat motion (dash/knockback) really displaced the
## body via move_and_collide. Known M5 limits: slow/stun statuses on the player gate casts
## and executor motions but not Player.gd's walk.
##
## Aim = mouse direction from the player (get_global_mouse_position) when a display exists;
## headless (and the test harness) falls back to a stored aim_dir refreshed by movement.

var proxy: Agent = null
var body: Node2D = null
var executor: CombatExecutor = null
## Fallback aim (headless / mouse at rest on the body): last movement direction, else right.
var aim_fallback: Vector2 = Vector2.RIGHT
## M13: proximity auto-pickup radius (pixels). The player walks over a ground ammo pile and takes it.
## Engine-neutral: operates on RoomItems.take_near → proxy.add_item — the same path NPCs use for gather.
const PICKUP_RADIUS: float = 48.0
## B1 (retro): the items.json tag naming the walk-over ground-gather set — ammo AND the pathway
## Characteristic drops are just tagged rows (data, never an engine id list), so a downed Beyonder's
## dropped <pathway>_characteristic is collectible LIVE by walking over it, at the ammo radius/feel.
const GATHER_TAG: String = "gatherable"
## The gatherable id set, cached once (items.json is static data; ItemDB loads it once).
var _gather_ids_cache: Array = []
## M31: the PLAYER'S spirituality (mana) pool — a regenerating reservoir the Hermit's star/ritual arts
## spend, so those casts have a real cadence instead of firing free. It lives HERE (on this node) and is
## enforced ONLY inside try_pay, exactly like the stamina leg reads Player.gd's pool: the pinned sims
## never route a cast through this node (their bots carry no cost_provider) and enemies pay via the
## untouched AgentCostProvider (spirituality stays free for NPCs), so the pool is provably ADDITIVE.
## M34 RETUNE — MAX 40 / REGEN 4·s: the star primary (star_brand 10/cd1.0) now drains net 6/s, so a full
## reserve buys ~6 casts before dry (was ~26 at 60/8) and a drained pool waits 2.5s for one star_brand
## (was 1.25s) — the push-your-luck reserve fork now bites. Still no dead-end: drained→star_brand 2.5s,
## →collapsing_star 5.0s, all bounded (regen is strictly +4/s; dash rides Player.gd's separate stamina).
const MAX_SPIRIT: float = 40.0
const SPIRIT_REGEN: float = 4.0          # per second
var spirituality: float = MAX_SPIRIT

func _ready() -> void:
	add_to_group("player_combat")
	body = get_parent() as Node2D
	var reg := _al("Agents")
	if reg == null or body == null:
		set_physics_process(false)
		return
	proxy = reg.ensure_player_proxy(body.global_position, _current_room())
	if proxy.combat_form == "":
		proxy.combat_form = "player"   # the data kit in combat_forms.json (no reflex rows)
	executor = CombatExecutor.new()
	executor.name = "Executor"
	executor.bind(proxy, body)
	executor.cost_provider = self
	# Single stepping authority, ordered: THIS node mirrors body → proxy, THEN steps the
	# executor (its own physics callback is off), so walk and combat never fight per-frame.
	executor.set_physics_process(false)
	add_child(executor)

func _physics_process(delta: float) -> void:
	if executor == null:
		return
	var reg := _al("Agents")
	if reg != null and reg.get_agent("player") != proxy:
		# The registry was rebuilt under us (run restart / harness staging): re-ensure the
		# fresh proxy and re-bind the executor to it.
		proxy = reg.ensure_player_proxy(body.global_position, _current_room())
		if proxy.combat_form == "":
			proxy.combat_form = "player"
		executor.bind(proxy, body)
	else:
		proxy.position = body.global_position
	var move := Input.get_vector("move_left", "move_right", "move_up", "move_down")
	if move.length() > 0.001:
		aim_fallback = move.normalized()
	# M13/B1: proximity auto-pickup — walk over any GATHERABLE ground pile (the items.json tag: ammo,
	# a dropped pathway Characteristic) to collect it into the proxy inventory. Uses the same
	# take_near→add_item path as NPC gather_item; engine-neutral, no NPC-id/item-id branch.
	_try_pickup_nearby()
	# M32: the SAME ground-pickup seam for COUNTER-RITE ingredients — walk over chalk/candle (e.g. the
	# cult's supply cache in the City) and collect them into the ritual Inventory the rite reads. This
	# is the live world source that makes the anti-Doom rite reachable by gathering, not just at Franky's.
	_try_pickup_ingredients()
	# M18: loot a fallen body you walk over — the same proximity seam, extended to downed agents
	# (once each, latched). Engine-neutral: loot = the body's whole inventory, no NPC-id branch.
	_try_loot_downed_body()
	# M31: regen the spirituality pool once per frame off the SAME dt the executor steps on (a pure
	# function of the frame — no wall-clock), before the combat step so a cast this frame reads the
	# freshly-regenerated pool. Always-armed (incl. dialogue), exactly like Player.gd's stamina.
	step_spirituality(delta)
	executor.step_combat(delta)

## Real input path. Dialogue holds the player's hands exactly as it freezes their feet
## (Player.gd); the headless tests call the on_*_pressed handlers directly instead.
func _unhandled_input(event: InputEvent) -> void:
	if executor == null:
		return
	var dm := _al("DialogueManager")
	if dm != null and bool(dm.get("active")):
		return
	if event.is_action_pressed("attack"):
		on_attack_pressed()
	elif event.is_action_pressed("melee"):
		on_melee_pressed()
	elif event.is_action_pressed("dash"):
		on_dash_pressed()
	elif event.is_action_pressed("use_charm"):
		on_charm_pressed()

## Attack along the aim. Normally the human kit's revolver_shot; during the loss-of-control rampage
## (M4 §13 decision #5) the proxy wears the Seq-4 creature form, so the SAME button drives the
## MONSTER'S primary art instead — the player still controls the body, now with the beast's kit.
## Engine-neutral: the creature art is resolved generically from the worn form's kit (its first
## non-movement ability), never a form-name branch. Returns the executor's verdict {ok, reason}.
func on_attack_pressed(dir: Vector2 = Vector2.ZERO) -> Dictionary:
	if executor == null:
		return {"ok": false, "reason": "unbound"}
	var verdict: Dictionary = executor.try_cast(_primary_attack_id(), "", dir if dir != Vector2.ZERO else aim_dir())
	# M13/M34: empty-resource feedback. A dry gun ("no_ammo") pulses the ammo cue; an empty pool
	# ("no_spirit" — the Hermit's star primary) pulses the spirit cue — routed through ONE shared helper
	# so both spend paths cue identically. COSMETIC + an event; it MUST NOT change try_pay refusal
	# semantics or the combat_sim transcript. Fired exactly once per empty trigger (not per frame).
	_cue_for_refusal(verdict)
	return verdict

## M22 B8: the ammo-free MELEE FLOOR. Its own button (never the primary attack) so a DRY player —
## no rounds, revolver_shot starved to "no_ammo" — can always throw a free pistol_whip and chip hp.
## A weak, short strike (data: pistol_whip, cost {}); ammo starvation is no longer an unrecoverable
## soft-loss. Engine-neutral: fires whatever ammo-free strike the worn kit authors as its melee floor
## (its first strike-class art with no ammo cost), never a form-name branch — so the rampage creature
## body throws its own free melee too. Returns the executor's verdict {ok, reason}.
func on_melee_pressed(dir: Vector2 = Vector2.ZERO) -> Dictionary:
	if executor == null:
		return {"ok": false, "reason": "unbound"}
	return executor.try_cast(_melee_floor_id(), "", dir if dir != Vector2.ZERO else aim_dir())

## The worn form's ammo-free melee floor: its FIRST strike-class art whose cost names no ammo
## (pistol_whip for the Hunter player kit). "" when the form authors no free strike (then the button is
## inert — the caller's try_cast degrades to unknown_ability, harmlessly). M34: the Hermit kit authors NO
## strike (star_brand/ward_circle/dash/astral_sight), so its melee button is inert BY DESIGN — the
## Hermit's ammo-free damage floor is the spirit-funded star_brand primary, not a free pistol_whip it
## never earned. Reads AbilityDB generically — no form name. The db==null/proxy==null guard keeps the
## headless-safety "pistol_whip" fallback (a bare unit context still has a floor).
func _melee_floor_id() -> String:
	var db := _al("AbilityDB")
	if db == null or proxy == null:
		return "pistol_whip"
	for aid in db.kit_for(proxy.combat_form):
		var adef: Dictionary = db.ability_for(String(aid))
		if String(adef.get("class", "")) != "strike":
			continue
		var cost: Dictionary = adef.get("cost", {}) if adef.get("cost") is Dictionary else {}
		if int(cost.get("ammo", 0)) <= 0:
			return String(aid)
	return ""

## Called exactly once per empty-gun trigger. Emits a weapon_empty event on the EventBus (a future
## SFX pass can hook it) and requests a flash from CombatFeedback (gated by Settings.hit_flash — with
## the toggle off the flash is a no-op, but the event still fires: the cue is never suppressed).
func _on_weapon_empty() -> void:
	var eb := _al("EventBus")
	if eb != null:
		eb.emit_event("weapon_empty", {"caster": "player", "ammo": ammo_count()})
	# Flash: gated by hit_flash toggle (Settings) via CombatFeedback. Cosmetic only.
	var fb := _al("CombatFeedback")
	if fb != null and fb.has_method("flash"):
		fb.flash()

## M34: route a refused cast to the right empty-resource cue — a dry gun ("no_ammo") to the ammo pulse,
## a spent pool ("no_spirit" — the Hermit's star/ritual spend) to the spirit pulse. Shared by the attack
## + charm buttons so every spend path cues identically. A non-empty refusal (no_weapon / no_stamina /
## cooldown / unbound) cues nothing. Purely cosmetic + an event — never touches try_pay semantics.
func _cue_for_refusal(verdict: Dictionary) -> void:
	if bool(verdict.get("ok", false)):
		return
	match String(verdict.get("reason", "")):
		"no_ammo":
			_on_weapon_empty()
		"no_spirit":
			_on_spirit_empty()

## M34: called once per empty-pool trigger. Mirrors _on_weapon_empty on a SEPARATE channel — a
## spirit_empty event on the EventBus (a future SFX pass can hook it) + a flash from CombatFeedback
## (gated by Settings.hit_flash — off = no visual, but the event still fires: the cue is never
## suppressed). The HUD pulses its OWN Spirit bar off spirit_empty, so ammo and spirit read distinctly.
func _on_spirit_empty() -> void:
	var eb := _al("EventBus")
	if eb != null:
		eb.emit_event("spirit_empty", {"caster": "player", "spirit": spirituality_now()})
	var fb := _al("CombatFeedback")
	if fb != null and fb.has_method("flash"):
		fb.flash()

## M13 → B1 (retro): the walk-over GROUND-GATHER seam, now DATA-DRIVEN. Called each physics frame;
## takes ONE nearby unit of EACH gatherable item id per frame (a pile depletes over several frames,
## which is fine — the player walks through it). The gather set is the items.json "gatherable" TAG
## (ItemDB.ids_with_tag, cached) — ammo and the pathway Characteristics are just tagged rows, so the
## drop a downed Beyonder leaves on the ground is HARVESTABLE live by walking over it (the missing
## seam that dead-ended digest/advance and the sell fork in live play), and a future pathway's drop
## gathers with zero code change. Operates on RoomItems.take_near → proxy.add_item, the same path NPC
## gather_item uses, at the same PICKUP_RADIUS for every gatherable (ammo-consistent feel). Ammo keeps
## its DISTINCT ammo_picked_up cue (authored category "ammo"); every other gatherable emits the
## generic item_picked_up fact. Returns the first item id picked up, or "" if nothing was in range.
func _try_pickup_nearby() -> String:
	if proxy == null:
		return ""
	var ri := _al("RoomItems")
	if ri == null:
		return ""
	var idb := _al("ItemDB")
	var first := ""
	for item_id in _gather_ids(idb):
		var taken: String = ri.take_near(proxy.room, String(item_id), proxy.position, PICKUP_RADIUS)
		if taken == "":
			continue
		proxy.add_item(taken, 1)
		if first == "":
			first = taken
		var eb := _al("EventBus")
		if eb == null:
			continue
		var def: ItemDef = idb.get_def(taken) if idb != null else null
		if def != null and def.category == "ammo":
			eb.emit_event("ammo_picked_up", {"caster": "player", "item": taken, "ammo": ammo_count()})
		else:
			eb.emit_event("item_picked_up", {"caster": "player", "item": taken})
	return first

## The gatherable id set — the items.json GATHER_TAG rows, read once off ItemDB and cached (item defs
## are static content). Falls back to the M13 ammo literal when ItemDB is absent (a bare unit context
## still gathers ground rounds; never cached, so a late-arriving ItemDB upgrades the set).
func _gather_ids(idb: Node) -> Array:
	if not _gather_ids_cache.is_empty():
		return _gather_ids_cache
	if idb == null or not idb.has_method("ids_with_tag"):
		return ["revolver_round"]
	_gather_ids_cache = idb.ids_with_tag(GATHER_TAG)
	return _gather_ids_cache

## M32: proximity auto-pickup of COUNTER-RITE ingredients — the SAME M13 ground-pickup seam as ammo,
## but the ids are DATA (the counter-rite's authored ingredient bill, CounterRite.ingredients()) and the
## unit is DELIVERED into the ritual Inventory AUTOLOAD the counter-rite reads (Inventory.add), NOT the
## proxy. This is the M32 reachability bridge: a live world gather of chalk/candle (e.g. off the cult's
## City supply cache) lands in the store the rite reads, so it becomes performable AND fires the
## once-per-run discoverability hint (CounterRite watches Inventory.item_added). Takes one of EACH
## authored ingredient in range per frame (a stack depletes over frames, like the ammo pile).
## Engine-neutral: no item-id literal here; a no-op when the rite authors nothing or the autoloads are
## absent. Combat is untouched — ammo still lands in the proxy via _try_pickup_nearby.
func _try_pickup_ingredients() -> void:
	if proxy == null:
		return
	var ri := _al("RoomItems")
	var cr := _al("CounterRite")
	var inv := _al("Inventory")
	if ri == null or cr == null or inv == null or not cr.has_method("ingredients"):
		return
	for item_id in cr.ingredients():
		var taken: String = ri.take_near(proxy.room, String(item_id), proxy.position, PICKUP_RADIUS)
		if taken == "":
			continue
		inv.add(taken, 1)
		var eb := _al("EventBus")
		if eb != null:
			eb.emit_event("ingredient_picked_up", {"caster": "player", "item": taken})

## M18 loot: transfer a DOWNED body's ENTIRE carried inventory into a looter, exactly ONCE. Static +
## pure so the live proximity seam AND the tests drive the identical transfer. Engine-neutral: loot =
## the agent's whole inventory (weapons, rounds, valuables), NO id branch — a dead gunman yields his
## revolver + leftover rounds, a butcher his cleavers, with the same code. Latched by body.looted; a
## looted or still-STANDING body yields nothing. The body is NEVER deleted (the fixed-cast invariant —
## only its carried items move). The pathway Characteristic is NOT here: Progression already drops it
## to the ground on agent_downed, and that drop is kept (never duplicated). Returns the items moved
## {item_id: count} ({} when nothing was looted).
## Save/load: `looted` is ephemeral (not persisted), but the EMPTIED inventory IS — so reloading an
## already-looted body clears the latch yet finds {} to move, re-latches, and yields nothing. No
## duplication across a save/load. Safe by construction.
static func loot_downed_body(looter: Agent, body: Agent) -> Dictionary:
	if looter == null or body == null or not body.downed or body.looted:
		return {}
	var moved: Dictionary = {}
	for item_id in body.inventory.keys():
		var n := int(body.inventory[item_id])
		if n > 0:
			looter.add_item(String(item_id), n)
			moved[String(item_id)] = n
	body.inventory.clear()
	body.looted = true
	return moved

## M18: loot the nearest un-looted DOWNED body within reach, once. Called each physics frame beside
## the ammo pickup — the same M13 proximity seam, extended from "a ground pile" to "a fallen body".
## Engine-neutral (loot = the agent's inventory, no id branch); the latch (body.looted) stops the
## per-frame scan from re-looting. Returns the id of the body looted, or "" if none was in range.
func _try_loot_downed_body() -> String:
	if proxy == null:
		return ""
	var reg := _al("Agents")
	if reg == null:
		return ""
	for a in reg.all():
		if a == proxy or not a.downed or a.looted:
			continue
		if String(a.room) != String(proxy.room):
			continue
		if proxy.position.distance_to(a.position) > PICKUP_RADIUS:
			continue
		var moved: Dictionary = PlayerCombat.loot_downed_body(proxy, a)
		if moved.is_empty():
			a.looted = true   # an empty body still latches, so the scan never revisits it
			continue
		var eb := _al("EventBus")
		if eb != null:
			eb.emit_event("body_looted", {"looter": "player", "body": a.id, "items": moved})
		return String(a.id)
	return ""

## The art the attack button fires for the worn form: the worn KIT's first strike/projectile/spell
## (skipping movement/transform), read generically off AbilityDB. This is KIT-AWARE for the "player"
## form too (M34) — the Hunter build fires revolver_shot (its kit's first offensive art) and the Hermit
## build fires star_brand (its star-caster primary) through the SAME seam, so a live Hermit actually
## casts its spirit primary instead of the loadout revolver. Engine-neutral: the pick is driven by the
## worn kit's authored order, never a pathway/NPC branch. Falls back to revolver_shot only when the form
## authors no offensive art, or when the proxy/AbilityDB are absent (headless safety).
func _primary_attack_id() -> String:
	if proxy == null or proxy.combat_form == "":
		return "revolver_shot"
	var db := _al("AbilityDB")
	if db == null:
		return "revolver_shot"
	for aid in db.kit_for(proxy.combat_form):
		var klass := String((db.ability_for(String(aid)) as Dictionary).get("class", ""))
		if klass == "strike" or klass == "projectile" or klass == "spell":
			return String(aid)
	return "revolver_shot"

## Dash: along the CURRENT movement direction, else the aim (a standing dash goes where
## you're looking). The ability's authored i-frames ride the cast.
func on_dash_pressed(dir: Vector2 = Vector2.ZERO) -> Dictionary:
	if executor == null:
		return {"ok": false, "reason": "unbound"}
	var d := dir
	if d == Vector2.ZERO:
		d = Input.get_vector("move_left", "move_right", "move_up", "move_down")
	if d == Vector2.ZERO:
		d = aim_dir()
	return executor.try_cast("dash", "", d.normalized())

## Charm: paper_charm toward the aim (the zone plants at range along it).
func on_charm_pressed(dir: Vector2 = Vector2.ZERO) -> Dictionary:
	if executor == null:
		return {"ok": false, "reason": "unbound"}
	var verdict: Dictionary = executor.try_cast("paper_charm", "", dir if dir != Vector2.ZERO else aim_dir())
	# M34: paper_charm spends spirituality — a spent-pool press cues spirit_empty through the SAME shared
	# helper as the attack button (both spirit-spend paths read identically when the pool is dry).
	_cue_for_refusal(verdict)
	return verdict

## Mouse direction from the player when a real display exists; otherwise (headless) the
## stored fallback. A successful read refreshes the fallback, so the last real aim persists.
func aim_dir() -> Vector2:
	if body != null and body.is_inside_tree() and DisplayServer.get_name() != "headless":
		var v := body.get_global_mouse_position() - body.global_position
		if v.length() > 0.5:
			aim_fallback = v.normalized()
	return aim_fallback

## The executor's cost seam (duck-typed): check EVERY authored cost first, then deduct all —
## a refusal never half-pays. Enforced tonight: ammo (weapon/tool items — see below) + stamina
## (Player.gd's pool). Unknown cost keys are free (M5 scope; NPCs have no provider at all).
##
## `ammo` resolution is AGENT-GENERIC: the whole check-and-consume operates on the PROXY's
## per-agent inventory through ItemDB.weapon_for_ability (which weapon fires this art, what
## rounds it eats) — no player-only state beyond this node's existing provider wiring, so a
## future NPC cost provider pays the identical way. Refusal order: no carried granting weapon
## -> "no_weapon"; too few of its ammo_item rounds -> "no_ammo".
func try_pay(ability: Dictionary) -> Dictionary:
	var cost: Dictionary = ability.get("cost", {}) if ability.get("cost") is Dictionary else {}
	var ammo_cost := int(cost.get("ammo", 0))
	var round_item := ""
	if ammo_cost > 0:
		var idb := _al("ItemDB")
		var weapon: Dictionary = {}
		if idb != null:
			weapon = idb.weapon_for_ability(proxy, String(ability.get("id", "")))
		if weapon.is_empty():
			return {"ok": false, "reason": "no_weapon"}
		round_item = String(weapon.get("ammo_item", ""))
		if round_item == "" or proxy == null or proxy.item_count(round_item) < ammo_cost:
			return {"ok": false, "reason": "no_ammo"}
	var stamina_cost := float(cost.get("stamina", 0.0))
	if stamina_cost > 0.0:
		var pool: Variant = body.get("stamina") if body != null else null
		if pool == null or float(pool) < stamina_cost:
			return {"ok": false, "reason": "no_stamina"}
	# M31: the player's spirituality pool (this node's own field) — the Hermit's star/ritual scarcity.
	# Checked with ammo + stamina BEFORE any deduct (a refusal never half-pays), and refused "no_spirit"
	# when short. Enforced ONLY here: NPC casters pay via AgentCostProvider (spirituality free), so the
	# pinned sims stay byte-identical.
	var spirit_cost := float(cost.get("spirituality", 0.0))
	if spirit_cost > 0.0 and spirituality < spirit_cost:
		return {"ok": false, "reason": "no_spirit"}
	if ammo_cost > 0:
		proxy.remove_item(round_item, ammo_cost)
	if stamina_cost > 0.0:
		body.set("stamina", maxf(0.0, float(body.get("stamina")) - stamina_cost))
	if spirit_cost > 0.0:
		spirituality = maxf(0.0, spirituality - spirit_cost)
	return {"ok": true, "reason": ""}

## M31: advance the spirituality pool one frame — a PURE regen (drain happens only in try_pay), clamped
## to [0, MAX_SPIRIT]. Mirrors Player.step_stamina so it is unit-testable headless with no Input/tree.
func step_spirituality(dt: float) -> void:
	spirituality = minf(MAX_SPIRIT, spirituality + SPIRIT_REGEN * dt)

## HUD-facing spirituality read-outs (mirror ammo_count): the live pool + its max reservoir, so the
## CombatHUD Spirit bar reads the Hermit's mana exactly as it reads stamina.
func spirituality_now() -> float:
	return spirituality

func spirituality_max() -> float:
	return MAX_SPIRIT

## HUD-facing rounds read-out for the player's ammo-costing art: find the FIRST kit ability
## whose authored cost pays `ammo`, resolve its carried granting weapon via ItemDB, and count
## that weapon's ammo_item in the proxy inventory. -1 = nothing resolves (no ammo-costing art
## in the kit, or no granting weapon carried) — CombatHUD renders that as "—".
func ammo_count() -> int:
	if proxy == null:
		return -1
	var db := _al("AbilityDB")
	var idb := _al("ItemDB")
	if db == null or idb == null:
		return -1
	for aid in db.kit_for(proxy.combat_form):
		var cost: Variant = (db.ability_for(String(aid)) as Dictionary).get("cost", {})
		if cost is Dictionary and int((cost as Dictionary).get("ammo", 0)) > 0:
			var weapon: Dictionary = idb.weapon_for_ability(proxy, String(aid))
			if weapon.is_empty():
				return -1
			var round_item := String(weapon.get("ammo_item", ""))
			if round_item == "":
				return -1   # the weapon costs no ammo: "—", not a literal 0 of item ""
			return proxy.item_count(round_item)
	return -1

## Remaining-cooldown fraction for a kit ability (1 = just cast, 0 = ready) — HUD pips.
func cooldown_frac(ability_id: String) -> float:
	if executor == null:
		return 0.0
	var db := _al("AbilityDB")
	if db == null:
		return 0.0
	var cd_ms := int(round(float((db.ability_for(ability_id) as Dictionary).get("cooldown", 0.0)) * 1000.0))
	if cd_ms <= 0:
		return 0.0
	var remaining := int(executor.ledger.get(ability_id, 0)) - executor.now_ms()
	return clampf(float(remaining) / float(cd_ms), 0.0, 1.0)

## The player's current room: the live GameController's when one exists, else whatever the
## proxy already carries (headless staging), else the default city.
func _current_room() -> String:
	var gcs := get_tree().get_nodes_in_group("game_controller")
	if not gcs.is_empty():
		return String(gcs[0].current_room())
	var reg := _al("Agents")
	var existing: Agent = reg.get_agent("player") if reg != null else null
	return String(existing.room) if existing != null else "city"

## Autoload lookup via /root (class_name scripts can't reference autoload globals under the
## headless -s harness's parse ordering), tolerant of the autoload being absent entirely.
func _al(autoload_name: String) -> Node:
	var ml := Engine.get_main_loop()
	if ml == null or not (ml is SceneTree):
		return null
	return (ml as SceneTree).root.get_node_or_null(autoload_name)
