extends SceneTree
## Headless unit tests for scripts/snapshot_export.gd (issue #488). Run:
##   godot --headless --path godot-generative-agents/godot \
##     --script res://tests/test_snapshot_export.gd
## Exit 0 = all checks pass; run_smoke_test.sh runs this before the scene smoke
## and also greps for the success sentinel (Godot can exit 0 on a parse error).

const SnapshotExport := preload("res://scripts/snapshot_export.gd")

const TEST_DIR := "user://test_snapshots"

var _failures := 0


func _check(cond: bool, name: String) -> void:
	if cond:
		print("  ok: %s" % name)
	else:
		_failures += 1
		push_error("FAIL: %s" % name)


func _initialize() -> void:
	# --- file_name ---
	_check(SnapshotExport.file_name(3, "Jul 9, 2026, 09:12:00")
		== "penn-snapshot-03-jul-9-2026-09-12-00.png",
		"file_name slugs the world-time label")
	_check(SnapshotExport.file_name(3, "Jul 9, 2026, 09:12:00")
		== SnapshotExport.file_name(3, "Jul 9, 2026, 09:12:00"),
		"file_name is deterministic (re-save overwrites)")
	_check(SnapshotExport.file_name(0, "") == "penn-snapshot-00.png",
		"empty label -> index-only name")
	_check(SnapshotExport.file_name(12, "  ··weird—label!! ")
		== "penn-snapshot-12-weird-label.png",
		"non-alphanumeric runs collapse to single dashes, edges trimmed")

	# --- save(): a real end-to-end write via dir_override ---
	var img := Image.create(4, 4, false, Image.FORMAT_RGBA8)
	img.fill(Color(0.2, 0.6, 0.9))
	var tex := ImageTexture.create_from_image(img)
	var path := SnapshotExport.save(tex, 1, "Jul 9, 2026, 09:12:00", TEST_DIR)
	_check(path != "", "save returns a path")
	_check(path.ends_with("penn-snapshot-01-jul-9-2026-09-12-00.png"),
		"saved file carries the deterministic name")
	_check(FileAccess.file_exists(TEST_DIR.path_join(
		"penn-snapshot-01-jul-9-2026-09-12-00.png")), "the PNG exists on disk")
	var back := Image.new()
	_check(back.load(path) == OK and back.get_width() == 4,
		"the PNG loads back at the captured size")
	# The failure contract ("" + a console error). The ERROR line this prints
	# is expected output, not a test failure.
	_check(SnapshotExport.save(null, 2, "x", TEST_DIR) == "",
		"null texture -> empty path (failure signaled)")

	# Clean up the scratch dir so reruns start fresh.
	DirAccess.remove_absolute(TEST_DIR.path_join(
		"penn-snapshot-01-jul-9-2026-09-12-00.png"))
	DirAccess.remove_absolute(TEST_DIR)

	if _failures == 0:
		print("test_snapshot_export: all checks passed")
	quit(1 if _failures > 0 else 0)
