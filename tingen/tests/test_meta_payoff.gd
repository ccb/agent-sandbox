extends SceneTree
## M27 — Meta-progression payoff harness. Runs headless (no display): drive the Ritual Night climax
## to each outcome and assert the PERSISTENT meta reacts — the codex grows + dedupes, the first win
## unlocks the Fool pathway (a loss does not), the run-start pathway pick reads that unlock, the two
## wins pay UNEQUAL meta-currency (avatar_slain > descent_stopped), NO run stat inherits across a run
## boundary, and the whole meta round-trips through its own disk slot (separate from the run save).
##
## Run: godot --headless --path tingen -s tests/test_meta_payoff.gd
##
## TDD (M27, backlog "M21"): TODAY end_run('win'/'lose') writes NOTHING to _meta — death/win changes
## nothing about the next run. These assertions watch RED against that stub, then GREEN once the codex
## writer / Fool unlock / differential payout land in RunManager (+ the pathway pick read in Progression).

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

	_test_codex_grows_and_dedupes()          # (a)
	_test_first_win_unlocks_hermit()          # (b)
	_test_pathway_pick_reads_unlocks()        # (c)
	_test_win_grade_differential_payout()     # (d)
	_test_no_stat_inheritance()               # (e)
	_test_meta_roundtrips_separate_slot()     # (f)
	_test_win_reward_tables_stay_in_sync()    # (g) N1 guard: no WIN unlocks Fool yet pays 0
	_test_second_win_chain_unlocks_death()    # (h) N5: the WIN_UNLOCK_CHAIN's second entry

	print("\n=== meta_payoff: %d passed, %d failed ===" % [_passed, _failed])
	quit(1 if _failed > 0 else 0)

func _ok(cond: bool, label: String) -> void:
	if cond:
		_passed += 1
		print("  PASS  %s" % label)
	else:
		_failed += 1
		printerr("  FAIL  %s" % label)

# --- seams ------------------------------------------------------------------------------------
func _rm() -> Object:
	return root.get_node("/root/RunManager")

func _rn() -> Object:
	return root.get_node("/root/RitualNight")

func _agents() -> Object:
	return root.get_node("/root/Agents")

func _prog() -> Object:
	return root.get_node("/root/Progression")

func _eb() -> Object:
	return root.get_node("/root/EventBus")

## A fresh run + a scrubbed climax controller (mirrors test_ritual_night._fresh).
func _fresh() -> Object:
	_rm().start_run()
	_agents().rebuild()
	var rn := _rn()
	rn.reset()
	return rn

# --- outcome stagers (drive the climax to a concrete outcome -> end_run) -----------------------
func _win_descent_stopped(seed_val: int) -> void:
	var rn := _fresh_for_win()
	rn.force_assault(false, seed_val)
	rn.use_interrupt_interactable()
	rn.clear_backlash_wave()

func _win_avatar_slain(seed_val: int) -> void:
	var rn := _fresh_for_win()
	rn.force_assault(false, seed_val)
	rn.tick_fuse(rn.fuse_remaining() - rn.avatar_threshold() + 1)
	var av: Agent = _agents().get_agent(rn.avatar_id())
	if av != null:
		av.take_damage(av.hp + 10.0)
		rn.notify_agent_downed(av.id)

func _lose_descent(seed_val: int) -> void:
	var rn := _fresh_for_win()
	rn.force_assault(false, seed_val)
	rn.tick_fuse(9999)

## _fresh() but re-armed so a prior climax's terminal-death latch doesn't swallow the ending screen.
func _fresh_for_win() -> Object:
	var rn := _fresh()
	var eg := root.get_node_or_null("/root/EndGame")
	if eg != null and eg.has_method("rearm"):
		eg.rearm()
	return rn

## Down a synthetic adversary DURING the active run (mirrors a live agent_downed from CombatExecutor):
## register an agent carrying a combat_form + pathway, then publish the fact the codex writer ears.
func _down_adversary(id: String, form: String, pathway: String) -> void:
	var reg := _agents()
	var a: Agent = reg.get_agent(id)
	if a == null:
		a = Agent.new(id)
		a.display_name = id
		reg.register_agent(a)
	a.combat_form = form
	a.pathway = pathway
	a.room = "meta_room"
	_eb().emit_event("agent_downed", {"actor": "player", "target": id})

func _has_codex_id(codex: Array, id: String) -> bool:
	for e in codex:
		if e is Dictionary and String((e as Dictionary).get("id", "")) == id:
			return true
	return false

# --- (a) the codex grows on run end + dedupes across runs -------------------------------------
func _test_codex_grows_and_dedupes() -> void:
	print("[codex: a run end writes per-encounter knowledge; deduped + persisted across runs]")
	var RM := _rm()
	RM.reset_meta()
	var before: int = RM.meta_codex().size()
	# Run 1: down an adversary, then win by breaking the rite (descent_stopped).
	var rn := _fresh_for_win()
	_down_adversary("meta_foe_a", "butcher_human", "hunter")
	rn.force_assault(false, 4242)
	rn.use_interrupt_interactable()
	rn.clear_backlash_wave()
	var after1: Array = RM.meta_codex()
	_ok(after1.size() > before, "a winning run WRITES codex entries (RED today: end_run writes nothing)")
	_ok(_has_codex_id(after1, "ending:descent_stopped"), "the codex records the ending reached")
	_ok(_has_codex_id(after1, "adversary:butcher_human"), "the codex records a downed adversary faced")
	_ok(_has_codex_id(after1, "pathway:hunter"), "the codex records the pathway seen")
	var all_lined := true
	for e in after1:
		if not (e is Dictionary) or String((e as Dictionary).get("learned", "")) == "":
			all_lined = false
	_ok(all_lined, "every codex entry carries a short learned line (id + line)")
	# Run 2: the SAME adversary/pathway (dedupe) plus ONE new ending (avatar_slain) -> grows by exactly 1.
	var size1 := after1.size()
	rn = _fresh_for_win()
	_down_adversary("meta_foe_a", "butcher_human", "hunter")   # same form -> must dedupe
	rn.force_assault(false, 4242)
	rn.tick_fuse(rn.fuse_remaining() - rn.avatar_threshold() + 1)
	var av: Agent = _agents().get_agent(rn.avatar_id())
	if av != null:
		av.take_damage(av.hp + 10.0)
		rn.notify_agent_downed(av.id)
	var after2: Array = RM.meta_codex()
	_ok(_has_codex_id(after2, "ending:avatar_slain"), "run 2 adds the new ending fact to the codex")
	var seen := {}
	var dup := false
	for e in after2:
		var i := String((e as Dictionary).get("id", ""))
		if seen.has(i):
			dup = true
		seen[i] = true
	_ok(not dup, "the codex is DEDUPED — no repeated ids across the two runs")
	_ok(after2.size() == size1 + 1, "run 2 grows the codex by exactly the ONE new fact (rest deduped)")

# --- (b) first WIN unlocks the build + persists; a LOSS does not ------------------------------
## M28 retargeted the first-win unlock from the Fool STUB to the real HERMIT build (RunManager
## FIRST_WIN_PATHWAY). Fool stays a future stub and is no longer granted by the first win.
func _test_first_win_unlocks_hermit() -> void:
	print("[unlock: the first win adds 'hermit' to unlocked_pathways + persists; a loss does not]")
	var RM := _rm()
	RM.reset_meta()
	_ok(not RM.meta_unlocked_pathways().has("hermit"), "a fresh profile has the Hermit pathway LOCKED")
	# A losing run must NOT unlock.
	_lose_descent(4242)
	_ok(not RM.meta_unlocked_pathways().has("hermit"), "a LOSING run does not unlock Hermit")
	# The first WIN unlocks it.
	_win_descent_stopped(4242)
	_ok(RM.meta_unlocked_pathways().has("hermit"), "the first WIN unlocks the Hermit pathway")
	_ok(not RM.meta_unlocked_pathways().has("fool"), "the Fool stays a future stub (not granted by the first win)")
	# It PERSISTS to the meta slot — readable after a fresh re-read (i.e. next boot / next run).
	RM.reload_meta()
	_ok(RM.meta_unlocked_pathways().has("hermit"), "the Hermit unlock PERSISTS to the meta slot (survives reload)")

# --- (h) N5: the WIN-UNLOCK CHAIN's second entry — win #2 pays AND unlocks death ----------------
## The M_death unlock design: RunManager.WIN_UNLOCK_CHAIN replaces the single FIRST_WIN_PATHWAY
## const — each WIN unlocks the FIRST chain entry not yet owned (at most one per win, the roguelite
## drip). Win #1 stays byte-identical (hermit, pinned by (b)); win #2 unlocks death AND still pays
## currency; meta_last_payoff.new_unlocks NAMES the unlock so the EndGame payoff screen renders it
## (MetaSurface renders new_unlocks generically); a third win walks off the chain end and grants
## nothing more. Codex copy: a Death run's flush records pathway:death with a real learned line.
func _test_second_win_chain_unlocks_death() -> void:
	print("[chain (N5): win #2 pays currency AND unlocks death; new_unlocks names it; a 3rd win grants nothing]")
	var RM := _rm()
	var P := _prog()
	RM.reset_meta()
	# Win #1 -> hermit only (the drip: death stays locked).
	_win_descent_stopped(4242)
	_ok(RM.meta_unlocked_pathways().has("hermit") and not RM.meta_unlocked_pathways().has("death"),
		"win #1 unlocks hermit ONLY — death stays locked (one unlock per win)")
	var cur_after_1 := int(RM.meta_currency())
	# Win #2 -> death, AND the payout still lands (an unlock never eats the currency).
	_win_descent_stopped(4242)
	_ok(RM.meta_unlocked_pathways().has("death"), "win #2 unlocks the Death pathway (the chain's second entry)")
	_ok(int(RM.meta_currency()) > cur_after_1, "win #2 STILL pays meta-currency (%d > %d)" % [int(RM.meta_currency()), cur_after_1])
	var payoff: Dictionary = RM.meta_last_payoff()
	_ok((payoff.get("new_unlocks", []) as Array).has("death"),
		"meta_last_payoff.new_unlocks NAMES death (the EndGame payoff screen renders it)")
	RM.reload_meta()
	_ok(RM.meta_unlocked_pathways().has("death"), "the Death unlock PERSISTS to the meta slot (survives reload)")
	# A third win walks off the chain end: currency still pays, but nothing new unlocks.
	var owned: int = RM.meta_unlocked_pathways().size()
	_win_descent_stopped(4242)
	_ok(RM.meta_unlocked_pathways().size() == owned,
		"a THIRD win walks off the chain end and unlocks nothing more")
	_ok((RM.meta_last_payoff().get("new_unlocks", []) as Array).is_empty(),
		"…and its payoff reports no new unlock (new_unlocks empty)")
	# Codex copy: a run WALKED as Death records the pathway:death fact with a real learned line.
	var rn := _fresh_for_win()
	P.select_pathway("death")   # the unlock honors the pick — this run is a Death run
	rn.force_assault(false, 4242)
	rn.use_interrupt_interactable()
	rn.clear_backlash_wave()
	var entry := {}
	for e in RM.meta_codex():
		if e is Dictionary and String((e as Dictionary).get("id", "")) == "pathway:death":
			entry = e
	_ok(not entry.is_empty() and String(entry.get("learned", "")) != "",
		"the codex records pathway:death with a non-empty learned line")
	_ok(String(entry.get("learned", "")).findn("death") >= 0,
		"…and the learned line actually speaks of the Death pathway (authored copy, not a blank template)")
	P.select_pathway("hunter")   # hygiene

# --- (c) the run-start pathway pick READS _meta.unlocked_pathways ------------------------------
func _test_pathway_pick_reads_unlocks() -> void:
	print("[pick: run-start pathway pick reads the meta unlocks — Hunter always; Hermit after the win]")
	var RM := _rm()
	var P := _prog()
	RM.reset_meta()
	_ok(P.available_pathways().has("hunter"), "Hunter is ALWAYS available at the pick")
	_ok(not P.available_pathways().has("hermit"), "Hermit is NOT available before the unlock")
	_ok(String(P.select_pathway("hermit")) == "hunter", "picking a locked Hermit falls back to Hunter")
	# Win once -> unlock Hermit -> the pick honors it next run.
	_win_descent_stopped(4242)
	RM.reload_meta()
	_ok(P.available_pathways().has("hermit"), "after the win, Hermit is available at the pick")
	_ok(String(P.select_pathway("hermit")) == "hermit", "the pick now HONORS the Hermit unlock")
	_ok(String(P.pathway()) == "hermit", "Progression's live pathway is set to the picked Hermit")
	P.select_pathway("hunter")   # hygiene: back to the slice default

# --- (d) avatar_slain pays MORE meta reward than descent_stopped ------------------------------
func _test_win_grade_differential_payout() -> void:
	print("[payout: the Deep Win (avatar_slain) pays MORE meta-currency than the Quiet Win (descent_stopped)]")
	var RM := _rm()
	RM.reset_meta()
	_win_descent_stopped(4242)
	var quiet := int(RM.meta_currency())
	RM.reset_meta()
	_win_avatar_slain(4242)
	var deep := int(RM.meta_currency())
	_ok(quiet > 0, "the Quiet Win pays some meta-currency (got %d)" % quiet)
	_ok(deep > quiet, "the Deep Win pays MORE than the Quiet Win (%d > %d)" % [deep, quiet])
	# A LOSE pays nothing.
	RM.reset_meta()
	_lose_descent(4242)
	_ok(int(RM.meta_currency()) == 0, "a LOSE (descent_complete) pays no meta-currency")

# --- (g) N1 guard: the two outcome tables never drift — every WIN pays positive currency --------
func _test_win_reward_tables_stay_in_sync() -> void:
	print("[tables in sync: every WIN_OUTCOMES grade carries a positive META_REWARD currency (no silent 0-pay win)]")
	var RM := _rm()
	_ok(RM.meta_reward_tables_ok(), "the shipped WIN_OUTCOMES / META_REWARD tables are consistent (no win pays 0)")
	# Prove the guard actually catches a drift: every declared win must resolve to a positive payout,
	# which is exactly what a first-win Fool unlock rides on. Belt-and-suspenders over the two consts.
	for w in RM.WIN_OUTCOMES:
		var r = RM.META_REWARD.get(w)
		_ok(r is Dictionary and int((r as Dictionary).get("currency", 0)) > 0,
			"WIN outcome '%s' pays positive meta-currency (not a silent 0-pay unlock)" % String(w))

# --- (e) NO stat inheritance: only codex/unlocks/currency carry, never rank/hp/gear -----------
func _test_no_stat_inheritance() -> void:
	print("[no inheritance: a fresh run does NOT inherit rank/hp/gear — only meta (codex/unlock/currency) carries]")
	var RM := _rm()
	var P := _prog()
	RM.reset_meta()
	# Run A: climb a rank, arm/damage the player proxy, then WIN.
	var rn := _fresh_for_win()
	var proxy: Agent = _agents().ensure_player_proxy(Vector2.ZERO, "meta_room")
	proxy.add_item("hunter_characteristic", 1)
	P.mark_deed_done()
	var adv: Dictionary = P.advance()   # Seq 9 -> 8, grows the kit (mark_prey)
	_ok(bool(adv.get("ok", false)) and int(P.sequence()) == 8, "run A climbs to Seq 8")
	_ok(not P.granted_arts().is_empty(), "run A grew the kit (a granted art)")
	proxy.add_item("meta_test_gear", 5)
	proxy.take_damage(40.0)
	_ok(proxy.hp < proxy.max_hp, "run A damaged the player proxy")
	rn.force_assault(false, 4242)
	rn.use_interrupt_interactable()
	rn.clear_backlash_wave()   # WIN -> end run A
	var carried_currency := int(RM.meta_currency())
	# Run B: a fresh run — assert NONE of the run stats inherited.
	_fresh()
	var proxy_b: Agent = _agents().ensure_player_proxy(Vector2.ZERO, "meta_room")
	_ok(int(P.sequence()) == 9, "run B starts back at Seq 9 (rank NOT inherited)")
	_ok(P.granted_arts().is_empty(), "run B has an empty kit (granted arts NOT inherited)")
	_ok(proxy_b.hp == proxy_b.max_hp, "run B's player proxy is at full HP (hp NOT inherited)")
	_ok(proxy_b.item_count("meta_test_gear") == 0, "run B does not carry run A's gear (gear NOT inherited)")
	# ...but the META did carry across the boundary (the ONLY thing that inherits).
	_ok(int(RM.meta_currency()) == carried_currency and carried_currency > 0,
		"only the META carries across the run boundary (currency inherited, stats did not)")

# --- (f) the meta ROUND-TRIPS through its own slot, separate from the run save ----------------
func _test_meta_roundtrips_separate_slot() -> void:
	print("[roundtrip: meta writes on end_run -> reload the slot -> present; a SEPARATE file from the run save]")
	var RM := _rm()
	RM.reset_meta()
	_win_descent_stopped(4242)
	var codex_n: int = RM.meta_codex().size()
	var cur := int(RM.meta_currency())
	_ok(codex_n > 0 and cur > 0 and RM.meta_unlocked_pathways().has("hermit"),
		"the win wrote codex + currency + unlock to meta")
	# Round-trip: drop the cache, re-read the disk slot, assert everything survives.
	RM.reload_meta()
	_ok(RM.meta_codex().size() == codex_n, "the codex round-trips through the meta slot")
	_ok(int(RM.meta_currency()) == cur, "the meta-currency round-trips through the meta slot")
	_ok(RM.meta_unlocked_pathways().has("hermit"), "the Hermit unlock round-trips through the meta slot")
	# The ACTIVE meta slot is a SEPARATE file from the run save (not entangled with the M21 run-save
	# manifest). B3: asserted on RM.meta_path (the redirected test slot), not the real META_PATH —
	# the suite must never require (or touch) the real profile file.
	var save_path := String(root.get_node("/root/SaveManager").SAVE_PATH)
	_ok(String(RM.meta_path) != save_path, "the meta slot is a SEPARATE user:// file from the run save")
	_ok(FileAccess.file_exists(RM.meta_path), "the meta slot is persisted to its own user:// file")
