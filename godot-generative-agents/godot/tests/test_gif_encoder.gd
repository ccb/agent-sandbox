extends SceneTree
## Headless unit tests for scripts/gif_encoder.gd (issue #488). Run:
##   godot --headless --path godot-generative-agents/godot \
##     --script res://tests/test_gif_encoder.gd
## Exit 0 = all checks pass. External-viewer correctness (does Preview/Chrome
## open the GIF?) is checked by hand in acceptance; here we pin the byte
## structure, the palette bound, and a hand-computed LZW vector.

const GifEncoder := preload("res://scripts/gif_encoder.gd")

var _failures := 0


func _check(cond: bool, name: String) -> void:
	if cond:
		print("  ok: %s" % name)
	else:
		_failures += 1
		push_error("FAIL: %s" % name)


func _count_pairs(buf: PackedByteArray, a: int, b: int) -> int:
	var n := 0
	for i in range(buf.size() - 1):
		if buf[i] == a and buf[i + 1] == b:
			n += 1
	return n


func _initialize() -> void:
	# --- median cut collapses a >256-colour set to <=256 ---
	var samples := PackedInt32Array()
	for k in 500:
		samples.append(((k * 131) & 0xFF) << 16 | ((k * 71) & 0xFF) << 8 | ((k * 37) & 0xFF))
	var pal := GifEncoder._median_cut(samples, 256)
	_check(pal.size() % 3 == 0, "palette is whole RGB triples")
	_check(pal.size() / 3 <= 256, "palette collapses to <=256 colours")
	_check(pal.size() / 3 == 256, "500 distinct samples fill the 256-colour palette")

	# --- LZW: a hand-computed vector (indices [1,1,1,1], min_code_size 2) ---
	# clear=4,end=5. Emit clear@3, 1@3, 6@3, 1@4, 5@4 -> LSB-packed -> [140,163,0].
	var lzw := GifEncoder._lzw_compress(PackedByteArray([1, 1, 1, 1]), 2)
	_check(lzw == PackedByteArray([140, 163, 0]),
		"LZW matches the hand-computed vector, got %s" % str(lzw))

	# --- encode(): structural bytes of a real 2-frame GIF ---
	var f0 := Image.create(2, 2, false, Image.FORMAT_RGBA8)
	f0.fill(Color(0.9, 0.1, 0.1))
	var f1 := Image.create(2, 2, false, Image.FORMAT_RGBA8)
	f1.fill(Color(0.1, 0.2, 0.9))
	var gif := GifEncoder.encode([f0, f1], 10)
	_check(gif.size() > 0, "encode returns a non-empty buffer")
	_check(gif.slice(0, 6) == "GIF89a".to_ascii_buffer(), "starts with GIF89a")
	_check((gif[10] & 0x80) != 0, "global colour table flag set")
	_check(gif[gif.size() - 1] == 0x3B, "ends with the 0x3B trailer")
	_check(_count_pairs(gif, 0x21, 0xF9) == 2, "one graphic-control block per frame")

	_check(GifEncoder.encode([], 10).is_empty(), "no frames -> empty buffer (failure signaled)")

	if _failures == 0:
		print("test_gif_encoder: all checks passed")
	quit(1 if _failures > 0 else 0)
