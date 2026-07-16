extends SceneTree
## M5 Sequence-progression harness (direction v2 §6 — the RPG spine). Run with:
##   godot --headless --path tingen -s tests/test_progression.gd
##
## Watched RED before src/Progression.gd, the Characteristic items, the acting deed, and the
## Hunter kit-growth rows existed. Covers the §6 advance loop end to end:
##   (a) Progression starts Hunter · Seq 9, resets per run, and snapshot/restores WITHIN a run
##       (carry within a run, reset between runs — no cross-run stat inheritance, §8);
##   (b) advance() is REFUSED without a same-pathway Characteristic AND without the acting deed done;
##   (c) a successful advance consumes the Characteristic, raises the rank 9->8->7, spikes Madness by
##       ~35 (Meters.add_madness), and grows the player kit (mark_prey at Seq8, incendiary_round at Seq7);
##   (d) the two new abilities load in AbilityDB with valid shapes + the M1 fx field;
##   (e) killing a hunter-pathway foe drops a hunter_characteristic; an off-pathway foe (the butcher)
##       drops a GENERIC (non-hunter) characteristic instead;
##   (f) determinism: progression state does NOT alter combat_sim's transcript (kit growth happens
##       between fights, never mid-flight).
## Plus a cross-run reset assert (advancing, then a new run, wipes the rank back to Seq 9 — no
## inheritance) and the player-kit growth reaching PlayerCombat's usable arts.

var _passed: int = 0
var _failed: int = 0

func _init() -> void:
	await process_frame
	await process_frame
	# B3 (retro): NEVER touch the player's REAL persistent profile (user://meta.json) — redirect
	# the meta slot to a test-scoped file before anything drives RunManager (tests/test_meta_isolation.gd).
	# N1 (sprint safety): sandbox EVERY persistent path (meta/save/settings/hints/playlog) into
	# user://test_sandbox/<run>/ and arm the write guard — see src/TestSandbox.gd.
	preload("res://src/TestSandbox.gd").activate(root)

	_test_starts_hunter_seq9_and_resets_per_run()
	_test_snapshot_restore_within_run()
	_test_advance_refused_without_characteristic_or_deed()
	_test_advance_consumes_raises_spikes_and_grows_kit()
	_test_new_abilities_load_with_valid_shapes()
	_test_player_kit_gains_new_arts()
	_test_hunter_foe_drops_characteristic_offpathway_does_not()
	_test_cross_run_reset_no_inheritance()
	await _test_progression_is_cosmetic_to_combat()
	await _test_hud_shows_sequence_rank()

	print("\n=== %d passed, %d failed ===" % [_passed, _failed])
	quit(1 if _failed > 0 else 0)

func _ok(cond: bool, label: String) -> void:
	if cond:
		_passed += 1
		print("  PASS  %s" % label)
	else:
		_failed += 1
		printerr("  FAIL  %s" % label)

func _P() -> Node: return root.get_node_or_null("/root/Progression")
func _RM() -> Object: return root.get_node("/root/RunManager")
func _M() -> Object: return root.get_node("/root/Meters")
func _AG() -> Object: return root.get_node("/root/Agents")
func _EB() -> Object: return root.get_node("/root/EventBus")
func _DB() -> Object: return root.get_node("/root/AbilityDB")

## Give the player proxy a same-pathway Characteristic + mark the acting deed done, so advance()
## is unblocked. Returns the proxy.
func _arm_advance() -> Agent:
	var proxy: Agent = _AG().ensure_player_proxy(Vector2.ZERO, "prog_room")
	proxy.add_item("hunter_characteristic", 1)
	_P().mark_deed_done()   # the acting ritual (DeedRunner deed) counts as performed this cycle
	return proxy

# --- (a) starts Hunter · Seq 9, resets per run -------------------------------------------------
func _test_starts_hunter_seq9_and_resets_per_run() -> void:
	print("[progression: starts Hunter · Seq 9, and a fresh run resets to Seq 9]")
	var P := _P()
	_ok(P != null, "Progression autoload is registered")
	if P == null:
		return
	_RM().start_run()
	_AG().rebuild()
	_ok(P.pathway() == "hunter", "the default slice pathway is 'hunter'")
	_ok(P.sequence() == 9, "the run starts at Sequence 9 (the low rank)")

# --- (a) snapshot/restore WITHIN a run ---------------------------------------------------------
func _test_snapshot_restore_within_run() -> void:
	print("[progression: rank carries WITHIN a run via snapshot/restore]")
	var P := _P()
	if P == null:
		return
	_RM().start_run()
	_AG().rebuild()
	# Advance once so the rank is 8, then a nightly checkpoint captures it.
	_arm_advance()
	P.advance()
	_ok(P.sequence() == 8, "advanced to Seq 8 before the checkpoint")
	_M().set_meter("doom", 30.0)   # keep Doom < 100 so a death restores rather than ends the run
	_RM().checkpoint_night()
	# Advance again (Seq 7), then a death restores the pre-checkpoint snapshot -> rank comes back to 8.
	_arm_advance()
	P.advance()
	_ok(P.sequence() == 7, "advanced again to Seq 7 after the checkpoint")
	_RM().end_run("death")
	_ok(P.sequence() == 8, "a checkpoint restore brings the rank back to the snapshotted Seq 8")
	_RM().start_run()
	_AG().rebuild()

# --- (b) advance refused without characteristic AND without the deed ---------------------------
func _test_advance_refused_without_characteristic_or_deed() -> void:
	print("[progression: advance() is refused without a same-pathway Characteristic AND without the deed]")
	var P := _P()
	if P == null:
		return
	_RM().start_run()
	_AG().rebuild()
	var proxy: Agent = _AG().ensure_player_proxy(Vector2.ZERO, "prog_room")
	# Neither held nor deed done: refused.
	_ok(not P.can_advance().get("ok", false), "advance is refused with no characteristic and no deed")
	# Deed done but no characteristic: still refused (needs BOTH).
	P.mark_deed_done()
	_ok(not P.can_advance().get("ok", false), "advance is refused with the deed done but no characteristic")
	var seq_before: int = P.sequence()
	_ok(not P.advance().get("ok", false) and P.sequence() == seq_before,
		"a refused advance() does not raise the rank")
	# Characteristic held but deed NOT done: still refused. (Reset the deed latch first.)
	P.reset()
	proxy.add_item("hunter_characteristic", 1)
	_ok(not P.can_advance().get("ok", false), "advance is refused with the characteristic but no deed")
	_ok(proxy.item_count("hunter_characteristic") == 1, "a refused advance never consumes the characteristic")
	_RM().start_run()
	_AG().rebuild()

# --- (c) a successful advance: consume, raise 9->8->7, +35 Madness, grow kit -------------------
func _test_advance_consumes_raises_spikes_and_grows_kit() -> void:
	print("[progression: advance consumes the Characteristic, raises 9->8->7, spikes Madness ~35, grows the kit]")
	var P := _P()
	if P == null:
		return
	_RM().start_run()
	_AG().rebuild()
	var M := _M()
	M.set_meter("madness", 0.0)
	# --- 9 -> 8 unlocks mark_prey ---
	var proxy := _arm_advance()
	_ok(proxy.item_count("hunter_characteristic") == 1, "the proxy holds one hunter_characteristic")
	var mad_before: float = M.get_meter("madness")
	var res: Dictionary = P.advance()
	_ok(res.get("ok", false), "advance() succeeds when armed")
	_ok(P.sequence() == 8, "the rank rises 9 -> 8")
	_ok(proxy.item_count("hunter_characteristic") == 0, "the advance consumes the characteristic")
	_ok(absf(M.get_meter("madness") - (mad_before + 35.0)) < 0.01,
		"the advance spikes Madness by ~35 (%.1f -> %.1f)" % [mad_before, M.get_meter("madness")])
	_ok(P.granted_arts().has("mark_prey"), "Seq 8 grants mark_prey to the Hunter kit")
	# --- 8 -> 7 unlocks incendiary_round ---
	proxy.add_item("hunter_characteristic", 1)
	P.mark_deed_done()
	P.advance()
	_ok(P.sequence() == 7, "the rank rises 8 -> 7")
	_ok(P.granted_arts().has("incendiary_round"), "Seq 7 grants incendiary_round to the Hunter kit")
	# --- the slice caps at Seq 7 ---
	proxy.add_item("hunter_characteristic", 1)
	P.mark_deed_done()
	_ok(not P.can_advance().get("ok", false), "the slice ladder caps at Seq 7 (no further advance)")
	_RM().start_run()
	_AG().rebuild()

# --- (d) the two new abilities load with valid shapes + fx -------------------------------------
func _test_new_abilities_load_with_valid_shapes() -> void:
	print("[abilities: mark_prey + incendiary_round load in AbilityDB with valid shapes + fx (M1)]")
	var db := _DB()
	for aid in ["mark_prey", "incendiary_round"]:
		_ok(db.has_ability(aid), "%s is loaded in AbilityDB" % aid)
		var a: Dictionary = db.ability_for(aid)
		_ok(String(a.get("class", "")) != "", "%s authors a class" % aid)
		_ok(a.get("effects", []) is Array and not (a.get("effects", []) as Array).is_empty(),
			"%s authors a non-empty effects array" % aid)
		_ok(String(a.get("fx", "")) != "", "%s authors the M1 fx field" % aid)
		_ok(float(a.get("cast_time", -1.0)) >= 0.0 and float(a.get("cooldown", -1.0)) >= 0.0,
			"%s authors sane cast_time + cooldown" % aid)
	# The new rows must not introduce a validate_refs problem (unknown effect kind / zone status).
	var problems: Array = db.validate_refs(
		{"mark_prey": db.ability_for("mark_prey"), "incendiary_round": db.ability_for("incendiary_round")},
		{})
	_ok(problems.is_empty(), "the new rows pass AbilityDB.validate_refs (%s)" % str(problems))
	# Hardening (M5 review minor #1): a DIRECT kind:"status" effect naming a status the resolver
	# doesn't know (e.g. a typo'd "slwo") loads silently and no-ops every tick — validate_refs must
	# catch it against CombatResolver.STATUS_KINDS the same way it already guards zone status names.
	var typo: Dictionary = {"bad_status": {"class": "effect",
		"effects": [{"kind": "status", "status": "slwo", "duration": 1.0}]}}
	_ok(not db.validate_refs(typo, {}).is_empty(),
		"validate_refs flags a direct status effect with an unknown status name")
	# ...and the real kinds the resolver handles (incl. `dot`, absent from NAMED_STATUS_DEFAULTS)
	# stay clean — the guard keys off STATUS_KINDS, not the zone-only defaults table.
	var good: Dictionary = {"ok_status": {"class": "effect",
		"effects": [{"kind": "status", "status": "dot", "duration": 1.0}]}}
	_ok(db.validate_refs(good, {}).is_empty(),
		"validate_refs accepts a direct status effect naming a real resolver status kind (dot)")

# --- the growth reaches PlayerCombat's usable arts --------------------------------------------
func _test_player_kit_gains_new_arts() -> void:
	print("[progression: kit growth reaches the player's usable arts (AbilityDB.kit_for('player'))]")
	var P := _P()
	var db := _DB()
	if P == null:
		return
	_RM().start_run()
	_AG().rebuild()
	var base_kit: Array = db.kit_for("player")
	_ok(not base_kit.has("mark_prey") and not base_kit.has("incendiary_round"),
		"at Seq 9 the player kit does NOT yet carry the growth arts")
	_arm_advance()
	P.advance()   # -> Seq 8
	var kit8: Array = db.kit_for("player")
	_ok(kit8.has("mark_prey"), "after advancing to Seq 8 the player kit carries mark_prey")
	# A live PlayerCombat resolves its primary attack from the SAME effective kit lookup. Stage the
	# real Player scene FIRST (adding a node in group "player" makes StandaloneBoot auto-start a run,
	# which resets progression), THEN advance — so the growth is demonstrably visible to the LIVE
	# proxy's kit lookup, not a stale pre-boot snapshot.
	var p = load("res://scenes/Player.tscn").instantiate()
	root.add_child(p)
	await process_frame
	var pc: Node = p.get_node("Combat")
	_ok(pc != null and pc.proxy != null and pc.proxy.combat_form == "player",
		"the live player proxy wears the human 'player' form before advancing")
	# Arm + advance on the LIVE proxy (the one PlayerCombat bound), then its own kit lookup grows.
	pc.proxy.add_item("hunter_characteristic", 1)
	P.mark_deed_done()
	P.advance()   # -> Seq 8, grants mark_prey
	_ok(db.kit_for(pc.proxy.combat_form).has("mark_prey"),
		"the live player proxy's kit lookup (its primary-attack seam) sees the granted art")
	p.free()
	await process_frame   # let the freed player node leave the tree before the next test (else
	                      # StandaloneBoot keeps seeing a player-in-group and auto-starts runs)
	_RM().start_run()
	_AG().rebuild()

# --- (e) hunter-pathway foe drops a characteristic; the off-pathway butcher does not -----------
func _test_hunter_foe_drops_characteristic_offpathway_does_not() -> void:
	print("[characteristic economy: a hunter-pathway kill drops hunter_characteristic; the butcher drops a generic one]")
	var P := _P()
	if P == null:
		return
	_RM().start_run()
	_AG().rebuild()
	var EB := _EB()
	var RI: Object = root.get_node("/root/RoomItems")
	# A hunter-pathway foe in a room, downed -> the drop lands its hunter_characteristic on the ground.
	var foe := _stage_foe("prog_hunter_foe", "drop_room", "hunter")
	RI.clear()
	EB.emit_event("agent_downed", {"actor": "player", "target": "prog_hunter_foe"})
	_ok(RI.count("drop_room", "hunter_characteristic") >= 1,
		"downing a hunter-pathway foe drops a hunter_characteristic")
	# The butcher stays OFF-pathway (§3): its drop is a generic/sellable characteristic, NOT hunter's.
	var butcher := _stage_foe("prog_butcher", "butcher_room", "")
	RI.clear()
	EB.emit_event("agent_downed", {"actor": "player", "target": "prog_butcher"})
	_ok(RI.count("butcher_room", "hunter_characteristic") == 0,
		"the off-pathway butcher does NOT drop a hunter_characteristic")
	_ok(RI.count("butcher_room") >= 1, "the off-pathway kill still drops a generic characteristic")
	RI.clear()
	_AG().rebuild()

# --- cross-run reset: no stat inheritance (§8) -------------------------------------------------
func _test_cross_run_reset_no_inheritance() -> void:
	print("[progression: advancing then a NEW run wipes the rank back to Seq 9 (no cross-run inheritance)]")
	var P := _P()
	if P == null:
		return
	_RM().start_run()
	_AG().rebuild()
	_arm_advance()
	P.advance()
	_ok(P.sequence() == 8 and not P.granted_arts().is_empty(), "advanced to Seq 8 with a granted art this run")
	# A brand-new run must NOT inherit the rank or the granted arts.
	_RM().start_run()
	_AG().rebuild()
	_ok(P.sequence() == 9, "the new run resets the rank to Seq 9 (no inheritance)")
	_ok(P.granted_arts().is_empty(), "the new run wipes the granted arts (no inheritance)")

# --- (f) determinism: progression is cosmetic to a fixed duel ---------------------------------
func _test_progression_is_cosmetic_to_combat() -> void:
	print("[progression: kit growth between fights does NOT alter a fixed duel's transcript]")
	var t_seq9 := await _run_duel_at_sequence(false)
	var t_seq7 := await _run_duel_at_sequence(true)
	_ok(t_seq9 == t_seq7 and not t_seq9.is_empty(),
		"the NPC-vs-NPC combat transcript is byte-identical regardless of the player's Sequence rank")

## Run a fixed NPC-vs-NPC duel; if `advanced`, first push the player's progression forward so the
## kit has grown. The player's kit growth must NOT touch a duel that does not involve the player form.
func _run_duel_at_sequence(advanced: bool) -> Array:
	var P := _P()
	var AG := _AG()
	var EB := _EB()
	_RM().start_run()
	AG.rebuild()
	if advanced and P != null:
		var proxy: Agent = AG.ensure_player_proxy(Vector2.ZERO, "prog_room")
		proxy.add_item("hunter_characteristic", 1)
		P.mark_deed_done()
		P.advance()
		proxy.add_item("hunter_characteristic", 1)
		P.mark_deed_done()
		P.advance()   # Seq 7
	AG.rebuild()
	EB.clear()
	var shooter := _stage("prog_shooter", "prog_duel", Vector2.ZERO)
	var mark := _stage("prog_mark", "prog_duel", Vector2(200, 0))
	var sx := CombatExecutor.new()
	sx.bind(shooter)
	var mx := CombatExecutor.new()
	mx.bind(mark)
	sx.try_cast("revolver_shot", "prog_mark")
	# Combat events emit SYNCHRONOUSLY from step_combat — snapshot the transcript immediately after
	# the stepped duel, with NO awaited frame (a frame would let StandaloneBoot / a live player node
	# reset the run and clear EventBus, which is exactly what a determinism fixture must not depend on).
	var combat_types := ["ability_cast_started", "ability_cast_finished",
		"ability_cast_interrupted", "agent_attacked", "agent_downed", "transformed"]
	var transcript: Array = []
	for _i in range(60):
		sx.step_combat(1.0 / 60.0)
		mx.step_combat(1.0 / 60.0)
	for ev in EB.events():
		if combat_types.has(String(ev.get("type", ""))):
			transcript.append({"type": ev.get("type"), "data": ev.get("data")})
	sx.free()
	mx.free()
	AG.rebuild()
	EB.clear()
	return transcript

# --- (5) the HUD shows the Sequence rank line -------------------------------------------------
func _test_hud_shows_sequence_rank() -> void:
	print("[HUD: the MeterHUD shows a legible 'Hunter · Seq 9' rank line that tracks advances]")
	var P := _P()
	if P == null:
		return
	_RM().start_run()
	_AG().rebuild()
	var hud = load("res://ui/HUD.tscn").instantiate()
	root.add_child(hud)
	await process_frame   # let the MeterHUD's @onready create the Sequence line
	var mh: Node = hud.get_node_or_null("MeterHUD")
	_ok(mh != null, "the persistent HUD carries the MeterHUD widget")
	if mh == null:
		hud.queue_free()
		return
	# Re-assert a clean Seq-9 state right before reading (the frame above lets other autoloads run;
	# the line is a pure read-out of the Progression authority, so a fresh reset + refresh is exact).
	P.reset()
	mh.refresh()
	var seq_line: Label = mh.get_node_or_null("Sequence") as Label
	_ok(seq_line != null and seq_line.visible, "the MeterHUD shows a Sequence rank line")
	_ok(seq_line != null and seq_line.text == "Hunter · Seq 9",
		"the rank line reads 'Hunter · Seq 9' at run start (got '%s')" % (seq_line.text if seq_line != null else "<null>"))
	# Advancing updates the line (event-driven via Progression.advanced -> _on_advanced -> refresh).
	var proxy: Agent = _AG().ensure_player_proxy(Vector2.ZERO, "hud_prog")
	proxy.add_item("hunter_characteristic", 1)
	P.mark_deed_done()
	P.advance()   # -> Seq 8, fires `advanced` which refreshes the line synchronously
	_ok(seq_line != null and seq_line.text == "Hunter · Seq 8",
		"the rank line follows an advance to 'Hunter · Seq 8' (got '%s')" % (seq_line.text if seq_line != null else "<null>"))
	# REGRESSION (N5 probe shot 25 — the stale "Hunter · Seq 9" flash): a NON-default pathway picked
	# at the New-Run picker must show its rank line THE MOMENT the run starts. Meters.reset() fires
	# meter_changed MID-reset (BEFORE Progression.select_pathway applies the pick), so the label used
	# to render the reset default and only corrected on the next meter tick — seconds into a live run.
	# Unlock Hermit via the REAL win seam (mirrors test_hermit_live._unlock_hermit), start a Hermit
	# run with the HUD mounted, and read the label with NO manual refresh() and NO awaited frame.
	_RM().reset_meta()
	_RM().start_run()
	_RM().end_run("win", {"outcome": "descent_stopped"})
	_RM().reload_meta()
	_RM().start_run("hermit")
	_ok(seq_line != null and seq_line.text == "Hermit · Seq 9",
		"the rank line reads 'Hermit · Seq 9' immediately after start_run(\"hermit\") — no stale Hunter flash (got '%s')" % (seq_line.text if seq_line != null else "<null>"))
	_RM().reset_meta()   # scrub the unlock/runs-played this block wrote into the sandboxed meta slot
	hud.queue_free()
	await process_frame
	_RM().start_run()
	_AG().rebuild()

# --- helpers -----------------------------------------------------------------------------------
func _stage(id: String, room_id: String, pos: Vector2) -> Agent:
	var a := Agent.new(id)
	a.display_name = id
	a.room = room_id
	a.position = pos
	a.combat_form = "civilian"
	a.in_combat = true
	_AG()._agents[id] = a
	return a

## Stage a downable foe carrying a `pathway` tag (the DATA the drop keys off — no NPC-identity branch).
func _stage_foe(id: String, room_id: String, pathway: String) -> Agent:
	var a := Agent.new(id)
	a.display_name = id
	a.room = room_id
	a.position = Vector2(120, 40)
	a.combat_form = "butcher_human"
	a.pathway = pathway
	a.downed = true
	_AG()._agents[id] = a
	return a
