extends SceneTree
## #951: emoji must resolve from the bundled fallback font — a web export has
## no system fonts, so the OS fallback that made native builds look fine cannot
## be load-bearing. RED before the fix: the default theme font is Godot's
## built-in Open Sans, which has no emoji glyphs, and every 💭/🔬 in the WASM
## viewer rendered as an empty box.


func _initialize() -> void:
	var failures := 0

	# The bundled font itself covers the glyphs the viewer ships: the 💭 wish
	# marker (#625), persona badges like 🔬, and the timeline hover emoji 🤢/🍵.
	var emoji := load("res://theme/fonts/NotoEmoji-VariableFont_wght.ttf") as Font
	if emoji == null:
		print("FAIL: bundled emoji font is missing or not importable")
		failures += 1
	else:
		for cp: int in [0x1F4AD, 0x1F52C, 0x1F922, 0x1F375]:
			if not emoji.has_char(cp):
				print("FAIL: bundled font lacks U+%X" % cp)
				failures += 1
		if failures == 0:
			print("ok: bundled font covers the viewer's emoji")

	# And the default theme font actually reaches it: either has_char resolves
	# through the chain, or the font is the FontVariation the EmojiFont autoload
	# installs, with a fallback that covers the glyph.
	var fallback := ThemeDB.fallback_font
	var resolves := fallback != null and fallback.has_char(0x1F4AD)
	if not resolves and fallback is FontVariation:
		for f: Font in (fallback as FontVariation).fallbacks:
			if f != null and f.has_char(0x1F4AD):
				resolves = true
				break
	if resolves:
		print("ok: default theme font resolves U+1F4AD via the bundled fallback")
	else:
		print("FAIL: ThemeDB.fallback_font cannot resolve U+1F4AD — emoji tofu on web")
		failures += 1

	if failures == 0:
		print("test_emoji_fallback: all checks passed")
	quit(0 if failures == 0 else 1)
