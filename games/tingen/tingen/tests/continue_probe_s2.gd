extends SceneTree
## N3 — CONTINUE PROBE, SESSION 2 of 2 (a TOOL; see tests/continue_probe.sh). The second half of
## the TWO-PROCESS cross-session Continue proof: a FRESH Godot process (fresh autoloads — the real
## "next sitting") boots the REAL Main.tscn title, presses the REAL Continue, and asserts the
## resumed run is indistinguishable from a never-quit run:
##   C1  the title offers Continue (enabled button) because session 1's save exists
##   C2  [B-F1] RunManager.run_active() is TRUE after Continue
##   C3  [B-F1] the day counter resumed at 2 (not stuck at 1)
##   C4  the world loaded (Clock day 2, lodging scene, Hunter Seq 9)
##   C5  pause works (PauseMenu.open() is eligible again)
##   C6  [B-F2] the run knowledge ledger survived the process boundary (codex will flush on end)
##   C7  codex recording is LIVE again (a fresh downed Beyonder lands in the ledger)
##   C8  nightly checkpoints continue (rest_until_morning -> day 3 checkpoint)
##   C9  Ritual Night can arm and fire (Doom 100 -> latch + staged climax)
##   C10 [B-F5] a full run-end invalidates the save — title Continue greys out (no ghost resume)
## Run AFTER continue_probe_s1.gd, same fixed slots:
##   godot --headless --path tingen -s tests/continue_probe_s2.gd

const SHARED_DIR := "user://test_sandbox/continue_probe/"
const SHARED_SAVE := SHARED_DIR + "save.json"
const SHARED_META := SHARED_DIR + "meta.json"

var _passed := 0
var _failed := 0

func _ok(cond: bool, label: String) -> void:
	if cond:
		_passed += 1
		print("  PASS  %s" % label)
	else:
		_failed += 1
		printerr("  FAIL  %s" % label)

func _find_button(node: Node, name_: String) -> Button:
	if node is Button and node.name == name_:
		return node
	for c in node.get_children():
		var b := _find_button(c, name_)
		if b != null:
			return b
	return null

func _init() -> void:
	await process_frame
	await process_frame
	preload("res://src/TestSandbox.gd").activate(root)
	var SM: Node = root.get_node("/root/SaveManager")
	var RM: Node = root.get_node("/root/RunManager")
	var CL: Node = root.get_node("/root/Clock")
	SM.save_path = SHARED_SAVE
	RM.meta_path = SHARED_META
	RM.reload_meta()

	_ok(FileAccess.file_exists(SHARED_SAVE),
		"s2 precondition: session 1's shared save exists (run continue_probe_s1.gd first)")

	print("[s2] fresh process — boot the REAL Main.tscn title")
	var main: Node = (load("res://scenes/Main.tscn") as PackedScene).instantiate()
	root.add_child(main)
	await process_frame
	await process_frame
	_ok(bool(main.is_at_title()), "s2: boot lands at the title")
	_ok(bool(main.has_continue()), "s2 C1: has_continue() true (session 1's save offered)")
	var cont_btn := _find_button(main, "ContinueButton")
	_ok(cont_btn != null and not cont_btn.disabled, "s2 C1: title Continue button enabled")

	print("[s2] press the REAL Continue (BootController.continue_run)")
	main.continue_run()
	for i in 10:
		await process_frame

	# --- B-F1: the resumed run is a LIVE run --------------------------------------------------
	_ok(bool(RM.run_active()), "s2 C2 [B-F1]: RunManager.run_active() TRUE after Continue")
	_ok(RM.current_day() == 2, "s2 C3 [B-F1]: day counter resumed at 2 (got %d)" % RM.current_day())
	_ok(int(CL.day) == 2, "s2 C4: Clock day 2 (world state loaded)")
	_ok(String(main.current_scene_path) == String(RM.LODGING_SCENE),
		"s2 C4: resumed into the checkpoint's lodging scene (got %s)" % String(main.current_scene_path))
	var P: Node = root.get_node("/root/Progression")
	_ok(String(P.pathway()) == "hunter" and int(P.sequence()) == 9,
		"s2 C4: pathway/sequence resumed (hunter Seq 9)")
	_ok(bool(RM.has_checkpoint()) and RM.checkpoint_day() == 2,
		"s2 C4: the in-memory checkpoint rebuilt from the save (day 2)")

	# --- C5: pause is eligible again (PauseMenu gates on run_active) ---------------------------
	var PM: Node = root.get_node_or_null("/root/PauseMenu")
	if PM != null:
		PM.open()
		_ok(bool(PM.is_open()), "s2 C5: pause menu opens during the resumed run")
		PM.resume()
	else:
		_ok(false, "s2 C5: PauseMenu autoload present")

	# --- C6/C7: the codex ledger crossed the process boundary AND still records live -----------
	var knowledge: Dictionary = RM._run_knowledge
	_ok(knowledge.has("adversary:butcher_human"),
		"s2 C6 [B-F2]: session 1's learned fact (adversary:butcher_human) survived the resume")
	var EB: Node = root.get_node("/root/EventBus")
	EB.emit_event("agent_downed", {"target": "sable_wren"})
	await process_frame
	knowledge = RM._run_knowledge
	_ok(knowledge.has("adversary:wren_human"),
		"s2 C7: codex recording LIVE after resume (fresh downed Beyonder recorded)")

	# --- C8: nightly checkpoints continue -------------------------------------------------------
	var r: Dictionary = RM.rest_until_morning()
	_ok(bool(r.get("ok", false)) and RM.current_day() == 3 and RM.checkpoint_day() == 3,
		"s2 C8: the resumed run keeps checkpointing (rest -> day 3 checkpoint)")

	# --- C9: Ritual Night can arm and fire ------------------------------------------------------
	var M: Node = root.get_node("/root/Meters")
	M.set_meter("doom", 100.0)
	await process_frame
	var RN: Node = root.get_node("/root/RitualNight")
	_ok(bool(RM.ritual_night_reached()), "s2 C9: Doom 100 latched Ritual Night on the resumed run")
	_ok(bool(RN.active()), "s2 C9: the Ritual Night climax STAGED (RitualNight.active)")

	# --- C10 [B-F5]: a full run-end invalidates the save — no ghost Continue --------------------
	RM.end_run("lose")
	await process_frame
	await process_frame
	_ok(not bool(main.has_continue()),
		"s2 C10 [B-F5]: after the run ends, the stale save is gone — Continue not offered")
	_ok(bool(main.is_at_title()), "s2 C10: back at the title after the run end")
	var cont_btn2 := _find_button(main, "ContinueButton")
	_ok(cont_btn2 != null and cont_btn2.disabled, "s2 C10 [B-F5]: title Continue button greyed out")

	print("\n=== continue_probe_s2: %d passed, %d failed ===" % [_passed, _failed])
	quit(1 if _failed > 0 else 0)
