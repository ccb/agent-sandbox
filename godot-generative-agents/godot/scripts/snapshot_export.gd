extends RefCounted
## Saves gallery snapshots as PNGs (issue #488, the PNG half). Scene-free
## static helper (the replay_markers.gd pattern): snapshot_gallery.gd owns the
## buttons, this file owns the naming and the one IO seam. Desktop builds
## write into <Pictures>/penn-snapshots/ (names are deterministic, so
## re-saving a shot overwrites its earlier file); the web build hands the
## encoded PNG to the browser's download flow instead. Unit-tested headlessly
## (tests/test_snapshot_export.gd).

const DIR_NAME := "penn-snapshots"


static func file_name(index: int, label: String) -> String:
	# penn-snapshot-<index>-<slug>.png. The label is the capture's world-time
	# caption ("Jul 9, 2026, 09:12:00"); every non-alphanumeric run collapses
	# to one dash. Zero-padding keeps a directory listing in capture order.
	var re := RegEx.create_from_string("[^a-z0-9]+")
	var slug := re.sub(label.to_lower(), "-", true).lstrip("-").rstrip("-")
	if slug == "":
		return "penn-snapshot-%02d.png" % index
	return "penn-snapshot-%02d-%s.png" % [index, slug]


static func save(texture: Texture2D, index: int, label: String, dir_override := "") -> String:
	# Returns where the PNG went: an absolute path on desktop, the download's
	# file name on web, or "" on failure (with the reason pushed as an error).
	# `dir_override` (the headless test) replaces the whole directory choice
	# and forces the disk path even under a web build.
	if texture == null:
		push_error("snapshot_export: no texture to save")
		return ""
	var img := texture.get_image()
	if img == null:
		push_error("snapshot_export: texture has no image")
		return ""
	var fname := file_name(index, label)
	if dir_override == "" and OS.has_feature("web"):
		# The browser owns the destination; it surfaces its own download UI.
		JavaScriptBridge.download_buffer(img.save_png_to_buffer(), fname, "image/png")
		return fname
	var dir := dir_override
	if dir == "":
		var pictures := OS.get_system_dir(OS.SYSTEM_DIR_PICTURES)
		# Some minimal Linux setups report no Pictures dir; fall back to the
		# app's own user:// space rather than failing the save.
		dir = pictures.path_join(DIR_NAME) if pictures != "" else "user://snapshots"
	# make_dir_recursive_absolute returns OK even when the dir already exists.
	var err := DirAccess.make_dir_recursive_absolute(dir)
	if err != OK:
		push_error("snapshot_export: cannot create %s (%d)" % [dir, err])
		return ""
	var path := dir.path_join(fname)
	err = img.save_png(path)
	if err != OK:
		push_error("snapshot_export: save failed for %s (%d)" % [path, err])
		return ""
	# user:// paths globalize to a real OS path for display/Reveal; an already
	# absolute Pictures path passes through unchanged.
	return ProjectSettings.globalize_path(path)
