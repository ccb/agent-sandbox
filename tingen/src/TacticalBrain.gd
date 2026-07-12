class_name TacticalBrain
extends RefCounted
## Per-executor tactical layer (combat plan §M3): the ~8Hz decision loop between the LLM's
## ~15s intent verbs and the executor's frame-rate FSM. Owned and ticked by its
## CombatExecutor from step_combat, so every decision runs on the executor's own accumulated
## clock — never wall time — and headless == live.
##
## It READS published facts only: agent.combat_intent (the LLM's re-mask), the combat_form's
## kit (AbilityDB — re-read every tick, so a transform re-arms it instantly), distance bands
## DERIVED from ability data, the cooldown ledger, own hp, statuses. It ACTS only through the
## executor: try_cast + steering directives (pursue/strafe/back_away/goto/hold). It never
## deals damage, never writes an intent (intents are the LLM's published facts; a reflex may
## overwrite intent.style in place, and that happens in the executor).
##
## Styles are DATA masks (STYLES) consumed by ONE selection function — no per-style branching.
## The pure statics (bands_for/band_of/choose/protect_post) are M9 vector seeds.

const TACTICAL_HZ: int = 8
const TICK_MS: int = 1000 / TACTICAL_HZ
## Band fallbacks for kits that author no strike/projectile (data-driven first, these second).
const DEFAULT_MELEE_BAND: float = 48.0
const DEFAULT_NEAR_BAND: float = 160.0
## Protect geometry: the guard posts up guard_r from the ward toward the threat (never past
## the midpoint), and drifts back to the ward when no threat is known.
const PROTECT_GUARD_R: float = 48.0
const PROTECT_HOLD_R: float = 60.0
const PROTECT_ARRIVE: float = 6.0
## Disengage exits combat after sustaining more than DISENGAGE_EXIT_FACTOR x the near band of
## distance from every combatant for DISENGAGE_EXIT_MS.
const DISENGAGE_EXIT_FACTOR: float = 2.0
const DISENGAGE_EXIT_MS: int = 2000
## Defensive counters only within this window of taking/witnessing a hit.
const COUNTER_WINDOW_MS: int = 2000

## The style masks (plan §M3) — ability-class preferences + band policy as DATA, consumed by
## the one `choose` selector. rank: "damage" prefers the biggest hit within the preferred
## class; "cooldown" prefers the shortest cooldown (spam). retreat_hp: back away at/below this
## hp fraction (0 = never). counter_only: cast only within COUNTER_WINDOW_MS of a hit.
## reckless: keep closing even inside the target band.
const STYLES: Dictionary = {
	"aggressive": {"band": "melee", "class_pref": ["strike", "movement", "projectile", "spell", "effect"],
		"rank": "damage", "retreat_hp": 0.0, "counter_only": false, "reckless": false},
	"cautious": {"band": "near", "class_pref": ["projectile", "spell", "effect", "strike", "movement"],
		"rank": "damage", "retreat_hp": 1.0 / 3.0, "counter_only": false, "reckless": false},
	"defensive": {"band": "hold", "class_pref": ["strike", "projectile", "spell", "effect", "movement"],
		"rank": "damage", "retreat_hp": 0.0, "counter_only": true, "reckless": false},
	"desperate": {"band": "melee", "class_pref": [],
		"rank": "cooldown", "retreat_hp": 0.0, "counter_only": false, "reckless": true},
}
const DEFAULT_STYLE: String = "aggressive"

var _next_tick_ms: int = 0
var _far_since_ms: int = -1     # disengage sustained-distance bookkeeping
var _prev_target: String = ""   # band_entered transition tracking (per target)
var _prev_band: String = ""

## ---- pure statics (M9 vector seeds) ----

## Distance bands from ability DATA: melee = the kit's longest strike reach, near = its
## longest projectile range, far beyond. No per-form numbers live in code — an authored kit
## change re-derives the bands.
static func bands_for(kit_defs: Array) -> Dictionary:
	var melee: float = 0.0
	var near: float = 0.0
	for def_v in kit_defs:
		if typeof(def_v) != TYPE_DICTIONARY:
			continue
		var def: Dictionary = def_v
		var r := float(def.get("range", 0.0))
		match String(def.get("class", "")):
			"strike":
				melee = maxf(melee, r)
			"projectile":
				near = maxf(near, r)
	if melee <= 0.0:
		melee = DEFAULT_MELEE_BAND
	if near <= melee:
		near = maxf(melee * 2.0, DEFAULT_NEAR_BAND)
	return {"melee": melee, "near": near}

static func band_of(dist: float, bands: Dictionary) -> String:
	if dist <= float(bands.get("melee", DEFAULT_MELEE_BAND)):
		return "melee"
	if dist <= float(bands.get("near", DEFAULT_NEAR_BAND)):
		return "near"
	return "far"

## THE style-parameterized selector: one view of the fight ({kit: [ability defs], dist (edge
## distance to target), ledger, now_ms, hp_frac, recent_hit, bands, current_form}) + one mask
## -> {cast: ability id or "", steer: {kind[, stop_at]}}. Deterministic: candidates are ranked
## by (class preference, rank score, id) — never dict order, never RNG.
static func choose(view: Dictionary, style: String) -> Dictionary:
	var mask: Dictionary = STYLES.get(style, STYLES[DEFAULT_STYLE])
	var bands: Dictionary = view.get("bands", {}) if view.get("bands") is Dictionary else {}
	return {
		"cast": _select_ability(view, mask),
		"steer": _band_move(float(view.get("dist", INF)), bands, mask, float(view.get("hp_frac", 1.0))),
	}

## The guard post: on the ward->threat line, guard_r from the ward (halving a tighter gap so
## the guard never overshoots past the threat). A threat ON the ward -> stand at the ward.
static func protect_post(ward_pos: Vector2, threat_pos: Vector2, guard_r: float = PROTECT_GUARD_R) -> Vector2:
	var to := threat_pos - ward_pos
	var len := to.length()
	if len <= 0.001:
		return ward_pos
	return ward_pos + to / len * minf(guard_r, len * 0.5)

## ---- the per-tick instance loop (driven by the executor's clock) ----

func tick(ex: CombatExecutor) -> void:
	var agent := ex.agent
	if agent == null or agent.downed or not agent.in_combat:
		return
	var now := ex.now_ms()
	if now < _next_tick_ms:
		return
	_next_tick_ms = now + TICK_MS
	var kit_defs := _kit_defs(agent)
	var bands := bands_for(kit_defs)
	# Mode: a reflex flee > an empty kit (civilians run, they don't spar) > the LLM's standing
	# intent > the default posture (face whoever hit last, in the form's default style).
	var mode := String(agent.combat_intent.get("mode", ""))
	if ex.reflex_flee or kit_defs.is_empty():
		mode = "disengage"
	elif mode == "":
		mode = "engage"
	match mode:
		"protect":
			_tick_protect(ex, agent, kit_defs, bands, now)
		"disengage":
			_tick_disengage(ex, agent, bands, now, String(agent.combat_intent.get("via", "")))
		_:
			_tick_engage(ex, agent, kit_defs, bands, now)

func _tick_engage(ex: CombatExecutor, agent: Agent, kit_defs: Array, bands: Dictionary, now: int) -> void:
	var target_id := String(agent.combat_intent.get("target", ""))
	if target_id == "":
		target_id = ex.last_attacker_id
	var target := _find_agent(target_id)
	if target == null or target.downed or String(target.room) != String(agent.room) or target_id == agent.id:
		ex.set_steering({})
		_prev_target = ""
		return
	var eff := maxf(0.0, agent.position.distance_to(target.position) - CombatExecutor.radius_of(target.id))
	# band_entered reflex events ride band TRANSITIONS against the current target.
	var band := band_of(eff, bands)
	if target_id != _prev_target:
		_prev_target = target_id
		_prev_band = band
	elif band != _prev_band:
		_prev_band = band
		ex.on_reflex_event({"kind": "band_entered", "band": band})
	var choice := choose(_view_of(ex, agent, kit_defs, bands, eff, now), _style_for(ex, agent))
	var cast := String(choice.get("cast", ""))
	if cast != "" and ex.phase == CombatExecutor.PHASE_IDLE:
		ex.try_cast(cast, target_id)
	ex.set_steering(_bind_steer(choice.get("steer", {}), target))

func _tick_protect(ex: CombatExecutor, agent: Agent, kit_defs: Array, bands: Dictionary, now: int) -> void:
	var ward := _find_agent(String(agent.combat_intent.get("agent", "")))
	if ward == null or ward.downed or String(ward.room) != String(agent.room):
		ex.set_steering({})
		return
	# The threat is whoever last DAMAGED the ward (cheap static lookup on the hit ledger).
	var threat := _find_agent(CombatExecutor.last_attacker_of(ward.id))
	if threat != null and (threat.downed or String(threat.room) != String(agent.room) or threat.id == agent.id):
		threat = null
	if threat == null:
		if agent.position.distance_to(ward.position) > PROTECT_HOLD_R:
			ex.set_steering({"kind": "goto", "pos": ward.position, "arrive": PROTECT_HOLD_R - PROTECT_ARRIVE})
		else:
			ex.set_steering({})
		return
	ex.set_steering({"kind": "goto", "pos": protect_post(ward.position, threat.position), "arrive": PROTECT_ARRIVE})
	# Engage a threat entering the ward's melee band; otherwise hold the post, weapons cold.
	var threat_gap := maxf(0.0, ward.position.distance_to(threat.position) - CombatExecutor.radius_of(threat.id))
	if threat_gap > float(bands.get("melee", DEFAULT_MELEE_BAND)):
		return
	var eff := maxf(0.0, agent.position.distance_to(threat.position) - CombatExecutor.radius_of(threat.id))
	var cast := String((choose(_view_of(ex, agent, kit_defs, bands, eff, now), _style_for(ex, agent)) as Dictionary).get("cast", ""))
	if cast != "" and ex.phase == CombatExecutor.PHASE_IDLE:
		ex.try_cast(cast, threat.id)

func _tick_disengage(ex: CombatExecutor, agent: Agent, bands: Dictionary, now: int, via: String) -> void:
	var nearest := _nearest_combatant(agent)
	var dist := INF if nearest == null else agent.position.distance_to(nearest.position)
	if dist > float(bands.get("near", DEFAULT_NEAR_BAND)) * DISENGAGE_EXIT_FACTOR:
		if _far_since_ms < 0:
			_far_since_ms = now
		elif now - _far_since_ms >= DISENGAGE_EXIT_MS:
			var cm := _al("CombatMode")
			if cm != null:
				cm.exit_combat(agent)
			else:
				agent.in_combat = false
			ex.reflex_flee = false
			ex.set_steering({})
			return
	else:
		_far_since_ms = -1
	var via_pos: Variant = _resolve_via(via, agent.room)
	if via_pos != null:
		ex.set_steering({"kind": "goto", "pos": via_pos, "arrive": 24.0})
	elif nearest != null:
		ex.set_steering({"kind": "back_away", "from": nearest.position})
	else:
		ex.set_steering({})

## ---- internals ----

func _view_of(ex: CombatExecutor, agent: Agent, kit_defs: Array, bands: Dictionary, eff_dist: float, now: int) -> Dictionary:
	# B2 dry-art fallback (the M18 "leans on free arts" claim): an art the executor's cost
	# provider just refused (ex.cost_suppressed — e.g. a dry revolver's no_ammo) is excluded
	# from THIS selection round, so the one selector falls through to an affordable art instead
	# of re-locking the refused top pick every tick. Selection-only: bands stay derived from the
	# FULL kit, the pure statics (choose/_select_ability — M9 vector seeds) are untouched, and
	# the cast ledger is never marked by a refusal.
	var selectable: Array = []
	for def_v in kit_defs:
		if typeof(def_v) == TYPE_DICTIONARY \
				and ex.cost_suppressed(String((def_v as Dictionary).get("id", "")), now):
			continue
		selectable.append(def_v)
	return {
		"kit": selectable, "dist": eff_dist, "ledger": ex.ledger, "now_ms": now,
		"hp_frac": (agent.hp / agent.max_hp) if agent.max_hp > 0.0 else 1.0,
		"recent_hit": ex.recent_combat_hit(now, COUNTER_WINDOW_MS),
		"bands": bands, "current_form": agent.combat_form,
	}

## Style precedence: the intent's validated style > a reflex style override > the form's
## authored default_style > aggressive.
func _style_for(ex: CombatExecutor, agent: Agent) -> String:
	var s := String(agent.combat_intent.get("style", ""))
	if s == "":
		s = ex.style_override
	if s == "":
		var db := _al("AbilityDB")
		if db != null:
			s = String((db.form_def(agent.combat_form) as Dictionary).get("default_style", ""))
	return s if STYLES.has(s) else DEFAULT_STYLE

static func _select_ability(view: Dictionary, mask: Dictionary) -> String:
	if bool(mask.get("counter_only", false)) and not bool(view.get("recent_hit", false)):
		return ""
	var dist := float(view.get("dist", INF))
	var ledger: Dictionary = view.get("ledger", {}) if view.get("ledger") is Dictionary else {}
	var now := int(view.get("now_ms", 0))
	var current_form := String(view.get("current_form", ""))
	var prefs: Array = mask.get("class_pref", []) if mask.get("class_pref") is Array else []
	var by_cooldown := String(mask.get("rank", "damage")) == "cooldown"
	var best_id := ""
	var best_key: Array = []
	for def_v in (view.get("kit", []) as Array):
		if typeof(def_v) != TYPE_DICTIONARY:
			continue
		var def: Dictionary = def_v
		var id := String(def.get("id", ""))
		if id == "" or not CombatResolver.ledger_ready(ledger, id, now):
			continue
		if not _castable(def, dist, current_form):
			continue
		var pref := prefs.find(String(def.get("class", "")))
		if pref < 0:
			pref = prefs.size()
		var score := float(def.get("cooldown", 0.0)) if by_cooldown else -_damage_of(def)
		var key := [pref, score, id]
		if best_id == "" or _key_less(key, best_key):
			best_id = id
			best_key = key
	return best_id

## Is this ability usable at this edge distance? Transform-class abilities are NEVER a
## tactical pick — plan §0: the monster reveal is never an automatic engine rule, so only the
## authored reflex rows (hp_below → cast assume_form), the LLM's own choice, or a GM/Director
## directive may cast one; this deterministic layer must not decide it. Self-targets always
## cast; a pure-repositioning movement skill (no effects) is steering's job, never a tactical
## pick; everything else is authored-range gated.
static func _castable(def: Dictionary, dist: float, _current_form: String) -> bool:
	if String(def.get("class", "")) == "transform":
		return false
	if String(def.get("target_type", "")) == "self":
		return true
	if String(def.get("class", "")) == "movement" and (def.get("effects", []) as Array).is_empty():
		return false
	return dist <= float(def.get("range", 0.0))

static func _damage_of(def: Dictionary) -> float:
	var total: float = 0.0
	for eff_v in (def.get("effects", []) as Array):
		if typeof(eff_v) == TYPE_DICTIONARY and String((eff_v as Dictionary).get("kind", "")) == "damage":
			total += float((eff_v as Dictionary).get("amount", 0.0))
	return total

## Lexicographic key compare — Arrays don't order-compare in GDScript, so spell it out.
static func _key_less(a: Array, b: Array) -> bool:
	for i in range(mini(a.size(), b.size())):
		if a[i] < b[i]:
			return true
		if a[i] > b[i]:
			return false
	return a.size() < b.size()

## Band policy per mask: melee closes (strafing on top unless reckless), near kites the ring
## (backing out of melee), hold stands. Retreat overrides everything at/below retreat_hp.
static func _band_move(dist: float, bands: Dictionary, mask: Dictionary, hp_frac: float) -> Dictionary:
	var melee := float(bands.get("melee", DEFAULT_MELEE_BAND))
	var near := float(bands.get("near", DEFAULT_NEAR_BAND))
	var retreat := float(mask.get("retreat_hp", 0.0))
	if retreat > 0.0 and hp_frac <= retreat:
		return {"kind": "back_away"}
	match String(mask.get("band", "melee")):
		"melee":
			if dist > melee:
				return {"kind": "pursue", "stop_at": melee}
			return {"kind": "pursue", "stop_at": 0.0} if bool(mask.get("reckless", false)) else {"kind": "strafe"}
		"near":
			if dist < melee:
				return {"kind": "back_away"}
			if dist > near:
				return {"kind": "pursue", "stop_at": near}
			return {"kind": "strafe"}
		_:
			return {"kind": "hold"}

## Attach the live target to a pure band-move directive for the executor's steering.
static func _bind_steer(steer_v: Variant, target: Agent) -> Dictionary:
	var steer: Dictionary = steer_v if steer_v is Dictionary else {}
	var out := steer.duplicate(true)
	match String(out.get("kind", "")):
		"pursue", "strafe":
			out["target"] = target.id
		"back_away":
			out["from"] = target.position
		"hold":
			return {}
	return out

## The named `via` of a disengage, resolved against ActionCommit's navigable places — but ONLY
## in the agent's own room (cross-room coordinates are wrong-space). null = no usable point.
static func _resolve_via(via: String, room: String) -> Variant:
	if via == "":
		return null
	if ActionCommit.NAV_SITES.has(via):
		var nav: Dictionary = ActionCommit.NAV_SITES[via]
		if String(nav.get("room", "")) == String(room):
			return nav.get("pos")
	if ActionCommit.SITES.has(via) and String(ActionCommit.SITE_ROOM.get(via, RoomGraph.DEFAULT_ROOM)) == String(room):
		return ActionCommit.SITES[via]
	return null

## Nearest same-room standing combatant other than self (deterministic: registry order breaks
## exact ties, and the registry is insertion-ordered).
static func _nearest_combatant(agent: Agent) -> Agent:
	var reg := _al("Agents")
	if reg == null:
		return null
	var best: Agent = null
	var best_d := INF
	for a_v in reg.all():
		var a: Agent = a_v
		if a == agent or a.downed or not a.in_combat or String(a.room) != String(agent.room):
			continue
		var d := agent.position.distance_to(a.position)
		if d < best_d:
			best = a
			best_d = d
	return best

func _kit_defs(agent: Agent) -> Array:
	var db := _al("AbilityDB")
	if db == null:
		return []
	var out: Array = []
	for id in (db.kit_for(agent.combat_form) as Array):
		var def: Dictionary = db.ability_for(String(id))
		if not def.is_empty():
			out.append(def)
	return out

static func _find_agent(id: String) -> Agent:
	if id == "":
		return null
	var reg := _al("Agents")
	return reg.get_agent(id) if reg != null else null

## Autoload lookup via /root (class_name scripts can't reference autoload globals under the
## headless -s harness's parse ordering), tolerant of the autoload being absent entirely.
static func _al(autoload_name: String) -> Node:
	var ml := Engine.get_main_loop()
	if ml == null or not (ml is SceneTree):
		return null
	return (ml as SceneTree).root.get_node_or_null(autoload_name)
