extends SceneTree
## Headless contrast tests for the Cute Fantasy parchment UI. Run:
##   godot --headless --path godot-generative-agents/godot \
##     --script res://tests/test_ui_contrast.gd
## Exit 0 = every text colour clears WCAG AA; 1 = at least one failed
## (run_smoke_test.sh runs this before the scene smoke).
##
## Why this exists: the panel colours are hand-picked brown/red/teal tints chosen
## "to stay readable on the parchment", and that claim silently rotted. Four of the
## request log's six tints had drifted below AA (the row timestamp was 2.86:1, the
## wish tint 2.40:1) while the comment above them still said they were darkened for
## readability, and the error red — the text that most needs reading — sat at
## 3.29:1. A comment cannot enforce a contrast ratio; this test can.
##
## Every colour is READ FROM THE SOURCE (script constants + the theme resource),
## never restated here, so the test measures what actually ships.

const THEME_PATH := "res://theme/cute_fantasy_ui.tres"

# The panel interior. theme/cute_fantasy_ui.tres 9-slices SB_panel out of
# UI_Frames.png at Rect2(1067, 11, 26, 26) with 8px margins, and that centre is a
# single flat colour — every pixel is #f6ca9f. Re-measure with any image tool if
# the panel StyleBox is ever repointed at a different region.
const PARCHMENT := Color("f6ca9f")

# WCAG 2.1: 4.5:1 for normal text. The panels run text as small as 12px, so this is
# a floor, not a target — most values here sit at 5:1+.
const MIN_TEXT_RATIO := 4.5

## Colours that are deliberately below the text floor, each for a stated reason.
## Anything not listed is treated as text and must clear MIN_TEXT_RATIO.
const EXEMPT := {
	# WCAG explicitly exempts disabled controls.
	"theme Button/colors/font_disabled_color": "disabled text is meant to recede",
	# A 12x12 ColorRect, not text, and redundant: the status line next to it spells
	# the same state out in words ("Live · turn 42", "Degraded").
	"live_hud.DOT_COLORS": "non-text status dot, redundant with the status label",
	# Only ever assigned to _dot.color (live_hud.gd:448) — the same dot, so the same
	# 3:1 rule. Kept loud on purpose; see the constant's comment.
	"live_hud.HALT_COLOR": "non-text status dot; must stay louder than DOWN",
	# modulate() applied to a whole row as a highlight wash, not a glyph colour.
	"agent_panel.ACTIVE_TINT": "row highlight wash, not text",
	"agent_panel.ROW_DIM_ALPHA": "not a colour",
}

var _failures := 0


func _check(cond: bool, name: String) -> void:
	if cond:
		print("  ok: %s" % name)
	else:
		_failures += 1
		push_error("FAIL: %s" % name)


func _relative_luminance(c: Color) -> float:
	# WCAG 2.1 relative luminance: sRGB -> linear, then the 0.2126/0.7152/0.0722 mix.
	var chan := [c.r, c.g, c.b]
	var lin := []
	for v in chan:
		lin.append(v / 12.92 if v <= 0.03928 else pow((v + 0.055) / 1.055, 2.4))
	return 0.2126 * lin[0] + 0.7152 * lin[1] + 0.0722 * lin[2]


func _ratio(fg: Color, bg: Color) -> float:
	var a := _relative_luminance(fg)
	var b := _relative_luminance(bg)
	var hi: float = max(a, b)
	var lo: float = min(a, b)
	return (hi + 0.05) / (lo + 0.05)


func _check_text(label: String, c: Color) -> void:
	var r := _ratio(c, PARCHMENT)
	_check(
		r >= MIN_TEXT_RATIO,
		"%s #%s is %.2f:1 on the parchment (needs %.1f:1)" % [
			label, c.to_html(false), r, MIN_TEXT_RATIO,
		]
	)


func _initialize() -> void:
	# --- the measuring method itself, against known-good reference pairs ---
	_check(is_equal_approx(snappedf(_ratio(Color.BLACK, Color.WHITE), 0.01), 21.0),
		"black on white is 21:1 (the WCAG maximum)")
	_check(is_equal_approx(_ratio(Color.WHITE, Color.WHITE), 1.0),
		"a colour against itself is 1:1")
	_check(is_equal_approx(_ratio(Color.RED, Color.BLUE), _ratio(Color.BLUE, Color.RED)),
		"the ratio is symmetric in its arguments")

	# --- the parchment really is the flat colour this test assumes ---
	# Pull the panel StyleBox out of the theme and sample its texture, so a swap to
	# a different frame region can't leave the constant above quietly stale.
	var theme: Theme = load(THEME_PATH)
	_check(theme != null, "the theme resource loads")
	var panel_sb := theme.get_stylebox("panel", "PanelContainer")
	_check(panel_sb is StyleBoxTexture, "PanelContainer/panel is a StyleBoxTexture")
	var sampled_ok := false
	if panel_sb is StyleBoxTexture:
		var tex: Texture2D = (panel_sb as StyleBoxTexture).texture
		if tex != null:
			var img := tex.get_image()
			if img != null and img.get_width() > 16 and img.get_height() > 16:
				# The 9-slice centre, well inside the 8px margins.
				var mid := img.get_pixel(img.get_width() / 2, img.get_height() / 2)
				sampled_ok = true
				_check(
					mid.is_equal_approx(PARCHMENT),
					"the panel's centre pixel is still #%s (sampled #%s)" % [
						PARCHMENT.to_html(false), mid.to_html(false),
					]
				)
	if not sampled_ok:
		# Not a failure: headless Godot can decline to hand back texture pixels.
		# The ratios below still run against the documented constant.
		print("  --: panel texture not readable headless; using the documented #%s"
			% PARCHMENT.to_html(false))

	# --- theme colours ---
	# Every font_color the theme sets, by the type it applies to.
	for entry in [
		["Label", "font_color"],
		["Button", "font_color"],
		["Button", "font_hover_color"],
		["Button", "font_pressed_color"],
		["Button", "font_focus_color"],
		["OptionButton", "font_color"],
		["OptionButton", "font_hover_color"],
		["OptionButton", "font_pressed_color"],
		["RichTextLabel", "default_color"],
		["TitleRibbon", "font_color"],
	]:
		var type_name: String = entry[0]
		var color_name: String = entry[1]
		var key := "theme %s/colors/%s" % [type_name, color_name]
		_check(theme.has_color(color_name, type_name), "%s is themed" % key)
		if theme.has_color(color_name, type_name):
			_check_text(key, theme.get_color(color_name, type_name))

	# RichTextLabel is the one that bit us: Godot's own default is white, which is
	# invisible here, so the theme MUST carry it (live_hud's log used to patch it
	# per-node). Assert the theme owns it, not just that some colour passes.
	_check(theme.has_color("default_color", "RichTextLabel"),
		"RichTextLabel/default_color is themed, so log text isn't white-on-parchment")

	# The disabled colour is exempt, but assert it's actually the dim one — i.e. it
	# was left low deliberately, not by the same drift this test guards against.
	var disabled := theme.get_color("font_disabled_color", "Button")
	_check(_ratio(disabled, PARCHMENT) < MIN_TEXT_RATIO,
		"Button/font_disabled_color stays below the floor on purpose (%s)"
			% EXEMPT["theme Button/colors/font_disabled_color"])

	# --- script constants: the small print on the parchment surfaces ---
	# Read straight out of each script's constant map so the values under test are
	# the shipped ones. Every entry here renders as TEXT on a parchment panel.
	var text_consts := {
		"res://scripts/agent_panel.gd": ["STATUS_COLOR"],
		"res://scripts/actions_hud.gd": ["MUTED_COLOR"],
		"res://scripts/dialogue_log_panel.gd": ["MUTED_COLOR"],
		"res://scripts/main_menu.gd": ["HINT_COLOR", "ERROR_COLOR"],
		"res://scripts/past_runs.gd": ["HINT_COLOR", "ERROR_COLOR"],
		"res://scripts/simulation_setup.gd": ["HINT_COLOR", "ERROR_COLOR"],
		# HALT_COLOR is absent on purpose: it is a dot, not text (see EXEMPT).
		"res://scripts/live_hud.gd": [
			"MUTED_COLOR", "TRIPPED_COLOR", "WISH_TINT", "LOG_TIME_COLOR",
		],
	}
	for path in text_consts:
		var script: GDScript = load(path)
		_check(script != null, "%s loads" % path)
		if script == null:
			continue
		var consts := script.get_script_constant_map()
		for const_name in text_consts[path]:
			var label := "%s.%s" % [path.get_file(), const_name]
			_check(consts.has(const_name), "%s exists" % label)
			if consts.has(const_name):
				_check_text(label, consts[const_name])

	# The request log's per-role tints, all four, from the dictionary itself — so
	# adding a fifth role without darkening it fails here rather than in someone's
	# eyes six months later.
	var hud_consts: Dictionary = (load("res://scripts/live_hud.gd") as GDScript) \
		.get_script_constant_map()
	var tints: Dictionary = hud_consts["LOG_ROLE_TINTS"]
	_check(not tints.is_empty(), "LOG_ROLE_TINTS is non-empty")
	for role in tints:
		_check_text("live_hud.LOG_ROLE_TINTS[%s]" % role, tints[role])

	# The muted small print is shared by seven files as three different names. They
	# drifted apart once already; assert they're still one value.
	var muted := [
		(load("res://scripts/agent_panel.gd") as GDScript)
			.get_script_constant_map()["STATUS_COLOR"],
		(load("res://scripts/actions_hud.gd") as GDScript)
			.get_script_constant_map()["MUTED_COLOR"],
		(load("res://scripts/dialogue_log_panel.gd") as GDScript)
			.get_script_constant_map()["MUTED_COLOR"],
		(load("res://scripts/main_menu.gd") as GDScript)
			.get_script_constant_map()["HINT_COLOR"],
		(load("res://scripts/past_runs.gd") as GDScript)
			.get_script_constant_map()["HINT_COLOR"],
		(load("res://scripts/simulation_setup.gd") as GDScript)
			.get_script_constant_map()["HINT_COLOR"],
		hud_consts["MUTED_COLOR"],
	]
	var all_same := true
	for c in muted:
		if not (c as Color).is_equal_approx(muted[0]):
			all_same = false
	_check(all_same,
		"STATUS_COLOR / MUTED_COLOR / HINT_COLOR are still the same brown across all seven files")

	# The status dots are graphics, so they answer to the 3:1 non-text threshold
	# rather than 4.5:1. HALT_COLOR is the one that matters: it marks the most
	# severe state, so assert it clears 3:1 AND stays at least as loud as the DOWN
	# dot — darkening it for "contrast" would quietly invert the severity ordering.
	var halt: Color = hud_consts["HALT_COLOR"]
	var down: Color = (hud_consts["DOT_COLORS"] as Dictionary)[3]
	_check(_ratio(halt, PARCHMENT) >= 3.0,
		"HALT_COLOR clears the 3:1 non-text threshold (%.2f:1)" % _ratio(halt, PARCHMENT))
	_check(halt.v >= down.v,
		"the HALTED dot is at least as bright as the DOWN dot (%.2f vs %.2f)" % [halt.v, down.v])

	# The alarm reds are separate constants but should stay recognisably one colour
	# family — a red that drifts to orange stops reading as an error.
	for entry in [
		["main_menu.ERROR_COLOR", (load("res://scripts/main_menu.gd") as GDScript)
			.get_script_constant_map()["ERROR_COLOR"]],
		["live_hud.HALT_COLOR", halt],
		["live_hud.TRIPPED_COLOR", hud_consts["TRIPPED_COLOR"]],
	]:
		var c: Color = entry[1]
		_check(c.h * 360.0 < 15.0 or c.h * 360.0 > 345.0,
			"%s is still in the red hue band (%.0f°)" % [entry[0], c.h * 360.0])

	# --- no font is bundled (the pack's pixel font was deleted) ---
	# The theme must keep inheriting Godot's built-in face; a default_font here
	# would silently repaint every panel in whatever got added.
	_check(theme.default_font == null,
		"the theme sets no default_font, so UI text stays on Godot's built-in face")
	_check(not FileAccess.file_exists("res://Cute_Fantasy_UI/Fonts/CuteFantasy-5x9.ttf"),
		"the unused Cute Fantasy pixel font is gone")

	if _failures == 0:
		print("test_ui_contrast: all checks passed")
	quit(1 if _failures > 0 else 0)
