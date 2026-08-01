extends SceneTree
## Headless unit tests for the visible replay-load error surface (issue #937).
## A corrupt or unfetchable replay used to abort with only a console
## push_error, leaving a silent empty campus. Run:
##   godot --headless --path godot-generative-agents/godot \
##     --script res://tests/test_replay_load_error.gd
## Exit 0 = all checks pass; 1 = at least one failed (run_smoke_test.sh runs
## this before the scene smoke).

var _failures := 0


func _check(cond: bool, name: String) -> void:
	if cond:
		print("  ok: %s" % name)
	else:
		_failures += 1
		push_error("FAIL: %s" % name)


func _find_label_with(node: Node, needle: String) -> bool:
	if node is Label and needle in (node as Label).text:
		return true
	for child in node.get_children():
		if _find_label_with(child, needle):
			return true
	return false


func _find_back_button(node: Node) -> Button:
	if node is Button:
		for conn in (node as Button).pressed.get_connections():
			if (conn["callable"] as Callable).get_method() == "_on_back_to_menu":
				return node
	for child in node.get_children():
		var found := _find_back_button(child)
		if found != null:
			return found
	return null


func _initialize() -> void:
	# load() at runtime, NOT a class-level preload: under --script the harness
	# compiles this file before the project's autoload registry exists, and
	# viewer.gd references autoloads (LaunchConfig) — a parse-time preload of
	# it deadlocks the run instead of failing.
	var viewer_script := load("res://scripts/viewer.gd") as GDScript
	# A bare instance, never added to the tree: _ready never runs, so the test
	# exercises only the error surface, not the whole viewer boot.
	var viewer: Node = viewer_script.new()

	# Guarded call: invoking a missing method on the instance would abort
	# _initialize before quit() and hang the harness instead of failing it.
	if not viewer.has_method("_show_replay_load_error"):
		_check(false, "viewer.gd defines _show_replay_load_error")
		viewer.free()
		quit(1)
		return

	# --- the surface: message on screen + a way back -------------------------
	viewer._show_replay_load_error("truncated at byte 12345")
	var panel := viewer.get_node_or_null("ReplayLoadError")
	_check(panel != null, "the error surface mounts as ReplayLoadError")
	if panel != null:
		_check(_find_label_with(panel, "truncated at byte 12345"),
			"the failure detail is readable on screen")
		_check(_find_back_button(panel) != null,
			"a button on the surface leads back to the menu (_on_back_to_menu)")

	# --- idempotence: a second failure must not stack a second panel ---------
	viewer._show_replay_load_error("second failure")
	var layers := 0
	for child in viewer.get_children():
		if child.name.begins_with("ReplayLoadError"):
			layers += 1
	_check(layers == 1, "a repeat failure reuses the surface (no stacking)")
	if panel != null:
		_check(_find_label_with(panel, "truncated at byte 12345"),
			"the first (root-cause) message is kept")

	viewer.free()

	# --- routing: every silent load-failure site calls the surface -----------
	# Source-level pins, matching the four #937 sites; keeps a refactor from
	# quietly reverting one path to console-only.
	var src := FileAccess.get_file_as_string("res://scripts/viewer.gd")
	_check("_show_replay_load_error(load_error)" in src,
		"guard failure (_load_replay_from_text) routes to the surface")
	_check('_show_replay_load_error("cannot open' in src,
		"desktop file-open failure routes to the surface")
	_check('_show_replay_load_error("fetching' in src,
		"web non-200 fetch routes to the surface")
	_check('_show_replay_load_error("could not start' in src,
		"web request-start failure routes to the surface")

	if _failures == 0:
		print("test_replay_load_error: all checks passed")
	quit(1 if _failures > 0 else 0)
