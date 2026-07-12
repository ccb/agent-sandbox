extends Node
## Meter drivers (autoload singleton `MeterDrivers`) — direction v2 §4.
##
## The event-wired, engine-neutral bridge that turns world events into meter movement. Listens on
## the EventBus and nudges the four meters through the Meters authority — NEVER the reverse: meters
## READ combat/cult events, they never feed back into combat resolution (the §f determinism guard
## pins that the transcript is identical whatever the meters read). Deterministic — no RNG, no
## per-frame LLM, no wall time. No NPC-identity branches (engine neutrality): the drivers key on
## event TYPE + the neutral caster="player" fact, never on who any NPC is.
##
## Wiring (§4 "meter drivers"):
##   * ability_cast_started by the PLAYER  -> Notice (OCCULT power use only — B5 retro: Notice is
##     the "Attention of the Beyond", so it gates on the cast being occult exactly like the Madness
##     tick gates on HEAVY_CLASSES; a mundane dash/pistol_whip/revolver_shot draws none) + Madness
##     (heavy/assume_form casts) + Heat IF the cast is in PUBLIC VIEW — Heat is vision-gated through
##     the ONE shared perceiver gate (Perception.can_perceive), exactly like Stimulus's witness fan
##     and the HUD telegraph: a cast no living witness could see raises no Heat. A mundane gun still
##     drives Heat this way (officialdom cares about public gunfire; the Beyond does not).
##   * transformed (agent="player") -> Madness (assume_form is the leash; §4 +25). The player's own
##     transform is the heavy-power tick; NPC transforms are the city's business (DeedRunner), not
##     the player's meters.
##   * ritual_advanced / summoning_climax -> Doom (cult progress you didn't stop hastens the clock).
##   * Clock.minute_ticked (batched to whole in-game hours) -> Doom, over TWO §4 sources: the world
##     clock's own creep (time passing) and a per-monster nudge for every monster left alive. Pure
##     game-time — no wall clock, no RNG — and a pure world-state READ, never a combat feed-back.
##   * agent_downed by the PLAYER in public view -> Heat (a body left where it's seen).
##
## Numbers are TUNING placeholders.

## Notice per OCCULT player cast (see OCCULT_CLASSES + the abilities.json `occult` tag). TUNING.
const NOTICE_PER_CAST: float = 6.0
## Heat per witnessed public player cast. TUNING.
const HEAT_PER_PUBLIC_CAST: float = 8.0
## Heat per witnessed player kill (a body left seen). TUNING.
const HEAT_PER_WITNESSED_KILL: float = 12.0
## Madness per heavy/high-tier player cast (assume_form rides `transformed` instead). TUNING.
const MADNESS_PER_HEAVY_CAST: float = 8.0
## Doom per rite step the player didn't stop. TUNING.
const DOOM_PER_RITE_STEP: float = 4.0
## Doom the world clock creeps up on its own per in-game hour — time is the cult's ally (§4 "Doom
## rises when time passes"). TUNING. Retuned down from 0.5 in M11: the coarser DAY/PHASE-advance fill
## below is now the primary passive pacer, and the two together are tuned so a fully-idle ~7-day run
## reaches Doom 100 around day 6-7 on its own (so the meters can't be ignored — the clock is always
## ticking toward Ritual Night).
const DOOM_PER_HOUR: float = 0.3
## Doom the run's PROGRESS adds on every in-game day/phase advance (§4 "Doom rises with time" / M11 —
## an idle run still paces toward Ritual Night). Fired on Clock.phase_changed so each of the day's
## phase boundaries (early-morning/morning/afternoon/dusk/night/late-night) nudges Doom; combined with
## the hourly creep above and the rite-step/lead drivers, an idle run's passive-only fill hits 100 by
## ~day 6-7 (a phase is ~1/6 of a day, so ~1.7/phase carries a clean run to the climax on its own —
## measured: an idle run from day-1 08:00 reaches Doom 100 on day 6). TUNING — placeholder.
const DOOM_PER_PHASE: float = 1.7
## Doom per LIVE monster left loose in the district, per in-game hour — a monster you don't put down
## keeps hastening the descent (§4 "monsters you leave alive"). M26 BALANCE RETUNE #2: cut 0.75 ->
## 0.35. At 0.75 a SINGLE loose monster added 0.75*24 = 18 Doom/day — on top of the ~17.4/day passive
## fill, one monster HALVED the run (idle-plus-one-monster hit 100 by ~day 3-4 instead of ~day 6).
## 0.35 (8.4/day per monster) keeps a loose monster a real, mounting cost without turning one straggler
## into a forced loss. Applies to transformed monster forms (is_monster_form, always) AND — only once
## its lead is KNOWN — the hidden-Beyonder human phases folded into _live_monster_count
## (is_hidden_beyonder_form gated on LeadSystem.known_prey_forms()): ignoring KNOWN prey costs Doom at
## the same per-head rate, but an idle player who was never told of a Beyonder is not taxed for it (the
## RETUNE #2 pacing fix — otherwise 3 always-loose hidden Beyonders collapse the idle run to day 3). TUNING.
const DOOM_PER_MONSTER_HOUR: float = 0.35
## The CANONICAL passive Notice/Heat decay, per in-game hour (§4 "Notice/Heat decays over time"). This
## is a GLOBAL passive bleed of the two watcher meters — it lives here with the other passive meter
## mechanics (not in MeterThreats, which only stages the spawns), so a reader tuning meter decay finds
## it in one place. MeterThreats drives it once per hourly threat tick, BEFORE it reconciles its
## spawns, so a meter that decays below the threat rung in the same tick stops respawning its hunter
## (the threat-decay lifecycle). Bleeds only while the meter is > 0 (never nudges a meter the drivers
## never raised). TUNING placeholder — at 6/hour a spiked 70 meter bleeds to 0 in ~12 in-game hours.
const NOTICE_HEAT_DECAY_PER_HOUR: float = 6.0
## The watcher meters this passive decay bleeds (the two threat-driving meters — Doom/Madness have
## their own dynamics and never passively bleed). Data, not a branch.
const DECAYING_METERS: Array[String] = ["notice", "heat"]
## The Clock ticks per game-minute; the slow Doom fill batches to whole in-game hours.
const MINUTES_PER_HOUR: int = 60
## The player id (the neutral proxy id — no NPC-identity branch).
const PLAYER_ID: String = "player"

## Game-minutes counted toward the next whole-hour Doom tick. Zeroed on a fresh run (RunManager
## .run_started) so a new run's slow fill restarts on an hour boundary. Sub-hour scratch only —
## deliberately not persisted (a save lands on the current hour's granularity).
var _doom_minute_accum: int = 0

## Ability classes that count as "heavy/high-tier" for the Madness tick (a plain revolver shot is
## not heavy). Data-driven off the ability's authored class — no per-ability hardcode.
const HEAVY_CLASSES: Array[String] = ["transform", "spell"]

## B5 retro (live-playtest BUG A): the classes whose every member is an OCCULT working — the Notice
## gate's class half, mirroring the HEAVY_CLASSES mechanism above. Notice is the "Attention of the
## Beyond" (Meters §4): it rises ONLY on occult power use. Abilities of other classes that are still
## occult (the Hermit's star_brand projectile, the effect-class rites) carry an `occult: true` DATA
## tag in abilities.json — a data tag + a class set, never a hardcoded ability-id list in engine.
## Kept a SEPARATE constant from HEAVY_CLASSES (same membership today): "heavy enough to rattle YOUR
## control" and "occult enough to draw the Beyond's eye" are different tuning axes.
const OCCULT_CLASSES: Array[String] = ["transform", "spell"]

func _ready() -> void:
	var eb := _al("EventBus")
	if eb != null and not eb.event_logged.is_connected(_on_event):
		eb.event_logged.connect(_on_event)
	# The two engine-neutral, game-time Doom drivers (§4): the world clock's own creep and the
	# pressure of monsters left alive both ride the Clock's per-minute tick, batched to whole hours.
	var clock := _al("Clock")
	if clock != null and not clock.minute_ticked.is_connected(_on_minute_ticked):
		clock.minute_ticked.connect(_on_minute_ticked)
	# M11: the DAY/PHASE-advance passive Doom pacer — each in-game phase boundary nudges Doom, so an
	# idle run still marches toward Ritual Night (§4). Rides phase_changed (fires once per phase
	# crossing), never wall time — deterministic, and inert for the combat sims (which don't advance
	# whole phases mid-fight).
	if clock != null and not clock.phase_changed.is_connected(_on_phase_changed):
		clock.phase_changed.connect(_on_phase_changed)
	# A fresh run zeroes the sub-hour accumulator so the slow fill restarts on an hour boundary.
	var rm := _al("RunManager")
	if rm != null and not rm.run_started.is_connected(_on_run_started):
		rm.run_started.connect(_on_run_started)

func _on_event(ev: Dictionary) -> void:
	var m := _al("Meters")
	if m == null:
		return
	var t := String(ev.get("type", ""))
	var d: Dictionary = ev.get("data", {}) if ev.get("data") is Dictionary else {}
	match t:
		"ability_cast_started":
			_on_player_cast(m, d)
		"transformed":
			# The player's own transform is the assume_form leash tick (+25). NPC transforms are
			# not the player's Madness (they drive the city through DeedRunner, not this meter).
			if String(d.get("agent", "")) == PLAYER_ID:
				m.add_madness(Meters.MADNESS_ASSUME_FORM, "assume_form")
		"ritual_advanced", "summoning_climax":
			# Cult progress the player didn't stop hastens the Doom clock.
			m.adjust("doom", DOOM_PER_RITE_STEP, t)
		"agent_downed":
			_on_player_kill(m, d)

## A player cast: Notice for OCCULT casts only (B5 — the Beyond watches occult power, not gunpowder;
## gate mirrors the Madness HEAVY_CLASSES mechanism below) + a Madness tick for heavy casts; Heat
## only when a living witness could perceive it (vision-gated public view) — mundane arts included,
## so the revolver still costs Heat when fired in public even though it never draws Notice.
func _on_player_cast(m: Node, d: Dictionary) -> void:
	if String(d.get("caster", "")) != PLAYER_ID:
		return
	var ability_id := String(d.get("ability", ""))
	if _cast_is_occult(ability_id):
		m.adjust("notice", NOTICE_PER_CAST, "power_use")
	# Heavy/high-tier casts also cost Madness (assume_form itself rides `transformed`).
	var klass := _ability_class(ability_id)
	if HEAVY_CLASSES.has(klass):
		m.add_madness(MADNESS_PER_HEAVY_CAST, "heavy_cast")
	if _cast_is_witnessed():
		m.adjust("heat", HEAT_PER_PUBLIC_CAST, "public_cast")

## A downing whose actor is the player, seen in public -> Heat (a body left where it's seen).
func _on_player_kill(m: Node, d: Dictionary) -> void:
	if String(d.get("actor", "")) != PLAYER_ID:
		return
	if _cast_is_witnessed():
		m.adjust("heat", HEAT_PER_WITNESSED_KILL, "witnessed_kill")

## The slow, game-time Doom drivers (§4). Every in-game minute the Clock ticks, count it toward the
## next whole hour; on each hour boundary the world clock creeps forward AND every monster still
## loose adds its pressure. Batched to hours so the registry is read at most once per in-game hour
## (cheap) and the fill is identical however the clock was advanced — deterministic, so the minute /
## day args are unused. Pure world-state READ + Meters write; never touches combat resolution.
func _on_minute_ticked(_minute_of_day: int, _day: int) -> void:
	_doom_minute_accum += 1
	while _doom_minute_accum >= MINUTES_PER_HOUR:
		_doom_minute_accum -= MINUTES_PER_HOUR
		_apply_hourly_doom()

## M11: a day/phase advance is the run's coarse passive Doom pacer (§4 "Doom rises with time"). Each
## in-game phase boundary the Clock crosses adds DOOM_PER_PHASE, so an idle run still paces toward the
## climax. Pure game-time (fires off phase_changed) + a Meters write; never touches combat resolution.
func _on_phase_changed(_phase: String, _day: int) -> void:
	var m := _al("Meters")
	if m == null:
		return
	m.adjust("doom", DOOM_PER_PHASE, "time_phase")

## One in-game hour of Doom fill: the world clock's own creep (time passing) plus a nudge for every
## monster left alive. Two distinct §4 sources, tagged with separate reasons so the HUD/telemetry
## can tell them apart. A no-op when there is no Meters authority (headless unit contexts).
func _apply_hourly_doom() -> void:
	var m := _al("Meters")
	if m == null:
		return
	m.adjust("doom", DOOM_PER_HOUR, "time")
	var loose := _live_monster_count()
	if loose > 0:
		m.adjust("doom", DOOM_PER_MONSTER_HOUR * float(loose), "monsters_alive")

## The canonical passive Notice/Heat decay (§4). Bleeds each watcher meter by NOTICE_HEAT_DECAY_PER_HOUR
## while it's > 0 (never nudges a meter the drivers never raised). Called ONCE per in-game hour by
## MeterThreats' hourly threat tick, BEFORE it reconciles its spawns — so decay and respawn share a
## single deterministic pump and a meter that crosses below the threat rung this hour stops its hunter
## from respawning. Public so the threat pump (the one hourly hour-boundary owner) can order it ahead of
## reconcile; pure Meters write, never a combat feed-back. A no-op when there is no Meters authority.
func apply_passive_meter_decay() -> void:
	var m := _al("Meters")
	if m == null:
		return
	for meter in DECAYING_METERS:
		if m.get_meter(meter) > 0.0:
			m.adjust(meter, -NOTICE_HEAT_DECAY_PER_HOUR, "meter_decay")

## Count the LIVE agents that hasten Doom — keyed generically off the form's own data flags, NEVER an
## NPC-identity branch. Two kinds count, both at DOOM_PER_MONSTER_HOUR each (M26 RETUNE #2):
##   * a TRANSFORMED monster form (AbilityDB.is_monster_form — the loose creature) ALWAYS counts: a beast
##     rampaging in the street is self-evidently a threat, no lead needed; AND
##   * a HIDDEN-Beyonder human phase (AbilityDB.is_hidden_beyonder_form — butcher_human / wren_human /
##     mack_harbor) counts ONLY once the player has been TOLD it is prey — i.e. its lead is KNOWN
##     (LeadSystem.known_prey_forms(), matched on the lead's DATA prey_form). This is the RETUNE #2 fix:
##     the 3 hidden Beyonders are live in their human faces from run start, so counting them
##     unconditionally taxed an IDLE player ~25 Doom/day and collapsed the run to day 3. Gating on KNOWN
##     prey means a player who has engaged nothing is never taxed for Beyonders they were never named
##     (idle passive stays ~day 6), while IGNORING prey the city HAS named still costs Doom — the exact
##     §4 intent ("ignoring known prey"). The transformed shapes stay counted via is_monster_form, so a
##     foe that sheds its human face into its beast keeps counting regardless of lead state.
## A downed agent is no longer a threat, so it doesn't count. Pure read of the Agents/LeadSystem
## registries; monster-form count still works with no LeadSystem (unit contexts); 0 when Agents/AbilityDB
## is absent. Engine-neutral: no NPC id, no form id hardcoded here — the linkage lives in leads.json.
func _live_monster_count() -> int:
	var reg := _al("Agents")
	var db := _al("AbilityDB")
	if reg == null or db == null:
		return 0
	var ls := _al("LeadSystem")
	var known: Dictionary = ls.known_prey_forms() if ls != null else {}
	var n := 0
	for a in reg.all():
		if a == null or a.downed:
			continue
		if db.is_monster_form(a.combat_form):
			n += 1
		elif db.is_hidden_beyonder_form(a.combat_form) and known.has(a.combat_form):
			n += 1
	return n

## A fresh run restarts the slow Doom fill from a whole-hour boundary (see `_doom_minute_accum`).
func _on_run_started(_day: int) -> void:
	_doom_minute_accum = 0

## Was the player's action in PUBLIC VIEW? True when SOME other live agent could perceive the
## player through the ONE shared perceiver gate (Perception.can_perceive — same room + within that
## witness's own vision_r of where the player stands). The player proxy itself never witnesses
## itself; a downed agent has no working eyes. B5 retro (live-playtest BUG B): a DISPATCHED THREAT
## is not a public witness either — the hunter IS the meter's pursuit made flesh, so its own eyes
## must not compound the meter that sent it (fighting the nighthawk used to feed Heat +8 per shot
## it "witnessed", pinning the meter above its respawn rung forever). Keyed on the combat_form via
## MeterThreats' DATA threat-form registry (the THREATS table), never an NPC identity. Pure read —
## no combat state touched.
func _cast_is_witnessed() -> bool:
	var reg := _al("Agents")
	if reg == null:
		return false
	var proxy: Agent = reg.get_agent(PLAYER_ID)
	if proxy == null:
		return false
	var mt := _al("MeterThreats")
	for other in reg.all():
		if other == null or other.id == PLAYER_ID or other.downed:
			continue
		if mt != null and mt.has_method("is_threat_form") and mt.is_threat_form(other.combat_form):
			continue
		if Perception.can_perceive(other, proxy.room, proxy.position):
			return true
	return false

## The authored class of an ability (data-driven; "" when unknown).
func _ability_class(ability_id: String) -> String:
	if ability_id == "":
		return ""
	var db := _al("AbilityDB")
	if db == null or not db.has_ability(ability_id):
		return ""
	return String((db.ability_for(ability_id) as Dictionary).get("class", ""))

## Is a cast an OCCULT working (the Notice gate, B5)? True when its authored class is in
## OCCULT_CLASSES (every spell/transform is occult by nature) OR the ability carries the
## `occult: true` DATA tag in abilities.json (the occult members of the other classes — e.g. the
## Hermit's star_brand projectile, the effect-class rites). Data-driven both halves: no ability-id
## hardcode in engine. An unknown/empty ability is not occult (raises no Notice).
func _cast_is_occult(ability_id: String) -> bool:
	if ability_id == "":
		return false
	var db := _al("AbilityDB")
	if db == null or not db.has_ability(ability_id):
		return false
	var def: Dictionary = db.ability_for(ability_id)
	if OCCULT_CLASSES.has(String(def.get("class", ""))):
		return true
	return bool(def.get("occult", false))

func _al(autoload_name: String) -> Node:
	var ml := Engine.get_main_loop()
	if ml == null or not (ml is SceneTree):
		return null
	return (ml as SceneTree).root.get_node_or_null(autoload_name)
