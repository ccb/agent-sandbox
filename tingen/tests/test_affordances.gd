extends SceneTree
## LAB PULL-IN P2 — affordances as declarative DATA + per-decision verb curation.
## Verbs declare `required_affordances` in data/action_schema.json; rooms carry affordance TAGS
## in data/city_layout.json (the tingen_action_sketch v3 §5 vocabulary: bar, seat, altar, pew,
## crypt_stair, counter, shelf, cache, door, bed, desk, ...). The sidecar offers only universal
## verbs + verbs whose affordances the current room carries. INVARIANT (verbatim from the lab's
## #446): curation shrinks invalid PHRASINGS only; ActionCommit gates stay the sole authority over
## invalid ACTS — "curation offers a verb ⇔ its gate's place-check would pass". Gates unchanged.
## Standalone: godot --headless --path tingen -s tests/test_affordances.gd
## Also folded into the main suite (run_tests.gd `_test_affordances`) via the SAME run_all().

func _init() -> void:
	await process_frame
	await process_frame
	preload("res://src/TestSandbox.gd").activate(root)
	var r: Dictionary = run_all()
	print("\n=== test_affordances: %d passed, %d failed ===" % [int(r["passed"]), int(r["failed"])])
	quit(1 if int(r["failed"]) > 0 else 0)

## The one entry point (returns {passed, failed}); folded into run_tests.gd.
static func run_all() -> Dictionary:
	var c := {"passed": 0, "failed": 0}
	var root: Node = (Engine.get_main_loop() as SceneTree).root
	_a_schema_declares_affordances(c)
	_b_rooms_carry_sketch_tags(c)
	_c_snapshot_carries_room_affordances(c, root)
	_d_gates_stay_the_authority(c, root)
	_e_rite_tag_set_equals_gateable_rooms(c)
	root.get_node("/root/Agents").rebuild()
	return c

static func _check(c: Dictionary, cond: bool, label: String) -> void:
	if cond:
		c["passed"] = int(c["passed"]) + 1
		print("  PASS  %s" % label)
	else:
		c["failed"] = int(c["failed"]) + 1
		printerr("  FAIL  %s" % label)

## The Thursday-alignment tag vocabulary (tingen_action_sketch v3 §5 + §2 menus). `rite_site`
## is the place-tag of the ONE existing place-gated NPC verb (perform_ritual_step's
## _near_any_rite_site check); the rest are the sketch's object tags, present wherever the
## authored objects exist so ○-row verbs light up as they land.
const VOCABULARY: Array = ["bar", "seat", "altar", "pew", "crypt_stair", "counter", "shelf",
	"cache", "door", "bed", "desk", "hearth", "cot", "lamp", "chest", "wardrobe", "hooks",
	"board", "crate", "rite_site"]

# (a) --------------------------------------------------------------------------------------------
static func _a_schema_declares_affordances(c: Dictionary) -> void:
	print("[affordances (a): verbs declare required_affordances in action_schema.json]")
	var parsed: Variant = JSON.parse_string(FileAccess.get_file_as_string("res://data/action_schema.json"))
	var d: Dictionary = parsed if parsed is Dictionary else {}
	var aff: Dictionary = d.get("affordances", {}) if d.get("affordances") is Dictionary else {}
	var verbs: Dictionary = d.get("verbs", {}) if d.get("verbs") is Dictionary else {}
	_check(c, not aff.is_empty(), "action_schema.json declares an `affordances` section")
	# Every affordance-gated verb is a REAL schema verb, and every tag is in the vocabulary.
	var clean := true
	for v in aff:
		if not verbs.has(v):
			clean = false
		for t in (aff[v] as Array):
			if not VOCABULARY.has(String(t)):
				clean = false
	_check(c, clean, "every affordance row names a real verb + vocabulary tags only")
	# The one place-gated verb today: perform_ritual_step requires the rite_site tag; the NPC
	# pray stub is tagged to the altar (sketch §2.2 pray_at_altar) so its menu row lands right.
	_check(c, (aff.get("perform_ritual_step", []) as Array).has("rite_site"),
		"perform_ritual_step requires rite_site (mirrors its _near_any_rite_site gate)")
	_check(c, (aff.get("pray", []) as Array).has("altar"), "pray requires altar (sketch §2.2)")
	# Universal verbs stay undeclared: move/talk/idle carry no place requirement.
	_check(c, not aff.has("move_to") and not aff.has("talk_to") and not aff.has("idle"),
		"universal verbs (move_to/talk_to/idle) declare NO required affordances")

# (b) --------------------------------------------------------------------------------------------
static func _b_rooms_carry_sketch_tags(c: Dictionary) -> void:
	print("[affordances (b): every room carries its sketch-menu tags]")
	var tags_tavern: Array = CityLayout.room_affordances("laughing_eel_tavern")
	_check(c, tags_tavern.has("bar") and tags_tavern.has("seat") and tags_tavern.has("hearth"),
		"the Laughing Eel carries bar/seat/hearth (sketch §2.1 — objects already built)")
	_check(c, not tags_tavern.has("altar"), "the tavern carries NO altar tag")
	var tags_nave: Array = CityLayout.room_affordances("cathedral_nave")
	_check(c, tags_nave.has("altar") and tags_nave.has("pew") and tags_nave.has("crypt_stair"),
		"the nave carries altar/pew/crypt_stair (sketch §2.2)")
	var tags_crypt: Array = CityLayout.room_affordances("cathedral_crypt")
	_check(c, tags_crypt.has("altar") and tags_crypt.has("rite_site"),
		"the crypt carries altar + rite_site (the dark altar IS the rite site)")
	var tags_city: Array = CityLayout.room_affordances("city")
	_check(c, tags_city.has("rite_site") and tags_city.has("lamp"),
		"the city carries rite_site (warehouse wall) + lamp (street lamps)")
	_check(c, CityLayout.room_affordances("klein_room").has("bed"),
		"the lodging carries bed (RestSpot exists)")
	_check(c, CityLayout.room_affordances("warehouse_inner").has("cache"),
		"the warehouse inner carries cache (sketch §2.10)")
	# Every RoomGraph room has a tag row (an untagged room would silently curate to universal-only).
	var all_tagged := true
	for room in RoomGraph.ROOMS:
		var t: Array = CityLayout.room_affordances(String(room))
		if t.is_empty():
			all_tagged = false
			printerr("    missing tags for room: %s" % room)
		for tag in t:
			if not VOCABULARY.has(String(tag)):
				all_tagged = false
				printerr("    off-vocabulary tag %s in room %s" % [tag, room])
	_check(c, all_tagged, "every RoomGraph room carries vocabulary tags")
	_check(c, CityLayout.room_affordances("no_such_room").is_empty(), "an unknown room yields []")

# (c) --------------------------------------------------------------------------------------------
static func _c_snapshot_carries_room_affordances(c: Dictionary, root: Node) -> void:
	print("[affordances (c): the snapshot + decide request carry the room's tags]")
	var AG: Object = root.get_node("/root/Agents")
	AG.rebuild()
	var a: Agent = AG.get_agent("clerk_voss")
	a.room = "laughing_eel_tavern"
	var snap: Dictionary = Perception.build_snapshot(a, Vector2.ZERO)
	var st: Array = snap.get("room_affordances", []) if snap.get("room_affordances") is Array else []
	_check(c, st.has("bar"), "build_snapshot carries the current room's tags")
	var req: Dictionary = Perception.decide_request(snap, "s")
	var pt: Array = (req.get("perception", {}) as Dictionary).get("room_affordances", [])
	_check(c, pt.has("bar") and not pt.has("altar"),
		"decide_request forwards room_affordances to the sidecar")
	a.room = "cathedral_crypt"
	var snap2: Dictionary = Perception.build_snapshot(a, Vector2.ZERO)
	_check(c, (snap2.get("room_affordances", []) as Array).has("rite_site"),
		"moving rooms changes the forwarded tags")
	AG.rebuild()

# (d) --------------------------------------------------------------------------------------------
## AUTHORITY INTACT: a curated-out verb, forced through commit anyway, gate-refuses IDENTICALLY
## to before curation existed. Curation shrinks phrasings; the gates judge acts.
static func _d_gates_stay_the_authority(c: Dictionary, root: Node) -> void:
	print("[affordances (d): curation never touches the gates — forced verbs refuse identically]")
	var AG: Object = root.get_node("/root/Agents")
	AG.rebuild()
	var a: Agent = AG.get_agent("clerk_voss")
	a.room = "laughing_eel_tavern"   # a bar room: pray + perform_ritual_step are curated OUT here
	a.position = Vector2(100, 100)
	a.task = {"ritual": "summoning_descent"}
	var out: Dictionary = ActionCommit.commit(
		{"actor": a.id, "verb": "perform_ritual_step", "args": {"step": "x"}}, a)
	_check(c, bool(out.get("advanced", true)) == false,
		"a forced off-site rite still refuses through the SAME _near_any_rite_site gate")
	var out2: Dictionary = ActionCommit.commit(
		{"actor": a.id, "verb": "pray", "args": {"god": "selena", "prayer": "..."}}, a)
	_check(c, String(out2.get("prayed_to", "")) == "selena",
		"a forced pray commits the SAME memory-flavor outcome as before (gate unchanged)")
	# And the schema validator still accepts curated-out verbs — curation is not legality.
	var v: Dictionary = ActionSchema.validate({"actor": a.id, "verb": "pray",
		"args": {"god": "selena", "prayer": "x"}})
	_check(c, bool(v.get("ok", false)), "ActionSchema still validates a curated-out verb (menu ≠ law)")
	AG.rebuild()

# (e) --------------------------------------------------------------------------------------------
## THE ⇔ FORWARD DIRECTION (review fix, lab pull-ins wave): the `rite_site` TAG SET must EQUAL the
## set of rooms where perform_ritual_step's place-check (_near_any_rite_site) can actually pass.
## Section (d) pins the safety-critical direction (curated-out ⇒ still gate-refused); this pins the
## data discipline: a stray rite_site tag on a room with no real site would offer the rite verb
## somewhere its gate can NEVER pass (a phrasing dead-end), and an untagged site room would curate
## the rite verb out of the one place it works. Both directions checked against the REAL gate fn
## and the REAL data rows (city_layout.json), not copies.
static func _e_rite_tag_set_equals_gateable_rooms(c: Dictionary) -> void:
	print("[affordances (e): rite_site tag set == rooms where _near_any_rite_site can pass]")
	# Rooms where the gate CAN pass: standing exactly ON each ActionCommit site, in that site's room.
	var gateable: Dictionary = {}
	for site_name in ActionCommit.SITES:
		var site_room: String = ActionCommit._site_room(String(site_name))
		_check(c, ActionCommit._near_any_rite_site(site_room, ActionCommit.SITES[site_name]),
			"the gate passes AT site %s in its own room %s" % [site_name, site_room])
		gateable[site_room] = true
	# Rooms that CARRY the tag (raw data rows — catches tags on rooms outside RoomGraph too).
	var parsed: Variant = JSON.parse_string(FileAccess.get_file_as_string("res://data/city_layout.json"))
	var rows: Dictionary = (parsed as Dictionary).get("room_affordances", {}) \
		if parsed is Dictionary and (parsed as Dictionary).get("room_affordances") is Dictionary else {}
	var tagged: Dictionary = {}
	for room in rows:
		if (rows[room] as Array).has("rite_site"):
			tagged[String(room)] = true
	_check(c, not tagged.is_empty() and not gateable.is_empty(),
		"both sets are non-empty (the rite exists somewhere)")
	for room in tagged:
		_check(c, gateable.has(room),
			"tagged room %s has a REAL rite site (tag => gate can pass)" % room)
	for room in gateable:
		_check(c, tagged.has(room),
			"site room %s carries the rite_site tag (gate can pass => tag)" % room)
