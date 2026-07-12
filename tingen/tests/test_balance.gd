extends SceneTree
## M26 — BALANCE RETUNE sanity harness (data-only pacing/economy retune). Runs headless.
##   godot --headless --path tingen -s tests/test_balance.gd
## Also folded into the main suite (run_tests.gd `_test_balance`) via the SAME run_all() entry
## point, so both share one set of assertions.
##
## The six balance-sanity pins (mapping the five retunes + the combat-determinism invariant):
##   #1  the SHIPPED idle run (the REAL live roster — 3 hidden Beyonders loose, the opening's butcher lead
##       known + ignored, nothing downed) paces to Doom 100 ~day 5 — NOT the day-3 collapse the
##       unconditional count caused. The PURE passive time+phase clock (no prey known) alone lands ~day
##       6-7, and live-but-UNKNOWN Beyonders cost nothing (the known-gate holds an idle player harmless).
##       [RETUNE #2 + the known-gate pacing fix]
##   #2  a KNOWN hidden-Beyonder human phase (butcher_human — not flagged monster) IS counted by the
##       loose-monster Doom driver once its lead is surfaced, so ignoring KNOWN prey costs Doom over
##       time; a live but UNKNOWN one does NOT (the gate).                    [RETUNE #2]
##   #3  a player who SELLS one hunter_characteristic can STILL reach Seq 7 (the pity margin removes the
##       trap) — but selling BOTH meals' fuel STILL forfeits (the choice keeps its teeth). [RETUNE #1]
##   #4  TWO advances raise Madness MEANINGFULLY toward the 50/75 thresholds even with a night's rest +
##       acting deeds applied between them (real, survivable push-your-luck tension). [RETUNE #5]
##   #5  the Ritual Night fuse is ~48 beats (the ~cross-the-city window), authored + engine-consumed. [RETUNE #3]
##   #6  the retune did NOT touch the pinned combat numbers — the combat-facing Madness spikes are
##       unchanged; the changed constants are the out-of-combat pacing ones. (combat_sim 59/0 +
##       run_combat_vectors 95/0 are the real determinism guard, run in VERIFY.)

const _HOUR_START_MIN: int = 480   # 08:00, inside "morning" — +60 stays in-phase (isolates the hourly fill)

func _init() -> void:
	await process_frame
	await process_frame
	# B3 (retro): NEVER touch the player's REAL persistent profile (user://meta.json) — redirect
	# the meta slot to a test-scoped file before anything drives RunManager (tests/test_meta_isolation.gd).
	root.get_node("/root/RunManager").set("meta_path", "user://meta_test.json")
	root.get_node("/root/RunManager").reload_meta()
	var r: Dictionary = run_all()
	print("\n=== test_balance: %d passed, %d failed ===" % [int(r["passed"]), int(r["failed"])])
	quit(1 if int(r["failed"]) > 0 else 0)

## The one entry point (returns {passed, failed}); folded into run_tests.gd.
static func run_all() -> Dictionary:
	var c := {"passed": 0, "failed": 0}
	var root: Node = (Engine.get_main_loop() as SceneTree).root
	var passive_day := _1_idle_pacer_and_one_monster_survivable(c, root)
	_2_hidden_beyonder_costs_doom(c, root)
	_3_sell_fork_trap_is_gone(c, root)
	_3b_hermit_sell_fork_mirror(c, root)
	_4_two_advances_pressure_madness(c, root)
	_5_ritual_night_fuse_window(c, root)
	_6_combat_pins_unchanged(c, root)
	# Restore a clean world for whatever runs next in the shared suite.
	root.get_node("/root/RunManager").start_run()
	root.get_node("/root/Agents").rebuild()
	return c

# --- #1: the shipped idle paces sanely; the known-gate keeps live-but-unknown prey harmless (RETUNE #2) ---
static func _1_idle_pacer_and_one_monster_survivable(c: Dictionary, root: Node) -> int:
	print("[#1: shipped idle (real roster) ~day 5; pure passive ~day 6-7; unknown Beyonders cost nothing]")
	var M: Object = root.get_node("/root/Meters")
	var CL: Object = root.get_node("/root/Clock")
	var AG: Object = root.get_node("/root/Agents")
	var RM: Object = root.get_node("/root/RunManager")
	var LS: Object = root.get_node("/root/LeadSystem")

	# (a) The SHIPPED idle run, on the REAL live roster — 3 hidden Beyonders loose in their human faces,
	# NOTHING downed. The opening surfaces the butcher lead (exactly ONE prey KNOWN); the player ignores
	# everything. This measures the number that actually ships (no `_down_counted` fiction). It must land
	# well past the old day-3 collapse: the known-gate + the 0.35 retune mean one ignored known Beyonder
	# is a modest cost, not a halving.
	RM.start_run()
	AG.rebuild()
	_check(c, LS.known_prey_forms().size() >= 1,
		"the opening surfaced >=1 prey lead — the shipped idle run KNOWS the butcher (%s)" % str(LS.known_prey_forms().keys()))
	var shipped_day := _idle_reach_day(M, CL)
	_check(c, shipped_day >= 5 and shipped_day <= 7,
		"shipped idle (real roster, butcher known + ignored) reaches Doom 100 on day %d (~5-7, NOT the day-3 collapse)" % shipped_day)

	# (b) The PURE passive time+phase clock: with NO prey KNOWN (a run that has surfaced nothing — the
	# fresh-run floor), the 3 live Beyonders contribute NOTHING because the gate holds them. So the
	# passive pacer alone must still land ~day 6-7 (the fundamental clock survived the retune), and it is
	# SLOWER than the shipped idle (knowing + ignoring the butcher accelerates the descent).
	RM.start_run()
	AG.rebuild()
	_set_all_known(LS, false)
	var passive_day := _idle_reach_day(M, CL)
	_check(c, passive_day >= 6 and passive_day <= 7,
		"pure passive clock reaches 100 on day %d (~6-7) — live but UNKNOWN Beyonders cost nothing (the gate holds)" % passive_day)
	_check(c, shipped_day <= passive_day,
		"knowing the butcher and ignoring it ACCELERATES the descent vs pure passive (day %d <= %d)" % [shipped_day, passive_day])

	# (c) The WORST case — a player who surfaced ALL THREE hidden Beyonders and hunted NONE. Ignoring all
	# known prey really bites (the intended §4 pressure), collapsing the run toward day 3; but even so the
	# 0.35 retune keeps it well past a day-1/2 forced loss (at the OLD 0.75 the same load lost far sooner).
	RM.start_run()
	AG.rebuild()
	_set_all_known(LS, true)
	var all_known_day := _idle_reach_day(M, CL)
	_check(c, all_known_day >= 3 and all_known_day < passive_day,
		"ignoring ALL 3 known Beyonders collapses the run to day %d (real teeth) yet not a day-1/2 forced loss" % all_known_day)
	return passive_day

# --- #2: only a KNOWN hidden-Beyonder human phase is counted by the Doom driver (RETUNE #2) ------
static func _2_hidden_beyonder_costs_doom(c: Dictionary, root: Node) -> void:
	print("[#2: only KNOWN hidden Beyonders cost Doom — ignoring named prey is punished, unknown prey isn't]")
	var M: Object = root.get_node("/root/Meters")
	var CL: Object = root.get_node("/root/Clock")
	var AG: Object = root.get_node("/root/Agents")
	var RM: Object = root.get_node("/root/RunManager")
	var DB: Object = root.get_node("/root/AbilityDB")
	var MD: Object = root.get_node("/root/MeterDrivers")
	var LS: Object = root.get_node("/root/LeadSystem")

	# The three hidden-Beyonder human forms are hidden_beyonder but NOT monster:true (still human).
	_check(c, DB.is_hidden_beyonder_form("butcher_human") and not DB.is_monster_form("butcher_human"),
		"butcher_human is a HIDDEN Beyonder (hidden_beyonder:true, monster:false — the human phase)")
	_check(c, DB.is_hidden_beyonder_form("wren_human") and DB.is_hidden_beyonder_form("mack_harbor"),
		"wren_human + mack_harbor are hidden Beyonders too (the two Hunter-pathway meals)")

	# Real live roster; force EVERY lead unknown so we start from a truly idle, un-surfaced world.
	RM.start_run()
	AG.rebuild()
	_set_all_known(LS, false)

	# (a) UNKNOWN prey: bram_kell (butcher_human) is LIVE in the city, but the player has been told
	# nothing — the gate must hold, so an in-phase hour fills ONLY the time creep (no monster nudge).
	CL.set_time(1, _HOUR_START_MIN)
	M.set_meter("doom", 0.0)
	CL.advance_minutes(60)
	var time_only: float = M.get_meter("doom")
	_check(c, is_equal_approx(time_only, MD.DOOM_PER_HOUR),
		"a LIVE but UNKNOWN hidden Beyonder does NOT push Doom (%.2f == time creep %.2f) — the idle player isn't taxed"
			% [time_only, MD.DOOM_PER_HOUR])

	# (b) The city NAMES the butcher (constable_brom surfaces his lead) — the prey is now KNOWN.
	LS.surface_from("constable_brom")
	_check(c, LS.known_prey_forms().has("butcher_human"),
		"surfacing the butcher lead marks butcher_human KNOWN (the city named the prey)")
	CL.set_time(1, _HOUR_START_MIN)
	M.set_meter("doom", 0.0)
	CL.advance_minutes(60)
	var with_known: float = M.get_meter("doom")
	_check(c, with_known > time_only,
		"a KNOWN hidden Beyonder raises Doom faster than time alone (%.2f > %.2f) — ignoring NAMED prey costs Doom"
			% [with_known, time_only])

	# (c) Hunt it down: a downed Beyonder is no longer a threat, so Doom falls back to the time creep.
	for a in AG.all():
		if a != null and a.combat_form == "butcher_human":
			a.downed = true
	CL.set_time(1, _HOUR_START_MIN)
	M.set_meter("doom", 0.0)
	CL.advance_minutes(60)
	_check(c, is_equal_approx(M.get_meter("doom"), time_only),
		"a DOWNED known Beyonder no longer pushes Doom (hunting the named prey removes the pressure)")

# --- #3: the sell-fork trap is gone, but selling both still forfeits (RETUNE #1) ----------------
static func _3_sell_fork_trap_is_gone(c: Dictionary, root: Node) -> void:
	print("[#3: sell ONE fuel and still reach Seq 7 (pity margin); sell BOTH and still forfeit]")
	var S: Object = root.get_node_or_null("/root/Shop")
	var PR: Object = root.get_node("/root/Progression")
	var AG: Object = root.get_node("/root/Agents")
	var RM: Object = root.get_node("/root/RunManager")
	if S == null:
		_check(c, false, "Shop autoload missing — cannot test the sell fork")
		return
	_check(c, PR.pity_on_sell(), "the pity margin is enabled in scenario.json (progression.pity_fuel_on_sell)")

	var fuel := String(PR.characteristic_item())

	# (a) SELL ONE fuel, then advance TWICE -> still reaches the Seq 7 cap (the trap is gone).
	RM.start_run()
	var p: Object = AG.ensure_player_proxy(Vector2.ZERO, "balance_shop")
	p.inventory["shilling"] = 0
	_check(c, PR.sequence() == 9, "a fresh run starts at Seq 9")
	# Meal 1 harvested, then SOLD at Franky's counter (the push-your-luck cash-in).
	p.add_item(fuel, 1)
	S.sell_harvest()
	_check(c, p.item_count(fuel) == 0, "the sold fuel left the inventory (real coin taken)")
	# Meal 2 harvested. Now advance twice: real fuel first, then the pity margin.
	p.add_item(fuel, 1)
	PR.mark_deed_done(); var a1: Dictionary = PR.advance()
	PR.mark_deed_done(); var a2: Dictionary = PR.advance()
	_check(c, bool(a1.get("ok", false)) and bool(a2.get("ok", false)) and PR.sequence() == 7,
		"sold ONE fuel and STILL climbed 9 -> 8 -> 7 (Seq %d) — the M15 sell-fork trap is gone" % PR.sequence())

	# (b) SELL BOTH meals' fuel -> the pity margin (cap 1) covers only ONE, so the climb STILL forfeits.
	RM.start_run()
	p = AG.ensure_player_proxy(Vector2.ZERO, "balance_shop")
	p.inventory["shilling"] = 0
	p.add_item(fuel, 2)
	S.sell_harvest()   # both sold; pity granted is capped at 1
	PR.mark_deed_done(); var b1: Dictionary = PR.advance()   # spends the single pity -> Seq 8
	PR.mark_deed_done(); var b2: Dictionary = PR.advance()   # no fuel, no pity left -> refused
	_check(c, bool(b1.get("ok", false)) and not bool(b2.get("ok", false)) and PR.sequence() == 8,
		"selling BOTH fuels leaves the climb short at Seq %d — the choice keeps its teeth" % PR.sequence())

# --- #3b: the Hermit mirror of the sell fork — the fuel-vs-coin choice exists for the Hermit too (M34 D) -
## The Hermit's Characteristic drop (hermit_characteristic) is ALSO its advance fuel, so — exactly like
## the Hunter's — it must sell for real coin (the push-your-luck fork) yet stay covered by the SAME pity
## margin: sell ONE and still reach Seq 7, sell BOTH and forfeit at Seq 8. Engine-neutral: the price is a
## data row (scenario.json sell_prices) and the pity keys off characteristic_item()="hermit_characteristic"
## — no NPC/pathway branch in src/. RED before M34: sell_prices has no hermit_characteristic (price 0, the
## sale refuses nothing_to_sell), so the Hermit had no coin fork at all.
static func _3b_hermit_sell_fork_mirror(c: Dictionary, root: Node) -> void:
	print("[#3b: Hermit sell fork — price 10; sell ONE fuel and still reach Seq 7 (pity); sell BOTH and forfeit]")
	var S: Object = root.get_node_or_null("/root/Shop")
	var PR: Object = root.get_node("/root/Progression")
	var AG: Object = root.get_node("/root/Agents")
	var RM: Object = root.get_node("/root/RunManager")
	if S == null:
		_check(c, false, "Shop autoload missing — cannot test the Hermit sell fork")
		return
	# The authored Hermit fuel sell price (RED before M34: absent -> 0).
	_check(c, int(S.sell_prices().get("hermit_characteristic", 0)) == 10,
		"hermit_characteristic sells for 10 (the fuel-vs-coin fork exists for the Hermit too)")

	# A live Hermit run (unlock -> start_run('hermit')); its advance fuel is hermit_characteristic.
	_unlock_hermit(RM)
	RM.start_run("hermit")
	AG.rebuild()
	PR.select_pathway("hermit")
	var fuel := String(PR.characteristic_item())
	_check(c, fuel == "hermit_characteristic", "the Hermit run's advance fuel is hermit_characteristic")

	# (a) SELL ONE fuel for real coin (incl the 10), then advance TWICE -> reaches the Seq-7 cap.
	var p: Object = AG.ensure_player_proxy(Vector2.ZERO, "balance_hermit_shop")
	p.inventory["shilling"] = 0
	_check(c, PR.sequence() == 9, "a fresh Hermit run starts at Seq 9")
	p.add_item(fuel, 1)
	var s1: Dictionary = S.sell_harvest()
	_check(c, bool(s1.get("ok", false)) and int(s1.get("coins", 0)) >= 10 and p.item_count("shilling") >= 10,
		"selling one hermit fuel pays REAL coin incl the authored 10 (got %d, RED: nothing_to_sell)" % int(s1.get("coins", 0)))
	_check(c, p.item_count(fuel) == 0, "…and the sold fuel left the inventory")
	p.add_item(fuel, 1)   # meal 2 harvested
	PR.mark_deed_done(); var a1: Dictionary = PR.advance()   # real fuel -> Seq 8
	PR.mark_deed_done(); var a2: Dictionary = PR.advance()   # the pity margin -> Seq 7
	_check(c, bool(a1.get("ok", false)) and bool(a2.get("ok", false)) and PR.sequence() == 7,
		"sold ONE hermit fuel and STILL climbed 9 -> 8 -> 7 (Seq %d) — the pity margin covers the sale" % PR.sequence())

	# (b) SELL BOTH meals' fuel -> the pity (cap 1) covers only ONE, so the climb STILL forfeits at Seq 8.
	RM.start_run("hermit")
	AG.rebuild()
	PR.select_pathway("hermit")
	p = AG.ensure_player_proxy(Vector2.ZERO, "balance_hermit_shop")
	p.inventory["shilling"] = 0
	p.add_item(fuel, 2)
	S.sell_harvest()   # both sold; pity granted capped at 1
	PR.mark_deed_done(); var b1: Dictionary = PR.advance()   # spends the single pity -> Seq 8
	PR.mark_deed_done(); var b2: Dictionary = PR.advance()   # no fuel, no pity left -> refused
	_check(c, bool(b1.get("ok", false)) and not bool(b2.get("ok", false)) and PR.sequence() == 8,
		"selling BOTH hermit fuels leaves the climb short at Seq %d — the Hermit's choice keeps its teeth" % PR.sequence())

# --- #4: two advances raise Madness meaningfully with realistic relief (RETUNE #5) --------------
static func _4_two_advances_pressure_madness(c: Dictionary, root: Node) -> void:
	print("[#4: two advances cross the whispers rung even with a night's rest + deeds — real tension]")
	var M: Object = root.get_node("/root/Meters")
	var PR: Object = root.get_node("/root/Progression")
	var AG: Object = root.get_node("/root/Agents")
	var RM: Object = root.get_node("/root/RunManager")

	RM.start_run()
	var p: Object = AG.ensure_player_proxy(Vector2.ZERO, "balance_lodging")
	M.set_meter("madness", 0.0)
	p.add_item(String(PR.characteristic_item()), 2)

	# Advance #1 (+35), then a REALISTIC amount of relief: one night's Cogitation (-10) + two acting
	# deeds (-3 each) = -16. Then advance #2 (+35): 0 -> 35 -> 25 -> 19 -> 54.
	PR.mark_deed_done(); PR.advance()
	M.relieve_madness_rest()
	M.try_relieve_madness_deed(); M.try_relieve_madness_deed()
	var mid: float = M.get_meter("madness")
	PR.mark_deed_done(); PR.advance()
	var after_two: float = M.get_meter("madness")

	_check(c, after_two >= float(M.MADNESS_WHISPERS),
		"two advances reach %.0f Madness — CROSSES the whispers rung (%d) despite rest + deeds (was trivially suppressed pre-retune)"
			% [after_two, M.MADNESS_WHISPERS])
	_check(c, after_two < float(M.MADNESS_LOSS_OF_CONTROL),
		"...but stays below loss-of-control (%.0f < 100) — real, SURVIVABLE push-your-luck tension" % after_two)
	_check(c, mid < after_two,
		"the second advance is what pushes past the rung (mid %.0f -> %.0f) — the relief did not erase the spikes"
			% [mid, after_two])

	# The SURVIVABLE side (documents review finding #2, LOW): the tension is intentionally RUSH-gated. A
	# patient player who SPACES the two advances across TWO full days of MAXIMAL relief (2x nightly rest
	# -10 + 2x the 3/day deed cap -9) fully bleeds the first +35 before the second lands, so Madness never
	# accumulates across them and never crosses whispers. This is BY DESIGN — the B2 cycle is survivable,
	# not a ratchet; patience is a valid escape, paid for in Doom-clock time (a slow run pays at the Doom
	# pacer instead of at Madness). It is the deliberate counterpart to the clustered case above.
	var CL: Object = root.get_node("/root/Clock")
	RM.start_run()
	p = AG.ensure_player_proxy(Vector2.ZERO, "balance_lodging")
	CL.set_time(1, 480)
	M.set_meter("madness", 0.0)
	p.add_item(String(PR.characteristic_item()), 2)
	PR.mark_deed_done(); PR.advance()                       # +35 -> 35
	for day in [2, 3]:                                      # two full days of maximal relief between advances
		CL.set_time(day, 480)
		M.relieve_madness_rest()                            # -10 (the night's Cogitation)
		M.try_relieve_madness_deed(); M.try_relieve_madness_deed(); M.try_relieve_madness_deed()  # -9 (the 3/day cap)
	PR.mark_deed_done(); PR.advance()                       # +35 -> 35 (the first spike bled to 0 first)
	var patient_after: float = M.get_meter("madness")
	_check(c, patient_after < float(M.MADNESS_WHISPERS),
		"SPACED advances (2 full days of max relief between) hold at %.0f — BELOW whispers (%d): the cycle is survivable/rush-gated by design, not a ratchet"
			% [patient_after, M.MADNESS_WHISPERS])

# --- #5: the Ritual Night fuse window is ~48 beats (RETUNE #3) ----------------------------------
static func _5_ritual_night_fuse_window(c: Dictionary, root: Node) -> void:
	print("[#5: the Ritual Night fuse is ~48 beats — the promised cross-the-city window]")
	var authored := _scenario_fuse_beats()
	_check(c, authored == 48,
		"data/scenario.json ritual_night.fuse_beats == %d (want 48; was 12 = a ~90s geographic forced loss)" % authored)
	var RN: Object = root.get_node_or_null("/root/RitualNight")
	if RN != null:
		_check(c, int(RN._fuse_beats_start) == 48,
			"the RitualNight engine consumed the authored fuse (_fuse_beats_start == %d)" % int(RN._fuse_beats_start))

# --- #6: the retune did not touch the pinned combat numbers ------------------------------------
static func _6_combat_pins_unchanged(c: Dictionary, root: Node) -> void:
	print("[#6: combat-facing Madness spikes UNCHANGED; only out-of-combat pacing constants moved]")
	var M: Object = root.get_node("/root/Meters")
	var MD: Object = root.get_node("/root/MeterDrivers")
	# The digest/assume_form spikes and the nightly rest are UNCHANGED (the +35 digest is pinned by
	# progression/full_run; assume_form +25 by the rampage path). The retune moved only the deed relief.
	_check(c, is_equal_approx(M.MADNESS_DIGEST, 35.0), "MADNESS_DIGEST unchanged (35 — the pinned digest spike)")
	_check(c, is_equal_approx(M.MADNESS_ASSUME_FORM, 25.0), "MADNESS_ASSUME_FORM unchanged (25)")
	_check(c, is_equal_approx(M.MADNESS_REST_RELIEF, 10.0), "MADNESS_REST_RELIEF unchanged (10 — the nightly rest)")
	# The two constants the retune DID move, at their new values.
	_check(c, is_equal_approx(M.MADNESS_DEED_RELIEF, 3.0), "MADNESS_DEED_RELIEF retuned 5 -> 3 (RETUNE #5)")
	_check(c, is_equal_approx(MD.DOOM_PER_MONSTER_HOUR, 0.35), "DOOM_PER_MONSTER_HOUR retuned 0.75 -> 0.35 (RETUNE #2)")
	# NOTE: none of these feed combat RESOLUTION (they are out-of-combat pacing/economy). The real
	# determinism guard is combat_sim (59/0) + run_combat_vectors (95/0), run in the VERIFY step — the
	# retune stages no combat world, so those pinned transcripts are untouched.

# --- helpers -----------------------------------------------------------------------------------
## Advance an idle run minute-by-minute from day 1 08:00 and return the day Doom first reaches 100
## (0 if it never does within a 7-day window). Uses the real Clock->MeterDrivers passive fill.
static func _idle_reach_day(M: Object, CL: Object) -> int:
	M.set_meter("doom", M.run_start("doom"))
	CL.set_time(1, 480)
	for _i in range(7 * 1440):
		CL.advance_minutes(1)
		if M.get_meter("doom") >= 100.0:
			return int(CL.day)
	return 0

## Force every slotted lead's KNOWN flag (and un-hide any gated lead when marking known) — the seam the
## pacing pins use to isolate the known-gate WITHOUT downing the real live roster. `false` = a truly
## un-surfaced idle world (the live Beyonders stay uncounted); `true` = the worst case where the player
## surfaced every prey and hunted none. Reaches LeadSystem's `_leads` directly (the codebase's test
## style — cf. AG._agents / RN._fuse_beats_start); no NPC-id branch.
static func _set_all_known(LS: Object, v: bool) -> void:
	for id in LS._leads.keys():
		var lead: Dictionary = LS._leads[id]
		lead["known"] = v
		if v and String(lead.get("state", "")) == "hidden":
			lead["state"] = "open"   # a surfaced lead is player-visible; open it so known_prey_forms counts it

## Read the authored Ritual Night fuse straight from the scenario data (the value the engine loads).
static func _scenario_fuse_beats() -> int:
	var path := "res://data/scenario.json"
	if not FileAccess.file_exists(path):
		return -1
	var parsed: Variant = JSON.parse_string(FileAccess.get_file_as_string(path))
	if not (parsed is Dictionary):
		return -1
	var rn: Variant = (parsed as Dictionary).get("ritual_night", {})
	return int((rn as Dictionary).get("fuse_beats", -1)) if rn is Dictionary else -1

## A win writes the Hermit unlock into the persistent meta (so start_run('hermit') honors the pick).
static func _unlock_hermit(RM: Object) -> void:
	RM.reset_meta()
	RM.start_run()
	RM.end_run("win", {"outcome": "descent_stopped"})
	RM.reload_meta()

static func _check(c: Dictionary, cond: bool, label: String) -> void:
	if cond:
		c["passed"] = int(c["passed"]) + 1
		print("  PASS  %s" % label)
	else:
		c["failed"] = int(c["failed"]) + 1
		printerr("  FAIL  %s" % label)
