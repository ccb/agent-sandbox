extends Node
## Run lifecycle owner (autoload singleton `RunManager`). M2 run shell.
##
## Tingen is a ROGUELITE (direction v2 §8, §13 LOCKED): ~7 in-game days, ~60 min, a nightly
## safe-house checkpoint; death/rampage costs the CURRENT DAY, not the whole run. RunManager owns
## that lifecycle — starting a fresh run, tracking the ~7-day calendar over the existing Clock
## phases, snapshotting at each safe-house night, and ending a run (death/lost_control restore to
## the last checkpoint; win/lose end the run → meta → title). It does NOT own the climax SCREEN —
## that stays in EndGame; RunManager just receives the summoning_climax and calls end_run().
##
## Design notes:
##   * The single reset seam. start_run() scrubs every run-scoped subsystem back to run-start so a
##     fresh run is byte-identical to the very first (fixes GAP-2.9 — the EndGame restart leak). It
##     reuses each subsystem's own reset()/rebuild()/clear(), never reaching into their internals.
##   * Checkpoints are in-memory snapshots built from the same to_dict()/from_dict() contract
##     SaveManager uses, so a nightly restore is a pure data reload (no scene work here — the boot
##     controller / GameController own scene swaps).
##   * MetaState is a tiny persistent record that SURVIVES restart, in a SEPARATE user:// slot from
##     the run save: runs_played, the growing codex (what you know about the occult city), the earned
##     unlocked_pathways (Fool after the first win), and a meta_currency. M27 WRITES all of it on a
##     win/lose run-end (the roguelite's reason to replay). No stat inheritance (§8) — meta is
##     bookkeeping (codex + unlocks + currency), never power (never hp/rank/gear).

signal run_started(day: int)
signal run_ended(reason: String)
signal day_rolled(day: int)
signal checkpoint_saved(day: int)

## The run calendar — ~7 in-game days (direction v2 §13 LOCKED). Ritual Night is the last day.
const TOTAL_DAYS: int = 7
const RUN_START_MINUTE: int = 480   # 08:00 — Clock's canonical morning start.

## P1 (experiential wave) — the RUN PACE, the ~60-minute budget (§13) made an EXPLICIT run constant.
## Clock's own default (1.0 s/game-min = 24 real-min/day) was ~2.3x over budget, and the only thing
## that ever set a faster pace (CitySummoning._bootstrap's demo override) has been DEAD/unmounted
## since M20 — so every live run silently played at the slow default. The pace is now RunManager's
## to own: applied at run start / wipe / checkpoint-restore / disk-load (never a scene side-effect).
## The arithmetic (from MeterDrivers' passive Doom fill, the run's real pacer — pinned by
## tests/test_run_pace.gd so a retune moves the pin too):
##   passive fill/day = DOOM_PER_HOUR 0.3*24 + DOOM_PER_PHASE 1.7*6      = 17.4 Doom/day
##   idle Doom-100    = 100 / 17.4 = ~5.75 days                          = ~8280 game-minutes
##   at 0.42 s/game-min: 8280 * 0.42 = ~3478 s                           = ~58 real minutes  ✓
##   (the full 7-day calendar ceiling: 10080 * 0.42 = ~71 real minutes)
const RUN_SECONDS_PER_GAME_MINUTE: float = 0.42

## Where the player wakes: the LODGING (the existing IntroRoom scene, reused as Klein's bedroom).
const LODGING_SCENE: String = "res://scenes/IntroRoom.tscn"

const META_PATH: String = "user://meta.json"
const META_VERSION: int = 1

## B3 (retro): the ACTIVE meta slot — REDIRECTABLE so tests never read or wipe the real player
## profile (tests share user:// with the live game; the suite used to reset_meta()/end_run straight
## into the real user://meta.json). Live play never touches this default; every test harness points
## it at a test-scoped file (user://meta_test.json) and reload_meta()s before driving any meta seam.
## N1 (sprint safety): harnesses now redirect it via src/TestSandbox.gd `activate()` into
## user://test_sandbox/<run>/, whose write guard also REFUSES out-of-sandbox meta writes.
var meta_path: String = META_PATH
const _TSandbox := preload("res://src/TestSandbox.gd")

## M27 (backlog "M21") — the meta PAYOFF constants (the roguelite's reason to replay). All three
## payoffs (codex / Fool unlock / differential currency) are DATA, not NPC/id branches (§8, engine
## neutrality): they key off the climax OUTCOME string the RitualNight resolver already produces.
const SCENARIO_PATH: String = "res://data/scenario.json"

## The two climax WIN outcomes (RitualNight): avatar_slain = the hard "Deep Win" (strike the half-
## landed god), descent_stopped = the "Quiet Win" (break the rite at the altar). A win is what
## unlocks Fool + pays currency; descent_complete is the LOSE.
const WIN_OUTCOMES: Array = ["avatar_slain", "descent_stopped"]

## M_death — the WIN-UNLOCK CHAIN (replaces the single FIRST_WIN_PATHWAY const): each WIN unlocks the
## FIRST chain entry not yet owned (at most ONE per win — the roguelite drip). Win 1 -> hermit
## (byte-identical to the pinned first-win behavior for a fresh profile); win 2 -> death (the third
## playable build: censer/grave kit, the sister_auber/brother_cassian prey, the Death ladder). Writing
## an entry into _meta.unlocked_pathways is the whole unlock; available_pathways()/select_pathway honor
## it next run. Data-driven: a table walk, no pathway/id branch — a future 4th pathway is one more
## entry. Losses grant nothing; a win past the chain end grants nothing (asserted in test_meta_payoff).
const WIN_UNLOCK_CHAIN: Array = ["hermit", "death"]

## The win-grade DIFFERENTIAL payout (M27): the two wins pay UNEQUAL meta-currency — the push-your-
## luck harder win (avatar_slain) pays more than the safer win (descent_stopped); a LOSE pays nothing.
## Meta-currency is bookkeeping toward future meta unlocks, NEVER run power (§8 — no stat inheritance).
## Data table (not code branches) so the payout curve is tunable and outcome-keyed. TUNING placeholder.
const META_REWARD: Dictionary = {
	"avatar_slain": {"currency": 3},      # Deep Win — the harder, push-your-luck win pays the most
	"descent_stopped": {"currency": 1},   # Quiet Win — a real win, but the safer grade pays less
	"descent_complete": {"currency": 0},  # LOSE — the descent completed; no reward
}

var _current_day: int = 1
var _run_active: bool = false

## The last nightly safe-house snapshot (a data dict, or {} when none this run). Restoring to it
## costs the current day; absent it (day-1 pre-checkpoint) a death restarts the run.
var _checkpoint: Dictionary = {}
var _checkpoint_day: int = 0

## Persistent meta — survives restart. Loaded lazily on first access / _ready.
var _meta: Dictionary = {}
var _meta_loaded: bool = false

## M27 — the RUN-SCOPED knowledge ledger (a set of codex fact-ids learned THIS run). Grown as the run
## plays (adversaries downed, the pathway seen) and flushed into the persistent _meta.codex on a
## win/lose run-end, deduped. Reset at run start (a fresh run learns from scratch); it is NOT meta —
## only what survives the flush into _meta.codex carries across runs.
var _run_knowledge: Dictionary = {}

## M27 — the codex "learned line" copy table, loaded lazily from data/scenario.json's `codex` block
## (content-in-data, §engine neutrality). Cached; a robust code fallback covers a missing block so the
## codex still reads without the data.
var _codex_lore_cache: Dictionary = {}
var _codex_lore_loaded: bool = false

func _ready() -> void:
	# Roll the run day when the Clock crosses a day boundary. Idempotent connect for world swaps.
	if not Clock.day_rolled.is_connected(_on_clock_day_rolled):
		Clock.day_rolled.connect(_on_clock_day_rolled)
	# M9 Gap 2: the nightly safe-house checkpoint. When the Clock rolls into NIGHT and the player is
	# resting in the LODGING (the safe house), snapshot the run — so a later death/rampage costs the
	# current day (restore) rather than wiping the run (was: checkpoint_night had NO live caller, so
	# has_checkpoint() was always false and every death fell through to a full day-1 wipe).
	if not Clock.phase_changed.is_connected(_on_clock_phase_changed):
		Clock.phase_changed.connect(_on_clock_phase_changed)
	# The climax fires through EndGame's SCREEN; RunManager owns the run OUTCOME. Listen directly to
	# the plan so the run ends whether or not the EndGame overlay is mounted (headless included).
	if not SummoningPlan.summoning_climax.is_connected(_on_summoning_climax):
		SummoningPlan.summoning_climax.connect(_on_summoning_climax)
	# M4: Doom topping out flags Ritual Night — the run's climax (§9). The climax SCREEN itself is
	# M7; for now RunManager latches it so the calendar/climax gating can already ask.
	if Meters != null and not Meters.ritual_night.is_connected(_on_ritual_night):
		Meters.ritual_night.connect(_on_ritual_night)
	# M27: the codex writer's EAR. A downed Beyonder (agent_downed) during a live run is a thing the
	# player LEARNED — record it into the run knowledge ledger (flushed to _meta.codex on run end). A
	# passive read only (records a fact-id into a Dictionary), so it never touches combat/RNG and is
	# inert outside an active run (the sims never start one). Idempotent connect across world swaps.
	if EventBus != null and not EventBus.event_logged.is_connected(_on_meta_world_event):
		EventBus.event_logged.connect(_on_meta_world_event)
	# M27 N1 guard: WIN_OUTCOMES (drives the Fool unlock) and META_REWARD (drives currency) are two
	# parallel outcome tables. A future win added to one but not the other would unlock Fool yet pay 0
	# currency silently. Fail loud at boot if they ever drift out of sync (see meta_reward_tables_ok()).
	assert(meta_reward_tables_ok(), "M27: a WIN_OUTCOMES entry has no positive META_REWARD currency — the two meta tables drifted")
	# P1: the Continue path (BootController -> SaveManager.load_game) never passes through start_run,
	# and the pace is a run CONSTANT (not snapshot state — Clock.to_dict never carries it), so a loaded
	# run must have the pace re-applied here. Idempotent connect across world swaps.
	if not SaveManager.loaded.is_connected(_on_save_loaded):
		SaveManager.loaded.connect(_on_save_loaded)
	_load_meta()

## P1 — apply the run's explicit pace to the Clock. The ONE pace writer (run start, day-1 wipe,
## checkpoint restore, disk load all route here); scenes never set the pace as a side-effect.
func _apply_run_pace() -> void:
	Clock.real_seconds_per_game_minute = RUN_SECONDS_PER_GAME_MINUTE

func _on_save_loaded(_path: String) -> void:
	_apply_run_pace()

# --- Ritual Night (M4 hook; the climax SCREEN is M7) ------------------------------------------
## True once Doom has reached 100 this run — the descent's fuse is lit. The playable climax is M7;
## this latch is the seam that gating (and the run summary) reads today.
var _ritual_night: bool = false

func ritual_night_reached() -> bool:
	return _ritual_night

func _on_ritual_night() -> void:
	if not _run_active:
		return
	_ritual_night = true

# --- Calendar ---------------------------------------------------------------------------------
## The run day IS the Clock day while a run is live (the Clock is the single time source — a
## day_rolled OR a direct Clock.set_time both move the run day). Between runs, the last stamped day.
func current_day() -> int:
	if _run_active:
		_current_day = Clock.day
	return _current_day

## The current Clock phase (bare, e.g. "morning") — the run's phase IS the Clock's phase.
func current_phase() -> String:
	return Clock.phase

func total_days() -> int:
	return TOTAL_DAYS

## True on the final day (Ritual Night lands here). M4+ hooks the climax gating to this.
func is_final_day() -> bool:
	return _current_day >= TOTAL_DAYS

func run_active() -> bool:
	return _run_active

func _on_clock_day_rolled(day: int) -> void:
	if not _run_active:
		return
	_current_day = day
	day_rolled.emit(_current_day)

## M9 Gap 2: the safe-house night beat. Take the nightly checkpoint the FIRST time each day the
## Clock enters NIGHT while the player is resting in the LODGING (the safe house). Gated so it fires
## at most once per day and only from the safe house — a death out in the streets can't checkpoint.
func _on_clock_phase_changed(phase: String, _day: int) -> void:
	if not _run_active:
		return
	# P1: the rest-until-morning fast-forward crosses nightfall on its way to 08:00 — the verb takes
	# its OWN single checkpoint at the morning landing, so the nightly auto-snapshot must stand down
	# for the duration (else one rest would checkpoint twice: nightfall + morning).
	if _resting:
		return
	if phase != "night":
		return
	# Only the safe house (the lodging) is a safe point — checkpoint nowhere else.
	if not _player_in_lodging():
		return
	# One checkpoint per day: a re-entry into the night phase the same day must not re-snapshot.
	if _checkpoint_day == current_day():
		return
	checkpoint_night()

## True when the live world scene is the lodging (the safe house). Reads the GameController
## (BootController) seam so RunManager never reaches into scene internals. Headless-safe (false when
## no controller is mounted — the harness drives checkpoint_night() directly).
func _player_in_lodging() -> bool:
	var ml := Engine.get_main_loop()
	if ml == null or not (ml is SceneTree):
		return false
	var gc := (ml as SceneTree).get_first_node_in_group("game_controller")
	if gc == null:
		return false
	var scene := ""
	if "current_scene_path" in gc:
		scene = String(gc.current_scene_path)
	return scene == LODGING_SCENE

# --- Meters (M4) ------------------------------------------------------------------------------
## The four meters (Doom/Madness/Notice/Heat) live in the Meters autoload (direction v2 §4). Doom is
## the world clock; this forwards it so downstream code (the run summary, doom-tiered opposition)
## can ask without reaching across autoloads.
func doom() -> float:
	return Meters.get_meter("doom") if Meters != null else 0.0

# --- Lifecycle --------------------------------------------------------------------------------
## Begin a FRESH run — the player-facing "New Run". Scrubs every run-scoped subsystem back to
## run-start (the GAP-2.9 fix), stamps day 1 / morning, seeds the run, clears any prior checkpoint,
## and bumps the persistent run count (this is the ONE place a "run played" is counted).
##
## M30 G1: `pathway_id` is the run's chosen PATHWAY (the New-Run pick). It is applied INSIDE the
## world reset — after Progression.reset() so the reset can't clobber it, and before LeadSystem
## slots the run's leads so the pathway-gated prey leads slot correctly. "" / a locked-or-unknown id
## falls back to the shipped Hunter build, so a no-arg start_run() is byte-identical to before.
func start_run(pathway_id: String = "") -> void:
	_bump_meta_runs()
	_restart_fresh(pathway_id)
	run_started.emit(_current_day)

## Reset the world to a fresh run WITHOUT counting it as a new run played. Shared by start_run()
## and the death-with-no-checkpoint path (a day-1 wipe is the same run continuing, not a new one).
func _restart_fresh(pathway_id: String = "") -> void:
	# B5 (M21): a genuinely NEW run RE-RANDOMIZES the world seed BEFORE the subsystem re-slots below
	# (WorldManager._start_run / LeadSystem.slot_run / AmmoSpawn.seed_run all read seed_value), so run 2
	# in a session differs from run 1 — the seed used to be frozen at its first value for the whole
	# session. A within-run checkpoint restore does NOT pass through here (it goes through _restore,
	# which reloads the checkpointed seed), so a death costs the day without reshuffling the run.
	WorldManager.seed_value = randi()
	_reset_run_world(pathway_id)
	_current_day = 1
	_checkpoint = {}
	_checkpoint_day = 0
	_ritual_night = false
	# M27: a genuinely NEW run learns the codex from scratch — scrub the run knowledge ledger (what
	# survives is only whatever the PRIOR run already flushed into the persistent _meta.codex). A
	# within-run checkpoint restore does NOT pass here, so a death keeps what this run has learned.
	_run_knowledge = {}
	# B3: a stale prior-run payoff must never render on a NEW run's ending screen.
	_last_payoff = {}
	# N3: re-arm the payoff latch — the NEW run's eventual end pays exactly once.
	_payoff_flushed = false
	_run_active = true

## Reset every run-scoped singleton to its run-start values. Reuses each subsystem's OWN reset
## (never reaches into internals) so this list is the complete "what makes a run" manifest. This is
## the single seam the leak test pins: after this, a fresh run == the very first run.
func _reset_run_world(pathway_id: String = "") -> void:
	# Time: back to day 1, 08:00 morning, at the run's explicit pace (P1 — the ~60-min budget).
	Clock.set_time(1, RUN_START_MINUTE)
	_apply_run_pace()
	# World pressures + lead.
	WorldState.reset()
	# The four meters (Doom/Madness/Notice/Heat) — re-derived from the freshly-reset pressures +
	# Madness/Heat zeroed + disclosure/ladder/rampage latches cleared (M4). MUST follow WorldState.reset
	# so Doom/Notice sync from run-start values.
	Meters.reset()
	# Investigation board.
	ClueDB.reset()
	# The cult's summoning attempt (countdown, ingredients, deposits, climax latch).
	SummoningPlan.reset()
	# M7: the Ritual Night climax (fuse, staged crypt roster, interrupt/avatar/backlash latches). A
	# fresh run must not inherit a prior climax's state. RitualNight owns its own reset seam.
	var rn := get_node_or_null("/root/RitualNight")
	if rn != null and rn.has_method("reset"):
		rn.reset()
	# The hidden director + its per-run flags.
	Overseer.reset()
	# Strategic stage machine + seeded slots (keep_state=false is a full reset).
	WorldManager._start_run(false)
	# Sequence progression (M5, direction v2 §6/§8): rank + granted arts back to Seq 9 (NO cross-run
	# stat inheritance), then APPLY the run's chosen PATHWAY (M30 G1). Ordered HERE — after reset() so
	# the reset can't clobber the pick back to Hunter (the old B2-class blocker), and BEFORE
	# LeadSystem.slot_run below so the pathway-gated prey leads slot against the RIGHT pathway (bug#3).
	# Engine-neutral: select_pathway honors the meta unlock and falls back to Hunter for "" / a locked
	# id, so a no-arg start_run stays byte-identical to the shipped Hunter run.
	Progression.reset()
	Progression.select_pathway(pathway_id)
	# The lead/quest layer (M6, direction v2 §5): scrub every lead, then GM-slot this run's leads
	# from the SAME deterministic run seed the strategic slots use, so the whole reshuffle is
	# reproducible per run (never RNG-in-combat). This seeds the guaranteed butcher lead (§3 opener).
	LeadSystem.reset()
	LeadSystem.slot_run(WorldManager.seed_value)
	# M8 (direction v2 §3): the GM-guaranteed first-ten-minutes opening. Scrub its per-run latches
	# here so a fresh run's opening is guaranteed AGAIN with no carry; the STAGING itself re-fires
	# from the run_started signal (begin_opening), which lands AFTER this reset completes — so the
	# butcher is staged + the hot lead surfaced onto the just-reset leads/roster.
	var gmo := get_node_or_null("/root/GMOpening")
	if gmo != null and gmo.has_method("reset"):
		gmo.reset()
	# M32: re-arm the counter-rite's once-per-run discoverability hint so a fresh run surfaces it again
	# the first time the player holds the ingredients (no carry — the same per-run latch lesson). Reached
	# via /root so the reset manifest doesn't hard-depend on the autoload's parse order under the -s harness.
	var cr := get_node_or_null("/root/CounterRite")
	if cr != null and cr.has_method("reset"):
		cr.reset()
	# Scrub the run-scoped navigable sites (the ActionCommit nav-site cache) before the opening
	# restages. The opening's begin_opening() re-registers its own where-site AFTER this reset (off
	# the run_started emit), so a fresh run's move targets are re-derived clean — no prior run's
	# staged site leaks a phantom target. (Was never cleared: harmless idempotent overwrite today,
	# but the reset manifest should own it so it can't rot as staging grows.)
	ActionCommit.clear_nav_sites()
	# Occult tools + the live agent roster (rebuild re-seeds every NPC from NpcDB).
	OccultToolManager.rebuild()
	Agents.rebuild()
	# M11: the Notice/Heat threat spawner (beyond_hunter / nighthawk_pursuer). Agents.rebuild() above
	# already dropped the runtime-registered threat agents; this scrubs MeterThreats' live-threat
	# bookkeeping so a fresh run inherits no phantom hunter (the leak lesson). Reached via /root so the
	# reset manifest doesn't hard-depend on the autoload's parse order under the -s harness.
	var mth := get_node_or_null("/root/MeterThreats")
	if mth != null and mth.has_method("reset"):
		mth.reset()
	# Per-scene activation flags (e.g. a turned waverer) must not survive into a new run.
	AgentRuntime.always_active.clear()
	# Carried items — a new run starts empty-handed (was leaking across restart, GAP-2.9).
	Inventory.clear()
	# Per-god prayer standing (was leaking: an old run's favour carried into the fresh run).
	PrayerService.reset()
	# (Sequence progression rank/pathway is scrubbed + the run's pathway applied EARLIER, before the
	# lead slot — see the Progression.reset()/select_pathway block above, M5 §6/§8 + M30 G1.)
	# Once-per-day deed latches (were leaking: already-fired deeds stayed latched into a new run).
	DeedRunner.reset()
	# Ground / dropped items (were leaking: a dropped item survived the restart).
	RoomItems.clear()
	# M13: Place world ammo pickups for this run (AFTER RoomItems.clear so no carry from prior run).
	# AmmoSpawn.seed_run is run-seeded (deterministic per seed) — the sprint-long leak lesson applied.
	var as_node := get_node_or_null("/root/AmmoSpawn")
	if as_node != null and as_node.has_method("seed_run"):
		as_node.seed_run(WorldManager.seed_value)
	# B1 (retro): stock the cult SUPPLY CACHE onto the city floor (also AFTER RoomItems.clear, so a
	# fresh run re-stocks exactly once — no carry, no accumulation). scenario.json's
	# summoning.cache_items ({item_id: [x,y]}) authors WHAT and WHERE; its only prior placer was
	# CitySummoning's scene-node bootstrap, whose node was removed from City.tscn in M20 B1 — leaving
	# the cache (the counter-rite's authored world source and the cult's gather leg) NEVER stocked in
	# live play. This is the LIVE placement seam: it runs on every world build, scene-independent.
	_stock_supply_cache()
	# M15: Franky's shop — the per-run ammo restock latch back to a full shelf. Coin itself needs
	# no line here: it lives in the player proxy's inventory, and Agents.rebuild() above dropped
	# the ephemeral proxy, so the next ensure_player_proxy re-grants the scenario loadout.
	var shop_node := get_node_or_null("/root/Shop")
	if shop_node != null and shop_node.has_method("reset"):
		shop_node.reset()
	# Emergent-event cooldowns + RNG re-seed (kept in step with the fresh run seed).
	EventManager.reset()
	# The world event log.
	EventBus.clear()
	# CombatExecutor's static attacker ledger — else protect-mode could name a stale threat at
	# run start (the static outlives every executor instance).
	CombatExecutor.reset_last_attackers()
	# EndGame's terminal-death latch, so a new run can reach an ending again.
	if EndGame.has_method("rearm"):
		EndGame.rearm()

## B1 (retro): the cult supply cache — scenario.json summoning.cache_items, hydrated once at script
## load (static init, the AmmoSpawn pattern) so repeated run starts never re-parse the JSON.
static var _cache_items: Dictionary = _load_cache_items()

static func _load_cache_items() -> Dictionary:
	if not FileAccess.file_exists(SCENARIO_PATH):
		return {}
	var parsed: Variant = JSON.parse_string(FileAccess.get_file_as_string(SCENARIO_PATH))
	if not (parsed is Dictionary):
		return {}
	var summoning: Variant = (parsed as Dictionary).get("summoning", {})
	if not (summoning is Dictionary):
		return {}
	var cache: Variant = (summoning as Dictionary).get("cache_items", {})
	return cache if cache is Dictionary else {}

## B1 (retro): place ONE of each authored cache offering on the City ground (data: id -> [x, y] in
## City world space, the same coordinates CitySummoning authored). Called from _reset_run_world after
## RoomItems.clear() — the LIVE run-start placement replacing the dead CitySummoning path. Engine-
## neutral: every id and position is scenario data; a missing/malformed block is a clean no-op.
func _stock_supply_cache() -> void:
	for item_id in _cache_items:
		var pos_arr: Variant = _cache_items[item_id]
		if not (pos_arr is Array) or (pos_arr as Array).size() < 2:
			continue
		RoomItems.place("city", String(item_id),
			Vector2(float((pos_arr as Array)[0]), float((pos_arr as Array)[1])), 1)

## Snapshot the run at a safe-house night. In-memory (fast, and the authoritative restore target);
## also mirrored to the SaveManager slot on disk so a real night is a persisted safe point.
func checkpoint_night() -> void:
	# N2 (A4): once the Ritual Night fuse is lit there is NO safe night. A checkpoint taken during
	# the live climax would freeze Doom at 100 with Meters' ritual_night_fired latch already spent —
	# restoring it could never relight the fuse (RitualNight is reset by _restore, but the Doom-100
	# edge never re-fires), a softlocked descent. Refuse, exactly like rest_until_morning refuses:
	# the descent won't wait, and the LAST pre-climax checkpoint stays the honest restore target.
	# (The rest verb's own refusal covers the pre-sleep case; this single seam also covers Doom
	# topping out DURING the rest fast-forward and a nightfall crossed inside the live climax.)
	var rn_cp := get_node_or_null("/root/RitualNight")
	var climax_live: bool = rn_cp != null and rn_cp.has_method("active") and bool(rn_cp.active())
	if _ritual_night or climax_live:
		return
	# B2 (M20): a night's Cogitation at the safe house is the live Madness REST sink (-10, §4) — the
	# nightly half of the Madness cycle that had no caller (only tests reached relieve_madness_rest).
	# Applied BEFORE the snapshot so the checkpoint captures the post-rest Madness. Guarded on
	# madness > 0 so a fresh-run checkpoint (Madness 0) neither clamps a no-op nor prematurely reveals
	# the meter (§3 progressive disclosure — the meter reveals on a real trigger, not on rest).
	if Meters != null and Meters.get_meter("madness") > 0.0:
		Meters.relieve_madness_rest()
	_checkpoint = _snapshot()
	_checkpoint_day = current_day()
	# Best-effort disk mirror (the nightly safe-house save). Never fatal in headless.
	if SaveManager.has_method("save_game"):
		SaveManager.save_game()
	checkpoint_saved.emit(_checkpoint_day)

## P1 (experiential wave) — REST UNTIL MORNING: the lodging bed's dead-time skip (the run finally
## has a way to spend the boring hours). Fast-forwards the Clock to the NEXT morning phase (08:00,
## the run's canonical day start) through the normal minute pipeline — so NPC schedules, meter
## drivers, and the day roll all tick exactly as if the time had passed; sleeping is push-your-luck,
## not free (Doom keeps creeping while you lie still). Then takes the ONE nightly safe-house
## checkpoint at the morning landing (checkpoint_night — which also applies the existing rest
## Madness relief, the B2 Cogitation). Refuses cleanly (typed reason, no clock movement, no
## checkpoint) during Ritual Night or while the player is in combat.
## Returns {ok, day, minutes} on success; {ok:false, reason} on refusal.
var _resting: bool = false

func rest_until_morning() -> Dictionary:
	if not _run_active:
		return {"ok": false, "reason": "no_run"}
	# Ritual Night: once the fuse is lit (Doom 100 latch) or the climax is live, there is no morning
	# to sleep toward — the descent won't wait for the player to wake.
	var rn := get_node_or_null("/root/RitualNight")
	var climax_live: bool = rn != null and rn.has_method("active") and bool(rn.active())
	if _ritual_night or climax_live:
		return {"ok": false, "reason": "ritual_night"}
	if _player_in_combat():
		return {"ok": false, "reason": "in_combat"}
	# Minutes to the NEXT 08:00: later today when we're before it (post-midnight late-night),
	# else across the midnight roll. Resting AT 08:00 sleeps a full day (never a no-op).
	var mins: int = RUN_START_MINUTE - Clock.minute_of_day
	if mins <= 0:
		mins += Clock.DAY_MINUTES
	_resting = true
	Clock.advance_minutes(mins)
	_resting = false
	# The verb's single checkpoint, taken at the morning landing (so a later death restores to the
	# rested morning, not the pre-sleep evening). checkpoint_night applies the rest Madness relief.
	checkpoint_night()
	return {"ok": true, "day": current_day(), "minutes": mins}

## True while the player's combat proxy is engaged (the CombatMode in_combat mask on the neutral
## "player" proxy id — the same neutral fact the meta writer reads; no NPC-identity branch).
func _player_in_combat() -> bool:
	var reg := get_node_or_null("/root/Agents")
	if reg == null:
		return false
	var a: Object = reg.get_agent("player")
	return a != null and bool(a.in_combat)

func has_checkpoint() -> bool:
	return not _checkpoint.is_empty()

func checkpoint_day() -> int:
	return _checkpoint_day

## M9 Gap 3: where the last checkpoint's safe house was (the scene the death/rampage restore should
## reload). Falls back to the lodging when no checkpoint has been taken (the day-1 fresh-restart also
## wakes in the lodging), so the boot controller always has a sane wake scene.
func checkpoint_scene() -> String:
	return String(_checkpoint.get("scene", LODGING_SCENE))

## The player body position saved with the last checkpoint (where to drop the body on a restore).
func checkpoint_player_pos() -> Vector2:
	var p: Dictionary = _checkpoint.get("player_pos", {})
	return Vector2(float(p.get("x", 0.0)), float(p.get("y", 0.0)))

## End the current run. reason ∈ { "death", "lost_control", "win", "lose" }.
##   death / lost_control -> restore to the LAST NIGHTLY CHECKPOINT (costs the current day). With no
##       checkpoint yet (day-1 pre-checkpoint): a DEATH is a normal run LOSS (meta flushed, emitted
##       as "lose" -> title, N2 A1); a lost_control restarts the same run fresh.
##   win / lose (Ritual Night; comes later) -> full run-end. Meta already persisted; the boot
##       controller returns to the title. State is left for the caller to start_run() again.
## `context` (M27): optional run-end payload — the RitualNight resolver passes {"outcome": <climax
## outcome>} so the meta payoff (codex / Fool unlock / differential currency) can key off which win
## or lose the run reached. Absent (a bare abandon-to-title lose), the outcome falls back to the
## resolver's last result(), else "" (no ending fact / no payout).
func end_run(reason: String, context: Dictionary = {}) -> void:
	_run_active = false
	# Do the DATA restore/reset BEFORE emitting, so run_ended listeners (the boot controller's scene
	# swap + player reposition, M9 Gap 3) see the run in its final restored state (correct day, the
	# checkpoint's scene/pos already latched). The emit stays the LAST step for every reason.
	match reason:
		"death", "lost_control":
			if has_checkpoint():
				_restore(_checkpoint)
				_current_day = _checkpoint_day
				_run_active = true
				# Re-arm the terminal-death ending so the player can be downed again this run
				# (_restart_fresh does this via _reset_run_world; the restore branch must too).
				if EndGame.has_method("rearm"):
					EndGame.rearm()
			elif reason == "death":
				# N2 (A1): a combat death BEFORE the first nightly checkpoint has no safe point to
				# wake back to — it is a normal RUN LOSS, not a silent same-run wipe. Flush the meta
				# payoff exactly like a climax lose (the codex keeps what this run learned; a
				# "player_downed" outcome unlocks nothing and pays nothing), then hand every listener
				# the loss: the boot controller returns to the title and the ending screen's payoff
				# section renders through the ONE run-end seam. The next run starts only via New Run.
				_finalize_run_end(_end_outcome(context))
				reason = "lose"
			else:
				# lost_control day-1 pre-checkpoint: no safe point yet -> the SAME run continues,
				# fresh (the Madness rampage burns the day, never the whole run). PRESERVE the run's
				# chosen pathway (M30 G1) so a Hermit run that rampages on day 1 doesn't silently
				# restart as Hunter (read it BEFORE _restart_fresh scrubs Progression).
				_restart_fresh(Progression.pathway())
		"win", "lose":
			# Full run-end. M27: WRITE the persistent meta payoff BEFORE the title handoff — the codex
			# grows with what this run learned, the FIRST win unlocks the Fool pathway, and the win-grade
			# differential currency pays out. All three key off the climax OUTCOME (avatar_slain /
			# descent_stopped / descent_complete), which arrives in `context` from the resolver. Title
			# handoff stays the boot controller's job; this touches only the meta + save slots.
			_finalize_run_end(_end_outcome(context))
		_:
			push_warning("RunManager.end_run: unknown reason '%s'" % reason)
	run_ended.emit(reason)

## The climax reached zero — the run is decided. Map the resolver's outcome to a run reason. EndGame
## still owns and shows the SCREEN; here we only close the run so meta/title flow is correct.
func _on_summoning_climax(strength: float) -> void:
	if not _run_active:
		return
	# B1 (M20): the LEGACY SummoningPlan auto-resolve no longer owns the run's loss. The M7 Ritual
	# Night (Doom-fill / force-assault) is the climax authority now, and it routes its OWN outcome
	# straight to end_run(). The old cult countdown (CitySummoning demo) firing summoning_climax must
	# NOT self-end the run — it bypassed the built climax and lost every live run ~80s after entering
	# the city. Only honor this signal when a Ritual Night is the ACTIVE/resolving climax path; else
	# no-op so the legacy descent is inert. Engine-neutral (no NPC/id branch — a subsystem-state gate).
	var rn := get_node_or_null("/root/RitualNight")
	var rn_owns_climax: bool = rn != null and (
		(rn.has_method("active") and bool(rn.active())) or (rn.has_method("resolved") and bool(rn.resolved())))
	if not rn_owns_climax:
		return
	# The resolver's Gate 1: a strong descent unmade the city (lose); a stopped descent is a win.
	var reason := "lose" if strength > EndGameResolver.STOP_THRESHOLD else "win"
	end_run(reason)

# --- N3: the run SESSION block (SaveManager SUBSYSTEMS entry) + the Continue resume seam -------
## The persisted RUN SESSION (B-F2): the day, the live flag, the ritual latch, the checkpoint day,
## and the run knowledge ledger. Deliberately WITHOUT the in-memory checkpoint payload — the disk
## save IS the nightly checkpoint mirror, so resume_from_save() rebuilds the checkpoint from the
## whole loaded payload instead of nesting snapshots inside snapshots (the block also rides along
## inertly inside each nightly _snapshot(), which _restore() ignores — RunManager manages its own
## fields explicitly around a within-run restore, exactly as before).
func to_dict() -> Dictionary:
	var ids: Array = _run_knowledge.keys()
	ids.sort()   # deterministic payload (the ledger is a set)
	return {
		"day": current_day(),
		"run_active": _run_active,
		"ritual_night": _ritual_night,
		"checkpoint_day": _checkpoint_day,
		"knowledge": ids,
	}

## Restore the session DATA half (called by SaveManager.apply_subsystem_dump on every disk load,
## AFTER the Clock so the day default can lean on it). The LIVE flag is deliberately NOT flipped
## here — a bare load_game() (harness round-trips) stays side-effect-light; the player-facing
## Continue goes through resume_from_save(), which re-arms the session. Knowledge MERGES (union)
## so a load can only add facts, never erase what the live run has since learned.
func from_dict(d: Dictionary) -> void:
	_current_day = int(d.get("day", Clock.day))
	_ritual_night = bool(d.get("ritual_night", _ritual_night))
	_checkpoint_day = int(d.get("checkpoint_day", _checkpoint_day))
	var kn: Variant = d.get("knowledge", [])
	if kn is Array:
		for fid in (kn as Array):
			_note_knowledge(String(fid))

## N3 (B-F1) — make a cross-session Continue a FIRST-CLASS RESUME. Called by the REAL
## BootController.continue_run() after SaveManager.load_game() has hydrated every world subsystem
## (including this manager's session block via from_dict). This re-arms everything a fresh boot
## loses: the LIVE flag (nightly checkpoints, codex recording, Ritual Night arming, pause and the
## endings all gate on it), the run pace, the payoff latch, and the in-memory checkpoint rebuilt
## from the loaded payload — so a post-resume death restores to this resumed morning exactly like
## a never-quit run. Returns false when there is no loaded payload to resume from.
func resume_from_save() -> bool:
	var data: Dictionary = SaveManager.last_loaded_payload()
	if data.is_empty():
		return false
	_run_active = true
	_current_day = Clock.day
	_payoff_flushed = false   # the resumed run has not ended — its eventual end pays exactly once
	_apply_run_pace()
	# Rebuild the nightly checkpoint from the payload: the same shape _snapshot() builds (the
	# manifest subsystem dump + the wake placement), so end_run("death") restores correctly.
	var snap: Dictionary = {}
	for entry in SaveManager.SUBSYSTEMS:
		var key := String(entry[0])
		if data.has(key):
			snap[key] = data[key]
	snap["day"] = _current_day
	var scene := String(data.get("scene_path", ""))
	snap["scene"] = scene if scene != "" else LODGING_SCENE
	var pp: Variant = data.get("player_pos", [])
	var has_pp: bool = pp is Array and (pp as Array).size() >= 2
	snap["player_pos"] = {
		"x": float((pp as Array)[0]) if has_pp else 0.0,
		"y": float((pp as Array)[1]) if has_pp else 0.0,
	}
	_checkpoint = snap.duplicate(true)
	if _checkpoint_day <= 0:
		_checkpoint_day = _current_day   # legacy saves predate the session block
	# Re-derive the ritual latch from the RESTORED Doom (single source of truth — the _restore
	# lesson): a save can only exist pre-climax (checkpoint_night refuses once the fuse is lit),
	# but a legacy/hand-edited payload must not resume with a stale latch either way.
	_ritual_night = Meters.get_meter("doom") >= 100.0 if Meters != null else _ritual_night
	return true

# --- Snapshot / restore (same contract as SaveManager) ----------------------------------------
## Build an in-memory data snapshot of the run-scoped subsystems. Mirrors SaveManager's key set so
## _restore() is a straight from_dict() fan-out. Duplicated deep so later mutation can't alias it.
func _snapshot() -> Dictionary:
	# M9 Gap 3: record the safe-house SCENE + the player's body position so a death/rampage restore
	# can wake the player back IN the lodging (the boot controller reads these) rather than stranding
	# them in a stale scene (the crypt / a random street). Best-effort: headless snapshots (no live
	# GameController) record the lodging default at spawn, which is exactly where a real night rests.
	var scene := LODGING_SCENE
	var ppos := Vector2.ZERO
	var ml := Engine.get_main_loop()
	if ml != null and ml is SceneTree:
		var gc := (ml as SceneTree).get_first_node_in_group("game_controller")
		if gc != null:
			if "current_scene_path" in gc and String(gc.current_scene_path) != "":
				scene = String(gc.current_scene_path)
			if gc.has_method("player_position"):
				ppos = gc.player_position()
	# B3 (M21): the subsystem payload is built from SaveManager's ONE shared manifest — the same seam
	# the disk save uses — so the in-memory checkpoint and the cross-session save can never again cover
	# different key sets (meters/progression/leads/shop used to be listed here but NOT on disk). Deep-
	# duplicated so a later mutation of a live subsystem can't alias this frozen snapshot.
	var snap: Dictionary = SaveManager.subsystem_dump().duplicate(true)
	# The restore-placement meta (not a subsystem): where a death/rampage restore wakes the player.
	snap["day"] = current_day()
	snap["scene"] = scene
	snap["player_pos"] = {"x": ppos.x, "y": ppos.y}
	return snap

## Reload a snapshot into the live subsystems (pure data — no scene work).
func _restore(snap: Dictionary) -> void:
	# The Ritual-Night latch is derived from Doom, not part of any subsystem snapshot — clear it
	# here so a checkpoint taken pre-Doom-100 doesn't leave it stuck true after a restore (Meters'
	# own _ritual_night_fired comes back through the meter snapshot; this is RunManager's mirror of
	# the same fact and must be re-derived on the restore path too, exactly like _restart_fresh).
	_ritual_night = false
	WorldManager.from_dict(snap.get("world_manager", {}))
	ClueDB.from_dict(snap.get("clues", {}))
	Clock.from_dict(snap.get("clock", {}))
	# P1: the pace is a run CONSTANT, never snapshot state — re-apply it so a stale snapshot (or
	# anything that fiddled the Clock between checkpoint and restore) can't drag the run pace back.
	_apply_run_pace()
	WorldState.from_dict(snap.get("world_state", {}))
	# Meters AFTER WorldState (it re-derives Doom/Notice from the just-restored pressures, then
	# overlays the meter-only Madness/Heat/disclosure fields).
	Meters.from_dict(snap.get("meters", {}))
	SummoningPlan.from_dict(snap.get("summoning_plan", {}))
	Overseer.from_dict(snap.get("overseer", {}))
	OccultToolManager.from_dict(snap.get("occult_tools", {}))
	PrayerService.from_dict(snap.get("prayer", {}))
	DeedRunner.from_dict(snap.get("deeds", {}))
	Inventory.from_dict(snap.get("inventory", {}))
	# Rebuild the roster first so from_dict has fresh Agents to hydrate onto.
	Agents.rebuild()
	Agents.from_dict(snap.get("agents", {}))
	# M7: symmetry with _reset_run_world — a checkpoint restore also scrubs the Ritual Night climax.
	# _restore already rebuilt Agents (wiping any runtime-staged crypt roster), so a live climax's
	# latches (_active/_fuse/dangling agent ids) must be cleared too, else a mid-climax restore would
	# leave RitualNight._active=true pointing at agents that no longer exist. Latent today (a Doom-100
	# climax can't coexist with an earlier-day checkpoint), fixed here for safety before checkpoints
	# are touched again.
	var rn_restore := get_node_or_null("/root/RitualNight")
	if rn_restore != null and rn_restore.has_method("reset"):
		rn_restore.reset()
	EventBus.from_dict(snap.get("event_bus", {}))
	# Sequence rank + granted arts restore with the checkpointed day (M5) — the climb carries within
	# a run; only start_run() (a NEW run) scrubs it back to Seq 9.
	Progression.from_dict(snap.get("progression", {}))
	# Active leads (M6) restore with the checkpointed day — the whispered board carries within a run.
	LeadSystem.from_dict(snap.get("leads", {}))
	# M15: the shop's stock latch restores with the checkpoint (symmetry with _reset_run_world).
	var shop_restore := get_node_or_null("/root/Shop")
	if shop_restore != null and shop_restore.has_method("from_dict"):
		shop_restore.from_dict(snap.get("shop", {}))
	# Re-derive the Ritual-Night latch from the RESTORED Doom (single source of truth): a checkpoint
	# taken at Doom>=100 stays lit; the normal pre-100 checkpoint leaves it cleared. This closes the
	# M2-class leak where the latch outlived a restore that pulled Doom back below 100.
	_ritual_night = Meters.get_meter("doom") >= 100.0 if Meters != null else false

# --- MetaState (persists across restart; separate slot) ---------------------------------------
func meta_runs_played() -> int:
	_load_meta()
	return int(_meta.get("runs_played", 0))

## The persistent codex (the growing "what you know about the occult city" record). Read-only copy;
## no stat inheritance — each entry is data { id, learned }, never power.
func meta_codex() -> Array:
	_load_meta()
	return (_meta.get("codex", []) as Array).duplicate(true)

## M27 — the pathways the meta has unlocked (read by the run-start pathway pick). Read-only copy.
## Hunter is always available WITHOUT being listed here (the slice baseline); this holds the EARNED
## unlocks (e.g. "fool" after the first win). No stat inheritance — a flag, not power.
func meta_unlocked_pathways() -> Array:
	_load_meta()
	return (_meta.get("unlocked_pathways", []) as Array).duplicate()

## M27 — the persistent meta-currency (bookkeeping toward future meta unlocks; NEVER run power, §8).
func meta_currency() -> int:
	_load_meta()
	return int(_meta.get("meta_currency", 0))

## B3 (retro) — what the LAST win/lose run-end actually wrote to the meta: {outcome, currency_delta,
## currency_total, new_unlocks, new_codex}. Recorded by _flush_meta_on_run_end (the single payoff
## seam, so the display can never drift from the write) and rendered on the EndGame screen through
## MetaSurface.payoff_model. {} until a run ends; cleared by a new run. Read-only deep copy.
func meta_last_payoff() -> Dictionary:
	return _last_payoff.duplicate(true)

var _last_payoff: Dictionary = {}

func _bump_meta_runs() -> void:
	_load_meta()
	_meta["runs_played"] = int(_meta.get("runs_played", 0)) + 1
	_save_meta()

func _default_meta() -> Dictionary:
	return {"version": META_VERSION, "runs_played": 0, "unlocked_pathways": [], "codex": [], "meta_currency": 0}

# --- M27: the meta PAYOFF writers (the roguelite's reason to replay) ---------------------------
## The codex writer's EAR (connected in _ready). A downed Beyonder during a LIVE run is knowledge —
## record its combat_form (as `adversary:<form>`) and, if it carries one, its pathway (`pathway:<p>`)
## into the run knowledge ledger. Engine-neutral: keyed purely off the agent's DATA fields, no id
## branch. Passive (only writes a Dictionary), inert outside an active run, never touches combat.
func _on_meta_world_event(ev: Dictionary) -> void:
	if not _run_active:
		return
	if String(ev.get("type", "")) != "agent_downed":
		return
	var d: Dictionary = ev.get("data", {}) if ev.get("data") is Dictionary else {}
	var target := String(d.get("target", ""))
	if target == "" or target == "player":
		return   # the player proxy going down is a run event, not a harvestable/known Beyonder
	var reg := get_node_or_null("/root/Agents")
	var a: Object = reg.get_agent(target) if reg != null else null
	if a == null:
		return
	if String(a.combat_form) != "":
		_note_knowledge("adversary:%s" % String(a.combat_form))
	if String(a.pathway) != "":
		_note_knowledge("pathway:%s" % String(a.pathway))

## Record a codex fact-id into the run knowledge ledger (a set; deduped on flush). No-op on empty.
func _note_knowledge(fact_id: String) -> void:
	if fact_id != "":
		_run_knowledge[fact_id] = true

## Resolve the climax outcome for a win/lose end: the resolver's `context` first, else its last
## result(), else "" (a bare abandon with no climax — codex still gets the pathway fact, no payout).
func _end_outcome(context: Dictionary) -> String:
	if context.has("outcome"):
		return String(context["outcome"])
	var rn := get_node_or_null("/root/RitualNight")
	if rn != null and rn.has_method("result"):
		var r: Dictionary = rn.result()
		return String(r.get("outcome", ""))
	return ""

## N3 — the ONE full-run-end finalizer (every path that truly ENDS a run lands here: climax win/
## lose, the abandon-to-title lose, the pre-checkpoint final death). Two effects: the meta payoff
## flush (latched — see _flush_meta_on_run_end) and the save-slot invalidation (B-F5: an ended run
## must not leave a resumable ghost — the title's Continue greys out).
func _finalize_run_end(outcome: String) -> void:
	_flush_meta_on_run_end(outcome)
	if SaveManager.has_method("invalidate_save"):
		SaveManager.invalidate_save()

## N3 — the payoff IDEMPOTENCE LATCH: end_run can be reached more than once for the SAME run (a
## climax lose then a pause-menu abandon; a double player_downed edge) — the payoff must count
## EXACTLY once per run. Re-armed by a genuinely new run (_restart_fresh) and by a Continue resume
## (resume_from_save) — never by a within-run checkpoint restore (the run hasn't ended).
var _payoff_flushed: bool = false

## The single meta-payoff seam, run on a win/lose end_run. Writes THREE persistent effects, all data-
## keyed off `outcome` (no NPC/id branch): (1) append this run's learned facts to _meta.codex, deduped;
## (2) on a WIN, walk WIN_UNLOCK_CHAIN and grant the first pathway not yet owned (ONE per win — the
## roguelite drip; additive/deduped); (3) pay the outcome's differential meta-currency. Persists to
## the meta slot. NO stat inheritance. LATCHED (N3): a second call for the same run is a no-op —
## an unlatched double flush would double-pay currency AND walk the unlock chain twice per win.
func _flush_meta_on_run_end(outcome: String) -> void:
	if _payoff_flushed:
		return
	_payoff_flushed = true
	_load_meta()
	# (1) the always-learned facts of THIS run: the ending reached + the pathway the player walked.
	if outcome != "":
		_note_knowledge("ending:%s" % outcome)
	var pw := _player_pathway()
	if pw != "":
		_note_knowledge("pathway:%s" % pw)
	# Append every new fact to the codex, deduped by id (a fact known from a prior run is not re-added).
	var codex: Array = _meta.get("codex", []) as Array
	var known: Dictionary = {}
	for e in codex:
		if e is Dictionary:
			known[String((e as Dictionary).get("id", ""))] = true
	var ids: Array = _run_knowledge.keys()
	ids.sort()   # deterministic append order (the ledger is a set)
	var new_entries: Array = []   # B3: what THIS flush added (the EndGame payoff display)
	for fid in ids:
		var fid_s := String(fid)
		if known.has(fid_s):
			continue
		var entry := {"id": fid_s, "learned": _codex_line(fid_s)}
		codex.append(entry)
		new_entries.append(entry.duplicate(true))
		known[fid_s] = true
	_meta["codex"] = codex
	# (2) M_death — a WIN walks the unlock chain: grant the FIRST entry not yet owned (at most ONE
	# per win, the roguelite drip; a loss unlocks nothing; past the chain end nothing is granted).
	var new_unlocks: Array = []   # B3: an unlock granted by THIS flush (not one already owned)
	if _is_win_outcome(outcome):
		var unlocks: Array = _meta.get("unlocked_pathways", []) as Array
		for pw_id in WIN_UNLOCK_CHAIN:
			if not unlocks.has(pw_id):
				unlocks.append(pw_id)
				new_unlocks.append(pw_id)
				break   # ONE unlock per win — the drip
		_meta["unlocked_pathways"] = unlocks
	# (3) the win-grade DIFFERENTIAL currency payout (avatar_slain > descent_stopped; lose = 0).
	var reward: Dictionary = META_REWARD.get(outcome, {}) if META_REWARD.get(outcome) is Dictionary else {}
	var pay := int(reward.get("currency", 0))
	if pay != 0:
		_meta["meta_currency"] = int(_meta.get("meta_currency", 0)) + pay
	# B3: record what this run-end actually paid, AT the write seam (see meta_last_payoff).
	_last_payoff = {
		"outcome": outcome,
		"currency_delta": pay,
		"currency_total": int(_meta.get("meta_currency", 0)),
		"new_unlocks": new_unlocks,
		"new_codex": new_entries,
	}
	_save_meta()

func _is_win_outcome(outcome: String) -> bool:
	return WIN_OUTCOMES.has(outcome)

## M27 N1 consistency guard (queryable for the regression test): every WIN outcome must carry a
## POSITIVE META_REWARD currency — a win that unlocks Fool but pays 0 would be a silent table drift.
## Pure data check over the two consts; no side effects. Returns false the moment the tables diverge.
func meta_reward_tables_ok() -> bool:
	for w in WIN_OUTCOMES:
		var r = META_REWARD.get(w)
		if not (r is Dictionary) or int((r as Dictionary).get("currency", 0)) <= 0:
			return false
	return true

## The pathway the player walked this run (for the codex `pathway:<p>` fact). Reads Progression.
func _player_pathway() -> String:
	var prog := get_node_or_null("/root/Progression")
	if prog != null and prog.has_method("pathway"):
		return String(prog.pathway())
	return ""

## The short "learned line" for a codex fact-id. Content lives in data/scenario.json's `codex` block
## (engine neutrality); the engine only splits the fact-id on its `:` category for the template path.
## A code fallback covers a missing data block so the codex always reads.
func _codex_line(fact_id: String) -> String:
	var lore := _codex_lore()
	if lore.has(fact_id):
		return String(lore[fact_id])
	var parts := fact_id.split(":")
	var cat := String(parts[0]) if parts.size() > 0 else ""
	var subj := String(parts[1]) if parts.size() > 1 else ""
	var templ: Dictionary = lore.get("_templates", {}) if lore.get("_templates") is Dictionary else {}
	var t := ""
	if templ.has(cat):
		t = String(templ[cat])
	else:
		match cat:   # engine-side fallback copy so the codex works with no data block
			"adversary": t = "You faced and put down a Beyonder in the %s shape; its ways are known to you now."
			"pathway": t = "You have glimpsed the %s pathway and something of how its Beyonders climb."
			"ending": t = "You witnessed how a run can end: %s."
			_: t = "You learned something of %s."
	return (t % subj.capitalize()) if t.find("%s") >= 0 else t

## Lazy-load + cache the codex copy table from data/scenario.json's `codex` block. Tolerant of a
## missing file/block (returns {}), leaning on _codex_line's code fallback.
func _codex_lore() -> Dictionary:
	if _codex_lore_loaded:
		return _codex_lore_cache
	_codex_lore_loaded = true
	if FileAccess.file_exists(SCENARIO_PATH):
		var parsed: Variant = JSON.parse_string(FileAccess.get_file_as_string(SCENARIO_PATH))
		if parsed is Dictionary:
			var block: Variant = (parsed as Dictionary).get("codex", {})
			if block is Dictionary:
				_codex_lore_cache = block
	return _codex_lore_cache

func _load_meta() -> void:
	if _meta_loaded:
		return
	_meta_loaded = true
	if not FileAccess.file_exists(meta_path):
		_meta = _default_meta()
		return
	var parsed: Variant = JSON.parse_string(FileAccess.get_file_as_string(meta_path))
	if parsed is Dictionary:
		_meta = parsed
	else:
		_meta = _default_meta()

func _save_meta() -> void:
	# N1: under an active test sandbox, a meta write outside user://test_sandbox/ is refused.
	if not _TSandbox.guard_write(meta_path):
		return
	var f := FileAccess.open(meta_path, FileAccess.WRITE)
	if f == null:
		push_warning("RunManager: cannot write meta to %s" % meta_path)
		return
	f.store_string(JSON.stringify(_meta, "\t"))
	f.close()

## Test / new-profile helper: wipe the persistent meta back to a fresh profile.
func reset_meta() -> void:
	_meta = _default_meta()
	_meta_loaded = true
	_save_meta()

## M27 — force the persistent meta to be RE-READ from its disk slot (drops the in-memory cache). The
## boot/next-run seam that proves the meta round-trips: write on end_run -> reload the slot -> present.
func reload_meta() -> void:
	_meta_loaded = false
	_meta = {}
	_load_meta()
