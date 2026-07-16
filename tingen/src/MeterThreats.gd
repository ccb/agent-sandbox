extends Node
## The meter TEETH — Notice/Heat spawns (autoload singleton `MeterThreats`) — direction v2 §4, M11.
##
## M4 gave Notice/Heat a threat_threshold signal that fired at the high rung but spawned NOTHING, so a
## player could ignore the meters. This node wires that signal to REAL opposition:
##   * Notice crossing its high threshold -> a BEYOND-TOUCHED HUNTER (combat_form 'beyond_hunter', a
##     monster form: the Attention of the Beyond made flesh, canon a corrupted/unknown-touched thing)
##     is dispatched to pursue + fight the player.
##   * Heat crossing its high threshold -> a NIGHTHAWK (combat_form 'nighthawk_pursuer', an official
##     Evernight Beyonder — a HUMAN, not a monster) is dispatched to hunt the player. Being hunted by
##     the player's nominal allies' faction is the cost of public power; kept engine-neutral (no
##     morality branch) — it's just an agent in combat with the player.
##
## Engine neutrality (the hard constraint): the spawn keys off the meter + the form/pathway DATA
## table below, NEVER an NPC identity. A spawned threat is a plain runtime Agent registered through
## the M9 Agents.register_agent seam, wearing its form, flagged in_combat, with a published
## combat_intent engaging "player" — so the BUILT tactical/intent/executor layer pursues + attacks
## the investigator with no new combat code. Reuses the exact seam RitualNight stages its crypt
## roster with.
##
## Lifecycle (each meter independently):
##   * CAP: at most one active threat per meter (MAX_ACTIVE). A second high pulse never stacks.
##   * KILL RELIEF (B5): downing the dispatched hunter IS bringing the meter down — the agent_downed
##     ear relieves the meter by the row's DATA kill_relief (sized to always land below the rung),
##     so fighting the hunt off is a real, winnable counterplay (the live playtest proved the old
##     kill-changes-nothing loop unwinnable). A respawn only happens if the meter is driven high AGAIN.
##   * CLIMAX SHIELD (B5): no spawn/respawn while RitualNight.active() — the crypt climax is not
##     stacked with hunters; the pressure resumes on the first threat tick after it resolves.
##   * RESPAWN: a threat killed while the meter stays high is replaced on the next threat tick — the
##     pressure persists until the player brings the meter DOWN.
##   * DECAY: the driven meter bleeds off over in-game time via MeterDrivers' canonical passive decay
##     (MeterDrivers.apply_passive_meter_decay, driven once per hourly threat tick here BEFORE reconcile
##     so the two share one deterministic pump). Once it falls below the threat rung, a downed threat is
##     NOT replaced — killing it (or waiting out the decay) resolves the threat. Killing the hunter is
##     thus a threat resolved; Notice/Heat decays over time.
##   * RESET: RunManager._reset_run_world calls reset(); Agents.rebuild() drops the runtime agents.
##     Live-threat bookkeeping is scrubbed so a fresh run never inherits a phantom hunter (the
##     sprint-long leak lesson).
##
## Determinism: spawn placement for a fixed run-seed is identical — a run-seed scatter offset (never
## RNG-in-combat; the fight itself is untouched). Placement/decay ride game-time (Clock), never wall
## time. This node writes NO combat state beyond staging an agent — the combat_sim / vector fixtures
## (which never cross a threat threshold) stay byte-identical.

## The DATA table the spawn keys off — meter -> its threat's form + id prefix + engage style. Adding
## a fourth meter's teeth is a row here, no code branch. Forms live in data/combat_forms.json.
## `loadout` (combat plan §M18): the DATA carried-items block a spawned threat is armed with, keyed off
## THIS meter row (never an NPC identity). The Nighthawk's form opens with revolver_shot (an ammo-costed
## art) — with the generic AgentCostProvider now bound on the NPC seam, an unarmed gunman would run dry
## instantly, so the disciplined hunter carries a revolver + a deep magazine (it stays the lethal ranged
## threat it was, and its body is LOOTABLE when downed). The Beyond-touched hunter is a MONSTER (free
## cleaver kit) and needs nothing — omit the key. Monster forms stay authored around free stamina.
## `kill_relief` (B5 retro, live-playtest BUG B): the ACTIVE meter sink — downing THIS meter's
## dispatched hunter relieves the meter by this much ("the hunt is thrown off"). Sized 40 so a kill
## ALWAYS clears below the 70 rung: the meter clamps at 100 and 100 - 40 = 60 < THREAT_RUNG, and the
## relief is applied LAST on the agent_downed event (MeterDrivers registers before MeterThreats in
## project.godot [autoload], so any witnessed-kill Heat lands, clamped, before the relief). The ~35-60
## the meter keeps is real residual pressure the 6/hr passive decay then bleeds. TUNING placeholder.
const THREATS: Dictionary = {
	"notice": {"form": "beyond_hunter", "prefix": "beyond_hunter", "style": "aggressive",
		"kill_relief": 40.0},
	"heat":   {"form": "nighthawk_pursuer", "prefix": "nighthawk_pursuer", "style": "cautious",
		"loadout": {"revolver": 1, "revolver_round": 24}, "kill_relief": 40.0},
}

## At most one active threat per meter. TUNING placeholder.
const MAX_ACTIVE: int = 1
## The Clock ticks per game-minute; the slow decay/respawn batches to whole in-game hours.
const MINUTES_PER_HOUR: int = 60
## The deterministic run-seed scatter radius (px) when spawn_pos is unset — the threat appears a
## seeded offset from the player, reproducible per run (never RNG-in-combat). TUNING placeholder.
const SEED_SCATTER_R: float = 96.0
const PLAYER_ID: String = "player"

## Where a threat is spawned. Defaults to the player's current room/position each spawn (live play);
## a test overrides these to a fixed arena. spawn_pos == Vector2.ZERO => use the seeded scatter.
var spawn_room: String = ""
var spawn_pos: Vector2 = Vector2.ZERO

## Live-threat bookkeeping: meter -> the agent id currently staged for it ("" = none). Run-scoped;
## reset() scrubs it. Never persisted — a save that reloads mid-hunt rebuilds the roster fresh and
## the next threat tick re-dispatches if the meter is still high.
var _active: Dictionary = {"notice": "", "heat": ""}
## Game-minutes counted toward the next whole-hour decay/respawn tick. Sub-hour scratch only.
var _minute_accum: int = 0

func _ready() -> void:
	var m := _al("Meters")
	if m != null and not m.threat_threshold.is_connected(_on_threat_threshold):
		m.threat_threshold.connect(_on_threat_threshold)
	# The decay/respawn pump rides the Clock's per-minute tick, batched to whole hours (cheap, and
	# identical however the clock was advanced — deterministic).
	var clock := _al("Clock")
	if clock != null and not clock.minute_ticked.is_connected(_on_minute_ticked):
		clock.minute_ticked.connect(_on_minute_ticked)
	# A fresh run restarts the sub-hour accumulator on an hour boundary.
	var rm := _al("RunManager")
	if rm != null and not rm.run_started.is_connected(_on_run_started):
		rm.run_started.connect(_on_run_started)
	# B5 (BUG B): the kill-relief ear — downing a dispatched hunter is the ACTIVE meter sink, keyed
	# on the agent_downed world fact (the same event the executor's real damage path emits).
	var eb := _al("EventBus")
	if eb != null and not eb.event_logged.is_connected(_on_event):
		eb.event_logged.connect(_on_event)

# --- the threat threshold ear -----------------------------------------------------------------
## Meters fires this once when Notice/Heat crosses the high rung upward. Dispatch the meter's threat.
func _on_threat_threshold(meter: String, _level: int) -> void:
	if not THREATS.has(meter):
		return
	_ensure_threat(meter)

## B5 (BUG B): the kill-relief ear. When the agent DOWNED is a meter's tracked dispatched threat,
## the hunt is thrown off: the bookkeeping clears at once and the meter is relieved by the row's
## DATA kill_relief — killing the hunter is now an ACTIVE Notice/Heat sink that always lands below
## the respawn rung (see the kill_relief doc on THREATS). Keyed on the tracked spawn id (this
## node's own provenance), never an NPC identity; the relief value rides the meter's DATA row.
func _on_event(ev: Dictionary) -> void:
	if String(ev.get("type", "")) != "agent_downed":
		return
	var d: Dictionary = ev.get("data", {}) if ev.get("data") is Dictionary else {}
	var target_id := String(d.get("target", ""))
	if target_id == "":
		return
	for meter in THREATS.keys():
		if String(_active.get(meter, "")) != target_id:
			continue
		_active[meter] = ""
		var relief := float((THREATS[meter] as Dictionary).get("kill_relief", 0.0))
		var m := _al("Meters")
		if m != null and relief > 0.0:
			m.adjust(meter, -relief, "threat_downed")
		var eb := _al("EventBus")
		if eb != null:
			# A world fact (not a command) — the HUD/telemetry can announce "the hunt is thrown off".
			# N4: carries the FORM (this meter's DATA row) so the announcement layer can resolve the
			# authored copy off the form def — symmetrical with threat_dispatched, never an NPC id.
			eb.emit_event("threat_resolved", {"meter": meter, "agent": target_id,
				"form": String((THREATS[meter] as Dictionary).get("form", ""))})

## Ensure the meter's threat is staged (up to the cap) when the meter is at/above the rung. Idempotent:
## a live, standing threat is left as-is (no stacking); a missing or downed one is (re)spawned.
## B5 (BUG C, the climax shield): NEVER spawns/respawns while Ritual Night is live — the crypt climax
## already stages defenders + backlash, and a high-Heat arrival used to get hunters respawning into
## it every threat tick on top. Both dispatch paths (the threshold ear and the hourly reconcile)
## funnel through here, so the shield covers both; the meter stays high, and the FIRST threat tick
## after the climax ends re-dispatches (the pressure resumes, never silently dropped).
func _ensure_threat(meter: String) -> void:
	if not THREATS.has(meter):
		return
	var rn := _al("RitualNight")
	if rn != null and rn.has_method("active") and rn.active():
		return
	if not _meter_high(meter):
		return
	if _live_count(meter) >= MAX_ACTIVE:
		return
	_spawn_threat(meter)

## Spawn one threat for a meter: a runtime Agent wearing the meter's form, flagged in_combat with a
## published combat_intent engaging the player, registered through the M9 seam so the built tactical
## layer pursues + attacks. Keyed off DATA (the THREATS row), never an NPC identity.
func _spawn_threat(meter: String) -> void:
	var reg := _al("Agents")
	if reg == null:
		return
	var row: Dictionary = THREATS[meter]
	var id := "%s__%s" % [String(row["prefix"]), str(_spawn_serial())]
	var a := Agent.new(id)
	# N6 (B2): the hunt reads diegetic — the form's DATA display_name when authored (combat_
	# forms.json), the prefix only as the fallback. No raw ids on labels/announcements.
	var adb := _al("AbilityDB")
	var dn: String = String(adb.form_display_name(String(row["form"]))) if adb != null else ""
	a.display_name = dn if dn != "" else String(row["prefix"])
	a.combat_form = String(row["form"])
	a.room = _target_room()
	a.position = _spawn_position(meter)
	a.hp = a.max_hp
	a.downed = false
	# M18: arm the threat from its DATA loadout (a gun-user carries a revolver + rounds so the bound
	# cost provider doesn't leave it dry; a monster form has no loadout key). Re-hydrated every spawn;
	# Agents.rebuild drops the runtime agent on a fresh run, so nothing leaks across runs.
	var loadout: Variant = row.get("loadout", {})
	if loadout is Dictionary:
		for item_id in (loadout as Dictionary):
			var n: Variant = (loadout as Dictionary)[item_id]
			if typeof(n) in [TYPE_INT, TYPE_FLOAT] and int(n) > 0:
				a.add_item(String(item_id), int(n))
	# The built engagement seam: in_combat + an engage intent targeting the player. The tactical
	# brain reads combat_intent.target and pursues + casts the form's kit at the investigator.
	a.in_combat = true
	a.combat_intent = {"mode": "engage", "target": PLAYER_ID, "style": String(row["style"]),
		"set_at_beat": 0}
	reg.register_agent(a)
	_active[meter] = id
	var eb := _al("EventBus")
	if eb != null:
		# A world fact (not a command) — the HUD/telemetry can announce "a hunter is on you".
		eb.emit_event("threat_dispatched", {"meter": meter, "form": String(row["form"]), "agent": id})

# --- decay / respawn pump ---------------------------------------------------------------------
func _on_minute_ticked(_minute_of_day: int, _day: int) -> void:
	_minute_accum += 1
	while _minute_accum >= MINUTES_PER_HOUR:
		_minute_accum -= MINUTES_PER_HOUR
		_hourly_tick()

## One in-game hour: first bleed the watcher meters via the CANONICAL passive decay (owned by
## MeterDrivers, alongside the other passive meter mechanics), THEN reconcile each threat — respawn a
## killed one while the meter stays high, leave it cleared once the meter has decayed below the rung.
## Decay runs before reconcile (same single hourly pump) so a meter that crosses below the threat rung
## this hour stops its hunter from respawning — the threat-decay lifecycle.
func _hourly_tick() -> void:
	var m := _al("Meters")
	if m == null:
		return
	# The passive Notice/Heat decay is MeterDrivers' canonical mechanic; drive it here (the one hourly
	# hour-boundary owner) ahead of reconcile. If MeterDrivers is absent (headless unit contexts), the
	# reconcile below still runs off whatever the meters currently read.
	var drivers := _al("MeterDrivers")
	if drivers != null and drivers.has_method("apply_passive_meter_decay"):
		drivers.apply_passive_meter_decay()
	for meter in THREATS.keys():
		_reconcile(meter)

## Bring the meter's live threat in line with the meter: (re)spawn while high + under cap, and drop
## the bookkeeping for a threat that has been downed/cleared.
func _reconcile(meter: String) -> void:
	# Clear the bookkeeping if the tracked agent is gone/downed.
	var tracked := String(_active.get(meter, ""))
	if tracked != "":
		var reg := _al("Agents")
		var a: Agent = reg.get_agent(tracked) if reg != null else null
		if a == null or a.downed:
			_active[meter] = ""
	# Respawn while the meter stays high (the pressure persists until the player brings it down).
	if _meter_high(meter):
		_ensure_threat(meter)

## The manual pump seam the harness drives (a headless test steps the reconcile without a live Clock).
func tick_threats() -> void:
	for meter in THREATS.keys():
		_reconcile(meter)

# --- reset (run-scoped; no cross-run leak) ----------------------------------------------------
## Scrub the live-threat bookkeeping. RunManager._reset_run_world calls this; the paired Agents.rebuild
## drops the runtime-registered threat agents themselves, so a fresh run inherits no phantom hunter.
func reset() -> void:
	_active = {"notice": "", "heat": ""}
	_minute_accum = 0
	# Reset the spawn serial too, so a fresh run's threat ids (and thus the deterministic replay of a
	# fixture that scrubs to a clean baseline each pass) are byte-identical run-to-run — the serial is
	# run-scoped bookkeeping, not a process-lifetime counter.
	_serial = 0

func _on_run_started(_day: int) -> void:
	# The reset() above ran inside _reset_run_world (before this signal); just re-zero the accumulator
	# so the decay pump restarts on an hour boundary. Idempotent with reset().
	_minute_accum = 0

# --- queries (for the harness + HUD) ----------------------------------------------------------
## True when a live (registered, not-downed) threat is staged for the meter.
func has_active_threat(meter: String) -> bool:
	return _live_count(meter) > 0

func active_threat_id(meter: String) -> String:
	return String(_active.get(meter, ""))

## B5 (BUG B): the DATA threat-form registry — true when a combat_form is one THIS node dispatches
## (a row in THREATS). MeterDrivers' public-witness gate excludes such agents (a dispatched hunter
## is the pursuit itself, not a bystander whose sighting should compound the meter that sent it).
## Pure read of the THREATS data table; engine-neutral (a form check, never an NPC identity).
func is_threat_form(form: String) -> bool:
	if form == "":
		return false
	for meter in THREATS.keys():
		if String((THREATS[meter] as Dictionary).get("form", "")) == form:
			return true
	return false

# --- helpers ----------------------------------------------------------------------------------
## The meter is at/above its threat rung (Meters.THREAT_RUNG).
func _meter_high(meter: String) -> bool:
	var m := _al("Meters")
	if m == null:
		return false
	return m.get_meter(meter) >= float(m.THREAT_RUNG)

## How many live (registered, not-downed) threats wear this meter's form right now.
func _live_count(meter: String) -> int:
	if not THREATS.has(meter):
		return 0
	var reg := _al("Agents")
	if reg == null:
		return 0
	var tracked := String(_active.get(meter, ""))
	if tracked == "":
		return 0
	var a: Agent = reg.get_agent(tracked)
	return 1 if (a != null and not a.downed) else 0

## The room a threat spawns into — the override, else the live player's room.
func _target_room() -> String:
	if spawn_room != "":
		return spawn_room
	var reg := _al("Agents")
	var p: Agent = reg.get_agent(PLAYER_ID) if reg != null else null
	return p.room if p != null else "city"

## Where a threat spawns. An explicit spawn_pos wins (tests); otherwise a DETERMINISTIC run-seed
## scatter around the player's position — reproducible per run, never RNG-in-combat.
func _spawn_position(meter: String) -> Vector2:
	if spawn_pos != Vector2.ZERO:
		return spawn_pos
	var reg := _al("Agents")
	var p: Agent = reg.get_agent(PLAYER_ID) if reg != null else null
	var base := p.position if p != null else Vector2.ZERO
	# A seeded angle per meter so the two threats don't overlap, folded with the run seed — pure math,
	# no RNG object, so it's byte-identical for a fixed seed.
	var wm := _al("WorldManager")
	var seed_val := int(wm.seed_value) if (wm != null and "seed_value" in wm) else 0
	var salt := 1 if meter == "notice" else 2
	var angle := float((seed_val * 31 + salt * 97) % 360) * PI / 180.0
	return base + Vector2(cos(angle), sin(angle)) * SEED_SCATTER_R

## A monotonic serial so successive spawns get unique ids within a run (a respawn is a NEW agent, so
## its runtime state is clean). Derived from the registry size + a counter; deterministic per run.
var _serial: int = 0
func _spawn_serial() -> int:
	_serial += 1
	return _serial

func _al(autoload_name: String) -> Node:
	var ml := Engine.get_main_loop()
	if ml == null or not (ml is SceneTree):
		return null
	return (ml as SceneTree).root.get_node_or_null(autoload_name)
