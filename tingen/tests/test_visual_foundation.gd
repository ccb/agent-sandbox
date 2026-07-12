extends SceneTree
## M16 — Visual Foundation harness. Standalone, dependency-free:
##   godot --headless --path tingen -s tests/test_visual_foundation.gd
##
## Proves the three seams the milestone wires, each falling back safely for a missing asset:
##   (a) an NPC WITH a real sprite asset loads that texture (path != icon.svg), tint dropped;
##   (b) an NPC WITHOUT art keeps the icon.svg placeholder + its identity tint (no crash);
##   (c) a combat_form with assets/enemies/<form>.png shows it; one without falls back cleanly;
##   (d) the shared Theme resource loads and a probe Control under a themed root inherits it;
##   (e) the M10 Settings seams (text_scale + colorblind) still take effect with the theme active.
## Determinism (f) is proven by the separate combat_sim / vectors / full_run runners — nothing here
## touches combat resolution (resolve_sprite_path + _apply_form_sprite are cosmetic-only).

const THEME_PATH := "res://assets/ui/tingen_theme.tres"
const ICON := "res://icon.svg"

var _passed: int = 0
var _failed: int = 0

func _init() -> void:
	await process_frame
	await process_frame
	await _test_a_npc_with_art_loads_real_sprite()
	await _test_b_npc_without_art_falls_back()
	await _test_c_form_sprite_shows_and_falls_back()
	await _test_d_theme_loads_and_inherits()
	await _test_e_settings_seams_survive_theme()
	print("\n=== test_visual_foundation: %d passed, %d failed ===" % [_passed, _failed])
	quit(1 if _failed > 0 else 0)

func _ok(cond: bool, label: String) -> void:
	if cond:
		_passed += 1
		print("  PASS  %s" % label)
	else:
		_failed += 1
		printerr("  FAIL  %s" % label)

# (a) a mapped NPC shows real art -----------------------------------------------------------------
func _test_a_npc_with_art_loads_real_sprite() -> void:
	print("[a] npc with real sprite")
	# constable_brom is mapped by CONVENTION (assets/characters/constable_brom.png);
	# ledger_finch by the explicit `sprite` field. Both must resolve to real art, not icon.svg.
	for id in ["constable_brom", "ledger_finch"]:
		var npc = load("res://scenes/NPC.tscn").instantiate()
		npc.npc_id = id
		root.add_child(npc)
		await process_frame
		var spr: Sprite2D = npc.get_node("Sprite2D")
		var path := spr.texture.resource_path if spr.texture != null else ""
		_ok(path != "" and path != ICON, "%s loads a real sprite (%s)" % [id, path])
		_ok(spr.modulate.r == 1.0 and spr.modulate.g == 1.0 and spr.modulate.b == 1.0,
			"%s drops the flat identity tint when real art loads" % id)
		npc.queue_free()
		await process_frame

# (b) an unmapped NPC keeps the placeholder + tint, no crash --------------------------------------
func _test_b_npc_without_art_falls_back() -> void:
	print("[b] npc without art falls back")
	var npc = load("res://scenes/NPC.tscn").instantiate()
	npc.npc_id = "zz_artless_probe"   # a synthetic id with no art file and no sprite field -> placeholder
	root.add_child(npc)
	await process_frame
	var spr: Sprite2D = npc.get_node("Sprite2D")
	_ok(spr.texture != null and spr.texture.resource_path == ICON,
		"an artless npc keeps the icon.svg placeholder")
	_ok(load("res://src/NPC.gd").resolve_sprite_path("zz_artless_probe", {}) == "",
		"the seam resolves NO art for an artless id (placeholder contract)")
	npc.queue_free()
	# a bogus id must also not crash (empty def -> placeholder path)
	var bogus = load("res://scenes/NPC.tscn").instantiate()
	bogus.npc_id = "no_such_npc_xyz"
	root.add_child(bogus)
	await process_frame
	var bspr: Sprite2D = bogus.get_node("Sprite2D")
	_ok(bspr.texture != null and bspr.texture.resource_path == ICON,
		"unknown id falls back to placeholder without crashing")
	bogus.queue_free()
	await process_frame

# (c) per-form body sprite shows / falls back -----------------------------------------------------
func _test_c_form_sprite_shows_and_falls_back() -> void:
	print("[c] combat form body sprite")
	var body := Node2D.new()
	var spr := Sprite2D.new()
	spr.texture = load(ICON)
	body.add_child(spr)
	root.add_child(body)
	var ex := CombatExecutor.new()
	var ag := Agent.new("form_probe")
	ex.bind(ag, body)
	# a form WITH an enemies/<form>.png swaps the body sprite
	ex._apply_form_sprite("bieber_monster")
	var swapped := spr.texture != null and spr.texture.resource_path.ends_with("bieber_monster.png")
	_ok(swapped, "a combat_form with enemies/<form>.png shows it (%s)" % (spr.texture.resource_path if spr.texture else ""))
	# a form WITHOUT a png must not touch the sprite (no crash, no null-out)
	var before := spr.texture
	ex._apply_form_sprite("zz_artless_form_probe")   # a synthetic form id with no enemies/<form>.png
	_ok(spr.texture == before, "a form without art falls back cleanly (sprite unchanged, no crash)")
	ex.free()
	body.queue_free()
	await process_frame

# (d) theme loads + inherits ----------------------------------------------------------------------
func _test_d_theme_loads_and_inherits() -> void:
	print("[d] shared theme")
	_ok(ResourceLoader.exists(THEME_PATH), "theme resource exists on disk")
	var th = load(THEME_PATH)
	_ok(th is Theme, "theme resource loads as a Theme")
	_ok(th != null and th.default_font_size > 0, "theme declares a default font size")
	# broad application: the project sets it as the root gui theme so EVERY Control inherits it
	_ok(String(ProjectSettings.get_setting("gui/theme/custom", "")) == THEME_PATH,
		"theme is set as the project-wide gui theme (root ancestor)")
	# a probe Control under a themed root inherits the theme's default font size
	var host := Control.new()
	host.theme = th
	var probe := Label.new()
	host.add_child(probe)
	root.add_child(host)
	await process_frame
	_ok(probe.get_theme_default_font_size() == th.default_font_size,
		"a probe Control under a themed root inherits the theme")
	host.queue_free()
	await process_frame

# (e) M10 Settings seams still bite with the theme active -----------------------------------------
func _test_e_settings_seams_survive_theme() -> void:
	print("[e] settings seams under theme")
	var Settings_al: Object = root.get_node("/root/Settings")
	var th = load(THEME_PATH)
	var host := Control.new()
	host.theme = th
	var label := Label.new()
	host.add_child(label)
	root.add_child(host)
	await process_frame
	# text_scale override must win over the theme's default font size
	Settings_al.set_value("text_scale", 2.0)
	Settings_al.apply_text_scale(label, 12)
	_ok(label.get_theme_font_size("font_size") == 24,
		"text_scale override beats the theme default (24 = 12 * 2.0)")
	# colorblind palette is drawn directly, untouched by the theme
	Settings_al.set_value("colorblind", true)
	var cb: Color = Settings_al.meter_color("doom")
	_ok(abs(cb.r - 0.0) < 0.01 and abs(cb.g - 0.45) < 0.01 and abs(cb.b - 0.70) < 0.01,
		"colorblind palette still applies with the theme active")
	# restore defaults so later tests / runs see a clean settings store
	Settings_al.set_value("text_scale", 1.0)
	Settings_al.set_value("colorblind", false)
	host.queue_free()
	await process_frame
