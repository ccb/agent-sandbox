extends Node
## Perception-event triggers (autoload `Stimulus`) — design Feature 2.
##
## Turns OBJECTIVE world events into neutral perception FACTS written into the affected agents'
## short_memory, so the LLM brain decides the reaction entirely on its own. The wording is uniform and
## states only what happened ("X entered the crypt", "A struck B") — NEVER a reaction ("attack"). The
## cult turning hostile when the player walks in on the rite must EMERGE from that agent's own
## secret-rite context + goals + persona, not from biased signal text. This is the whole principle.
##
## Why short_memory (not the EventBus log): decide_request forwards an agent's short_memory as the
## brain's `events`, but it does NOT forward EventBus.latest — so a stimulus MUST be written to the
## targeted agents' short_memory to reach the prompt. Emitting an EventBus event alone would never
## reach a brain.

## The memory-importance LADDER (lab pull-in P1, ported from the lab's Penn-sim work): importance
## is a number the AUTHOR of a fan block writes ON the row at write time, on the same 1-10 scale
## cognition/agent_memory.py stores (MemoryRecord.importance). Three rungs:
##   IMP_AMBIENT (1.0)  — background texture: someone entered the room;
##   IMP_OUTCOME (2.0)  — a witnessed/felt act and its outcome: a gather, a telegraph, a blow;
##   IMP_PINNED  (8.0)  — must never fade: a body's flesh splitting into something else.
## Perception._event_importance survives only as the FALLBACK scorer for unscored/legacy rows.
const IMP_AMBIENT: float = 1.0
const IMP_OUTCOME: float = 2.0
const IMP_PINNED: float = 8.0

func _ready() -> void:
	if not WorldState.room_changed.is_connected(_on_room_changed):
		WorldState.room_changed.connect(_on_room_changed)
	if not EventBus.event_logged.is_connected(_on_event):
		EventBus.event_logged.connect(_on_event)

## The player crossed into a room — tell everyone standing in it who can SEE the doorway (within
## their own vision_r of where the player stands), as a plain fact. Identical whether that room is
## a tavern or the crypt mid-rite; the cult's reaction is theirs to choose.
func _on_room_changed(room_id: String, _scene_path: String) -> void:
	if room_id == "":
		return
	var player: Agent = Agents.get_agent(Agents.PLAYER_ID)
	var who: String = player.display_name if player != null else "Someone"
	var where := room_id.replace("_", " ")
	var line := "%s entered the %s." % [who, where]
	if player != null:
		_fan_room(room_id, line, [], player.position, IMP_AMBIENT)   # the event happens where the entering player stands
	else:
		# No player proxy has been synced yet, so there is no meaningful event position to measure
		# vision against — fall back to room-wide co-location.
		_fan_room(room_id, line, [], null, IMP_AMBIENT)

## Combat events become perception for the victim + co-located witnesses, so a strike or a death is
## something the others can react to — not just a number in the log. Gather/deposit acts fan the same
## way: watching a peer pick something up is public information, and it is THE fact that lets
## same-task agents divide the remaining work instead of all reaching for the same item
## (orchestrator/GM design §4). All witness gating is vision-based (same room + within the witness's
## own vision_r of where it happened) — never a group filter.
func _on_event(event: Dictionary) -> void:
	var t := String(event.get("type", ""))
	if t == "item_gathered" or t == "material_deposited":
		var d: Dictionary = event.get("data", {})
		var actor: Agent = Agents.get_agent(String(d.get("actor", "")))
		if actor == null:
			return
		var item := String(d.get("item_id", "")).replace("_", " ")
		var act_line := ("%s picked up the %s." % [_name(actor.id), item]) if t == "item_gathered" \
			else ("%s laid the %s at the site." % [_name(actor.id), item])
		# The actor already remembers its own act from the commit; witnesses learn it here.
		_fan_room(actor.room, act_line, [actor.id], actor.position, IMP_OUTCOME)
		return
	# A cast telegraph (combat plan §M1) is SEEN, not felt: vision-gated from where the caster
	# stands, worded as the bare wind-up fact — no reaction, no threat reading. Whether a witness
	# dodges, flees, or watches is its own brain's call (reflex rules dodge in M3; the LLM never
	# rides the frame path).
	if t == "ability_cast_started":
		var cd: Dictionary = event.get("data", {})
		var caster: Agent = Agents.get_agent(String(cd.get("caster", "")))
		if caster == null:
			return
		var tgt := String(cd.get("target", ""))
		var cast_line := ("%s begins to loose something at %s." % [_name(caster.id), _name(tgt)]) if tgt != "" \
			else ("%s begins to loose something." % _name(caster.id))
		# The caster knows its own act (the M2 executor records it); witnesses learn it here.
		_fan_room(caster.room, cast_line, [caster.id], caster.position, IMP_OUTCOME)
		return
	# A transform resolving (combat plan §M6) is the most public thing a body can do: whoever can
	# SEE the agent watches its shape change. Same neutral-fact rules as every other fan — the
	# wording names WHO changed but never the data's form id (what it became is for eyes to judge),
	# and it is generic for ANY transforming agent (no identity branch).
	if t == "transformed":
		var td: Dictionary = event.get("data", {})
		var changed: Agent = Agents.get_agent(String(td.get("agent", "")))
		if changed == null:
			return
		_fan_room(changed.room, "%s's flesh splits — something else stands in their skin." % _name(changed.id),
			[changed.id], changed.position, IMP_PINNED)
		return
	# A data-authored deed firing (DeedRunner, plan §M6): the event carries its own authored
	# fact_line, so the engine adds no wording at all — it just fans the data's sentence from
	# where the actor stands, through the identical vision gate.
	if t == "deed_performed":
		var dd: Dictionary = event.get("data", {})
		var doer: Agent = Agents.get_agent(String(dd.get("actor", "")))
		var deed_line := String(dd.get("line", ""))
		if doer == null or deed_line == "":
			return
		_fan_room(doer.room, deed_line, [doer.id], doer.position, IMP_OUTCOME)
		return
	if t != "agent_attacked" and t != "agent_downed":
		return
	var data: Dictionary = event.get("data", {})
	var target: Agent = Agents.get_agent(String(data.get("target", "")))
	if target == null:
		return
	if t == "agent_attacked":
		var line := "%s struck %s." % [_name(String(data.get("actor", ""))), _name(target.id)]
		if target.id != Agents.PLAYER_ID:
			# The direct victim ALWAYS perceives the blow — a strike on your own body is felt, not
			# seen, so no vision gate applies. (The player proxy has no brain to remember with.)
			target.remember_scored(line, IMP_OUTCOME)
		_fan_room(target.room, line, [target.id], target.position, IMP_OUTCOME)   # witnessed where the victim stands
	else:  # agent_downed — a person struck down is seen by whoever present can see the body fall
		_fan_room(target.room, "%s was struck down." % _name(target.id), [target.id], target.position, IMP_OUTCOME)

## Write `line` into the short_memory of every agent co-located in `room` AND — when the caller gave
## the event a position — standing within its OWN vision_r of `event_pos`. Perception is
## perceiver-centric: the same downing is seen by a keen-eyed watcher and missed by a dim one; still
## no group/faction filter (whoever can see it, friend or stranger, witnesses it). Skips the `except`
## ids and the player proxy. A null event_pos means the caller had no meaningful position for the
## event, so room-wide co-location alone decides. The gate itself is the ONE shared
## Perception.can_perceive (combat plan §M3) — the M2/M3 executor's reflex channel filters raw
## EventBus events through the identical function, so witnessing and reflexes can never disagree.
## `importance` is the fan block's AUTHORED ladder value (P1), written on every witness row.
func _fan_room(room: String, line: String, except: Array, event_pos: Variant = null,
		importance: float = IMP_OUTCOME) -> void:
	for a in Agents.all():
		if a.id == Agents.PLAYER_ID or a.id in except:
			continue
		if not Perception.can_perceive(a, room, event_pos):
			continue
		a.remember_scored(line, importance)

func _name(id: String) -> String:
	var a: Agent = Agents.get_agent(id)
	return a.display_name if a != null and a.display_name != "" else id
