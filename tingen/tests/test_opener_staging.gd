extends SceneTree
## P4 (experiential wave) — the STAGED OPENER + the HARVEST-FORK CHOICE UI (logic layer).
##
## Audit finding: the dramatic opening beat (Constable Brom hammering on doors with the butcher
## lead) happened only as a top-bar string — the player never SAW anyone; and the famous harvest
## fork (digest / sell / keep) was a thought-panel string with no choice UI. This harness pins the
## HEADLESS LOGIC that backs both fixes (the rendered pixels are proven by tests/screenshot_probe.gd):
##
##   (a) GMOpening.stage_source_at_door(): a generic, data-driven staging verb — the scenario's
##       `source_npc` is placed at the authored lodging-door spot (`source_stage_room`/`source_stage_pos`),
##       kept active, latched ONCE per run (idempotent).
##   (b) release_source(): the constable moves on after the beat — back to the authored release spot,
##       activity latch dropped (he is a real scheduled NPC, not a permanent door ornament).
##   (c) DETERMINISM GUARD: a headless start_run must NOT auto-stage the door beat (it is live-only
##       presentation direction) — the pinned sims stay byte-identical by construction.
##   (d) fork_ui() data: scenario.json authors the 3-choice panel copy (title/prompt/options), option
##       ids mirror the harvest_fork words (digest/sell/keep) — copy is DATA, not engine literals.
##   (e) the fork-UI trigger: the FIRST player characteristic pickup (the real `item_picked_up` seam)
##       requests the panel EXACTLY ONCE per run; non-characteristic pickups never do; answered or
##       already-requested never re-presents; reset() re-arms for a fresh run.
##   (f) choose_harvest marks the chosen PLAN on the HUD lead line (guidance only), replacing (not
##       stacking) a prior plan mark.
##   (g) the choice NEVER auto-executes the verbs: no sequence advance, no sale, no item consumed.
##   (h) NPC.show_bark is headless-inert visually (state records the line; no bubble node) — the
##       live-only speech bubble pattern (CombatFeedback/_is_live).
##   (i) HarvestForkPanel (the UI): present() opens with the authored options, choose() routes to
##       GMOpening.choose_harvest and closes, and an answered fork never re-opens.
##
## Standalone: godot --headless --path tingen -s tests/test_opener_staging.gd
## Also folded into the main suite (run_tests.gd `_test_opener_staging`) via the SAME run_all() entry.

func _init() -> void:
	await process_frame
	await process_frame
	# Never touch the player's REAL persistent profile (see tests/test_meta_isolation.gd).
	# N1 (sprint safety): sandbox EVERY persistent path (meta/save/settings/hints/playlog) into
	# user://test_sandbox/<run>/ and arm the write guard — see src/TestSandbox.gd.
	preload("res://src/TestSandbox.gd").activate(root)
	var r: Dictionary = run_all()
	print("\n=== test_opener_staging: %d passed, %d failed ===" % [int(r["passed"]), int(r["failed"])])
	quit(1 if int(r["failed"]) > 0 else 0)

## The one entry point (returns {passed, failed}); folded into run_tests.gd.
static func run_all() -> Dictionary:
	var c := {"passed": 0, "failed": 0}
	var root: Node = (Engine.get_main_loop() as SceneTree).root
	_a_stage_source_at_door(c, root)
	_b_release_source(c, root)
	_c_headless_start_run_never_auto_stages(c, root)
	_d_fork_ui_copy_is_data(c, root)
	_e_fork_ui_trigger_once_per_run(c, root)
	_f_choice_marks_plan_on_lead_line(c, root)
	_g_choice_never_auto_executes(c, root)
	_h_bark_headless_inert(c, root)
	_i_fork_panel_ui(c, root)
	# Leave a clean world for whatever runs next in the shared suite.
	root.get_node("/root/RunManager").start_run()
	root.get_node("/root/Agents").rebuild()
	return c

static func _check(c: Dictionary, cond: bool, label: String) -> void:
	if cond:
		c["passed"] = int(c["passed"]) + 1
		print("  PASS  %s" % label)
	else:
		c["failed"] = int(c["failed"]) + 1
		printerr("  FAIL  %s" % label)

static func _n(root: Node, autoload_name: String) -> Node:
	return root.get_node_or_null("/root/" + autoload_name)

# (a) --------------------------------------------------------------------------------------------
static func _a_stage_source_at_door(c: Dictionary, root: Node) -> void:
	print("[opener staging (a): stage_source_at_door places the source NPC at the authored lodging door, once]")
	var GM: Object = _n(root, "GMOpening")
	var AG: Object = _n(root, "Agents")
	var AR: Object = _n(root, "AgentRuntime")
	var RM: Object = _n(root, "RunManager")
	_check(c, GM != null and GM.has_method("stage_source_at_door"),
		"GMOpening exposes stage_source_at_door() (the generic door-beat staging verb)")
	if GM == null or not GM.has_method("stage_source_at_door"):
		return
	RM.start_run()
	var source := String(GM.OPENING.get("source_npc", ""))
	var stage_room := String(GM.OPENING.get("source_stage_room", ""))
	_check(c, stage_room != "" and (GM.OPENING.get("source_stage_pos") is Array),
		"the scenario authors the door-beat staging spot (source_stage_room + source_stage_pos — data, not code)")
	var staged: Dictionary = GM.stage_source_at_door()
	var brom: Agent = AG.get_agent(source)
	_check(c, brom != null, "the source NPC ('%s') is on the roster" % source)
	if brom == null:
		return
	_check(c, String(staged.get("agent", "")) == source, "the staging verb reports the scenario's source NPC (data-driven)")
	_check(c, brom.room == stage_room, "the source NPC now stands in the authored lodging room ('%s')" % stage_room)
	var want_pos: Vector2 = staged.get("position", Vector2.INF)
	_check(c, brom.position == want_pos and want_pos != Vector2.INF,
		"…at the authored door position %s" % str(want_pos))
	_check(c, bool(AR.always_active.get(source, false)),
		"…and kept ACTIVE so he does not despawn out of the beat")
	_check(c, bool(GM.source_staged()), "source_staged() reads true after the staging")
	# ONCE per run: a second call is a no-op (the latch holds even if he has moved on).
	brom.position = Vector2(-999, -999)
	var again: Dictionary = GM.stage_source_at_door()
	_check(c, again.is_empty() and brom.position == Vector2(-999, -999),
		"a second stage call is a NO-OP (per-run once latch — the knock never replays)")

# (b) --------------------------------------------------------------------------------------------
static func _b_release_source(c: Dictionary, root: Node) -> void:
	print("[opener staging (b): release_source sends the constable back to his beat]")
	var GM: Object = _n(root, "GMOpening")
	var AG: Object = _n(root, "Agents")
	var AR: Object = _n(root, "AgentRuntime")
	var RM: Object = _n(root, "RunManager")
	if GM == null or not GM.has_method("stage_source_at_door"):
		_check(c, false, "GMOpening.stage_source_at_door missing — release_source unpinnable")
		return
	_check(c, GM.has_method("release_source"), "GMOpening exposes release_source()")
	if not GM.has_method("release_source"):
		return
	RM.start_run()
	GM.stage_source_at_door()
	var source := String(GM.OPENING.get("source_npc", ""))
	GM.release_source()
	var brom: Agent = AG.get_agent(source)
	var stage_room := String(GM.OPENING.get("source_stage_room", ""))
	_check(c, brom != null and brom.room != stage_room,
		"released: the source NPC left the lodging room (back on his city beat)")
	_check(c, not bool(AR.always_active.get(source, false)),
		"released: the always-active staging latch is dropped (a real scheduled NPC again)")
	_check(c, bool(GM.source_staged()), "the per-run once latch HOLDS through release (no knock replay)")

# (c) --------------------------------------------------------------------------------------------
static func _c_headless_start_run_never_auto_stages(c: Dictionary, root: Node) -> void:
	print("[opener staging (c): DETERMINISM — a headless start_run never auto-stages the door beat]")
	var GM: Object = _n(root, "GMOpening")
	var AG: Object = _n(root, "Agents")
	var RM: Object = _n(root, "RunManager")
	if GM == null or not GM.has_method("source_staged"):
		_check(c, false, "GMOpening.source_staged missing — determinism guard unpinnable")
		return
	RM.start_run()
	var source := String(GM.OPENING.get("source_npc", ""))
	var stage_room := String(GM.OPENING.get("source_stage_room", ""))
	var brom: Agent = AG.get_agent(source)
	_check(c, DisplayServer.get_name() == "headless", "(precondition) this harness runs headless")
	_check(c, not bool(GM.source_staged()),
		"headless start_run did NOT auto-stage the door beat (live-only presentation direction)")
	_check(c, brom != null and brom.room != stage_room,
		"…and the source NPC is NOT standing in the lodging (pinned sims byte-identical by construction)")

# (d) --------------------------------------------------------------------------------------------
static func _d_fork_ui_copy_is_data(c: Dictionary, root: Node) -> void:
	print("[opener staging (d): the fork panel copy is scenario DATA, ids mirror the fork words]")
	var GM: Object = _n(root, "GMOpening")
	_check(c, GM != null and GM.has_method("fork_ui"), "GMOpening exposes fork_ui() (the authored panel copy)")
	if GM == null or not GM.has_method("fork_ui"):
		return
	var ui: Dictionary = GM.fork_ui()
	_check(c, String(ui.get("title", "")) != "" and String(ui.get("prompt", "")) != "",
		"the fork panel authors a title + a prompt (diegetic copy from data)")
	var opts: Array = ui.get("options", [])
	var fork_words: Array = GM.harvest_fork().get("options", [])
	_check(c, opts.size() == fork_words.size() and opts.size() == 3,
		"the panel offers exactly the fork's option count (3)")
	var ids: Array = []
	var labels_ok := true
	for o in opts:
		ids.append(String((o as Dictionary).get("id", "")))
		if String((o as Dictionary).get("label", "")) == "":
			labels_ok = false
	for w in fork_words:
		_check(c, ids.has(String(w)), "panel option ids include the fork word '%s'" % String(w))
	_check(c, labels_ok, "every panel option carries a non-empty authored label")

# (e) --------------------------------------------------------------------------------------------
static func _e_fork_ui_trigger_once_per_run(c: Dictionary, root: Node) -> void:
	print("[opener staging (e): the FIRST characteristic pickup requests the fork panel exactly once]")
	var GM: Object = _n(root, "GMOpening")
	var RM: Object = _n(root, "RunManager")
	if GM == null or not GM.has_signal("harvest_fork_ui_requested"):
		_check(c, false, "GMOpening.harvest_fork_ui_requested signal missing")
		return
	RM.start_run()
	var seen := {"n": 0, "title": ""}
	var cb := func(ui: Dictionary) -> void:
		seen["n"] = int(seen["n"]) + 1
		seen["title"] = String(ui.get("title", ""))
	GM.harvest_fork_ui_requested.connect(cb)
	# A non-characteristic pickup never presents (the fork is about the harvest).
	GM._on_event({"type": "item_picked_up", "data": {"caster": "player", "item": "revolver_round"}})
	_check(c, int(seen["n"]) == 0, "a non-characteristic pickup does NOT request the fork panel")
	# The first characteristic pickup presents (the tainted butcher drop, data convention *_characteristic).
	GM._on_event({"type": "item_picked_up", "data": {"caster": "player", "item": "tainted_characteristic"}})
	_check(c, int(seen["n"]) == 1, "the FIRST characteristic pickup requests the fork panel")
	_check(c, String(seen["title"]) == String(GM.fork_ui().get("title", "")),
		"…carrying the authored panel copy (data)")
	_check(c, bool(GM.fork_ui_presented()), "fork_ui_presented() latched")
	# A second pickup never re-presents (per-run once flag — the HintDirector pattern).
	GM._on_event({"type": "item_picked_up", "data": {"caster": "player", "item": "hunter_characteristic"}})
	_check(c, int(seen["n"]) == 1, "a SECOND characteristic pickup is a no-op (per-run once flag)")
	# Answered forks stay answered: a fresh run re-arms, then an early answer suppresses the panel.
	RM.start_run()
	_check(c, not bool(GM.fork_ui_presented()), "a fresh run re-arms the fork panel (reset scrubs the latch)")
	GM.choose_harvest("keep")
	GM._on_event({"type": "item_picked_up", "data": {"caster": "player", "item": "tainted_characteristic"}})
	_check(c, int(seen["n"]) == 1, "an ALREADY-ANSWERED fork never re-presents on pickup")
	GM.harvest_fork_ui_requested.disconnect(cb)

# (f) --------------------------------------------------------------------------------------------
static func _f_choice_marks_plan_on_lead_line(c: Dictionary, root: Node) -> void:
	print("[opener staging (f): the choice marks the chosen PLAN on the HUD lead line (guidance only)]")
	var GM: Object = _n(root, "GMOpening")
	var WS: Object = _n(root, "WorldState")
	var RM: Object = _n(root, "RunManager")
	if GM == null or not GM.has_method("fork_ui"):
		_check(c, false, "GMOpening.fork_ui missing — plan marking unpinnable")
		return
	RM.start_run()
	var before := String(WS.current_lead)
	GM.choose_harvest("sell")
	var after := String(WS.current_lead)
	var sell_label := _option_label(GM, "sell")
	_check(c, sell_label != "" and after.find(sell_label) != -1,
		"choosing 'sell' marks the authored plan label on the lead line: %s" % after)
	_check(c, after.begins_with(before.split(" · plan:")[0].strip_edges()) or after.find("—") != -1,
		"…the original objective text survives (the plan is appended guidance, not a replacement)")
	# Re-choosing REPLACES the plan mark (never stacks two plans).
	GM.choose_harvest("digest")
	var re := String(WS.current_lead)
	var digest_label := _option_label(GM, "digest")
	_check(c, re.find(digest_label) != -1 and re.find(sell_label) == -1,
		"re-choosing replaces the plan mark (no stacking): %s" % re)

static func _option_label(GM: Object, id: String) -> String:
	for o in (GM.fork_ui().get("options", []) as Array):
		if String((o as Dictionary).get("id", "")) == id:
			return String((o as Dictionary).get("label", ""))
	return ""

# (g) --------------------------------------------------------------------------------------------
static func _g_choice_never_auto_executes(c: Dictionary, root: Node) -> void:
	print("[opener staging (g): the fork choice sets GUIDANCE only — the world verbs stay the real seams]")
	var GM: Object = _n(root, "GMOpening")
	var AG: Object = _n(root, "Agents")
	var PR: Object = _n(root, "Progression")
	var SH: Object = _n(root, "Shop")
	var RM: Object = _n(root, "RunManager")
	if GM == null:
		return
	RM.start_run()
	# Give the player a sellable/digestible harvest so an auto-execute WOULD be observable.
	var proxy: Agent = AG.ensure_player_proxy(Vector2(100, 100), "city")
	proxy.add_item("tainted_characteristic", 1)
	var seq0: int = int(PR.sequence())
	var coin0: int = proxy.item_count(SH.coin_item())
	GM.choose_harvest("digest")
	_check(c, int(PR.sequence()) == seq0, "choosing 'digest' did NOT advance the Sequence (guidance, not execution)")
	GM.choose_harvest("sell")
	_check(c, proxy.item_count(SH.coin_item()) == coin0, "choosing 'sell' did NOT sell anything (no coin appeared)")
	_check(c, proxy.item_count("tainted_characteristic") == 1,
		"the carried Characteristic is untouched by any choice (the world actions remain the seams)")

# (h) --------------------------------------------------------------------------------------------
static func _h_bark_headless_inert(c: Dictionary, root: Node) -> void:
	print("[opener staging (h): NPC.show_bark is headless-inert visually (live-only speech bubble)]")
	var npc: Node = (load("res://scenes/NPC.tscn") as PackedScene).instantiate()
	npc.npc_id = "constable_brom"
	root.add_child(npc)
	_check(c, npc.has_method("show_bark"), "NPC bodies expose show_bark(text) (the spoken-line bubble seam)")
	if npc.has_method("show_bark"):
		npc.show_bark("The butcher's on Iron Cross.")
		_check(c, String(npc.bark_text()) == "The butcher's on Iron Cross.",
			"the bark STATE is recorded (headless-observable)")
		_check(c, npc.get_node_or_null("Bark") == null,
			"headless: NO bubble node is mounted (pinned sims never see a cosmetic node)")
	npc.free()

# (i) --------------------------------------------------------------------------------------------
static func _i_fork_panel_ui(c: Dictionary, root: Node) -> void:
	print("[opener staging (i): HarvestForkPanel presents the authored options and routes the choice]")
	var GM: Object = _n(root, "GMOpening")
	var RM: Object = _n(root, "RunManager")
	if not ResourceLoader.exists("res://src/HarvestForkPanel.gd"):
		_check(c, false, "src/HarvestForkPanel.gd exists (the 3-choice fork panel)")
		return
	RM.start_run()
	var panel: Control = (load("res://src/HarvestForkPanel.gd") as GDScript).new()
	root.add_child(panel)
	_check(c, not panel.is_open(), "the panel starts closed")
	panel.present(GM.fork_ui())
	_check(c, panel.is_open(), "present() opens the panel")
	_check(c, panel.option_count() == 3, "the panel shows the 3 authored choices")
	panel.choose("keep")
	_check(c, not panel.is_open(), "choosing closes the panel")
	_check(c, String(GM.harvest_choice()) == "keep",
		"the panel routed the choice to GMOpening.choose_harvest (one logic seam)")
	# An answered fork never re-opens (the panel respects the once-answered contract).
	panel.present(GM.fork_ui())
	_check(c, not panel.is_open(), "an ANSWERED fork never re-opens the panel")
	panel.free()
