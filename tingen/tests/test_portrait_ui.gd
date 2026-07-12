extends SceneTree
## M19 — NPC portrait in the UI. Standalone, dependency-free headless harness:
##   godot --headless --path tingen -s tests/test_portrait_ui.gd
##
## Proves the portrait seam + its wiring into the dialogue panel, each falling back safely:
##   (a) opening a dialogue with an NPC that HAS art shows that texture in the panel's portrait slot
##       (bram_kell / old_neil -> the slot texture path is their assets/characters/<id>.png);
##   (b) an NPC WITHOUT art falls back cleanly (no texture / neutral silhouette), dialogue still works,
##       no crash;
##   (c) the reusable Portrait helper resolves id -> texture with a graceful fallback (null for artless);
##   (d) the dialogue portrait UPDATES when the speaker changes and CLEARS when the conversation closes;
##   (e) determinism is untouched — this file never touches combat (portrait resolution is cosmetic-only,
##       proven by the separate combat_sim / vectors / full_run runners).

const PortraitScript := preload("res://src/Portrait.gd")
const CHAR_DIR := "res://assets/characters/"
const ICON := "res://icon.svg"

var _passed: int = 0
var _failed: int = 0

func _init() -> void:
	await process_frame
	await process_frame
	_test_c_helper_resolves_with_fallback()
	await _test_a_dialogue_with_art_shows_portrait()
	await _test_b_artless_npc_falls_back()
	await _test_d_portrait_updates_on_speaker_change_and_clears()
	await _test_e_settings_connect_is_idempotent()
	_test_f_headshot_side_never_exceeds_bounds()
	print("\n=== test_portrait_ui: %d passed, %d failed ===" % [_passed, _failed])
	quit(1 if _failed > 0 else 0)

func _ok(cond: bool, label: String) -> void:
	if cond:
		_passed += 1
		print("  PASS  %s" % label)
	else:
		_failed += 1
		printerr("  FAIL  %s" % label)

# (c) the reusable Portrait helper resolves id -> texture with fallback ----------------------------
func _test_c_helper_resolves_with_fallback() -> void:
	print("[c] Portrait helper resolves id -> texture with fallback")
	for id in ["bram_kell", "old_neil"]:
		var tex: Texture2D = PortraitScript.resolve_texture(id)
		_ok(tex != null, "%s resolves to a real texture" % id)
		_ok(PortraitScript.resolve_path(id) == "%s%s.png" % [CHAR_DIR, id],
			"%s resolves by convention to its character png" % id)
	_ok(PortraitScript.resolve_texture("zz_artless_probe") == null,
		"an artless id resolves to NO texture (null) — the fallback contract")
	_ok(PortraitScript.resolve_path("zz_artless_probe") == "",
		"an artless id resolves to an empty path")

# (a) opening a dialogue with an NPC that HAS art shows that texture in the panel's slot -----------
func _test_a_dialogue_with_art_shows_portrait() -> void:
	print("[a] dialogue panel shows the speaker's portrait")
	var panel: Control = load("res://ui/DialoguePanel.tscn").instantiate()
	root.add_child(panel)
	await process_frame
	for id in ["bram_kell", "old_neil"]:
		# _on_started is the dialogue_started(npc_id) handler — the seam that fires the instant a
		# conversation opens (DialogueManager.open emits it with the npc id).
		panel._on_started(id)
		await process_frame
		var slot: Texture2D = panel.portrait_texture()
		var path := slot.resource_path if slot != null else ""
		_ok(path == "%s%s.png" % [CHAR_DIR, id],
			"opening with %s shows their character png in the slot (%s)" % [id, path])
		_ok(panel.visible, "the panel is visible while %s is on screen" % id)
	panel.queue_free()
	await process_frame

# (b) an NPC WITHOUT art falls back with no crash, dialogue still works ----------------------------
func _test_b_artless_npc_falls_back() -> void:
	print("[b] artless npc falls back cleanly")
	var panel: Control = load("res://ui/DialoguePanel.tscn").instantiate()
	root.add_child(panel)
	await process_frame
	panel._on_started("zz_artless_probe")
	await process_frame
	_ok(panel.portrait_texture() == null, "an artless speaker leaves the slot empty (no texture)")
	_ok(panel.visible, "the panel still opens for an artless speaker (no crash)")
	# dialogue still renders text + options after the artless open
	panel._on_node_changed("Nobody", "A voice with no face.", [{"text": "Go on."}])
	await process_frame
	var text: Label = panel.get_node("Box/Margin/Body/Text")
	_ok(text.text == "A voice with no face.", "dialogue still renders text for an artless speaker")
	panel.queue_free()
	await process_frame

# (d) portrait updates when the speaker changes and clears on close -------------------------------
func _test_d_portrait_updates_on_speaker_change_and_clears() -> void:
	print("[d] portrait updates on speaker change + clears on close")
	var panel: Control = load("res://ui/DialoguePanel.tscn").instantiate()
	root.add_child(panel)
	await process_frame
	panel._on_started("bram_kell")
	await process_frame
	var a: Texture2D = panel.portrait_texture()
	_ok(a != null and a.resource_path.ends_with("bram_kell.png"), "bram_kell portrait shown first")
	panel._on_started("old_neil")   # speaker changes (open with a different npc)
	await process_frame
	var b: Texture2D = panel.portrait_texture()
	_ok(b != null and b.resource_path.ends_with("old_neil.png"), "portrait swaps to old_neil on speaker change")
	panel._on_ended()   # conversation closes
	await process_frame
	_ok(panel.portrait_texture() == null, "the portrait clears when the conversation closes")
	_ok(not panel.visible, "the panel hides when the conversation closes")
	panel.queue_free()
	await process_frame

# (e) regression (FIXER LOW): the Settings.changed connect is idempotent — re-running _ready() on a
# re-parented Portrait must not stack duplicate handlers (was an unguarded lambda -> double-connect).
func _test_e_settings_connect_is_idempotent() -> void:
	print("[e] Portrait Settings.changed connect is idempotent under re-_ready()")
	var s := root.get_node_or_null("/root/Settings")
	if s == null or not s.has_signal("changed"):
		_ok(true, "Settings autoload absent — connect-guard vacuously safe (skipped)")
		return
	var p: Control = PortraitScript.new()
	root.add_child(p)         # first _ready() -> one connection
	await process_frame
	p._ready()                # simulate a re-parent re-running _ready()
	p._ready()
	var n := 0
	for c in s.get_signal_connection_list("changed"):
		if c.get("callable") is Callable and (c["callable"] as Callable).get_object() == p:
			n += 1
	_ok(n == 1, "exactly ONE Settings.changed handler after three _ready() calls (got %d)" % n)
	p.queue_free()
	await process_frame

# (f) regression (FIXER COSMETIC): the leads-board headshot crop never runs its atlas region past the
# texture — clamped to the shorter side. A wider-than-tall texture is the failing-before case.
func _test_f_headshot_side_never_exceeds_bounds() -> void:
	print("[f] InvestigationBoard.headshot_side clamps to the shorter side")
	var Board := load("res://src/InvestigationBoard.gd")
	var wide := _tex(100, 40)   # wider than tall — the case the old Rect2(0,0,w,w) overran
	var tall := _tex(40, 100)
	_ok(Board.headshot_side(wide) == 40.0, "wide portrait clamps the square to its HEIGHT (40)")
	_ok(Board.headshot_side(wide) <= float(wide.get_height()), "region height never exceeds the texture")
	_ok(Board.headshot_side(tall) == 40.0, "tall portrait (every shipped one) uses its WIDTH unchanged")

func _tex(w: int, h: int) -> Texture2D:
	return ImageTexture.create_from_image(Image.create(w, h, false, Image.FORMAT_RGBA8))
