class_name ActionCommit
extends RefCounted
## Deterministically applies ONE already-validated action to its agent and the world.
## Returns a small outcome Dictionary describing what happened (logged to the EventBus by
## the runtime). This is the only place agents change world state. For the slice, verbs
## that belong to later systems (combat, ritual countdown, sabotage economy) are recorded
## as memory + outcome here and given their full effects in their own plans.

## Named ritual/world sites in world coordinates, anchored to the canonical map via MapProjection
## so they stay true to the map. const can't call a static fn, so this is a static var.
static var SITES: Dictionary = {
	"iron_cross_warehouse": MapProjection.map_to_world(MapProjection.WAREHOUSE_MAP),
	# The cathedral rite site, INSIDE CathedralCrypt.tscn (local space). It is the only cathedral rite
	# site — there is deliberately no City-surface chapel site, so the only way to work the rite is to
	# descend through the cathedral's portals to the crypt (tingen_scene_graph_design.md §1).
	"crypt_altar": Vector2(691, 600),
}

## The room (RoomGraph) each site lives in; absent -> the city room. A site's SITES position is its
## LOCAL position within that room.
static var SITE_ROOM: Dictionary = {
	"iron_cross_warehouse": "city",
	"crypt_altar": "cathedral_crypt",
}

static func _site_room(site_name: String) -> String:
	return String(SITE_ROOM.get(site_name, RoomGraph.DEFAULT_ROOM))

## Named, navigable, NON-rite locations — e.g. the cult's supply cache where the offerings are stocked.
## Kept separate from SITES so move_to can target them and they appear as valid targets, WITHOUT
## _near_any_rite_site ever mistaking the cache for the altar. Populated at runtime (CitySummoning
## registers the cache); name -> { "pos": Vector2 (local to its room), "room": String }.
static var NAV_SITES: Dictionary = {}

## Register/replace a navigable location (used by the demo bootstrap; idempotent).
static func set_nav_site(name: String, pos: Vector2, room: String) -> void:
	NAV_SITES[name] = {"pos": pos, "room": room}

static func clear_nav_sites() -> void:
	NAV_SITES.clear()

## Every named place an agent can move_to right now: rite sites + navigable caches.
static func location_names() -> Array:
	var out: Array = SITES.keys()
	out.append_array(NAV_SITES.keys())
	return out

## How close (px) an agent must stand to the rite site for its ritual work to actually bite.
## Shared with AmbientSidecar so the live brain only proposes the rite when committing it counts.
const RITE_RADIUS: float = 80.0

## How close (px) an agent must stand to a ground item to pick it up.
const GATHER_RADIUS: float = 80.0

## How close (px) an agent must be to a portal's from_pos before it crosses. Deliberately small (a
## doorway, not a full stride): tying it to the movement step would teleport the agent across the
## portal up to one whole step early, so the body would vanish well short of the visible door. With
## this tight radius the cult walks onto the doorway and crosses there, like the player's door.
const PORTAL_CROSS_RADIUS: float = 40.0
## Fallback reach for drawing from the cult's stash: when nothing is within GATHER_RADIUS, a gather
## still pulls the nearest matching pile within this wider radius (so a clustered supply cache reliably
## depletes even if the cultist isn't standing exactly on it), but NOT from clear across a large room.
const STASH_RADIUS: float = 700.0

## How close (px) an attacker must stand to its target for a strike to connect; a swing from
## farther off is flavor only. Mirrors how the rite is proximity-gated.
const ATTACK_RADIUS: float = 64.0
## Flat damage per connecting strike — deterministic, no RNG/crit (Yumina's ability model).
## About three strikes fell a full-HP agent.
const ATTACK_DAMAGE: float = 34.0
## How close (px) two agents must be for talk to carry — a rumor spreads face-to-face, not across
## the district. Roomy (wider than ATTACK_RADIUS) since conversation reaches farther than a blade.
const TALK_RADIUS: float = 96.0

## The legal engage styles (combat plan §M1) — the L2 tactical layer's masks. An engage that
## names none (or an unknown one) commits with the default; the intent stays schema-simple for
## the LLM (style is an OPTIONAL arg).
const ENGAGE_STYLES: Array = ["aggressive", "cautious", "defensive", "desperate"]
const DEFAULT_ENGAGE_STYLE: String = "aggressive"

## Resolve an autoload singleton by name. Direct `Autoload.` references fail to compile
## in a class_name script under the headless -s harness (autoloads register after
## class_name scripts are parsed); the /root lookup is ordering-independent.
static func _al(autoload_name: String) -> Node:
	return (Engine.get_main_loop() as SceneTree).root.get_node("/root/" + autoload_name)

## One beat's worth of movement, matching the registry fallback step.
static func _step() -> float:
	return _al("Agents").fallback_speed

## Max magnitude (px) of an agent's formation offset — chosen to sit strictly inside BOTH
## proximity gates the offset must never break:
##   * PORTAL_CROSS_RADIUS (40): an agent standing at from_pos+offset still counts as "at the door"
##     and crosses, and one arriving at to_pos+offset can still reach and re-cross a reverse portal;
##   * RITE_RADIUS (80): a cultist resting at site+offset still stands close enough for its rite
##     (and its gathering, GATHER_RADIUS 80) to bite.
## Any larger and a worst-case offset could strand an agent one pixel outside a gate; much smaller
## and the crowd reads as a stack again. 38 keeps a visible spread while staying strictly under the
## tightest gate (the portal's 40): max offset is (38-1) + 0.5px jitter = 37.5. Widened from 30 when
## the roster grew to 19 NPCs — 23 cast ids need 28 slots, and 28 slots inside a 29px disc could
## not hold the >10px pairwise separation the suite asserts.
const FORMATION_RADIUS: float = 38.0
## The formation is a fixed sunflower of this many slots (golden-angle layout, radius growing with
## sqrt(slot/K), scaled to FORMATION_RADIUS-1 so slot+jitter never exceeds FORMATION_RADIUS). The
## slot points are mutually separated so ANY two agents in different slots rest visibly apart (> 10px
## even after each side's 0.5px jitter) — a geometric guarantee, not hash luck. K must stay >= the
## cast size or pigeonhole forces a shared slot; but K >= cast only makes distinct slots POSSIBLE, a
## salt that actually achieves them still has to be found. M12 grew the cast to 24 (the second
## adversary sable_wren): NO salt separated 24 ids in 28 slots (a birthday-collision wall — 3M+
## numeric salts checked, best only ~1px), so K was raised 28 -> 36 to reopen the slot space, and a
## fresh salt found that separates the whole 24-id cast (min pairwise ~10.3px; see _test_spawn_formation).
## M14 grew the cast to 25 (leland_mack, the third adversary). At 25 ids the 10px target hits the
## birthday wall even at K=48. K raised 36->48, fresh salt found; measured min pairwise on the
## shipped (K=48, salt 422736) cast = 8.85px — the suite threshold is updated to >8px accordingly.
const _FORMATION_SLOTS: int = 48
## Salt mixed into the id before slotting. The number was CHOSEN (see _test_spawn_formation) so the
## current cast (data/npcs.json + the player proxy + the suite's cult ids) occupies pairwise
## distinct slots; the suite asserts that separation, so a future roster addition that happens to
## share a slot fails CI loudly — raise _FORMATION_SLOTS and/or bump this salt until the whole cast
## separates again (a joint (K, salt) search — a salt bump alone may not suffice past a birthday wall).
const _FORMATION_SALT: String = "|formation422736"
const _GOLDEN_ANGLE: float = 2.399963229728653

## Deterministic per-agent offset applied wherever the whole cast would otherwise converge on ONE
## exact pixel — portal exits, named-site goals, door queues, altar piles. This is a DATA fix, not a
## render jitter: RoomView/NPC puppet agent.position exactly, so the spread must live in the agents'
## logical positions. A pure function of the id (no RNG, no beat) so the same agent always gets the
## same offset — replays stay deterministic and a resting spot never wobbles between beats.
static func _formation_offset(id: String) -> Vector2:
	# MD5, not hash(): Godot's String hash is djb2 (h = h*33 + c) and 33 == 1 (mod 16), so
	# `hash % small K` collapses to the id's character SUM mod K — near-identical slots for many
	# ids, and a salt shifts EVERY id by the same constant (verified: salting never changed the
	# cast's relative offsets). MD5 avalanche-mixes, making the slot pick honestly uniform.
	var digest := (id + _FORMATION_SALT).md5_text()
	var slot := int(("0x" + digest.substr(0, 8)).hex_to_int() % _FORMATION_SLOTS)
	var radius := sqrt(float(slot + 1) / float(_FORMATION_SLOTS)) * (FORMATION_RADIUS - 1.0)
	var point := Vector2(cos(slot * _GOLDEN_ANGLE), sin(slot * _GOLDEN_ANGLE)) * radius
	# Sub-pixel per-id jitter from an independent digest channel: even two ids that DO share a slot
	# never land on the same exact point, so "coincident forever" cannot restart on a slot collision.
	var jitter_angle := float(("0x" + digest.substr(8, 8)).hex_to_int()) / 4294967296.0 * TAU
	return point + Vector2(cos(jitter_angle), sin(jitter_angle)) * 0.5

## P5 (lab pull-in) — classify one committed action's outcome as a GATE FAILURE or not.
## Returns "" for successes and for informed PROGRESS states (a phase-1 deposit, a landed step);
## otherwise a stable key of verb + args + refusal reason, so the runtime can count consecutive
## IDENTICAL failures (same key) per agent and force a replan at three. Pure — reads only the
## outcome dicts this file itself returns; adding a new verb whose failure shape carries one of
## these markers is covered automatically.
static func failure_key(action: Dictionary, outcome: Dictionary) -> String:
	var verb := String(action.get("verb", ""))
	var reason := ""
	if outcome.has("noop"):
		reason = String(outcome["noop"])
	elif outcome.has("reason") and (bool(outcome.get("added", true)) == false
			or bool(outcome.get("ok", true)) == false
			or String(outcome.get("engaged", "x")) == ""):
		reason = String(outcome["reason"])   # gather full/none_here, cast refusals, junk engage
	elif outcome.has("hit") and not bool(outcome["hit"]):
		reason = "no_hit"                    # out-of-reach / cross-room / downed-target swing
	elif outcome.has("shared") and not bool(outcome["shared"]):
		reason = "not_shared"                # out-of-reach / cross-room / empty-speaker talk
	elif verb == "perform_ritual_step" and not bool(outcome.get("advanced", true)) \
			and not outcome.has("deposited"):
		reason = "not_advanced"              # off-site or starved rite (a deposit is progress)
	if reason == "":
		return ""
	return "%s|%s|%s" % [verb, JSON.stringify(action.get("args", {}) if action.get("args") is Dictionary else {}), reason]

static func commit(action: Dictionary, agent: Agent) -> Dictionary:
	agent.current_action = action.duplicate(true)
	agent.thought = String(action.get("thought", ""))
	var verb := String(action.get("verb", ""))
	# Defensive: a typed `Dictionary` assignment would CRASH on a non-dict `args` (e.g. a model that
	# returns "args":"go north"). The autonomous path can't reach this (ActionSchema.validate rejects it
	# first), but commit is the single world-mutation point, so coerce rather than trust the caller.
	var args: Dictionary = action.get("args", {}) if action.get("args") is Dictionary else {}
	# A fresh committed decision SUPERSEDES a standing combat stance (review M1 #1): without this,
	# an agent that once engaged holds position on every off-cohort beat forever unless the LLM
	# happens to emit an explicit disengage. Intent verbs manage the field themselves below;
	# `attack` is a combat act (review M2 #3) — a swing thrown mid-fight must not erase the stance —
	# and so is `cast_ability` (M4): a GM-forced art must not strip the stance the agent fights by.
	if verb != "engage" and verb != "disengage" and verb != "protect" and verb != "attack" \
			and verb != "cast_ability" \
			and not agent.combat_intent.is_empty():
		agent.combat_intent = {}
	match verb:
		"move_to":
			return _move_to(agent, String(args.get("target", "")))
		"talk_to":
			return _talk_to(agent, String(args.get("agent", "")), String(args.get("topic", "")))
		"gather_item":
			return _gather_item(agent, String(args.get("item_id", "")))
		"perform_ritual_step":
			return _perform_ritual_step(agent, String(args.get("step", "")))
		"recruit":
			agent.remember("approached %s to recruit" % args.get("agent", ""))
			return {"recruited": String(args.get("agent", ""))}
		"report":
			agent.remember("reported to %s: %s" % [args.get("to", ""), args.get("info", "")])
			return {"reported_to": String(args.get("to", ""))}
		"pray":
			# An NPC praying is memory-only flavor; only PrayerService.pray() (player-initiated)
			# runs adjudication and applies mechanical effects.
			agent.remember("prayed to %s" % args.get("god", ""))
			return {"prayed_to": String(args.get("god", ""))}
		"adopt_goal":
			return _adopt_goal(agent, String(args.get("goal", "")), goal_kind(args))
		"drop_goal":
			return _drop_goal(agent, String(args.get("goal", "")))
		"hide":
			agent.remember("went to ground")
			return {"hid": true}
		"flee":
			return _flee(agent, String(args.get("from", "")))
		"attack":
			return _attack(agent, String(args.get("target", "")))
		"cast_ability":
			return _cast_ability(agent, String(args.get("ability", "")))
		"engage":
			return _engage(agent, String(args.get("target", "")), String(args.get("style", "")))
		"disengage":
			return _disengage(agent, String(args.get("via", "")))
		"protect":
			return _protect(agent, String(args.get("agent", "")))
		"idle":
			return {"idle": true}
		_:
			return {"noop": "unhandled verb '%s'" % verb}

## A cultist working the rite AT the warehouse drives the summoning clock forward — this is the
## only place cult behavior bites the doomsday countdown, so the player can watch the descent leap
## as the faithful gather. The same verb off-site, or from anyone outside the cult, is flavor only.
## (The Critic already blocks non-cultists from proposing this verb; the guard here keeps the world
## effect honest regardless of how the action reached commit.) Emits `ritual_advanced` for the
## debug log — deliberately NOT a public cult-progress event, so the rite stays hidden but felt.
## True when the agent is in a rite site's ROOM and within RITE_RADIUS of it — the warehouse (room
## "city") and the crypt altar (room "cathedral_crypt"). Room-aware, so an off-scene crypt rite counts
## and a same-coordinate point in the wrong room (e.g. standing on the chapel steps in the City) does
## NOT — the cult must actually descend through the portals to work the cathedral rite.
static func _near_any_rite_site(room: String, pos: Vector2) -> bool:
	for site_name in SITES:
		if _site_room(site_name) == room and pos.distance_to(SITES[site_name]) <= RITE_RADIUS:
			return true
	return false

## The rite at the altar is now a two-phase act, so the cult must FETCH before they can summon:
##   1. lay materials — if the cultist is carrying a material the altar still wants, set one down
##      (consume from inventory, push it onto the altar pile so it renders, count it toward the
##      requirement). The descent does NOT move yet.
##   2. invoke — once every required material is laid (SummoningPlan.materials_ready), each rite step
##      advances the doomsday clock by one beat as before.
## An empty-handed cultist at a still-incomplete altar gets a no-op (advanced:false, awaiting): the
## brain's perception tells it what's missing, so it goes back to the cache for more. Off-site or
## non-cult steps stay flavor-only.
static func _perform_ritual_step(agent: Agent, step: String) -> Dictionary:
	agent.remember("performed ritual step: %s" % step)
	if agent.task.is_empty() or not _near_any_rite_site(agent.room, agent.position):
		return {"ritual_step": step, "advanced": false}
	var sp: Node = _al("SummoningPlan")
	# Phase 1 — lay one carried material the altar still wants.
	for item_id in agent.inventory.keys():
		if sp.needs(item_id) and agent.item_count(item_id) > 0:
			agent.remove_item(item_id, 1)
			sp.deposit(item_id)
			# Render it on the altar as a non-gatherable pile so it can't be re-picked-up. Offset
			# per (agent, item) so the offerings spread around the layer instead of piling on its
			# exact pixel; the same pair always lands on the same spot, so repeat lays still stack.
			_al("RoomItems").place(agent.room, item_id,
				agent.position + _formation_offset(agent.id + "|" + item_id), 1, false)
			agent.remember("laid %s at the altar" % item_id)
			_al("EventBus").emit_event("material_deposited", {
				"actor": agent.id, "item_id": item_id, "room": agent.room,
				"deposited": sp.materials_deposited_total(), "required": sp.materials_required_total(),
			})
			return {"ritual_step": step, "deposited": item_id, "advanced": false}
	# Phase 2 — altar fully stocked: working the rite advances the descent.
	if sp.materials_ready():
		sp.advance_rite(1)
		_al("EventBus").emit_event("ritual_advanced",
			{"actor": agent.id, "step": step, "closeness": sp.closeness_ratio()})
		return {"ritual_step": step, "advanced": true}
	# Empty-handed at an unfinished altar — nothing to lay, can't invoke yet.
	return {"ritual_step": step, "advanced": false, "awaiting_materials": true}

static func _move_to(agent: Agent, target: String) -> Dictionary:
	var resolved := _resolve_target(target)
	if not resolved["found"]:
		return {"noop": "unresolved target '%s'" % target}
	var troom: String = String(resolved.get("room", ""))
	# Target in a DIFFERENT room: walk to the next portal on the path, then cross it. Crossing is a
	# pure data move (set room + reposition), never a scene load — so the agent traverses City ->
	# Nave -> Crypt one room at a time even when the player is elsewhere.
	if troom != "" and troom != agent.room and RoomGraph.has_room(troom) and RoomGraph.has_room(agent.room):
		var hop := RoomGraph.next_hop(agent.room, troom)
		var p := RoomGraph.portal(agent.room, hop)
		if not p.is_empty():
			var from_pos: Vector2 = p["from_pos"]
			if agent.position.distance_to(from_pos) <= PORTAL_CROSS_RADIUS:
				var from_room := agent.room
				agent.room = hop
				# Arrive at the exit PLUS this agent's formation offset: without it every crosser
				# lands on the identical to_pos pixel, and the fully deterministic walk that follows
				# keeps coincident agents coincident forever — the "cult stack" bug.
				agent.position = (p["to_pos"] as Vector2) + _formation_offset(agent.id)
				agent.remember("crossed into %s" % hop)
				agent.mark_transition("just_changed_room")   # one-shot transition marker (P1)
				# The single public, human-readable "an NPC walked into a new scene" signal — the debug
				# overlay renders "Dalia moved from the harbor to the cathedral crypt." (the raw
				# agent_action move is hidden); PlayLog records it too.
				_al("EventBus").emit_event("agent_moved_room",
					{"actor": agent.id, "from": from_room, "to": hop})
				return {"crossed_to": hop, "pos": [agent.position.x, agent.position.y]}
			# Queue AT the door, not ON one pixel: each agent walks to the door plus its own offset.
			# The crossing gate above still bites because FORMATION_RADIUS < PORTAL_CROSS_RADIUS.
			return _step_toward(agent, from_pos + _formation_offset(agent.id), "the door to %s" % hop)
	# Same room (or a roomless "x,y" / cross-room with no path): step toward the local position.
	# A NAMED site fans out per-agent so the cell gathers AROUND the altar instead of freezing on
	# its exact pixel (the rite gate still bites: FORMATION_RADIUS < RITE_RADIUS). Agent targets and
	# raw "x,y" coordinates stay exact — following someone or an explicit point must not drift.
	var dest: Vector2 = resolved["pos"]
	if SITES.has(target) or NAV_SITES.has(target):
		dest += _formation_offset(agent.id)
	return _step_toward(agent, dest, target)

## One beat's straight-line step toward `dest` in the agent's current room; snaps on arrival.
static func _step_toward(agent: Agent, dest: Vector2, label: String) -> Dictionary:
	var to_dest: Vector2 = dest - agent.position
	var dist: float = to_dest.length()
	var step := _step()
	if dist <= step or dist == 0.0:
		agent.position = dest
	else:
		agent.position += to_dest / dist * step
	agent.remember("moved toward %s" % label)
	return {"moved_to": [agent.position.x, agent.position.y]}

## Keyword fallback for classifying a goal's kind when the action carries no explicit `kind`. Words that
## read as turning a waverer AGAINST its cell. Used ONCE at adoption (see `goal_kind`), never re-scanned at
## read time — the decision is persisted on the goal entry, so behavioral state and its detector can't drift.
const _DEFECTION_KEYWORDS: Array = ["help", "stop", "investigator", "against", "abandon", "betray",
	"turn", "save", "warn", "protect", "no longer", "leave the cell", "give them up"]

## The kind to stamp on a goal as it is adopted: the brain's explicit `kind` arg if it emitted one (it
## knows when it is persuading a defection), else the keyword classification of the text. Decided here ONCE
## per adoption; downstream reads the stored kind (Agent.has_defection_goal) and never re-classifies.
static func goal_kind(args: Dictionary) -> String:
	var explicit := String(args.get("kind", "")).strip_edges()
	if explicit != "":
		return explicit
	return _classify_goal_kind(String(args.get("goal", "")))

static func _classify_goal_kind(goal: String) -> String:
	var g := goal.to_lower()
	for kw in _DEFECTION_KEYWORDS:
		if g.contains(kw):
			return "defection"
	return "other"

## The agent TAKES ON a new goal — the engine-side of goal-changing dialogue (precedent:
## agent-sandbox AdoptGoal). General-purpose: what keeps persuasion honest is the deciding agent's
## persona (the LLM choosing this), not a restriction here. Idempotent — re-adopting a held goal is a
## no-op. The goal lands in `agent.adopted_goals` as {"text", "kind"}, which Perception folds into the
## brain's goal set; the persisted `kind` is what marks a turned waverer.
static func _adopt_goal(agent: Agent, goal: String, kind: String = "") -> Dictionary:
	if goal == "" or agent.has_adopted_goal(goal):
		return {"adopted": "", "already": agent.has_adopted_goal(goal)}
	var k := kind if kind != "" else _classify_goal_kind(goal)
	agent.adopted_goals.append({"text": goal, "kind": k})
	agent.remember("adopted a new goal: %s" % goal)
	return {"adopted": goal, "kind": k}

## The agent ABANDONS one of its adopted goals (precedent: agent-sandbox DropGoal). A goal it does not
## hold is a safe no-op.
static func _drop_goal(agent: Agent, goal: String) -> Dictionary:
	if goal == "" or not agent.has_adopted_goal(goal):
		return {"dropped": ""}
	for i in range(agent.adopted_goals.size()):
		if String((agent.adopted_goals[i] as Dictionary).get("text", "")) == goal:
			agent.adopted_goals.remove_at(i)
			break
	agent.remember("abandoned the goal: %s" % goal)
	return {"dropped": goal}

static func _flee(agent: Agent, from: String) -> Dictionary:
	var resolved := _resolve_target(from)
	if resolved["found"]:
		var away: Vector2 = agent.position - (resolved["pos"] as Vector2)
		if away.length() > 0.0:
			agent.position += away / away.length() * _step()
	agent.remember("fled from %s" % from)
	return {"fled_from": from}

## A strike on another agent: flat damage when the attacker is in reach and the target is up.
## Felling a target downs (incapacitates) it rather than deleting it — our cast is fixed and
## saved. Out-of-reach swings, unknown targets, and blows on an already-downed body are
## flavor-only no-ops. Emits `agent_attacked` per connecting blow and `agent_downed` once, the
## moment a target is felled — the public, felt signals that combat actually happened.
static func _attack(agent: Agent, target_id: String) -> Dictionary:
	agent.remember("attacked %s" % target_id)
	var target: Agent = _al("Agents").get_agent(target_id)
	if target == null or target.downed:
		return {"attacked": target_id, "hit": false}
	# Rooms are separate scenes with LOCAL coordinate spaces — a cross-room distance compares
	# unrelated numbers, so a target in another room can never be in reach (same no-op outcome
	# as an out-of-reach swing).
	if String(target.room) != String(agent.room):
		return {"attacked": target_id, "hit": false}
	if agent.position.distance_to(target.position) > ATTACK_RADIUS:
		return {"attacked": target_id, "hit": false}
	target.take_damage(ATTACK_DAMAGE)
	var eb: Node = _al("EventBus")
	eb.emit_event("agent_attacked",
		{"actor": agent.id, "target": target_id, "damage": ATTACK_DAMAGE, "target_hp": target.hp, "downed": target.downed})
	if target.downed:
		eb.emit_event("agent_downed", {"actor": agent.id, "target": target_id})
	return {"attacked": target_id, "hit": true, "target_hp": target.hp, "downed": target.downed}

## --- Combat intent verbs (combat plan §M1). Each commit PUBLISHES Agent.combat_intent as a
## fact — {"mode", target/via/agent, "style", "set_at_beat"} — and does nothing else: no damage,
## no movement, no cooldown. The M2 executor + M3 tactical layer read the fact and act at frame
## rate; the intent itself is just the LLM re-masking that machinery (~15s cadence). ---

## `engage {target, style?}` — the agent commits to fighting `target`. Style is validated here
## (∈ ENGAGE_STYLES, default aggressive) so downstream layers never see a junk mask. The target
## must RESOLVE (review M1 #5) — an unknown/empty/self target publishes no intent (the M2/M3
## layers must never read junk). A valid engage also ENTERS combat mode (review M1 #6): choosing
## the fight flips the stance exactly like being struck does — the executor keys on in_combat.
static func _engage(agent: Agent, target_id: String, style: String) -> Dictionary:
	var target: Agent = _al("Agents").get_agent(target_id)
	if target == null or target_id == agent.id:
		agent.remember("considered a fight, but there was no one to fight")
		return {"engaged": "", "reason": "no_such_target"}
	var s := style if ENGAGE_STYLES.has(style) else DEFAULT_ENGAGE_STYLE
	agent.combat_intent = {
		"mode": "engage", "target": target_id, "style": s,
		"set_at_beat": int(_al("Clock").beat_index),
	}
	if not agent.in_combat:
		_al("CombatMode").enter_combat(agent)
	agent.remember("resolved to engage %s" % target_id)
	return {"engaged": target_id, "style": s}

## `disengage {via?}` — the agent commits to breaking off. Also EXITS combat mode (via CombatMode,
## which publishes combat_ended): disengage is the intent layer's way OUT of the mask that damage
## flipped on.
static func _disengage(agent: Agent, via: String) -> Dictionary:
	agent.combat_intent = {"mode": "disengage", "via": via, "set_at_beat": int(_al("Clock").beat_index)}
	_al("CombatMode").exit_combat(agent)
	agent.remember("broke off from the fight" + ((" via %s" % via) if via != "" else ""))
	return {"disengaged": true, "via": via}

## `cast_ability {ability}` — route ONE ability cast into the frame-rate combat machinery
## (combat plan §M4). This is the GM/Director's seam: Overseer directives commit through here
## (the /decide menu deliberately does NOT offer this verb yet — the intent layer picks stances,
## not casts — and the Critic vetoes it from a proposal unless the agent is already in a fight).
## A cast on an agent not yet fighting ENTERS combat first (the GM-forced case: the corruption
## loss-of-control transform drags the body into the fight it transforms in). The cast itself
## executes on the agent's CombatExecutor — immediately when one is live and willing, else it
## PARKS on agent.pending_cast and the executor consumes it on its first step (the NPC seam
## spawns the executor a frame after combat_started). Unknown arts and downed agents are safe
## no-ops; telegraphs, resolution, and the transform swap all stay the executor's (M2/M3).
static func _cast_ability(agent: Agent, ability_id: String) -> Dictionary:
	if agent.downed:
		return {"cast_ability": ability_id, "ok": false, "reason": "downed"}
	if ability_id == "" or not _al("AbilityDB").has_ability(ability_id):
		return {"cast_ability": ability_id, "ok": false, "reason": "unknown_ability"}
	if not agent.in_combat:
		_al("CombatMode").enter_combat(agent)
	agent.remember("worked the art %s" % ability_id)
	var ex: CombatExecutor = CombatExecutor.for_agent(agent.id)
	if ex != null:
		var res: Dictionary = ex.try_cast(ability_id, String(agent.combat_intent.get("target", "")))
		if bool(res.get("ok", false)):
			return {"cast_ability": ability_id, "ok": true, "pending": false}
		var reason := String(res.get("reason", ""))
		# busy/stunned are TIMING refusals — park the cast and let the executor retry on its
		# clock (the same retry contract a reflex cast gets); anything else is a real refusal.
		if reason != "busy" and reason != "stunned":
			return {"cast_ability": ability_id, "ok": false, "reason": reason}
	agent.pending_cast = ability_id
	return {"cast_ability": ability_id, "ok": true, "pending": true}

## `protect {agent}` — the agent commits to shielding a ward. A published stance, not an act.
static func _protect(agent: Agent, ward_id: String) -> Dictionary:
	agent.combat_intent = {"mode": "protect", "agent": ward_id, "set_at_beat": int(_al("Clock").beat_index)}
	agent.remember("moved to shield %s" % ward_id)
	return {"protecting": ward_id}

## Gathering a known item stocks the agent's OWN inventory, capacity-gated (Agent.carry_capacity) —
## a cultist can only carry so many materials per trip, which is what forces the gather→deliver loop.
## If that item is lying on the ground in the agent's room (RoomItems — the cult's supply cache),
## gathering CONSUMES one off the pile so it visibly depletes: nearest-within-reach first, else the
## nearest of that type anywhere in the room (the cell drawing from its own stash).
##
## A RITUAL OFFERING (anything in SummoningPlan.ritual_requirement) may ONLY be picked up off a real
## ground pile — it is NEVER foraged from thin air. This is the gate that makes the summoning honest:
## the cult must carry the offerings down from the City cache (it can't fabricate them at the altar),
## and emptying the cache genuinely STARVES the rite (the player can sabotage it). Every OTHER known
## item still forages when the room holds none (per-agent fieldwork — Yumina-style). The player still
## sabotages the cult's separate rite cache (SummoningPlan), which gathering does not restock. Unknown
## items, a full pack, and an un-forageable offering with no pile in reach are safe no-ops. Emits
## `item_gathered` only when something is actually added.
static func _gather_item(agent: Agent, item_id: String) -> Dictionary:
	agent.remember("gathered %s" % item_id)
	if item_id == "" or not _al("ItemDB").has_def(item_id):
		return {"gathered": item_id, "added": false}
	if not agent.can_carry():
		# Informed failure, like the empty-pile case below: without this fact the LLM re-gathers
		# forever (live playtest finding) — with it, the next deliberation knows to go deliver first.
		agent.remember("tried to gather %s, but hands were full" % item_id)
		return {"gathered": item_id, "added": false, "reason": "full", "count": agent.item_count(item_id)}
	var ri: Node = _al("RoomItems")
	var picked: String = ri.take_near(agent.room, item_id, agent.position, GATHER_RADIUS)
	if picked == "":
		picked = ri.take_near(agent.room, item_id, agent.position, STASH_RADIUS)   # else draw from the cell's nearby stash
	# Ritual offerings can't be foraged — no ground pile, no pickup, so the cult must use the cache.
	if picked == "" and _al("SummoningPlan").ritual_requirement.has(item_id):
		# Contention fact (agent-sandbox turns.py precedent): tell the loser WHY the gather failed,
		# so its next deliberation is an informed retry (pick a different item) instead of a blind
		# repeat of the same stale premise. Who emptied the pile arrives via the witness channel.
		agent.remember("reached for %s, but found none left" % item_id)
		return {"gathered": item_id, "added": false, "reason": "none_here", "count": agent.item_count(item_id)}
	agent.add_item(item_id, 1)
	_al("EventBus").emit_event("item_gathered", {
		"actor": agent.id, "item_id": item_id, "count": agent.item_count(item_id),
		"from_ground": picked != "",
	})
	return {"gathered": item_id, "added": true, "from_ground": picked != "", "count": agent.item_count(item_id)}

## A talk passes the speaker's freshest observation to the listener as hearsay — this is how
## knowledge (and the player's exposure) actually travels between agents, not just flavor. Modeled
## on Yumina's talk_to_npc, which seeds the LISTENER's "heard from others" log, with the same
## anti-hallucination guard: an agent who has observed nothing has nothing to share, so no rumor is
## invented. Proximity-gated (TALK_RADIUS) like the rite and the strike — a conversation must happen
## face-to-face. The speaker's own memory is captured BEFORE recording "talked to ..." so the
## exchange itself never becomes the rumor. A downed, unknown, or out-of-reach listener, or an empty
## speaker, is a memory-only no-op. Emits `rumor_spread` so the spread is observable in the log.
static func _talk_to(agent: Agent, target_id: String, topic: String) -> Dictionary:
	# mem_text, not String(): a scored dict row (P1) must share its TEXT, never a "{...}" wrapper.
	var observation: String = Agent.mem_text(agent.short_memory[-1]) if not agent.short_memory.is_empty() else ""
	agent.remember("talked to %s about %s" % [target_id, topic])
	var listener: Agent = _al("Agents").get_agent(target_id)
	if listener == null or listener.downed:
		return {"talked_to": target_id, "shared": false}
	# Same-room guard (same bug class as the cross-room strike): local coordinates from two
	# different rooms are not comparable, and a face-to-face talk cannot span rooms anyway.
	if String(listener.room) != String(agent.room):
		return {"talked_to": target_id, "shared": false}
	if agent.position.distance_to(listener.position) > TALK_RADIUS:
		return {"talked_to": target_id, "shared": false}
	if observation == "":
		return {"talked_to": target_id, "shared": false}
	var speaker_name := agent.display_name if agent.display_name != "" else agent.id
	listener.remember("heard from %s: %s" % [speaker_name, observation])
	_al("EventBus").emit_event("rumor_spread",
		{"from": agent.id, "to": target_id, "summary": observation, "topic": topic})
	return {"talked_to": target_id, "shared": true, "rumor": observation}

## Resolve a target string to a position. Order: another agent's id, a named site, an
## "x,y" coordinate. Returns { found: bool, pos: Vector2 }.
static func _resolve_target(target: String) -> Dictionary:
	var other: Agent = _al("Agents").get_agent(target)
	if other != null:
		return {"found": true, "pos": other.position, "room": other.room}
	if SITES.has(target):
		return {"found": true, "pos": SITES[target], "room": _site_room(target)}
	if NAV_SITES.has(target):
		var nav: Dictionary = NAV_SITES[target]
		return {"found": true, "pos": nav["pos"], "room": String(nav["room"])}
	if "," in target:
		var parts := target.split(",")
		if parts.size() >= 2 and parts[0].is_valid_float() and parts[1].is_valid_float():
			# A bare coordinate is interpreted in the agent's CURRENT room ("" -> no cross-room hop).
			return {"found": true, "pos": Vector2(float(parts[0]), float(parts[1])), "room": ""}
	return {"found": false, "pos": Vector2.ZERO, "room": ""}
