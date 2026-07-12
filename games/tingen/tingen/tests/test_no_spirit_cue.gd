extends SceneTree
## M34 — the NO_SPIRIT CUE (the spirit counterpart to the M13 no_ammo / weapon_empty cue). When the
## Hermit casts on a spent spirituality pool, the refusal must READ: a distinct "spirit_empty" event +
## a red pulse on the HUD's OWN Spirit bar (its own channel — never the ammo-label pulse, never the
## full-screen hit-flash), so a drained star-caster sees "out of spirit", not "I took damage" and not
## "out of ammo". Fired from BOTH spirit-spend buttons (the primary attack AND the charm). Mirrors
## _on_weapon_empty exactly: the flash is Settings.hit_flash-gated (off -> no visual), but the EVENT
## always fires — the cue is never suppressed.
## Run: godot --headless --path tingen -s tests/test_no_spirit_cue.gd
## Also folded into the main suite (run_tests.gd `_test_no_spirit_cue`) via the SAME run_all() entry.
##
## Covers (TDD):
##  T2a RED  — a Hermit casting on an empty pool (attack AND charm) emits spirit_empty >= 1
##            (RED: _on_spirit_empty absent — no spirit_empty event ever fires).
##  T2b GUARD — CHANNEL SEPARATION: no_ammo emits weapon_empty (not spirit_empty); no_spirit emits
##            spirit_empty (not weapon_empty) — the two dry-resource cues never cross-fire.
##  T2c RED  — FLASH-GATE PARITY: hit_flash off -> flash no-op (alpha 0) but spirit_empty STILL fires.
##  T2d RED  — HUD: a spirit_empty (hit_flash on) arms the Spirit-bar red pulse; gated off it does not.

func _init() -> void:
	await process_frame
	await process_frame
	# B3 (retro): NEVER touch the player's REAL persistent profile (user://meta.json) — redirect
	# the meta slot to a test-scoped file before anything drives RunManager (tests/test_meta_isolation.gd).
	root.get_node("/root/RunManager").set("meta_path", "user://meta_test.json")
	root.get_node("/root/RunManager").reload_meta()
	var r: Dictionary = run_all()
	print("\n=== test_no_spirit_cue: %d passed, %d failed ===" % [int(r["passed"]), int(r["failed"])])
	quit(1 if int(r["failed"]) > 0 else 0)

## The one entry point (returns {passed, failed}); folded into run_tests.gd.
static func run_all() -> Dictionary:
	var c := {"passed": 0, "failed": 0}
	var root: Node = (Engine.get_main_loop() as SceneTree).root
	_t_spirit_empty_event(c, root)
	_t_channel_separation(c, root)
	_t_flash_gate_parity(c, root)
	_t_hud_spirit_pulse(c, root)
	# Leave a clean Hunter world for whatever runs next in the shared suite.
	root.get_node("/root/RunManager").start_run()
	root.get_node("/root/Agents").rebuild()
	root.get_node("/root/Progression").select_pathway("hunter")
	var S: Object = root.get_node_or_null("/root/Settings")
	if S != null and S.has_method("reset_defaults"):
		S.reset_defaults()
	return c

# --- helpers ------------------------------------------------------------------------------------
static func _check(c: Dictionary, cond: bool, label: String) -> void:
	if cond:
		c["passed"] = int(c["passed"]) + 1
		print("  PASS  %s" % label)
	else:
		c["failed"] = int(c["failed"]) + 1
		printerr("  FAIL  %s" % label)

static func _unlock_hermit(RM: Object) -> void:
	RM.reset_meta()
	RM.start_run()
	RM.end_run("win", {"outcome": "descent_stopped"})
	RM.reload_meta()

static func _stage_player(root: Node, pathway: String, room: String) -> Node:
	var RM: Object = root.get_node("/root/RunManager")
	var AG: Object = root.get_node("/root/Agents")
	if pathway == "hermit":
		_unlock_hermit(RM)
	RM.start_run(pathway)
	AG.rebuild()
	var p: Node = load("res://scenes/Player.tscn").instantiate()
	root.add_child(p)
	var pc: Node = p.get_node("Combat")
	pc.proxy.room = room
	pc.proxy.position = Vector2.ZERO
	return p

static func _end_player(root: Node, p: Node) -> void:
	if p != null:
		p.free()
	root.get_node("/root/Agents").rebuild()
	root.get_node("/root/EventBus").clear()

## Tolerant read of a maybe-missing HUD field (so the file PARSES + runs RED before the field exists).
static func _field(obj: Object, name: String) -> float:
	var v: Variant = obj.get(name)
	return float(v) if v != null else -1.0

# T2a --------------------------------------------------------------------------------------------
## A drained Hermit casting the primary (star_brand) OR the charm (paper_charm) must emit a spirit_empty
## cue on the EventBus. RED at HEAD: PlayerCombat has no _on_spirit_empty / spirit_empty spend path, so
## the refusal is silent (no cue event ever fires).
static func _t_spirit_empty_event(c: Dictionary, root: Node) -> void:
	print("[M34 T2a: a drained Hermit cast (attack AND charm) emits a spirit_empty cue]")
	var EB: Object = root.get_node("/root/EventBus")
	var p: Node = _stage_player(root, "hermit", "no_spirit_arena")
	var pc: Node = p.get_node("Combat")
	pc.set("spirituality", 0.0)
	EB.clear()
	var r_attack: Dictionary = pc.on_attack_pressed(Vector2.RIGHT)
	_check(c, String(r_attack.get("reason", "")) == "no_spirit",
		"the drained Hermit's ATTACK (star_brand) is refused no_spirit")
	_check(c, EB.events("spirit_empty").size() >= 1,
		"…and emits a spirit_empty cue (RED: _on_spirit_empty absent — %d)" % EB.events("spirit_empty").size())
	var before: int = EB.events("spirit_empty").size()
	var r_charm: Dictionary = pc.on_charm_pressed(Vector2.RIGHT)
	_check(c, String(r_charm.get("reason", "")) == "no_spirit",
		"the drained Hermit's CHARM (paper_charm) is also refused no_spirit")
	_check(c, EB.events("spirit_empty").size() > before,
		"…and the CHARM button ALSO emits spirit_empty (both spirit-spend paths cue)")
	_end_player(root, p)

# T2b GREEN-GUARD --------------------------------------------------------------------------------
## Channel separation: the two dry-resource cues never cross-fire. An empty-spirit Hermit cast cues
## spirit_empty and NOT weapon_empty; an empty-ammo Hunter cast cues weapon_empty and NOT spirit_empty.
static func _t_channel_separation(c: Dictionary, root: Node) -> void:
	print("[M34 T2b GUARD: channel separation — no_spirit -> spirit_empty only; no_ammo -> weapon_empty only]")
	var EB: Object = root.get_node("/root/EventBus")
	# (a) Hermit, empty spirit.
	var ph: Node = _stage_player(root, "hermit", "sep_hermit_arena")
	var pch: Node = ph.get_node("Combat")
	pch.set("spirituality", 0.0)
	EB.clear()
	pch.on_attack_pressed(Vector2.RIGHT)
	_check(c, EB.events("spirit_empty").size() >= 1 and EB.events("weapon_empty").size() == 0,
		"an empty-spirit Hermit cast cues spirit_empty ONLY (weapon_empty=%d)" % EB.events("weapon_empty").size())
	_end_player(root, ph)
	# (b) Hunter, empty ammo (weapon still carried), full spirit.
	var pu: Node = _stage_player(root, "hunter", "sep_hunter_arena")
	var pcu: Node = pu.get_node("Combat")
	pcu.proxy.inventory.erase("revolver_round")
	EB.clear()
	pcu.on_attack_pressed(Vector2.RIGHT)
	_check(c, EB.events("weapon_empty").size() >= 1 and EB.events("spirit_empty").size() == 0,
		"an empty-ammo Hunter cast cues weapon_empty ONLY (spirit_empty=%d)" % EB.events("spirit_empty").size())
	_end_player(root, pu)

# T2c --------------------------------------------------------------------------------------------
## Flash-gate parity with the ammo cue: with hit_flash ON the CombatFeedback flash fires; with it OFF
## the flash is a verified no-op — but the spirit_empty EVENT fires either way (the cue is never gated
## out). RED at HEAD: no spirit_empty event fires at all.
static func _t_flash_gate_parity(c: Dictionary, root: Node) -> void:
	print("[M34 T2c: hit_flash gates the spirit-empty FLASH, never the EVENT (cue not suppressed)]")
	var EB: Object = root.get_node("/root/EventBus")
	var S: Object = root.get_node_or_null("/root/Settings")
	var FB: Object = root.get_node_or_null("/root/CombatFeedback")
	if S == null or FB == null:
		_check(c, false, "Settings + CombatFeedback available for the flash-gate parity test")
		return
	var p: Node = _stage_player(root, "hermit", "flash_gate_arena")
	var pc: Node = p.get_node("Combat")
	pc.set("spirituality", 0.0)
	# hit_flash ON: the flash fires + the event fires.
	S.set_value("hit_flash", true)
	FB.reset_probe(); EB.clear()
	pc.on_attack_pressed(Vector2.RIGHT)
	_check(c, FB.last_flash_alpha() > 0.0,
		"hit_flash ON -> the spirit-empty flash fires (alpha=%.2f)" % FB.last_flash_alpha())
	_check(c, EB.events("spirit_empty").size() >= 1,
		"…and the spirit_empty event fires (%d)" % EB.events("spirit_empty").size())
	# hit_flash OFF: the flash is a no-op, but the event STILL fires.
	S.set_value("hit_flash", false)
	FB.reset_probe(); EB.clear()
	pc.on_attack_pressed(Vector2.RIGHT)
	_check(c, FB.last_flash_alpha() == 0.0,
		"hit_flash OFF -> the spirit-empty flash is a no-op (alpha=%.2f)" % FB.last_flash_alpha())
	_check(c, EB.events("spirit_empty").size() >= 1,
		"…but the spirit_empty event STILL fires — the cue is not suppressed (%d)" % EB.events("spirit_empty").size())
	S.reset_defaults()
	_end_player(root, p)

# T2d --------------------------------------------------------------------------------------------
## The HUD reads the cue on its OWN Spirit-bar channel: a spirit_empty (hit_flash on) arms the red
## Spirit-bar pulse (_spirit_empty_t) and _process paints the bar red; gated off it arms nothing (visual
## suppressed, exactly like the ammo-label pulse). RED at HEAD: CombatHUD has no spirit_empty case.
static func _t_hud_spirit_pulse(c: Dictionary, root: Node) -> void:
	print("[M34 T2d: the HUD pulses its OWN Spirit bar red on spirit_empty (hit_flash-gated visual)]")
	var EB: Object = root.get_node("/root/EventBus")
	var S: Object = root.get_node_or_null("/root/Settings")
	var hud: Node = load("res://ui/HUD.tscn").instantiate()
	root.add_child(hud)
	var chud: Node = hud.get_node_or_null("CombatHUD")
	_check(c, chud != null, "the persistent HUD carries the CombatHUD widgets")
	if chud == null:
		hud.free()
		return
	var bar: ProgressBar = chud.get_node("Vitals/Spirit/Bar")
	var base_mod: Color = bar.modulate   # the bar's normal theme tint (a lavender, NOT white)
	# hit_flash ON -> the pulse arms and _process paints the Spirit bar red (red has r > b; the base
	# lavender has r < b, so this genuinely distinguishes the pulse from the resting tint).
	if S != null:
		S.set_value("hit_flash", true)
	EB.emit_event("spirit_empty", {"caster": "player", "spirit": 0.0})
	_check(c, _field(chud, "_spirit_empty_t") > 0.0,
		"a spirit_empty (hit_flash on) arms the Spirit-bar pulse (_spirit_empty_t=%s)" % str(chud.get("_spirit_empty_t")))
	chud._process(0.05)
	_check(c, bar.modulate.r > bar.modulate.b,
		"…and _process paints the Spirit bar RED on its own channel (r>b: %s)" % str(bar.modulate))
	# …and it RESTORES the bar's normal tint once the pulse expires (never stuck red / clobbered to white).
	chud.set("_spirit_empty_t", 0.0)
	chud._process(0.5)
	_check(c, bar.modulate == base_mod,
		"…and restores the bar's normal tint once the pulse expires (%s)" % str(bar.modulate))
	# hit_flash OFF -> a spirit_empty arms NOTHING (visual gated, like the ammo pulse).
	if S != null:
		S.set_value("hit_flash", false)
	EB.emit_event("spirit_empty", {"caster": "player", "spirit": 0.0})
	_check(c, _field(chud, "_spirit_empty_t") == 0.0,
		"hit_flash OFF -> a spirit_empty does NOT arm the Spirit-bar pulse (visual gated)")
	if S != null:
		S.reset_defaults()
	hud.queue_free()
