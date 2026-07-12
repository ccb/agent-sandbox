extends SceneTree
## M9 expected-value generator. Fills every `expected` field in
## agent-sidecar/cognition/combat_test_vectors.json by RUNNING the live GDScript combat
## implementations (via the SAME fill_* statics the runner uses — dump and verify can never
## drift), then writes `<vectors>.filled` beside the source. A post-pass (any JSON tool)
## may prettify int-valued floats; the runner compares numerically so formatting is free.
##
##   godot --headless --path tingen -s tests/dump_combat_vectors.gd
##
## NEVER hand-edit expected values: change the implementation (or the vector inputs), then
## regenerate and re-run both vector runners + the Yumina-side runner.

func _init() -> void:
	var Runner := load("res://tests/run_combat_vectors.gd")
	var path: String = Runner.vectors_path()
	var V: Dictionary = Runner.load_vectors()
	if V.is_empty():
		printerr("DUMP FAIL: could not load %s" % path)
		quit(1)
		return
	var filled: Dictionary = Runner.fill_all(V)
	var out_path := path + ".filled"
	var f := FileAccess.open(out_path, FileAccess.WRITE)
	if f == null:
		printerr("DUMP FAIL: cannot write %s" % out_path)
		quit(1)
		return
	f.store_string(JSON.stringify(filled, "  ", false, true) + "\n")
	f.close()
	print("DUMP OK: wrote %s" % out_path)
	quit(0)
