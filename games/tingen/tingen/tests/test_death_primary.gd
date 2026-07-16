extends SceneTree
## N5 — the DEATH build's LIVE COMBAT IDENTITY (the M34 wire, proven for the THIRD pathway with zero
## new engine code). Drives the REAL primary-attack input (on_attack_pressed — the exact path
## _unhandled_input's "attack" action calls) for a Death build and a Hunter build and asserts the
## kit-aware wire holds: a Death-kitted player CASTS censer_ember (spirit debited via
## PlayerCombat.try_pay, NO revolver round spent); a Hunter still FIRES revolver_shot (ammo, no
## spirit); the ammo-free melee floor is kit-aware (Death inert "", Hunter pistol_whip); and a
## DRAINED pool refuses the cast `no_spirit` + emits the M34 spirit_empty cue — the third pathway
## rides the same generic spirit machinery, no pathway branch anywhere.
## Run: godot --headless --path tingen -s tests/test_death_primary.gd
## Also folded into the main suite (run_tests.gd `_test_death_primary`) via the SAME run_all() entry.

func _init() -> void:
	await process_frame
	await process_frame
	# B3 (retro): NEVER touch the player's REAL persistent profile (user://meta.json) — redirect
	# the meta slot to a test-scoped file before anything drives RunManager (tests/test_meta_isolation.gd).
	# N1 (sprint safety): sandbox EVERY persistent path (meta/save/settings/hints/playlog) into
	# user://test_sandbox/<run>/ and arm the write guard — see src/TestSandbox.gd.
	preload("res://src/TestSandbox.gd").activate(root)
	var r: Dictionary = run_all()
	print("\n=== test_death_primary: %d passed, %d failed ===" % [int(r["passed"]), int(r["failed"])])
	quit(1 if int(r["failed"]) > 0 else 0)

## The one entry point (returns {passed, failed}); folded into run_tests.gd.
static func run_all() -> Dictionary:
	var c := {"passed": 0, "failed": 0}
	var root: Node = (Engine.get_main_loop() as SceneTree).root
	_t_death_primary_casts_censer_ember(c, root)
	_t_hunter_primary_still_revolver(c, root)
	_t_melee_floor_kit_aware(c, root)
	_t_drained_pool_refuses_no_spirit(c, root)
	# Leave a clean Hunter world for whatever runs next in the shared suite.
	root.get_node("/root/RunManager").start_run()
	root.get_node("/root/Agents").rebuild()
	root.get_node("/root/Progression").select_pathway("hunter")
	return c

# --- helpers ------------------------------------------------------------------------------------
static func _check(c: Dictionary, cond: bool, label: String) -> void:
	if cond:
		c["passed"] = int(c["passed"]) + 1
		print("  PASS  %s" % label)
	else:
		c["failed"] = int(c["failed"]) + 1
		printerr("  FAIL  %s" % label)

## TWO wins write the Death unlock into the persistent meta (win 1 -> hermit, win 2 -> death).
static func _unlock_death(RM: Object) -> void:
	RM.reset_meta()
	for _i in 2:
		RM.start_run()
		RM.end_run("win", {"outcome": "descent_stopped"})
		RM.reload_meta()

## Stage a LIVE run of `pathway`, then instantiate the REAL Player scene (its Combat child binds a fresh
## proxy to a live CombatExecutor) in `room`. Returns the player node; the Combat node is `p/Combat`.
static func _stage_player(root: Node, pathway: String, room: String) -> Node:
	var RM: Object = root.get_node("/root/RunManager")
	var AG: Object = root.get_node("/root/Agents")
	if pathway == "death":
		_unlock_death(RM)
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

## Capture the ability id of the FIRST player cast_started emitted while driving `pc.on_attack_pressed`.
static func _drive_attack_capture(root: Node, pc: Node) -> String:
	var EB: Object = root.get_node("/root/EventBus")
	var cast := {"art": ""}
	var on_cast := func(ev: Dictionary) -> void:
		if String(ev.get("type", "")) != "ability_cast_started":
			return
		var d: Dictionary = ev.get("data", {}) if ev.get("data") is Dictionary else {}
		if String(d.get("caster", "")) == "player" and String(cast["art"]) == "":
			cast["art"] = String(d.get("ability", ""))
	EB.event_logged.connect(on_cast)
	pc.on_attack_pressed(Vector2.RIGHT)
	EB.event_logged.disconnect(on_cast)
	return String(cast["art"])

# P1 --------------------------------------------------------------------------------------------
## A LIVE Death build: the attack button must cast censer_ember (its spirit primary), debit the
## spirituality pool, and spend NO revolver round — the M34 kit-aware primary, data-only for the
## third pathway (censer_ember leads the authored kit row).
static func _t_death_primary_casts_censer_ember(c: Dictionary, root: Node) -> void:
	print("[N5 P1: a LIVE Death-kitted player's attack button casts censer_ember (spirit), not a revolver]")
	var P: Object = root.get_node("/root/Progression")
	var p: Node = _stage_player(root, "death", "death_primary_arena")
	var pc: Node = p.get_node("Combat")
	_check(c, String(P.pathway()) == "death", "the staged run is a Death build (pathway == death)")
	_check(c, String(pc._primary_attack_id()) == "censer_ember",
		"the attack button's primary resolves to censer_ember for the Death kit")
	var spirit_before: float = float(pc.get("spirituality"))
	var ammo_before: int = pc.proxy.item_count("revolver_round")
	var art: String = _drive_attack_capture(root, pc)
	_check(c, art == "censer_ember",
		"the REAL attack input started a censer_ember cast on the player proxy (got '%s')" % art)
	_check(c, float(pc.get("spirituality")) < spirit_before,
		"…debiting the spirituality pool (%.0f -> %.0f) — the censer primary is spirit-funded"
			% [spirit_before, float(pc.get("spirituality"))])
	_check(c, pc.proxy.item_count("revolver_round") == ammo_before,
		"…and spending NO revolver round (ammo held at %d) — the Corpse Collector fires no gun" % ammo_before)
	_end_player(root, p)

# GUARD -------------------------------------------------------------------------------------------
## A LIVE Hunter build: the attack button must STILL fire revolver_shot (ammo), spirituality untouched.
## The Hunter-neutrality guard — proves adding a third kit row regressed no primary.
static func _t_hunter_primary_still_revolver(c: Dictionary, root: Node) -> void:
	print("[N5 GUARD: a LIVE Hunter-kitted player's attack button still fires revolver_shot (ammo, no spirit)]")
	var P: Object = root.get_node("/root/Progression")
	var p: Node = _stage_player(root, "hunter", "hunter_primary_arena_n5")
	var pc: Node = p.get_node("Combat")
	_check(c, String(P.pathway()) == "hunter", "the staged run is a Hunter build (pathway == hunter)")
	_check(c, String(pc._primary_attack_id()) == "revolver_shot",
		"the attack button's primary stays revolver_shot for the Hunter kit")
	var spirit_before: float = float(pc.get("spirituality"))
	var ammo_before: int = pc.proxy.item_count("revolver_round")
	var art: String = _drive_attack_capture(root, pc)
	_check(c, art == "revolver_shot",
		"the REAL attack input started a revolver_shot cast on the player proxy (got '%s')" % art)
	_check(c, pc.proxy.item_count("revolver_round") == ammo_before - 1,
		"…spending one revolver round (ammo %d -> %d) — the gun still fires" % [ammo_before, pc.proxy.item_count("revolver_round")])
	_check(c, is_equal_approx(float(pc.get("spirituality")), spirit_before),
		"…and NOT touching the spirituality pool (still %.0f) — the Hunter is spirit-free" % float(pc.get("spirituality")))
	_end_player(root, p)

# MELEE FLOOR --------------------------------------------------------------------------------------
## The ammo-free MELEE FLOOR is kit-aware for the third kit too: the Death base kit authors NO
## strike-class art (§0 — same as the Hermit), so its melee button is deliberately inert (""); the
## Hunter form keeps pistol_whip.
static func _t_melee_floor_kit_aware(c: Dictionary, root: Node) -> void:
	print("[N5: the ammo-free melee floor is kit-aware — Death inert (\"\"), Hunter keeps pistol_whip]")
	var p_d: Node = _stage_player(root, "death", "death_melee_arena")
	var pc_d: Node = p_d.get_node("Combat")
	_check(c, String(pc_d._melee_floor_id()) == "",
		"a Death-kitted player authors NO free strike — _melee_floor_id() == \"\" (deliberately inert, the Hermit precedent)")
	_end_player(root, p_d)

	var p_u: Node = _stage_player(root, "hunter", "hunter_melee_arena_n5")
	var pc_u: Node = p_u.get_node("Combat")
	_check(c, String(pc_u._melee_floor_id()) == "pistol_whip",
		"a Hunter-kitted player keeps pistol_whip as its ammo-free melee floor")
	_end_player(root, p_u)

# NO_SPIRIT ----------------------------------------------------------------------------------------
## A DRAINED Death pool refuses the primary `no_spirit` (no cooldown burned, PlayerCombat.try_pay is
## the ONE enforcement seam) and emits the M34 spirit_empty cue — the third pathway inherits the
## whole dry-resource read with zero new code.
static func _t_drained_pool_refuses_no_spirit(c: Dictionary, root: Node) -> void:
	print("[N5: a drained Death pool refuses no_spirit + emits the spirit_empty cue (the M34 wire, third pathway)]")
	var EB: Object = root.get_node("/root/EventBus")
	var p: Node = _stage_player(root, "death", "death_no_spirit_arena")
	var pc: Node = p.get_node("Combat")
	pc.set("spirituality", 0.0)
	EB.clear()
	var r_attack: Dictionary = pc.on_attack_pressed(Vector2.RIGHT)
	_check(c, String(r_attack.get("reason", "")) == "no_spirit",
		"the drained Death ATTACK (censer_ember) is refused no_spirit (got '%s')" % String(r_attack.get("reason", "")))
	_check(c, EB.events("spirit_empty").size() >= 1,
		"…and the refusal emitted the spirit_empty cue (the M34 dry-spirit read, no new code)")
	_end_player(root, p)
