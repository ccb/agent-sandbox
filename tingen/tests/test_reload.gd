extends SceneTree
## M13 — Reload / ammo pickups + empty-gun feedback harness (TDD).
## Run: godot --headless --path tingen -s tests/test_reload.gd
##
## Covers the M13 TDD contract:
##   (a) A run seeds N revolver_round pickups (deterministic for a fixed seed); picking one up
##       raises the player's revolver_round count and revolver_shot works again after being empty.
##   (b) A no_ammo refusal emits weapon_empty exactly once per empty trigger (NOT per frame) and
##       the HUD/ammo label reflects empty (ammo_count() == 0).
##   (c) The empty flash respects the Settings hit_flash toggle: off -> visual flash no-op but
##       the weapon_empty EVENT still fires.
##   (d) Pickups reset per run (no carry/leak — the sprint lesson).
##   (e) Determinism: none of this alters combat_sim (current count) or try_pay refusal ordering;
##       vectors 95/0 still green; combat_sim still green.

var _passed: int = 0
var _failed: int = 0

func _init() -> void:
	await process_frame
	await process_frame
	# B3 (retro): NEVER touch the player's REAL persistent profile (user://meta.json) — redirect
	# the meta slot to a test-scoped file before anything drives RunManager (tests/test_meta_isolation.gd).
	root.get_node("/root/RunManager").set("meta_path", "user://meta_test.json")
	root.get_node("/root/RunManager").reload_meta()

	_test_a_pickups_seed_deterministic_and_restore_firing()
	_test_b_weapon_empty_event_once_per_trigger()
	_test_c_flash_toggle_gates_visual_but_event_fires()
	_test_d_pickups_reset_per_run()
	_test_e_determinism_try_pay_unaltered()
	_test_f_city_bootstrap_preserves_cathedral_ammo()
	_test_g_player_proximity_pickup_production_path()

	print("\n=== test_reload: %d passed, %d failed ===" % [_passed, _failed])
	quit(1 if _failed > 0 else 0)

func _ok(cond: bool, label: String) -> void:
	if cond:
		_passed += 1
		print("  PASS  %s" % label)
	else:
		_failed += 1
		printerr("  FAIL  %s" % label)

# ──────────────────────────────────────────────────────────────────────────────
# (a) Deterministic pickup seeding + restore firing after empty
# ──────────────────────────────────────────────────────────────────────────────
func _test_a_pickups_seed_deterministic_and_restore_firing() -> void:
	print("[a: pickups seeded deterministic; picking one up restores firing]")
	var RI: Object = root.get_node("/root/RoomItems")
	var AS: Object = root.get_node_or_null("/root/AmmoSpawn")
	_ok(AS != null, "AmmoSpawn autoload is registered")
	if AS == null:
		return

	# Seed with a known value and count what was placed.
	RI.clear()
	AS.seed_run(42)
	var total_placed: int = 0
	for room_id in AS.spawn_rooms():
		total_placed += RI.count(room_id, "revolver_round")
	_ok(total_placed >= 1, "seed_run(42) places at least one revolver_round pickup (%d placed)" % total_placed)

	# Re-seed with the SAME value -> identical count (deterministic).
	RI.clear()
	AS.seed_run(42)
	var total_again: int = 0
	for room_id in AS.spawn_rooms():
		total_again += RI.count(room_id, "revolver_round")
	_ok(total_again == total_placed,
		"same seed -> same total pickups (deterministic: %d == %d)" % [total_again, total_placed])

	# A different seed produces a seeded but possibly different table — just check it's placed.
	RI.clear()
	AS.seed_run(999)
	var total_999: int = 0
	for room_id in AS.spawn_rooms():
		total_999 += RI.count(room_id, "revolver_round")
	_ok(total_999 >= 1, "seed_run(999) also places pickups (%d placed)" % total_999)

	# Now: stage the player; drain to 0; pick up one round; fire again successfully.
	var p := _stage_player("t_reload_arena")
	var pc: Node = p.get_node("Combat")

	# Drain to 0.
	pc.proxy.inventory["revolver_round"] = 1
	_ok(bool(pc.on_attack_pressed(Vector2.RIGHT).get("ok", false)), "1 round: shot fires")
	_step(pc, 1.0)
	_ok(pc.proxy.item_count("revolver_round") == 0, "after the shot, rounds == 0")

	# Confirm the gun is silent.
	var refused: Dictionary = pc.on_attack_pressed(Vector2.RIGHT)
	_ok(not bool(refused.get("ok", false)) and String(refused.get("reason", "")) == "no_ammo",
		"an empty gun refuses with no_ammo")

	# Drop a round in the player's room via RoomItems and have the player pick it up.
	var room_id: String = pc.proxy.room
	var pos: Vector2 = pc.proxy.position
	RI.clear()
	RI.place(room_id, "revolver_round", pos, 1)
	_ok(RI.count(room_id, "revolver_round") == 1, "a round is on the ground in the player's room")

	# Simulate the pickup: take_near + add_item (the standard RoomItems pickup path).
	var taken: String = RI.take_near(room_id, "revolver_round", pos, 64.0)
	_ok(taken == "revolver_round", "take_near picks up the round")
	pc.proxy.add_item(taken, 1)
	_ok(pc.proxy.item_count("revolver_round") == 1, "the inventory now has 1 round after pickup")

	# The gun must work again.
	_step(pc, 0.5)   # let any prior cooldown lapse
	var reloaded: Dictionary = pc.on_attack_pressed(Vector2.RIGHT)
	_ok(bool(reloaded.get("ok", false)),
		"after picking up a round the gun fires again — the ammo dead-end is closed")

	_end_player(p)

# ──────────────────────────────────────────────────────────────────────────────
# (b) weapon_empty emits exactly once per trigger; ammo_count() == 0
# ──────────────────────────────────────────────────────────────────────────────
func _test_b_weapon_empty_event_once_per_trigger() -> void:
	print("[b: weapon_empty fires once per empty trigger; ammo_count() == 0]")
	var EB: Object = root.get_node("/root/EventBus")
	EB.clear()
	var p := _stage_player("t_empty_arena")
	var pc: Node = p.get_node("Combat")

	# Drain to 0.
	pc.proxy.inventory["revolver_round"] = 1
	pc.on_attack_pressed(Vector2.RIGHT)
	_step(pc, 1.0)
	_ok(pc.proxy.item_count("revolver_round") == 0, "rounds drained to 0")

	# First empty trigger.
	pc.on_attack_pressed(Vector2.RIGHT)
	var empties_1: int = EB.events("weapon_empty").size()
	_ok(empties_1 == 1, "first empty trigger emits weapon_empty exactly once (%d)" % empties_1)

	# Calling it again immediately is another trigger but still ONCE per call (not per frame).
	pc.on_attack_pressed(Vector2.RIGHT)
	var empties_2: int = EB.events("weapon_empty").size()
	_ok(empties_2 == 2, "second empty trigger emits a second weapon_empty (now %d total)" % empties_2)

	# ammo_count() == 0 when rounds are 0 (not -1, because the weapon IS carried).
	_ok(pc.ammo_count() == 0, "ammo_count() == 0 when rounds are exhausted")

	_end_player(p)

# ──────────────────────────────────────────────────────────────────────────────
# (c) hit_flash OFF -> visual flash no-op; weapon_empty event still fires
# ──────────────────────────────────────────────────────────────────────────────
func _test_c_flash_toggle_gates_visual_but_event_fires() -> void:
	print("[c: hit_flash OFF -> visual flash no-op; weapon_empty event still fires]")
	var S: Object = root.get_node_or_null("/root/Settings")
	var FB: Object = root.get_node_or_null("/root/CombatFeedback")
	var EB: Object = root.get_node("/root/EventBus")
	if S == null or FB == null:
		printerr("  SKIP  Settings or CombatFeedback not available")
		return
	EB.clear()
	S.reset_defaults()

	var p := _stage_player("t_flash_arena")
	var pc: Node = p.get_node("Combat")

	# Drain to 0.
	pc.proxy.inventory["revolver_round"] = 1
	pc.on_attack_pressed(Vector2.RIGHT)
	_step(pc, 1.0)

	# hit_flash ON: firing empty should trigger the ammo-empty flash.
	S.set_value("hit_flash", true)
	FB.reset_probe()
	pc.on_attack_pressed(Vector2.RIGHT)
	var flash_on: float = FB.last_flash_alpha()
	var events_on: int = EB.events("weapon_empty").size()
	_ok(flash_on > 0.0, "hit_flash ON -> empty-gun flash fires (alpha=%.2f)" % flash_on)
	_ok(events_on >= 1, "hit_flash ON -> weapon_empty event still fires (%d)" % events_on)

	# hit_flash OFF: flash is a no-op, but the event still fires.
	EB.clear()
	S.set_value("hit_flash", false)
	FB.reset_probe()
	pc.on_attack_pressed(Vector2.RIGHT)
	var flash_off: float = FB.last_flash_alpha()
	var events_off: int = EB.events("weapon_empty").size()
	_ok(flash_off == 0.0, "hit_flash OFF -> empty-gun flash is a no-op (alpha=%.2f)" % flash_off)
	_ok(events_off >= 1, "hit_flash OFF -> weapon_empty event STILL fires (the cue is not suppressed)")

	S.reset_defaults()
	_end_player(p)

# ──────────────────────────────────────────────────────────────────────────────
# (d) Pickups reset per run (no carry/leak)
# ──────────────────────────────────────────────────────────────────────────────
func _test_d_pickups_reset_per_run() -> void:
	print("[d: pickups reset per run — no carry/leak]")
	var RI: Object = root.get_node("/root/RoomItems")
	var RM: Object = root.get_node("/root/RunManager")
	var AS: Object = root.get_node_or_null("/root/AmmoSpawn")
	if AS == null:
		_ok(false, "AmmoSpawn not registered — cannot test reset")
		return

	# Seed a run.
	RI.clear()
	AS.seed_run(1234)
	var before: int = 0
	for room_id in AS.spawn_rooms():
		before += RI.count(room_id, "revolver_round")
	_ok(before >= 1, "pickups placed before the run (%d)" % before)

	# Simulate a player picking up all rounds.
	for room_id in AS.spawn_rooms():
		for _i in RI.count(room_id, "revolver_round"):
			RI.take_near(room_id, "revolver_round", Vector2.ZERO, 99999.0)
	var after_pickup: int = 0
	for room_id in AS.spawn_rooms():
		after_pickup += RI.count(room_id, "revolver_round")
	_ok(after_pickup == 0, "all pickups consumed (%d remain)" % after_pickup)

	# A fresh run must re-place the pickups.
	RM.start_run()
	var after_reset: int = 0
	for room_id in AS.spawn_rooms():
		after_reset += RI.count(room_id, "revolver_round")
	_ok(after_reset >= 1,
		"after start_run() the pickups are re-placed (no carry/leak, %d present)" % after_reset)

	# A second start_run does NOT accumulate extra pickups (exact re-seed, not additive).
	RM.start_run()
	var after_second: int = 0
	for room_id in AS.spawn_rooms():
		after_second += RI.count(room_id, "revolver_round")
	_ok(after_second == after_reset,
		"a second start_run() does not accumulate extra pickups (%d == %d)" % [after_second, after_reset])

# ──────────────────────────────────────────────────────────────────────────────
# (e) Determinism: try_pay refusal order unchanged; weapon_empty is cosmetic only
# ──────────────────────────────────────────────────────────────────────────────
func _test_e_determinism_try_pay_unaltered() -> void:
	print("[e: determinism — try_pay refusal order unchanged; weapon_empty is cosmetic only]")
	var p := _stage_player("t_det_arena")
	var pc: Node = p.get_node("Combat")

	# no_weapon takes precedence over no_ammo (pinned by combat_sim).
	pc.proxy.remove_item("revolver", 1)
	pc.proxy.inventory["revolver_round"] = 5
	var r1: Dictionary = pc.on_attack_pressed(Vector2.RIGHT)
	_ok(not bool(r1.get("ok", false)) and String(r1.get("reason", "")) == "no_weapon",
		"no carried weapon -> no_weapon (precedence unchanged by M13)")

	# Restore weapon; no rounds -> no_ammo.
	pc.proxy.add_item("revolver", 1)
	pc.proxy.remove_item("revolver_round", 5)
	var r2: Dictionary = pc.on_attack_pressed(Vector2.RIGHT)
	_ok(not bool(r2.get("ok", false)) and String(r2.get("reason", "")) == "no_ammo",
		"weapon present, no rounds -> no_ammo (reason unchanged by M13)")

	# The try_pay call with a failing stamina leg must still not half-pay rounds.
	pc.proxy.inventory["revolver_round"] = 3
	var r3: Dictionary = pc.try_pay({"id": "revolver_shot", "cost": {"ammo": 1, "stamina": 9999.0}})
	_ok(not bool(r3.get("ok", false)) and String(r3.get("reason", "")) == "no_stamina",
		"check-all-before-deduct-all: stamina refusal when ammo is present")
	_ok(pc.proxy.item_count("revolver_round") == 3, "…round count untouched (no half-pay)")

	# weapon_empty does NOT fire on a non-no_ammo refusal (e.g. no_weapon, no_stamina).
	var EB: Object = root.get_node("/root/EventBus")
	EB.clear()
	pc.proxy.remove_item("revolver", 1)
	pc.on_attack_pressed(Vector2.RIGHT)   # fires no_weapon
	_ok(EB.events("weapon_empty").size() == 0,
		"weapon_empty NOT emitted for a no_weapon refusal (only for no_ammo)")

	_end_player(p)

# ──────────────────────────────────────────────────────────────────────────────
# Helpers
# ──────────────────────────────────────────────────────────────────────────────

# ──────────────────────────────────────────────────────────────────────────────
# (f) CitySummoning bootstrap does NOT wipe cathedral ammo pickups
# ──────────────────────────────────────────────────────────────────────────────
func _test_f_city_bootstrap_preserves_cathedral_ammo() -> void:
	print("[f: CitySummoning bootstrap preserves non-city ammo (review finding 1 regression)]")
	var RI: Object = root.get_node("/root/RoomItems")
	var AS: Object = root.get_node_or_null("/root/AmmoSpawn")
	_ok(AS != null, "AmmoSpawn autoload is registered for finding-1 regression")
	if AS == null:
		return
	# Seed all rooms.
	RI.clear()
	AS.seed_run(42)
	var nave_before: int = RI.count("cathedral_nave", "revolver_round")
	var crypt_before: int = RI.count("cathedral_crypt", "revolver_round")
	_ok(nave_before >= 1, "cathedral_nave seeded with ammo (%d)" % nave_before)
	_ok(crypt_before >= 1, "cathedral_crypt seeded with ammo (%d)" % crypt_before)
	# Run the bootstrap seam: clear city, re-seed city only.
	var CS: GDScript = load("res://src/CitySummoning.gd") as GDScript
	var cs_inst: Node = CS.new()
	root.add_child(cs_inst)
	cs_inst._clear_room("city")
	AS.seed_run_room("city", 0)
	_ok(RI.count("cathedral_nave", "revolver_round") == nave_before,
		"cathedral_nave ammo intact after bootstrap (%d)" % RI.count("cathedral_nave", "revolver_round"))
	_ok(RI.count("cathedral_crypt", "revolver_round") == crypt_before,
		"cathedral_crypt ammo intact after bootstrap (%d)" % RI.count("cathedral_crypt", "revolver_round"))
	_ok(RI.count("city", "revolver_round") >= 1,
		"city ammo re-seeded by bootstrap (%d)" % RI.count("city", "revolver_round"))
	cs_inst.free()
	RI.clear()

# ──────────────────────────────────────────────────────────────────────────────
# (g) Player proximity auto-pickup via the production path
# ──────────────────────────────────────────────────────────────────────────────
func _test_g_player_proximity_pickup_production_path() -> void:
	print("[g: player proximity auto-pickup via _try_pickup_nearby (production path)]")
	var RI: Object = root.get_node("/root/RoomItems")
	var p := _stage_player("t_proximity_g")
	var pc: Node = p.get_node("Combat")
	# Drain to 0.
	pc.proxy.inventory["revolver_round"] = 1
	pc.on_attack_pressed(Vector2.RIGHT)
	_step(pc, 1.0)
	_ok(pc.proxy.item_count("revolver_round") == 0, "rounds drained to 0")
	# Place a round at the player's position.
	var room_id: String = pc.proxy.room
	var pos: Vector2 = pc.proxy.position
	RI.clear()
	RI.place(room_id, "revolver_round", pos, 1)
	# Call the production seam (same as _physics_process does each frame).
	var taken: String = pc._try_pickup_nearby()
	_ok(taken == "revolver_round",
		"_try_pickup_nearby() picks up the round (production seam)")
	_ok(pc.proxy.item_count("revolver_round") == 1,
		"inventory has 1 round after proximity pickup")
	# Gun fires again.
	_step(pc, 0.5)
	_ok(bool(pc.on_attack_pressed(Vector2.RIGHT).get("ok", false)),
		"gun fires after proximity pickup — dead-end closed via production path")
	_end_player(p)
	RI.clear()

## Stage the real Player scene (with its Combat child bound to a fresh proxy).
func _stage_player(room_id: String, pos: Vector2 = Vector2.ZERO) -> Node:
	var p = load("res://scenes/Player.tscn").instantiate()
	root.add_child(p)
	p.global_position = pos
	var pc: Node = p.get_node("Combat")
	pc.proxy.room = room_id
	pc.proxy.position = pos
	return p

## Fixed-dt deterministic stepping of the player executor.
func _step(pc: Node, seconds: float) -> void:
	var steps := int(round(seconds * 60.0))
	for i in steps:
		pc.executor.step_combat(1.0 / 60.0)

## Free the player scene + restore the roster.
func _end_player(player: Node) -> void:
	if player != null:
		player.free()
	root.get_node("/root/Agents").rebuild()
	root.get_node("/root/EventBus").clear()
