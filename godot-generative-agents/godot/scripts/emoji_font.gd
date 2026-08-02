extends Node
## Installs the bundled monochrome Noto Emoji as a fallback on the default
## theme font (#951).
##
## The theme deliberately ships no font of its own — Godot's built-in Open
## Sans is the look we want — but Open Sans has no emoji glyphs. Native builds
## papered over that with OS font fallback (Apple Color Emoji et al.); a web
## export runs in the browser sandbox with no system fonts at all, so every
## 💭 wish marker and persona badge rendered as an empty box. Wrapping the
## default font once here makes both platforms resolve emoji from the same
## bundled file. Fallbacks are only consulted for glyphs the base font lacks,
## so Latin text stays Open Sans, pixel for pixel.

const EMOJI_FONT_PATH := "res://theme/fonts/NotoEmoji-VariableFont_wght.ttf"


func _init() -> void:
	var emoji := load(EMOJI_FONT_PATH) as Font
	if emoji == null:
		push_error("emoji_font: cannot load %s — emoji will render as boxes" % EMOJI_FONT_PATH)
		return
	var wrapped := FontVariation.new()
	wrapped.base_font = ThemeDB.fallback_font
	wrapped.fallbacks = [emoji]
	ThemeDB.fallback_font = wrapped
