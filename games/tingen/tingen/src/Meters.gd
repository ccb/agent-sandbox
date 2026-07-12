extends Node
## The four-meter push-your-luck system (autoload singleton `Meters`) — direction v2 §4.
##
## Tingen's central tension is FOUR meters, each 0..100, that the player pushes their luck against:
##   * Doom   (world clock)     — how close the cult is to the descent. Rises with time, cult
##                                progress you don't stop, monsters left alive. At 100 -> Ritual Night.
##   * Madness (your control)   — how close YOU are to losing yourself. A CYCLE, not a ratchet:
##                                rises on advancing Sequence / ingesting a Characteristic (+35),
##                                heavy assume_form use (+25); FALLS via acting deeds (-5) and a
##                                night's Cogitation rest (-10). Ladder: whispers at 50, the form
##                                STIRS at 75, LOSS OF CONTROL at 100 (the ~60s creature rampage).
##   * Notice ("Attention of the Beyond") — how much the unknown watches you. Rises on flashy/high-
##                                Sequence power use and digesting. At high Notice -> Beyond-hunters spawn.
##   * Heat   (officialdom)      — how exposed you are to the law/Nighthawks. Rises when you use
##                                powers in PUBLIC VIEW (vision-gated witness) or leave bodies seen.
##                                At high Heat -> the Nighthawks hunt you.
##
## This node is the meter AUTHORITY (the single source of truth for the four values, their ladders,
## the rampage window, and progressive-disclosure "revealed" state). MeterDrivers wires EventBus
## events INTO the add_*/adjust APIs here; the HUD reads OUT of them. Deterministic — no RNG, no
## per-frame LLM, no wall time. The meters READ combat events (via the drivers) but never feed back
## into combat resolution (the §f determinism guard pins this).
##
## Migration note (§4 "small, additive change"): the legacy WorldState pressures stay intact so
## saves don't break — at reset() Doom is DERIVED from corruption (folding cult_readiness into its
## fill) and Notice from attention, a ONE-WAY seed via _sync_from_world. The meters are the source of
## truth thereafter and NEVER write back onto those pressures (a write-back would double-drive the
## pinned combat/decision vectors — see adjust_legacy + _sync_from_world). The four live values carry
## across a checkpoint through THIS node's own to_dict()/from_dict (the M21 save manifest), not by
## mirroring onto WorldState. panic is DERIVED from Doom (read-only), and fatigue is left inert.
## RunManager.reset already scrubs WorldState; reset() here re-derives Doom/Notice from those
## run-start pressures + zeroes Madness/Heat.

signal meter_changed(meter: String, value: float)
## A telegraphed Madness ladder crossing: level ∈ {50, 75, 100}. Fired ONCE per upward crossing
## (re-arms after Madness falls back below the rung). 100 also begins the loss-of-control rampage.
signal madness_threshold(level: int)
## A Notice/Heat threat threshold crossed upward (level ∈ {70}) — the hook the later spawn logic
## listens on ("a Beyond-hunter is dispatched" / "the Nighthawks hunt you"). Spawn is a stub for now.
signal threat_threshold(meter: String, level: int)
## Ritual Night: Doom reached 100. The climax itself is M7; for now this flags/hooks it.
signal ritual_night

## The four canonical meters. Doom/Notice alias the legacy WorldState pressures; Madness/Heat are new.
const METERS: Array[String] = ["doom", "madness", "notice", "heat"]

## M25 (backlog "M18") — the ONE documented table that routes a legacy §8.3 WorldState pressure onto
## its live v2 meter. The three orphaned PLAYER systems (PrayerService, the occult tools, EventManager)
## used to write these dead pressures directly; they now route their effects HERE via adjust_legacy(),
## so praying / using a tool / an ambient beat all move the FOUR live meters the HUD actually shows.
## Engine-neutral: a data map, not a per-caller branch — a reader tuning the mapping finds it in one
## place. Heat has no legacy source (none of the §8.3 pressures modelled officialdom/the law); it stays
## driven only by public power use + bodies-left-seen (MeterDrivers), never by these three systems.
##   corruption/cult_readiness -> Doom   (world ruin / cult progress hasten the descent clock; §4 folds
##                                         cult_readiness into Doom's fill, so both land on Doom)
##   attention                 -> Notice  (the "attention of the Beyond" — the canon §4 alias)
##   panic/fatigue             -> Madness (the city's/your dread + occult/mental strain rattle YOUR
##                                         control; panic is derived-from-Doom now and fatigue was inert,
##                                         so Madness is the live meter that carries their felt weight)
const LEGACY_METER_MAP := {
	"corruption": "doom",
	"cult_readiness": "doom",
	"attention": "notice",
	"panic": "madness",
	"fatigue": "madness",
}

## Run-start values (§ direction v2 §3: HUD shows Doom only at 0:00, the rest reveal on trigger).
## Doom seeds from the run-start Doom fill (corruption 5 + cult_readiness 0 folded in); the others
## start clean. TUNING — placeholders.
const RUN_START := {"doom": 5.0, "madness": 0.0, "notice": 0.0, "heat": 0.0}

## The Madness ladder rungs (telegraphed). TUNING.
const MADNESS_WHISPERS: int = 50
const MADNESS_STIRRING: int = 75
const MADNESS_LOSS_OF_CONTROL: int = 100
## Notice/Heat "a hunter is dispatched" rung. TUNING.
const THREAT_RUNG: int = 70

## Madness sources/sinks (§4). TUNING — placeholders, comment each at the call site.
##
## M26 BALANCE RETUNE #5 — the intended Madness curve (the B2 cycle is now live/M20). Two Sequence
## advances spike +35 each = +70 gross; the tension is that push-your-luck ADVANCING should build real
## Madness pressure toward the 50 (whispers) / 75 (form stirs) rungs, but a careful, well-rested player
## survives a ~7-day run. The OLD drain was too strong: nightly rest -10 PLUS 3 acting deeds at -5 =
## -25/day, so a +35 spike was ~gone in a day and a half — Madness never accumulated, the whole cycle
## was trivially suppressible. RETUNE: cut the per-deed relief 5 -> 3 (keep the 3/day cap and the -10
## nightly rest). New max drain = 10 + 3*3 = 19/day. Worked curve for two advances with realistic relief
## between them (from Madness 0): +35 (advance) -10 (one night's rest) -3 -3 (two deeds) = +19, then +35
## (advance) = 54 -> CROSSES 50 (whispers). Two advances pushed close together with less relief climb
## toward 75. A player who spaces advances and fully rests can still bleed a lone spike back down (a spike
## alone: 35 - 19/day -> ~0 in two days), so the pressure is REAL but SURVIVABLE, not a ratchet.
const MADNESS_DIGEST: float = 35.0
const MADNESS_ASSUME_FORM: float = 25.0
const MADNESS_WITNESS_RITE: float = 5.0
## RETUNE #5: 5.0 -> 3.0 — an acting deed is a small nudge of relief, not a spike-eraser (see the curve
## above). The 3/day cap below is unchanged, so max deed relief is now 3*3 = 9/day (was 15/day).
const MADNESS_DEED_RELIEF: float = 3.0
const MADNESS_REST_RELIEF: float = 10.0
## B2 (M20): daily cap on the acting-deed Madness relief (§4 "3/day"). TUNING.
const MADNESS_DEED_CAP_PER_DAY: int = 3

## The loss-of-control rampage window (game-time seconds). TUNING — §13 decision #5 says ~60s.
## Overridable (a test shortens it); the driver reads this seam.
var rampage_duration_s: float = 60.0
## The creature form the player's proxy assumes when it loses control. The Seq-4 monster form on
## every ladder (§6 assume_form reframe). Reuses combat_forms.json's built monster kit. TUNING —
## placeholder form until per-pathway Seq-4 forms exist.
const RAMPAGE_FORM: String = "bieber_monster"

var _values: Dictionary = {"doom": 5.0, "madness": 0.0, "notice": 0.0, "heat": 0.0}
## Progressive disclosure (§3): Doom is always revealed; the others reveal on their first trigger.
var _revealed: Dictionary = {"doom": true, "madness": false, "notice": false, "heat": false}
## Ladder edge-latches: highest rung currently armed-below, so each crossing fires once.
var _madness_armed: int = 0          # the next Madness rung not yet fired (0 -> 50 -> 75 -> 100)
var _threat_armed: Dictionary = {"notice": false, "heat": false}
var _ritual_night_fired: bool = false
## B2 (M20): per-day acting-deed relief accounting (the 3/day cap). Tracked by Clock day so it
## rolls over automatically; scrubbed to run-start in reset().
var _deed_relief_day: int = -1
var _deed_relief_count: int = 0

## Rampage state — the ~60s creature window (§13 decision #5).
var _in_rampage: bool = false
var _rampage_elapsed_s: float = 0.0
var _rampage_prev_form: String = ""

func _ready() -> void:
	# Derive the meters from whatever WorldState currently holds (a fresh boot = run-start).
	_sync_from_world()

# --- read / write -----------------------------------------------------------------------------
func get_meter(meter: String) -> float:
	return float(_values.get(meter, 0.0))

func run_start(meter: String) -> float:
	return float(RUN_START.get(meter, 0.0))

## Directly set a meter (save/load, dev console, tests). Clamps 0..100, reveals on first
## non-run-start touch, and runs the ladder/threshold edges. Does NOT write back onto any WorldState
## pressure — the meters are one-way authorities (see the migration note above / adjust_legacy).
func set_meter(meter: String, value: float) -> void:
	if not METERS.has(meter):
		push_warning("Meters.set_meter: unknown meter '%s'" % meter)
		return
	var before := float(_values.get(meter, 0.0))
	var after := clampf(value, 0.0, 100.0)
	_values[meter] = after
	_after_change(meter, before, after)

## Nudge a meter by delta (the driver path). Reveals the meter (a trigger = the first thing that
## moves it off run-start), then edges the ladders.
func adjust(meter: String, delta: float, _reason: String = "") -> void:
	if not METERS.has(meter):
		push_warning("Meters.adjust: unknown meter '%s'" % meter)
		return
	if delta != 0.0:
		_revealed[meter] = true
	set_meter(meter, get_meter(meter) + delta)

## M25 (backlog "M18"): route a legacy §8.3 pressure delta onto its mapped live meter (LEGACY_METER_MAP).
## The single seam the three rewired player systems (PrayerService / the occult tools / EventManager)
## call so their effects land on the FOUR live meters instead of the dead WorldState pressures. Sign is
## preserved (a relief stays a relief); the clamp, progressive disclosure, and the Madness/threat ladder
## edges all run through adjust(). An unmapped legacy name is a safe no-op (warns) — engine-neutral, no
## per-caller branch. Never writes back onto the WorldState pressure (the city sim owns those via
## DeedRunner; a write-back would double-drive the pinned combat/decision vectors).
func adjust_legacy(legacy_name: String, delta: float, reason: String = "") -> void:
	var meter := String(LEGACY_METER_MAP.get(legacy_name, ""))
	if meter == "":
		push_warning("Meters.adjust_legacy: unmapped legacy pressure '%s'" % legacy_name)
		return
	adjust(meter, delta, reason)

func is_revealed(meter: String) -> bool:
	return bool(_revealed.get(meter, false))

# --- Madness cycle (§4) -----------------------------------------------------------------------
## Raise Madness (advancing Sequence / digesting +35, assume_form +25, witnessing a rite +5).
func add_madness(amount: float, reason: String = "") -> void:
	if amount == 0.0:
		return
	adjust("madness", absf(amount), reason)

## Lower Madness by an explicit amount (generic sink; the deed/rest helpers wrap it).
func relieve_madness(amount: float) -> void:
	adjust("madness", -absf(amount), "relieve")

## An acting deed — performing your Sequence's role in the world (−5). Uncapped primitive; the
## capped live verb is try_relieve_madness_deed().
func relieve_madness_deed() -> void:
	relieve_madness(MADNESS_DEED_RELIEF)

## B2 (M20): the LIVE daily acting-deed relief, capped at MADNESS_DEED_CAP_PER_DAY per game-day
## (§4 "acting deeds -5, 3/day"). The cap tracks by Clock day so it rolls over automatically each
## day and never needs an explicit reset. Returns {ok, count, reason}: ok=false reason "daily_cap"
## once the day's three are spent. This is the caller the Interactable acting-deed flag drives.
func try_relieve_madness_deed() -> Dictionary:
	var d := _clock_day()
	if d != _deed_relief_day:
		_deed_relief_day = d
		_deed_relief_count = 0
	if _deed_relief_count >= MADNESS_DEED_CAP_PER_DAY:
		return {"ok": false, "reason": "daily_cap", "count": _deed_relief_count}
	_deed_relief_count += 1
	relieve_madness_deed()
	return {"ok": true, "reason": "", "count": _deed_relief_count}

## Acting-deed relief uses remaining today (for a HUD/thought line).
func deed_relief_remaining_today() -> int:
	if _clock_day() != _deed_relief_day:
		return MADNESS_DEED_CAP_PER_DAY
	return maxi(0, MADNESS_DEED_CAP_PER_DAY - _deed_relief_count)

func _clock_day() -> int:
	var clk := _al("Clock")
	return int(clk.day) if clk != null else 0

## A night's Cogitation (sleep at a lodging) — −10.
func relieve_madness_rest() -> void:
	relieve_madness(MADNESS_REST_RELIEF)

# --- panic (derived, read-only) ---------------------------------------------------------------
## Panic is no longer a driven meter (§4): it is a pure read-only function of Doom (the city's
## fear tracks how close the descent is). Same shape as the old panic weight; deterministic.
##
## Canonical vs legacy (save-compat, review M4 #4): THIS `Meters.panic()` is the §4 canonical
## panic — the derived-flavor value the meter system exposes. The legacy `WorldState.panic` field
## is DELIBERATELY left live (still fed by DeedRunner consequence rows, still read by
## WorldState.stability(), the LLM perception input, and the GM/PlayLog snapshots) so existing
## saves and the pinned combat/decision vectors don't shift — repointing those at this derived
## value would move inputs the determinism guards pin. New code should read Meters.panic().
func panic() -> float:
	return clampf(get_meter("doom") * 0.6, 0.0, 100.0)

# --- rampage (§13 decision #5) ----------------------------------------------------------------
func in_rampage() -> bool:
	return _in_rampage

## Seconds remaining in the loss-of-control window (0 when not rampaging) — the HUD countdown reads this.
func rampage_remaining_s() -> float:
	return maxf(0.0, rampage_duration_s - _rampage_elapsed_s) if _in_rampage else 0.0

## Begin the loss-of-control rampage: the player's proxy assumes the Seq-4 creature form (reusing
## the built transform on the PLAYER proxy) and a rampage window opens. Their input still drives
## PlayerCombat, now with the monster kit; at expiry tick_rampage() ends the run 'lost_control'.
func _begin_rampage() -> void:
	if _in_rampage:
		return
	_in_rampage = true
	_rampage_elapsed_s = 0.0
	var reg := _al("Agents")
	if reg != null:
		var proxy: Agent = reg.get_agent("player")
		if proxy != null:
			_rampage_prev_form = proxy.combat_form
			# Drive the transform through the same seam the executor uses: swap the form and reload
			# the kit. A live PlayerCombat executor re-reads the kit each frame, so the player now
			# fights with the monster kit. If an executor is bound, mark it in combat so it acts.
			proxy.combat_form = RAMPAGE_FORM
			proxy.in_combat = true
			# NOTE (review M4 #5, TUNING): _load_reflexes() also loads the monster form's authored
			# reflex rows onto the player executor, so the creature can auto-cast (e.g. blood_frenzy
			# on low hp) alongside the player's own input. Minor tension with "the player CONTROLS
			# the creature-form"; left as-is for M4 (the player still drives the primary attack).
			# Future tuning could gate reflex firing while in_rampage() to make control total.
			var ex := CombatExecutor.for_agent("player")
			if ex != null:
				ex._load_reflexes()
				# M6 visual pass parity: swap the bound body to the creature sprite too, so a LIVE
				# rampage actually shows the beast (the executor's own assume_form block does this;
				# this direct seam must match it, else the monster is invisible). No sprite = no-op.
				ex._apply_form_sprite(RAMPAGE_FORM)
			var eb := _al("EventBus")
			if eb != null:
				eb.emit_event("transformed", {"agent": "player", "form": RAMPAGE_FORM})

## Advance the rampage clock (game-time seconds — the live tree calls this from _process while a
## rampage is live; tests call it directly). At expiry: end the run 'lost_control' and clear.
func tick_rampage(dt: float) -> void:
	if not _in_rampage:
		return
	_rampage_elapsed_s += dt
	if _rampage_elapsed_s >= rampage_duration_s:
		_end_rampage()

func _end_rampage() -> void:
	_in_rampage = false
	var rm := _al("RunManager")
	if rm != null:
		# End the run FIRST (restore to the checkpoint / day-1; the boot controller wakes the player
		# in the safe house on run_ended — M9 Gap 3), THEN raise the player-facing "you lost control"
		# screen (M9 Gap 4) — symmetric with combat death's player_downed() screen, so a rampage no
		# longer silently resets with no feedback into a stale scene.
		rm.end_run("lost_control")
	var eg := _al("EndGame")
	if eg != null and eg.has_method("lost_control"):
		eg.lost_control()

func _process(delta: float) -> void:
	# The live rampage clock (game-time). Headless tests drive tick_rampage directly instead.
	if _in_rampage:
		tick_rampage(delta)

# --- internals --------------------------------------------------------------------------------
## After any change: fire meter_changed, run the Madness ladder + Notice/Heat threat edges, and
## latch Ritual Night when Doom tops out.
func _after_change(meter: String, before: float, after: float) -> void:
	if before == after:
		# Still emit on an explicit set (heals/loads need the HUD to refresh) but skip the edges.
		meter_changed.emit(meter, after)
		return
	meter_changed.emit(meter, after)
	match meter:
		"madness":
			_edge_madness(before, after)
		"notice", "heat":
			_edge_threat(meter, before, after)
		"doom":
			if after >= 100.0 and not _ritual_night_fired:
				_ritual_night_fired = true
				ritual_night.emit()

## The telegraphed Madness ladder: fire each rung once on an upward crossing; re-arm when Madness
## falls back below it. 100 also opens the loss-of-control rampage.
func _edge_madness(before: float, after: float) -> void:
	# Re-arm rungs we've fallen back below.
	if after < float(MADNESS_WHISPERS):
		_madness_armed = 0
	elif after < float(MADNESS_STIRRING):
		_madness_armed = mini(_madness_armed, 1)
	elif after < float(MADNESS_LOSS_OF_CONTROL):
		_madness_armed = mini(_madness_armed, 2)
	# Fire rising crossings, in order, each exactly once.
	if after >= float(MADNESS_WHISPERS) and _madness_armed < 1:
		_madness_armed = 1
		madness_threshold.emit(MADNESS_WHISPERS)
	if after >= float(MADNESS_STIRRING) and _madness_armed < 2:
		_madness_armed = 2
		madness_threshold.emit(MADNESS_STIRRING)
	if after >= float(MADNESS_LOSS_OF_CONTROL) and _madness_armed < 3:
		_madness_armed = 3
		madness_threshold.emit(MADNESS_LOSS_OF_CONTROL)
		_begin_rampage()

## Notice/Heat threat rung (a single rung tonight): fire once on the upward crossing, re-arm below.
func _edge_threat(meter: String, before: float, after: float) -> void:
	if after < float(THREAT_RUNG):
		_threat_armed[meter] = false
	elif not bool(_threat_armed.get(meter, false)):
		_threat_armed[meter] = true
		threat_threshold.emit(meter, THREAT_RUNG)

## Seed Doom/Notice from WorldState's run-start pressures (§4 migration: corruption->Doom folding
## cult_readiness into its fill, attention->Notice). This is a READ-ONLY derivation used only at
## reset — the meters are the source of truth thereafter and NEVER write back onto the WorldState
## pressures (the legacy DeedRunner consequence rows still drive attention/panic on their own; a
## write-back here would double-drive them and break combat_sim's pinned pressure deltas). Madness
## and Heat have no legacy pressure — they live only here, snapshotted through to_dict().
func _sync_from_world() -> void:
	var ws := _al("WorldState")
	if ws == null:
		return
	# Doom's fill folds cult_readiness into corruption (§4: cult_readiness folds into Doom's fill).
	var doom := clampf(float(ws.get("corruption")) + float(ws.get("cult_readiness")) * 0.5, 0.0, 100.0)
	_values["doom"] = doom
	_values["notice"] = clampf(float(ws.get("attention")), 0.0, 100.0)

## Scrub the meters to run-start — the seam RunManager.reset()/start_run() calls AFTER WorldState.reset
## so a fresh run's meters are byte-identical to the very first. Re-derives Doom/Notice from the
## freshly-reset pressures, zeroes Madness/Heat, resets disclosure + ladder latches + the rampage.
func reset() -> void:
	_sync_from_world()
	_values["madness"] = RUN_START["madness"]
	_values["heat"] = RUN_START["heat"]
	# Doom starts revealed (HUD shows it at 0:00); the rest hide until first trigger.
	_revealed = {"doom": true, "madness": false, "notice": false, "heat": false}
	_madness_armed = 0
	_threat_armed = {"notice": false, "heat": false}
	_ritual_night_fired = false
	_in_rampage = false
	_rampage_elapsed_s = 0.0
	_rampage_prev_form = ""
	# B2 (M20): a fresh run's acting-deed cap starts clean (no carry of a prior run's spent deeds).
	_deed_relief_day = -1
	_deed_relief_count = 0
	for meter in METERS:
		meter_changed.emit(meter, get_meter(meter))

# --- save / load (the four meters + disclosure/ladder latches live only here) ------------------
func to_dict() -> Dictionary:
	return {
		"doom": get_meter("doom"),
		"madness": get_meter("madness"),
		"notice": get_meter("notice"),
		"heat": get_meter("heat"),
		"revealed": _revealed.duplicate(),
		"madness_armed": _madness_armed,
		"threat_armed": _threat_armed.duplicate(),
		"ritual_night_fired": _ritual_night_fired,
	}

func from_dict(d: Dictionary) -> void:
	# A restore with a meter snapshot loads all four directly; a legacy save without one falls back
	# to the WorldState-derived Doom/Notice seed (older saves predate the meters).
	if not d.has("doom") and not d.has("notice"):
		_sync_from_world()
	for meter in METERS:
		if d.has(meter):
			_values[meter] = clampf(float(d[meter]), 0.0, 100.0)
	if d.get("revealed") is Dictionary:
		for k in (d["revealed"] as Dictionary):
			_revealed[k] = bool((d["revealed"] as Dictionary)[k])
	_madness_armed = int(d.get("madness_armed", _madness_armed))
	if d.get("threat_armed") is Dictionary:
		_threat_armed = (d["threat_armed"] as Dictionary).duplicate()
	_ritual_night_fired = bool(d.get("ritual_night_fired", _ritual_night_fired))
	for meter in METERS:
		meter_changed.emit(meter, get_meter(meter))

## Autoload lookup via /root (class_name-safe under the headless -s harness).
func _al(autoload_name: String) -> Node:
	var ml := Engine.get_main_loop()
	if ml == null or not (ml is SceneTree):
		return null
	return (ml as SceneTree).root.get_node_or_null(autoload_name)
