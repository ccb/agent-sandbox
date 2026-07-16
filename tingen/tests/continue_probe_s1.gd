extends SceneTree
## N3 — CONTINUE PROBE, SESSION 1 of 2 (a TOOL, not an auto-run test; see tests/continue_probe.sh).
## The first half of the TWO-PROCESS cross-session Continue proof: this process plays the part of
## "the player's first sitting" — boot the REAL Main.tscn, New Run, learn a codex fact in the live
## world, rest to day 2 (the nightly safe-house checkpoint mirrors to disk), then QUIT. A separate
## fresh Godot process (tests/continue_probe_s2.gd) then Continues from that disk save and asserts
## the resumed run is a first-class live run (B-F1/B-F2/B-F5).
##
## The save/meta slots are FIXED paths under user://test_sandbox/continue_probe/ so BOTH processes
## share them while the TestSandbox write guard still protects the real profile. Session 1 wipes
## the shared dir first, so every probe run starts from a fresh cross-session profile.
## Run:  godot --headless --path tingen -s tests/continue_probe_s1.gd

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

func _init() -> void:
	await process_frame
	await process_frame
	# Sandbox first (never the real profile), then pin the save/meta slots to the FIXED shared dir
	# (still inside the sandbox root, so the write guard allows them and both processes agree).
	preload("res://src/TestSandbox.gd").activate(root)
	var abs_dir := ProjectSettings.globalize_path(SHARED_DIR)
	if DirAccess.dir_exists_absolute(abs_dir):
		for f in DirAccess.get_files_at(abs_dir):
			DirAccess.remove_absolute(abs_dir.path_join(f))
	DirAccess.make_dir_recursive_absolute(abs_dir)
	var SM: Node = root.get_node("/root/SaveManager")
	var RM: Node = root.get_node("/root/RunManager")
	SM.save_path = SHARED_SAVE
	RM.meta_path = SHARED_META
	RM.reload_meta()

	print("[s1] boot the REAL Main.tscn (BootController) and start a New Run")
	var main: Node = (load("res://scenes/Main.tscn") as PackedScene).instantiate()
	root.add_child(main)
	await process_frame
	await process_frame
	_ok(main.has_method("start_new_run"), "boot controller mounted (start_new_run present)")
	main.start_new_run()
	await process_frame
	await process_frame
	_ok(bool(RM.run_active()), "s1: run live after New Run")
	_ok(RM.current_day() == 1, "s1: day 1 after New Run")

	# Learn a codex fact through the REAL ear (a downed Beyonder) so the run knowledge ledger is
	# non-empty when the nightly save is written — session 2 must find it again after Continue.
	var EB: Node = root.get_node("/root/EventBus")
	EB.emit_event("agent_downed", {"target": "bram_kell"})
	await process_frame
	var knowledge: Dictionary = RM._run_knowledge
	_ok(knowledge.has("adversary:butcher_human"),
		"s1: downing the butcher recorded adversary:butcher_human into the run knowledge ledger")

	# Rest to day 2 — the nightly safe-house checkpoint (which mirrors to the disk save).
	var r: Dictionary = RM.rest_until_morning()
	_ok(bool(r.get("ok", false)), "s1: rest_until_morning() ok")
	_ok(RM.current_day() == 2, "s1: day 2 after the rest (got %d)" % RM.current_day())
	_ok(bool(RM.has_checkpoint()), "s1: nightly checkpoint taken")
	_ok(SM.has_save(), "s1: the nightly checkpoint mirrored to the disk save")

	# B-F2 — the save payload itself must carry the run session: a run_manager block with the day,
	# the live flag, and the run knowledge, so a fresh process can resume more than just the world.
	var parsed: Variant = JSON.parse_string(FileAccess.get_file_as_string(SHARED_SAVE))
	var data: Dictionary = parsed if parsed is Dictionary else {}
	var rm_block: Variant = data.get("run_manager")
	_ok(rm_block is Dictionary, "s1 [B-F2]: save payload has a run_manager block")
	if rm_block is Dictionary:
		_ok(int((rm_block as Dictionary).get("day", -1)) == 2,
			"s1 [B-F2]: run_manager block carries day 2")
		_ok(bool((rm_block as Dictionary).get("run_active", false)),
			"s1 [B-F2]: run_manager block carries run_active=true")
		var kn: Variant = (rm_block as Dictionary).get("knowledge", [])
		_ok(kn is Array and (kn as Array).has("adversary:butcher_human"),
			"s1 [B-F2]: run_manager block carries the run knowledge ledger")

	print("[s1] quitting mid-run (the cross-session seam) — day=%d doom=%.1f" %
		[RM.current_day(), root.get_node("/root/Meters").get_meter("doom")])
	print("\n=== continue_probe_s1: %d passed, %d failed ===" % [_passed, _failed])
	quit(1 if _failed > 0 else 0)
