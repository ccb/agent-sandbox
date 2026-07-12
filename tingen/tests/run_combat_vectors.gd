extends SceneTree
## M9 combat vector runner (COMBAT_SPEC.md). Run standalone with:
##   godot --headless --path tingen -s tests/run_combat_vectors.gd
## Also folded into the main suite (run_tests.gd `_test_combat_vectors`) so CI-equivalence
## holds — both entry points share the SAME fill/compare statics below.
##
## Loads agent-sidecar/cognition/combat_test_vectors.json and re-runs every vector against
## the pure combat statics (CombatResolver / ReflexRules / TacticalBrain + the ActionCommit
## style constants). A vector passes when the freshly computed result deep-equals the stored
## `expected` (floats at 1e-6 tolerance; strings/bools/shapes exact). The SAME fixtures must
## pass in Yumina's TypeScript port; when implementations diverge, the fixtures are the
## arbiter. Expected values are MACHINE-GENERATED (tests/dump_combat_vectors.gd) — never
## hand-edit them; regenerate after an intentional algorithm change.

const TOL: float = 1e-6

## The vectors live beside the cognition fixtures (the M9 parity deliverable), outside res://.
static func vectors_path() -> String:
	return ProjectSettings.globalize_path("res://").path_join("../agent-sidecar/cognition/combat_test_vectors.json")

static func load_vectors() -> Dictionary:
	var raw := FileAccess.get_file_as_string(vectors_path())
	var parsed: Variant = JSON.parse_string(raw)
	return parsed if parsed is Dictionary else {}

## ---- the one entry point (returns {passed, failed}; prints cognition-runner-style lines) ----

static func run_all() -> Dictionary:
	var c := {"passed": 0, "failed": 0}
	var V := load_vectors()
	if V.is_empty():
		_check(c, false, "combat_test_vectors.json loads from %s" % vectors_path())
		return c
	var kits: Dictionary = V.get("kits", {})
	_run_constants(c, V.get("constants", {}))
	print("[resolver_apply]")
	for v in (V.get("resolver_apply", []) as Array):
		_vector(c, v, fill_apply(v), "resolver_apply")
	print("[resolver_chain]")
	for v in (V.get("resolver_chain", []) as Array):
		_vector(c, v, fill_chain(v), "resolver_chain")
	print("[resolver_sequence]")
	for v in (V.get("resolver_sequence", []) as Array):
		_vector(c, v, fill_sequence(v), "resolver_sequence")
	print("[resolver_ledger]")
	for v in (V.get("resolver_ledger", []) as Array):
		_vector(c, v, fill_ledger(v), "resolver_ledger")
	print("[reflex]")
	for v in (V.get("reflex", []) as Array):
		_vector(c, v, fill_reflex(v), "reflex")
	print("[tactical_bands]")
	for v in (V.get("tactical_bands", []) as Array):
		_vector(c, v, fill_bands(v, kits), "tactical_bands")
	print("[tactical_band_of]")
	for v in (V.get("tactical_band_of", []) as Array):
		_vector(c, v, fill_band_of(v), "tactical_band_of")
	print("[tactical_choose]")
	for v in (V.get("tactical_choose", []) as Array):
		_vector(c, v, fill_choose(v, kits), "tactical_choose")
	return c

## ---- fill functions: recompute a vector's `expected` from the live implementation.
## The dump harness WRITES these results; the runner COMPARES against the stored ones. ----

static func fill_all(V: Dictionary) -> Dictionary:
	var out := V.duplicate(true)
	var kits: Dictionary = V.get("kits", {})
	out["resolver_apply"] = (V.get("resolver_apply", []) as Array).map(fill_apply)
	out["resolver_chain"] = (V.get("resolver_chain", []) as Array).map(fill_chain)
	out["resolver_sequence"] = (V.get("resolver_sequence", []) as Array).map(fill_sequence)
	out["resolver_ledger"] = (V.get("resolver_ledger", []) as Array).map(fill_ledger)
	out["reflex"] = (V.get("reflex", []) as Array).map(fill_reflex)
	out["tactical_bands"] = (V.get("tactical_bands", []) as Array).map(
		func(v: Dictionary) -> Dictionary: return fill_bands(v, kits))
	out["tactical_band_of"] = (V.get("tactical_band_of", []) as Array).map(fill_band_of)
	out["tactical_choose"] = (V.get("tactical_choose", []) as Array).map(
		func(v: Dictionary) -> Dictionary: return fill_choose(v, kits))
	return out

## One apply_ability call -> the projected delta contract (COMBAT_SPEC.md §1.4).
static func fill_apply(v: Dictionary) -> Dictionary:
	var out := v.duplicate(true)
	var d := CombatResolver.apply_ability(v.get("caster", {}), v.get("target", {}),
		v.get("ability", {}), v.get("ctx", {}))
	out["expected"] = _project_deltas(d, true)
	return out

## Sequential hits threading target_state through (poise accumulation vectors).
static func fill_chain(v: Dictionary) -> Dictionary:
	var out := v.duplicate(true)
	var t: Dictionary = v.get("target", {})
	for hit_v in (out.get("hits", []) as Array):
		var hit: Dictionary = hit_v
		var d := CombatResolver.apply_ability({}, t, hit.get("ability", {}), hit.get("ctx", {}))
		hit["expected"] = _project_deltas(d, false)
		t = d.get("target_state", {})
	return out

## apply_status / tick_statuses / status queries threading one state through.
static func fill_sequence(v: Dictionary) -> Dictionary:
	var out := v.duplicate(true)
	var state := CombatResolver.normalize_state(v.get("initial", {}))
	for op_v in (out.get("ops", []) as Array):
		var op: Dictionary = op_v
		match String(op.get("op", "")):
			"apply_status":
				state = CombatResolver.apply_status(state, op.get("status", {}))
				op["expected"] = {"status_count": (state.get("statuses", []) as Array).size()}
			"tick":
				var r := CombatResolver.tick_statuses(state, int(op.get("now_ms", 0)))
				state = r.get("state", {})
				op["expected"] = {"dot_damage": r.get("dot_damage", 0.0),
					"status_count": (state.get("statuses", []) as Array).size(),
					"hp": state.get("hp", 0.0)}
			"query_magnitude":
				op["expected"] = CombatResolver.status_magnitude(state, String(op.get("kind", "")), int(op.get("now_ms", 0)))
			"query_has":
				op["expected"] = CombatResolver.has_status(state, String(op.get("kind", "")), int(op.get("now_ms", 0)))
	return out

## ledger_ready / ledger_mark ops threading one ledger through.
static func fill_ledger(v: Dictionary) -> Dictionary:
	var out := v.duplicate(true)
	var led: Dictionary = {}
	for op_v in (out.get("ops", []) as Array):
		var op: Dictionary = op_v
		var ability := String(op.get("ability", ""))
		if String(op.get("op", "")) == "ready":
			op["expected"] = CombatResolver.ledger_ready(led, ability, int(op.get("now_ms", 0)))
		else:
			led = CombatResolver.ledger_mark(led, ability, int(op.get("now_ms", 0)), int(op.get("cooldown_ms", 0)))
			op["expected"] = {"ready_at_ms": led[ability]}
	return out

## One ReflexRules.evaluate call. JSON carries fired_counts with STRING keys (JSON objects);
## the implementation keys by INT rule index — the conversion here is part of the binding.
static func fill_reflex(v: Dictionary) -> Dictionary:
	var out := v.duplicate(true)
	var counts: Dictionary = {}
	for k in (v.get("fired_counts", {}) as Dictionary):
		counts[int(String(k))] = int((v.get("fired_counts", {}) as Dictionary)[k])
	out["expected"] = ReflexRules.evaluate(v.get("rules", []), v.get("event", {}),
		v.get("self_state", {}), int(v.get("now_ms", 0)), counts)
	return out

static func fill_bands(v: Dictionary, kits: Dictionary) -> Dictionary:
	var out := v.duplicate(true)
	out["expected"] = TacticalBrain.bands_for(_kit(v.get("kit"), kits))
	return out

static func fill_band_of(v: Dictionary) -> Dictionary:
	var out := v.duplicate(true)
	out["expected"] = TacticalBrain.band_of(float(v.get("dist", 0.0)), v.get("bands", {}))
	return out

static func fill_choose(v: Dictionary, kits: Dictionary) -> Dictionary:
	var out := v.duplicate(true)
	var view: Dictionary = (v.get("view", {}) as Dictionary).duplicate(true)
	view["kit"] = _kit(view.get("kit"), kits)
	out["expected"] = TacticalBrain.choose(view, String(v.get("style", "")))
	return out

## ---- internals ----

## A string kit is a ref into the top-level `kits` map; an array is inline.
static func _kit(kit_v: Variant, kits: Dictionary) -> Array:
	if kit_v is String:
		return kits.get(kit_v, []) as Array
	return kit_v if kit_v is Array else []

## The language-neutral projection of apply_ability's deltas (states flattened to the pinned
## fields; transform_to present only when the resolver reported one).
static func _project_deltas(d: Dictionary, full: bool) -> Dictionary:
	var t: Dictionary = d.get("target_state", {})
	var exp: Dictionary = {
		"damage_dealt": d.get("damage_dealt", 0.0),
		"poise_damage": d.get("poise_damage", 0.0),
		"staggered": d.get("staggered", false),
		"dodged": d.get("dodged", false),
		"target_hp": t.get("hp", 0.0),
		"target_poise": t.get("poise", 0.0),
	}
	if full:
		exp["knockback"] = d.get("knockback", [0.0, 0.0])
		exp["statuses_added"] = d.get("statuses_added", [])
		exp["zones"] = d.get("zones", [])
		exp["target_statuses"] = t.get("statuses", [])
		exp["caster_hp"] = (d.get("caster_state", {}) as Dictionary).get("hp", 0.0)
	if d.has("transform_to"):
		exp["transform_to"] = d["transform_to"]
	return exp

## The pinned constants must match the implementation on BOTH sides of the port.
static func _run_constants(c: Dictionary, k: Dictionary) -> void:
	print("[constants]")
	_check(c, _eq(CombatResolver.POISE_BREAK, k.get("POISE_BREAK")), "POISE_BREAK")
	_check(c, _eq(CombatResolver.DEFAULT_DOT_TICK_MS, k.get("DEFAULT_DOT_TICK_MS")), "DEFAULT_DOT_TICK_MS")
	_check(c, _eq(CombatResolver.STAGGER_STUN_MS, k.get("STAGGER_STUN_MS")), "STAGGER_STUN_MS")
	_check(c, _eq(CombatResolver.KNOCKBACK_MS, k.get("KNOCKBACK_MS")), "KNOCKBACK_MS")
	_check(c, _eq(CombatResolver.STATUS_KINDS, k.get("STATUS_KINDS")), "STATUS_KINDS")
	_check(c, _eq(CombatResolver.NAMED_STATUS_DEFAULTS, k.get("NAMED_STATUS_DEFAULTS")), "NAMED_STATUS_DEFAULTS")
	_check(c, _eq(ReflexRules.DELAY_MIN_MS, k.get("DELAY_MIN_MS")), "DELAY_MIN_MS")
	_check(c, _eq(ReflexRules.DELAY_MAX_MS, k.get("DELAY_MAX_MS")), "DELAY_MAX_MS")
	_check(c, _eq(ReflexRules.DEFAULT_DELAY_MS, k.get("DEFAULT_DELAY_MS")), "DEFAULT_DELAY_MS")
	_check(c, _eq(TacticalBrain.DEFAULT_MELEE_BAND, k.get("DEFAULT_MELEE_BAND")), "DEFAULT_MELEE_BAND")
	_check(c, _eq(TacticalBrain.DEFAULT_NEAR_BAND, k.get("DEFAULT_NEAR_BAND")), "DEFAULT_NEAR_BAND")
	_check(c, _eq(TacticalBrain.TACTICAL_HZ, k.get("TACTICAL_HZ")), "TACTICAL_HZ")
	_check(c, _eq(TacticalBrain.TICK_MS, k.get("TICK_MS")), "TICK_MS")
	_check(c, _eq(TacticalBrain.STYLES, k.get("STYLES")), "STYLES mask table")
	_check(c, _eq(ActionCommit.ENGAGE_STYLES, k.get("ENGAGE_STYLES")), "ENGAGE_STYLES")
	_check(c, _eq(ActionCommit.DEFAULT_ENGAGE_STYLE, k.get("DEFAULT_ENGAGE_STYLE")), "DEFAULT_ENGAGE_STYLE")

## One vector = one check: the recomputed vector must deep-equal the stored one (the only
## difference fill_* introduces is the expected fields, so whole-vector equality IS the test).
static func _vector(c: Dictionary, stored: Dictionary, recomputed: Dictionary, cat: String) -> void:
	_check(c, _eq(recomputed, stored), "%s: %s" % [cat, String(stored.get("name", "?"))],
		recomputed, stored)

static func _check(c: Dictionary, cond: bool, label: String, got: Variant = null, want: Variant = null) -> void:
	if cond:
		c["passed"] = int(c["passed"]) + 1
		print("  PASS  %s" % label)
	else:
		c["failed"] = int(c["failed"]) + 1
		printerr("  FAIL  %s" % label)
		if want != null:
			printerr("    want: %s" % JSON.stringify(want))
			printerr("    got:  %s" % JSON.stringify(got))

## Deep equality with 1e-6 float tolerance (ints and floats compare numerically — JSON
## numbers all parse as floats); bools compare strictly; dict key SETS must match exactly.
static func _eq(a: Variant, b: Variant) -> bool:
	if typeof(a) == TYPE_BOOL or typeof(b) == TYPE_BOOL:
		return typeof(a) == typeof(b) and a == b
	if (typeof(a) == TYPE_INT or typeof(a) == TYPE_FLOAT) \
			and (typeof(b) == TYPE_INT or typeof(b) == TYPE_FLOAT):
		return absf(float(a) - float(b)) < TOL
	if a is Dictionary and b is Dictionary:
		if (a as Dictionary).size() != (b as Dictionary).size():
			return false
		for key in (a as Dictionary):
			if not (b as Dictionary).has(key) or not _eq(a[key], b[key]):
				return false
		return true
	if a is Array and b is Array:
		if (a as Array).size() != (b as Array).size():
			return false
		for i in range((a as Array).size()):
			if not _eq(a[i], b[i]):
				return false
		return true
	return typeof(a) == typeof(b) and a == b

## ---- standalone -s entry ----

func _init() -> void:
	var r := run_all()
	print("\n=== %d passed, %d failed ===" % [int(r["passed"]), int(r["failed"])])
	quit(1 if int(r["failed"]) > 0 else 0)
