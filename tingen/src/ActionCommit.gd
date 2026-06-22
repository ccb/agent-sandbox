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
}

## How close (px) an agent must stand to the rite site for its ritual work to actually bite.
## Shared with AmbientSidecar so the live brain only proposes the rite when committing it counts.
const RITE_RADIUS: float = 80.0

## How close (px) an attacker must stand to its target for a strike to connect; a swing from
## farther off is flavor only. Mirrors how the rite is proximity-gated.
const ATTACK_RADIUS: float = 64.0
## Flat damage per connecting strike — deterministic, no RNG/crit (Yumina's ability model).
## About three strikes fell a full-HP agent.
const ATTACK_DAMAGE: float = 34.0
## How close (px) two agents must be for talk to carry — a rumor spreads face-to-face, not across
## the district. Roomy (wider than ATTACK_RADIUS) since conversation reaches farther than a blade.
const TALK_RADIUS: float = 96.0

## Resolve an autoload singleton by name. Direct `Autoload.` references fail to compile
## in a class_name script under the headless -s harness (autoloads register after
## class_name scripts are parsed); the /root lookup is ordering-independent.
static func _al(autoload_name: String) -> Node:
	return (Engine.get_main_loop() as SceneTree).root.get_node("/root/" + autoload_name)

## One beat's worth of movement, matching the registry fallback step.
static func _step() -> float:
	return _al("Agents").fallback_speed

static func commit(action: Dictionary, agent: Agent) -> Dictionary:
	agent.current_action = action.duplicate(true)
	agent.thought = String(action.get("thought", ""))
	var verb := String(action.get("verb", ""))
	var args: Dictionary = action.get("args", {})
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
		"hide":
			agent.remember("went to ground")
			return {"hid": true}
		"flee":
			return _flee(agent, String(args.get("from", "")))
		"attack":
			return _attack(agent, String(args.get("target", "")))
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
static func _perform_ritual_step(agent: Agent, step: String) -> Dictionary:
	agent.remember("performed ritual step: %s" % step)
	var site: Vector2 = SITES["iron_cross_warehouse"]
	if agent.faction == "cult" and agent.position.distance_to(site) <= RITE_RADIUS:
		var sp: Node = _al("SummoningPlan")
		sp.advance_rite(1)
		_al("EventBus").emit_event("ritual_advanced",
			{"actor": agent.id, "step": step, "closeness": sp.closeness_ratio()})
		return {"ritual_step": step, "advanced": true}
	return {"ritual_step": step, "advanced": false}

static func _move_to(agent: Agent, target: String) -> Dictionary:
	var resolved := _resolve_target(target)
	if not resolved["found"]:
		return {"noop": "unresolved target '%s'" % target}
	var dest: Vector2 = resolved["pos"]
	var to_dest: Vector2 = dest - agent.position
	var dist: float = to_dest.length()
	var step := _step()
	if dist <= step or dist == 0.0:
		agent.position = dest
	else:
		agent.position += to_dest / dist * step
	agent.remember("moved toward %s" % target)
	return {"moved_to": [agent.position.x, agent.position.y]}

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
	if agent.position.distance_to(target.position) > ATTACK_RADIUS:
		return {"attacked": target_id, "hit": false}
	target.take_damage(ATTACK_DAMAGE)
	var eb: Node = _al("EventBus")
	eb.emit_event("agent_attacked",
		{"actor": agent.id, "target": target_id, "damage": ATTACK_DAMAGE, "target_hp": target.hp, "downed": target.downed})
	if target.downed:
		eb.emit_event("agent_downed", {"actor": agent.id, "target": target_id})
	return {"attacked": target_id, "hit": true, "target_hp": target.hp, "downed": target.downed}

## Gathering a known item stocks the agent's OWN inventory. The player sabotages the cult's
## *shared* rite cache (SummoningPlan), but gathering is per-agent fieldwork and deliberately
## does NOT restock that cache — a conscious divergence from a shared-cache shortcut (Yumina has
## no shared cache and likewise gathers into a personal store). Unknown items are a safe no-op.
## Emits `item_gathered` so the gather is observable.
static func _gather_item(agent: Agent, item_id: String) -> Dictionary:
	agent.remember("gathered %s" % item_id)
	if item_id == "" or not _al("ItemDB").has_def(item_id):
		return {"gathered": item_id, "added": false}
	agent.add_item(item_id, 1)
	_al("EventBus").emit_event("item_gathered",
		{"actor": agent.id, "item_id": item_id, "count": agent.item_count(item_id)})
	return {"gathered": item_id, "added": true, "count": agent.item_count(item_id)}

## A talk passes the speaker's freshest observation to the listener as hearsay — this is how
## knowledge (and the player's exposure) actually travels between agents, not just flavor. Modeled
## on Yumina's talk_to_npc, which seeds the LISTENER's "heard from others" log, with the same
## anti-hallucination guard: an agent who has observed nothing has nothing to share, so no rumor is
## invented. Proximity-gated (TALK_RADIUS) like the rite and the strike — a conversation must happen
## face-to-face. The speaker's own memory is captured BEFORE recording "talked to ..." so the
## exchange itself never becomes the rumor. A downed, unknown, or out-of-reach listener, or an empty
## speaker, is a memory-only no-op. Emits `rumor_spread` so the spread is observable in the log.
static func _talk_to(agent: Agent, target_id: String, topic: String) -> Dictionary:
	var observation: String = String(agent.short_memory[-1]) if not agent.short_memory.is_empty() else ""
	agent.remember("talked to %s about %s" % [target_id, topic])
	var listener: Agent = _al("Agents").get_agent(target_id)
	if listener == null or listener.downed:
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
		return {"found": true, "pos": other.position}
	if SITES.has(target):
		return {"found": true, "pos": SITES[target]}
	if "," in target:
		var parts := target.split(",")
		if parts.size() >= 2 and parts[0].is_valid_float() and parts[1].is_valid_float():
			return {"found": true, "pos": Vector2(float(parts[0]), float(parts[1]))}
	return {"found": false, "pos": Vector2.ZERO}
