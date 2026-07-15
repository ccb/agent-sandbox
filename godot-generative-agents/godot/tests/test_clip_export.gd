extends SceneTree
## Headless unit tests for scripts/clip_export.gd (issue #488). Run:
##   godot --headless --path godot-generative-agents/godot \
##     --script res://tests/test_clip_export.gd

const ClipExport := preload("res://scripts/clip_export.gd")

const TEST_DIR := "user://test_clips"

var _failures := 0


func _check(cond: bool, name: String) -> void:
	if cond:
		print("  ok: %s" % name)
	else:
		_failures += 1
		push_error("FAIL: %s" % name)


func _initialize() -> void:
	_check(ClipExport.clip_base(3, 17) == "penn-clip-0003-0017",
		"clip_base zero-pads the span")

	# save_gif via dir_override writes the bytes verbatim.
	var bytes := PackedByteArray([1, 2, 3, 4, 5])
	var gpath := ClipExport.save_gif(bytes, 3, 17, TEST_DIR)
	_check(gpath.ends_with("penn-clip-0003-0017.gif"), "save_gif names the file by span")
	var rf := FileAccess.open(TEST_DIR.path_join("penn-clip-0003-0017.gif"), FileAccess.READ)
	_check(rf != null and rf.get_buffer(5) == bytes, "save_gif wrote the exact bytes")
	if rf != null:
		rf.close()
	_check(ClipExport.save_gif(PackedByteArray(), 0, 1, TEST_DIR) == "",
		"empty buffer -> empty path (failure signaled)")

	# save_frames writes one zero-padded PNG per image.
	var imgs: Array = []
	for _i in 3:
		var im := Image.create(2, 2, false, Image.FORMAT_RGBA8)
		im.fill(Color(0.3, 0.5, 0.7))
		imgs.append(im)
	var fdir := ClipExport.save_frames(imgs, 3, 17, TEST_DIR)
	_check(fdir != "", "save_frames returns the folder")
	var one := TEST_DIR.path_join("penn-clip-0003-0017").path_join("frame_0000.png")
	var two := TEST_DIR.path_join("penn-clip-0003-0017").path_join("frame_0002.png")
	_check(FileAccess.file_exists(one), "frame_0000.png exists")
	_check(FileAccess.file_exists(two), "frame_0002.png exists (zero-padded, capture order)")
	var back := Image.new()
	_check(back.load(ProjectSettings.globalize_path(one)) == OK and back.get_width() == 2,
		"a saved frame loads back at its size")

	# ffmpeg_command mentions the dir and both encoders.
	var cmd := ClipExport.ffmpeg_command("/tmp/penn-clip-0003-0017")
	_check(cmd.contains("ffmpeg") and cmd.contains("palettegen") and cmd.contains("libx264")
		and cmd.contains("/tmp/penn-clip-0003-0017"),
		"ffmpeg_command references the dir + GIF and MP4 recipes")

	# run_ffmpeg with a missing binary reports failure (not a crash), so the caller
	# can fall back to the printed command. Real ffmpeg output is a manual-
	# acceptance path -- CI and other machines may not have ffmpeg installed. The
	# ERROR line this prints is expected, not a test failure.
	var ff := ClipExport.run_ffmpeg(TEST_DIR, "/nonexistent/ffmpeg")
	_check(not ff.get("ok", true), "run_ffmpeg with a missing binary -> ok=false")

	# Clean up scratch.
	var d := DirAccess.open(TEST_DIR.path_join("penn-clip-0003-0017"))
	if d != null:
		for f in d.get_files():
			DirAccess.remove_absolute(TEST_DIR.path_join("penn-clip-0003-0017").path_join(f))
	DirAccess.remove_absolute(TEST_DIR.path_join("penn-clip-0003-0017"))
	DirAccess.remove_absolute(TEST_DIR.path_join("penn-clip-0003-0017.gif"))
	DirAccess.remove_absolute(TEST_DIR)

	if _failures == 0:
		print("test_clip_export: all checks passed")
	quit(1 if _failures > 0 else 0)
