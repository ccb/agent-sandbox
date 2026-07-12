extends SceneTree
## M8 — the first-ten-minutes GM opening (direction v2 §3 "the new-player contract").
## Run: godot --headless --path tingen -s tests/test_opening.gd
##
## The GM GUARANTEES run-1's opening: after start_run + landing in the city, the first lead is hot
## and close and reaches the player fast; the butcher fight is reachable from that lead; downing the
## butcher yields the harvest + the fork; a witnessed opening fight reveals the Heat meter; and by the
## end of the opening beat >=2 follow-up leads (one hunter-pathway, one cult) are live. Everything is
## wired through the M1-M7 public seams — GMOpening owns no new engine, only the guaranteed routing.
##
## Covers the DELIVER acceptance (§3 contract):
##  (a) start_run guarantees the butcher lead present + hot + sourced to constable_brom, surfaced fast
##  (b) the butcher (bram_kell) is staged/reachable at the lead's where_hint
##  (c) downing the butcher yields the harvest drop + the fork option + the "same-pathway prey" hint
##  (d) a witnessed opening fight reveals the Heat meter (disclosure state flips)
##  (e) by the end of the opening beat >=2 follow-up leads exist (one hunter-pathway, one cult)
##  (f) the opening state resets on a fresh run (guaranteed again, no carry)
##  (g) determinism: the opening for a fixed run-seed is identical

var _passed: int = 0
var _failed: int = 0

func _init() -> void:
	await process_frame
	await process_frame
	# B3 (retro): NEVER touch the player's REAL persistent profile (user://meta.json) — redirect
	# the meta slot to a test-scoped file before anything drives RunManager (tests/test_meta_isolation.gd).
	root.get_node("/root/RunManager").set("meta_path", "user://meta_test.json")
	root.get_node("/root/RunManager").reload_meta()

	_test_a_butcher_lead_guaranteed_and_surfaced()
	_test_b_butcher_staged_reachable_at_where_hint()
	_test_c_harvest_fork_and_same_pathway_hint()
	_test_d_witnessed_fight_reveals_heat()
	_test_e_two_follow_up_leads_hunter_and_cult()
	_test_f_opening_resets_per_run()
	_test_g_opening_deterministic_for_seed()
	_test_h_source_line_is_data_driven()
	_test_i_reset_scrubs_stale_nav_sites()

	print("\n=== %d passed, %d failed ===" % [_passed, _failed])
	quit(1 if _failed > 0 else 0)

func _ok(cond: bool, label: String) -> void:
	if cond:
		_passed += 1
		print("  PASS  %s" % label)
	else:
		_failed += 1
		printerr("  FAIL  %s" % label)

func _n(name: String) -> Node:
	return root.get_node_or_null("/root/" + name)

# (a) --------------------------------------------------------------------------------------------
func _test_a_butcher_lead_guaranteed_and_surfaced() -> void:
	print("[opening: start_run guarantees the butcher lead present + hot + sourced to constable_brom + surfaced fast]")
	var RM: Object = _n("RunManager")
	var GM: Object = _n("GMOpening")
	var LS: Object = _n("LeadSystem")
	if GM == null:
		_ok(false, "GMOpening autoload exists")
		return
	# Catch the promptly-surfaced lead (Brom hammering on doors) fired during start_run's opening.
	var surfaced := {"id": ""}
	var cb := func(lead_id: String): surfaced["id"] = lead_id
	LS.lead_surfaced.connect(cb)
	RM.start_run()
	LS.lead_surfaced.disconnect(cb)
	var b: Dictionary = GM.butcher_lead()
	_ok(not b.is_empty(), "the opening exposes the guaranteed butcher lead")
	_ok(String(b.get("id", "")) == "butcher_iron_cross", "…and it is butcher_iron_cross")
	_ok(bool(b.get("hot", false)), "the butcher lead is HOT (a hot, close tip)")
	_ok(String(b.get("source", "")) == "constable_brom", "…sourced to constable_brom (the §3 opener)")
	_ok(String(b.get("state", "")) == "open", "…and open (surfaced is not followed)")
	_ok(surfaced["id"] == "butcher_iron_cross",
		"the butcher lead SURFACES promptly during start_run (Brom reaches the player fast)")
	_ok(GM.opening_active(), "the opening beat is active right after start_run")

# (b) --------------------------------------------------------------------------------------------
func _test_b_butcher_staged_reachable_at_where_hint() -> void:
	print("[opening: bram_kell is staged + reachable at the lead's where_hint (his Iron Cross shop)]")
	var RM: Object = _n("RunManager")
	var GM: Object = _n("GMOpening")
	var AG: Object = _n("Agents")
	var AR: Object = _n("AgentRuntime")
	if GM == null:
		return
	RM.start_run()
	var staged: Dictionary = GM.butcher_staged_at()
	_ok(String(staged.get("agent", "")) == "bram_kell", "the staged butcher is bram_kell")
	var kell: Agent = AG.get_agent("bram_kell")
	_ok(kell != null, "bram_kell exists in the roster")
	if kell == null:
		return
	# He is physically placed where the lead points, and marked present so he doesn't wander off.
	_ok(kell.room == String(staged.get("room", "")) and String(staged.get("room", "")) != "",
		"bram_kell is placed in the staged room")
	_ok(kell.position == staged.get("position", Vector2.INF),
		"bram_kell stands at the staged Iron Cross position (his shop)")
	_ok(bool(AR.always_active.get("bram_kell", false)),
		"bram_kell is kept ACTIVE so the fight is reachable from the lead")
	_ok(kell.combat_form == "butcher_human",
		"the butcher opens in human form (phase 1 -> assume_form -> bieber_monster is the built fight)")

# (c) --------------------------------------------------------------------------------------------
func _test_c_harvest_fork_and_same_pathway_hint() -> void:
	print("[opening: downing the butcher yields the harvest drop + the fork + the same-pathway prey hint]")
	var RM: Object = _n("RunManager")
	var GM: Object = _n("GMOpening")
	var AG: Object = _n("Agents")
	var EB: Object = _n("EventBus")
	var RI: Object = _n("RoomItems")
	var LS: Object = _n("LeadSystem")
	if GM == null:
		return
	RM.start_run()
	var kell: Agent = AG.get_agent("bram_kell")
	# Down the butcher: publish the harvest trigger (agent_downed) — Progression drops the
	# Characteristic (off-pathway -> tainted, §3), and GMOpening presents the fork.
	kell.downed = true
	EB.emit_event("agent_downed", {"actor": "player", "target": "bram_kell"})
	# The harvest: a tainted (off-pathway) Characteristic precipitates on the ground where he fell.
	var dropped_tainted: bool = int(RI.count(kell.room, "tainted_characteristic")) > 0
	_ok(dropped_tainted, "the downed butcher drops a tainted (off-pathway) Characteristic — the harvest (§3 5:30)")
	# The fork the GM presents at the harvest: digest / sell / keep (§3 5:30).
	var fork: Dictionary = GM.on_butcher_downed()
	var opts: Array = fork.get("options", [])
	_ok(opts.has("digest") and opts.has("sell") and opts.has("keep"),
		"the harvest fork offers digest / sell / keep: %s" % [opts])
	_ok(String(fork.get("hint", "")).to_lower().find("wasn't the only one") != -1
			or String(fork.get("hint", "")).to_lower().find("same") != -1,
		"the fork carries the 'he wasn't the only one' same-pathway hint")
	# The hint is BACKED by a real lead: the same-pathway (hunter) prey lead is now live on the board.
	var hunter_lead: Dictionary = GM.hunter_pathway_lead()
	_ok(not hunter_lead.is_empty(), "downing the butcher surfaces a same-pathway (hunter) prey lead")
	_ok(String(hunter_lead.get("subject_key", "")) == "hunter"
			or String(hunter_lead.get("pathway", "")) == "hunter",
		"…and that lead is tagged to the player's own (hunter) pathway")
	_ok(not LS.get_lead(String(hunter_lead.get("id", ""))).is_empty(),
		"the same-pathway lead is actually live on the LeadSystem board (wired, not just returned)")

# (d) --------------------------------------------------------------------------------------------
func _test_d_witnessed_fight_reveals_heat() -> void:
	print("[opening: a WITNESSED opening fight reveals the Heat meter (progressive disclosure flips)]")
	var RM: Object = _n("RunManager")
	var GM: Object = _n("GMOpening")
	var AG: Object = _n("Agents")
	var EB: Object = _n("EventBus")
	var Mt: Object = _n("Meters")
	if GM == null:
		return
	RM.start_run()
	# Heat is hidden at run start (§3: HUD shows Doom only; the rest reveal on first trigger).
	_ok(not Mt.is_revealed("heat"), "Heat starts HIDDEN at the opening (progressive disclosure)")
	# Put the player next to the staged butcher and stage a witness who can see the fight.
	var staged: Dictionary = GM.butcher_staged_at()
	var room: String = String(staged.get("room", ""))
	var pos: Vector2 = staged.get("position", Vector2.ZERO)
	AG.ensure_player_proxy(pos, room)
	var kell: Agent = AG.get_agent("bram_kell")
	# A witness on the street (the constable who named it) can perceive the player's public kill.
	var witness: Agent = AG.get_agent("constable_brom")
	witness.room = room
	witness.position = pos
	witness.vision_r = 600.0
	witness.downed = false
	# The player downs the butcher in public view -> MeterDrivers raises Heat -> Heat reveals.
	kell.downed = true
	EB.emit_event("agent_downed", {"actor": "player", "target": "bram_kell"})
	_ok(Mt.get_meter("heat") > 0.0, "a witnessed public kill raised Heat off zero")
	_ok(Mt.is_revealed("heat"), "…and the Heat meter REVEALED (the disclosure state flipped)")

# (e) --------------------------------------------------------------------------------------------
func _test_e_two_follow_up_leads_hunter_and_cult() -> void:
	print("[opening: by the end of the opening beat >=2 follow-up leads (hunter-pathway + cult) are live]")
	var RM: Object = _n("RunManager")
	var GM: Object = _n("GMOpening")
	var AG: Object = _n("Agents")
	var EB: Object = _n("EventBus")
	if GM == null:
		return
	RM.start_run()
	# Play the opening beat through the butcher kill (which seeds the same-pathway follow-up).
	var kell: Agent = AG.get_agent("bram_kell")
	kell.downed = true
	EB.emit_event("agent_downed", {"actor": "player", "target": "bram_kell"})
	GM.on_butcher_downed()
	var follow: Array = GM.follow_up_leads()
	_ok(follow.size() >= 2, "at least TWO follow-up leads are live after the butcher (%d)" % follow.size())
	var has_hunter := false
	var has_cult := false
	for l in follow:
		var pk := String(l.get("subject_key", "")) + "|" + String(l.get("pathway", ""))
		if pk.find("hunter") != -1:
			has_hunter = true
		if String(l.get("subject_key", "")) == "courier" or String(l.get("subject_key", "")).find("cult") != -1:
			has_cult = true
	_ok(has_hunter, "one follow-up smells like the player's own (hunter) pathway's prey (the first real hunt)")
	_ok(has_cult, "one follow-up is a cult-courier sighting (-> the cult plot -> Doom)")
	# Every follow-up lead names a place (walking range, board-renderable).
	var all_placed := true
	for l in follow:
		if String(l.get("where_hint", "")) == "":
			all_placed = false
	_ok(all_placed, "every follow-up lead names a where_hint (in walking range, on the board)")

# (f) --------------------------------------------------------------------------------------------
func _test_f_opening_resets_per_run() -> void:
	print("[opening: the opening state resets on a fresh run (guaranteed again, no carry)]")
	var RM: Object = _n("RunManager")
	var GM: Object = _n("GMOpening")
	var AG: Object = _n("Agents")
	var EB: Object = _n("EventBus")
	if GM == null:
		return
	# Run 1: play the opening forward (down the butcher, present the fork).
	RM.start_run()
	var kell: Agent = AG.get_agent("bram_kell")
	kell.downed = true
	EB.emit_event("agent_downed", {"actor": "player", "target": "bram_kell"})
	GM.on_butcher_downed()
	_ok(GM.harvest_presented(), "run 1: the harvest fork was presented (opening state advanced)")
	# Run 2: a fresh run scrubs the opening — the butcher is up again, the fork not yet presented,
	# the guaranteed lead re-seeded and open.
	RM.start_run()
	_ok(not GM.harvest_presented(), "a fresh run scrubs the harvest-presented latch (no carry)")
	var kell2: Agent = AG.get_agent("bram_kell")
	_ok(not kell2.downed, "a fresh run stands the butcher back up (rebuilt, not downed)")
	_ok(String(GM.butcher_lead().get("state", "")) == "open",
		"a fresh run re-seeds the guaranteed butcher lead, open again (guaranteed every run)")

# (g) --------------------------------------------------------------------------------------------
func _test_g_opening_deterministic_for_seed() -> void:
	print("[opening: the opening for a fixed run-seed is identical]")
	var GM: Object = _n("GMOpening")
	var WM: Object = _n("WorldManager")
	if GM == null:
		return
	var a: Dictionary = _opening_signature(2468)
	var b: Dictionary = _opening_signature(2468)
	_ok(a == b and not a.is_empty(),
		"the same run-seed yields an identical opening signature (determinism): %s" % [a])
	# Genuinely seeded, not hardcoded: two DIFFERENT seeds must place the follow-up leads
	# differently (the butcher opener is a fixed authored spot, but the seeded slots move).
	var s111: Dictionary = _opening_signature(111)
	var s999: Dictionary = _opening_signature(999)
	_ok(s111.get("leads", []) != s999.get("leads", []),
		"different run-seeds yield different follow-up lead placements (seeded, not hardcoded)")

## A stable fingerprint of the opening's seeded placements for a fixed seed: stage the world at
## `seed` (as RunManager does) and read the butcher staging + follow-up lead where_hints.
func _opening_signature(seed: int) -> Dictionary:
	var GM: Object = _n("GMOpening")
	var WM: Object = _n("WorldManager")
	var AG: Object = _n("Agents")
	var LS: Object = _n("LeadSystem")
	# Restage deterministically for this seed (the same seam RunManager.reset uses).
	AG.rebuild()
	WM.seed_value = seed
	LS.reset()
	LS.slot_run(seed)
	GM.reset()
	GM.begin_opening()
	var staged: Dictionary = GM.butcher_staged_at()
	var sig := {
		"butcher_room": String(staged.get("room", "")),
		"butcher_pos": str(staged.get("position", Vector2.ZERO)),
	}
	var wheres: Array = []
	for l in LS.active_leads():
		wheres.append("%s@%s" % [l.get("id", ""), l.get("where_hint", "")])
	wheres.sort()
	sig["leads"] = wheres
	return sig

# (h) --------------------------------------------------------------------------------------------
func _test_h_source_line_is_data_driven() -> void:
	print("[opening: Brom's spoken line is DATA (scenario.json source_line), not a hardcoded engine string]")
	var RM: Object = _n("RunManager")
	var GM: Object = _n("GMOpening")
	var EB: Object = _n("EventBus")
	if GM == null:
		return
	# The line the constable speaks when he surfaces the butcher lead must come from the scenario
	# `opening` block (engine-neutral: no opening CONTENT literal in GMOpening code). Catch the
	# npc_said fact fired during start_run and match it to the authored source_line.
	var said := {"agent": "", "text": ""}
	var cb := func(ev: Dictionary):
		if String(ev.get("type", "")) != "npc_said":
			return
		var data: Dictionary = ev.get("data", {})
		if String(data.get("agent", "")) == "constable_brom":
			said["agent"] = String(data.get("agent", ""))
			said["text"] = String(data.get("text", ""))
	EB.event_logged.connect(cb)
	RM.start_run()
	EB.event_logged.disconnect(cb)
	var authored := String(GM.OPENING.get("source_line", ""))
	_ok(authored != "", "the scenario opening block authors a source_line (the constable's tip is data)")
	_ok(said["text"] == authored and authored != "",
		"the surfaced npc_said line == the authored source_line (data-driven, not a hardcoded literal): %s" % [said["text"]])

# (i) --------------------------------------------------------------------------------------------
func _test_i_reset_scrubs_stale_nav_sites() -> void:
	print("[opening: a fresh run scrubs stale nav-sites — no cross-run nav-site carry]")
	var RM: Object = _n("RunManager")
	var GM: Object = _n("GMOpening")
	if GM == null:
		return
	# Plant a stale nav-site that does NOT belong to this run's opening. A fresh run must clear it
	# (the reset scrubs NAV_SITES) so a prior run's staging can't leak a phantom move target.
	ActionCommit.set_nav_site("stale_ghost_site", Vector2(1, 1), "city")
	_ok(ActionCommit.NAV_SITES.has("stale_ghost_site"), "planted a stale nav-site before the run")
	RM.start_run()
	_ok(not ActionCommit.NAV_SITES.has("stale_ghost_site"),
		"a fresh run scrubbed the stale nav-site (reset clears NAV_SITES, no carry)")
	# …and the opening's OWN nav-site is re-registered after the scrub (restaged on the fresh run).
	var site := String(GM.OPENING.get("where_site_name", ""))
	_ok(site != "" and ActionCommit.NAV_SITES.has(site),
		"the opening re-registers its own where-site after the scrub (%s reachable again)" % site)
