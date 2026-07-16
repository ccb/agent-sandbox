extends SceneTree
## N5 — the DEATH SAVE->LOAD ROUNDTRIP (the Death counterpart to test_hermit_save_load's R1/R2). It
## proves a cross-session DISK save (SaveManager.save_game/load_game) faithfully carries a DEATH
## run's whole run-scoped state — pathway + Sequence rung + granted arts + meters + leads + shop —
## so a "Continue" resumes the Death climb exactly where it was left. Standalone headless harness;
## also folded into the main suite (run_tests.gd `_test_death_save_load`) via the SAME run_all() entry.
## Run: godot --headless --path tingen -s tests/test_death_save_load.gd
##
## The pins:
##   R1  a Death run advanced to Seq 7 (both ladder arts granted: grave_hands + wailing_host) +
##       dirtied meters/leads/shop round-trips EVERY one of those subsystems through the disk save
##       (pathway=="death" survives; the death leads' states survive). A scrub-then-load proves the
##       load did the restoring work.
##   R2  the PLAYER's spirituality pool stays INTENTIONALLY transient (M31): never in the autoload
##       save manifest, and a fresh body re-inits it to FULL — the Death caster inherits the same
##       transience contract as the Hermit, asserted so a future change is deliberate.

## N1 (sprint safety): the temp save slot rides the harness sandbox (never the real user dir).
static func TMP_SAVE() -> String:
	return preload("res://src/TestSandbox.gd").path("test_death_save_load.json")

func _init() -> void:
	await process_frame
	await process_frame
	# B3 (retro): NEVER touch the player's REAL persistent profile (user://meta.json) — redirect
	# the meta slot to a test-scoped file before anything drives RunManager (tests/test_meta_isolation.gd).
	# N1 (sprint safety): sandbox EVERY persistent path (meta/save/settings/hints/playlog) into
	# user://test_sandbox/<run>/ and arm the write guard — see src/TestSandbox.gd.
	preload("res://src/TestSandbox.gd").activate(root)
	var r: Dictionary = run_all()
	print("\n=== test_death_save_load: %d passed, %d failed ===" % [int(r["passed"]), int(r["failed"])])
	quit(1 if int(r["failed"]) > 0 else 0)

## The one entry point (returns {passed, failed}); folded into run_tests.gd.
static func run_all() -> Dictionary:
	var c := {"passed": 0, "failed": 0}
	_r1_death_run_roundtrips(c)
	_r2_spirituality_transient_reinits_full(c)
	# Leave a clean Hunter world for whatever runs next in the shared suite.
	var root := _root()
	root.get_node("/root/RunManager").start_run()
	root.get_node("/root/Progression").select_pathway("hunter")
	return c

# --- R1: the whole Death run round-trips through the disk save -----------------------------------
static func _r1_death_run_roundtrips(c: Dictionary) -> void:
	print("[R1: a Death run (Seq 7 + granted arts + meters + leads + shop) round-trips through the disk save]")
	var root := _root()
	var SM: Object = root.get_node("/root/SaveManager")
	var RM: Object = root.get_node("/root/RunManager")
	var AG: Object = root.get_node("/root/Agents")
	var M: Object = root.get_node("/root/Meters")
	var P: Object = root.get_node("/root/Progression")
	var LS: Object = root.get_node("/root/LeadSystem")
	var S: Object = root.get_node_or_null("/root/Shop")

	# Stage a genuine LIVE Death run (two-win unlock -> start_run('death')), then advance it to the
	# Seq-7 slice cap with BOTH ladder arts granted, and DIRTY the meters/leads/shop the way a mid-run
	# save would find them.
	_unlock_death(RM)
	RM.start_run("death")
	AG.rebuild()
	_check(c, P.pathway() == "death" and P.sequence() == 9, "a live Death run begins Death · Seq 9")
	# Advance to Seq 7 carrying the two authored Death ladder arts (the state a two-kill climb leaves).
	P.from_dict({"pathway": "death", "sequence": 7,
		"granted_arts": ["grave_hands", "wailing_host"], "deed_done": true})
	M.set_meter("doom", 63.0)
	M.set_meter("madness", 41.0)
	M.set_meter("notice", 22.0)
	M.set_meter("heat", 18.0)
	LS.slot_run(31337)
	LS.follow("death_prey_auber")   # a followed Death prey lead — must survive the roundtrip
	if S != null:
		S.from_dict({"restocks_used": 1})

	var want_meters: Dictionary = M.to_dict()
	var want_prog: Dictionary = P.to_dict()
	var want_leads: Dictionary = LS.to_dict()
	var want_shop: Dictionary = S.to_dict() if S != null else {}

	# Persist to a temp slot, then SCRUB the live world (simulating a fresh process at the title).
	_check(c, bool(SM.save_game(TMP_SAVE())), "save_game writes the temp slot")
	M.reset(); P.reset(); LS.reset()
	if S != null:
		S.reset()

	# The scrub really cleared the Death state (so a green load can't be a no-op).
	_check(c, P.pathway() != "death", "reset scrubbed the pathway back off Death (state was live)")
	_check(c, P.sequence() == 9, "reset scrubbed the Sequence back to 9")
	_check(c, not _dict_eq(M.to_dict(), want_meters), "reset scrubbed the meters")

	# Load the slot back and prove EVERY subsystem returned.
	_check(c, bool(SM.load_game(TMP_SAVE())), "load_game reads the temp slot")
	_check(c, P.pathway() == "death", "R1: the run's PATHWAY restored to 'death' from disk")
	_check(c, P.sequence() == 7, "R1: the Sequence rung (Seq 7) restored from disk")
	_check(c, P.granted_arts().has("grave_hands") and P.granted_arts().has("wailing_host"),
		"R1: the granted Death arts (grave_hands + wailing_host) restored from disk")
	_check(c, _dict_eq(P.to_dict(), want_prog), "R1: the full progression dump restored byte-for-byte")
	_check(c, _dict_eq(M.to_dict(), want_meters), "R1: the meters (Doom/Madness/Notice/Heat) restored from disk")
	_check(c, _dict_eq(LS.to_dict(), want_leads), "R1: the leads (the followed Death prey lead) restored from disk")
	if S != null:
		_check(c, _dict_eq(S.to_dict(), want_shop), "R1: the shop (stock latch) restored from disk")

	# Leave a clean world for later tests.
	RM.start_run()

# --- R2: the player's spirituality pool is transient by design + re-inits to full ---------------
static func _r2_spirituality_transient_reinits_full(c: Dictionary) -> void:
	print("[R2: spirituality stays INTENTIONALLY transient for the Death caster (M31) — not in the manifest, re-inits full]")
	var root := _root()
	var SM: Object = root.get_node("/root/SaveManager")

	# The disk save is built ONLY from the autoload subsystem manifest; spirituality lives on the
	# PlayerCombat body (a scene node), so it is not — and by M31's design MUST not be — persisted.
	var dump: Dictionary = SM.subsystem_dump()
	var mentions_spirit := false
	for k in dump.keys():
		if String(k).findn("spirit") >= 0:
			mentions_spirit = true
	_check(c, not mentions_spirit,
		"the disk save manifest carries NO spirituality subsystem (the pool is transient by design)")

	# A fresh player body re-inits the pool to FULL — a post-load Death caster starts topped up.
	var pc = PlayerCombat.new()
	var now := float(pc.call("spirituality_now"))
	var maxv := float(pc.call("spirituality_max"))
	_check(c, maxv > 0.0 and is_equal_approx(now, maxv),
		"a fresh PlayerCombat re-inits spirituality to FULL (%.0f / %.0f) — transient, not a save bug" % [now, maxv])
	pc.free()

# --- helpers ------------------------------------------------------------------------------------
static func _check(c: Dictionary, cond: bool, label: String) -> void:
	if cond:
		c["passed"] = int(c["passed"]) + 1
		print("  PASS  %s" % label)
	else:
		c["failed"] = int(c["failed"]) + 1
		printerr("  FAIL  %s" % label)

static func _root() -> Node:
	return (Engine.get_main_loop() as SceneTree).root

## TWO wins write the Death unlock into the persistent meta (win 1 -> hermit, win 2 -> death).
static func _unlock_death(RM: Object) -> void:
	RM.reset_meta()
	for _i in 2:
		RM.start_run()
		RM.end_run("win", {"outcome": "descent_stopped"})
		RM.reload_meta()

## Compare two subsystem dicts for RESTORED-STATE equality, normalized through a JSON round-trip first
## (a disk save->load coerces whole-number ints to floats; the game reads via int()/float() casts, so
## that is a representation artifact, not state loss). Same pattern as test_hermit_save_load._dict_eq.
static func _dict_eq(a: Dictionary, b: Dictionary) -> bool:
	return _norm(a) == _norm(b)

static func _norm(d: Variant) -> String:
	return JSON.stringify(JSON.parse_string(JSON.stringify(d, "", true, true)), "", true, true)
