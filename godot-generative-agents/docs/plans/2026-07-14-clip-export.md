# Clip Export Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** From the baked-replay viewer, mark an in/out step span on the timeline and export it as a one-click animated GIF (desktop + web) or, on desktop, a numbered PNG folder plus a ready-to-run `ffmpeg` command.

**Architecture:** Two pure, headless-tested GDScript units — `gif_encoder.gd` (Array[Image] → GIF89a bytes: global median-cut palette, 15-bit nearest-colour LUT, variable-width LZW) and `clip_export.gd` (the file/download IO seam, mirroring `snapshot_export.gd`). The viewer gains a `_capture_span(from, to, sink)` coroutine that seeks each step offscreen (UI chrome hidden, playback paused) and hands the grab to a `sink` Callable; a GIF sink downscales+accumulates then encodes, a frames sink writes each PNG immediately. `agent_panel.gd`/`timeline_markers.gd` gain in/out markers, a span highlight, and Export controls.

**Tech Stack:** Godot 4.6 / GDScript. No new dependencies. Tests are `extends SceneTree` scripts run headlessly via `--script`, registered in `run_smoke_test.sh`.

## Global Constraints

- **Targets `godot-ga-main`** (godot-only change). Branch `feat/clip-export-488` (already created off `godot-ga-main`).
- **Baked-replay only.** Live mode is out of scope (filed as #548). Every entry point guards `if _is_live: return`.
- **No new dependencies**, no engine/`text_adventure_games/` or backend changes, no changes to `snapshot_export.gd` / `snapshot_gallery.gd` / the sim / the `.tmj`.
- **Web build:** GIF via `JavaScriptBridge.download_buffer`; the PNG-frames export is desktop-only, gated behind `OS.has_feature("web")` exactly like the gallery's "Save all".
- **Test convention:** each test `extends SceneTree`, defines `_check(cond, name)`, prints the sentinel `"<test_name>: all checks passed"` on success, and calls `quit(1 if _failures > 0 else 0)`. Register every new test in `godot-generative-agents/run_smoke_test.sh` with the `| tee /dev/stderr | grep -q "all checks passed"` idiom.
- **New `.gd` files generate a committed `.uid`** on first import — commit the `.uid` alongside the script (the repo tracks them).
- **Commits** end with `Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>`. Run all git from the repo root (`/Users/yh/Documents/GitHub/agent-sandbox`).
- **GIF defaults (no knobs):** 10 fps (`delay_cs = 10`), ≤640px wide, loop forever.
- Godot binary in commands below is `godot`; on macOS fall back to `/Applications/Godot.app/Contents/MacOS/Godot` (as `run_smoke_test.sh` does). `PROJECT=godot-generative-agents/godot`.

---

### Task 1: `gif_encoder.gd` — pure animated-GIF encoder

**Files:**
- Create: `godot-generative-agents/godot/scripts/gif_encoder.gd`
- Test: `godot-generative-agents/godot/tests/test_gif_encoder.gd`
- Modify: `godot-generative-agents/run_smoke_test.sh` (register the test)

**Interfaces:**
- Produces: `GifEncoder.encode(frames: Array, delay_cs: int) -> PackedByteArray` — `frames` is an Array of `Image`; returns a complete GIF89a buffer (empty + pushed error on bad input). Internal statics used by the test: `_median_cut(samples: PackedInt32Array, max_colors: int) -> PackedByteArray` and `_lzw_compress(indices: PackedByteArray, min_code_size: int) -> PackedByteArray`.

- [ ] **Step 1: Write the failing test**

Create `godot-generative-agents/godot/tests/test_gif_encoder.gd`:

```gdscript
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
```

- [ ] **Step 2: Run test to verify it fails**

Run: `godot --headless --path godot-generative-agents/godot --script res://tests/test_gif_encoder.gd`
Expected: FAIL — `gif_encoder.gd` does not exist (parse/preload error), no `"all checks passed"`.

- [ ] **Step 3: Write the encoder**

Create `godot-generative-agents/godot/scripts/gif_encoder.gd`:

```gdscript
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
		var data := frame.get_data()
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
	var data := frame.get_data()
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
```

- [ ] **Step 4: Run test to verify it passes**

Run: `godot --headless --path godot-generative-agents/godot --script res://tests/test_gif_encoder.gd 2>&1 | tail -20`
Expected: every `ok:` line, then `test_gif_encoder: all checks passed`, exit 0.

- [ ] **Step 5: Register the test in the smoke runner**

In `godot-generative-agents/run_smoke_test.sh`, after the `test_snapshot_export.gd` block (the last unit-test line before the `exec` line), add:

```bash
"$GODOT" --headless --path "$PROJECT_DIR" --script res://tests/test_gif_encoder.gd 2>&1 \
  | tee /dev/stderr | grep -q "all checks passed"
```

- [ ] **Step 6: Commit**

```bash
cd /Users/yh/Documents/GitHub/agent-sandbox
godot --headless --path godot-generative-agents/godot --import >/dev/null 2>&1 || true  # generate .uid
git add godot-generative-agents/godot/scripts/gif_encoder.gd \
        godot-generative-agents/godot/scripts/gif_encoder.gd.uid \
        godot-generative-agents/godot/tests/test_gif_encoder.gd \
        godot-generative-agents/godot/tests/test_gif_encoder.gd.uid \
        godot-generative-agents/run_smoke_test.sh
git commit -m "feat(viewer): pure-GDScript animated-GIF encoder (#488)

Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>"
```

---

### Task 2: `clip_export.gd` — file/download seam + ffmpeg command

**Files:**
- Create: `godot-generative-agents/godot/scripts/clip_export.gd`
- Test: `godot-generative-agents/godot/tests/test_clip_export.gd`
- Modify: `godot-generative-agents/run_smoke_test.sh` (register the test)

**Interfaces:**
- Consumes: nothing from Task 1 (independent).
- Produces (all static): `ClipExport.clip_base(start, end) -> String`; `ClipExport.save_gif(bytes: PackedByteArray, start: int, end: int, dir_override := "") -> String`; `ClipExport.make_frame_dir(start: int, end: int, dir_override := "") -> String`; `ClipExport.save_frame(img: Image, dir: String, index: int) -> bool`; `ClipExport.save_frames(frames: Array, start: int, end: int, dir_override := "") -> String`; `ClipExport.ffmpeg_command(dir: String) -> String`.

- [ ] **Step 1: Write the failing test**

Create `godot-generative-agents/godot/tests/test_clip_export.gd`:

```gdscript
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
```

- [ ] **Step 2: Run test to verify it fails**

Run: `godot --headless --path godot-generative-agents/godot --script res://tests/test_clip_export.gd`
Expected: FAIL — `clip_export.gd` does not exist.

- [ ] **Step 3: Write the export seam**

Create `godot-generative-agents/godot/scripts/clip_export.gd`:

```gdscript
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
```

- [ ] **Step 4: Run test to verify it passes**

Run: `godot --headless --path godot-generative-agents/godot --script res://tests/test_clip_export.gd 2>&1 | tail -20`
Expected: all `ok:`, then `test_clip_export: all checks passed`, exit 0.

- [ ] **Step 5: Register the test in the smoke runner**

In `godot-generative-agents/run_smoke_test.sh`, after the `test_gif_encoder.gd` block from Task 1, add:

```bash
"$GODOT" --headless --path "$PROJECT_DIR" --script res://tests/test_clip_export.gd 2>&1 \
  | tee /dev/stderr | grep -q "all checks passed"
```

- [ ] **Step 6: Commit**

```bash
cd /Users/yh/Documents/GitHub/agent-sandbox
godot --headless --path godot-generative-agents/godot --import >/dev/null 2>&1 || true
git add godot-generative-agents/godot/scripts/clip_export.gd \
        godot-generative-agents/godot/scripts/clip_export.gd.uid \
        godot-generative-agents/godot/tests/test_clip_export.gd \
        godot-generative-agents/godot/tests/test_clip_export.gd.uid \
        godot-generative-agents/run_smoke_test.sh
git commit -m "feat(viewer): clip_export file/download seam + ffmpeg command (#488)

Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>"
```

---

### Task 3: Timeline in/out markers + Export controls (`agent_panel.gd`, `timeline_markers.gd`)

Pure UI: adds the clip-span highlight and the Export affordance, plus the signal the viewer (Task 4) consumes. No headless unit test (Control layout); verified by the scene smoke test and manual check. Do Task 3 before Task 4 so the signal contract exists.

**Files:**
- Modify: `godot-generative-agents/godot/scripts/timeline_markers.gd`
- Modify: `godot-generative-agents/godot/scripts/agent_panel.gd`

**Interfaces:**
- Produces (agent_panel.gd): `signal clip_export_requested(kind: String)` (`"gif"` or `"frames"`); `func set_clip_span(a: int, b: int) -> void` (a<0 or b<a means "no span" → Export disabled, highlight cleared); `func set_clip_status(text: String, reveal_path: String) -> void` (reveal button shows when `reveal_path != ""`).
- Produces (timeline_markers.gd): `func set_clip_span(a: int, b: int) -> void`.

- [ ] **Step 1: Add the span highlight to `timeline_markers.gd`**

Add the state vars after line 29 (`var _filter := ""`):

```gdscript
var _clip_a := -1              # marked clip span (issue #488); -1 = unset
var _clip_b := -1
```

Add the setter after `set_filter` (after line 48):

```gdscript
func set_clip_span(a: int, b: int) -> void:
	_clip_a = a
	_clip_b = b
	queue_redraw()
```

In `_draw`, draw the span band BEFORE the tick loop (insert right after the `if _total <= 0: return` at line 62):

```gdscript
	if _clip_a >= 0 and _clip_b >= _clip_a:
		var x0 := _step_to_x(_clip_a)
		var x1 := _step_to_x(_clip_b)
		draw_rect(Rect2(x0, 0, maxf(x1 - x0, 2.0), size.y), Color(1.0, 0.85, 0.30, 0.35))
```

- [ ] **Step 2: Add the Export signal + controls to `agent_panel.gd`**

Add the signal after `signal seek_requested(step: int)` (line 29):

```gdscript
# The user asked to export the marked clip span (issue #488). kind = "gif" | "frames".
signal clip_export_requested(kind: String)
```

Add widget fields near the other scrubber fields (after line 235, `var _updating_scrubber`):

```gdscript
var _clip_gif_btn: Button           # export the marked span as a GIF (#488)
var _clip_frames_btn: Button        # export PNG frames for ffmpeg (desktop only)
var _clip_status: Label             # where the last export went
var _clip_reveal_btn: Button        # Reveal in Finder for the last export
```

Build the controls in `_ready()` immediately after the scrubber is added (after line 367, `col.add_child(_scrubber)`):

```gdscript
	# Clip export (issue #488): mark an in/out span with [ and ] (viewer.gd owns
	# the keys), then export the span. Frames+ffmpeg is desktop-only.
	var clip_row := HBoxContainer.new()
	clip_row.add_theme_constant_override("separation", 6)
	col.add_child(clip_row)

	_clip_gif_btn = Button.new()
	_clip_gif_btn.text = "Export GIF"
	_clip_gif_btn.tooltip_text = "Export the marked span ([ … ]) as an animated GIF"
	_clip_gif_btn.focus_mode = Control.FOCUS_NONE
	_clip_gif_btn.disabled = true
	_clip_gif_btn.pressed.connect(func() -> void: clip_export_requested.emit("gif"))
	clip_row.add_child(_clip_gif_btn)

	_clip_frames_btn = Button.new()
	_clip_frames_btn.text = "Export frames"
	_clip_frames_btn.tooltip_text = "Write the span as PNG frames + an ffmpeg command"
	_clip_frames_btn.focus_mode = Control.FOCUS_NONE
	_clip_frames_btn.disabled = true
	_clip_frames_btn.visible = not OS.has_feature("web")
	_clip_frames_btn.pressed.connect(func() -> void: clip_export_requested.emit("frames"))
	clip_row.add_child(_clip_frames_btn)

	_clip_reveal_btn = Button.new()
	_clip_reveal_btn.text = "Reveal"
	_clip_reveal_btn.focus_mode = Control.FOCUS_NONE
	_clip_reveal_btn.visible = false
	clip_row.add_child(_clip_reveal_btn)

	_clip_status = Label.new()
	_clip_status.add_theme_font_size_override("font_size", 12)
	_clip_status.autowrap_mode = TextServer.AUTOWRAP_WORD_SMART
	_clip_status.size_flags_horizontal = Control.SIZE_EXPAND_FILL
	col.add_child(_clip_status)
```

Add the two public methods (place them near `set_progress`, e.g. after line 640's function):

```gdscript
func set_clip_span(a: int, b: int) -> void:
	# Reflect the marked in/out span: highlight the strip, enable Export when the
	# span is valid (0 <= a <= b). A cleared span (a<0) disables export.
	var valid := a >= 0 and b >= a
	_markers_strip.set_clip_span(a if valid else -1, b if valid else -1)
	_clip_gif_btn.disabled = not valid
	_clip_frames_btn.disabled = not valid


func set_clip_status(text: String, reveal_path: String) -> void:
	_clip_status.text = text
	_clip_reveal_btn.visible = reveal_path != ""
	# Rewire Reveal to the newest path (disconnect any prior binding first).
	for c in _clip_reveal_btn.pressed.get_connections():
		_clip_reveal_btn.pressed.disconnect(c["callable"])
	if reveal_path != "":
		_clip_reveal_btn.pressed.connect(func() -> void:
			OS.shell_show_in_file_manager(reveal_path))
```

Hide the clip controls in live mode. In `set_live(live: bool)` (line 576), alongside the existing `_scrubber.visible = not live` / `_markers_strip.visible = not live` (lines 581–582), add:

```gdscript
	_clip_gif_btn.visible = not live
	_clip_frames_btn.visible = not live and not OS.has_feature("web")
	_clip_reveal_btn.visible = false
	_clip_status.visible = not live
```

- [ ] **Step 3: Verify the panel still loads (headless smoke)**

Run: `./godot-generative-agents/run_smoke_test.sh`
Expected: unit tests pass and every scene loads/paints (exit 0). This confirms `agent_panel.gd` / `timeline_markers.gd` parse and instantiate — the Export controls render even though nothing drives them yet.

- [ ] **Step 4: Commit**

```bash
cd /Users/yh/Documents/GitHub/agent-sandbox
git add godot-generative-agents/godot/scripts/agent_panel.gd \
        godot-generative-agents/godot/scripts/timeline_markers.gd
git commit -m "feat(viewer): clip in/out span highlight + Export controls (#488)

Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>"
```

---

### Task 4: Capture loop + wiring in `viewer.gd`

The integration: the offscreen capture coroutine, the two sinks, the `[`/`]` in/out keys, and the export dispatcher. Scene-coupled (needs a real framebuffer), so it is verified by the windowed smoke test plus a manual export in acceptance — NOT a headless unit test (the spec's stated boundary).

**Files:**
- Modify: `godot-generative-agents/godot/scripts/viewer.gd`

**Interfaces:**
- Consumes: `GifEncoder.encode` (Task 1); `ClipExport.save_gif` / `make_frame_dir` / `save_frame` / `ffmpeg_command` (Task 2); `_panel.clip_export_requested` / `set_clip_span` / `set_clip_status` (Task 3).

- [ ] **Step 1: Add preloads and clip-span state**

Near the other preloads (by `const ReplayMarkers := preload(...)` at line 123):

```gdscript
const GifEncoder := preload("res://scripts/gif_encoder.gd")
const ClipExport := preload("res://scripts/clip_export.gd")
```

Near `var _tracked_name := ""` (line 189):

```gdscript
# Clip export (issue #488): the marked in/out step span, -1 = unset. [ sets in,
# ] sets out; the panel highlights the span and enables Export when both are set.
var _clip_in := -1
var _clip_out := -1
```

- [ ] **Step 2: Connect the export signal in `_ready`**

Where the panel's playback signals are connected (by `_panel.seek_requested.connect(_on_seek)` at line 275), add:

```gdscript
	_panel.clip_export_requested.connect(_export_clip)
```

- [ ] **Step 3: Add the `[` / `]` in/out keys**

In `_unhandled_input`'s `match event.keycode` block (the modal-key handler around lines 1302–1316), add two cases:

```gdscript
		KEY_BRACKETLEFT:
			_set_clip_marker(true)
			get_viewport().set_input_as_handled()
		KEY_BRACKETRIGHT:
			_set_clip_marker(false)
			get_viewport().set_input_as_handled()
```

- [ ] **Step 4: Add the capture loop, sinks, and dispatcher**

Add these methods (place them next to `_take_snapshot`, after line 1458):

```gdscript
func _current_step() -> int:
	if step_seconds <= 0.0 or _frames.is_empty():
		return 0
	return clampi(int(_t / step_seconds), 0, maxi(_frames.size() - 1, 0))


func _set_clip_marker(is_in: bool) -> void:
	# [ marks the span start at the playhead, ] marks the end. Baked replay only.
	if _is_live or _frames.is_empty():
		return
	if is_in:
		_clip_in = _current_step()
	else:
		_clip_out = _current_step()
	_panel.set_clip_span(_clip_in, _clip_out)


func _downscale(img: Image) -> Image:
	# Cap GIF frames at 640px wide; full-res 720p GIFs are enormous.
	var maxw := 640
	if img.get_width() <= maxw:
		return img
	var out := img.duplicate()
	var h := int(round(img.get_height() * maxw / float(img.get_width())))
	out.resize(maxw, h, Image.INTERPOLATE_BILINEAR)
	return out


func _capture_span(from_step: int, to_step: int, sink: Callable) -> void:
	# Render each step in [from,to] offscreen and hand (seq_index, Image) to sink.
	# _paused stops _process advancing _t, so setting _t to an exact step multiple
	# renders that step with zero interpolation (see _process). UI chrome is hidden
	# so grabs are the bare campus; everything is restored on the way out.
	var last := maxi(_frames.size() - 1, 0)
	from_step = clampi(from_step, 0, last)
	to_step = clampi(to_step, from_step, last)
	var saved_t := _t
	var saved_paused := _paused
	_paused = true
	$UI.visible = false
	for step in range(from_step, to_step + 1):
		_t = float(step) * step_seconds
		await RenderingServer.frame_post_draw
		sink.call(step - from_step, get_viewport().get_texture().get_image())
	$UI.visible = true
	_t = saved_t
	_paused = saved_paused


func _export_clip(kind: String) -> void:
	# Dispatch the marked span to the GIF or the PNG-frames path (issue #488).
	if _is_live or _frames.is_empty():
		return
	if _clip_in < 0 or _clip_out < 0:
		_panel.set_clip_status("Mark a clip span first: [ sets start, ] sets end.", "")
		return
	var a := mini(_clip_in, _clip_out)
	var b := maxi(_clip_in, _clip_out)
	_panel.set_clip_status("Exporting %d frames…" % (b - a + 1), "")
	if kind == "gif":
		var frames: Array = []
		await _capture_span(a, b, func(_i: int, img: Image) -> void:
			frames.append(_downscale(img)))
		var bytes := GifEncoder.encode(frames, 10)
		var path := ClipExport.save_gif(bytes, a, b)
		if path == "":
			_panel.set_clip_status("GIF export failed — see console.", "")
		else:
			_panel.set_clip_status("saved → %s" % path,
				"" if OS.has_feature("web") else path)
	else:  # "frames"
		var dir := ClipExport.make_frame_dir(a, b)
		if dir == "":
			_panel.set_clip_status("Frame export failed — see console.", "")
			return
		var count := [0]
		await _capture_span(a, b, func(i: int, img: Image) -> void:
			if ClipExport.save_frame(img, dir, i):
				count[0] += 1)
		var gdir := ProjectSettings.globalize_path(dir)
		_panel.set_clip_status("%d frames → %s\n%s" % [count[0], gdir,
			ClipExport.ffmpeg_command(dir)], gdir)
```

- [ ] **Step 5: Headless smoke — everything still loads**

Run: `./godot-generative-agents/run_smoke_test.sh`
Expected: unit tests (incl. the two new ones) pass; all scenes load/paint; exit 0.

- [ ] **Step 6: Manual acceptance — a real clip (needs a windowed run + a baked replay)**

```bash
# Bake a short replay if one isn't present:
LLM_PROVIDER=mock uv run python godot-generative-agents/backend/penn/generate_penn_replay.py --steps 120
./godot-generative-agents/run.sh   # menu → "Play the bundled replay"
```
In the viewer: pause, seek to a start step, press `[`; seek later, press `]` (the timeline shows a gold band). Click **Export GIF** → status shows `saved → …/penn-clips/penn-clip-XXXX-YYYY.gif`. **Open that .gif in Preview and a browser** — it must animate and loop (this is the external-decoder correctness gate the headless tests can't provide). Click **Export frames** → confirm the PNG folder + that the printed `ffmpeg` command produces a GIF/MP4.

- [ ] **Step 7: Commit**

```bash
cd /Users/yh/Documents/GitHub/agent-sandbox
git add godot-generative-agents/godot/scripts/viewer.gd
git commit -m "feat(viewer): offscreen clip capture + GIF/frames export wiring (#488)

Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>"
```

---

## Notes for the implementer

- **Why `_paused = true` is enough (no `_process` edit):** `viewer._process` (line 1575) only advances `_t`/`_anim_t` `if not _paused`, and always renders agent positions from `_t` with `frac = fpos - int(fpos)`. Setting `_t = step * step_seconds` while paused therefore renders exactly that step (frac ≈ 0). `_anim_t` drives only the walk-cycle sprite frame, not position, so it needn't be reset.
- **GDScript lambda capture:** lambdas capture outer locals by value, so the sinks mutate a *reference* (`frames` Array append; `count` via a one-element `[0]` box) — do not rewrite these as plain `int`/reassignment, which would not propagate.
- **Performance:** encoding is O(pixels): the 32768-entry LUT build is ~instant, but mapping + LZW over ~100 × 640×360 frames is a few seconds. That is why the UI shows "Exporting N frames…" first. Keep the ≤640px cap.
- **LZW correctness:** the round-trip is pinned by a hand-computed vector in Task 1, and the code-size bump rule (`next_code == (1 << code_size)`) is the giflib-compatible one; Task 4 Step 6's "open in Preview/browser" is the external-decoder gate.

## Self-review

- **Spec coverage:** gif_encoder (§Design 1) → Task 1; clip_export IO seam incl. `save_frame`/`save_frames`/`ffmpeg_command` (§Design 2) → Task 2; `_capture_span` + sinks + downscale (§Design 3) → Task 4; in/out markers + span highlight + Export controls + web gate + status/Reveal (§Design 4) → Tasks 3–4; testing (§Verification) → headless tests Tasks 1–2, smoke + manual Tasks 3–4; baked-only guard, defaults, out-of-scope → Global Constraints. All covered.
- **Type consistency:** `save_gif(bytes, start, end, dir_override)`, `save_frame(img, dir, index)`, `make_frame_dir(start, end, dir_override)`, `ffmpeg_command(dir)`, `set_clip_span(a, b)`, `set_clip_status(text, reveal_path)`, `clip_export_requested(kind)` — used identically in every task that references them.
- **Placeholder scan:** no TBD/TODO; every code step carries complete code or an exact insertion point with the full snippet.
