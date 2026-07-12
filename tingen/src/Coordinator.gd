extends Node
## The GM's COORDINATOR role (autoload `Coordinator`; orchestrator/GM design §4.2, Phase 2) — a
## deterministic work partition over the agents sharing a task. Each query allocates the task's
## outstanding materials across the task's living agents: carriers keep what they already hold
## (deliver, don't re-fetch), then unclaimed materials go to unallocated agents in stable id order.
##
## The allocation is PUBLISHED as a perception FACT ("the plan currently allocates to you: candle"),
## never a command — the LLM still chooses in character, so coordination emerges from information,
## not force (the Critic does not enforce focus). Pure function of live state (SummoningPlan ledger +
## the registry), so it is replay-deterministic and needs no per-beat cache; no group/faction branch —
## ANY set of agents sharing a `task.ritual` is partitioned identically.
##
## The Narrator role lives in GMPanel; the Director role is Overseer+Critic. A future LLM GM replaces
## THIS function behind the same `focus` seam (design §4, Phase 3).

## The allocation entry for one agent: {"subtask": item_id, "why": "you carry it"|"unclaimed"},
## or {} when the agent has no task, is downed, is IN COMBAT (combat plan §M4: a body fighting
## for its life is not a courier this beat — the work partition routes around it), or every
## material is claimed/deposited.
func focus_for(agent_id: String) -> Dictionary:
	var me: Agent = Agents.get_agent(agent_id)
	if me == null or me.downed or me.in_combat or me.task.is_empty():
		return {}
	var ritual := String(me.task.get("ritual", ""))
	if ritual == "":
		return {}
	# Outstanding materials (requirement - deposited), flattened and stable-sorted. NOTE: counts are
	# flattened to ONE subtask per item id — correct while every requirement is 1 (rituals.json and
	# CitySummoning both pin 1/1/1, and a suite test asserts they agree). If multi-count requirements
	# return, expand to one subtask per outstanding UNIT here.
	var left: Array = []
	var outstanding: Dictionary = SummoningPlan.materials_outstanding()
	for item_id in outstanding:
		if int(outstanding[item_id]) > 0:
			left.append(String(item_id))
	if left.is_empty():
		return {}
	left.sort()
	# The task group: every living agent working the same ritual, in stable id order.
	var group: Array = []
	for other in Agents.all():
		if not other.downed and String(other.task.get("ritual", "")) == ritual:
			group.append(other.id)
	group.sort()
	var alloc: Dictionary = {}   # agent_id -> {subtask, why}
	# Pass 1 — carried materials are CLAIMED (they cannot be fetched from the world, whoever holds
	# them); each carrier is allocated the first material it holds. A carrier holding two has both
	# claimed but only one allocated — the second is in its pack either way.
	for item_id in left.duplicate():
		for gid in group:
			var ga: Agent = Agents.get_agent(gid)
			if ga.item_count(String(item_id)) > 0:
				if not alloc.has(gid):
					alloc[gid] = {"subtask": String(item_id), "why": "you carry it"}
				left.erase(item_id)
				break
	# True only when CARRIERS drained the pool — the one case where "everything the site needs is
	# already in someone's hands" is a true statement. Pass 2 merely allocates; a material handed to
	# a peer as its focus still LIES ON THE GROUND, so publishing all_claimed then would be a false
	# fact (review finding).
	var carriers_hold_everything := left.is_empty()
	# Pass 2 — unclaimed materials to unallocated agents, both in stable order. In-combat members
	# are skipped HERE but stayed in the group for pass 1: what a fighter already CARRIES is
	# truly claimed (it rides in their pack, unfetchable — allocating it to a walker would
	# publish a false fact), but a ground material must go to someone free to fetch it.
	for gid in group:
		if left.is_empty():
			break
		if alloc.has(gid):
			continue
		var walker: Agent = Agents.get_agent(gid)
		if walker == null or walker.in_combat:
			continue
		alloc[gid] = {"subtask": String(left.pop_front()), "why": "unclaimed"}
	if alloc.has(agent_id):
		return alloc[agent_id]
	# Unallocated while every outstanding material is in plan-members' HANDS: say that — without
	# this fact an empty-handed agent loops on the empty cache with no way to know why (live
	# playtest finding). Unallocated merely because peers got the remaining ground materials
	# (design §6's "extras get none") stays an empty focus.
	if carriers_hold_everything:
		return {"all_claimed": true}
	return {}
