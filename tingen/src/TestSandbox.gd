@static_unload
extends Object
## N1 (sprint safety) — the HARNESS USER-DIR SANDBOX. The test suites share the ONE real
## app_userdata dir with the live game: every harness run used to stomp the developer's actual
## save.json / settings.json / hints_seen.json (audit finding E2 — a real player profile was
## mutated during audits). B3 (retro) had already made the META slot redirectable
## (RunManager.meta_path), but saves / settings / hints and every STANDALONE harness still hit
## the real user dir.
##
## `activate(root)` redirects EVERY persistent path the game writes into an isolated
## user://test_sandbox/<run>/ directory (one per harness process), and arms a WRITE GUARD:
## while the sandbox is active, the persistence seams (SaveManager / Settings / HintDirector /
## RunManager meta) call `guard_write(path)` before writing — a write outside the sandbox is
## REFUSED, push_error'd, and recorded in `violations`, which run_tests.gd asserts empty as its
## final test. So a stale-path test physically CANNOT touch the real profile.
##
## Usage (every harness, FIRST thing in _init after the autoload-settle frames):
##   preload("res://src/TestSandbox.gd").activate(root)
##
## NOT an autoload, no class_name: pure static helper, shared statics via the one preloaded
## GDScript resource. Inert in live play (`active` stays false; guard_write always allows).
## Engine-neutral: pure path plumbing, no NPC identity, never reaches combat resolution.

const SANDBOX_ROOT := "user://test_sandbox/"
## Engine-owned / non-profile subtrees the isolation snapshot ignores (the ENGINE writes logs and
## caches on every headless boot; they are not player-profile state and the game never reads them).
const SNAPSHOT_EXCLUDE: Array = ["test_sandbox", "logs", "shader_cache", "vulkan", "objectdb_snapshots"]
## Prune sandbox run dirs older than this (parallel harness processes each make one).
const PRUNE_AGE_SEC: int = 24 * 3600

static var active: bool = false
static var dir: String = ""
static var violations: PackedStringArray = PackedStringArray()

## Redirect every persistent seam into a fresh per-process sandbox dir. Idempotent.
## Returns the sandbox dir (user:// form).
static func activate(root: Node) -> String:
	if active:
		return dir
	_prune_old_runs()
	dir = SANDBOX_ROOT + "run_%d_%d/" % [OS.get_process_id(), Time.get_ticks_usec()]
	DirAccess.make_dir_recursive_absolute(ProjectSettings.globalize_path(dir))
	active = true

	# META (RunManager) — the B3 redirect, now into the sandbox; fresh defaults for determinism.
	var rm := root.get_node_or_null("/root/RunManager")
	if rm != null:
		rm.set("meta_path", path("meta_test.json"))
		rm.call("reload_meta")
	# RUN SAVE (SaveManager) — was the E2 smoking gun: nightly checkpoints overwrote the real save.json.
	var sm := root.get_node_or_null("/root/SaveManager")
	if sm != null:
		sm.set("save_path", path("save.json"))
	# SETTINGS — reset to defaults so no test depends on the developer's cosmetic preferences.
	var st := root.get_node_or_null("/root/Settings")
	if st != null:
		st.set("settings_path", path("settings.json"))
		if st.has_method("reset_defaults"):
			st.call("reset_defaults")
	# HINTS — clear_for_test() used to DELETE the real user://hints_seen.json; now sandbox-scoped.
	var hd := root.get_node_or_null("/root/HintDirector")
	if hd != null:
		hd.set("persist_path", path("hints_seen.json"))
		if hd.has_method("clear_for_test"):
			hd.call("clear_for_test")
	# PLAYLOG — flushes into the repo's playlogs/ when a scene arms it; harnesses flush here instead.
	var pl := root.get_node_or_null("/root/PlayLog")
	if pl != null:
		pl.set("dir_override", ProjectSettings.globalize_path(path("playlogs")))
	return dir

## Sandbox-scoped path for a file name (falls back to plain user:// when inactive, so callers
## can use it unconditionally).
static func path(name: String) -> String:
	return (dir + name) if active else ("user://" + name)

## The WRITE GUARD: persistence seams call this before writing their target path. While the
## sandbox is active, any target outside user://test_sandbox/ is refused + recorded.
static func guard_write(p: String) -> bool:
	if not active:
		return true
	var target := ProjectSettings.globalize_path(p)
	if target.begins_with(ProjectSettings.globalize_path(SANDBOX_ROOT)):
		return true
	violations.append(p)
	push_error("TestSandbox VIOLATION: refused persistent write outside the sandbox: %s" % p)
	return false

## Snapshot the REAL user dir (path -> md5), excluding SNAPSHOT_EXCLUDE subtrees. run_tests.gd
## captures this before any test runs and asserts byte-identity as its final test.
static func snapshot_user_dir() -> Dictionary:
	var out: Dictionary = {}
	_walk("user://", out)
	return out

static func _walk(p: String, out: Dictionary) -> void:
	var d := DirAccess.open(p)
	if d == null:
		return
	d.list_dir_begin()
	var name := d.get_next()
	while name != "":
		if name != "." and name != "..":
			var child := p.path_join(name)
			if d.current_is_dir():
				# The excluded subtrees live at the user:// ROOT (engine caches + the sandbox itself).
				if not (p == "user://" and SNAPSHOT_EXCLUDE.has(name)):
					_walk(child, out)
			else:
				out[child] = FileAccess.get_md5(child)
		name = d.get_next()
	d.list_dir_end()

## Human-readable diff of two snapshots (for the failure message).
static func snapshot_diff(before: Dictionary, after: Dictionary) -> String:
	var lines: PackedStringArray = PackedStringArray()
	for k in before.keys():
		if not after.has(k):
			lines.append("DELETED  %s" % k)
		elif after[k] != before[k]:
			lines.append("CHANGED  %s" % k)
	for k in after.keys():
		if not before.has(k):
			lines.append("CREATED  %s" % k)
	return "; ".join(lines)

## Prune stale sandbox run dirs left by earlier harness processes (age-gated so PARALLEL
## harness runs never delete each other's live sandboxes).
static func _prune_old_runs() -> void:
	var root_abs := ProjectSettings.globalize_path(SANDBOX_ROOT)
	var d := DirAccess.open(root_abs)
	if d == null:
		return
	var now := int(Time.get_unix_time_from_system())
	d.list_dir_begin()
	var name := d.get_next()
	while name != "":
		if name != "." and name != ".." and d.current_is_dir():
			var sub := root_abs.path_join(name)
			if now - int(FileAccess.get_modified_time(sub)) > PRUNE_AGE_SEC:
				_rm_rf(sub)
		name = d.get_next()
	d.list_dir_end()

static func _rm_rf(abs_path: String) -> void:
	var d := DirAccess.open(abs_path)
	if d == null:
		return
	d.list_dir_begin()
	var name := d.get_next()
	while name != "":
		if name != "." and name != "..":
			if d.current_is_dir():
				_rm_rf(abs_path.path_join(name))
			else:
				DirAccess.remove_absolute(abs_path.path_join(name))
		name = d.get_next()
	d.list_dir_end()
	DirAccess.remove_absolute(abs_path)
