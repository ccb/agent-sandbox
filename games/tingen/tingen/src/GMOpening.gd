extends Node
## The GM's guaranteed first-ten-minutes opening (autoload `GMOpening`) — direction v2 §3
## "the new-player contract". The doc's promise — "the fun is the hunt" — must be cashed before
## minute five, in play, with ZERO tutorial text. Run one is tuned by this hook.
##
## This node owns NO new engine. It is a thin DIRECTOR that ROUTES the player through the built
## M1-M7 systems in the guaranteed order, using only their public seams:
##
##   0:00  cold open in the lodging (BootController) — Doom-only HUD (Meters disclosure, M4).
##   1:30  the FIRST lead is hot + close: constable_brom hammers on doors — "the butcher's on Iron
##         Cross. Blood under the door." begin_opening() SURFACES the guaranteed butcher lead (M6)
##         promptly (Brom's chatter line rides the LeadSystem npc_said seam) so it reaches the
##         player fast, and STAGES bram_kell at his Iron Cross shop so the lead's where_hint is a
##         real, reachable place (M2 world / Agents).
##   3:00  the butcher fight (the built, live-verified two-phase fight): bram_kell opens in
##         butcher_human and casts assume_form -> bieber_monster at half HP. GMOpening only ensures
##         he is PRESENT and reachable; the fight itself is the combat stack, untouched.
##   5:30  the harvest fork: downing the butcher drops an off-pathway `tainted_characteristic`
##         (Progression, M5); on_butcher_downed() presents the digest/sell/keep fork and SURFACES
##         the same-pathway (hunter) follow-up lead the "he wasn't the only one" hint is backed by.
##   6:30  a WITNESSED opening fight raises Heat (MeterDrivers, M4) and the Heat meter REVEALS —
##         that disclosure is the existing driver's job; GMOpening just guarantees a witness is on
##         the street (the source constable), so the reveal reliably fires.
##   7:00  two follow-up leads in walking range: the same-pathway hunter prey (the first real hunt,
##         M5 progression) + a cult-courier sighting (the cult plot, Doom). Both are LeadSystem
##         leads (M6); the opening ensures both are live by the end of the beat.
##
## Engine-neutral (CLAUDE.md hard rule): the WHOLE opening script is data — data/scenario.json's
## "opening" block names the roles (which lead, which source NPC, which staged Beyonder + where,
## the fork options, the follow-up lead). No constable_brom/bram_kell identity branch lives in this
## code; it stages whatever the scenario publishes. Determinism: the staging is a fixed authored
## position (no RNG); the follow-up lead placement rides LeadSystem's SEEDED slot (never RNG-in-
## combat). Nothing here touches an in-flight fight.
##
## Run-scoped: RunManager.start_run() re-fires the opening every run (guaranteed again, no carry) and
## GMOpening.reset() scrubs the per-run latches — the same reset lesson as M2/M4/M5/M6.

signal opening_began
## The harvest fork was presented at the butcher's downing (digest / sell / keep). Carries the fork.
signal harvest_fork_presented(fork: Dictionary)
## P4: the fork wants a real 3-CHOICE PANEL — fired ONCE per run on the FIRST player characteristic
## pickup (the harvest is literally in hand). Carries the authored fork_ui() copy. The HUD's
## HarvestForkPanel listens live; headless nothing listens (state-only, deterministic).
signal harvest_fork_ui_requested(ui: Dictionary)

const SCENARIO_PATH: String = "res://data/scenario.json"

## The opening script (roles + staging), loaded once from scenario.json. Static: identity data.
static var OPENING: Dictionary = _load_opening()

static func _load_opening() -> Dictionary:
	if not FileAccess.file_exists(SCENARIO_PATH):
		push_error("GMOpening: missing %s" % SCENARIO_PATH)
		return {}
	var parsed: Variant = JSON.parse_string(FileAccess.get_file_as_string(SCENARIO_PATH))
	if typeof(parsed) != TYPE_DICTIONARY:
		push_error("GMOpening: %s is not a JSON object" % SCENARIO_PATH)
		return {}
	return (parsed as Dictionary).get("opening", {})

## The lead-line plan mark separator (choose_harvest appends " · plan: <label>" as pure guidance).
const PLAN_MARK: String = " · plan: "

## Per-run latches (scrubbed by reset()).
var _active: bool = false          # the opening beat is live this run
var _harvest_presented: bool = false   # the harvest fork has been presented at the butcher's kill
var _harvest_choice: String = ""       # the fork option the player took ("" until chosen)
var _source_staged: bool = false       # the door-knock beat staged the source NPC this run (once)
var _door_beat_scheduled: bool = false # the live door-beat timer is armed this run (once)
var _fork_ui_shown: bool = false       # the 3-choice fork panel was requested this run (once)

func _ready() -> void:
	# The opening is guaranteed at the START of every run. RunManager.start_run() re-slots the world
	# (leads, roster, meters) FIRST, then emits run_started — we hook that so the opening stages onto a
	# freshly-reset world. Idempotent connect across world swaps / the headless harness.
	var rm := _al("RunManager")
	if rm != null and not rm.run_started.is_connected(_on_run_started):
		rm.run_started.connect(_on_run_started)
	# M15 review fix: the fork must be PRESENTED live, not only when a harness calls
	# on_butcher_downed(). The published `agent_downed` FACT is the trigger — the exact same bus
	# seam Progression rides for the harvest drop — so a live player who downs the staged opening
	# Beyonder sees the digest/sell/keep words (and the sell_hint that points at real coin) with no
	# choice UI needed. Idempotent connect across world swaps.
	var eb := _al("EventBus")
	if eb != null and not eb.event_logged.is_connected(_on_event):
		eb.event_logged.connect(_on_event)

## The bus triggers this director listens for (both ride the ONE event_logged seam):
##   * `agent_downed` naming the scenario's staged opening Beyonder (DATA — `opening.butcher_npc`,
##     no NPC-id literal here) presents the fork and narrates it. Gated on an ACTIVE opening + the
##     per-run presented latch, so replays/other downings no-op.
##   * `item_picked_up` by the player of ANY `*_characteristic` (the data convention every pathway's
##     harvest follows) requests the 3-choice fork PANEL exactly once per run (P4) — the moment the
##     harvest is literally in hand.
func _on_event(ev: Dictionary) -> void:
	var data: Dictionary = ev.get("data", {}) if ev.get("data") is Dictionary else {}
	match String(ev.get("type", "")):
		"agent_downed":
			if not _active or _harvest_presented:
				return
			var butcher_id := String(OPENING.get("butcher_npc", ""))
			if butcher_id == "" or String(data.get("target", "")) != butcher_id:
				return
			_narrate_fork(on_butcher_downed())
		"item_picked_up":
			_maybe_present_fork_ui(data)

## Surface the presented fork as an internal thought (WorldState.thought_requested — the built M3
## narration seam): the authored options, the "he wasn't the only one" hint, and the sell_hint that
## points the SELL word at Franky's counter (where Shop.sell_harvest pays real coin). Every piece
## of CONTENT is scenario data; only the connective phrasing lives here (engine-neutral).
func _narrate_fork(fork: Dictionary) -> void:
	var ws := _al("WorldState")
	if ws == null:
		return
	var parts: Array = []
	var opts: Array = fork.get("options", []) as Array
	if not opts.is_empty():
		var words: Array = []
		for o in opts:
			words.append(String(o))
		parts.append("Its Characteristic is mine to spend — %s." % " / ".join(words))
	var hint := String(fork.get("hint", ""))
	if hint != "":
		parts.append(hint)
	var sell_hint := String(OPENING.get("sell_hint", ""))
	if sell_hint != "":
		parts.append(sell_hint)
	if parts.is_empty():
		return
	ws.emit_signal("thought_requested", " ".join(parts))

func _on_run_started(_day: int) -> void:
	begin_opening()

# --- the guaranteed opening (§3 0:00 -> 3:00) -------------------------------------------------
## Guarantee run-1's opening onto the freshly-reset world: stage the butcher at his Iron Cross shop
## (reachable from the lead's where_hint) and SURFACE the guaranteed butcher lead promptly (the
## constable hammering on doors reaches the player fast). Called by RunManager on every run start;
## safe to call directly (tests, a determinism restage).
func begin_opening() -> void:
	_active = true
	_harvest_presented = false
	_stage_butcher()
	_surface_butcher_lead_promptly()
	_point_hud_objective_at_opener()
	# P4: the door-knock beat is STAGED IN THE WORLD live — Brom walks to the lodging door, knocks,
	# and speaks his line as a bark at the door (not just the top bar). LIVE-ONLY direction: under
	# --headless nothing is scheduled and nothing moves (test_opener_staging (c) pins it), so every
	# pinned deterministic harness is byte-identical by construction.
	if _is_live():
		_schedule_door_beat()
	opening_began.emit()

## B6 (M20): the top-bar HUD objective (WorldState.current_lead) must NAME the guaranteed butcher
## opener so it matches the board's hot lead — not the stale legacy cult-warehouse string, and not a
## third door-override objective. Composes the objective from the just-slotted butcher lead's own
## data (subject + where_hint), so the copy is DATA (leads.json), never a content literal here.
func _point_hud_objective_at_opener() -> void:
	var ws := _al("WorldState")
	if ws == null:
		return
	var lead := butcher_lead()
	if lead.is_empty():
		return
	var subject := String(lead.get("subject", ""))
	var where := String(lead.get("where_hint", ""))
	if subject == "":
		return
	var text := "%s — %s" % [subject, where] if where != "" else subject
	ws.set_lead(text)

func opening_active() -> bool:
	return _active

## Stage the opening Beyonder (bram_kell) at his authored Iron Cross shop so the lead's where_hint is
## a real, reachable place, in his human phase-1 form, and mark him ACTIVE so he doesn't wander off
## the beat before the player arrives. Pure DATA staging (the scenario names who + where) — no
## combat touched, no RNG. Also registers the shop as a navigable site named for the lead, so the
## where_hint resolves to a move target (the same nav-site seam CitySummoning uses for the cache).
func _stage_butcher() -> void:
	var reg := _al("Agents")
	if reg == null:
		return
	var butcher_id := String(OPENING.get("butcher_npc", ""))
	var kell: Agent = reg.get_agent(butcher_id)
	if kell == null:
		return
	var room := String(OPENING.get("butcher_room", "city"))
	var pos := _shop_pos()
	kell.room = room
	kell.position = pos
	kell.downed = false
	var open_form := String(OPENING.get("butcher_open_form", ""))
	if open_form != "":
		kell.combat_form = open_form
	# Keep him present/reachable (the AgentRuntime activation seam, same one CitySummoning uses).
	var art := _al("AgentRuntime")
	if art != null:
		art.always_active[butcher_id] = true
	# Register the where_hint as a navigable site (the ActionCommit nav-site seam) so the lead's
	# named street resolves to a real move target — reachability made concrete, not just asserted.
	var site := String(OPENING.get("where_site_name", ""))
	if site != "":
		ActionCommit.set_nav_site(site, pos, room)

## The butcher's shop world-position: the scenario's authored `butcher_shop_pos` (his Iron Cross
## shop). A Vector2 from the JSON [x, y].
func _shop_pos() -> Vector2:
	var arr: Variant = OPENING.get("butcher_shop_pos", [])
	if arr is Array and (arr as Array).size() >= 2:
		return Vector2(float((arr as Array)[0]), float((arr as Array)[1]))
	return Vector2.ZERO

## SURFACE the guaranteed butcher lead promptly — Brom hammering on doors, naming the street (§3
## 1:30). Rides the LeadSystem chatter seam (an npc_said fact from the source constable turns into a
## surface, exactly as a live spoken line would), so this is not a special reveal path — it is the
## living-city seam, fired at run start so the tip reaches the player fast.
func _surface_butcher_lead_promptly() -> void:
	var ls := _al("LeadSystem")
	if ls == null:
		return
	var source := String(OPENING.get("source_npc", ""))
	var lead_id := String(OPENING.get("butcher_lead", ""))
	# Direct source-gated surface (fires lead_surfaced -> the board flashes it).
	if source != "":
		ls.surface_from(source)
	# Also publish Brom's spoken line onto the shared bus, so the chatter seam + play-log narrate
	# "the constable let something slip" identically to a live conversation. The line is DATA
	# (scenario `source_line`) — the one piece of opening CONTENT kept out of engine code, so no
	# NPC-content literal lives here (engine-neutrality, CLAUDE.md hard rule).
	var eb := _al("EventBus")
	var source_line := String(OPENING.get("source_line", ""))
	if eb != null and source != "" and source_line != "":
		eb.emit_event("npc_said", {"agent": source, "text": source_line})

# --- P4: the STAGED door-knock beat (the opener happens in the WORLD) ---------------------------
## Stage the scenario's source NPC at the authored lodging-door spot (`source_stage_room` /
## `source_stage_pos`) — the constable physically hammering on the player's door. Generic staging
## verb, pure DATA state (fixed authored position, no RNG, no combat): the same seams _stage_butcher
## uses (Agent.room/position + the AgentRuntime activation latch). ONCE per run (the knock never
## replays); returns {agent, room, position} on the staging call, {} on the no-op repeat/failure.
func stage_source_at_door() -> Dictionary:
	if _source_staged:
		return {}
	var reg := _al("Agents")
	var source := String(OPENING.get("source_npc", ""))
	var room := String(OPENING.get("source_stage_room", ""))
	if reg == null or source == "" or room == "":
		return {}
	var brom: Agent = reg.get_agent(source)
	if brom == null:
		return {}
	_source_staged = true
	var pos := _v2(OPENING.get("source_stage_pos", []))
	brom.room = room
	brom.position = pos
	brom.downed = false
	var art := _al("AgentRuntime")
	if art != null:
		art.always_active[source] = true
	return {"agent": source, "room": room, "position": pos}

## The constable moves on after the beat — back to his authored patrol spot (`source_release_room` /
## `source_release_pos`), the activity latch dropped: he is a real scheduled NPC, not a permanent
## door ornament. The per-run once latch HOLDS (releasing never re-arms the knock).
func release_source() -> void:
	var reg := _al("Agents")
	var source := String(OPENING.get("source_npc", ""))
	if reg == null or source == "":
		return
	var brom: Agent = reg.get_agent(source)
	if brom == null:
		return
	brom.room = String(OPENING.get("source_release_room", "city"))
	brom.position = _v2(OPENING.get("source_release_pos", []))
	var art := _al("AgentRuntime")
	if art != null:
		art.always_active.erase(source)

## Has the door-knock beat staged the source NPC this run? (Per-run latch; headless stays false —
## the determinism guard test_opener_staging (c) pins that.)
func source_staged() -> bool:
	return _source_staged

## Arm the LIVE door-beat timer: `door_beat_delay` seconds after run start (past the IntroCard
## establishing shot) the knock lands. Live-only by construction — begin_opening only calls this
## under a real display. Real-time timer (ignores pause/hit-stop), once per run.
func _schedule_door_beat() -> void:
	if _door_beat_scheduled or _source_staged:
		return
	var ml := Engine.get_main_loop()
	if ml == null or not (ml is SceneTree):
		return
	_door_beat_scheduled = true
	var delay := maxf(0.5, float(OPENING.get("door_beat_delay", 6.0)))
	(ml as SceneTree).create_timer(delay, true, false, true).timeout.connect(_play_door_beat)

## The knock itself: stage the constable at the door, let RoomView give him a body NOW (the player
## is in the lodging at the cold open), fire the door_knock audio event, and speak the authored
## source_line as a BARK bubble on his body. Then he dwells `door_dwell` seconds and moves on.
## Presentation direction only — the lead surfacing already happened at run start (the M6 seam).
func _play_door_beat() -> void:
	if not _is_live() or not _active or _source_staged:
		return
	var staged := stage_source_at_door()
	if staged.is_empty():
		return
	var rv := _al("RoomView")
	if rv != null and rv.has_method("reconcile"):
		rv.reconcile()
	var am := _al("AudioManager")
	if am != null and am.has_method("cue"):
		am.cue("door_knock", {"agent": String(staged.get("agent", ""))})
	_show_door_bark(String(staged.get("agent", "")))
	var ml := Engine.get_main_loop()
	if ml != null and ml is SceneTree:
		var dwell := maxf(2.0, float(OPENING.get("door_dwell", 14.0)))
		(ml as SceneTree).create_timer(dwell, true, false, true).timeout.connect(_end_door_beat)

## Speak the authored line as a bark bubble on the source NPC's spawned body (if the player is in
## the room to see it — otherwise the knock still landed and the top-bar lead already carries it).
func _show_door_bark(agent_id: String) -> void:
	var line := String(OPENING.get("source_line", ""))
	if line == "" or agent_id == "":
		return
	var ml := Engine.get_main_loop()
	if ml == null or not (ml is SceneTree):
		return
	for b in (ml as SceneTree).get_nodes_in_group("npc"):
		if String(b.get("npc_id")) == agent_id and b.has_method("show_bark"):
			b.show_bark(line)
			return

## The beat ends: the constable walks his beat again (release), and the body follows the data on
## the next reconcile.
func _end_door_beat() -> void:
	if not _active:
		return
	release_source()
	var rv := _al("RoomView")
	if rv != null and rv.has_method("reconcile"):
		rv.reconcile()

## [x, y] JSON array -> Vector2 (authored positions). Vector2.ZERO on malformed data.
static func _v2(arr: Variant) -> Vector2:
	if arr is Array and (arr as Array).size() >= 2:
		return Vector2(float((arr as Array)[0]), float((arr as Array)[1]))
	return Vector2.ZERO

# --- reads (the opening's guaranteed facts) ---------------------------------------------------
## The guaranteed hot opener lead (the butcher on Iron Cross), or {} if the board has none.
func butcher_lead() -> Dictionary:
	var ls := _al("LeadSystem")
	if ls == null:
		return {}
	return ls.get_lead(String(OPENING.get("butcher_lead", "")))

## Where the butcher is staged: {agent, room, position} — the reachable target of the lead. Reads the
## live agent so it reflects the actual staging (not just the authored intent).
func butcher_staged_at() -> Dictionary:
	var reg := _al("Agents")
	var butcher_id := String(OPENING.get("butcher_npc", ""))
	var kell: Agent = reg.get_agent(butcher_id) if reg != null else null
	if kell == null:
		return {}
	return {"agent": butcher_id, "room": kell.room, "position": kell.position}

# --- the harvest fork (§3 5:30) ----------------------------------------------------------------
## Present the harvest fork at the butcher's downing: the digest / sell / keep choice (§3), plus the
## "he wasn't the only one" same-pathway hint — BACKED by surfacing the hunter-pathway follow-up
## lead so the hint is a real, followable trail (the first real hunt). Idempotent: presenting again
## returns the same fork without re-surfacing. Returns {options, hint, hunter_lead}.
func on_butcher_downed() -> Dictionary:
	var fork := harvest_fork()
	if not _harvest_presented:
		_harvest_presented = true
		_surface_hunter_follow_up()
		harvest_fork_presented.emit(fork)
	return fork

## The fork options + hint (pure — the authored fork, no state change). Reads scenario data so the
## choices are data, not code.
func harvest_fork() -> Dictionary:
	return {
		"options": (OPENING.get("harvest_fork", []) as Array).duplicate(),
		"hint": String(OPENING.get("harvest_hint", "")),
		"hunter_lead": String(OPENING.get("hunter_follow_up_lead", "")),
	}

func harvest_presented() -> bool:
	return _harvest_presented

# --- P4: the fork as a real 3-CHOICE PANEL ------------------------------------------------------
## The authored panel copy (scenario `opening.fork_ui`): {title, prompt, options: [{id,label,line}]}.
## Pure data read — the engine holds no fork copy; option ids mirror the harvest_fork words.
func fork_ui() -> Dictionary:
	var ui: Variant = OPENING.get("fork_ui", {})
	return (ui as Dictionary).duplicate(true) if ui is Dictionary else {}

## Was the 3-choice panel requested this run? (Per-run once flag — the HintDirector dedup pattern,
## scrubbed by reset().)
func fork_ui_presented() -> bool:
	return _fork_ui_shown

## The panel trigger: the FIRST player pickup of any `*_characteristic` (the data convention every
## pathway's harvest drop follows — no item-id branch) requests the panel EXACTLY ONCE per run.
## Never re-presents once requested OR once the fork is already answered; inert outside an active
## opening. Returns true IFF the panel was requested on THIS call.
func _maybe_present_fork_ui(data: Dictionary) -> bool:
	if not _active or _fork_ui_shown or _harvest_choice != "":
		return false
	if String(data.get("caster", "")) != "player":
		return false
	if not String(data.get("item", "")).ends_with("_characteristic"):
		return false
	var ui := fork_ui()
	if ui.is_empty():
		return false   # nothing authored — do not latch, so it can fire once copy exists
	_fork_ui_shown = true
	harvest_fork_ui_requested.emit(ui)
	return true

## The authored panel label for a fork option id ("" when none is authored). Pure data read.
func _fork_option_label(option: String) -> String:
	for o in (fork_ui().get("options", []) as Array):
		if o is Dictionary and String((o as Dictionary).get("id", "")) == option:
			return String((o as Dictionary).get("label", ""))
	return ""

## Record the player's harvest-fork choice (M15 — the fork's words must lead somewhere real).
## Refuses an option the authored fork doesn't offer. For "sell" the promise is cashed: the
## authored shop hint (scenario `sell_hint`) is surfaced as an internal thought, pointing the
## player at the counter where Shop.sell_harvest() pays REAL coin for the tainted harvest —
## digest stays Progression.advance(), keep is simply carrying it. The choice + hint are DATA
## (no shopkeeper literal in engine code); the latch is per-run (reset() scrubs it).
func choose_harvest(option: String) -> Dictionary:
	var opts: Array = OPENING.get("harvest_fork", []) as Array
	if not opts.has(option):
		return {"ok": false, "reason": "unknown_option"}
	_harvest_choice = option
	var hint := ""
	if option == "sell":
		hint = String(OPENING.get("sell_hint", ""))
		if hint != "":
			var ws := _al("WorldState")
			if ws != null:
				ws.emit_signal("thought_requested", hint)
	# P4: the choice sets GUIDANCE — mark the chosen plan on the HUD lead line (the top-bar
	# objective), replacing any prior plan mark (never stacking). The label is authored panel copy
	# (fork_ui data), falling back to the fork word itself. Deterministic string state, no execution.
	_mark_plan_on_lead(option)
	var eb := _al("EventBus")
	if eb != null:
		eb.emit_event("harvest_fork_chosen", {"choice": option, "hint": hint})
	return {"ok": true, "choice": option, "hint": hint}

## Append (or replace) the " · plan: <label>" guidance mark on WorldState.current_lead.
func _mark_plan_on_lead(option: String) -> void:
	var ws := _al("WorldState")
	if ws == null:
		return
	var label := _fork_option_label(option)
	if label == "":
		label = option
	var base := String(ws.current_lead)
	var cut := base.find(PLAN_MARK)
	if cut != -1:
		base = base.substr(0, cut)
	ws.set_lead(base + PLAN_MARK + label)

## The fork option the player took this run ("" until chosen). Pure read.
func harvest_choice() -> String:
	return _harvest_choice

## Surface the same-pathway (hunter) follow-up lead through the source constable's chatter seam — the
## "he wasn't the only one" hint made concrete. The lead is already slotted (it is guaranteed in
## leads.json); this just SURFACES it so it flashes onto the board at the harvest beat.
func _surface_hunter_follow_up() -> void:
	var ls := _al("LeadSystem")
	if ls == null:
		return
	var hunter_id := String(OPENING.get("hunter_follow_up_lead", ""))
	if hunter_id != "" and not ls.get_lead(hunter_id).is_empty():
		ls.surface(ls.get_lead(hunter_id))

## The live same-pathway (hunter) follow-up lead, or {} if not on the board.
func hunter_pathway_lead() -> Dictionary:
	var ls := _al("LeadSystem")
	if ls == null:
		return {}
	return ls.get_lead(String(OPENING.get("hunter_follow_up_lead", "")))

# --- the follow-up leads (§3 7:00-10:00) -------------------------------------------------------
## The follow-up leads live on the board by the end of the opening beat: every OPEN lead that is not
## the guaranteed butcher opener. By contract this is at least the hunter-pathway prey (the first
## real hunt) and the cult-courier sighting (the cult plot). Reads the live board (M6), so this is
## exactly "what the city is whispering now, minus the one you just fought".
func follow_up_leads() -> Array:
	var ls := _al("LeadSystem")
	if ls == null:
		return []
	var opener := String(OPENING.get("butcher_lead", ""))
	var out: Array = []
	for l in ls.active_leads():
		if String(l.get("id", "")) == opener:
			continue
		out.append(l)
	return out

# --- run lifecycle (§8 — no cross-run carry) ---------------------------------------------------
## Scrub the per-run opening latches — the seam RunManager.reset()/start_run() calls so a fresh run's
## opening is guaranteed AGAIN with no carry. The staging itself is re-applied by begin_opening() on
## the next run_started; reset() only clears the latches so harvest_presented()/opening_active() read
## fresh. (No snapshot: the opening latches are re-derivable and intentionally do NOT ride a nightly
## checkpoint — a mid-run death restores the run, not the tutorial beat, which has long since passed.)
func reset() -> void:
	_active = false
	_harvest_presented = false
	_harvest_choice = ""
	_source_staged = false
	_door_beat_scheduled = false
	_fork_ui_shown = false

# --- helpers -----------------------------------------------------------------------------------
## True only with a real display (live play); false under --headless — where the door beat is NEVER
## scheduled, so every pinned deterministic harness is byte-identical by construction (the
## CombatFeedback._is_live pattern).
func _is_live() -> bool:
	return DisplayServer.get_name() != "headless"

## Autoload lookup via /root (class_name-safe under the headless -s harness).
func _al(autoload_name: String) -> Node:
	var ml := Engine.get_main_loop()
	if ml == null or not (ml is SceneTree):
		return null
	return (ml as SceneTree).root.get_node_or_null(autoload_name)
