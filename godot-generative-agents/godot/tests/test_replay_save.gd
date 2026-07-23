extends SceneTree
## Headless unit tests for scripts/replay_save.gd (issue #716). Run:
##   godot --headless --path godot-generative-agents/godot \
##     --script res://tests/test_replay_save.gd

const ReplaySave := preload("res://scripts/replay_save.gd")

const TEST_DIR := "user://test_runs"

var _failures := 0


func _check(cond: bool, name: String) -> void:
	if cond:
		print("  ok: %s" % name)
	else:
		_failures += 1
		push_error("FAIL: %s" % name)


func _initialize() -> void:
	_check(ReplaySave.replay_name("run-2-live") == "penn_replay_run-2-live.json",
		"replay_name uses the run id")
	_check(ReplaySave.replay_name("") == "penn_replay.json",
		"blank id -> stable fallback name")
	_check(not ReplaySave.replay_name("a/b\\c").contains("/")
		and not ReplaySave.replay_name("a/b\\c").contains("\\"),
		"path separators in the id are neutralized")

	# save via dir_override writes the exact text and names by run id.
	var text := '{"meta":{},"frames":[],"memory_streams":{},"events":[],"wishes":[]}'
	var path := ReplaySave.save(text, "run-1-old", TEST_DIR)
	_check(path.ends_with("penn_replay_run-1-old.json"), "save names the file by run id")
	var rf := FileAccess.open(TEST_DIR.path_join("penn_replay_run-1-old.json"), FileAccess.READ)
	_check(rf != null and rf.get_as_text() == text, "save wrote the exact text verbatim")
	if rf != null:
		rf.close()

	_check(ReplaySave.save("", "run-1-old", TEST_DIR) == "",
		"empty text -> empty path (failure signaled)")
	_check(ReplaySave.save("   ", "run-1-old", TEST_DIR) == "",
		"whitespace-only text -> empty path")

	# Clean up scratch.
	DirAccess.remove_absolute(TEST_DIR.path_join("penn_replay_run-1-old.json"))
	DirAccess.remove_absolute(TEST_DIR)

	if _failures == 0:
		print("test_replay_save: all checks passed")
	quit(1 if _failures > 0 else 0)
