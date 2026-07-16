extends SceneTree
## M29 — Combat CAMERA framing + limits + room-entry snap fix. Runs headless:
##   godot --headless --path tingen -s tests/test_combat_camera.gd
## Also folded into the main suite (run_tests.gd `_test_combat_camera`) via the SAME run_all()
## entry point, so both share one set of assertions.
##
## The camera is PRESENTATION ONLY: CameraRig never reads or writes combat state, meters, RNG, or
## anything the simulation observes, so combat_sim + run_combat_vectors stay byte-identical. Every
## time-based/visual effect (offset framing, zoom tween, reset_smoothing) is LIVE-ONLY, gated behind
## _is_live() exactly like CombatFeedback. This harness asserts only the MATH + the snap-state
## invariant — never any pixel motion:
##   B1 LIMITS   : the painted-map rect is derived from the authored ground (MapProjection / the City
##                 ground sprite), and clamp_center keeps the camera's VIEW inside that rect.
##   B2 REFRAME  : on combat, the desired center is the player↔threat midpoint with a gentle zoom-IN.
##   B3 LOOKAHEAD: the camera offset leads toward the mouse-aim (reusing PlayerCombat.aim_dir()).
##   B4 SNAP FIX : a (re-)instanced / room-entered camera is snap-pending so its first frame jumps to
##                 the target (reset_smoothing) instead of gliding in — the fix for the per-room snap.

func _init() -> void:
	await process_frame
	await process_frame
	# N1 (sprint safety): sandbox EVERY persistent path (meta/save/settings/hints/playlog) into
	# user://test_sandbox/<run>/ and arm the write guard — see src/TestSandbox.gd.
	preload("res://src/TestSandbox.gd").activate(root)
	var r := run_all()
	print("\n=== combat_camera: %d passed, %d failed ===" % [int(r["passed"]), int(r["failed"])])
	quit(1 if int(r["failed"]) > 0 else 0)

## The one entry point (returns {passed, failed}); folded into run_tests.gd. Pure (no awaits) so
## callers invoke it directly. Loads CameraRig via load() (not the class_name) so this file still
## PARSES when the feature is absent — a missing script fails the asserts cleanly (feature missing),
## never a parse abort.
static func run_all() -> Dictionary:
	var c := {"passed": 0, "failed": 0}
	var Rig: Variant = load("res://src/CameraRig.gd")
	_check(c, Rig != null, "src/CameraRig.gd exists and loads (presentation-only camera brain)")
	if Rig == null:
		_check(c, false, "B1 LIMITS: city_map_rect + clamp_center keep the view inside the painted map (CameraRig missing)")
		_check(c, false, "B2 REFRAME: reframe_target midpoint + gentle combat zoom-in (CameraRig missing)")
		_check(c, false, "B3 LOOKAHEAD: lookahead_offset leads toward the aim (CameraRig missing)")
		_check(c, false, "B4 SNAP FIX: snap-pending mechanism prevents the room-entry glide (CameraRig missing)")
		return c

	var rig: Object = Rig.new()

	# ---- B1: LIMITS (derive the painted extents; clamp so the VIEW never shows past them) --------
	print("[B1: camera limits — derived map rect + view clamp]")
	var authored := Rect2(Vector2.ZERO, MapProjection.MAP_SIZE * MapProjection.CITY_SCALE)
	var city_rect: Rect2 = rig.city_map_rect()
	_check(c, _req(city_rect, Rect2(0, 0, 6270, 6270), 0.5),
		"B1: city_map_rect() = (0,0,6270,6270) — the painted City extents")
	_check(c, _req(city_rect, authored, 0.001),
		"B1: city_map_rect() reads the AUTHORED MapProjection world-rect (not a guessed literal)")
	# Derive the same rect straight from the scene's authored ground sprite — proves it is not hardcoded.
	var city: Node = (load("res://scenes/City.tscn") as PackedScene).instantiate()
	var derived: Rect2 = rig.derive_map_rect(city)
	_check(c, _req(derived, city_rect, 1.0),
		"B1: derive_map_rect(City) matches the painted ground sprite extents (derived, not hardcoded)")
	city.free()
	# The clamp math: half of a 1920x1080 view at zoom 1.
	var hv := Vector2(960.0, 540.0)
	var past_br: Vector2 = rig.clamp_center(Vector2(99999.0, 99999.0), city_rect, hv)
	_check(c, _veq(past_br, Vector2(6270.0 - 960.0, 6270.0 - 540.0), 0.001),
		"B1: a target past the SE corner clamps so the view stays inside the map")
	var past_tl: Vector2 = rig.clamp_center(Vector2(-99999.0, -99999.0), city_rect, hv)
	_check(c, _veq(past_tl, Vector2(960.0, 540.0), 0.001),
		"B1: a target past the NW corner clamps so the view stays inside the map")
	var inside: Vector2 = rig.clamp_center(Vector2(3135.0, 3135.0), city_rect, hv)
	_check(c, _veq(inside, Vector2(3135.0, 3135.0), 0.001),
		"B1: an in-bounds target passes through unchanged")
	# Prove the clamped VIEW rect is a subset of the map rect (the real invariant: no painting past the edge).
	var vmin := past_br - hv
	var vmax := past_br + hv
	_check(c, vmin.x >= city_rect.position.x - 0.001 and vmin.y >= city_rect.position.y - 0.001
			and vmax.x <= city_rect.end.x + 0.001 and vmax.y <= city_rect.end.y + 0.001,
		"B1: the clamped view rect is a subset of the map rect")
	# A room smaller than the view on an axis -> center on the map (no jitter against impossible limits).
	var small := Rect2(0.0, 0.0, 1000.0, 1000.0)
	var small_c: Vector2 = rig.clamp_center(Vector2(99999.0, -99999.0), small, hv)
	_check(c, _veq(small_c, Vector2(500.0, 500.0), 0.001),
		"B1: when the room is smaller than the view, the camera centers on it")
	_check(c, _veq(rig.clamp_center(Vector2(99999.0, 99999.0), city_rect, hv), past_br, 0.0),
		"B1: clamp_center is pure/deterministic (same input -> same output)")

	# ---- B2: REFRAME (midpoint + gentle zoom-in) -------------------------------------------------
	print("[B2: combat reframe — player↔threat midpoint + gentle zoom-in]")
	var mid: Vector2 = rig.reframe_target(Vector2(100.0, 200.0), Vector2(300.0, 600.0))
	_check(c, _veq(mid, Vector2(200.0, 400.0), 0.001),
		"B2: reframe_target = the midpoint between the player and the active threat")
	var cz: Vector2 = rig.combat_zoom()
	_check(c, cz.x > 1.0 and is_equal_approx(cz.x, cz.y),
		"B2: combat zoom is a gentle UNIFORM zoom-IN (Godot zoom > 1 = closer)")
	_check(c, cz.x > float(rig.rest_zoom().x),
		"B2: the combat zoom is tighter than the resting zoom")

	# ---- B3: LOOKAHEAD (lead toward the mouse-aim) -----------------------------------------------
	print("[B3: mouse-aim lookahead — lead toward the aim, reusing PlayerCombat.aim_dir()]")
	var la_r: Vector2 = rig.lookahead_offset(Vector2.RIGHT, 96.0)
	_check(c, _veq(la_r, Vector2(96.0, 0.0), 0.001),
		"B3: lookahead leads 96px along a rightward aim")
	var la_diag: Vector2 = rig.lookahead_offset(Vector2(1.0, 1.0), 100.0)
	_check(c, _veq(la_diag, Vector2(70.710678, 70.710678), 0.01),
		"B3: a non-unit aim is normalized before scaling (magnitude == distance)")
	var la_zero: Vector2 = rig.lookahead_offset(Vector2.ZERO, 96.0)
	_check(c, _veq(la_zero, Vector2.ZERO, 0.001),
		"B3: no aim -> no lookahead offset")
	var la_def: Vector2 = rig.lookahead_offset(Vector2.RIGHT)
	_check(c, _veq(la_def, Vector2(float(rig.lookahead_default_distance()), 0.0), 0.001),
		"B3: the default lookahead distance is applied when unspecified")
	var pc: Object = load("res://src/PlayerCombat.gd").new()
	_check(c, pc.has_method("aim_dir"),
		"B3: reuses the existing PlayerCombat.aim_dir() mouse-aim seam")
	pc.free()

	rig.free()

	# ---- B4: SNAP FIX (kill the per-room-entry smoothing glide) ----------------------------------
	print("[B4: room-entry snap fix — snap-pending on (re-)instantiation and re-entry]")
	var r1: Object = Rig.new()
	_check(c, r1.is_snap_pending() == true,
		"B4: a freshly (re-)instanced camera starts SNAP-PENDING (its first frame jumps to target)")
	var first: bool = r1.consume_snap()
	_check(c, first == true and r1.is_snap_pending() == false,
		"B4: consuming the snap fires the reset_smoothing() once, then the camera follows smoothly")
	_check(c, r1.consume_snap() == false,
		"B4: the snap is consumed exactly once (no repeated mid-room jump)")
	r1.arm_snap()
	_check(c, r1.is_snap_pending() == true,
		"B4: a room entry re-arms the snap — the invariant that eliminates the per-room glide")
	r1.free()

	# Drive the invariant through the REAL room_changed seam (not just arm_snap): the handler the
	# world's room_changed signal fires must itself re-arm the snap, else a live re-entry glides.
	var r2: Object = Rig.new()
	r2.consume_snap()  # clear the freshly-instanced snap so we isolate the re-entry case
	r2._on_room_changed("crypt", "res://scenes/SomeRoom.tscn")
	_check(c, r2.is_snap_pending() == true,
		"B4: the room_changed HANDLER itself re-arms the snap (live re-entry seam, not just arm_snap)")
	r2.free()

	return c

static func _check(c: Dictionary, cond: bool, label: String) -> void:
	if cond:
		c["passed"] = int(c["passed"]) + 1
		print("  PASS  %s" % label)
	else:
		c["failed"] = int(c["failed"]) + 1
		printerr("  FAIL  %s" % label)

static func _veq(a: Vector2, b: Vector2, eps: float) -> bool:
	return absf(a.x - b.x) <= eps and absf(a.y - b.y) <= eps

static func _req(a: Rect2, b: Rect2, eps: float) -> bool:
	return _veq(a.position, b.position, eps) and _veq(a.size, b.size, eps)
