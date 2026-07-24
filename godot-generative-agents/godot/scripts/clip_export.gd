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
	# The fallback when run_ffmpeg() can't find an ffmpeg to run itself.
	var frames := dir.path_join("frame_%04d.png")
	var gif := dir.path_join("clip.gif")
	var mp4 := dir.path_join("clip.mp4")
	return ("# GIF:\nffmpeg -framerate 10 -i '%s' "
		+ "-vf 'split[a][b];[a]palettegen[p];[b][p]paletteuse' '%s'\n"
		+ "# MP4:\nffmpeg -framerate 10 -i '%s' -c:v libx264 -pix_fmt yuv420p '%s'") \
		% [frames, gif, frames, mp4]


static func _ffmpeg_bin() -> String:
	# Resolve an ffmpeg executable: PATH first (works when the viewer was launched
	# from a shell, e.g. run.sh), then the usual Homebrew/Unix locations for a
	# Finder-launched app whose PATH is minimal. "" if none run. Desktop only.
	var out: Array = []
	for bin in ["ffmpeg", "/opt/homebrew/bin/ffmpeg", "/usr/local/bin/ffmpeg", "/usr/bin/ffmpeg"]:
		if OS.execute(bin, ["-version"], out) == 0:
			return bin
	return ""


static func run_ffmpeg(dir: String, bin_override := "") -> Dictionary:
	# Encode the frame folder to BOTH clip.mp4 (libx264) and a high-quality
	# clip.gif (palettegen/paletteuse) in-place, so the user gets finished files
	# instead of a command to copy. Blocking (a few seconds). Returns
	# {ok:true, mp4, gif} or {ok:false, error} -- callers fall back to
	# ffmpeg_command() so it can still be run by hand. `bin_override` is for tests.
	var bin := bin_override if bin_override != "" else _ffmpeg_bin()
	if bin == "":
		return {"ok": false, "error": "ffmpeg not found"}
	var frames := dir.path_join("frame_%04d.png")
	var mp4 := dir.path_join("clip.mp4")
	var gif := dir.path_join("clip.gif")
	var log: Array = []
	var r_mp4 := OS.execute(bin, [
		"-y", "-framerate", "10", "-i", frames,
		"-c:v", "libx264", "-pix_fmt", "yuv420p", mp4], log, true)
	var r_gif := OS.execute(bin, [
		"-y", "-framerate", "10", "-i", frames,
		"-vf", "split[a][b];[a]palettegen[p];[b][p]paletteuse", gif], log, true)
	if r_mp4 != 0 or r_gif != 0:
		push_error("clip_export: ffmpeg failed (mp4=%d gif=%d)\n%s" % [
			r_mp4, r_gif, "\n".join(log)])
		return {"ok": false, "error": "ffmpeg exit mp4=%d gif=%d" % [r_mp4, r_gif]}
	return {
		"ok": true,
		"mp4": ProjectSettings.globalize_path(mp4),
		"gif": ProjectSettings.globalize_path(gif),
	}
