extends SceneTree
## N2 — DEATH COSTS A DAY, NOT THE RUN (checkpoint integrity). A fresh-eyes playtest found the
## roguelite's core promise broken at four seams; this harness pins each one FROM THE LIVE WIRES
## (the real Main.tscn BootController, the real EventBus agent_downed the combat executor emits,
## the real overlay buttons) so a green run proves the player-facing flow, not just the autoloads:
##   (a) A1  a combat death AFTER a nightly checkpoint routes through RunManager.end_run("death")
##           and WAKES the player at the lodging: day rolled back, inventory restored, pathway +
##           run codex ledger retained, a Continue-style "death_wake" screen (mirrors lost_control).
##   (b) A1  a combat death with NO checkpoint (day-1 pre-checkpoint) is a normal RUN LOSS: the
##           meta payoff flushes (codex keeps what the run learned), run_ended("lose") returns the
##           boot controller to the title, and the terminal screen carries the payoff section.
##   (c) B-F3/B-F4  the ending screen's action button returns to the TITLE through the boot flow —
##           NO direct start_run (no double-counted runs_played, no Hermit->Hunter reroute); the
##           next run starts only through the real New Run flow / pathway picker.
##   (d) A2  the player proxy's INVENTORY (rounds/shillings/tools/characteristics) rides the DISK
##           save manifest too (shared-manifest discipline), and a post-load ensure_player_proxy
##           does NOT re-grant the day-1 loadout.
##   (e) A4  checkpoint_night() REFUSES during a live Ritual Night (no safe night once the fuse is
##           lit — the rest verb already refuses); a death then restores the last PRE-climax
##           checkpoint and the fuse can RELIGHT (Doom back below 100, the fired latch clear).
##   (f) A4  RitualNight.reset() restores the AUTHORED site room (a tipped-relocation must not
##           leak the relocated crypt across runs).
## Standalone: godot --headless --path tingen -s tests/test_death_checkpoint.gd
## Also folded into the main suite (run_tests.gd `_test_death_checkpoint`) via the SAME run_all().

func _init() -> void:
	await process_frame
	await process_frame
	# N1 (sprint safety): sandbox EVERY persistent path (meta/save/settings/hints/playlog) into
	# user://test_sandbox/<run>/ and arm the write guard — see src/TestSandbox.gd.
	preload("res://src/TestSandbox.gd").activate(root)
	var r: Dictionary = await run_all()
	print("\n=== test_death_checkpoint: %d passed, %d failed ===" % [int(r["passed"]), int(r["failed"])])
	quit(1 if int(r["failed"]) > 0 else 0)

## The one entry point (returns {passed, failed}); folded into run_tests.gd. Coroutine (mounts the
## REAL boot controller + awaits frames), so callers must `await run_all()`.
static func run_all() -> Dictionary:
	var c := {"passed": 0, "failed": 0}
	var root: Node = (Engine.get_main_loop() as SceneTree).root
	# Mount the REAL entry scene: the live seam every beat below must be reachable from.
	var main: Node = (load("res://scenes/Main.tscn") as PackedScene).instantiate()
	root.add_child(main)
	await root.get_tree().process_frame
	await root.get_tree().process_frame
	await _a_death_after_checkpoint_wakes(c, root, main)
	await _b_day1_death_is_run_loss(c, root, main)
	await _c_ending_button_returns_to_title(c, root, main)
	main.queue_free()
	await root.get_tree().process_frame
	_d_inventory_rides_disk_save(c, root)
	_e_ritual_night_fuse_integrity(c, root)
	_f_site_room_reset(c, root)
	# Leave a clean world for whatever runs next in the shared suite.
	var eg: Object = root.get_node("/root/EndGame")
	eg._hide_overlay()
	eg.rearm()
	root.get_tree().paused = false
	root.get_node("/root/RunManager").start_run()
	root.get_node("/root/Agents").rebuild()
	return c

static func _check(c: Dictionary, cond: bool, label: String) -> bool:
	if cond:
		c["passed"] = int(c["passed"]) + 1
		print("  PASS  %s" % label)
	else:
		c["failed"] = int(c["failed"]) + 1
		printerr("  FAIL  %s" % label)
	return cond

static func _n(root: Node, name: String) -> Object:
	return root.get_node_or_null("/root/" + name)

## Depth-first find a Button by exact label under `node` (the real overlay buttons are pressed).
static func _find_button(node: Node, text: String) -> Button:
	if node == null:
		return null
	if node is Button and String((node as Button).text) == text:
		return node
	for ch in node.get_children():
		var hit := _find_button(ch, text)
		if hit != null:
			return hit
	return null

## The ending screen's non-Quit action button (labelled "Restart" pre-N2, "Return to Title" after)
## — found by exclusion so the RED run still presses the OLD wire and proves the damage.
static func _action_button(node: Node) -> Button:
	if node == null:
		return null
	if node is Button and String((node as Button).text) != "Quit":
		return node
	for ch in node.get_children():
		var hit := _action_button(ch)
		if hit != null:
			return hit
	return null

## Down the live player proxy through the REAL lethal seam: CombatExecutor.route_hit emits the
## same agent_downed{target:"player"} the live fight does — the wire EndGame listens on.
static func _down_player(root: Node) -> void:
	var AG: Object = _n(root, "Agents")
	var proxy: Agent = AG.ensure_player_proxy(Vector2(300, 300), "klein_bedroom")
	proxy.hp = 5.0
	proxy.downed = false
	var attacker: Agent = AG.get_agent("clerk_voss")
	CombatExecutor.route_hit(attacker, proxy,
		{"id": "n2_lethal", "effects": [{"kind": "damage", "amount": 9999.0}]}, Vector2.LEFT)

# (a) ----------------------------------------------------------------------------------------------
static func _a_death_after_checkpoint_wakes(c: Dictionary, root: Node, main: Node) -> void:
	print("[N2 (a): a checkpointed combat death costs THE DAY — end_run('death') wakes the player at the lodging]")
	var RM: Object = _n(root, "RunManager")
	var AG: Object = _n(root, "Agents")
	var CL: Object = _n(root, "Clock")
	var EG: Object = _n(root, "EndGame")
	var PR: Object = _n(root, "Progression")

	# Start through the REAL New Run flow (drive the picker to Hunter if the meta offers one).
	main.start_new_run()
	if main.pathway_picker_active():
		main.choose_pathway("hunter")
	await root.get_tree().process_frame
	await root.get_tree().process_frame
	_check(c, RM.run_active() and String(main.current_scene_path) == "res://scenes/IntroRoom.tscn",
		"New Run started a live run in the lodging")

	# What the run has LEARNED (the codex ledger) must survive the death (a setback, not a run end).
	RM._run_knowledge["adversary:n2_probe_form"] = true

	# Shape the day's earnings/spends so the restore has something real to reproduce.
	var proxy: Agent = AG.ensure_player_proxy(main.player_position(), "klein_bedroom")
	proxy.remove_item("revolver_round", 3)   # spent rounds: 12 -> 9
	proxy.add_item("ritual_salt", 1)         # a gathered ingredient
	var rounds_at_cp: int = proxy.item_count("revolver_round")
	var salt_at_cp: int = proxy.item_count("ritual_salt")

	# Cross NIGHTFALL while resting in the lodging — the LIVE nightly auto-checkpoint seam.
	CL.set_time(2, 1140)
	_check(c, RM.has_checkpoint() and RM.checkpoint_day() == 2,
		"nightfall in the lodging took the nightly checkpoint (day 2)")

	# The NEXT day goes badly: more spends, a strange pickup, and a march into the crypt.
	CL.set_time(3, 600)
	proxy.remove_item("revolver_round", 5)
	proxy.add_item("n2_bauble", 1)
	main.load_world_at("res://scenes/CathedralCrypt.tscn", Vector2(691, 500))
	await root.get_tree().process_frame
	await root.get_tree().process_frame
	_check(c, String(main.current_scene_path) == "res://scenes/CathedralCrypt.tscn",
		"the player walked into the crypt on day 3 (the doomed day)")

	# Down the player through the REAL lethal wire; collect the run_ended reasons.
	var ended: Array = []
	var on_end := func(reason: String) -> void: ended.append(reason)
	RM.run_ended.connect(on_end)
	_down_player(root)
	await root.get_tree().process_frame
	await root.get_tree().process_frame
	await root.get_tree().process_frame
	RM.run_ended.disconnect(on_end)

	_check(c, ended == ["death"],
		"the live combat death routed through RunManager.end_run('death') exactly once (got %s)" % str(ended))
	_check(c, RM.run_active(), "the run CONTINUES after a checkpointed death (a setback, not a run end)")
	_check(c, RM.current_day() == 2,
		"the death cost THE DAY: day 3 rolled back to the checkpoint's day 2 (got %d)" % RM.current_day())
	_check(c, RM.has_checkpoint(), "the checkpoint survives the restore (a second death still wakes)")
	_check(c, String(main.current_scene_path) == "res://scenes/IntroRoom.tscn",
		"the player WOKE at the lodging (the boot controller's wake seam fired)")
	# The wake must NOT mount the run-opening IntroCard cinematic: frozen at its black first frame
	# by the death-screen pause (layer 200 over EndGame's 12) it painted the WHOLE screen black —
	# probe shot 21 caught the death screen invisible behind it. A wake is not an opening.
	var ws: Node = main.world_scene()
	_check(c, ws != null and ws.get_node_or_null("IntroCard") == null,
		"the wake carries NO IntroCard cinematic (the death screen owns the screen)")
	_check(c, EG.has_overlay() and root.get_tree().paused,
		"a Continue-style death screen is up over the wake (paused)")
	_check(c, String(EG._last_result.get("outcome", "")) == "death_wake",
		"the screen is the 'death_wake' beat, not the terminal ending (got '%s')"
		% String(EG._last_result.get("outcome", "")))

	# A2 tie-in: the restore reproduces the CHECKPOINT loadout, not day-1, not the doomed day's.
	var p2: Agent = AG.get_agent("player")
	_check(c, p2 != null and p2.item_count("revolver_round") == rounds_at_cp,
		"the checkpoint INVENTORY is back: %d rounds (got %s)"
		% [rounds_at_cp, str(p2.item_count("revolver_round")) if p2 != null else "<no proxy>"])
	_check(c, p2 != null and p2.item_count("ritual_salt") == salt_at_cp,
		"…the pre-checkpoint ingredient survives (ritual_salt)")
	_check(c, p2 != null and p2.item_count("n2_bauble") == 0,
		"…the post-checkpoint pickup is gone (the lost day)")
	_check(c, String(PR.pathway()) == "hunter", "the run's PATHWAY is preserved across the wake")
	_check(c, RM._run_knowledge.has("adversary:n2_probe_form"),
		"the run's in-memory codex ledger is RETAINED (a death never flushes/wipes it)")

	# Press the REAL Continue: the freeze lifts and play resumes — mirroring the lost_control flow.
	var cont := _find_button(EG._overlay, "Continue")
	_check(c, cont != null, "the death_wake screen offers CONTINUE (not Restart/Quit)")
	if cont != null:
		cont.pressed.emit()
	await root.get_tree().process_frame
	_check(c, not root.get_tree().paused and not EG.has_overlay(),
		"Continue lifted the freeze and dropped the overlay (the day is lost; the run plays on)")

	# A SECOND death the same day, dying IN a freshly re-entered lodging whose own IntroCard is
	# still alive (the probe's exact staging): the wake swap briefly holds TWO scenes (the
	# queue_freed old one is still child 0), so stripping only the FIRST card found skips the
	# dying scene's card and leaves the freshly mounted one frozen black over the death screen.
	main.load_world_at("res://scenes/IntroRoom.tscn", Vector2(415, 470))
	await root.get_tree().process_frame
	await root.get_tree().process_frame
	_down_player(root)
	await root.get_tree().process_frame
	await root.get_tree().process_frame
	await root.get_tree().process_frame
	_check(c, (main._world.find_children("IntroCard", "", true, false) as Array).is_empty(),
		"a death FROM the lodging strips EVERY IntroCard (none left to black out the death screen)")
	_check(c, EG.has_overlay() and String(EG._last_result.get("outcome", "")) == "death_wake",
		"…and the second same-day death still raises the death_wake screen")
	var cont2 := _find_button(EG._overlay, "Continue")
	if cont2 != null:
		cont2.pressed.emit()
	await root.get_tree().process_frame

# (b) ----------------------------------------------------------------------------------------------
static func _b_day1_death_is_run_loss(c: Dictionary, root: Node, main: Node) -> void:
	print("[N2 (b): a day-1 pre-checkpoint combat death is a NORMAL RUN LOSS — meta payoff + title]")
	var RM: Object = _n(root, "RunManager")
	var EG: Object = _n(root, "EndGame")

	# Close (a)'s live run cleanly (abandon -> title), then start a fresh day-1 run.
	if RM.run_active():
		RM.end_run("lose")
	await root.get_tree().process_frame
	var runs0: int = int(RM.meta_runs_played())
	main.start_new_run()
	if main.pathway_picker_active():
		main.choose_pathway("hunter")
	await root.get_tree().process_frame
	await root.get_tree().process_frame
	_check(c, RM.run_active() and not RM.has_checkpoint(),
		"a fresh run is live with NO checkpoint yet (day-1 pre-checkpoint)")
	var runs_started: int = int(RM.meta_runs_played())
	_check(c, runs_started == runs0 + 1, "New Run counted exactly one run played")
	RM._run_knowledge["adversary:n2_day1_form"] = true

	var ended: Array = []
	var on_end := func(reason: String) -> void: ended.append(reason)
	RM.run_ended.connect(on_end)
	_down_player(root)
	await root.get_tree().process_frame
	await root.get_tree().process_frame
	await root.get_tree().process_frame
	RM.run_ended.disconnect(on_end)

	_check(c, ended == ["lose"],
		"the no-checkpoint death closed the run as a LOSS — run_ended('lose') exactly once (got %s)" % str(ended))
	_check(c, not RM.run_active(), "the run is over (nothing to wake back to)")
	_check(c, main.is_at_title(), "the boot controller returned to the TITLE under the ending overlay")
	_check(c, EG.has_overlay() and root.get_tree().paused,
		"the terminal death screen is up (paused) over the title")
	_check(c, String(EG._last_result.get("outcome", "")) == "player_downed",
		"…and it is the terminal 'player_downed' ending (got '%s')"
		% String(EG._last_result.get("outcome", "")))
	# The meta payoff FLUSHED: the codex keeps what the doomed run learned + the ending fact.
	var ids: Array = []
	for e in RM.meta_codex():
		if e is Dictionary:
			ids.append(String((e as Dictionary).get("id", "")))
	_check(c, ids.has("adversary:n2_day1_form"),
		"the meta codex kept what the doomed run learned (correct flush, not a silent wipe)")
	_check(c, ids.has("ending:player_downed"),
		"the meta codex records the 'ending:player_downed' fact")
	_check(c, int(RM.meta_runs_played()) == runs_started,
		"the death itself counted NO extra run (runs_played still %d)" % runs_started)
	# The overlay carries the run-payoff section (the same seam a climax lose renders through).
	_check(c, EG._overlay_box != null and EG._overlay_box.get_node_or_null("RunPayoff") != null,
		"the ending screen shows the run's payoff section (the loss still pays the codex forward)")

# (c) ----------------------------------------------------------------------------------------------
static func _c_ending_button_returns_to_title(c: Dictionary, root: Node, main: Node) -> void:
	print("[N2 (c): the ending screen's action button returns to the TITLE — no start_run, no reroute]")
	var RM: Object = _n(root, "RunManager")
	var EG: Object = _n(root, "EndGame")
	var PR: Object = _n(root, "Progression")

	# Clear (b)'s terminal overlay through its own action button FIRST — this is the B-F3 seam.
	var btn := _action_button(EG._overlay)
	_check(c, btn != null, "the terminal ending screen offers a non-Quit action button")
	var runs_before: int = int(RM.meta_runs_played())
	if btn != null:
		btn.pressed.emit()
	await root.get_tree().process_frame
	await root.get_tree().process_frame
	_check(c, not root.get_tree().paused and not EG.has_overlay(),
		"the button dropped the overlay and lifted the freeze")
	_check(c, not RM.run_active(),
		"NO run was started by the ending screen (the next run starts only via New Run)")
	_check(c, int(RM.meta_runs_played()) == runs_before,
		"runs_played did NOT bump (no double-counted run; got %d, want %d)"
		% [int(RM.meta_runs_played()), runs_before])
	_check(c, main.is_at_title(), "the flow stands at the TITLE (the boot flow owns the handoff)")

	# The Hermit reroute (B-F4): win as Hermit, take the ending button, and prove the NEXT run is
	# started only through the real picker — with Hermit still offered and honored.
	RM.start_run()
	RM.end_run("win", {"outcome": "descent_stopped"})   # the unlock write (first win -> Hermit)
	RM.reload_meta()
	await root.get_tree().process_frame
	main.start_new_run()
	await root.get_tree().process_frame
	_check(c, main.pathway_picker_active(), "with Hermit unlocked, New Run presents the pathway picker")
	main.choose_pathway("hermit")
	await root.get_tree().process_frame
	await root.get_tree().process_frame
	_check(c, String(PR.pathway()) == "hermit", "the picked Hermit run is live")
	# Reach a win SCREEN the way the resolver does (screen first, then the run outcome).
	EG.show_ritual_result({"outcome": "descent_stopped", "reason": "win"})
	RM.end_run("win", {"outcome": "descent_stopped"})
	await root.get_tree().process_frame
	_check(c, EG.has_overlay(), "the climax win screen is up")
	var runs_hermit: int = int(RM.meta_runs_played())
	var btn2 := _action_button(EG._overlay)
	# Read the label BEFORE pressing — the press frees the overlay (and the button with it).
	var btn2_text: String = String(btn2.text) if btn2 != null else "<none>"
	_check(c, btn2 != null and btn2_text.contains("Title"),
		"the button says what it does now — it returns to the Title (got '%s')" % btn2_text)
	if btn2 != null:
		btn2.pressed.emit()
	await root.get_tree().process_frame
	await root.get_tree().process_frame
	_check(c, not RM.run_active() and int(RM.meta_runs_played()) == runs_hermit,
		"the win screen's button started NO run and counted NO run (B-F3)")
	main.start_new_run()
	await root.get_tree().process_frame
	_check(c, main.pathway_picker_active(), "the NEXT run goes through the REAL picker again")
	main.choose_pathway("hermit")
	await root.get_tree().process_frame
	_check(c, String(PR.pathway()) == "hermit",
		"…and a Hermit player STAYS Hermit (no silent Hunter reroute, B-F4)")
	RM.end_run("lose")   # abandon back to the title so teardown leaves no live run on `main`
	await root.get_tree().process_frame

# (d) ----------------------------------------------------------------------------------------------
static func _d_inventory_rides_disk_save(c: Dictionary, root: Node) -> void:
	print("[N2 (d): the player proxy inventory rides the DISK save manifest (shared-manifest discipline)]")
	var RM: Object = _n(root, "RunManager")
	var AG: Object = _n(root, "Agents")
	var SM: Object = _n(root, "SaveManager")

	RM.start_run()
	var proxy: Agent = AG.ensure_player_proxy(Vector2(100, 100), "city")
	proxy.remove_item("revolver_round", 4)          # 12 -> 8 spent
	proxy.add_item("ritual_salt", 2)                # tools/ingredients
	proxy.add_item("hunter_characteristic", 1)      # the pathway's advance fuel
	var shillings: int = proxy.item_count("shilling")
	_check(c, bool(SM.save_game()), "save_game() wrote the (sandboxed) nightly save")

	# Post-save drift that the load must UNDO; then a fresh-boot roster (the proxy is gone).
	proxy.add_item("revolver_round", 99)
	proxy.remove_item("ritual_salt", 2)
	AG.rebuild()
	_check(c, AG.get_agent("player") == null, "rebuild dropped the ephemeral proxy (fresh boot)")
	_check(c, bool(SM.load_game()), "load_game() read the save back")

	var p2: Agent = AG.get_agent("player")
	_check(c, p2 != null, "the load restored a player proxy (the inventory has a body to live on)")
	_check(c, p2 != null and p2.item_count("revolver_round") == 8,
		"spent rounds STAY spent across save/load (8, got %s)"
		% (str(p2.item_count("revolver_round")) if p2 != null else "<none>"))
	_check(c, p2 != null and p2.item_count("ritual_salt") == 2
			and p2.item_count("hunter_characteristic") == 1,
		"tools + the harvested Characteristic survive the load")
	_check(c, p2 != null and p2.item_count("shilling") == shillings,
		"the coin purse survives the load (%d shillings)" % shillings)
	# The per-frame ensure must NOT re-grant the day-1 loadout on top of the restored proxy.
	var p3: Agent = AG.ensure_player_proxy(Vector2(101, 100), "city")
	_check(c, p3.item_count("revolver_round") == 8,
		"ensure_player_proxy after a load does NOT re-grant the day-1 loadout")
	RM.start_run()   # leave a clean run state

# (e) ----------------------------------------------------------------------------------------------
static func _e_ritual_night_fuse_integrity(c: Dictionary, root: Node) -> void:
	print("[N2 (e): no checkpoint during a live Ritual Night — a death restores PRE-climax and the fuse relights]")
	var RM: Object = _n(root, "RunManager")
	var M: Object = _n(root, "Meters")
	var RN: Object = _n(root, "RitualNight")

	RM.start_run()
	M.set_meter("doom", 40.0)
	RM.checkpoint_night()
	_check(c, RM.has_checkpoint(), "a pre-climax nightly checkpoint stands (Doom 40)")

	M.set_meter("doom", 100.0)
	_check(c, RN.active(), "Doom 100 lit the Ritual Night (precondition)")

	# The gate: once the fuse is lit there is NO safe night (the rest verb already refuses).
	var saves := {"n": 0}
	var on_cp := func(_day: int) -> void: saves["n"] = int(saves["n"]) + 1
	RM.checkpoint_saved.connect(on_cp)
	RM.checkpoint_night()
	RM.checkpoint_saved.disconnect(on_cp)
	_check(c, int(saves["n"]) == 0,
		"checkpoint_night() REFUSES during the live climax (no Doom-100 checkpoint can exist)")

	# A death mid-climax restores the PRE-climax checkpoint — and the fuse can relight.
	RM.end_run("death")
	_check(c, M.get_meter("doom") < 100.0,
		"the restore pulled Doom back below 100 (got %.0f)" % M.get_meter("doom"))
	_check(c, not RN.active() and not RM.ritual_night_reached(),
		"no climax is live after the restore")
	_check(c, not bool(M._ritual_night_fired),
		"the Meters ritual_night latch is UNSPENT after the restore (the fuse can relight)")
	M.set_meter("doom", 100.0)
	_check(c, RN.active(), "Doom 100 RELIGHTS the Ritual Night after the death-restore (no softlock)")
	RN.reset()
	RM.start_run()
	root.get_node("/root/Agents").rebuild()

# (f) ----------------------------------------------------------------------------------------------
static func _f_site_room_reset(c: Dictionary, root: Node) -> void:
	print("[N2 (f): RitualNight.reset() restores the AUTHORED site room (no relocation leak across runs)]")
	var RN: Object = _n(root, "RitualNight")
	var authored := "cathedral_crypt"
	if FileAccess.file_exists("res://data/scenario.json"):
		var parsed: Variant = JSON.parse_string(FileAccess.get_file_as_string("res://data/scenario.json"))
		if parsed is Dictionary and (parsed as Dictionary).get("ritual_night") is Dictionary:
			authored = String(((parsed as Dictionary)["ritual_night"] as Dictionary).get("site_room", authored))

	RN.reset()
	RN.set_tipped(true)
	RN.force_assault(true, 0)   # early + tipped -> the site relocates once (seeded, deterministic)
	_check(c, bool(RN.relocated()) and String(RN.site_room()) != authored,
		"a tipped early assault RELOCATED the site (precondition; got '%s')" % String(RN.site_room()))
	RN.reset()
	_check(c, String(RN.site_room()) == authored,
		"reset() restores the AUTHORED site room '%s' (got '%s')" % [authored, String(RN.site_room())])
	root.get_node("/root/Agents").rebuild()
