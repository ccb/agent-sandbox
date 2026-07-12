class_name Perception
extends RefCounted
## Builds the perception snapshot a sidecar needs to choose an action for one agent.
## A snapshot is a flat, JSON-safe Dictionary: who the agent is, what it wants, where it
## stands, who/what is near it, the recent event stream, and the world's coarse state.
## Pure read — never mutates anything.

## Default per-agent vision radius (px) — absorbs the old NEARBY_RADIUS, so default behavior is
## unchanged. Vision is per-agent DATA (agent-sandbox precedent): each Agent carries its own
## `vision_r` (hydrated from an optional "vision_r" in npcs.json), and this constant is only the
## default for agents whose def doesn't set one. It gates (1) which same-room peers enter the
## agent's `nearby` roster and (2) which room events Stimulus writes into its memory.
const DEFAULT_VISION_R: float = 160.0

## Resolve an autoload singleton by name. Direct `Autoload.` references fail to compile
## in a class_name script under the headless -s harness (autoloads register after
## class_name scripts are parsed); the /root lookup is ordering-independent.
static func _al(autoload_name: String) -> Node:
	return (Engine.get_main_loop() as SceneTree).root.get_node("/root/" + autoload_name)

## Coarse condition band (combat plan §M1): healthy(>2/3) | hurt(>1/3) | critical(>0) | downed.
## Peers are ALWAYS banded, never exact — an agent can see that a neighbor limps, not read their
## hit points. Mirrors brain.py's hp_band (language-neutral rule).
static func hp_band(hp: float, max_hp: float, downed: bool) -> String:
	if downed or hp <= 0.0:
		return "downed"
	var ratio := hp / max_hp if max_hp > 0.0 else 1.0
	if ratio > 2.0 / 3.0:
		return "healthy"
	if ratio > 1.0 / 3.0:
		return "hurt"
	return "critical"

## The ONE perceiver gate (combat plan §M3): can `viewer` perceive an event that happened at
## `event_pos` in `event_room`? Same room AND — when the event carries a position — within the
## VIEWER's own vision_r (perception is the perceiver's property; no group/faction filter). A
## null event_pos means the caller had no meaningful position, so room co-location alone
## decides. Extracted from Stimulus._fan_room so the witness fan and the M3 reflex channel
## share one gate, tested once.
static func can_perceive(viewer: Agent, event_room: String, event_pos: Variant = null) -> bool:
	if viewer == null:
		return false
	if String(viewer.room) != String(event_room):
		return false
	if event_pos != null and viewer.position.distance_to(event_pos) > viewer.vision_r:
		return false
	return true

static func build_snapshot(agent: Agent, _player_center: Vector2) -> Dictionary:
	return {
		"agent_id": agent.id,
		"display_name": agent.display_name,
		"role": agent.role,
		"intent": agent.intent,
		"adopted_goals": agent.adopted_goals.duplicate(true),
		"description": agent.description,
		"voice": agent.voice,
		"knowledge": agent.knowledge.duplicate(),
		"secrets": agent.secrets.duplicate(),
		"tier": agent.tier,
		"goals": agent.goals.duplicate(true),
		"task": agent.task.duplicate(true),
		"position": [agent.position.x, agent.position.y],
		"room": agent.room,
		# The agent's OWN health — exact, because your own body is the one thing you know exactly
		# (combat plan §M1). Peers get a coarse hp_band in `nearby` instead, never these numbers.
		"hp": agent.hp,
		"max_hp": agent.max_hp,
		"downed": agent.downed,
		# Combat facts (combat plan §M4). `in_combat` is the mask flag; `combat_intent` is the
		# agent's OWN published stance, full detail — it authored it; `last_attacker` is the
		# executor hit ledger's fact of who last landed a blow on THIS body ("" outside combat:
		# the static ledger outlives fights, so it is only forwarded while the fight is real);
		# `kit` is the worn form's art roster (its own body — id/class/authored description).
		"in_combat": agent.in_combat,
		"combat_form": agent.combat_form,
		"combat_intent": agent.combat_intent.duplicate(true),
		"last_attacker": CombatExecutor.last_attacker_of(agent.id) if agent.in_combat else "",
		"kit": _kit_summary(agent),
		"short_memory": agent.short_memory.duplicate(),
		"mem_total": agent.mem_total,
		"current_action": agent.current_action.duplicate(true),
		"nearby": _nearby(agent),
		"inventory": agent.inventory.duplicate(),
		"carry_capacity": agent.carry_capacity,
		"can_carry_more": agent.can_carry(),
		"ground_items": _ground_items(agent),
		"rite_materials": _rite_materials(),
		# The GM Coordinator's work-partition FACT for this agent ({} for bystanders/no allocation):
		# published information, never a command (orchestrator/GM design §4.2).
		"focus": _al("Coordinator").focus_for(agent.id),
		# recent_events was removed: a global event feed here would leak past each agent's vision_r
		# (omniscience); what an agent may know of others' deeds arrives via the vision-gated
		# Stimulus channel into short_memory instead.
		"stage": _al("WorldManager").current_stage_id,
		"pressures": {
			"corruption": _al("WorldState").corruption,
			"cult_readiness": _al("WorldState").cult_readiness,
			"panic": _al("WorldState").panic,
			"attention": _al("WorldState").attention,
		},
		"phase": _al("Clock").phase,
		"beat": _al("Clock").beat_index,
	}

## Build the stateful-brain decide request (agent-sidecar SPEC §6) for one agent, purely from the
## snapshot dict above. Every entry currently in short_memory is sent each beat, tagged with its
## absolute lifetime sequence id (`seq`): the window holds the last N observations, so the i-th
## surviving entry has seq = mem_total - len + i. The brain ingests only seq it has not seen, so
## re-sending the whole (capped) window every beat is idempotent and correct even after eviction —
## no fragile client-side high-water mark. Tiered goals + world_state drive cognition + the veto.
static func decide_request(snap: Dictionary, session_id: String) -> Dictionary:
	var mem: Array = snap.get("short_memory", [])
	var mem_total: int = int(snap.get("mem_total", mem.size()))
	var base_seq: int = mem_total - mem.size()   # absolute seq of mem[0]
	var events: Array = []
	for i in mem.size():
		var text := String(mem[i])
		events.append({"text": text, "importance": _event_importance(text), "seq": base_seq + i})
	var posarr: Array = snap.get("position", [0.0, 0.0])
	var pos := Vector2(float(posarr[0]), float(posarr[1])) if posarr.size() >= 2 else Vector2.ZERO
	var room := String(snap.get("room", RoomGraph.DEFAULT_ROOM))
	var perception := {
		"agent_id": snap.get("agent_id", ""),
		"display_name": snap.get("display_name", ""),
		"role": snap.get("role", ""),
		"room": room,
		# Persona prose for the prompt. `secrets` are deliberately NOT forwarded on the autonomous /decide
		# path (a hidden context) — they only surface in converse, behind the revealed gate.
		"description": snap.get("description", ""),
		"voice": snap.get("voice", ""),
		"knowledge": snap.get("knowledge", []),
		"tier": snap.get("tier", "light"),
		"nearby": snap.get("nearby", []),
		# Own condition, exact (combat plan §M1) — the brain renders it as a plain fact
		# ("Your condition: hurt (61/100)."); peers stay banded inside `nearby`.
		"hp": snap.get("hp", 100.0),
		"max_hp": snap.get("max_hp", 100.0),
		"downed": snap.get("downed", false),
		# The combat mask always rides as a plain bool (the brain gates its COMBAT block on it);
		# the detail fields are added below only while the fight is real, so a peaceful beat's
		# request keeps the legacy shape (and its token budget).
		"in_combat": bool(snap.get("in_combat", false)),
		"locations": ActionCommit.location_names(),
		"pressures": snap.get("pressures", {}),
		# What the agent is carrying + can still pick up, and what's lying within reach — this is what
		# lets the brain choose gather_item with a real target and stop once its hands are full.
		"inventory": snap.get("inventory", {}),
		"carry_capacity": snap.get("carry_capacity", 0),
		"can_carry_more": snap.get("can_carry_more", true),
		"ground_items": snap.get("ground_items", []),
	}
	# Combat detail (combat plan §M4) rides only while in combat: the OWN standing intent (plus
	# how many beats it has stood — the brain renders "set N beats ago" from it), who last struck
	# this body (the executor ledger fact; the same event also reached short_memory as Stimulus
	# prose), and the worn form's art roster. All facts; the brain adds no reading of them.
	if bool(snap.get("in_combat", false)):
		var intent_fact: Dictionary = (snap.get("combat_intent", {}) as Dictionary).duplicate(true)
		if not intent_fact.is_empty():
			intent_fact["set_beats_ago"] = maxi(0, int(snap.get("beat", 0)) - int(intent_fact.get("set_at_beat", 0)))
			perception["combat_intent"] = intent_fact
		var last_attacker := String(snap.get("last_attacker", ""))
		if last_attacker != "":
			perception["last_attacker"] = last_attacker
		var kit: Array = snap.get("kit", []) if snap.get("kit") is Array else []
		if not kit.is_empty():
			perception["kit"] = kit.duplicate(true)
	# An agent that has a deliverable TASK gets its operational ledger (what the task site still needs)
	# and the task itself, so the generic task-situation cue can render. Gated on having a task, not on a
	# faction — a bystander with no task sees neither, so the gather→deliver detail never leaks.
	if not (snap.get("task", {}) as Dictionary).is_empty():
		perception["rite_materials"] = snap.get("rite_materials", {})
		perception["task"] = snap.get("task", {})
		# The Coordinator's allocation rides only with the task it partitions (a bystander never
		# sees the ledger, so it must never see an allocation either).
		if not (snap.get("focus", {}) as Dictionary).is_empty():
			perception["focus"] = snap.get("focus", {})
	# Goals come straight from the agent's own DATA (npcs.json) — a flat tiered list, goals are goals
	# (agent-sandbox model: no public/secret split). The agent knows its own aims; what it CONCEALS from
	# others lives in `secrets` (gated separately), not in a hidden goal. Then this beat's intent as a
	# short goal. No faction branch, no hardcoded goal strings — the engine authors none of them.
	var goals: Array = []
	for g in (snap.get("goals", []) as Array):
		if g is Dictionary:
			goals.append({"description": String(g.get("description", "")), "tier": String(g.get("tier", "medium"))})
	var intent_s := String(snap.get("intent", ""))
	if intent_s != "":
		goals.append({"description": intent_s, "tier": "short"})
	# Goals the agent TOOK ON at runtime (adopt_goal) ride as short goals so they actually steer its
	# next decisions — this is what makes goal-changing dialogue change behavior, not just memory. Each
	# entry is {"text", "kind"}; only the text is a goal the brain pursues (the kind is engine bookkeeping).
	for ag_goal in (snap.get("adopted_goals", []) as Array):
		var ag_text := String((ag_goal as Dictionary).get("text", "")) if ag_goal is Dictionary else String(ag_goal)
		if ag_text != "":
			goals.append({"description": ag_text, "tier": "short", "secret": false})
	return {
		"session_id": session_id,
		"agent_id": snap.get("agent_id", ""),
		"turn": int(snap.get("beat", 0)),
		"events": events,
		"perception": perception,
		"goals": goals,
		"world_state": {
			"actor_at_rite_site": ActionCommit._near_any_rite_site(room, pos),
			# Player-earned exposure (the player uncovering the cult) APPROVES an otherwise-incidental
			# reveal. No exposure mechanic exists yet, so this is false today (all current cult exposure
			# is AI-incidental and so vetoable). Forward hook: an action the player forces carries
			# player_triggered, which flips this true and makes the approve branch reachable live.
			"player_triggered": bool((snap.get("current_action", {}) as Dictionary).get("player_triggered", false)),
		},
	}

## Build a /converse request for ONE conversation turn (design §2.3). Mirrors decide_request's
## perception + gated goals so the NPC speaks consistently with how it acts, then adds the player's
## utterance + dialogue history, FORWARDS `secrets` (the brain renders them only when `revealed`), and
## sets world_state.player_triggered = true — a player-prompted reveal/defection is player-earned, so
## the cult_secrecy veto must not block it. `revealed` stays false (the NPC has not yet broken cover).
static func converse_request(snap: Dictionary, session_id: String, utterance: String, history: Array) -> Dictionary:
	var rc: Dictionary = decide_request(snap, session_id)
	rc["speaker"] = "player"
	rc["utterance"] = utterance
	rc["history"] = history.duplicate()
	rc["revealed"] = false
	(rc["perception"] as Dictionary)["secrets"] = (snap.get("secrets", []) as Array).duplicate()
	# B11 (part 3): a monster's TRUE combat identity must never ride the converse channel. decide_request
	# folds `kit` (the worn form's art roster) and `combat_intent` (its published stance) into perception
	# while in_combat; here we strip them so a conversation with an in-combat NPC can never leak what it
	# can become. Engine-neutral — the keys are dropped whoever the agent is, no identity branch.
	var perc: Dictionary = rc["perception"]
	perc.erase("kit")
	perc.erase("combat_intent")
	(rc["world_state"] as Dictionary)["player_triggered"] = true
	return rc

## Coarse importance for a freeform memory line: occult/rite-charged observations are worth recalling.
static func _event_importance(text: String) -> float:
	var t := text.to_lower()
	for kw in ["rite", "summon", "cathedral", "crypt", "warehouse", "nighthawk", "god", "altar", "blood", "vessel", "ritual"]:
		if t.contains(kw):
			return 6.0
	return 3.0

## Gatherable items lying in the agent's current room, nearest first, each tagged with whether it is
## already within gather reach — so the brain can both walk toward a cache and pick it up on arrival.
static func _ground_items(agent: Agent) -> Array:
	var out: Array = []
	for e in (_al("RoomItems")).items_in(agent.room):
		if not bool(e.get("gatherable", true)):
			continue   # laid offerings render but aren't pickup targets
		var p: Vector2 = e["pos"]
		var d: float = agent.position.distance_to(p)
		out.append({
			"item_id": String(e["item_id"]), "qty": int(e.get("qty", 1)),
			"distance": d, "in_reach": d <= ActionCommit.GATHER_RADIUS,
			"pos": [p.x, p.y],
		})
	out.sort_custom(func(a, b): return float(a["distance"]) < float(b["distance"]))
	return out

## The agent's OWN combat kit as data facts — [{id, class, description}] straight from AbilityDB
## (combat plan §M4), only while the agent is in combat with a combat_form bound (outside a fight
## the roster is not this beat's business; a form-less brawler has no authored arts to know).
## The `description` is the authored honest text from abilities.json — assume_form's phrasing
## stays neutral-but-known through it: the character knows what it can become because its own
## data says so; the engine adds no reading.
static func _kit_summary(agent: Agent) -> Array:
	if not agent.in_combat or agent.combat_form == "":
		return []
	var db := _al("AbilityDB")
	var out: Array = []
	for ability_id in (db.kit_for(agent.combat_form) as Array):
		var def: Dictionary = db.ability_for(String(ability_id))
		if def.is_empty():
			continue   # AbilityDB.validate_refs already warned about the dangling kit entry
		out.append({
			"id": String(ability_id),
			"class": String(def.get("class", "")),
			"description": String(def.get("description", "")),
		})
	return out

## The altar's offering ledger: what's still missing, how much is laid, and whether the rite can now
## advance. Lets the brain know whether to keep fetching or switch to working the rite.
static func _rite_materials() -> Dictionary:
	var sp := _al("SummoningPlan")
	return {
		"outstanding": sp.materials_outstanding(),
		"deposited": sp.materials_deposited_total(),
		"required": sp.materials_required_total(),
		"ready": sp.materials_ready(),
	}

static func _nearby(agent: Agent) -> Array:
	var out: Array = []
	for other in _al("Agents").all():
		if other.id == agent.id:
			continue
		# Rooms are separate scenes with LOCAL coordinate spaces, so a distance between positions in
		# two different rooms compares unrelated numbers — an agent in another room is NEVER nearby,
		# however close its local coords coincidentally are.
		if String(other.room) != String(agent.room):
			continue
		var d: float = agent.position.distance_to(other.position)
		# Gated by the VIEWER's own vision radius — perception is the perceiver's property (data),
		# so a keen-eyed agent and a dim one standing together see different rosters.
		if d <= agent.vision_r:
			# Objective roster entry: identity + what the peer is visibly DOING (its last committed
			# action — watching someone walk toward the crypt is public information). No faction, no
			# concealment flag — how this agent regards who's nearby is its persona's call. The `doing`
			# fact is what lets same-task agents divide work instead of converging on the modal action
			# (orchestrator/GM design §4.2). `hp_band` is the peer's visible condition — BANDED, never
			# exact (combat plan §M1): whether a neighbor limps is public, their hit points are not.
			# `in_combat` is a public fact like `doing`: that a neighbor is visibly fighting is
			# something anyone watching can see (combat plan §M4) — their intent/kit never ride.
			out.append({"id": other.id, "role": other.role, "distance": d, "doing": _doing(other),
				"hp_band": hp_band(other.hp, other.max_hp, other.downed),
				"in_combat": other.in_combat})
	return out

## The peer's last committed action as a compact objective phrase ("move_to crypt_altar",
## "gather_item candle"), or "" when it has none worth reporting. States only verb + primary
## target — never a motive or reading.
static func _doing(other: Agent) -> String:
	var act: Dictionary = other.current_action
	var verb := String(act.get("verb", ""))
	if verb == "" or verb == "idle":
		return ""
	var args: Dictionary = act.get("args", {}) if act.get("args") is Dictionary else {}
	for key in ["target", "item_id", "agent", "to"]:
		if args.has(key):
			return ("%s %s" % [verb, String(args[key])]).left(48)
	return verb
