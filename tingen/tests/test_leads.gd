extends SceneTree
## M6 — Rumors -> Leads (direction v2 §5). Standalone headless harness for the lead/quest layer.
## Run: godot --headless --path tingen -s tests/test_leads.gd
##
## Covers the DELIVER acceptance:
##  (a) run start slots leads incl. the guaranteed butcher lead from constable_brom
##  (b) an NPC surfaces a lead they'd plausibly know; a source who wouldn't know does NOT
##  (c) an unfollowed lead goes cold past the threshold -> Doom+5 -> a NEW lead spawns elsewhere
##  (d) follow+resolve closes a lead
##  (e) leads reset per run (no carry) + snapshot/restore within a run
##  (f) the board reads active leads
##  (g) determinism: lead slotting for a fixed run-seed is identical across runs

var _passed: int = 0
var _failed: int = 0

func _init() -> void:
	await process_frame
	await process_frame
	# B3 (retro): NEVER touch the player's REAL persistent profile (user://meta.json) — redirect
	# the meta slot to a test-scoped file before anything drives RunManager (tests/test_meta_isolation.gd).
	root.get_node("/root/RunManager").set("meta_path", "user://meta_test.json")
	root.get_node("/root/RunManager").reload_meta()

	_test_run_start_slots_guaranteed_butcher()
	_test_source_gated_surface()
	_test_perish_cold_respawn_doom()
	_test_follow_resolve_closes()
	_test_reset_and_snapshot_restore()
	_test_board_reads_active_leads()
	_test_determinism_fixed_seed()

	print("\n=== %d passed, %d failed ===" % [_passed, _failed])
	quit(1 if _failed > 0 else 0)

func _ok(cond: bool, label: String) -> void:
	if cond:
		_passed += 1
		print("  PASS  %s" % label)
	else:
		_failed += 1
		printerr("  FAIL  %s" % label)

func _ls() -> Node:
	return root.get_node_or_null("/root/LeadSystem")

func _test_run_start_slots_guaranteed_butcher() -> void:
	print("[leads: run start slots the guaranteed butcher lead from constable_brom]")
	var RM: Object = root.get_node("/root/RunManager")
	var LS: Object = _ls()
	if LS == null:
		_ok(false, "LeadSystem autoload exists")
		return
	RM.start_run()
	var butcher: Dictionary = LS.get_lead("butcher_iron_cross")
	_ok(not butcher.is_empty(), "the butcher lead is slotted at run start")
	_ok(String(butcher.get("source", "")) == "constable_brom",
		"the butcher lead's source is constable_brom (the §3 opener)")
	_ok(String(butcher.get("where_hint", "")) == "Iron Cross Street",
		"the butcher lead names Iron Cross Street as its where_hint (hot + close)")
	_ok(String(butcher.get("state", "")) == "open", "a freshly slotted lead is open")
	_ok(LS.active_leads().size() >= 1, "run start seeds at least the guaranteed lead")

func _test_source_gated_surface() -> void:
	print("[leads: an NPC surfaces a lead they'd know; a source who wouldn't does not]")
	var RM: Object = root.get_node("/root/RunManager")
	var LS: Object = _ls()
	if LS == null:
		return
	RM.start_run()
	# constable_brom is the butcher lead's source -> he surfaces it.
	var revealed: Dictionary = LS.surface_from("constable_brom")
	_ok(String(revealed.get("id", "")) == "butcher_iron_cross",
		"constable_brom (the source) surfaces the butcher lead")
	# An NPC who is not the source and whose knowledge doesn't cover it does NOT surface it.
	_ok(not LS.npc_knows("old_neil", LS.get_lead("butcher_iron_cross")),
		"old_neil (alchemist, no beat knowledge) would NOT know the butcher lead")
	_ok(LS.npc_knows("constable_brom", LS.get_lead("butcher_iron_cross")),
		"constable_brom (source) would know the butcher lead")
	# The multi-source knowledge branch is LIVE (M6 review finding 4a): a non-source NPC whose
	# npcs.json knowledge names the subject ALSO surfaces the lead, and a non-source non-knower is
	# rejected against that SAME lead — so the gate is proven to both accept and reject on real data,
	# not pass trivially against an empty knowledge set.
	_ok(LS.npc_knows("maribel_hatch", LS.get_lead("butcher_iron_cross")),
		"maribel_hatch (non-source) knows the butcher lead via knowledge (multi-source gate accepts)")
	_ok(String(LS.surface_from("maribel_hatch").get("id", "")) == "butcher_iron_cross",
		"the non-source knower actually surfaces the lead through the knowledge branch")
	# Integration: a spoken NPC line (npc_said on the shared bus) surfaces the lead the speaker knows.
	# The converse route fires npc_said today; an ambient beat would ride the identical seam. This is
	# how leads come through TALK.
	var EB: Object = root.get_node("/root/EventBus")
	var seen := {"npc": "", "lead": ""}
	var cb := func(npc_id: String, lead: Dictionary):
		seen["npc"] = npc_id
		seen["lead"] = String(lead.get("id", ""))
	LS.lead_from_chatter.connect(cb)
	EB.emit_event("npc_said", {"agent": "constable_brom", "text": "the butcher's on Iron Cross."})
	LS.lead_from_chatter.disconnect(cb)
	_ok(seen["npc"] == "constable_brom" and seen["lead"] == "butcher_iron_cross",
		"a spoken line from the source surfaces the lead through the chatter seam")
	# A speaker who wouldn't know surfaces nothing through the same seam.
	var seen2 := {"hit": false}
	var cb2 := func(_n: String, _l: Dictionary): seen2["hit"] = true
	LS.lead_from_chatter.connect(cb2)
	EB.emit_event("npc_said", {"agent": "old_neil", "text": "Celeste..."})
	LS.lead_from_chatter.disconnect(cb2)
	_ok(not seen2["hit"], "a speaker who wouldn't know surfaces no lead (source-gated)")

func _test_perish_cold_respawn_doom() -> void:
	print("[leads: an unfollowed lead goes cold past the threshold -> Doom+5 -> a NEW lead spawns elsewhere]")
	var RM: Object = root.get_node("/root/RunManager")
	var Mt: Object = root.get_node("/root/Meters")
	var LS: Object = _ls()
	if LS == null:
		return
	RM.start_run()
	var before_doom: float = Mt.get_meter("doom")
	var before_count: int = LS.active_leads().size()
	var butcher: Dictionary = LS.get_lead("butcher_iron_cross")
	var old_where: String = String(butcher.get("where_hint", ""))
	var spawned_day: int = int(butcher.get("spawned_day", 1))
	# Perish tick a full threshold past its spawn day: the butcher lead (left OPEN/unfollowed) goes cold.
	LS.perish_tick(spawned_day + LS.COLD_AFTER_DAYS + 1)
	_ok(LS.get_lead("butcher_iron_cross").is_empty(),
		"the cold lead is removed from the active board (the subject moved)")
	_ok(Mt.get_meter("doom") >= before_doom + 5.0,
		"a cold lead bumps Doom +5 (the city boils over where you weren't watching)")
	# A NEW lead spawned elsewhere with a fresh where_hint.
	var respawn: Dictionary = LS.get_lead("butcher_iron_cross_2")
	_ok(not respawn.is_empty(), "a fresh lead re-emerges after the trail goes cold")
	_ok(String(respawn.get("where_hint", "")) != old_where and String(respawn.get("where_hint", "")) != "",
		"the re-emerged lead points somewhere new")
	_ok(LS.active_leads().size() == before_count,
		"the board count holds (one cold removed, one fresh spawned)")

func _test_follow_resolve_closes() -> void:
	print("[leads: follow + resolve closes a lead cleanly]")
	var RM: Object = root.get_node("/root/RunManager")
	var Mt: Object = root.get_node("/root/Meters")
	var LS: Object = _ls()
	if LS == null:
		return
	RM.start_run()
	LS.follow("butcher_iron_cross")
	_ok(String(LS.get_lead("butcher_iron_cross").get("state", "")) == "followed",
		"following a lead marks it followed")
	# A followed lead does NOT go cold on the perish tick.
	var b: Dictionary = LS.get_lead("butcher_iron_cross")
	LS.perish_tick(int(b.get("spawned_day", 1)) + LS.COLD_AFTER_DAYS + 1)
	_ok(not LS.get_lead("butcher_iron_cross").is_empty(),
		"a followed lead survives the perish tick (it isn't abandoned)")
	# Doom is captured AFTER the perish tick (which cold-ed the sibling open leads) and immediately
	# before resolve — resolve itself must move nothing (you fought the encounter, no cost).
	var doom_before: float = Mt.get_meter("doom")
	LS.resolve("butcher_iron_cross")
	_ok(LS.get_lead("butcher_iron_cross").is_empty(),
		"a resolved lead leaves the active board")
	_ok(Mt.get_meter("doom") == doom_before,
		"resolving cleanly costs no Doom (you fought the encounter)")

func _test_reset_and_snapshot_restore() -> void:
	print("[leads: reset per run (no carry) + snapshot/restore within a run]")
	var RM: Object = root.get_node("/root/RunManager")
	var LS: Object = _ls()
	if LS == null:
		return
	RM.start_run()
	LS.follow("butcher_iron_cross")
	var snap: Dictionary = LS.to_dict()
	# Mutate within the run: resolve the followed lead.
	LS.resolve("butcher_iron_cross")
	_ok(LS.get_lead("butcher_iron_cross").is_empty(), "resolved before restore")
	# Restore the snapshot -> the followed (unresolved) lead is back.
	LS.from_dict(snap)
	_ok(String(LS.get_lead("butcher_iron_cross").get("state", "")) == "followed",
		"snapshot/restore brings the followed lead back within a run")
	# A fresh run wipes everything and re-slots (no carry of the resolved/followed state).
	RM.start_run()
	_ok(String(LS.get_lead("butcher_iron_cross").get("state", "")) == "open",
		"a new run resets leads to open (no cross-run carry)")

func _test_board_reads_active_leads() -> void:
	print("[leads: the board reads active leads (subject + where_hint + freshness)]")
	var RM: Object = root.get_node("/root/RunManager")
	var LS: Object = _ls()
	if LS == null:
		return
	RM.start_run()
	var rows: Array = LS.active_leads()
	_ok(rows.size() >= 1, "the board has at least one active lead to render")
	var has_fields := true
	for r in rows:
		if String(r.get("subject", "")) == "" or String(r.get("where_hint", "")) == "":
			has_fields = false
	_ok(has_fields, "every active lead exposes a subject and a where_hint for the board")

func _test_determinism_fixed_seed() -> void:
	print("[leads: slotting for a fixed run-seed is identical across runs]")
	var LS: Object = _ls()
	if LS == null:
		return
	LS.slot_run(4242)
	var a: Array = _where_signature(LS.active_leads())
	LS.slot_run(4242)
	var b: Array = _where_signature(LS.active_leads())
	_ok(a == b and not a.is_empty(),
		"the same run-seed slots identical leads (deterministic reshuffle): %s" % [a])
	LS.slot_run(9999)
	var c: Array = _where_signature(LS.active_leads())
	_ok(c.size() == a.size(), "a different seed still slots the same lead set (variety is in placement)")
	_ok(c != a,
		"a different seed produces a DIFFERENT placement signature (the reshuffle is real): 4242=%s 9999=%s" % [a, c])

func _where_signature(rows: Array) -> Array:
	var out: Array = []
	for r in rows:
		out.append("%s@%s" % [r.get("id", ""), r.get("where_hint", "")])
	out.sort()
	return out
