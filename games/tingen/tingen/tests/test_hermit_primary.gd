extends SceneTree
## M34 — the HERMIT'S LIVE COMBAT IDENTITY (the headline fix). The bug this pins: at HEAD
## PlayerCombat._primary_attack_id() short-circuited `combat_form == "player" -> revolver_shot`, so a
## LIVE Hermit-kitted player (same "player" form, a swapped KIT) fired a REVOLVER (ammo) — its
## star_brand / ward_circle spirit arts had NO live input binding and the M31 spirituality pool was
## barely exercised in real play. This harness drives the REAL primary-attack input (on_attack_pressed —
## the exact path _unhandled_input's "attack" action calls) for a Hermit build and a Hunter build and
## asserts the wire is correct + engine-neutral (the primary is the worn KIT's first offensive art, not a
## pathway/NPC branch): a Hermit CASTS star_brand (spirit debited, no revolver round spent); a Hunter
## still FIRES revolver_shot (ammo spent, spirit untouched).
## Run: godot --headless --path tingen -s tests/test_hermit_primary.gd
## Also folded into the main suite (run_tests.gd `_test_hermit_primary`) via the SAME run_all() entry.
##
## Covers (TDD):
##  P1a RED  — a Hermit-kitted player's attack button casts star_brand (its spirit primary), debiting
##             the spirituality pool and spending NO revolver round (RED: fires revolver_shot).
##  P1b GUARD — a Hunter-kitted player's attack button still fires revolver_shot (ammo, no spirit)
##             (stays GREEN before + after — proves the fix is Hunter-neutral, no primary regressed).
##  P5  RED  — the ammo-free MELEE FLOOR is kit-aware too: a Hermit "player" form authors NO free strike
##             (_melee_floor_id()=="", the button inert — its damage floor is spirit-funded star_brand);
##             a Hunter form keeps pistol_whip. (RED at HEAD: both return "pistol_whip".)

func _init() -> void:
	await process_frame
	await process_frame
	# B3 (retro): NEVER touch the player's REAL persistent profile (user://meta.json) — redirect
	# the meta slot to a test-scoped file before anything drives RunManager (tests/test_meta_isolation.gd).
	# N1 (sprint safety): sandbox EVERY persistent path (meta/save/settings/hints/playlog) into
	# user://test_sandbox/<run>/ and arm the write guard — see src/TestSandbox.gd.
	preload("res://src/TestSandbox.gd").activate(root)
	var r: Dictionary = run_all()
	print("\n=== test_hermit_primary: %d passed, %d failed ===" % [int(r["passed"]), int(r["failed"])])
	quit(1 if int(r["failed"]) > 0 else 0)

## The one entry point (returns {passed, failed}); folded into run_tests.gd.
static func run_all() -> Dictionary:
	var c := {"passed": 0, "failed": 0}
	var root: Node = (Engine.get_main_loop() as SceneTree).root
	_t_hermit_primary_casts_star_brand(c, root)
	_t_hunter_primary_still_revolver(c, root)
	_t_melee_floor_kit_aware(c, root)
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

## A win writes the Hermit unlock into the persistent meta (so select_pathway/start_run honor it).
static func _unlock_hermit(RM: Object) -> void:
	RM.reset_meta()
	RM.start_run()
	RM.end_run("win", {"outcome": "descent_stopped"})
	RM.reload_meta()

## Stage a LIVE run of `pathway`, then instantiate the REAL Player scene (its Combat child binds a fresh
## proxy to a live CombatExecutor) in `room`. Returns the player node; the Combat node is `p/Combat`.
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

# P1a --------------------------------------------------------------------------------------------
## A LIVE Hermit build: the attack button must cast star_brand (its spirit primary), debit the
## spirituality pool, and spend NO revolver round. RED at HEAD: _primary_attack_id short-circuits the
## "player" form to revolver_shot, so the attack fires the loadout revolver instead (ammo 12 -> 11).
static func _t_hermit_primary_casts_star_brand(c: Dictionary, root: Node) -> void:
	print("[M34 P1a: a LIVE Hermit-kitted player's attack button casts star_brand (spirit), not a revolver]")
	var P: Object = root.get_node("/root/Progression")
	var p: Node = _stage_player(root, "hermit", "hermit_primary_arena")
	var pc: Node = p.get_node("Combat")
	_check(c, String(P.pathway()) == "hermit", "the staged run is a Hermit build (pathway == hermit)")
	_check(c, String(pc._primary_attack_id()) == "star_brand",
		"the attack button's primary resolves to star_brand for the Hermit kit (RED: hard-coded revolver_shot)")
	var spirit_before: float = float(pc.get("spirituality"))
	var ammo_before: int = pc.proxy.item_count("revolver_round")
	var art: String = _drive_attack_capture(root, pc)
	_check(c, art == "star_brand",
		"the REAL attack input started a star_brand cast on the player proxy (got '%s')" % art)
	_check(c, float(pc.get("spirituality")) < spirit_before,
		"…debiting the spirituality pool (%.0f -> %.0f) — the star primary is spirit-funded"
			% [spirit_before, float(pc.get("spirituality"))])
	_check(c, pc.proxy.item_count("revolver_round") == ammo_before,
		"…and spending NO revolver round (ammo held at %d) — the Hermit no longer fires a gun" % ammo_before)
	_end_player(root, p)

# P1b GREEN-GUARD --------------------------------------------------------------------------------
## A LIVE Hunter build: the attack button must STILL fire revolver_shot (ammo), spirituality untouched.
## Stays GREEN before AND after the fix — the proof the kit-aware rewire is Hunter-neutral (no primary
## regressed for the always-available slice build; full_run's revolver_shot spine is safe).
static func _t_hunter_primary_still_revolver(c: Dictionary, root: Node) -> void:
	print("[M34 P1b GUARD: a LIVE Hunter-kitted player's attack button still fires revolver_shot (ammo, no spirit)]")
	var P: Object = root.get_node("/root/Progression")
	var p: Node = _stage_player(root, "hunter", "hunter_primary_arena")
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

# P5 --------------------------------------------------------------------------------------------
## The ammo-free MELEE FLOOR is kit-aware too. The Hermit "player" form authors NO free strike, so its
## melee button is inert (_melee_floor_id()=="" -> try_cast degrades to unknown_ability harmlessly) — its
## live damage floor is the spirit-funded star_brand primary (P1). The Hunter form keeps pistol_whip (its
## kit's free strike). RED at HEAD: the final fallback returns "pistol_whip" for both.
static func _t_melee_floor_kit_aware(c: Dictionary, root: Node) -> void:
	print("[M34 P5: the ammo-free melee floor is kit-aware — Hermit inert (\"\"), Hunter keeps pistol_whip]")
	var p_h: Node = _stage_player(root, "hermit", "hermit_melee_arena")
	var pc_h: Node = p_h.get_node("Combat")
	_check(c, String(pc_h._melee_floor_id()) == "",
		"a Hermit-kitted player authors NO free strike — _melee_floor_id() == \"\" (RED: \"pistol_whip\")")
	_end_player(root, p_h)

	var p_u: Node = _stage_player(root, "hunter", "hunter_melee_arena")
	var pc_u: Node = p_u.get_node("Combat")
	_check(c, String(pc_u._melee_floor_id()) == "pistol_whip",
		"a Hunter-kitted player keeps pistol_whip as its ammo-free melee floor")
	_end_player(root, p_u)
