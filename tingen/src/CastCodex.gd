extends Object
## M_cast (user request) — THE CAST dossier panel's pure VIEW-MODEL builder.
##
## v2 (user correction): "the point of the roulette is for me to see the character information,
## ALL of it. for now, write everything on there, including their goals, personality, their
## powers, abilities, etc." — the panel is (for now) a FULL DESIGN-REFERENCE DOSSIER:
##   * SHOW_ALL (the ONE gate flag) ships TRUE: every Beyonder card is built REVEALED — pathway/
##     sequence, the form family, the beneath-the-mask monster art, and BOTH forms' full kits
##     with each ability's REAL numbers (damage/cast/cooldown/cost/range from abilities.json).
##     The codex-gate machinery is KEPT behind the flag (build_cards' show_all arg) so a
##     player-facing gated mode can return later; `learned` stays truthful to the ledger and a
##     learned line is still quoted either way.
##   * EVERY authored npcs.json field rides the card: persona (description + voice), GOALS
##     (intent + the goals list), SECRETS (the actual strings), KNOWLEDGE, the full phase
##     SCHEDULE as readable district lines, and a generic RECORDS catch-all for any field no
##     named section consumed (tier / vision_r / max_hp / task / carried_items / tint /
##     dialogue_id / a future field) — so new authored data can never silently vanish.
##     Underscore-prefixed keys (_pathway_note …) are authoring comments (JSON's comment
##     convention), not character data — excluded by CONVENTION, never by id.
##
## Mundane NPCs (no combat_form / pathway data) are never redacted or revealed: "No touch of
## the Beyond" — but they carry the same full civilian dossier.
##
## PURE + headless-testable (the MetaSurface pattern): no autoload reads, no scene work, no RNG.
## ENGINE-NEUTRAL (§8): no NPC-id branches anywhere. The codex records `adversary:<combat_form>`
## fact-ids (RunManager._on_meta_world_event stamps the DOWNED form — the human phase if the prey
## fell early, the monster phase after its descend). The NPC<->form mapping is therefore walked
## from DATA alone: npcs.json `combat_form` is the start of a FORM FAMILY grown through the
## `transform` effects of the kit/reflex abilities in abilities.json (assume_form / *_descend all
## carry their destination form) — a record of ANY family member reveals the NPC. Districts for
## the haunts/schedule lines come from districts.json map_polygons via the MapProjection math.

## v2 (user correction): the SHIPPED default is show-everything — a design-reference dossier.
## Flip to false (or pass show_all=false) to restore the codex-gated player-facing mode.
const SHOW_ALL := true

const REDACTED_LINE := "Their nature is not yet known to you."
const MUNDANE_LINE := "No touch of the Beyond has been observed."
## The M16 portrait-convention seam lives on NPC.gd as a static; load() (untyped) dispatches it
## (a typed preload of a class_name-less script can't — the Portrait.gd pattern).
const NPC_SCRIPT_PATH := "res://src/NPC.gd"

## npcs.json fields a NAMED dossier section consumes; everything else (non-underscore) flows to
## the generic RECORDS catch-all. A list of SECTION names, not NPC ids — engine-neutral.
const SECTION_FIELDS: Array = ["name", "role", "description", "voice", "intent", "goals",
	"secrets", "knowledge", "schedule", "pathway", "sequence", "combat_form", "sprite"]

## The one entry point: (npcs.json defs, combat_forms defs, abilities id->def, districts array,
## the persistent codex array, the gate flag) -> an Array of card Dictionaries in roster order.
## show_all=null takes the shipped SHOW_ALL default; tests pass false to pin the gated mode.
static func build_cards(npcs: Dictionary, forms: Dictionary, abilities: Dictionary,
		districts: Array, codex: Array, show_all: Variant = null) -> Array:
	var all: bool = SHOW_ALL if show_all == null else bool(show_all)
	var learned := learned_adversary_forms(codex)
	var out: Array = []
	for id in npcs.keys():
		var def_v: Variant = npcs[id]
		if not def_v is Dictionary:
			continue
		out.append(_card(String(id), def_v as Dictionary, forms, abilities, districts, learned, all))
	return out

## The codex's learned ADVERSARY forms: form id -> its learned ledger line. Only `adversary:`
## fact-ids gate the reveal — knowing a pathway or an ending is not knowing the person.
static func learned_adversary_forms(codex: Array) -> Dictionary:
	var known: Dictionary = {}
	for e in codex:
		if e is Dictionary:
			var fid := String((e as Dictionary).get("id", ""))
			if fid.begins_with("adversary:"):
				known[fid.substr(10)] = String((e as Dictionary).get("learned", ""))
	return known

## The FORM FAMILY of a start form: the start plus every form reachable through the `transform`
## effects of the abilities its kits/reflexes name, transitively (cycle-guarded). Pure data walk.
static func form_family(start: String, forms: Dictionary, abilities: Dictionary) -> Array:
	var fam: Array = []
	if start == "":
		return fam
	var stack: Array = [start]
	while not stack.is_empty():
		var f := String(stack.pop_front())
		if f == "" or fam.has(f):
			continue
		fam.append(f)
		var fd: Dictionary = forms.get(f, {}) if forms.get(f) is Dictionary else {}
		var aids: Array = []
		var kit: Variant = fd.get("kit", [])
		if kit is Array:
			for aid in (kit as Array):
				aids.append(String(aid))
		var reflexes: Variant = fd.get("reflexes", [])
		if reflexes is Array:
			for r in (reflexes as Array):
				if r is Dictionary and (r as Dictionary).get("do") is Dictionary:
					var doo: Dictionary = (r as Dictionary)["do"]
					if String(doo.get("kind", "")) == "cast":
						aids.append(String(doo.get("ability", "")))
		for aid in aids:
			var a: Dictionary = abilities.get(aid, {}) if abilities.get(aid) is Dictionary else {}
			var effs: Variant = a.get("effects", [])
			if effs is Array:
				for e in (effs as Array):
					if e is Dictionary and String((e as Dictionary).get("kind", "")) == "transform":
						stack.append(String((e as Dictionary).get("form", "")))
	return fam

## One NPC's card model.
static func _card(id: String, def: Dictionary, forms: Dictionary, abilities: Dictionary,
		districts: Array, learned_forms: Dictionary, show_all: bool) -> Dictionary:
	var fam := form_family(String(def.get("combat_form", "")), forms, abilities)
	var is_beyonder: bool = (not fam.is_empty()) or String(def.get("pathway", "")) != ""
	var learned := false
	var lines: Array = []
	for f in fam:
		if learned_forms.has(f):
			learned = true
			if String(learned_forms[f]) != "" and not lines.has(String(learned_forms[f])):
				lines.append(String(learned_forms[f]))
	var state := "mundane"
	var secret_line := MUNDANE_LINE
	var secret: Dictionary = {}
	if is_beyonder:
		if learned or show_all:
			# SHOW_ALL (design reference) or a real ledger record — the full secret layer.
			state = "revealed"
			secret_line = ""
			secret = _secret(def, fam, forms, abilities)
		else:
			state = "redacted"
			secret_line = REDACTED_LINE
			lines = []   # an unlearned card quotes nothing
	var display_name := String(def.get("name", ""))
	if display_name == "":
		display_name = id.capitalize()
	var sched: Dictionary = def.get("schedule", {}) if def.get("schedule") is Dictionary else {}
	return {
		"id": id,
		"name": display_name,
		"role": String(def.get("role", "")).capitalize(),
		"haunts": haunts_line(sched, districts),
		"description": String(def.get("description", "")),
		"portrait": portrait_path(id, def),
		# v2 (user correction): the WHOLE authored dossier, on every card.
		"voice": String(def.get("voice", "")),
		"goals": goal_lines(def),
		"secrets": _string_list(def.get("secrets", [])),
		"knowledge": _string_list(def.get("knowledge", [])),
		"schedule_lines": schedule_lines(sched, districts),
		"records": record_lines(def),
		"is_beyonder": is_beyonder,
		"learned": learned,
		"state": state,
		"secret_line": secret_line,
		"secret": secret,
		"codex_lines": lines,
	}

## GOALS: the authored `intent` (the driving want) first, then every `goals` entry —
## description + its authored tier tag.
static func goal_lines(def: Dictionary) -> Array:
	var out: Array = []
	var intent := String(def.get("intent", "")).strip_edges()
	if intent != "":
		out.append(intent)
	var gs: Variant = def.get("goals", [])
	if gs is Array:
		for g in (gs as Array):
			if g is Dictionary:
				var line := String((g as Dictionary).get("description", "")).strip_edges()
				var tier := String((g as Dictionary).get("tier", "")).strip_edges()
				if line != "":
					out.append(line + ("  (%s)" % tier if tier != "" else ""))
			elif String(g).strip_edges() != "":
				out.append(String(g).strip_edges())
	return out

## The generic RECORDS catch-all: every authored field no named section consumed, as readable
## "key: value" lines. Underscore-prefixed keys are authoring comments — skipped by convention.
## Empty values ("", [], {}) carry no information and are skipped.
static func record_lines(def: Dictionary) -> Array:
	var out: Array = []
	for k in def.keys():
		var key := String(k)
		if key.begins_with("_") or SECTION_FIELDS.has(key):
			continue
		var v: Variant = def[k]
		if (v is String and String(v) == "") \
				or (v is Array and (v as Array).is_empty()) \
				or (v is Dictionary and (v as Dictionary).is_empty()):
			continue
		out.append("%s: %s" % [key, _fmt_value(v)])
	return out

## A readable value: whole floats print as ints, arrays as "(a, b, …)", dicts as "k v" pairs.
static func _fmt_value(v: Variant) -> String:
	if v is float or v is int:
		return _num(float(v))
	if v is Array:
		var parts := PackedStringArray()
		for e in (v as Array):
			parts.append(_fmt_value(e))
		return "(%s)" % ", ".join(parts)
	if v is Dictionary:
		var kv := PackedStringArray()
		for k in (v as Dictionary).keys():
			kv.append("%s %s" % [String(k), _fmt_value((v as Dictionary)[k])])
		return ", ".join(kv)
	return String(str(v))

## A trimmed number: 1.0 -> "1", 0.3 -> "0.3".
static func _num(f: float) -> String:
	if absf(f - roundf(f)) < 0.0005:
		return str(int(roundf(f)))
	return str(f)

## The revealed SECRET layer: pathway (+ an authored `sequence` when the data carries one), the
## form family, the monster face (the first family form flagged `monster:true` + its enemy art if
## the file exists), the union ability kit across the family's phases, and — v2 — form_kits:
## EACH phase's own kit with every ability's real numbers (the design-reference detail).
static func _secret(def: Dictionary, fam: Array, forms: Dictionary, abilities: Dictionary) -> Dictionary:
	var kit_ids: Array = []
	var form_kits: Array = []
	for f in fam:
		var fd: Dictionary = forms.get(f, {}) if forms.get(f) is Dictionary else {}
		var entries: Array = []
		var kit: Variant = fd.get("kit", [])
		if kit is Array:
			for aid in (kit as Array):
				entries.append(ability_entry(String(aid), abilities))
				if not kit_ids.has(String(aid)):
					kit_ids.append(String(aid))
		form_kits.append({
			"form": String(f),
			"monster": bool(fd.get("monster", false)),
			"abilities": entries,
		})
	var kit_out: Array = []
	for aid in kit_ids:
		kit_out.append(ability_entry(aid, abilities))
	var monster := ""
	for f in fam:
		if forms.get(f) is Dictionary and bool((forms[f] as Dictionary).get("monster", false)):
			monster = String(f)
			break
	# N6 (B1): the monster face rides the ONE N4 form->art resolver (alias rung + convention
	# rung), fed THIS builder's forms dict — an alias-only form (combat_forms.json `sprite`
	# with no enemies/<form>.png of its own) now carries its painting on the card too.
	var art := ""
	if monster != "":
		var mfd: Dictionary = forms.get(monster, {}) if forms.get(monster) is Dictionary else {}
		art = CombatExecutor.resolve_form_sprite_path(monster, mfd)
	return {
		"pathway": String(def.get("pathway", "")),
		"sequence": int(def.get("sequence", 0)),   # 0 = unauthored (hidden by the renderer)
		"forms": fam.duplicate(),
		"monster_form": monster,
		"monster_art": art,
		"abilities": kit_out,
		"form_kits": form_kits,
	}

## One kit entry: the flavor (name + one-liner) PLUS the real numbers from abilities.json —
## damage (summed over damage effects), cast_time, cooldown, range, cost — and a readable
## pre-joined `stats` line ("dmg 30 · cast 0.3s · cd 1s · cost 10 spirituality · range 500").
static func ability_entry(aid: String, abilities: Dictionary) -> Dictionary:
	var a: Dictionary = abilities.get(aid, {}) if abilities.get(aid) is Dictionary else {}
	var nm := String(a.get("name", "")).strip_edges()
	var dmg := 0.0
	var effs: Variant = a.get("effects", [])
	if effs is Array:
		for e in (effs as Array):
			if e is Dictionary and String((e as Dictionary).get("kind", "")) == "damage":
				dmg += float((e as Dictionary).get("amount", 0.0))
	var cost: Dictionary = a.get("cost", {}) if a.get("cost") is Dictionary else {}
	var parts := PackedStringArray()
	if dmg > 0.0:
		parts.append("dmg %s" % _num(dmg))
	if float(a.get("cast_time", 0.0)) > 0.0:
		parts.append("cast %ss" % _num(float(a.get("cast_time", 0.0))))
	if float(a.get("cooldown", 0.0)) > 0.0:
		parts.append("cd %ss" % _num(float(a.get("cooldown", 0.0))))
	for k in cost.keys():
		parts.append("cost %s %s" % [_num(float(cost[k])), String(k)])
	if float(a.get("range", 0.0)) > 0.0:
		parts.append("range %s" % _num(float(a.get("range", 0.0))))
	if float(a.get("aoe_radius", 0.0)) > 0.0:
		parts.append("aoe %s" % _num(float(a.get("aoe_radius", 0.0))))
	return {
		"id": aid,
		"name": nm if nm != "" else String(aid).replace("_", " "),
		"description": String(a.get("description", "")),
		"damage": dmg,
		"cast_time": float(a.get("cast_time", 0.0)),
		"cooldown": float(a.get("cooldown", 0.0)),
		"range": float(a.get("range", 0.0)),
		"cost": cost.duplicate(true),
		"stats": " · ".join(parts),
	}

## The full SCHEDULE, readable: one "Phase — place" line per authored phase, in authored order
## (the parsed JSON Dictionary preserves it). The place is the district the spot falls in;
## an interior-only / off-map spot reads as the city itself.
static func schedule_lines(schedule: Dictionary, districts: Array) -> Array:
	var out: Array = []
	for phase in schedule.keys():
		var pos_v: Variant = schedule[phase]
		if pos_v is Array and (pos_v as Array).size() >= 2:
			var world := Vector2(float((pos_v as Array)[0]), float((pos_v as Array)[1]))
			var nm := district_name_at(world, districts)
			out.append("%s — %s" % [String(phase).capitalize(),
				nm if nm != "" else "the streets of Tingen"])
	return out

## The HAUNTS line: the district names the NPC's authored schedule spots fall in, deduped in
## phase order. No hit (an interior-only schedule) reads as the city itself.
static func haunts_line(schedule: Dictionary, districts: Array) -> String:
	var names: Array = []
	for phase in schedule.keys():
		var pos_v: Variant = schedule[phase]
		if pos_v is Array and (pos_v as Array).size() >= 2:
			var world := Vector2(float((pos_v as Array)[0]), float((pos_v as Array)[1]))
			var nm := district_name_at(world, districts)
			if nm != "" and not names.has(nm):
				names.append(nm)
	if names.is_empty():
		return "The streets of Tingen"
	return ", ".join(PackedStringArray(names))

## The district a WORLD position falls in (world coords -> map-image space via
## MapProjection.CITY_SCALE -> districts.json map_polygon point tests), or "".
static func district_name_at(world: Vector2, districts: Array) -> String:
	var mp: Vector2 = MapProjection.world_to_map(world)
	for d in districts:
		if d is Dictionary and (d as Dictionary).get("map_polygon") is Array:
			var poly: Array = (d as Dictionary)["map_polygon"]
			var pts := PackedVector2Array()
			for i in range(0, poly.size() - 1, 2):
				pts.append(Vector2(float(poly[i]), float(poly[i + 1])))
			if pts.size() >= 3 and Geometry2D.is_point_in_polygon(mp, pts):
				return String((d as Dictionary).get("name", ""))
	return ""

## A clean Array-of-String from an authored array field.
static func _string_list(v: Variant) -> Array:
	var out: Array = []
	if v is Array:
		for e in (v as Array):
			if String(e).strip_edges() != "":
				out.append(String(e))
	return out

## The portrait path, through the ONE existing convention seam (NPC.resolve_sprite_path:
## explicit `sprite` override, else assets/characters/<id>.png, else "" — never a broken path).
static func portrait_path(id: String, def: Dictionary) -> String:
	var npc_script = load(NPC_SCRIPT_PATH)
	if npc_script == null:
		return ""
	return String(npc_script.resolve_sprite_path(id, def))
