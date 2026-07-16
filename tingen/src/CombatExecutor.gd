@static_unload
class_name CombatExecutor
extends Node2D
## Per-fighting-body action layer (combat plan §M2 + M3). Owns its agent's body authority while
## agent.in_combat: the ability-execution FSM (idle → windup → active → recovery), movement
## skills (dash/charge/blink + stagger knockback), spawned projectiles/zones, and this agent's
## frame-rate combat state (statuses, poise, i-frames) — all deterministic, all synchronous,
## advanced ONLY by step_combat(dt) with an internally accumulated clock (never wall time).
##
## M3 adds the two decision layers that pilot this machinery (the LLM still never rides the
## frame path):
##   * a TacticalBrain (opt-in via enable_tactics — the live NPC seam enables it; M2 harness
##     scripts that drive executors directly stay byte-identical), ticking at ~8Hz on THIS
##     clock, reading combat_intent/kit/bands/cooldowns and acting through try_cast + the
##     steering channel (pursue/strafe/back_away/goto walks, executed here at COMBAT_WALK_SPEED);
##   * compiled reflexes (ReflexRules over the combat_form's data rows): this executor listens
##     to the EventBus but FILTERS through the ONE shared perceiver gate
##     (Perception.can_perceive — same room + within THIS agent's vision_r), so reflexes react
##     only to what the agent could SEE; due reactions run on this clock (cast → try_cast,
##     dodge → dash if in kit else a strafe burst, style → intent.style in place, flee →
##     disengage posture).
##
## Damage lands ONLY through Agent.take_damage (the existing combat-mode flip / downed /
## EndGame wiring keeps working) and every strike emits the existing `agent_attacked` event
## shape through one helper, so Stimulus witnessing and the panels never notice the new
## machinery. Hit DETECTION is geometric against Hurtbox radii + agent.position (data stays
## authoritative; no physics-server dependency, so headless manual stepping and the live
## _physics_process advance identically); the Hurtbox Area2D still rides every fighting body
## for future editor/visual wiring. The LLM is never here: WHAT to cast is M3+ (tactical/
## reflex/intent); this node only executes.
##
## Instanced by NPC.gd when its bound agent enters combat (the M1 seam), freed when it exits;
## standalone-instancable for tests/harnesses: bind(agent) + manual step_combat(dt) calls.
## Combat state is EPHEMERAL (ms-stamped scratch) — never persisted by SaveManager.

## FSM phases.
const PHASE_IDLE := "idle"
const PHASE_WINDUP := "windup"
const PHASE_ACTIVE := "active"
const PHASE_RECOVERY := "recovery"

## Movement-skill speeds (px/s) — data distances ride the ability; speeds are engine feel.
const DASH_SPEED: float = 560.0
const CHARGE_SPEED: float = 420.0
## Active-phase windows (ms): a melee arc stays live briefly (dedup keeps it one hit).
const MELEE_ACTIVE_MS: int = 120
const DEFAULT_ACTIVE_MS: int = 100
## Recovery after the active phase when the ability doesn't author `recovery_ms`.
const DEFAULT_RECOVERY_MS: int = 300
## Melee arc half-width: target must sit within ~60° of the swing direction (cos 0.5).
const MELEE_ARC_COS: float = 0.5
## Hurtbox radius for a fighter whose body/executor never declared one.
const DEFAULT_HURTBOX_R: float = 12.0

var agent: Agent = null
var body: Node2D = null
## This agent's frame-rate combat state (resolver shape). hp mirrors the Agent (authority).
var state: Dictionary = {}
## Cooldown ledger (resolver helpers).
var ledger: Dictionary = {}
## Current FSM phase.
var phase: String = PHASE_IDLE
## Spawned-by-me projectiles / zones — stepped by ME (single stepping authority, so live
## engine callbacks and manual test stepping never double-advance them).
var projectiles: Array = []
var zones: Array = []
## Motion clamp when no physics body is available (permissive default; the live path uses
## move_and_collide against the body's real collider instead).
var world_rect: Rect2 = Rect2(-100000, -100000, 200000, 200000)
## Geometric hurtbox radius (sized from the body's collision when a body is bound).
var hurtbox_radius: float = DEFAULT_HURTBOX_R

## ---- M3 state ----
## Combat-walk pace for steering directives (px/s) — the deliberate closing/kiting stride,
## between the puppet glide (60) and a dash (560).
const COMBAT_WALK_SPEED: float = 140.0
## The kit-less dodge: a short perpendicular burst (survival sprint, sub-dash).
const REFLEX_BURST_SPEED: float = 280.0
const REFLEX_BURST_MS: int = 350

## The tactical layer (created by enable_tactics; null = scripted/harness-driven executor).
var tactics: TacticalBrain = null
## The ability-cost seam (M5). Null = every cast is FREE (NPC kits' authored costs stay
## unenforced tonight — byte-identical M2/M3 behavior). The player's PlayerCombat binds a
## provider object whose `try_pay(ability) -> {ok, reason}` is asked LAST in try_cast's
## refusal chain: a refused cost never burns the cooldown; a paying cast deducts at accept
## time (an interrupted cast has still spent, exactly like the cooldown mark).
var cost_provider: Object = null
## Dry-art retry-suppression (retro audit B2 — the M18 "leans on free arts" claim): an art the
## cost_provider just refused (no_ammo/no_weapon/…) is remembered here so the TACTICS layer skips
## it during re-SELECTION and falls through to an affordable art, instead of re-locking the same
## refused top pick every tick (a dry gunman used to livelock — offensively passive forever).
## SELECTION-ONLY by design: the cast ledger is never marked (a refused cost still burns NO
## cooldown), try_cast's own refusal contract is untouched (a direct/player retry still asks the
## provider and still gets "no_ammo"), and the suppression lapses after COST_RETRY_MS so a
## mid-fight resupply re-enables the art. ability_id -> executor-clock ms the art may be
## re-selected at.
const COST_RETRY_MS: int = 2000
var _cost_refused: Dictionary = {}
## Current steering directive {kind: pursue|strafe|back_away|goto, ...} — {} = hold.
var steering: Dictionary = {}
## Who last landed a routed hit on THIS agent (the no-intent default posture's target).
var last_attacker_id: String = ""
## When THIS agent last took a routed hit (executor clock; defensive counter window).
var last_hit_ms: int = -1000000
## A reflex `style` reaction with no standing intent lands here (the default posture's mask).
var style_override: String = ""
## A reflex `flee` latches disengage behavior on the tactical layer until combat ends.
var reflex_flee: bool = false

var _reflex_rules: Array = []          # the combat_form's authored rows (or test-injected)
var _reflex_fired: Dictionary = {}     # rule_index -> fires (ReflexRules max_fires ledger)
var _pending_reflex: Array = []        # scheduled reactions [{do, fire_at_ms, threat, ...}]
var _burst: Dictionary = {}            # {dir, until_ms} — the kit-less dodge in flight
var _last_seen_hit_ms: int = -1000000  # last PERCEIVED landed hit (own or witnessed)
var _dodge_sign: float = 1.0           # alternate side-dodge direction, deterministically
var _cd_watch: Array = []              # ability ids named by cooldown_ready reflex rows
var _cd_prev: Dictionary = {}          # ability id -> was-ready last frame (edge detection)

## Static hit ledger: target id -> last agent that DAMAGED it (any path, incl. fallback hits).
## The cheap lookup protect-mode needs to name a ward's threat; "dot" and blank actors never
## register (a threat must be a real agent).
static var _last_attacker: Dictionary = {}

static func last_attacker_of(target_id: String) -> String:
	return String(_last_attacker.get(target_id, ""))

static func reset_last_attackers() -> void:
	_last_attacker.clear()

var _time_s: float = 0.0
var _phase_end_ms: int = 0
var _cast: Dictionary = {}     # {ability, target_id, dir} while a cast is in flight
var _motion: Dictionary = {}   # {kind, dir, speed, remaining[, ability]} — empty = none
var _swing_hit: Array = []     # per-swing dedup (agent ids already hit by this arc)
var _hurtbox: Area2D = null

## ---- M6 anim wiring (first visual pass) ----
## Which strip file suffix each anim cue maps to. Only cues with authored strips play; every
## other cue (dash/cast/transform — no strips exist for them tonight) stays a silent no-op.
## Files follow the M7 naming: assets/anim/<combat_form>_<suffix>.png, 8 frames side-by-side.
const ANIM_STRIPS: Dictionary = {"attack": "attack_side", "hurt": "hurt_down", "death": "death_down"}
const ANIM_DIR: String = "res://assets/anim/"
## Static per-form body sprite (the transform's visible swap): assets/enemies/<form>.png.
const FORM_SPRITE_DIR: String = "res://assets/enemies/"
const STRIP_FRAMES: int = 8
const STRIP_FPS: float = 12.0
## On-screen height (px) a revealed form's standee sprite is scaled down to — and the height
## the strip FIGURE must match (P3 readability: the anim must not shrink the monster).
const FORM_SPRITE_TARGET_H: float = 64.0

var _strip: Dictionary = {}        # {sprite, start_ms, hold_last} — a strip in flight
var _sprite_base: Dictionary = {}  # the body sprite's resting look (captured once, transform re-bases)

## Live registry: agent id -> executor, so projectiles/zones/melee route a hit through the
## TARGET's executor (its i-frames, shield, poise live there).
static var _by_agent: Dictionary = {}

static func for_agent(id: String) -> CombatExecutor:
	return _by_agent.get(id, null)

## Route a hit onto a target agent: through its executor when it has one (i-frames/shield/
## poise live there), else the transient fallback (damage/downing/events still land).
static func route_hit(attacker: Agent, target: Agent, ability: Dictionary, dir: Vector2) -> Dictionary:
	var ex := for_agent(target.id)
	if ex != null:
		return ex.receive_hit(attacker, ability, dir)
	return land_fallback_hit(attacker, target, ability, dir)

## The geometric hurtbox radius for any agent (executor-declared, or the default).
static func radius_of(target_id: String) -> float:
	var ex := for_agent(target_id)
	return ex.hurtbox_radius if ex != null else DEFAULT_HURTBOX_R

func bind(agent_in: Agent, body_in: Node2D = null) -> void:
	agent = agent_in
	body = body_in
	state = {"hp": agent.hp, "max_hp": agent.max_hp, "statuses": [], "poise": 0.0, "i_frame_until_ms": 0}
	if agent.id != "":
		_by_agent[agent.id] = self
	if body != null:
		_attach_hurtbox()
		# N4: an agent ALREADY wearing a form with authored art fights in it from the first frame
		# this executor pilots the body — the RitualNight backlash flips combat_form + in_combat
		# directly (no assume_form deltas ever execute), so the VISIBLE half of that shed lands
		# here, through the same one resolution path the transform swap uses. Display-only
		# (a sprite write); a form resolving no art is a silent no-op, so harness stub bodies and
		# human-phase fighters are untouched and the pinned sims stay byte-identical.
		_apply_form_sprite(String(agent.combat_form))
	_load_reflexes()
	# The reflex channel: EventBus, FILTERED per event through the shared perceiver gate —
	# this executor only ever reacts to what its agent could see (plan §M3).
	var eb := _al("EventBus")
	if eb != null and not eb.event_logged.is_connected(_on_world_event):
		eb.event_logged.connect(_on_world_event)

## Attach the ~8Hz tactical layer (the live NPC seam calls this; harness scripts that pilot
## an executor directly leave it off, so the M2 scenarios stay byte-identical).
func enable_tactics() -> void:
	if tactics == null:
		tactics = TacticalBrain.new()

## This executor's deterministic combat clock (accumulated step dt, never wall time).
func now_ms() -> int:
	return int(round(_time_s * 1000.0))

func _physics_process(delta: float) -> void:
	step_combat(delta)

## Advance one combat frame. The ONE stepping entry — the live tree calls it from
## _physics_process; tests and the fight harness call it directly with a fixed dt.
func step_combat(dt: float) -> void:
	if agent == null:
		return
	_time_s += dt
	var now := now_ms()
	if agent.downed:
		# Review M2 #1: a downed body finishes NOTHING — the in-flight telegraph breaks
		# (cast_interrupted reason=downed), motion/steering/reflexes stop. Only the
		# already-spawned projectiles/zones keep flying: they left the body.
		if phase == PHASE_WINDUP:
			_interrupt("downed")
		elif phase != PHASE_IDLE:
			phase = PHASE_IDLE
			_cast = {}
		_motion = {}
		_burst = {}
		steering = {}
		_pending_reflex = []
		_step_spawned(dt)
		_step_strip(now)   # the death strip still advances on a felled body
		_sync_body()
		return
	# A cast PARKED by ActionCommit.cast_ability (the GM-directive seam, plan §M4 — it landed
	# before this executor was spawned, or while it was busy) is consumed on THIS clock: retried
	# while busy/stunned exactly like a reflex cast, dropped on any other refusal.
	if agent.pending_cast != "":
		var parked := try_cast(agent.pending_cast, _current_target_id())
		var parked_reason := String(parked.get("reason", ""))
		if bool(parked.get("ok", false)) or (parked_reason != "busy" and parked_reason != "stunned"):
			agent.pending_cast = ""
	_step_motion(dt, now)
	_step_steering(dt, now)
	_advance_statuses(now)
	_step_fsm(now)
	_step_spawned(dt)
	_watch_cooldowns(now)
	_evaluate_state_reflexes(now)
	_run_pending_reflexes(now)
	if tactics != null:
		tactics.tick(self)
	_step_strip(now)
	_sync_body()

## Ask to cast → {ok, reason}. Refusals: downed | busy | unknown_ability | stunned |
## silenced (windup abilities only — an instant motion has no windup to block) | cooldown |
## whatever the bound cost_provider refuses with (e.g. the player's "no_ammo"/"no_stamina").
## Accepting marks the cooldown ledger, enters windup, and emits the telegraph
## (CombatEvents.cast_started — Stimulus fans it vision-gated; damage NEVER precedes it).
func try_cast(ability_id: String, target_id: String = "", aim_dir: Vector2 = Vector2.ZERO) -> Dictionary:
	if agent == null or agent.downed:
		return {"ok": false, "reason": "downed"}
	if phase != PHASE_IDLE:
		return {"ok": false, "reason": "busy"}
	var db := _al("AbilityDB")
	if db == null or not db.has_ability(ability_id):
		return {"ok": false, "reason": "unknown_ability"}
	var ability: Dictionary = db.ability_for(ability_id)
	var now := now_ms()
	if CombatResolver.has_status(state, "stun", now):
		return {"ok": false, "reason": "stunned"}
	var cast_time := float(ability.get("cast_time", 0.0))
	if cast_time > 0.0 and CombatResolver.has_status(state, "silence", now):
		return {"ok": false, "reason": "silenced"}
	if not CombatResolver.ledger_ready(ledger, ability_id, now):
		return {"ok": false, "reason": "cooldown"}
	# The cost seam (M5): asked last, so a refused cost ("no_ammo"/"no_stamina") burns nothing.
	if cost_provider != null:
		var pay: Variant = cost_provider.call("try_pay", ability)
		if pay is Dictionary and not bool((pay as Dictionary).get("ok", true)):
			# B2 dry-art fallback: stamp the retry-suppression so tactics stop re-picking this
			# art (see _cost_refused docs). The refusal itself is returned UNCHANGED — no ledger
			# mark, no new reason — so the player's direct-input contract stays byte-identical.
			_cost_refused[ability_id] = now + COST_RETRY_MS
			return {"ok": false, "reason": String((pay as Dictionary).get("reason", "cost"))}
	_cost_refused.erase(ability_id)   # a paying (or free) cast clears any stale suppression
	ledger = CombatResolver.ledger_mark(ledger, ability_id, now,
		int(round(float(ability.get("cooldown", 0.0)) * 1000.0)))
	var dir := aim_dir.normalized() if aim_dir.length() > 0.0 else Vector2.ZERO
	var target := _find_agent(target_id)
	# A cross-room target is wrong-space (rooms are separate coordinate systems) — never aim
	# by its coordinates; the cast keeps its named target but falls back to the default axis.
	if target != null and String(target.room) != String(agent.room):
		target = null
	if dir == Vector2.ZERO and target != null:
		var to := target.position - agent.position
		dir = to.normalized() if to.length() > 0.0 else Vector2.RIGHT
	if dir == Vector2.ZERO:
		dir = Vector2.RIGHT
	_cast = {"ability": ability, "target_id": target_id, "dir": dir}
	phase = PHASE_WINDUP
	# The telegraph advertises the EFFECTIVE windup (frenzy compresses it) — reflex dodge
	# windows and the §0 acceptance beat both key on the REAL strike moment (review M2 #6).
	var eff_cast := cast_time / _attack_speed(now)
	_phase_end_ms = now + int(round(eff_cast * 1000.0))
	_play_anim(String(ability.get("anim", "")))
	CombatEvents.cast_started(agent.id, ability_id, target_id, dir, eff_cast)
	return {"ok": true, "reason": ""}

## A hit lands on THIS agent: the resolver applies against this executor's state (its
## i-frames, shields, poise), damage flows through Agent.take_damage, the strike emits the
## existing agent_attacked/agent_downed shapes, and a stagger interrupts + stuns + knocks back.
func receive_hit(attacker: Agent, ability: Dictionary, dir: Vector2) -> Dictionary:
	if agent == null or agent.downed:
		return {}
	var now := now_ms()
	state["hp"] = agent.hp
	state["max_hp"] = agent.max_hp
	var deltas := CombatResolver.apply_ability({}, state, ability, {"now_ms": now, "dir": [dir.x, dir.y]})
	if bool(deltas.get("dodged", false)):
		return deltas
	# M3: a routed (non-dodged) hit stamps the counter window and the default posture's target.
	last_hit_ms = now
	if attacker != null and attacker.id != "" and attacker.id != agent.id:
		last_attacker_id = attacker.id
	state = deltas.get("target_state", state)
	var dmg := float(deltas.get("damage_dealt", 0.0))
	if dmg > 0.0:
		var was_downed := agent.downed
		agent.take_damage(dmg)
		state["hp"] = agent.hp
		emit_attacked(attacker.id if attacker != null else "", agent, dmg, was_downed)
		# M6 visual pass: a landed blow flinches the body; the felling blow plays the death
		# strip instead (held on its last frame — the body stays down).
		_play_anim("death" if agent.downed else "hurt")
	var staggered := bool(deltas.get("staggered", false))
	if staggered:
		state = CombatResolver.apply_status(state, {"kind": "stun", "magnitude": 1.0,
			"duration_ms": CombatResolver.STAGGER_STUN_MS, "applied_at_ms": now})
		if not _motion.is_empty() and String(_motion.get("kind", "")) != "knockback":
			_motion = {}   # a stagger stops a dash/charge mid-flight
	var stunned := staggered or _added_kind(deltas, "stun")
	if stunned and phase == PHASE_WINDUP:
		_interrupt("stagger" if staggered else "stun")
	var kb: Array = deltas.get("knockback", [0.0, 0.0])
	var kb_vec := Vector2(float(kb[0]), float(kb[1])) if kb.size() >= 2 else Vector2.ZERO
	if kb_vec.length() > 0.0:
		_motion = {"kind": "knockback", "dir": kb_vec.normalized(),
			"speed": kb_vec.length() * 1000.0 / float(CombatResolver.KNOCKBACK_MS),
			"remaining": kb_vec.length()}
	return deltas

## A status lands on THIS agent (zone ticks ride this). Re-stamped to THIS executor's clock
## (each executor/zone keeps its own); a stun mid-windup interrupts the cast.
func receive_status(status: Dictionary) -> void:
	if agent == null or agent.downed:
		return
	var st := status.duplicate(true)
	st["applied_at_ms"] = now_ms()
	state = CombatResolver.apply_status(state, st)
	if String(st.get("kind", "")) == "stun" and phase == PHASE_WINDUP:
		_interrupt("stun")

## ---- internals ----

func _step_fsm(now: int) -> void:
	match phase:
		PHASE_WINDUP:
			if CombatResolver.has_status(state, "stun", now):
				_interrupt("stun")   # safety net (direct hits interrupt in receive_hit)
			elif now >= _phase_end_ms:
				_begin_active(now)
		PHASE_ACTIVE:
			if String((_cast.get("ability", {}) as Dictionary).get("class", "")) == "strike":
				_melee_sweep(now)
			if now >= _phase_end_ms and _motion.is_empty():
				phase = PHASE_RECOVERY
				var rec := int((_cast.get("ability", {}) as Dictionary).get("recovery_ms", DEFAULT_RECOVERY_MS))
				_phase_end_ms = now + int(round(float(rec) / _attack_speed(now)))
		PHASE_RECOVERY:
			if now >= _phase_end_ms:
				phase = PHASE_IDLE
				_cast = {}

## The strike moment: the windup resolved (cast_finished), the ability's class decides what
## enters the world. Targeted casts re-aim HERE — the flight line/arc locks at the strike,
## and afterwards geometry alone decides (that is what makes projectiles dodgeable).
func _begin_active(now: int) -> void:
	var ability: Dictionary = _cast.get("ability", {})
	var dir: Vector2 = _cast.get("dir", Vector2.RIGHT)
	var target := _find_agent(String(_cast.get("target_id", "")))
	if target != null and String(target.room) == String(agent.room):
		var to := target.position - agent.position
		if to.length() > 0.0:
			dir = to.normalized()
			_cast["dir"] = dir
	phase = PHASE_ACTIVE
	_phase_end_ms = now + DEFAULT_ACTIVE_MS
	CombatEvents.cast_finished(agent.id, String(ability.get("id", "")))
	match String(ability.get("class", "")):
		"projectile":
			_spawn_projectile(ability, dir)
		"strike":
			_swing_hit = []
			_phase_end_ms = now + MELEE_ACTIVE_MS
			_melee_sweep(now)
		"movement":
			_begin_motion(ability, dir, now)
		_:
			# spell/effect/transform: zone effects enter the world as CombatZones; every
			# other effect self-applies (self-target abilities: frenzy buff, transform).
			var deltas := CombatResolver.apply_ability(state, state, ability,
				{"now_ms": now, "dir": [dir.x, dir.y]})
			state = deltas.get("target_state", state)
			state["hp"] = agent.hp   # the agent stays the hp authority
			for z in (deltas.get("zones", []) as Array):
				var center := target.position if target != null \
					else agent.position + dir * float(ability.get("range", 0.0))
				# Cosmetic-only (M1): carry the ability's fx id onto the zone so its glyph resolves.
				# A copied local dict — never the authoritative effect; the resolver already ran.
				var zc: Dictionary = (z as Dictionary).duplicate()
				if not zc.has("fx") and ability.has("fx"):
					zc["fx"] = ability.get("fx")
				_spawn_zone(zc, center)
			# The transform EXECUTES here (plan §M3 — M2 only flipped the fact): swap the
			# form, reload the kit-derived layers (the tactical brain re-reads the kit from
			# AbilityDB each tick; the new form's reflex rows replace the old, counts reset),
			# and announce it. Transforming into the form already worn is a no-op — the
			# authored hp_below → assume_form row must never loop a monster through itself.
			var form := String(deltas.get("transform_to", ""))
			if form != "" and form != agent.combat_form:
				agent.combat_form = form
				_load_reflexes()
				_play_anim("transform")
				# M6 visual pass: the new form's authored body sprite (assets/enemies/<form>.png)
				# becomes the bound body's look — and its resting BASE, so hurt/death strips
				# restore to the monster, never back to the shed skin. No sprite = silent no-op.
				_apply_form_sprite(form)
				var eb := _al("EventBus")
				if eb != null:
					eb.emit_event("transformed", {"agent": agent.id, "form": form})

func _begin_motion(ability: Dictionary, dir: Vector2, now: int) -> void:
	var motion: Dictionary = ability.get("motion", {})
	var dist := float(motion.get("distance", float(ability.get("range", 0.0))))
	match String(motion.get("kind", "dash")):
		"blink":
			agent.position = _clamped(agent.position + dir * dist)
		"charge":
			_motion = {"kind": "charge", "dir": dir, "speed": CHARGE_SPEED,
				"remaining": dist, "ability": ability}
		_:   # dash
			_motion = {"kind": "dash", "dir": dir, "speed": DASH_SPEED, "remaining": dist}
			var ifr := float(ability.get("i_frames", 0.0))
			if ifr > 0.0:
				state["i_frame_until_ms"] = now + int(round(ifr * 1000.0))

func _step_motion(dt: float, now: int) -> void:
	if _motion.is_empty():
		return
	var kind := String(_motion.get("kind", ""))
	var speed := float(_motion.get("speed", 0.0))
	if kind != "knockback":
		speed *= _move_factor(now)   # slow bites movement skills, never a shove
	var dir: Vector2 = _motion.get("dir", Vector2.RIGHT)
	var step_len := minf(speed * dt, float(_motion.get("remaining", 0.0)))
	agent.position = _move_collide(dir * step_len)
	_motion["remaining"] = float(_motion.get("remaining", 0.0)) - step_len
	if kind == "charge":
		var victim := _first_contact()
		if victim != null:
			route_hit(agent, victim, _motion.get("ability", {}), dir)
			_motion = {}
			return
	if float(_motion.get("remaining", 0.0)) <= 0.0001:
		_motion = {}

## The tactical layer's movement channel (plan §M3): deliberate walks at COMBAT_WALK_SPEED.
## Movement SKILLS and knockback (_motion) always win over a walk; a stun roots everything;
## the reflex dodge burst overrides deliberate steering in ANY phase (survival first), while
## ordinary steering is rooted during windup/active (casting plants the feet).
func _step_steering(dt: float, now: int) -> void:
	if not _motion.is_empty():
		return
	if CombatResolver.has_status(state, "stun", now):
		return
	if not _burst.is_empty():
		if now < int(_burst.get("until_ms", 0)):
			var bdir: Vector2 = _burst.get("dir", Vector2.RIGHT)
			agent.position = _move_collide(bdir * REFLEX_BURST_SPEED * _move_factor(now) * dt)
			return
		_burst = {}
	if phase == PHASE_WINDUP or phase == PHASE_ACTIVE:
		return
	if steering.is_empty():
		return
	var speed := COMBAT_WALK_SPEED * _move_factor(now)
	match String(steering.get("kind", "")):
		"pursue":
			var t := _find_agent(String(steering.get("target", "")))
			if t == null or String(t.room) != String(agent.room):
				return
			var to := t.position - agent.position
			var gap := to.length() - radius_of(t.id) - float(steering.get("stop_at", 0.0))
			if gap <= 0.0 or to.length() <= 0.001:
				return
			agent.position = _move_collide(to.normalized() * minf(speed * dt, gap))
		"strafe":
			var t2 := _find_agent(String(steering.get("target", "")))
			if t2 == null or String(t2.room) != String(agent.room):
				return
			var to2 := t2.position - agent.position
			if to2.length() <= 0.001:
				return
			var perp := Vector2(-to2.y, to2.x).normalized() * signf(float(steering.get("sign", 1.0)))
			agent.position = _move_collide(perp * speed * dt)
		"back_away":
			var from_v: Variant = steering.get("from", null)
			if not (from_v is Vector2):
				return
			var away := agent.position - (from_v as Vector2)
			if away.length() <= 0.001:
				away = Vector2.RIGHT
			agent.position = _move_collide(away.normalized() * speed * dt)
		"goto":
			var pos_v: Variant = steering.get("pos", null)
			if not (pos_v is Vector2):
				return
			var to3 := (pos_v as Vector2) - agent.position
			if to3.length() <= float(steering.get("arrive", 4.0)):
				return
			agent.position = _move_collide(to3.normalized() * minf(speed * dt, to3.length()))
		_:
			pass

func set_steering(directive: Dictionary) -> void:
	steering = directive

## Is this art inside its cost-refusal retry window (the tactics layer must skip it this
## selection round)? Never consulted by try_cast itself — a direct caller (the player's input
## path, a reflex, a parked GM cast) always gets the provider's real answer.
func cost_suppressed(ability_id: String, now: int) -> bool:
	return now < int(_cost_refused.get(ability_id, -1))

## ---- M3 reflex machinery (data rows in, scheduled reactions out — all on THIS clock) ----

## (Re)load the combat_form's authored reflex rows; fired counts reset with them (a transform
## hands the fight to a NEW rule set).
func _load_reflexes() -> void:
	var db := _al("AbilityDB")
	var rows: Variant = (db.form_def(agent.combat_form) as Dictionary).get("reflexes", []) \
		if db != null and agent != null else []
	_apply_reflex_rows(rows if rows is Array else [])

## Replace this executor's reflex rows in place (tests pin behavior through here; the M3+ LLM
## add/edit data channel of the C design will author through the same seam).
func set_reflex_rules(rules: Array) -> void:
	_apply_reflex_rows(rules.duplicate(true))

func _apply_reflex_rows(rows: Array) -> void:
	_reflex_rules = rows
	_reflex_fired = {}
	_pending_reflex = []
	_cd_watch = []
	_cd_prev = {}
	for r_v in _reflex_rules:
		if typeof(r_v) != TYPE_DICTIONARY:
			continue
		var when_v: Variant = (r_v as Dictionary).get("when", {})
		if when_v is Dictionary and String((when_v as Dictionary).get("kind", "")) == "cooldown_ready":
			_cd_watch.append(String((when_v as Dictionary).get("ability", "")))

## An already-perceived (or self-generated: band_entered, cooldown_ready) reflex event —
## evaluate the rules NOW on this clock and schedule whatever is due.
func on_reflex_event(event: Dictionary) -> void:
	if _reflex_rules.is_empty() or agent == null or agent.downed:
		return
	_schedule_reactions(
		ReflexRules.evaluate(_reflex_rules, event, _reflex_self_state(), now_ms(), _reflex_fired), event)

## The bare per-frame evaluation (event = {}): state-driven triggers (hp_below) fire here.
func _evaluate_state_reflexes(now: int) -> void:
	if _reflex_rules.is_empty():
		return
	_schedule_reactions(
		ReflexRules.evaluate(_reflex_rules, {}, _reflex_self_state(), now, _reflex_fired), {})

## cooldown_ready is an EDGE (not-ready -> ready), watched only for abilities the rules name.
func _watch_cooldowns(now: int) -> void:
	for a_v in _cd_watch:
		var a := String(a_v)
		var ready := CombatResolver.ledger_ready(ledger, a, now)
		if ready and not bool(_cd_prev.get(a, true)):
			on_reflex_event({"kind": "cooldown_ready", "ability": a})
		_cd_prev[a] = ready

func _reflex_self_state() -> Dictionary:
	return {"hp_frac": (agent.hp / agent.max_hp) if agent != null and agent.max_hp > 0.0 else 1.0}

## Scheduling is the moment a rule FIRES: the fired count increments here (max_fires is
## enforced by ReflexRules against this ledger), and the threat (the telegraph's caster) is
## captured so a later dodge knows what to dodge.
func _schedule_reactions(due: Array, event: Dictionary) -> void:
	for r_v in due:
		var r: Dictionary = r_v
		var idx := int(r.get("rule_index", -1))
		_reflex_fired[idx] = int(_reflex_fired.get(idx, 0)) + 1
		var p := r.duplicate(true)
		p["threat"] = String(event.get("caster", ""))
		_pending_reflex.append(p)

## Execute reactions whose fire_at_ms has come due. A cast refused for being busy/stunned
## retries next frame (the reaction stands until the body can obey); any other refusal drops it.
func _run_pending_reflexes(now: int) -> void:
	if _pending_reflex.is_empty():
		return
	var keep: Array = []
	for p_v in _pending_reflex:
		var p: Dictionary = p_v
		if now < int(p.get("fire_at_ms", 0)) or not _execute_reflex(p, now):
			keep.append(p)
	_pending_reflex = keep

func _execute_reflex(p: Dictionary, now: int) -> bool:
	var doo: Dictionary = p.get("do", {}) if p.get("do") is Dictionary else {}
	match String(doo.get("kind", "")):
		"cast":
			# A transform reflex whose destination is the form ALREADY worn is consumed unfired:
			# the new form's own reflex table takes over after a swap, so a monster row like
			# `hp_below → cast assume_form` would otherwise re-cast into itself every trigger —
			# a 1.2s self-stun loop (final-review #2). Data fixed the shipped row; this keeps
			# any future-authored form safe by construction.
			var gdb := _al("AbilityDB")
			if gdb != null:
				var adef: Dictionary = gdb.ability_for(String(doo.get("ability", "")))
				if String(adef.get("class", "")) == "transform":
					for eff_v in (adef.get("effects", []) as Array):
						var eff: Dictionary = eff_v if eff_v is Dictionary else {}
						if String(eff.get("kind", "")) == "transform" \
								and String(eff.get("form", "")) == String(agent.combat_form):
							return true
			var res := try_cast(String(doo.get("ability", "")), _current_target_id())
			if bool(res.get("ok", false)):
				return true
			var reason := String(res.get("reason", ""))
			return not (reason == "busy" or reason == "stunned")
		"dodge":
			var away := Vector2.RIGHT
			var threat := _find_agent(String(p.get("threat", "")))
			if threat != null and String(threat.room) == String(agent.room):
				var v := agent.position - threat.position
				if v.length() > 0.001:
					away = v.normalized()
			var dir := away
			if String(doo.get("dir", "side")) != "away":
				dir = Vector2(-away.y, away.x) * _dodge_sign
				_dodge_sign = -_dodge_sign
			var db := _al("AbilityDB")
			if db != null and (db.kit_for(agent.combat_form) as Array).has("dash") \
					and bool(try_cast("dash", "", dir).get("ok", false)):
				return true
			_burst = {"dir": dir, "until_ms": now + REFLEX_BURST_MS}
			return true
		"style":
			var s := String(doo.get("style", ""))
			if ActionCommit.ENGAGE_STYLES.has(s):
				if not agent.combat_intent.is_empty():
					agent.combat_intent["style"] = s   # override the mask in place
				else:
					style_override = s
			return true
		"flee":
			reflex_flee = true
			return true
	return true

## The agent this executor is fighting right now: the intent's target, else the last attacker.
func _current_target_id() -> String:
	var t := String(agent.combat_intent.get("target", "")) if agent != null else ""
	return t if t != "" else last_attacker_id

## True when this agent took OR witnessed a landed hit within the window (defensive counters).
func recent_combat_hit(now: int, window_ms: int = 2000) -> bool:
	return now - last_hit_ms <= window_ms or now - _last_seen_hit_ms <= window_ms

## The reflex channel's ear: raw EventBus, FILTERED through the ONE shared perceiver gate
## (Perception.can_perceive — same room + within THIS agent's vision_r of where it happened),
## exactly like Stimulus's witness fan. Own casts are never events to oneself.
func _on_world_event(ev: Dictionary) -> void:
	if agent == null or agent.downed:
		return
	var d: Dictionary = ev.get("data", {}) if ev.get("data") is Dictionary else {}
	match String(ev.get("type", "")):
		"ability_cast_started":
			if _reflex_rules.is_empty():
				return
			var caster_id := String(d.get("caster", ""))
			if caster_id == agent.id:
				return
			var caster := _find_agent(caster_id)
			if caster == null or not Perception.can_perceive(agent, caster.room, caster.position):
				return
			var db := _al("AbilityDB")
			var klass := String((db.ability_for(String(d.get("ability", ""))) as Dictionary).get("class", "")) \
				if db != null else ""
			on_reflex_event({"kind": "telegraph", "ability": String(d.get("ability", "")),
				"class": klass, "at_me": String(d.get("target", "")) == agent.id, "caster": caster_id})
		"agent_attacked":
			if String(d.get("target", "")) == agent.id:
				_last_seen_hit_ms = now_ms()   # felt on your own body — no vision gate
				return
			var victim := _find_agent(String(d.get("target", "")))
			if victim != null and Perception.can_perceive(agent, victim.room, victim.position):
				_last_seen_hit_ms = now_ms()
		"agent_downed":
			if _reflex_rules.is_empty():
				return
			var fallen_id := String(d.get("target", ""))
			if fallen_id == agent.id:
				return
			var fallen := _find_agent(fallen_id)
			if fallen == null or not Perception.can_perceive(agent, fallen.room, fallen.position):
				return
			# No factions in the engine: the one body this agent is FIGHTING is its only
			# non-ally; anyone else falling reads as ally_downed to the reflex data.
			if fallen_id == _current_target_id():
				return
			on_reflex_event({"kind": "ally_downed", "agent": fallen_id})

## Collision-safe displacement: a real physics body slides against the world's colliders;
## a body-less (headless/test) executor clamps inside the world rect.
func _move_collide(delta_vec: Vector2) -> Vector2:
	if body != null and body is CharacterBody2D and body.is_inside_tree():
		(body as CharacterBody2D).move_and_collide(delta_vec)
		return body.global_position
	return _clamped(agent.position + delta_vec)

func _clamped(p: Vector2) -> Vector2:
	return Vector2(
		clampf(p.x, world_rect.position.x, world_rect.end.x),
		clampf(p.y, world_rect.position.y, world_rect.end.y))

## Advance statuses on the executor clock: expiry pruning + dot ticks. Dot damage lands
## through Agent.take_damage like every other point of damage (events/EndGame intact); the
## actor is the opaque "dot" — no shipped M2 ability authors a dot, doctored data only.
func _advance_statuses(now: int) -> void:
	var res := CombatResolver.tick_statuses(state, now)
	state = res.get("state", state)
	var dot := float(res.get("dot_damage", 0.0))
	if dot > 0.0 and not agent.downed:
		var was_downed := agent.downed
		agent.take_damage(dot)
		state["hp"] = agent.hp
		emit_attacked("dot", agent, dot, was_downed)

## The live melee arc: every non-owner body within reach and inside the swing's ~120° arc is
## hit ONCE per swing (_swing_hit dedup); i-frames/shields are the target resolver's call.
func _melee_sweep(_now: int) -> void:
	var ability: Dictionary = _cast.get("ability", {})
	var dir: Vector2 = _cast.get("dir", Vector2.RIGHT)
	var reach := float(ability.get("range", 0.0))
	for other_v in _agents_in_room():
		var other: Agent = other_v
		if other == agent or other.downed or _swing_hit.has(other.id):
			continue
		var to := other.position - agent.position
		if to.length() > reach + radius_of(other.id):
			continue
		if to.length() > 0.001 and dir.dot(to.normalized()) < MELEE_ARC_COS:
			continue
		_swing_hit.append(other.id)
		route_hit(agent, other, ability, to.normalized() if to.length() > 0.001 else dir)

## The nearest non-owner body in charge-contact range (deterministic: nearest, not dict order).
func _first_contact() -> Agent:
	var best: Agent = null
	var best_d := INF
	for other_v in _agents_in_room():
		var other: Agent = other_v
		if other == agent or other.downed:
			continue
		var d := agent.position.distance_to(other.position)
		if d <= hurtbox_radius + radius_of(other.id) and d < best_d:
			best = other
			best_d = d
	return best

func _spawn_projectile(ability: Dictionary, dir: Vector2) -> void:
	var p: CombatProjectile = _instance_scene("res://scenes/CombatProjectile.tscn")
	if p == null:
		p = CombatProjectile.new()
	p.setup(agent, ability, agent.position, dir)
	add_child(p)
	projectiles.append(p)

func _spawn_zone(effect: Dictionary, center: Vector2) -> void:
	var z: CombatZone = _instance_scene("res://scenes/CombatZone.tscn")
	if z == null:
		z = CombatZone.new()
	z.setup(agent, effect, center)
	add_child(z)
	zones.append(z)

func _instance_scene(path: String) -> Node:
	var ps := load(path)
	return (ps as PackedScene).instantiate() if ps is PackedScene else null

## Step my spawned projectiles/zones (single stepping authority) and free the spent ones.
func _step_spawned(dt: float) -> void:
	for p in projectiles.duplicate():
		p.step(dt)
		if not p.alive:
			projectiles.erase(p)
			_free_spawned(p)
	for z in zones.duplicate():
		z.step(dt)
		if not z.alive:
			zones.erase(z)
			_free_spawned(z)

func _free_spawned(n: Node) -> void:
	if n.is_inside_tree():
		n.queue_free()
	else:
		n.free()

func _interrupt(reason: String) -> void:
	CombatEvents.cast_interrupted(agent.id, String((_cast.get("ability", {}) as Dictionary).get("id", "")), reason)
	phase = PHASE_IDLE
	_cast = {}

## Animation hook — the M6 first visual pass. DEFENSIVE at every step (no body, no sprite, no
## authored strip file = silent no-op), purely cosmetic (touches only the body's sprite node,
## never agent/executor state), and stepped on THIS executor's deterministic clock — so the
## headless sims, which bind no bodies, are byte-identical with it in place.
##
## Two backends:
##   * AnimatedSprite2D bodies (the player's klein rig): play the cue when its SpriteFrames
##     authored an animation of that name (Player.gd's own walk-anim loop keeps ultimate
##     authority; this is a best-effort nudge).
##   * Sprite2D bodies (NPC.tscn): swap in the form's 8-frame strip texture
##     (assets/anim/<combat_form>_<suffix>.png, ANIM_STRIPS naming) and flip its frames at
##     STRIP_FPS via _step_strip; when the strip finishes, the sprite's captured resting look is
##     restored — except a death strip, which HOLDS its final frame (the body stays down).
func _play_anim(anim: String) -> void:
	if anim == "" or body == null or agent == null:
		return
	var sp := _body_sprite()
	if sp == null:
		return
	if sp is AnimatedSprite2D:
		var frames: SpriteFrames = (sp as AnimatedSprite2D).sprite_frames
		if frames != null and frames.has_animation(anim):
			(sp as AnimatedSprite2D).play(anim)
		return
	var suffix := String(ANIM_STRIPS.get(anim, ""))
	if suffix == "" or agent.combat_form == "":
		return
	var path := "%s%s_%s.png" % [ANIM_DIR, agent.combat_form, suffix]
	if not ResourceLoader.exists(path):
		return
	var tex: Texture2D = load(path)
	if tex == null:
		return
	var s := sp as Sprite2D
	_capture_sprite_base(s)
	s.texture = tex
	s.hframes = STRIP_FRAMES
	s.vframes = 1
	s.frame = 0
	s.scale = Vector2.ONE * strip_scale_for(tex)
	s.offset = strip_offset_for(tex)
	_strip = {"sprite": s, "start_ms": now_ms(), "hold_last": anim == "death"}

## P3 combat readability: the strip's on-screen scale. The gen sheets are 1536x1024 with the
## FIGURE occupying only a ~400px band of each otherwise-transparent 192x1024 cell — the old
## rule (scale the CELL height to 42px) rendered the monster as a ~8px-wide sliver on every
## anim cue. Scale by the sheet's USED (non-transparent) rect instead, so the FIGURE lands at
## the same on-screen height as the revealed-form standee it animates (FORM_SPRITE_TARGET_H).
## Measured once per strip texture (an Image decode) and cached statically; an unreadable or
## fully-opaque sheet degrades to the full cell height — never a divide-by-zero. Cosmetic only:
## headless sims bind no bodies, so _play_anim (the one caller) never reaches here.
static var _strip_scale_cache: Dictionary = {}

static func strip_scale_for(tex: Texture2D) -> float:
	var key := tex.resource_path if tex.resource_path != "" else str(tex.get_instance_id())
	if _strip_scale_cache.has(key):
		return float(_strip_scale_cache[key])
	var fig_h := maxf(1.0, float(tex.get_height()))
	var img := tex.get_image()
	if img != null:
		if img.is_compressed():
			img.decompress()
		var used := img.get_used_rect()
		if used.size.y > 0:
			fig_h = float(used.size.y)
	var s := FORM_SPRITE_TARGET_H / fig_h
	_strip_scale_cache[key] = s
	return s

## N6 (the offset half of the same readability rule): where the FIGURE sits inside the cell.
## bieber's sheet authors the figure band roughly centered, but the N6 drops (wren_predator /
## mack_beast / neil_monster / beyond_hunter) author it at the BOTTOM of the 1024px cell — a
## center-mounted Sprite2D would teleport the monster ~160px below its standee on every swing.
## Offset the sprite so the used-rect band's vertical CENTER lands on the body position (which
## is also where the standee's figure center sits — both render 64px tall). Vertical only: the
## per-frame horizontal drift IS the authored motion. Texture-local px (Sprite2D.offset scales
## with the node), cached per strip; a centered sheet (bieber) yields a ~0 offset, so nothing
## already-placed moves. Cosmetic only — headless sims bind no bodies.
static var _strip_offset_cache: Dictionary = {}

static func strip_offset_for(tex: Texture2D) -> Vector2:
	var key := tex.resource_path if tex.resource_path != "" else str(tex.get_instance_id())
	if _strip_offset_cache.has(key):
		return _strip_offset_cache[key]
	var off := Vector2.ZERO
	var img := tex.get_image()
	if img != null:
		if img.is_compressed():
			img.decompress()
		var used := img.get_used_rect()
		if used.size.y > 0:
			var fig_center_y := float(used.position.y) + float(used.size.y) * 0.5
			off = Vector2(0.0, float(tex.get_height()) * 0.5 - fig_center_y)
	_strip_offset_cache[key] = off
	return off

## Advance the strip in flight on the executor clock; restore the resting look when it ends
## (death holds its last frame instead).
func _step_strip(now: int) -> void:
	if _strip.is_empty():
		return
	var s: Sprite2D = _strip.get("sprite") if is_instance_valid(_strip.get("sprite")) else null
	if s == null:
		_strip = {}
		return
	var f := int(floor(float(now - int(_strip.get("start_ms", 0))) / 1000.0 * STRIP_FPS))
	if f < STRIP_FRAMES:
		s.frame = maxi(0, f)
		return
	if bool(_strip.get("hold_last", false)):
		s.frame = STRIP_FRAMES - 1
		return
	_restore_sprite_base(s)
	_strip = {}

## The bound body's first sprite node (NPC.tscn carries a Sprite2D, Player.tscn an
## AnimatedSprite2D) — null when the body has neither (harness stubs).
func _body_sprite() -> Node:
	if body == null:
		return null
	for child in body.get_children():
		if child is AnimatedSprite2D or child is Sprite2D:
			return child
	return null

## Capture the sprite's resting look ONCE (first strip on this body); transform re-bases it.
func _capture_sprite_base(s: Sprite2D) -> void:
	if not _sprite_base.is_empty():
		return
	_sprite_base = {"texture": s.texture, "hframes": s.hframes, "vframes": s.vframes,
		"frame": s.frame, "scale": s.scale, "offset": s.offset}

func _restore_sprite_base(s: Sprite2D) -> void:
	if _sprite_base.is_empty():
		return
	s.texture = _sprite_base.get("texture")
	s.hframes = int(_sprite_base.get("hframes", 1))
	s.vframes = int(_sprite_base.get("vframes", 1))
	s.frame = int(_sprite_base.get("frame", 0))
	s.scale = _sprite_base.get("scale", Vector2.ONE)
	s.offset = _sprite_base.get("offset", Vector2.ZERO)

## N4 — the ONE form->art resolution path, shared by the mid-fight mask-drop swap
## (_apply_form_sprite) AND the body-bind skin (NPC._apply_sprite), so a pre-formed monster and a
## mid-fight reveal wear the SAME painting through the SAME rules:
##   1. the DATA alias: an explicit `sprite` path on the form's combat_forms.json row wins, if the
##      file exists (the seam for forms whose own painting isn't done — nighthawk_pursuer wears the
##      nighthawk captain's standee until painted; data, never an engine id branch);
##   2. else the filename CONVENTION assets/enemies/<form>.png, if it exists;
##   3. else "" — the caller keeps its current look (the character-art/placeholder ladder).
## Static + defensive (only ever returns a path ResourceLoader can open); the AbilityDB autoload is
## reached via the /root lookup so the resolver also works under the -s harnesses.
## N6 (B1): pure builders that already HOLD the form's def (CastCodex walks a caller-supplied
## forms dict) pass it as `def_override` — the same ladder runs on their data, no autoload
## round-trip, no second resolution path. Empty (the default) keeps the AbilityDB lookup.
static func resolve_form_sprite_path(form: String, def_override: Dictionary = {}) -> String:
	if form == "":
		return ""
	var def := def_override
	if def.is_empty():
		var ml := Engine.get_main_loop()
		var adb: Node = null
		if ml is SceneTree:
			adb = (ml as SceneTree).root.get_node_or_null("AbilityDB")
		def = adb.form_def(form) if adb != null else {}
	var explicit := String(def.get("sprite", ""))
	if explicit != "" and ResourceLoader.exists(explicit):
		return explicit
	var conv := "%s%s.png" % [FORM_SPRITE_DIR, form]
	if ResourceLoader.exists(conv):
		return conv
	return ""

## The transform's visible half (M6): the new form's static body sprite (the shared
## resolve_form_sprite_path — the enemies/<form>.png convention or its DATA alias) replaces the
## body's look AND its captured base, so every later strip-restore lands on the revealed shape.
## Sprite2D bodies only; no authored art = no-op.
func _apply_form_sprite(form: String) -> void:
	var sp := _body_sprite()
	if not (sp is Sprite2D) or form == "":
		return
	var path := resolve_form_sprite_path(form)
	if path == "":
		return
	var tex: Texture2D = load(path)
	if tex == null:
		return
	var s := sp as Sprite2D
	_strip = {}   # the reveal supersedes any flourish mid-flight
	var new_scale := Vector2.ONE * (FORM_SPRITE_TARGET_H / maxf(1.0, float(tex.get_height())))
	s.texture = tex
	s.hframes = 1
	s.vframes = 1
	s.frame = 0
	s.scale = new_scale
	s.offset = Vector2.ZERO
	_sprite_base = {"texture": tex, "hframes": 1, "vframes": 1, "frame": 0, "scale": new_scale,
		"offset": Vector2.ZERO}

## In combat the DATA stays authoritative: motions write agent.position; the body follows.
func _sync_body() -> void:
	if body == null:
		return
	if body.is_inside_tree():
		body.global_position = agent.position
	else:
		body.position = agent.position

## Every fighting body gets a Hurtbox Area2D child sized from its existing collision
## (HeartBeast hitbox/hurtbox pattern). DETECTION stays geometric (the radius feeds the
## resolver-routed overlap checks) so headless and live runs are identical; the node marks
## the body for future editor/visual wiring and is reused if combat re-enters.
func _attach_hurtbox() -> void:
	if _hurtbox != null and is_instance_valid(_hurtbox):
		return   # already attached (a re-bind must not stack a second hurtbox)
	if body.has_node("CombatHurtbox"):
		_hurtbox = body.get_node("CombatHurtbox")
		var existing := _hurtbox.get_node_or_null("CollisionShape2D")
		if existing != null and existing is CollisionShape2D and (existing as CollisionShape2D).shape is CircleShape2D:
			hurtbox_radius = ((existing as CollisionShape2D).shape as CircleShape2D).radius
		return
	_hurtbox = Area2D.new()
	_hurtbox.name = "CombatHurtbox"
	_hurtbox.monitoring = false
	_hurtbox.monitorable = false
	var shape := CollisionShape2D.new()
	shape.name = "CollisionShape2D"
	var circle := CircleShape2D.new()
	circle.radius = _body_radius()
	shape.shape = circle
	_hurtbox.add_child(shape)
	# The player's executor binds DURING Player.tscn's own tree entry (M5), when the body is
	# still busy setting up children and a synchronous add_child hard-fails (and the orphaned
	# Area2D leaks its RID) — defer the attach there. The live NPC path (body ready long ago)
	# keeps the synchronous attach, so its hurtbox is inspectable the same frame as ever.
	# Detection never depended on the node either way — it is geometric off hurtbox_radius,
	# which is already set — so a frame-late attach changes nothing observable.
	if body.is_node_ready():
		body.add_child(_hurtbox)
	else:
		body.add_child.call_deferred(_hurtbox)
	hurtbox_radius = circle.radius

## Size from the body's existing collision shape (rect half-extent, circle/capsule radius).
func _body_radius() -> float:
	for child in body.get_children():
		if child is CollisionShape2D and (child as CollisionShape2D).shape != null:
			var sh: Shape2D = (child as CollisionShape2D).shape
			if sh is RectangleShape2D:
				var size: Vector2 = (sh as RectangleShape2D).size
				return maxf(size.x, size.y) / 2.0
			if sh is CircleShape2D:
				return (sh as CircleShape2D).radius
			if sh is CapsuleShape2D:
				return (sh as CapsuleShape2D).radius
	return DEFAULT_HURTBOX_R

## Frenzy (attack_speed buff) compresses windup/recovery; never below authored 1x pace.
func _attack_speed(now: int) -> float:
	return maxf(1.0, CombatResolver.status_magnitude(state, "frenzy", now))

## Slow statuses scale movement-skill speed (slow 0.5 -> half pace), floored at 10%.
func _move_factor(now: int) -> float:
	return clampf(1.0 - CombatResolver.status_magnitude(state, "slow", now), 0.1, 1.0)

func _agents_in_room() -> Array:
	var reg := _al("Agents")
	if reg == null or agent == null:
		return []
	var out: Array = []
	for a in reg.all():
		if String(a.room) == String(agent.room):
			out.append(a)
	return out

func _find_agent(id: String) -> Agent:
	if id == "":
		return null
	var reg := _al("Agents")
	return reg.get_agent(id) if reg != null else null

## No executor on the target (e.g. the player proxy until M5): resolve against a transient
## state — damage/downing/events still land through the same pipes; statuses have nowhere
## to live and are dropped (documented M2 limit; M5 gives the player a real combat node).
static func land_fallback_hit(attacker: Agent, target: Agent, ability: Dictionary, dir: Vector2) -> Dictionary:
	if target == null or target.downed:
		return {}
	var tstate := {"hp": target.hp, "max_hp": target.max_hp, "statuses": [],
		"poise": 0.0, "i_frame_until_ms": 0}
	var deltas := CombatResolver.apply_ability({}, tstate, ability, {"now_ms": 0, "dir": [dir.x, dir.y]})
	var dmg := float(deltas.get("damage_dealt", 0.0))
	if dmg > 0.0:
		var was_downed := target.downed
		target.take_damage(dmg)
		emit_attacked(attacker.id if attacker != null else "", target, dmg, was_downed)
	return deltas

## The ONE emitter of a landed strike: the existing `agent_attacked` shape
## {actor, target, damage, target_hp, downed} (Stimulus/witnessing/panels/PlayLog all key on
## it) + `agent_downed` {actor, target} exactly once, the moment a target is felled.
static func emit_attacked(actor_id: String, target: Agent, damage: float, was_downed: bool) -> void:
	# The static hit ledger (M3): protect-mode's cheap "who last damaged the ward" lookup.
	# Only real agents register — "dot" is an attribution label, not a threat to interpose.
	if actor_id != "" and actor_id != "dot":
		_last_attacker[target.id] = actor_id
	var eb := _al_static("EventBus")
	if eb == null:
		return
	eb.emit_event("agent_attacked", {"actor": actor_id, "target": target.id,
		"damage": damage, "target_hp": target.hp, "downed": target.downed})
	if target.downed and not was_downed:
		eb.emit_event("agent_downed", {"actor": actor_id, "target": target.id})

static func _added_kind(deltas: Dictionary, kind: String) -> bool:
	for st in (deltas.get("statuses_added", []) as Array):
		if typeof(st) == TYPE_DICTIONARY and String((st as Dictionary).get("kind", "")) == kind:
			return true
	return false

## Autoload lookup via /root (class_name scripts can't reference autoload globals under the
## headless -s harness's parse ordering), tolerant of the autoload being absent entirely.
func _al(autoload_name: String) -> Node:
	return _al_static(autoload_name)

static func _al_static(autoload_name: String) -> Node:
	var ml := Engine.get_main_loop()
	if ml == null or not (ml is SceneTree):
		return null
	return (ml as SceneTree).root.get_node_or_null(autoload_name)

func _notification(what: int) -> void:
	if what == NOTIFICATION_PREDELETE:
		# N6 (asset polish, probe-caught): a downing blow drops in_combat and the body FREES its
		# executor (NPC._physics_process) — an executor dying with a NON-hold strip still in
		# flight must not freeze the corpse on a mid-swing frame; the captured resting look
		# (the standee) is restored. A HOLD strip (death, hold_last) stays exactly as it is:
		# the held death frame IS the felled body's resting look (bieber's corpse).
		if not _strip.is_empty() and not bool(_strip.get("hold_last", false)):
			var strip_sprite: Variant = _strip.get("sprite")
			if strip_sprite is Sprite2D and is_instance_valid(strip_sprite):
				_restore_sprite_base(strip_sprite as Sprite2D)
			_strip = {}
		_orphan_survivors()
		# A hurtbox that never landed on the body (deferred attach still pending when this
		# executor dies — the M5 bind-during-scene-setup path) must not leak its Area2D RID;
		# one already IN the tree stays on the body for reuse, exactly as before.
		if _hurtbox != null and is_instance_valid(_hurtbox) and not _hurtbox.is_inside_tree():
			_hurtbox.free()
		var eb := _al_static("EventBus")
		if eb != null and eb.event_logged.is_connected(_on_world_event):
			eb.event_logged.disconnect(_on_world_event)
		if agent != null and _by_agent.get(agent.id, null) == self:
			_by_agent.erase(agent.id)

## ---- orphaned rounds/zones (review M2 #2) ----
## An executor dies when its agent leaves combat (incl. downing), but a fired round or a
## planted zone has already LEFT the body — it must not evaporate mid-flight. Survivors are
## reparented onto a neutral room-level stepper created on demand.

## Neutral stepper for spawned nodes that outlived their executor. Steps itself on live
## physics frames; headless harnesses drive it with CombatExecutor.step_orphans(dt).
class Orphanage:
	extends Node
	var spawned: Array = []

	func _physics_process(delta: float) -> void:
		step(delta)

	func step(dt: float) -> void:
		for n in spawned.duplicate():
			n.step(dt)
			if not n.alive:
				spawned.erase(n)
				if n.is_inside_tree():
					n.queue_free()
				else:
					n.free()

func _orphan_survivors() -> void:
	var survivors: Array = []
	for n_v in projectiles + zones:
		if is_instance_valid(n_v) and n_v.alive:
			survivors.append(n_v)
	projectiles = []
	zones = []
	if survivors.is_empty():
		return
	var o := _orphanage(true)
	if o == null:
		return
	for s in survivors:
		var parent := (s as Node).get_parent()
		if parent != null:
			parent.remove_child(s)
		o.add_child(s)
		o.spawned.append(s)

static func _orphanage(create: bool) -> Node:
	var ml := Engine.get_main_loop()
	if ml == null or not (ml is SceneTree):
		return null
	var root := (ml as SceneTree).root
	var o := root.get_node_or_null("CombatOrphans")
	if o == null and create:
		o = Orphanage.new()
		o.name = "CombatOrphans"
		root.add_child(o)
	return o

## Advance orphaned rounds/zones with a fixed dt (headless harnesses; the live tree steps
## them via the orphanage's own _physics_process).
static func step_orphans(dt: float) -> void:
	var o := _orphanage(false)
	if o != null:
		o.step(dt)

static func orphan_count() -> int:
	var o := _orphanage(false)
	return (o.spawned as Array).size() if o != null else 0
