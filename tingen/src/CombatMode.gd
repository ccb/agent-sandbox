extends Node
## Combat-mode transitions (autoload `CombatMode`) — combat plan §M1.
##
## The ONE place the `in_combat` mask flips, so the transition events are never emitted twice
## and never forgotten. Entering combat is a FLAG + EVENT only: no form/sprite swap, no kit
## application, no damage — transformation is an ability (data/abilities.json `transform`
## effects), cast later by the tactical layer, never a side effect of being hit.
## `combat_started`/`combat_ended` carry {agent} alone; whatever form the fight takes is
## decided by abilities, not at combat start.
##
## Drivers: Agent.take_damage (damage flips the mask on, plan §0) and ActionCommit._disengage
## (the LLM's intent verb flips it off). Both transitions are idempotent.

func enter_combat(agent: Agent) -> void:
	if agent == null or agent.in_combat:
		return
	agent.in_combat = true
	# One-shot transition marker (P1): the next deliberation snapshot learns the flip just happened.
	agent.mark_transition("just_entered_combat")
	EventBus.emit_event("combat_started", {"agent": agent.id})

func exit_combat(agent: Agent) -> void:
	if agent == null or not agent.in_combat:
		return
	agent.in_combat = false
	# Leaving the fight abandons any cast still PARKED for the executor (combat plan §M4):
	# combat scratch must never survive the mask it belongs to, or a later, unrelated fight
	# would open with a stale GM-ordered art.
	agent.pending_cast = ""
	agent.mark_transition("just_left_combat")   # one-shot transition marker (P1)
	EventBus.emit_event("combat_ended", {"agent": agent.id})
