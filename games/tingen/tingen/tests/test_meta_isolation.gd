extends SceneTree
## B3 (retro) — META-PROFILE ISOLATION harness. The test suite shares user:// with the LIVE game,
## and the meta tests used to reset_meta()/end_run() straight into the player's REAL
## user://meta.json — running the suite destroyed a real profile's codex/unlocks/currency.
##
## This harness stages a sentinel AS the real profile, drives every meta-WRITING seam the suite
## uses through the test-scoped redirect (RunManager.meta_path -> user://meta_test.json), and
## asserts the sentinel survives BYTE-IDENTICAL. RED before the redirect seam existed: the
## `set("meta_path", ...)` below was a silent no-op and reset_meta() wiped the sentinel.
##
## Run: godot --headless --path tingen -s tests/test_meta_isolation.gd
##
## The machine's true profile is backed up before the sentinel is staged and restored before the
## asserts, so this harness itself never harms a real profile either.

const TEST_SLOT := "user://meta_test.json"

var _passed: int = 0
var _failed: int = 0

func _init() -> void:
	await process_frame
	await process_frame

	var RM: Object = root.get_node("/root/RunManager")
	var real_path := String(RM.META_PATH)

	# Stage a SENTINEL as the player's real profile (backing up any true profile bytes first).
	var had_real := FileAccess.file_exists(real_path)
	var backup := ""
	if had_real:
		backup = FileAccess.get_file_as_string(real_path)
	var sentinel := JSON.stringify({"version": 1, "runs_played": 777, "unlocked_pathways": ["hermit"],
		"codex": [{"id": "ending:descent_stopped", "learned": "a real player's earned codex line"}],
		"meta_currency": 41}, "\t")
	var fw := FileAccess.open(real_path, FileAccess.WRITE)
	fw.store_string(sentinel)
	fw.close()

	# The redirect EVERY test harness applies before driving RunManager. Object.set() so the RED
	# state (no meta_path property) no-ops silently instead of crashing — the asserts catch it.
	RM.set("meta_path", TEST_SLOT)
	RM.reload_meta()

	# Drive every meta-WRITING seam the suite uses.
	RM.reset_meta()                                        # the test-profile wipe
	RM.start_run()                                         # _bump_meta_runs -> _save_meta
	RM.end_run("lose", {"outcome": "descent_complete"})    # _flush_meta_on_run_end -> _save_meta
	RM.reload_meta()                                       # the re-READ seam

	# Capture what the seams touched, scrub the ACTIVE slot, then restore the machine's true
	# profile BEFORE asserting — never leave the sentinel (or a wipe) behind on a real machine.
	var reads_test_slot := int(RM.meta_runs_played()) != 777
	var real_after := FileAccess.get_file_as_string(real_path) if FileAccess.file_exists(real_path) else ""
	var test_slot_written := FileAccess.file_exists(TEST_SLOT)
	RM.reset_meta()
	if had_real:
		var fr := FileAccess.open(real_path, FileAccess.WRITE)
		fr.store_string(backup)
		fr.close()
	else:
		DirAccess.remove_absolute(ProjectSettings.globalize_path(real_path))

	_ok(reads_test_slot,
		"meta READS come from the test slot, not the real profile (runs_played != the sentinel's 777)")
	_ok(real_after == sentinel,
		"the REAL user://meta.json survives the meta seams BYTE-IDENTICAL (was: reset_meta/end_run wiped it)")
	_ok(test_slot_written,
		"the meta writes landed in the test-scoped slot (user://meta_test.json) instead")

	print("\n=== meta_isolation: %d passed, %d failed ===" % [_passed, _failed])
	quit(1 if _failed > 0 else 0)

func _ok(cond: bool, label: String) -> void:
	if cond:
		_passed += 1
		print("  PASS  %s" % label)
	else:
		_failed += 1
		printerr("  FAIL  %s" % label)
