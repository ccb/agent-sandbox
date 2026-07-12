extends Node
## Ability + combat-form definitions (autoload `AbilityDB`) — combat plan §M1.
##
## Loads data/abilities.json (the shared-shape ability schema: id, class, cast_time telegraph,
## cooldown, cost, range, motion, projectile, typed effects[], anim, i_frames — design doc §2,
## field-parity with Yumina's types.ts is the M9 deliverable) and data/combat_forms.json (per-form
## kits + default_style + data reflex rows). Definitions are static content, read-only at runtime:
## the M2 resolver/executor and the M3 tactical/reflex layers consume them; nothing here executes.
## References are validated at load — a kit or reflex naming an ability that doesn't exist, or a
## transform effect naming an unknown form, warns loudly instead of failing silently in a fight.

const ABILITIES_PATH: String = "res://data/abilities.json"
const FORMS_PATH: String = "res://data/combat_forms.json"

## The effect vocabulary the M2 resolver will implement. An unknown kind is authoring drift —
## warn at load, don't wait for a fight to no-op.
const EFFECT_KINDS: Array = ["damage", "status", "buff", "zone", "transform"]

var _abilities: Dictionary = {}   # id -> Dictionary (raw def)
var _forms: Dictionary = {}       # form -> Dictionary (kit/default_style/reflexes)
## M28 — the PER-PATHWAY player base-kit table (combat_forms.json `_player_base_kits`): pathway -> the
## player's base kit for that build. NOT a combat_form (loaded out of the form loop, keyed on the
## reserved leading-underscore key). Consulted by kit_for('player') so selecting a pathway swaps the
## player's base kit through the ONE existing kit seam; a pathway absent here falls back to the 'player'
## form (Hunter/DEFAULT — unchanged, so the pinned sims stay byte-identical). Engine-neutral: data only.
var _player_base_kits: Dictionary = {}

func _ready() -> void:
	_load()

func _load() -> void:
	_abilities.clear()
	_forms.clear()
	# abilities.json: { "abilities": [ {id, ...}, ... ] }
	if not FileAccess.file_exists(ABILITIES_PATH):
		push_error("AbilityDB: missing %s" % ABILITIES_PATH)
	else:
		var parsed: Variant = JSON.parse_string(FileAccess.get_file_as_string(ABILITIES_PATH))
		if typeof(parsed) != TYPE_DICTIONARY:
			push_error("AbilityDB: %s is not a JSON object" % ABILITIES_PATH)
		elif typeof(parsed.get("abilities")) != TYPE_ARRAY:
			# Shape guard (review M1 #3): a blind `as Array` cast on authored-wrong data hard-errors
			# mid-load and silently skips the rest of the boot validation. Guard + report instead.
			push_error("AbilityDB: %s 'abilities' must be an array" % ABILITIES_PATH)
		else:
			for entry in (parsed.get("abilities") as Array):
				if typeof(entry) != TYPE_DICTIONARY:
					push_warning("AbilityDB: non-object ability entry skipped")
					continue
				var id := String((entry as Dictionary).get("id", ""))
				if id == "":
					push_warning("AbilityDB: ability with no id skipped")
					continue
				if _abilities.has(id):
					push_warning("AbilityDB: duplicate ability id '%s' — later entry wins" % id)
				_abilities[id] = entry
	# combat_forms.json: { form: {kit: [...], default_style, reflexes: [...]}, ... }
	if not FileAccess.file_exists(FORMS_PATH):
		push_error("AbilityDB: missing %s" % FORMS_PATH)
	else:
		var fparsed: Variant = JSON.parse_string(FileAccess.get_file_as_string(FORMS_PATH))
		if typeof(fparsed) != TYPE_DICTIONARY:
			push_error("AbilityDB: %s is not a JSON object" % FORMS_PATH)
		else:
			for form in (fparsed as Dictionary).keys():
				var fkey := String(form)
				# M28: the reserved `_player_base_kits` key is the per-pathway player base-kit TABLE, not a
				# combat_form — capture it and skip it in the form loop (leading-underscore = reserved).
				if fkey == "_player_base_kits":
					if typeof(fparsed[form]) == TYPE_DICTIONARY:
						_player_base_kits = fparsed[form]
					continue
				if typeof(fparsed[form]) == TYPE_DICTIONARY:
					_forms[fkey] = fparsed[form]
	for problem in validate_refs(_abilities, _forms):
		push_warning("AbilityDB: %s" % problem)
	# M28: the per-pathway player base-kit table's abilities must resolve too (it is not a form, so the
	# form loop above doesn't validate it) — warn at load on a dangling ref, same as a kit would.
	for pw in _player_base_kits.keys():
		var pk: Variant = _player_base_kits[pw]
		if pk is Array:
			for aid in (pk as Array):
				if not _abilities.has(String(aid)):
					push_warning("AbilityDB: player base kit '%s' names unknown ability '%s'" % [String(pw), String(aid)])

func has_ability(id: String) -> bool:
	return _abilities.has(id)

## The full ability def (a deep copy — defs are read-only content), {} when unknown.
func ability_for(id: String) -> Dictionary:
	return (_abilities.get(id, {}) as Dictionary).duplicate(true)

## The player-facing name for HUD/log lines; an unknown or unnamed ability degrades to its
## de-snaked id (never an empty string mid-telegraph).
func display_name(id: String) -> String:
	var n := String((_abilities.get(id, {}) as Dictionary).get("name", "")).strip_edges()
	return n if n != "" else id.replace("_", " ")

## The ability ids a combat_form fights with, [] for an unknown form or a shape-malformed kit
## (a String where an Array belongs must degrade to empty, not hard-error mid-fight — review M1 #3).
##
## Sequence kit-growth seam (M5, direction v2 §6): the base kit is APPENDED with whatever arts the
## Progression ladder has unlocked for this form THIS run (Progression.kit_additions). This is the
## single lookup every kit consumer routes through — PlayerCombat's primary-attack pick and the
## ammo/cooldown HUD all call kit_for, so the growth reaches the player's usable arts with no
## per-consumer change. Engine-neutral: AbilityDB owns the base kit (data), Progression owns the
## run's earned additions (data), and this returns their union. Absent Progression (unit contexts)
## degrades to the base kit. Additive + de-duplicated, so the base order is preserved.
func kit_for(form: String) -> Array:
	var out: Array
	if form == "player":
		# M28: the player's base kit is PER-PATHWAY (Progression.pathway() -> _player_base_kits), routed
		# through this same seam so every kit consumer sees the right build with no per-consumer change.
		out = _player_base_kit()
	else:
		var kit: Variant = (_forms.get(form, {}) as Dictionary).get("kit", [])
		out = (kit as Array).duplicate() if kit is Array else []
	var prog := _al("Progression")
	if prog != null:
		for art in prog.kit_additions(form):
			if not out.has(art):
				out.append(art)
	return out

## M28 — the player form's base kit, resolved through the PER-PATHWAY base-kit table. The run's pathway
## (Progression.pathway()) selects the base: a pathway authored in _player_base_kits swaps the kit; any
## pathway NOT in the table (hunter — the slice default) falls back to the "player" form's kit in
## combat_forms.json, UNCHANGED, so the Hunter base kit and the pinned combat_sim/full_run staging stay
## byte-identical. Absent Progression (unit/sim contexts, pathway "") also degrades to the default.
## Engine-neutral: a data table keyed by pathway string, no NPC/id branch.
func _player_base_kit() -> Array:
	var pw := _current_pathway()
	if pw != "" and _player_base_kits.has(pw):
		var k: Variant = _player_base_kits[pw]
		if k is Array:
			return (k as Array).duplicate()
	var base: Variant = (_forms.get("player", {}) as Dictionary).get("kit", [])
	return (base as Array).duplicate() if base is Array else []

## The run's current pathway (via the Progression autoload), "" when Progression is absent (unit/sim
## contexts) — kit_for then falls back to the DEFAULT/Hunter base kit, keeping the sims byte-identical.
func _current_pathway() -> String:
	var prog := _al("Progression")
	return String(prog.pathway()) if prog != null and prog.has_method("pathway") else ""

## Autoload lookup via /root — kit_for reaches the Progression autoload for the M5 growth seam,
## tolerant of it being absent (unit contexts / the doctored-data validate probes).
func _al(autoload_name: String) -> Node:
	var ml := Engine.get_main_loop()
	if ml == null or not (ml is SceneTree):
		return null
	return (ml as SceneTree).root.get_node_or_null(autoload_name)

## The whole form def (kit + default_style + reflex rows), {} when unknown.
func form_def(form: String) -> Dictionary:
	return (_forms.get(form, {}) as Dictionary).duplicate(true)

## True when a combat_form is authored as a MONSTER form — a Beyonder creature, keyed off the
## form's own data flag (`"monster": true` in combat_forms.json), NOT any NPC identity. The Doom
## "monsters left alive" driver (MeterDrivers) counts live agents wearing such a form off this
## generic predicate. Pure read of the loaded data; "" / an unknown form is not a monster.
func is_monster_form(form: String) -> bool:
	return bool((_forms.get(form, {}) as Dictionary).get("monster", false))

## M26 BALANCE RETUNE #2: True when a combat_form is a HIDDEN-Beyonder HUMAN phase — a Beyonder
## walking in a human face (`"hidden_beyonder": true` in combat_forms.json: butcher_human /
## wren_human / mack_harbor), NOT yet transformed and so NOT flagged `monster:true`. The Doom
## "monsters left alive" driver counts these too, so a known prey the player IGNORES (never hunts
## down) keeps costing Doom — the intended pressure. Keyed off the form's own data flag, NEVER an
## NPC identity. Pure read; "" / an unknown form is not a hidden Beyonder.
func is_hidden_beyonder_form(form: String) -> bool:
	return bool((_forms.get(form, {}) as Dictionary).get("hidden_beyonder", false))

func all_ability_ids() -> Array:
	return _abilities.keys()

## Cross-reference check, pure so the suite can probe it with doctored data: every kit entry and
## reflex `do.cast` must name a known ability; every `transform` effect must name a known form;
## every effect kind must be in the resolver's vocabulary. Returns human-readable problem strings
## ([] = clean); _load() warns one line per problem.
func validate_refs(abilities_in: Dictionary, forms_in: Dictionary) -> Array:
	var problems: Array = []
	for id in abilities_in.keys():
		var def: Dictionary = abilities_in[id]
		var effects: Variant = def.get("effects", [])
		if not effects is Array:
			problems.append("ability '%s' effects must be an array" % id)
			continue
		for eff in (effects as Array):
			if typeof(eff) != TYPE_DICTIONARY:
				problems.append("ability '%s' has a non-object effect entry" % id)
				continue
			var kind := String((eff as Dictionary).get("kind", ""))
			if not EFFECT_KINDS.has(kind):
				problems.append("ability '%s' has unknown effect kind '%s'" % [id, kind])
			elif kind == "transform" and not forms_in.has(String((eff as Dictionary).get("form", ""))):
				problems.append("ability '%s' transforms into unknown form '%s'"
					% [id, String((eff as Dictionary).get("form", ""))])
			elif kind == "status":
				# A DIRECT status effect names its status in `status` (zone effects list `statuses`).
				# A name the resolver can't build (a typo like "slwo") would load silently and no-op
				# every tick (review M5 minor #1) — validate it against the resolver's own vocabulary
				# (CombatResolver.STATUS_KINDS: slow/stun/dot/shield/frenzy/silence), which is broader
				# than the zone-only NAMED_STATUS_DEFAULTS and so admits dot/frenzy/shield too.
				var dname := String((eff as Dictionary).get("status", ""))
				if not CombatResolver.STATUS_KINDS.has(dname):
					problems.append("ability '%s' names unknown status '%s'" % [id, dname])
			elif kind == "zone":
				# A zone status without an authored default (CombatResolver.NAMED_STATUS_DEFAULTS)
				# would silently no-op every tick (review M2 #5) — report it at load instead.
				var names: Variant = (eff as Dictionary).get("statuses", [])
				if not names is Array:
					problems.append("ability '%s' zone statuses must be an array" % id)
				else:
					for sname in (names as Array):
						if not CombatResolver.NAMED_STATUS_DEFAULTS.has(String(sname)):
							problems.append("ability '%s' zone names status '%s' with no authored default"
								% [id, String(sname)])
	for form in forms_in.keys():
		var fdef: Dictionary = forms_in[form]
		# Shape guards before every cast (review M1 #3): report the malformed shape as a problem
		# instead of hard-erroring mid-validation and returning [] as if the data were clean.
		var kit: Variant = fdef.get("kit", [])
		if not kit is Array:
			problems.append("form '%s' kit must be an array" % form)
		else:
			for aid in (kit as Array):
				if not abilities_in.has(String(aid)):
					problems.append("form '%s' kit names unknown ability '%s'" % [form, String(aid)])
		var reflexes: Variant = fdef.get("reflexes", [])
		if not reflexes is Array:
			problems.append("form '%s' reflexes must be an array" % form)
		else:
			for r in (reflexes as Array):
				if typeof(r) != TYPE_DICTIONARY:
					problems.append("form '%s' has a non-object reflex row" % form)
					continue
				var doo_v: Variant = (r as Dictionary).get("do", {})
				if not doo_v is Dictionary:
					problems.append("form '%s' reflex 'do' must be an object" % form)
					continue
				var doo: Dictionary = doo_v
				if String(doo.get("kind", "")) == "cast" and not abilities_in.has(String(doo.get("ability", ""))):
					problems.append("form '%s' reflex casts unknown ability '%s'"
						% [form, String(doo.get("ability", ""))])
	return problems
