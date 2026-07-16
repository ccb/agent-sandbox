extends SceneTree
## P5 (experiential wave) — the CITY AS A PLACE (logic layer).
##
## Audit finding: gorgeous painted buildings sit on the live City like cardboard — no day/night
## tint on City.tscn (the DayNightTint script existed only in the orphaned CityBlocks.tscn), no
## lamp glow after dark, a district map with a player dot but NO marker for the current lead, and
## a top-bar clock frozen at "Morning - 08:00" for the whole run. This harness pins the HEADLESS
## LOGIC that backs the fixes (the rendered pixels are proven by tests/screenshot_probe.gd):
##
##   (a) DayNightTint: PHASE_TINTS covers every authored Clock phase; the palette is occult-noir
##       (cold blue-grey nights, warm amber dusk, neutral day); tint_for_phase() is the pure seam.
##   (b) the LIVE City.tscn carries the DayNightTint CanvasModulate, and headless it applies the
##       phase tint INSTANTLY on phase_changed (state-level phase->tint mapping, no per-frame lerp).
##   (c) StreetLamps: lit_for_phase() truth table (dusk/night/late-night on, day off); the lamps
##       are DATA (city_layout.json "lamps", map-image space) — enough of them, all inside the
##       world, none buried in a building collider; the live City carries the node; HEADLESS the
##       node mounts ZERO glow children (live-only presentation — sims stay byte-identical).
##   (d) LeadSystem.current_lead(): deterministic pick (a followed lead wins, else the first hot
##       open lead, else the first open lead, else {}); hidden leads never surface as current.
##   (e) lead map_pos is DATA (leads.json): the guaranteed butcher lead pins inside the Iron Cross
##       district's map_polygon; a where_candidates lead carries the map_pos of its PICKED
##       candidate; a cold-respawned lead DROPS map_pos (the subject moved — the trail is vague);
##       map_pos rides the save/load round-trip.
##   (f) DistrictMap.lead_pin_pos(): the pure lead->pin-projection seam ({} / missing -> INF).
##   (g) CrowdDressing: the ambient standee clusters are DATA (city_layout.json "crowds"); every
##       figure's art exists under assets/characters/; every figure stands INSIDE the world, clear
##       of building colliders, >=40 world px from EVERY scheduled NPC waypoint and >=60 from every
##       door/portal; the live City carries the node; HEADLESS it mounts ZERO standee children.
##   (h) the HUD top-bar clock follows the LIVE Clock (set_time -> the label reads the new phase
##       and time, not the frozen boot string).
##
## Standalone: godot --headless --path tingen -s tests/test_city_place.gd
## Also folded into the main suite (run_tests.gd `_test_city_place`) via the SAME run_all() entry.

func _init() -> void:
	await process_frame
	await process_frame
	# Never touch the player's REAL persistent profile (see tests/test_meta_isolation.gd).
	# N1 (sprint safety): sandbox EVERY persistent path (meta/save/settings/hints/playlog) into
	# user://test_sandbox/<run>/ and arm the write guard — see src/TestSandbox.gd.
	preload("res://src/TestSandbox.gd").activate(root)
	var r: Dictionary = run_all()
	print("\n=== test_city_place: %d passed, %d failed ===" % [int(r["passed"]), int(r["failed"])])
	quit(1 if int(r["failed"]) > 0 else 0)

## The one entry point (returns {passed, failed}); folded into run_tests.gd.
static func run_all() -> Dictionary:
	var c := {"passed": 0, "failed": 0}
	var root: Node = (Engine.get_main_loop() as SceneTree).root
	var clock: Node = root.get_node("/root/Clock")
	var day0: int = int(clock.day)
	var min0: int = int(clock.minute_of_day)
	_a_tint_palette(c, root)
	_b_city_wires_tint(c, root)
	_c_street_lamps(c, root)
	_d_current_lead(c, root)
	_e_lead_map_pos(c, root)
	_f_lead_pin_pos(c)
	_g_crowd_dressing(c, root)
	_h_hud_clock_follows(c, root)
	# Leave the clock and world exactly as found for whatever runs next in the shared suite.
	clock.set_time(day0, min0)
	root.get_node("/root/RunManager").start_run()
	root.get_node("/root/Agents").rebuild()
	return c

static func _check(c: Dictionary, cond: bool, label: String) -> void:
	if cond:
		c["passed"] = int(c["passed"]) + 1
		print("  PASS  %s" % label)
	else:
		c["failed"] = int(c["failed"]) + 1
		printerr("  FAIL  %s" % label)

static func _layout() -> Dictionary:
	var parsed: Variant = JSON.parse_string(FileAccess.get_file_as_string("res://data/city_layout.json"))
	return parsed if parsed is Dictionary else {}

## Every RectangleShape2D CollisionShape2D under a StaticBody2D (building bodies + edge walls) —
## the same blocker set run_tests' city-placements legality walks (Area2D doors are not blockers).
static func _collect_rect_colliders(node: Node, out: Array) -> void:
	for ch in node.get_children():
		if ch is CollisionShape2D and (ch as CollisionShape2D).shape is RectangleShape2D \
				and ch.get_parent() is StaticBody2D:
			out.append(ch)
		_collect_rect_colliders(ch, out)

static func _point_in_any_collider(p: Vector2, colliders: Array) -> String:
	for cn in colliders:
		var cs := cn as CollisionShape2D
		var local: Vector2 = cs.global_transform.affine_inverse() * p
		var half: Vector2 = (cs.shape as RectangleShape2D).size * 0.5
		if absf(local.x) <= half.x and absf(local.y) <= half.y:
			return String(cs.get_parent().name) + "/" + String(cs.name)
	return ""

## Every door/portal Area2D world position in the live City (crowd standees must not squat on one).
static func _door_positions(node: Node, out: Array) -> void:
	for ch in node.get_children():
		if ch is Area2D:
			out.append((ch as Node2D).global_position)
		_door_positions(ch, out)

# (a) --------------------------------------------------------------------------------------------
static func _a_tint_palette(c: Dictionary, root: Node) -> void:
	print("[city place (a): DayNightTint covers every Clock phase with an occult-noir palette]")
	var TintScript: GDScript = load("res://src/DayNightTint.gd")
	_check(c, TintScript != null, "src/DayNightTint.gd exists")
	if TintScript == null:
		return
	var tints: Dictionary = TintScript.PHASE_TINTS
	# Every authored Clock phase has a tint (derive the phase set from Clock's own bounds — no
	# drift). Autoload via /root — bare identifiers don't resolve under the -s harness.
	var phases: Dictionary = {}
	for entry in (root.get_node("/root/Clock").PHASE_BOUNDS as Array):
		phases[String(entry[1])] = true
	for ph in phases:
		_check(c, tints.has(ph), "PHASE_TINTS maps the authored Clock phase '%s'" % ph)
	_check(c, TintScript.has_method("tint_for_phase"), "DayNightTint exposes the pure tint_for_phase() seam")
	if not TintScript.has_method("tint_for_phase"):
		return
	var night: Color = TintScript.tint_for_phase("night")
	var late: Color = TintScript.tint_for_phase("late-night")
	var dusk: Color = TintScript.tint_for_phase("dusk")
	var noon: Color = TintScript.tint_for_phase("afternoon")
	_check(c, night.b > night.r and night.b > night.g, "night is COLD blue-grey (b %.2f > r %.2f)" % [night.b, night.r])
	_check(c, late.b > late.r and late.v < night.v, "late-night is colder and darker still")
	_check(c, dusk.r > dusk.b, "dusk is WARM amber (r %.2f > b %.2f)" % [dusk.r, dusk.b])
	_check(c, noon.is_equal_approx(Color.WHITE), "afternoon is the neutral daylight anchor (white)")
	_check(c, TintScript.tint_for_phase("no_such_phase").is_equal_approx(Color.WHITE),
		"an unknown phase falls back to white (never a black screen)")

# (b) --------------------------------------------------------------------------------------------
static func _b_city_wires_tint(c: Dictionary, root: Node) -> void:
	print("[city place (b): the LIVE City.tscn carries the tint and applies phases instantly headless]")
	var clock: Node = root.get_node("/root/Clock")
	var day0: int = int(clock.day)
	var min0: int = int(clock.minute_of_day)
	var scene: Node = (load("res://scenes/City.tscn") as PackedScene).instantiate()
	# Added to the tree so _ready wiring runs; freed synchronously below, BEFORE CitySummoning's
	# deferred bootstrap can fire (the run_tests city-legality pattern).
	root.add_child(scene)
	var tintn: Node = scene.get_node_or_null("DayNightTint")
	_check(c, tintn is CanvasModulate, "City.tscn has the DayNightTint CanvasModulate node")
	if tintn is CanvasModulate:
		var TintScript: GDScript = load("res://src/DayNightTint.gd")
		_check(c, tintn.get_script() == TintScript, "…driven by src/DayNightTint.gd")
		clock.set_time(day0, 21 * 60)   # 21:00 -> "night"
		var want: Color = TintScript.tint_for_phase("night")
		_check(c, (tintn as CanvasModulate).color.is_equal_approx(want),
			"headless phase_changed applies the night tint INSTANTLY (state-level mapping, no lerp)")
		clock.set_time(day0, 13 * 60)   # 13:00 -> "afternoon"
		_check(c, (tintn as CanvasModulate).color.is_equal_approx(TintScript.tint_for_phase("afternoon")),
			"…and back to the neutral afternoon tint on the next phase change")
	clock.set_time(day0, min0)
	scene.free()   # synchronous, before CitySummoning's deferred bootstrap

# (c) --------------------------------------------------------------------------------------------
static func _c_street_lamps(c: Dictionary, root: Node) -> void:
	print("[city place (c): street lamps — phase truth table, legal DATA spots, headless-inert]")
	if not ResourceLoader.exists("res://src/StreetLamps.gd"):
		_check(c, false, "src/StreetLamps.gd exists (the lamp-glow node)")
		return
	var Lamps: GDScript = load("res://src/StreetLamps.gd")
	for ph_on in ["dusk", "night", "late-night"]:
		_check(c, bool(Lamps.lit_for_phase(ph_on)), "lamps are LIT at %s" % ph_on)
	for ph_off in ["early-morning", "morning", "afternoon"]:
		_check(c, not bool(Lamps.lit_for_phase(ph_off)), "lamps are OFF at %s" % ph_off)
	# The lamp spots are DATA in the canonical map-image space.
	var lamps: Array = _layout().get("lamps", [])
	_check(c, lamps.size() >= 6, "city_layout.json authors >=6 lamp spots (got %d)" % lamps.size())
	var map_rect := Rect2(Vector2.ZERO, MapProjection.MAP_SIZE)
	var scene: Node = (load("res://scenes/City.tscn") as PackedScene).instantiate()
	root.add_child(scene)
	var lampn: Node = scene.get_node_or_null("StreetLamps")
	_check(c, lampn != null and lampn.get_script() == Lamps, "City.tscn has the StreetLamps node")
	var colliders: Array = []
	_collect_rect_colliders(scene, colliders)
	var bad_bounds: Array = []
	var buried: Array = []
	for i in lamps.size():
		var lp: Array = lamps[i]
		var mp := Vector2(float(lp[0]), float(lp[1]))
		if not map_rect.has_point(mp):
			bad_bounds.append(i)
		var hit := _point_in_any_collider(MapProjection.map_to_world(mp), colliders)
		if hit != "":
			buried.append("lamp %d inside %s" % [i, hit])
	_check(c, bad_bounds.is_empty(), "every lamp spot is inside the map image " + str(bad_bounds))
	_check(c, buried.is_empty(), "no lamp glow is buried in a building collider " + str(buried))
	if lampn != null:
		_check(c, lampn.get_child_count() == 0,
			"HEADLESS: the StreetLamps node mounts ZERO glow children (live-only presentation)")
		_check(c, lampn.has_method("glow_count") and int(lampn.glow_count()) == 0,
			"…and glow_count() reads 0 headless (the live count is probe-proven)")
	scene.free()

# (d) --------------------------------------------------------------------------------------------
static func _d_current_lead(c: Dictionary, root: Node) -> void:
	print("[city place (d): LeadSystem.current_lead — followed > first hot open > first open, never hidden]")
	var LS: Object = root.get_node("/root/LeadSystem")
	_check(c, LS.has_method("current_lead"), "LeadSystem exposes current_lead()")
	if not LS.has_method("current_lead"):
		return
	LS.slot_run(4242)
	var cur: Dictionary = LS.current_lead()
	_check(c, String(cur.get("id", "")) == "butcher_iron_cross",
		"at run start the current lead is the guaranteed HOT butcher opener (got '%s')" % String(cur.get("id", "")))
	# A FOLLOWED lead beats the hot opener (the player has committed to it).
	var other_id := ""
	for lead in (LS.active_leads() as Array):
		if String(lead.get("id", "")) != "butcher_iron_cross":
			other_id = String(lead.get("id", ""))
			break
	if other_id != "":
		LS.follow(other_id)
		_check(c, String(LS.current_lead().get("id", "")) == other_id,
			"a FOLLOWED lead becomes the current lead ('%s')" % other_id)
		LS.resolve(other_id)
		_check(c, String(LS.current_lead().get("id", "")) == "butcher_iron_cross",
			"resolving it falls back to the hot opener")
	# A hidden (after_advance-gated) lead is never current, even when everything else is resolved.
	for lead in (LS.active_leads() as Array):
		LS.resolve(String(lead.get("id", "")))
	var after: Dictionary = LS.current_lead()
	_check(c, after.is_empty() or String(after.get("state", "")) != "hidden",
		"a hidden after_advance lead is NEVER the current lead")
	LS.reset()
	_check(c, (LS.current_lead() as Dictionary).is_empty(), "no leads -> current_lead() is {}")

# (e) --------------------------------------------------------------------------------------------
static func _e_lead_map_pos(c: Dictionary, root: Node) -> void:
	print("[city place (e): lead map_pos is DATA — authored pin spots ride slotting, respawn drops them]")
	var LS: Object = root.get_node("/root/LeadSystem")
	LS.slot_run(4242)
	var butcher: Dictionary = LS.get_lead("butcher_iron_cross")
	_check(c, butcher.get("map_pos") is Array and (butcher["map_pos"] as Array).size() == 2,
		"the butcher lead carries an authored map_pos [x, y]")
	if butcher.get("map_pos") is Array and (butcher["map_pos"] as Array).size() == 2:
		var mp := Vector2(float(butcher["map_pos"][0]), float(butcher["map_pos"][1]))
		# The pin must land inside the Iron Cross district's own map_polygon (data vs data).
		var districts: Array = JSON.parse_string(FileAccess.get_file_as_string("res://data/districts.json"))
		var poly := PackedVector2Array()
		for d in districts:
			if String((d as Dictionary).get("id", "")) == "iron_cross":
				var raw: Array = (d as Dictionary).get("map_polygon", [])
				for i in range(0, raw.size() - 1, 2):
					poly.append(Vector2(float(raw[i]), float(raw[i + 1])))
		_check(c, poly.size() >= 3 and Geometry2D.is_point_in_polygon(mp, poly),
			"the butcher pin lands INSIDE the Iron Cross district polygon (%s)" % str(mp))
	# A where_candidates lead pins the PICKED candidate's own spot — across seeds, the resolved
	# where_hint and map_pos always come from the SAME candidate row (data linkage, no drift).
	var tmpl_by_id: Dictionary = {}
	for t in LS.TEMPLATES:
		tmpl_by_id[String((t as Dictionary).get("id", ""))] = t
	var courier_tmpl: Dictionary = tmpl_by_id.get("cult_courier", {})
	var cand_pins: Dictionary = {}
	for cand in (courier_tmpl.get("where_candidates", []) as Array):
		cand_pins[String((cand as Dictionary).get("value", ""))] = (cand as Dictionary).get("map_pos", null)
	var linked := true
	var seen_courier := false
	for seed in [1, 2, 3, 5, 8, 13, 21, 34]:
		LS.slot_run(seed)
		var courier: Dictionary = LS.get_lead("cult_courier")
		if courier.is_empty():
			continue
		seen_courier = true
		var want: Variant = cand_pins.get(String(courier.get("where_hint", "")), null)
		if not (want is Array) or str(courier.get("map_pos")) != str(want):
			linked = false
	_check(c, seen_courier, "(staging) the courier lead slotted for at least one probe seed")
	_check(c, linked, "a candidate-pool lead's map_pos always matches its PICKED candidate's authored pin")
	# A cold respawn is the subject MOVING — the fresh lead has no authored pin any more.
	LS.slot_run(4242)
	var lead0: Dictionary = LS.get_lead("butcher_iron_cross")
	_check(c, not lead0.is_empty(), "(staging) the butcher lead is live before the perish tick")
	LS.perish_tick(int(lead0.get("spawned_day", 1)) + 5)
	var fresh_id := ""
	for lead in (LS.active_leads() as Array):
		if String(lead.get("id", "")).begins_with("butcher_iron_cross_"):
			fresh_id = String(lead.get("id", ""))
	_check(c, fresh_id != "", "(staging) the cold butcher lead re-emerged elsewhere")
	if fresh_id != "":
		var fresh: Dictionary = LS.get_lead(fresh_id)
		_check(c, (fresh.get("map_pos", []) as Array).is_empty(),
			"the re-emerged lead DROPPED its map pin (the subject moved — the trail went vague)")
	# map_pos survives the snapshot/restore round-trip (the nightly checkpoint).
	LS.slot_run(4242)
	var snap: Dictionary = LS.to_dict()
	LS.reset()
	LS.from_dict(snap)
	var back: Dictionary = LS.get_lead("butcher_iron_cross")
	_check(c, back.get("map_pos") is Array and (back["map_pos"] as Array).size() == 2,
		"map_pos rides the to_dict/from_dict checkpoint round-trip")

# (f) --------------------------------------------------------------------------------------------
static func _f_lead_pin_pos(c: Dictionary) -> void:
	print("[city place (f): DistrictMap.lead_pin_pos — the pure lead->pin seam]")
	var DM: GDScript = load("res://src/DistrictMap.gd")
	_check(c, DM.has_method("lead_pin_pos"), "DistrictMap exposes the static lead_pin_pos() seam")
	if not DM.has_method("lead_pin_pos"):
		return
	_check(c, DM.lead_pin_pos({}) == Vector2.INF, "no lead -> no pin (Vector2.INF)")
	_check(c, DM.lead_pin_pos({"map_pos": []}) == Vector2.INF, "an empty map_pos -> no pin")
	_check(c, DM.lead_pin_pos({"map_pos": [718.0, 730.0]}) == Vector2(718.0, 730.0),
		"an authored [x, y] projects to its map-image point")

# (g) --------------------------------------------------------------------------------------------
static func _g_crowd_dressing(c: Dictionary, root: Node) -> void:
	print("[city place (g): crowd clusters — data-driven standees, legal spots, headless-inert]")
	if not ResourceLoader.exists("res://src/CrowdDressing.gd"):
		_check(c, false, "src/CrowdDressing.gd exists (the ambient standee dressing node)")
		return
	var Crowd: GDScript = load("res://src/CrowdDressing.gd")
	var clusters: Array = _layout().get("crowds", [])
	_check(c, clusters.size() >= 3, "city_layout.json authors >=3 crowd clusters (got %d)" % clusters.size())
	var ids: Array = []
	for cl in clusters:
		ids.append(String((cl as Dictionary).get("id", "")))
	for want_id in ["market", "docks", "tavern"]:
		_check(c, ids.has(want_id), "a '%s' cluster is authored (the audit's dead-space spots)" % want_id)
	# Every figure's art actually exists (assets/characters/<art>.png, the NPC body convention).
	var missing_art: Array = []
	var fig_count := 0
	for cl in clusters:
		for fig in ((cl as Dictionary).get("figures", []) as Array):
			fig_count += 1
			var art := String((fig as Dictionary).get("art", ""))
			if art == "" or not ResourceLoader.exists("res://assets/characters/%s.png" % art):
				missing_art.append(art)
	_check(c, fig_count >= 6, "the clusters stage >=6 standees total (got %d)" % fig_count)
	_check(c, missing_art.is_empty(), "every standee's art exists under assets/characters/ " + str(missing_art))
	# LEGALITY, exactly like the fill-blocks work: inside the world, not buried in a collider,
	# clear of EVERY scheduled NPC waypoint (>=40) and every door/portal Area2D (>=60).
	var scene: Node = (load("res://scenes/City.tscn") as PackedScene).instantiate()
	root.add_child(scene)
	var crowd_node: Node = scene.get_node_or_null("CrowdDressing")
	_check(c, crowd_node != null and crowd_node.get_script() == Crowd, "City.tscn has the CrowdDressing node")
	var colliders: Array = []
	_collect_rect_colliders(scene, colliders)
	var doors: Array = []
	_door_positions(scene, doors)
	var npc_defs: Dictionary = JSON.parse_string(FileAccess.get_file_as_string("res://data/npcs.json"))
	var waypoints: Array = []
	for aid in npc_defs:
		var sched: Dictionary = (npc_defs[aid] as Dictionary).get("schedule", {})
		for ph in sched:
			var arr: Array = sched[ph]
			waypoints.append(Vector2(float(arr[0]), float(arr[1])))
	var world_rect := Rect2(Vector2.ZERO, MapProjection.MAP_SIZE * MapProjection.CITY_SCALE)
	var illegal: Array = []
	for cl in clusters:
		var cd := cl as Dictionary
		var base: Vector2 = MapProjection.map_to_world(
			Vector2(float(cd["pos"][0]), float(cd["pos"][1]))) if cd.get("pos") is Array else Vector2.INF
		for fig in (cd.get("figures", []) as Array):
			var fd := fig as Dictionary
			var p: Vector2 = base + Vector2(float(fd.get("dx", 0)), float(fd.get("dy", 0)))
			if not world_rect.has_point(p):
				illegal.append("%s out of world" % str(p))
			var hit := _point_in_any_collider(p, colliders)
			if hit != "":
				illegal.append("%s inside %s" % [str(p), hit])
			for wp in waypoints:
				if p.distance_to(wp) < 40.0:
					illegal.append("%s within 40 of waypoint %s" % [str(p), str(wp)])
			for dp in doors:
				if p.distance_to(dp) < 60.0:
					illegal.append("%s within 60 of door %s" % [str(p), str(dp)])
	_check(c, illegal.is_empty(), "every standee stands LEGALLY (clear of colliders/waypoints/doors) " + str(illegal))
	if crowd_node != null:
		_check(c, crowd_node.get_child_count() == 0,
			"HEADLESS: the CrowdDressing node mounts ZERO standees (live-only dressing)")
		_check(c, crowd_node.has_method("figure_count") and int(crowd_node.figure_count()) == 0,
			"…and figure_count() reads 0 headless (the live count is probe-proven)")
		_check(c, crowd_node.has_method("cluster_center") \
				and world_rect.has_point(crowd_node.cluster_center("market")),
			"cluster_center('market') resolves from DATA even headless (the probe's camera anchor)")
	scene.free()

# (h) --------------------------------------------------------------------------------------------
static func _h_hud_clock_follows(c: Dictionary, root: Node) -> void:
	print("[city place (h): the HUD top-bar clock follows the LIVE Clock, not the boot string]")
	var clock: Node = root.get_node("/root/Clock")
	var day0: int = int(clock.day)
	var min0: int = int(clock.minute_of_day)
	var hud: Control = (load("res://ui/HUD.tscn") as PackedScene).instantiate()
	root.add_child(hud)
	var time_lbl: Label = hud.get_node_or_null("Top/Bar/Time")
	_check(c, time_lbl != null, "the HUD has the Top/Bar/Time label")
	if time_lbl != null:
		clock.set_time(day0, 13 * 60)   # afternoon
		_check(c, String(time_lbl.text).begins_with("Afternoon"),
			"set_time -> the label reads the NEW phase ('%s')" % time_lbl.text)
		_check(c, String(time_lbl.text).find("13:00") != -1,
			"…and the new clock time ('%s' carries 13:00)" % time_lbl.text)
		clock.set_time(day0, 21 * 60)   # night
		_check(c, String(time_lbl.text).begins_with("Night"),
			"a second jump follows too ('%s')" % time_lbl.text)
	clock.set_time(day0, min0)
	hud.free()
