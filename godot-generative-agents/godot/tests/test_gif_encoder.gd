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


func _init_table(clear: int) -> Array:
	var t: Array = []
	for i in clear:
		t.append(PackedByteArray([i]))
	t.append(PackedByteArray())  # clear-code slot
	t.append(PackedByteArray())  # end-code slot
	return t


func _lzw_decode(data: PackedByteArray, min_code_size: int) -> PackedByteArray:
	# The spec-standard GIF LZW decoder: reads a code, outputs it, then appends the
	# entry for the PREVIOUS code (a one-code lag), and grows the read width when
	# the table reaches 2^code_size. This lag is exactly why the encoder must use
	# the "early change" +1 rule; matching giflib/PIL semantics is the point.
	var clear := 1 << min_code_size
	var end_code := clear + 1
	var cs := min_code_size + 1
	var table := _init_table(clear)
	var buf := 0
	var nb := 0
	var pos := 0
	var out := PackedByteArray()
	var prev := -1
	while true:
		while nb < cs and pos < data.size():
			buf |= data[pos] << nb
			pos += 1
			nb += 8
		if nb < cs:
			break
		var code := buf & ((1 << cs) - 1)
		buf >>= cs
		nb -= cs
		if code == clear:
			table = _init_table(clear)
			cs = min_code_size + 1
			prev = -1
			continue
		if code == end_code:
			break
		var entry: PackedByteArray
		if code < table.size():
			entry = table[code]
		elif code == table.size() and prev != -1:
			entry = table[prev].duplicate()
			entry.append(table[prev][0])
		else:
			break  # malformed stream
		out.append_array(entry)
		if prev != -1:
			var ne: PackedByteArray = table[prev].duplicate()
			ne.append(entry[0])
			table.append(ne)
			if table.size() == (1 << cs) and cs < 12:
				cs += 1
		prev = code
	return out


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
	# clear=4,end=5,cs=3. Emit clear,1,6,1,5 all @3 (next_code reaches 8, but the
	# GIF early-change rule bumps only at 2^cs+1=9, so no bump). LSB-packed 3-bit
	# codes -> [140, 83].
	var lzw := GifEncoder._lzw_compress(PackedByteArray([1, 1, 1, 1]), 2)
	_check(lzw == PackedByteArray([140, 83]),
		"LZW matches the hand-computed vector, got %s" % str(lzw))

	# --- LZW round-trips through a STANDARD GIF decoder across width bumps ---
	# The real correctness gate: encode a long, varied index run (min_code_size 2,
	# so codes cross 3->4->5->... bit widths repeatedly) and decode it with the
	# spec-standard decoder below (lagging entry-add, bump at table==2^cs). A
	# desynced width (the pre-#488-fix bug) makes this diverge, exactly as PIL/
	# Preview did. This is what a self-mirroring decoder could never catch.
	var src := PackedByteArray()
	for k in 400:
		src.append((k * k + 7 * k + (k >> 1)) % 4)
	var round := _lzw_decode(GifEncoder._lzw_compress(src, 2), 2)
	_check(round == src, "LZW round-trips through a standard decoder (%d/%d)" % [
		round.size(), src.size()])

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

	# --- ordered dithering is active: a flat colour region maps across >1 index ---
	# (also guards the encoder still COMPILES with the dither path -- a type-infer
	# slip there previously made the whole script fail to load. #488)
	var flat := Image.create(16, 16, false, Image.FORMAT_RGBA8)
	flat.fill(Color8(128, 128, 128))
	# A palette straddling the flat colour (two greys either side of 128): with no
	# dither every pixel would pick the same nearest entry; the Bayer bias pushes
	# some pixels to each, so a working dither yields both indices.
	var two_greys := PackedByteArray([120, 120, 120, 136, 136, 136])
	var flat_idx := GifEncoder._map_indices(flat, 16, 16, GifEncoder._build_lut(two_greys))
	var distinct := {}
	for v in flat_idx:
		distinct[v] = true
	_check(distinct.size() > 1, "dithering stipples a flat region across >1 palette index")

	if _failures == 0:
		print("test_gif_encoder: all checks passed")
	quit(1 if _failures > 0 else 0)
