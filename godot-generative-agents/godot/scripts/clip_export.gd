extends RefCounted
## File/download seam for exported clips (issue #488) -- the snapshot_export.gd
## pattern one layer up: gif_encoder.gd makes the bytes, this decides where they
## land. Desktop writes <Pictures>/penn-clips/ (a GIF, or a per-clip frame
## folder); the web build hands the GIF to the browser download flow (frame
## folders are desktop-only). Headless-tested (tests/test_clip_export.gd).

const DIR_NAME := "penn-clips"


static func clip_base(start: int, end: int) -> String:
	# penn-clip-<start>-<end>, zero-padded so a directory listing sorts by span.
	return "penn-clip-%04d-%04d" % [start, end]


static func _clips_dir(dir_override: String) -> String:
	if dir_override != "":
		return dir_override
	var pics := OS.get_system_dir(OS.SYSTEM_DIR_PICTURES)
	return pics.path_join(DIR_NAME) if pics != "" else "user://clips"


static func save_gif(bytes: PackedByteArray, start: int, end: int, dir_override := "") -> String:
	# Absolute path on desktop, download file name on web, "" on failure.
	if bytes.is_empty():
		push_error("clip_export: empty GIF buffer")
		return ""
	var fname := clip_base(start, end) + ".gif"
	if dir_override == "" and OS.has_feature("web"):
		JavaScriptBridge.download_buffer(bytes, fname, "image/gif")
		return fname
	var dir := _clips_dir(dir_override)
	var err := DirAccess.make_dir_recursive_absolute(dir)
	if err != OK:
		push_error("clip_export: cannot create %s (%d)" % [dir, err])
		return ""
	var path := dir.path_join(fname)
	var f := FileAccess.open(path, FileAccess.WRITE)
	if f == null:
		push_error("clip_export: cannot open %s" % path)
		return ""
	f.store_buffer(bytes)
	f.close()
	return ProjectSettings.globalize_path(path)


static func make_frame_dir(start: int, end: int, dir_override := "") -> String:
	# Create (and return) the per-clip frame folder; "" on failure.
	var dir := _clips_dir(dir_override).path_join(clip_base(start, end))
	var err := DirAccess.make_dir_recursive_absolute(dir)
	if err != OK:
		push_error("clip_export: cannot create %s (%d)" % [dir, err])
		return ""
	return dir


static func save_frame(img: Image, dir: String, index: int) -> bool:
	# Write one frame_NNNN.png into an already-created clip dir.
	var path := dir.path_join("frame_%04d.png" % index)
	var err := img.save_png(path)
	if err != OK:
		push_error("clip_export: frame save failed %s (%d)" % [path, err])
		return false
	return true


static func save_frames(frames: Array, start: int, end: int, dir_override := "") -> String:
	# Batch wrapper (used by the headless test): make the dir, write every frame
	# in capture order, return the globalized dir or "".
	var dir := make_frame_dir(start, end, dir_override)
	if dir == "":
		return ""
	for i in frames.size():
		if not save_frame(frames[i], dir, i):
			return ""
	return ProjectSettings.globalize_path(dir)


static func ffmpeg_command(dir: String) -> String:
	# Ready-to-paste ffmpeg lines turning the frame folder into a GIF or an MP4.
	var frames := dir.path_join("frame_%04d.png")
	var gif := dir.path_join("clip.gif")
	var mp4 := dir.path_join("clip.mp4")
	return ("# GIF:\nffmpeg -framerate 10 -i '%s' "
		+ "-vf 'split[a][b];[a]palettegen[p];[b][p]paletteuse' '%s'\n"
		+ "# MP4:\nffmpeg -framerate 10 -i '%s' -c:v libx264 -pix_fmt yuv420p '%s'") \
		% [frames, gif, frames, mp4]
