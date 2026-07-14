extends RefCounted
## Pure animated-GIF encoder (issue #488, clip export). Bytes in -> bytes out:
## an Array of Image (all the same size) + a per-frame delay -> a GIF89a
## PackedByteArray. No IO, no scene -- scripts/clip_export.gd owns the file/
## download seam, the way snapshot_export.gd does for PNGs. Godot ships no video
## encoder, so we build the GIF ourselves: ONE global median-cut palette shared
## across every frame (a per-frame palette flickers), nearest-colour mapping via
## a 15-bit lookup cube (a per-pixel 256-way scan is too slow in GDScript), then
## GIF's variable-width LZW. Encoding is O(pixels): a long, wide clip takes a few
## seconds. Headless-tested (tests/test_gif_encoder.gd); open a real GIF in a
## viewer to confirm external decoders accept it.

const MAX_COLORS := 256
const SAMPLE_CAP := 16384  # palette is built from at most this many sampled pixels


static func encode(frames: Array, delay_cs: int) -> PackedByteArray:
	if frames.is_empty():
		push_error("gif_encoder: no frames")
		return PackedByteArray()
	# Normalise to RGBA8 so the 4-bytes-per-pixel indexing below holds.
	var norm: Array = []
	for f in frames:
		var img: Image = f
		if img.get_format() != Image.FORMAT_RGBA8:
			img = img.duplicate()
			img.convert(Image.FORMAT_RGBA8)
		norm.append(img)
	var w: int = norm[0].get_width()
	var h: int = norm[0].get_height()
	if w <= 0 or h <= 0 or w > 65535 or h > 65535:
		push_error("gif_encoder: bad frame size %dx%d" % [w, h])
		return PackedByteArray()

	var samples := _collect_samples(norm, w, h)
	var palette := _median_cut(samples, MAX_COLORS)
	var color_count := palette.size() / 3
	var bits := 1
	while (1 << bits) < color_count:
		bits += 1
	var min_code_size: int = maxi(2, bits)
	palette = _pad_palette(palette, 1 << min_code_size)
	var lut := _build_lut(palette)

	var buf := PackedByteArray()
	_append_header(buf, w, h, palette, min_code_size)
	for frame in norm:
		var indices := _map_indices(frame, w, h, lut)
		_append_frame(buf, w, h, indices, delay_cs, min_code_size)
	buf.append(0x3B)  # trailer
	return buf


# --- palette (median cut) --------------------------------------------------

static func _collect_samples(frames: Array, w: int, h: int) -> PackedInt32Array:
	# One packed RGB int (r<<16|g<<8|b) per sampled pixel across all frames.
	var total := w * h * frames.size()
	var stride: int = maxi(1, total / SAMPLE_CAP)
	var out := PackedInt32Array()
	var counter := 0
	for frame in frames:
		var data: PackedByteArray = frame.get_data()
		for i in w * h:
			if counter % stride == 0:
				var o := i * 4
				out.append((data[o] << 16) | (data[o + 1] << 8) | data[o + 2])
			counter += 1
	return out


static func _median_cut(samples: PackedInt32Array, max_colors: int) -> PackedByteArray:
	var palette := PackedByteArray()
	if samples.is_empty():
		palette.append_array([0, 0, 0])
		return palette
	var boxes: Array = [samples]
	while boxes.size() < max_colors:
		var best := -1
		var best_range := -1
		var best_channel := 0
		for bi in boxes.size():
			var box: PackedInt32Array = boxes[bi]
			if box.size() < 2:
				continue
			var rng := _channel_ranges(box)
			for ch in 3:
				if rng[ch] > best_range:
					best_range = rng[ch]
					best = bi
					best_channel = ch
		if best == -1:
			break  # nothing left to split
		var box: PackedInt32Array = boxes[best]
		var sorted_box := _sort_by_channel(box, best_channel)
		var mid := sorted_box.size() / 2
		boxes[best] = sorted_box.slice(0, mid)
		boxes.append(sorted_box.slice(mid))
	for box in boxes:
		palette.append_array(_average_color(box))
	return palette


static func _channel_ranges(box: PackedInt32Array) -> Array:
	var lo := [255, 255, 255]
	var hi := [0, 0, 0]
	for c in box:
		var v := [(c >> 16) & 255, (c >> 8) & 255, c & 255]
		for ch in 3:
			lo[ch] = mini(lo[ch], v[ch])
			hi[ch] = maxi(hi[ch], v[ch])
	return [hi[0] - lo[0], hi[1] - lo[1], hi[2] - lo[2]]


static func _sort_by_channel(box: PackedInt32Array, ch: int) -> PackedInt32Array:
	var shift := (2 - ch) * 8  # ch 0=R (>>16), 1=G (>>8), 2=B (>>0)
	var arr := Array(box)
	arr.sort_custom(func(a: int, b: int) -> bool:
		return ((a >> shift) & 255) < ((b >> shift) & 255))
	var out := PackedInt32Array()
	out.resize(arr.size())
	for i in arr.size():
		out[i] = arr[i]
	return out


static func _average_color(box: PackedInt32Array) -> PackedByteArray:
	if box.is_empty():
		return PackedByteArray([0, 0, 0])
	var s := [0, 0, 0]
	for c in box:
		s[0] += (c >> 16) & 255
		s[1] += (c >> 8) & 255
		s[2] += c & 255
	var n := box.size()
	return PackedByteArray([s[0] / n, s[1] / n, s[2] / n])


static func _pad_palette(palette: PackedByteArray, entries: int) -> PackedByteArray:
	var out := palette.duplicate()
	for _i in range(out.size() / 3, entries):
		out.append_array([0, 0, 0])
	return out


static func _build_lut(palette: PackedByteArray) -> PackedByteArray:
	# 15-bit RGB (5 bits/channel) -> nearest palette index. Built once (32768*256
	# ops); then per-pixel mapping is a single array lookup.
	var count := palette.size() / 3
	var lut := PackedByteArray()
	lut.resize(32768)
	for key in 32768:
		var r := ((key >> 10) & 31) << 3
		var g := ((key >> 5) & 31) << 3
		var b := (key & 31) << 3
		var best := 0
		var best_d := 1 << 30
		for pi in count:
			var o := pi * 3
			var dr := r - palette[o]
			var dg := g - palette[o + 1]
			var db := b - palette[o + 2]
			var d := dr * dr + dg * dg + db * db
			if d < best_d:
				best_d = d
				best = pi
		lut[key] = best
	return lut


static func _map_indices(frame: Image, w: int, h: int, lut: PackedByteArray) -> PackedByteArray:
	var data: PackedByteArray = frame.get_data()
	var out := PackedByteArray()
	out.resize(w * h)
	for i in w * h:
		var o := i * 4
		var key := ((data[o] >> 3) << 10) | ((data[o + 1] >> 3) << 5) | (data[o + 2] >> 3)
		out[i] = lut[key]
	return out


# --- GIF assembly ----------------------------------------------------------

static func _u16le(buf: PackedByteArray, v: int) -> void:
	buf.append(v & 0xFF)
	buf.append((v >> 8) & 0xFF)


static func _append_header(buf: PackedByteArray, w: int, h: int,
		palette: PackedByteArray, min_code_size: int) -> void:
	buf.append_array("GIF89a".to_ascii_buffer())
	_u16le(buf, w)
	_u16le(buf, h)
	# packed: GCT flag(1)=1 | colour resolution(3)=111 | sort(1)=0 | GCT size(3).
	# GCT holds 2^(size+1) entries, so size = min_code_size - 1 -> 2^min_code_size.
	buf.append(0xF0 | ((min_code_size - 1) & 0x07))
	buf.append(0x00)  # background colour index
	buf.append(0x00)  # pixel aspect ratio
	buf.append_array(palette)
	# Netscape 2.0 application extension: loop forever.
	buf.append(0x21)
	buf.append(0xFF)
	buf.append(0x0B)
	buf.append_array("NETSCAPE2.0".to_ascii_buffer())
	buf.append(0x03)
	buf.append(0x01)
	_u16le(buf, 0)    # loop count 0 = infinite
	buf.append(0x00)  # block terminator


static func _append_frame(buf: PackedByteArray, w: int, h: int,
		indices: PackedByteArray, delay_cs: int, min_code_size: int) -> void:
	# Graphic Control Extension (frame delay).
	buf.append(0x21)
	buf.append(0xF9)
	buf.append(0x04)
	buf.append(0x00)         # packed: no transparency, no disposal
	_u16le(buf, delay_cs)
	buf.append(0x00)         # transparent colour index (unused)
	buf.append(0x00)         # block terminator
	# Image Descriptor.
	buf.append(0x2C)
	_u16le(buf, 0)
	_u16le(buf, 0)
	_u16le(buf, w)
	_u16le(buf, h)
	buf.append(0x00)         # no local colour table
	# LZW image data.
	buf.append(min_code_size)
	_append_subblocks(buf, _lzw_compress(indices, min_code_size))


static func _append_subblocks(buf: PackedByteArray, data: PackedByteArray) -> void:
	var i := 0
	while i < data.size():
		var chunk: int = mini(255, data.size() - i)
		buf.append(chunk)
		buf.append_array(data.slice(i, i + chunk))
		i += chunk
	buf.append(0x00)  # block terminator


# --- LZW -------------------------------------------------------------------

static func _lzw_compress(indices: PackedByteArray, min_code_size: int) -> PackedByteArray:
	return _pack_codes(_lzw_codes(indices, min_code_size))


static func _lzw_codes(indices: PackedByteArray, min_code_size: int) -> Array:
	# GIF variable-width LZW. Each element is {"code": int, "width": int}; the
	# width is the code size in force when that code is emitted.
	var clear_code := 1 << min_code_size
	var end_code := clear_code + 1
	var code_size := min_code_size + 1
	var next_code := end_code + 1
	var dict := {}
	var out: Array = [{"code": clear_code, "width": code_size}]
	if indices.is_empty():
		out.append({"code": end_code, "width": code_size})
		return out
	var prefix := indices[0]
	for idx in range(1, indices.size()):
		var k := indices[idx]
		var key := "%d,%d" % [prefix, k]
		if dict.has(key):
			prefix = dict[key]
		else:
			out.append({"code": prefix, "width": code_size})
			dict[key] = next_code
			next_code += 1
			if next_code == (1 << code_size) and code_size < 12:
				code_size += 1
			if next_code == 4096:
				out.append({"code": clear_code, "width": code_size})
				dict = {}
				code_size = min_code_size + 1
				next_code = end_code + 1
			prefix = k
	out.append({"code": prefix, "width": code_size})
	out.append({"code": end_code, "width": code_size})
	return out


static func _pack_codes(codes: Array) -> PackedByteArray:
	# Pack codes LSB-first into a byte stream.
	var out := PackedByteArray()
	var bit_buffer := 0
	var bit_count := 0
	for entry in codes:
		bit_buffer |= int(entry["code"]) << bit_count
		bit_count += int(entry["width"])
		while bit_count >= 8:
			out.append(bit_buffer & 0xFF)
			bit_buffer >>= 8
			bit_count -= 8
	if bit_count > 0:
		out.append(bit_buffer & 0xFF)
	return out
