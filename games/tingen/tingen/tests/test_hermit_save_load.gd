extends SceneTree
## M33 — the HERMIT SAVE->LOAD ROUNDTRIP. The Hermit counterpart to test_save_spend_seed's B3 (which
## dirties + round-trips a HUNTER run): it proves a cross-session DISK save (SaveManager.save_game/
## load_game) faithfully carries a HERMIT run's whole run-scoped state — pathway + Sequence rung +
## granted arts + meters + leads + shop — so a "Continue" resumes the Hermit climb exactly where it
## was left. Standalone headless harness; also folded into the main suite (run_tests.gd
## `_test_hermit_save_load`) via the SAME run_all() entry.
## Run: godot --headless --path tingen -s tests/test_hermit_save_load.gd
##
## The pins:
##   R1  a Hermit run advanced to Seq 7 (both ladder arts granted) + dirtied meters/leads/shop
##       round-trips EVERY one of those subsystems through the disk save (pathway=="hermit" survives —
##       Progression.reset() used to hard-set hunter; the disk save used to drop meters/progression/
##       leads/shop entirely, M21 B3). A scrub-then-load proves the load did the restoring work.
##   R2  the PLAYER's spirituality pool is INTENTIONALLY transient (M31): it lives on the PlayerCombat
##       body, never in the autoload save manifest, and a fresh body re-inits it to FULL. This is BY
##       DESIGN (a regenerating reservoir, not saved run state) — assert it, so a future "persist
##       spirituality" change is a deliberate decision, not an accident, and the roundtrip never fails
##       for the "missing" pool.

const TMP_SAVE := "user://test_hermit_save_load.json"

func _init() -> void:
	await process_frame
	await process_frame
	# B3 (retro): NEVER touch the player's REAL persistent profile (user://meta.json) — redirect
	# the meta slot to a test-scoped file before anything drives RunManager (tests/test_meta_isolation.gd).
	root.get_node("/root/RunManager").set("meta_path", "user://meta_test.json")
	root.get_node("/root/RunManager").reload_meta()
	var r: Dictionary = run_all()
	print("\n=== test_hermit_save_load: %d passed, %d failed ===" % [int(r["passed"]), int(r["failed"])])
	quit(1 if int(r["failed"]) > 0 else 0)

## The one entry point (returns {passed, failed}); folded into run_tests.gd.
static func run_all() -> Dictionary:
	var c := {"passed": 0, "failed": 0}
	_r1_hermit_run_roundtrips(c)
	_r2_spirituality_transient_reinits_full(c)
	# Leave a clean Hunter world for whatever runs next in the shared suite.
	var root := _root()
	root.get_node("/root/RunManager").start_run()
	root.get_node("/root/Progression").select_pathway("hunter")
	return c

# --- R1: the whole Hermit run round-trips through the disk save ---------------------------------
static func _r1_hermit_run_roundtrips(c: Dictionary) -> void:
	print("[R1: a Hermit run (Seq 7 + granted arts + meters + leads + shop) round-trips through the disk save]")
	var root := _root()
	var SM: Object = root.get_node("/root/SaveManager")
	var RM: Object = root.get_node("/root/RunManager")
	var AG: Object = root.get_node("/root/Agents")
	var M: Object = root.get_node("/root/Meters")
	var P: Object = root.get_node("/root/Progression")
	var LS: Object = root.get_node("/root/LeadSystem")
	var S: Object = root.get_node_or_null("/root/Shop")

	# Stage a genuine LIVE Hermit run (unlock -> start_run('hermit')), then advance it to the Seq-7 slice
	# cap with BOTH ladder arts granted, and DIRTY the meters/leads/shop the way a mid-run save would find.
	_unlock_hermit(RM)
	RM.start_run("hermit")
	AG.rebuild()
	_check(c, P.pathway() == "hermit" and P.sequence() == 9, "a live Hermit run begins Hermit · Seq 9")
	# Advance to Seq 7 carrying the two authored Hermit ladder arts (the state a two-kill climb leaves).
	P.from_dict({"pathway": "hermit", "sequence": 7,
		"granted_arts": ["astral_chains", "collapsing_star"], "deed_done": true})
	M.set_meter("doom", 63.0)
	M.set_meter("madness", 41.0)
	M.set_meter("notice", 22.0)
	M.set_meter("heat", 18.0)
	LS.slot_run(31337)
	LS.follow("hermit_prey_finch")   # a followed Hermit prey lead — must survive the roundtrip
	if S != null:
		S.from_dict({"restocks_used": 1})

	var want_meters: Dictionary = M.to_dict()
	var want_prog: Dictionary = P.to_dict()
	var want_leads: Dictionary = LS.to_dict()
	var want_shop: Dictionary = S.to_dict() if S != null else {}

	# Persist to a temp slot, then SCRUB the live world (simulating a fresh process at the title).
	_check(c, bool(SM.save_game(TMP_SAVE)), "save_game writes the temp slot")
	M.reset(); P.reset(); LS.reset()
	if S != null:
		S.reset()

	# The scrub really cleared the Hermit state (so a green load can't be a no-op).
	_check(c, P.pathway() != "hermit", "reset scrubbed the pathway back off Hermit (state was live)")
	_check(c, P.sequence() == 9, "reset scrubbed the Sequence back to 9")
	_check(c, not _dict_eq(M.to_dict(), want_meters), "reset scrubbed the meters")

	# Load the slot back and prove EVERY subsystem returned.
	_check(c, bool(SM.load_game(TMP_SAVE)), "load_game reads the temp slot")
	_check(c, P.pathway() == "hermit", "R1: the run's PATHWAY restored to 'hermit' from disk")
	_check(c, P.sequence() == 7, "R1: the Sequence rung (Seq 7) restored from disk")
	_check(c, P.granted_arts().has("astral_chains") and P.granted_arts().has("collapsing_star"),
		"R1: the granted Hermit arts (astral_chains + collapsing_star) restored from disk")
	_check(c, _dict_eq(P.to_dict(), want_prog), "R1: the full progression dump restored byte-for-byte")
	_check(c, _dict_eq(M.to_dict(), want_meters), "R1: the meters (Doom/Madness/Notice/Heat) restored from disk")
	_check(c, _dict_eq(LS.to_dict(), want_leads), "R1: the leads (the followed Hermit prey lead) restored from disk")
	if S != null:
		_check(c, _dict_eq(S.to_dict(), want_shop), "R1: the shop (stock latch) restored from disk")

	# Leave a clean world for later tests.
	RM.start_run()

# --- R2: the player's spirituality pool is transient by design + re-inits to full ---------------
static func _r2_spirituality_transient_reinits_full(c: Dictionary) -> void:
	print("[R2: spirituality is INTENTIONALLY transient (M31) — not in the save manifest, re-inits to full]")
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

	# A fresh player body re-inits the pool to FULL (a regenerating reservoir, not saved run state) —
	# so a post-load body starts topped up, never stuck at whatever the pre-save value happened to be.
	var pc = PlayerCombat.new()
	var now := float(pc.call("spirituality_now"))
	var maxv := float(pc.call("spirituality_max"))
	_check(c, maxv > 0.0 and is_equal_approx(now, maxv),
		"a fresh PlayerCombat re-inits spirituality to FULL (%.0f / %.0f) — transient, not a save bug" % [now, maxv])
	# And even after the pool is DRAINED, a brand-new body (the post-load body) comes back full — proving
	# the roundtrip never carries a stale/empty pool across the save boundary.
	pc.set("spirituality", 0.0)
	var pc2 = PlayerCombat.new()
	_check(c, is_equal_approx(float(pc2.call("spirituality_now")), maxv),
		"a NEW body after a drained one still re-inits to full (the pool never persists a stale value)")
	pc.free()
	pc2.free()

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

## Drive the first-win meta unlock so Hermit is a selectable pathway (mirrors test_hermit_live).
static func _unlock_hermit(RM: Object) -> void:
	RM.reset_meta()
	RM.start_run()
	RM.end_run("win", {"outcome": "descent_stopped"})
	RM.reload_meta()

## Compare two subsystem dicts for RESTORED-STATE equality, normalized through a JSON round-trip first
## (a disk save->load coerces whole-number ints to floats; the game reads via int()/float() casts, so
## that is a representation artifact, not state loss). Same pattern as test_save_spend_seed._dict_eq.
static func _dict_eq(a: Dictionary, b: Dictionary) -> bool:
	return _norm(a) == _norm(b)

static func _norm(d: Variant) -> String:
	return JSON.stringify(JSON.parse_string(JSON.stringify(d, "", true, true)), "", true, true)
