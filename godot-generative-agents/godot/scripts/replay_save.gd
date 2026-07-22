extends RefCounted
## File/download seam for a saved run's replay (issue #716) -- the clip_export.gd
## pattern one layer up: the caller fetches the replay JSON from the backend
## (GET /runs/{id}/replay); this decides where it lands. Desktop writes
## <Documents>/penn-runs/<name>.json and returns the absolute path; the web build
## hands the bytes to the browser's download flow. Headless-tested
## (tests/test_replay_save.gd).

const DIR_NAME := "penn-runs"


static func replay_name(run_id: String) -> String:
	# penn_replay_<run_id>.json. A blank id falls back to a stable name so a store
	# that didn't report an id still saves a re-openable file. Run ids are slugs
	# today, but neutralize path separators so a stray one can't create sub-dirs.
	var safe := run_id.strip_edges()
	if safe == "":
		return "penn_replay.json"
	safe = safe.replace("/", "_").replace("\\", "_")
	return "penn_replay_%s.json" % safe


static func _runs_dir(dir_override: String) -> String:
	if dir_override != "":
		return dir_override
	var docs := OS.get_system_dir(OS.SYSTEM_DIR_DOCUMENTS)
	return docs.path_join(DIR_NAME) if docs != "" else "user://runs"


static func save(text: String, run_id: String, dir_override := "") -> String:
	# Absolute path on desktop, download file name on web, "" on failure. The text
	# is written verbatim (byte-preserving): the caller passes the raw HTTP body so
	# the saved file stays byte-identical to the backend's build_replay output.
	if text.strip_edges() == "":
		push_error("replay_save: empty replay text")
		return ""
	var fname := replay_name(run_id)
	if dir_override == "" and OS.has_feature("web"):
		JavaScriptBridge.download_buffer(text.to_utf8_buffer(), fname, "application/json")
		return fname
	var dir := _runs_dir(dir_override)
	var err := DirAccess.make_dir_recursive_absolute(dir)
	if err != OK:
		push_error("replay_save: cannot create %s (%d)" % [dir, err])
		return ""
	var path := dir.path_join(fname)
	var f := FileAccess.open(path, FileAccess.WRITE)
	if f == null:
		push_error("replay_save: cannot open %s" % path)
		return ""
	f.store_string(text)
	f.close()
	return ProjectSettings.globalize_path(path)
