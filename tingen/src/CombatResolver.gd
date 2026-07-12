class_name CombatResolver
extends RefCounted
## The deterministic combat core (combat plan §M2) — a PURE, static, language-neutral resolver.
##
## Everything here operates on plain state Dictionaries ({hp, max_hp, statuses, poise,
## i_frame_until_ms}) and JSON-safe values ([x, y] arrays, ms ints) — NO node access, NO autoloads,
## NO Vector2, NO randomness, fully synchronous. This is the layer the M9 back-port spec pins with
## language-neutral vectors: the same inputs MUST produce the same deltas in GDScript and in
## Yumina's TypeScript. Anything that touches the scene tree (bodies, projectiles, events,
## Agent.take_damage) lives in CombatExecutor; anything that decides WHAT to cast lives in M3+.

## Accumulated poise damage at/above this staggers the target (stagger = cast interruption +
## brief stun + knockback, enforced by the executor) and the pool resets.
const POISE_BREAK: float = 100.0
## The status vocabulary the resolver implements. `silence` is in the shipped data
## (paper_charm) — it blocks windup START, checked by the executor.
const STATUS_KINDS: Array = ["slow", "stun", "dot", "shield", "frenzy", "silence"]
## Default per-tick cadence for damage-over-time statuses that don't author one.
const DEFAULT_DOT_TICK_MS: int = 500
## How long a stagger's stun lasts (executor applies it when deltas.staggered).
const STAGGER_STUN_MS: int = 400
## Knockback displacement is applied over roughly this window (executor motion).
const KNOCKBACK_MS: int = 150
## Named-status defaults (magnitude, duration_ms) for statuses authored as bare names
## (e.g. paper_charm's zone `statuses: ["slow", "silence"]`). Durations outlive one zone
## tick (500ms) so standing inside keeps the status continuously refreshed.
const NAMED_STATUS_DEFAULTS: Dictionary = {
	"slow": {"magnitude": 0.5, "duration_ms": 1200},
	"silence": {"magnitude": 1.0, "duration_ms": 1200},
	"stun": {"magnitude": 1.0, "duration_ms": 400},
}

## A well-formed combat state from a possibly-partial dict (pure; input untouched).
static func normalize_state(state: Dictionary) -> Dictionary:
	var s := state.duplicate(true)
	if not s.has("hp"):
		s["hp"] = 100.0
	if not s.has("max_hp"):
		s["max_hp"] = 100.0
	if not (s.get("statuses") is Array):
		s["statuses"] = []
	if not s.has("poise"):
		s["poise"] = 0.0
	if not s.has("i_frame_until_ms"):
		s["i_frame_until_ms"] = 0
	return s

## Apply one ability from caster to target at ctx {now_ms, dir: [x, y]} → deltas:
## {damage_dealt, statuses_added, knockback [x,y], poise_damage, staggered, dodged,
##  target_state, caster_state, zones, transform_to?}.
##
## Rules, in order: an i-frame window zeroes the WHOLE hit (no damage, statuses, or poise);
## `zone` effects are never applied here (the executor spawns a CombatZone from deltas.zones);
## every other effect lands on the TARGET (self-target abilities pass self as target, so a
## `buff` is just a frenzy status on oneself); shields absorb before hp; poise accumulates
## and breaks at POISE_BREAK (staggered + pool reset); `transform` only REPORTS transform_to
## — executing the form swap (sprite/kit/Agent.combat_form) is the executor's job.
static func apply_ability(caster: Dictionary, target: Dictionary, ability: Dictionary, ctx: Dictionary) -> Dictionary:
	var now_ms: int = int(ctx.get("now_ms", 0))
	var cstate := normalize_state(caster)
	var tstate := normalize_state(target)
	var deltas: Dictionary = {
		"damage_dealt": 0.0, "statuses_added": [], "knockback": [0.0, 0.0],
		"poise_damage": 0.0, "staggered": false, "dodged": false, "zones": [],
		"target_state": tstate, "caster_state": cstate,
	}
	if now_ms < int(tstate.get("i_frame_until_ms", 0)):
		deltas["dodged"] = true
		return deltas
	var raw_damage: float = 0.0
	for eff_v in (ability.get("effects", []) as Array):
		if typeof(eff_v) != TYPE_DICTIONARY:
			continue
		var eff: Dictionary = eff_v
		match String(eff.get("kind", "")):
			"damage":
				raw_damage += float(eff.get("amount", 0.0))
			"status":
				var name := String(eff.get("status", ""))
				var st := status_from_name(name, now_ms)
				if st.is_empty():
					st = {"kind": name, "magnitude": 1.0, "duration_ms": 0, "applied_at_ms": now_ms}
				if eff.has("magnitude"):
					st["magnitude"] = float(eff.get("magnitude"))
				if eff.has("duration"):
					st["duration_ms"] = int(round(float(eff.get("duration")) * 1000.0))
				if name == "dot":
					st["tick_ms"] = int(round(float(eff.get("tick", float(DEFAULT_DOT_TICK_MS) / 1000.0)) * 1000.0))
				tstate = apply_status(tstate, st)
				(deltas["statuses_added"] as Array).append(st)
			"buff":
				# A stat buff is a frenzy-family status on the target (self-target abilities
				# pass self): {stat, mult, duration} → kind frenzy, magnitude = mult.
				var buff: Dictionary = {
					"kind": "frenzy", "stat": String(eff.get("stat", "attack_speed")),
					"magnitude": float(eff.get("mult", 1.0)),
					"duration_ms": int(round(float(eff.get("duration", 0.0)) * 1000.0)),
					"applied_at_ms": now_ms,
				}
				tstate = apply_status(tstate, buff)
				(deltas["statuses_added"] as Array).append(buff)
			"transform":
				deltas["transform_to"] = String(eff.get("form", ""))
			"zone":
				(deltas["zones"] as Array).append(eff.duplicate(true))
	# Shields absorb BEFORE hp; the strongest active pool pays first; depleted pools prune.
	var dealt := raw_damage
	if dealt > 0.0:
		var kept: Array = []
		for st_v in (tstate["statuses"] as Array):
			var st: Dictionary = st_v
			if String(st.get("kind", "")) == "shield" and _active(st, now_ms) and dealt > 0.0:
				var pool := float(st.get("magnitude", 0.0))
				var absorbed := minf(pool, dealt)
				dealt -= absorbed
				if pool - absorbed > 0.0:
					var reduced := st.duplicate(true)
					reduced["magnitude"] = pool - absorbed
					kept.append(reduced)
				continue
			kept.append(st)
		tstate["statuses"] = kept
	tstate["hp"] = clampf(float(tstate["hp"]) - dealt, 0.0, float(tstate["max_hp"]))
	deltas["damage_dealt"] = dealt
	# Poise accumulates on the target; the break staggers and resets the pool.
	var pd := float(ability.get("poise_damage", 0.0))
	if pd > 0.0:
		deltas["poise_damage"] = pd
		var poise := float(tstate.get("poise", 0.0)) + pd
		if poise >= POISE_BREAK:
			deltas["staggered"] = true
			poise = 0.0
		tstate["poise"] = poise
	# Knockback rides the hit direction, scaled by the ability's authored pixels.
	var kb := float(ability.get("knockback", 0.0))
	var dir: Array = ctx.get("dir", [0.0, 0.0]) if ctx.get("dir") is Array else [0.0, 0.0]
	if kb > 0.0 and dir.size() >= 2:
		var dx := float(dir[0])
		var dy := float(dir[1])
		var len := sqrt(dx * dx + dy * dy)
		if len > 0.0:
			deltas["knockback"] = [dx / len * kb, dy / len * kb]
	deltas["target_state"] = tstate
	return deltas

## Merge one status into a state under the stacking rules: same kind refreshes the window
## (new applied_at/duration) and keeps the STRONGER magnitude — never multiplies. A dot's
## tick bookkeeping survives the refresh so re-applying grants no immediate extra tick.
static func apply_status(state: Dictionary, status: Dictionary) -> Dictionary:
	var s := normalize_state(state)
	var incoming := status.duplicate(true)
	var out: Array = []
	var merged := false
	for st_v in (s["statuses"] as Array):
		var st: Dictionary = st_v
		if String(st.get("kind", "")) == String(incoming.get("kind", "")) and not merged:
			incoming["magnitude"] = maxf(float(st.get("magnitude", 0.0)), float(incoming.get("magnitude", 0.0)))
			if st.has("last_tick_ms"):
				incoming["last_tick_ms"] = st["last_tick_ms"]
			merged = true
			continue
		out.append(st)
	out.append(incoming)
	s["statuses"] = out
	return s

## Advance statuses to now_ms → {state, dot_damage}. Prunes expired statuses; accumulates
## dot ticks (magnitude per tick_ms, up to expiry, never double-counted). The returned
## state's hp is UNTOUCHED — the caller lands dot_damage through its own damage pipe
## (Agent.take_damage keeps the events/EndGame wiring live).
static func tick_statuses(state: Dictionary, now_ms: int) -> Dictionary:
	var s := normalize_state(state)
	var kept: Array = []
	var dot_damage: float = 0.0
	for st_v in (s["statuses"] as Array):
		var st: Dictionary = st_v
		var applied := int(st.get("applied_at_ms", 0))
		var expires := applied + int(st.get("duration_ms", 0))
		if String(st.get("kind", "")) == "dot":
			var tick := maxi(1, int(st.get("tick_ms", DEFAULT_DOT_TICK_MS)))
			var last := int(st.get("last_tick_ms", applied))
			var stop := mini(now_ms, expires)
			while last + tick <= stop:
				last += tick
				dot_damage += float(st.get("magnitude", 0.0))
			st = st.duplicate(true)
			st["last_tick_ms"] = last
		if now_ms < expires:
			kept.append(st)
	s["statuses"] = kept
	return {"state": s, "dot_damage": dot_damage}

## True when the state carries an unexpired status of this kind at now_ms.
static func has_status(state: Dictionary, kind: String, now_ms: int) -> bool:
	return status_magnitude(state, kind, now_ms) > 0.0

## The strongest active magnitude of this kind at now_ms (0.0 when none).
static func status_magnitude(state: Dictionary, kind: String, now_ms: int) -> float:
	var best: float = 0.0
	for st_v in (state.get("statuses", []) as Array):
		if typeof(st_v) != TYPE_DICTIONARY:
			continue
		var st: Dictionary = st_v
		if String(st.get("kind", "")) == kind and _active(st, now_ms):
			best = maxf(best, float(st.get("magnitude", 0.0)))
	return best

## Build a status dict from a bare authored name (zone statuses ride as names); {} when the
## name has no authored default (callers fill their own fields).
static func status_from_name(name: String, now_ms: int, source: String = "") -> Dictionary:
	if not NAMED_STATUS_DEFAULTS.has(name):
		return {}
	var d: Dictionary = NAMED_STATUS_DEFAULTS[name]
	var st: Dictionary = {
		"kind": name, "magnitude": float(d.get("magnitude", 1.0)),
		"duration_ms": int(d.get("duration_ms", 0)), "applied_at_ms": now_ms,
	}
	if source != "":
		st["source"] = source
	return st

## Cooldown ledger (plain dict ability_id -> ready_at_ms): ready when unmarked or elapsed.
static func ledger_ready(ledger: Dictionary, ability_id: String, now_ms: int) -> bool:
	return now_ms >= int(ledger.get(ability_id, 0))

## Mark an ability used at now_ms → NEW ledger (pure) with ready_at = now + cooldown_ms.
static func ledger_mark(ledger: Dictionary, ability_id: String, now_ms: int, cooldown_ms: int) -> Dictionary:
	var l := ledger.duplicate(true)
	l[ability_id] = now_ms + cooldown_ms
	return l

## True when a status is alive at now_ms (starts at applied_at, ends at +duration).
static func _active(st: Dictionary, now_ms: int) -> bool:
	var applied := int(st.get("applied_at_ms", 0))
	return now_ms >= applied and now_ms < applied + int(st.get("duration_ms", 0))
