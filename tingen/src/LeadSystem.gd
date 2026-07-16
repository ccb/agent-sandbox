extends Node
## Lead / quest layer (autoload singleton `LeadSystem`) — direction v2 §5 "Rumors -> Leads".
##
## The open world is navigated by TALK, not markers. NPCs surface LEADS through conversation and
## ambient chatter; a lead points at an emergent encounter (a hidden monster, the cult courier, the
## ritual site). Leads are PERISHABLE — left unfollowed past a threshold a lead goes COLD: the
## subject moves/kills again (Doom +5 via Meters, §4), and a fresh lead re-emerges ELSEWHERE. A
## followed lead you fought closes cleanly.
##
## A Lead = { id, subject (what/who), where_hint (a street/place NAME — never a map marker),
##            source (which NPC KNOWS it), state (open|followed|cold|resolved), spawned_day,
##            subject_key (the DATA hook the knowledge gate matches on) }.
##
## The GM SLOTS leads per run (§8.5 dynamic slotting = the roguelite reshuffle): at run start
## RunManager calls slot_run(seed), which seeds each run's leads from data/leads.json via a SEEDED
## RNG — deterministic/replayable, never RNG-in-combat. The guaranteed butcher lead (constable_brom
## -> the butcher on Iron Cross, §3 opener) is always slotted, hot + close.
##
## Engine-neutrality (CLAUDE.md hard rule): the "who knows what" is DATA, not an NPC-id branch. An
## NPC surfaces a lead only when it is the lead's `source`, OR when the lead's `subject_key` appears
## in that NPC's knowledge[] text (npcs.json). No identity branch lives in this engine code.
##
## Run-scoped: RunManager.reset() clears + re-slots leads (the M2/M4/M5 leak lesson), and
## to_dict()/from_dict() ride the snapshot/restore path so a nightly checkpoint carries leads.

signal leads_changed
## A lead just went cold (perished). Carries the cold lead id and the id of the fresh lead that
## re-emerged elsewhere. Observers (toasts, the board) react; the Doom bump is applied here.
signal lead_perished(cold_id: String, fresh_id: String)
## A lead was surfaced to the player (revealed in conversation / overheard). The board can flash it.
signal lead_surfaced(lead_id: String)
## A spoken NPC line surfaced a lead — carries the surfacing NPC + the lead payload, so the play-log
## / a toast can narrate "the city let something slip". Distinct from lead_surfaced (board-facing
## "flash lead X"); this one names WHO said it.
signal lead_from_chatter(npc_id: String, lead: Dictionary)

const LEADS_PATH: String = "res://data/leads.json"

## How many whole days a lead may sit OPEN + unfollowed before it goes cold. TUNING placeholder
## (§5 lifecycle: whisper -> lead -> cold). A followed lead never perishes.
const COLD_AFTER_DAYS: int = 1
## A cold lead's Doom bump (§5: "Doom +5, and the new lead spawns somewhere else"). TUNING.
const COLD_DOOM_BUMP: float = 5.0

## The GM's lead templates (the per-run seed pool). Static: identity data, loaded once.
static var TEMPLATES: Array = _load_templates()

static func _load_templates() -> Array:
	if not FileAccess.file_exists(LEADS_PATH):
		push_error("LeadSystem: missing %s" % LEADS_PATH)
		return []
	var parsed: Variant = JSON.parse_string(FileAccess.get_file_as_string(LEADS_PATH))
	if typeof(parsed) != TYPE_DICTIONARY:
		push_error("LeadSystem: %s is not a JSON object" % LEADS_PATH)
		return []
	return (parsed as Dictionary).get("leads", [])

## Active leads by id -> lead dict. Cold leads are REMOVED (a fresh one takes their place); resolved
## leads are removed. So this dict is exactly "what the city is whispering right now".
var _leads: Dictionary = {}
## Monotonic per-run counter so a re-emerged lead gets a unique id (butcher_iron_cross_2, ...).
var _respawn_seq: int = 0
## M25 (backlog "M18"): monotonic per-run counter for occult-DISCOVERED leads (occult_lead_1, ...), so
## a divination/sight reading slotted via surface_occult() gets a unique, stable id. Scrubbed on
## slot_run/reset like _respawn_seq; ridden through to_dict/from_dict so a checkpoint keeps ids stable.
var _occult_seq: int = 0
var _rng := RandomNumberGenerator.new()
var _seed: int = 0

func _ready() -> void:
	# Leads come from PEOPLE (§5): a spoken NPC line fires `npc_said` on the shared bus, and we listen
	# there — ONE seam. Today the ONLY emitter is the converse route (DialogueManager); the ambient /
	# Stimulus beat does not yet emit `npc_said` (Stimulus writes neutral perception FACTS, not
	# speech), so overheard-chatter leads ride the same seam the moment any ambient beat starts
	# speaking on it — no LeadSystem change needed. We surface any OPEN lead the speaker would
	# plausibly KNOW. The gate is pure DATA (npc_knows -> source field + npcs.json knowledge), so no
	# NPC-identity branch lives here and the converse SECRECY gate upstream is entirely untouched — a
	# lead reveal is just the board catching what the living city let slip.
	var eb := _al("EventBus")
	if eb != null and not eb.event_logged.is_connected(_on_event):
		eb.event_logged.connect(_on_event)
	# M14 post-advance gate: leads tagged after_advance:true are slotted at run start but surface only
	# AFTER the player's first advance (Progression.advanced -> surface_after_advance). Engine-neutral:
	# the gate key is a DATA field on the lead template; no lead id or npc id lives in this code.
	var prog := _al("Progression")
	if prog != null and not prog.advanced.is_connected(_on_progression_advanced):
		prog.advanced.connect(_on_progression_advanced)

## M14 post-advance hook: unhide every lead gated behind after_advance when the player advances
## for the first time. Flips state "hidden" -> "open" and re-stamps spawned_day (Finding 4: the
## doom clock must not penalise a lead the player could not yet see — the clock starts only once
## the gate opens). Fires lead_surfaced so the board flashes it. Engine-neutral — keyed off the
## data field, no lead id or npc id in this code; any future after_advance lead rides this for free.
func _on_progression_advanced(_pathway: String, _sequence: int) -> void:
	var day := _current_day()
	for id in _leads.keys():
		var lead: Dictionary = _leads[id]
		if String(lead.get("state", "")) == "hidden" and bool(lead.get("after_advance", false)):
			lead["state"] = "open"
			lead["spawned_day"] = day  # doom clock starts NOW, not at run start
			_mark_known(id)            # the city just told the player — the prey is now KNOWN (M26 RETUNE #2)
			lead_surfaced.emit(id)
	leads_changed.emit()

func _on_event(ev: Dictionary) -> void:
	if String(ev.get("type", "")) != "npc_said":
		return
	var data: Dictionary = ev.get("data", {}) if ev.get("data") is Dictionary else {}
	var npc_id := String(data.get("agent", ""))
	if npc_id == "":
		return
	var lead: Dictionary = surface_from(npc_id)
	if not lead.is_empty():
		lead_from_chatter.emit(npc_id, lead)

# --- GM slotting (the per-run reshuffle) -------------------------------------------------------
## Seed this run's leads from the templates, deterministically for `seed`. Clears any prior leads
## first (idempotent — safe to call again with a new seed). Guaranteed leads are always slotted; the
## rest resolve a where_hint from their weighted candidate pool via the seeded RNG (the variety).
func slot_run(seed: int) -> void:
	_seed = seed
	_rng.seed = seed
	_leads.clear()
	_respawn_seq = 0
	_occult_seq = 0
	var day: int = _current_day()
	var run_pathway := _run_pathway()
	for tmpl in TEMPLATES:
		# M30 bug#3: a PATHWAY-TAGGED prey lead only slots in a run of that pathway. A hermit_prey_*
		# lead (pathway:hermit) must never surface in a Hunter run — downing it drops a
		# hermit_characteristic a Hunter can neither digest nor sell (dead weight, the playtest bug) —
		# and vice-versa. Engine-neutral: keyed purely on the lead's DATA `pathway` tag vs the run's
		# Progression.pathway(); an untagged lead (butcher opener / courier / rite site) is pathway-
		# neutral and always slots. This is also what GUARANTEES >=2 same-pathway prey in a Hermit run
		# (neil + finch both slot), matching the Hunter staging.
		var tmpl_pathway := String(tmpl.get("pathway", ""))
		if tmpl_pathway != "" and tmpl_pathway != run_pathway:
			continue
		var lead := _instantiate(tmpl, day)
		_leads[lead["id"]] = lead
	leads_changed.emit()

## The current run's pathway (Progression.pathway()), defaulting to the shipped Hunter build when
## Progression is absent (unit contexts). Read by slot_run for the pathway gate (bug#3). Pure.
func _run_pathway() -> String:
	var prog := _al("Progression")
	if prog != null and prog.has_method("pathway"):
		return String(prog.pathway())
	return "hunter"

## Scrub every lead (RunManager.reset path — the leak fix). Re-slotting happens via slot_run().
func reset() -> void:
	_leads.clear()
	_respawn_seq = 0
	_occult_seq = 0
	leads_changed.emit()

## Build a live lead from a template, resolving its where_hint (a fixed hint, or a seeded pick from
## the weighted candidates). State starts OPEN, except for leads tagged after_advance:true which
## start HIDDEN — invisible to the board and immune to the perish clock until _on_progression_advanced
## flips them to open (Finding 3/4 fix: the gate was a no-op because active_leads/surface_from saw all
## leads regardless; hidden state is the enforcement mechanism).
func _instantiate(tmpl: Dictionary, day: int) -> Dictionary:
	var where := String(tmpl.get("where_hint", ""))
	# P5 — the authored MAP PIN: map-image-space [x, y] the district map marks for this lead. A
	# candidate-pool lead carries the PICKED candidate's own pin so hint and pin can never drift
	# apart. [] = no pin (occult readings, cold respawns — the trail is a name, not a spot).
	var map_pos: Array = (tmpl.get("map_pos", []) as Array).duplicate()
	if where == "" and tmpl.get("where_candidates") is Array:
		var cand: Dictionary = _weighted_pick(tmpl["where_candidates"])
		where = String(cand.get("value", ""))
		map_pos = (cand.get("map_pos", []) as Array).duplicate()
	var after_adv := bool(tmpl.get("after_advance", false))
	return {
		"id": String(tmpl.get("id", "")),
		"subject": String(tmpl.get("subject", "")),
		"subject_key": String(tmpl.get("subject_key", "")),
		"source": String(tmpl.get("source", "")),
		"where_hint": where,
		"hot": bool(tmpl.get("hot", false)),
		# The player-pathway tag (M8 §3): a same-pathway prey lead carries `pathway` so the GM opening
		# can find the "smells like your own pathway" follow-up without an id branch. "" = untagged.
		"pathway": String(tmpl.get("pathway", "")),
		# A follow-up lead surfaces AFTER the opening butcher (§3 7:00), not shouted at run start.
		"follow_up": bool(tmpl.get("follow_up", false)),
		# M14 post-advance gate: a lead tagged after_advance:true starts HIDDEN (not shown on the board,
		# not surfaceable via npc_said, not subject to the perish clock) until Progression.advanced fires.
		# Engine-neutral: keyed off the data field; any future after_advance lead rides this for free.
		"after_advance": after_adv,
		# "hidden" = slotted but not yet player-visible (after_advance gate is shut).
		# "open"   = visible on the board, surfaceable, subject to perish clock.
		# "followed"/"resolved" = normal lifecycle states.
		"state": "hidden" if after_adv else "open",
		"spawned_day": day,
		# P5: the district-map pin spot (map-image px), resolved above. Pure DATA — the map draws
		# a marker at the CURRENT lead's map_pos; no NPC-id lookup anywhere.
		"map_pos": map_pos,
		# M26 RETUNE #2 fix: the hidden-Beyonder combat_form this lead points at ("" for non-prey leads
		# like the courier/rite). The Doom "monsters left alive" driver counts a live hidden Beyonder
		# wearing this form ONLY once `known` flips true (the city surfaced the lead), so an idle player is
		# never taxed for prey they were never told about. Data linkage form<->lead, no NPC-id branch.
		"prey_form": String(tmpl.get("prey_form", "")),
		# Has the city SURFACED this lead to the player yet? Set true the moment it is revealed
		# (surface_from / the after_advance flip / an explicit surface). A slotted-but-unspoken lead is
		# NOT known — the player cannot be expected to hunt prey nobody has named.
		"known": false,
		"respawn_where": (tmpl.get("respawn_where", []) as Array).duplicate(),
	}

## Pick a whole candidate row (P5: the caller needs the candidate's `value` AND its `map_pos`,
## so hint and pin always come from the SAME row). RNG consumption unchanged — one randf per
## pick, so per-seed slotting stays byte-identical to the pre-P5 behavior.
func _weighted_pick(candidates: Array) -> Dictionary:
	var total: float = 0.0
	for c in candidates:
		total += float(c["weight"])
	var roll: float = _rng.randf() * total
	for c in candidates:
		roll -= float(c["weight"])
		if roll <= 0.0:
			return c
	return candidates[-1] if not candidates.is_empty() else {}

# --- reads ------------------------------------------------------------------------------------
## Every lead currently on the board (open / followed) — what the board renders. Excludes leads in
## the "hidden" state (gated by after_advance, not yet player-visible). Order is stable (insertion
## order of the backing dict), so the board and a signature test are deterministic.
func active_leads() -> Array:
	var out: Array = []
	for id in _leads.keys():
		var lead: Dictionary = _leads[id]
		if String(lead.get("state", "")) != "hidden":
			out.append(lead.duplicate(true))
	return out

## P5 — the CURRENT lead (the one the district map pins): the first FOLLOWED lead (the player's
## commitment wins), else the first HOT open lead (the opener), else the first open lead, else {}.
## Backing-dict insertion order is stable, so the pick is deterministic. Hidden leads (the
## after_advance gate still shut) are never current — the player cannot chase what the city has
## not named. Returns a defensive copy.
func current_lead() -> Dictionary:
	var first_open: Dictionary = {}
	var first_hot: Dictionary = {}
	for id in _leads.keys():
		var lead: Dictionary = _leads[id]
		match String(lead.get("state", "")):
			"followed":
				return lead.duplicate(true)
			"open":
				if first_open.is_empty():
					first_open = lead
				if first_hot.is_empty() and bool(lead.get("hot", false)):
					first_hot = lead
	var pick: Dictionary = first_hot if not first_hot.is_empty() else first_open
	return pick.duplicate(true) if not pick.is_empty() else {}

## A single lead by id (a defensive copy), or {} when it is not active (never slotted, resolved, or
## gone cold).
func get_lead(lead_id: String) -> Dictionary:
	if not _leads.has(lead_id):
		return {}
	return (_leads[lead_id] as Dictionary).duplicate(true)

## M26 RETUNE #2 fix — the set of hidden-Beyonder combat_forms the player has been TOLD about (a
## {form: true} lookup). The Doom "monsters left alive" driver (MeterDrivers._live_monster_count)
## consults this so a live hidden Beyonder costs Doom ONLY once its lead is KNOWN (surfaced): an idle
## player who has engaged nothing is never taxed for prey they were never named, but ignoring KNOWN
## prey keeps hastening the descent (the intended §4 pressure). A resolved lead is erased (its prey was
## put down), so it drops out automatically. Engine-neutral: matches on the lead's DATA `prey_form`,
## never an NPC id. A hidden lead (after_advance gate shut) is never known, so it is excluded.
func known_prey_forms() -> Dictionary:
	var forms: Dictionary = {}
	for id in _leads.keys():
		var lead: Dictionary = _leads[id]
		# A hidden lead (after_advance gate still shut) is never player-visible, so it can never be
		# "known" — defensive guard so a form can't leak in before the city has actually named it.
		if String(lead.get("state", "")) == "hidden":
			continue
		if not bool(lead.get("known", false)):
			continue
		var form := String(lead.get("prey_form", ""))
		if form != "":
			forms[form] = true
	return forms

## Latch a lead KNOWN (the city surfaced it to the player). Idempotent; a no-op for an unknown id.
func _mark_known(lead_id: String) -> void:
	if _leads.has(lead_id):
		(_leads[lead_id] as Dictionary)["known"] = true

## TEST/DEBUG seam (retro B4) — force every slotted lead's KNOWN flag at once. The intention-revealing
## way for pacing harnesses to stage the two known-gate extremes WITHOUT reaching into `_leads`:
##   false -> a truly UN-SURFACED idle run (the city has named nothing; the Doom monster driver skips
##            every live hidden Beyonder — isolates the pure passive time+phase pacer);
##   true  -> the worst case (the player was told about EVERY prey and hunted none); a hidden
##            after_advance lead is opened too, because a surfaced lead is player-visible by definition
##            (known_prey_forms() excludes hidden leads).
## Engine-neutral: flips the DATA flag on every lead — no NPC/lead-id branch. Not used by gameplay.
func debug_set_all_known(v: bool) -> void:
	for id in _leads.keys():
		var lead: Dictionary = _leads[id]
		lead["known"] = v
		if v and String(lead.get("state", "")) == "hidden":
			lead["state"] = "open"

# --- source-gated reveal (leads come from PEOPLE) ---------------------------------------------
## Would this NPC plausibly KNOW this lead? DATA-gated (engine-neutral): true when the NPC is the
## lead's authored `source`, OR the lead's `subject_key` appears in the NPC's knowledge[] text
## (npcs.json). No NPC-id branch — a new source is just a data edit.
func npc_knows(npc_id: String, lead: Dictionary) -> bool:
	if lead.is_empty():
		return false
	if String(lead.get("source", "")) == npc_id:
		return true
	var key := String(lead.get("subject_key", "")).to_lower()
	if key == "":
		return false
	var db := _al("NpcDB")
	if db == null:
		return false
	for k in (db.get_def(npc_id).get("knowledge", []) as Array):
		if String(k).to_lower().find(key) != -1:
			return true
	return false

## The lead this NPC would surface right now (the freshest OPEN lead they know), or {} if none.
## Marks it surfaced (fires lead_surfaced) — the board can flash it. A revealed lead stays OPEN
## until the player FOLLOWS it; surfacing is not following (silence-is-information still holds).
## Hidden leads (after_advance gate not yet open) are never surfaced here — the gate must fire first.
func surface_from(npc_id: String) -> Dictionary:
	for id in _leads.keys():
		var lead: Dictionary = _leads[id]
		var state := String(lead.get("state", ""))
		if state != "open":   # "hidden", "followed", "resolved" are all skipped
			continue
		if npc_knows(npc_id, lead):
			_mark_known(id)   # the city just named this prey — it is now KNOWN (M26 RETUNE #2)
			lead_surfaced.emit(id)
			return lead.duplicate(true)
	return {}

## M25 (backlog "M18"): slot an OCCULT-DISCOVERED lead — the directional impression an occult tool
## (divination / residue sight / gray fog / dream fragments) surfaces when the player USES it. Occult
## tools used to dump their hint into WorldState.set_lead (the dead single-objective string); a
## reading is now a first-class LEAD on the board, participating in the normal open->cold lifecycle.
## Returns the new lead's id. Engine-neutral: no tool-id branch — `source` is passed data, the text is
## the tool's own output. `mislead` tags a reading the fog twisted (a false lead the city let slip) so
## downstream (M22) can style it. State starts OPEN (subject to the perish clock like any tip).
func surface_occult(text: String, source: String, mislead: bool = false) -> String:
	if text == "":
		return ""
	_occult_seq += 1
	var id := "occult_lead_%d" % _occult_seq
	var lead: Dictionary = {
		"id": id,
		"subject": text,           # the directional impression IS the lead's subject line
		"subject_key": "",
		"source": source,          # the tool id that surfaced it (data, not a branch)
		"where_hint": "",          # occult readings point a direction, not a named street
		"hot": false,
		"pathway": "",
		"follow_up": false,
		"after_advance": false,
		"occult": true,            # provenance flag: this lead came from a costed occult reading
		"mislead": mislead,        # the fog twisted it (a false lead) — M22 can style this
		"prey_form": "",           # occult readings point a direction, not a specific Beyonder form
		"known": true,             # a used occult reading IS surfaced (the player just read it)
		"state": "open",
		"spawned_day": _current_day(),
		"map_pos": [],             # a direction, never a map pin (P5)
		"respawn_where": [],
	}
	_leads[id] = lead
	lead_surfaced.emit(id)
	leads_changed.emit()
	return id

## Explicit surface of a known lead (the `surface(lead)` verb from the spec). Fires the signal.
func surface(lead: Dictionary) -> void:
	var id := String(lead.get("id", ""))
	if _leads.has(id):
		_mark_known(id)   # an explicit surface is the city naming the prey — mark it KNOWN (M26 RETUNE #2)
		lead_surfaced.emit(id)

# --- lifecycle: follow / resolve --------------------------------------------------------------
## The player commits to a lead (heads for its where_hint). A followed lead no longer perishes.
func follow(lead_id: String) -> void:
	if not _leads.has(lead_id):
		return
	(_leads[lead_id] as Dictionary)["state"] = "followed"
	leads_changed.emit()

## The player fought the encounter — the lead closes cleanly (leaves the board, no Doom cost).
func resolve(lead_id: String) -> void:
	if not _leads.has(lead_id):
		return
	_leads.erase(lead_id)
	leads_changed.emit()

# --- perish (the pull that keeps the city boiling) --------------------------------------------
## Advance the perish clock to `current_day`. Any OPEN, unfollowed lead older than COLD_AFTER_DAYS
## goes COLD: it is removed, Doom bumps +5 (Meters, §4), and a FRESH lead re-emerges elsewhere with
## a new where_hint (the subject moved). Followed/resolved/hidden leads are untouched. Deterministic —
## the fresh where_hint is picked from the cold lead's respawn_where via the seeded RNG.
## Hidden leads (after_advance gate not yet fired) are explicitly exempt: the player could not act on
## them, so they must not incur Doom. Their spawned_day is re-stamped when the gate opens (Finding 4).
func perish_tick(current_day: int) -> void:
	var went_cold: Array = []
	for id in _leads.keys():
		var lead: Dictionary = _leads[id]
		if String(lead.get("state", "")) != "open":
			continue  # hidden, followed, and resolved are all exempt
		if current_day - int(lead.get("spawned_day", current_day)) > COLD_AFTER_DAYS:
			went_cold.append(id)
	for id in went_cold:
		_go_cold(id, current_day)

## One lead going cold: bump Doom, remove it, spawn a fresh one elsewhere, announce it.
func _go_cold(cold_id: String, current_day: int) -> void:
	var cold: Dictionary = _leads[cold_id]
	# Doom +5 — a cold lead means the monster moved/killed again (§5). Through the M4 Meters API.
	var mt := _al("Meters")
	if mt != null:
		mt.adjust("doom", COLD_DOOM_BUMP, "lead_went_cold")
	_leads.erase(cold_id)
	# The trail re-emerges ELSEWHERE, worse: a fresh lead, same subject/source, new where_hint.
	_respawn_seq += 1
	var fresh_id := "%s_%d" % [_strip_respawn_suffix(cold_id), _respawn_seq + 1]
	var where := _pick_respawn_where(cold, String(cold.get("where_hint", "")))
	var fresh: Dictionary = {
		"id": fresh_id,
		"subject": String(cold.get("subject", "")),
		"subject_key": String(cold.get("subject_key", "")),
		"source": String(cold.get("source", "")),
		"where_hint": where,
		"hot": false,   # a re-emerged trail is a cold restart, not a hot tip
		"pathway": String(cold.get("pathway", "")),
		"follow_up": bool(cold.get("follow_up", false)),
		"after_advance": bool(cold.get("after_advance", false)),
		# The subject is the SAME Beyonder that moved; carry its prey_form and its known-status forward,
		# so a prey the player already learned of and let slip keeps costing Doom at its new hiding spot.
		"prey_form": String(cold.get("prey_form", "")),
		"known": bool(cold.get("known", false)),
		"state": "open",
		"spawned_day": current_day,
		# P5: the subject MOVED — the fresh trail is a NAME, not a spot; the map pin is dropped
		# until the city can place it again (respawn_where hints have no authored coordinates).
		"map_pos": [],
		"respawn_where": (cold.get("respawn_where", []) as Array).duplicate(),
	}
	_leads[fresh_id] = fresh
	lead_perished.emit(cold_id, fresh_id)
	leads_changed.emit()

## Pick a NEW where_hint for a re-emerged lead: prefer the template's respawn_where pool (seeded,
## avoiding the old spot), else fall back to a decorated old hint so it is never blank/identical.
func _pick_respawn_where(cold: Dictionary, old_where: String) -> String:
	var pool: Array = (cold.get("respawn_where", []) as Array).filter(func(w): return String(w) != old_where)
	if not pool.is_empty():
		return String(pool[_rng.randi() % pool.size()])
	return "%s (moved)" % old_where if old_where != "" else "somewhere new"

## Strip a prior "_N" respawn suffix so successive cold cycles keep a clean base id.
func _strip_respawn_suffix(id: String) -> String:
	var parts := id.rsplit("_", true, 1)
	if parts.size() == 2 and parts[1].is_valid_int():
		return String(parts[0])
	return id

# --- save / load (run-scoped; snapshot rides RunManager's checkpoint) -------------------------
func to_dict() -> Dictionary:
	return {
		"leads": _leads.duplicate(true),
		"respawn_seq": _respawn_seq,
		"occult_seq": _occult_seq,
		"seed": _seed,
	}

func from_dict(d: Dictionary) -> void:
	_leads = (d.get("leads", {}) as Dictionary).duplicate(true)
	_respawn_seq = int(d.get("respawn_seq", 0))
	_occult_seq = int(d.get("occult_seq", 0))
	_seed = int(d.get("seed", 0))
	_rng.seed = _seed
	leads_changed.emit()

# --- helpers ----------------------------------------------------------------------------------
func _current_day() -> int:
	var rm := _al("RunManager")
	if rm != null and rm.has_method("current_day"):
		return int(rm.current_day())
	var clk := _al("Clock")
	return int(clk.day) if clk != null else 1

## Autoload lookup via /root (class_name-safe under the headless -s harness).
func _al(autoload_name: String) -> Node:
	var ml := Engine.get_main_loop()
	if ml == null or not (ml is SceneTree):
		return null
	return (ml as SceneTree).root.get_node_or_null(autoload_name)
