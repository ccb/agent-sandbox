class_name Critic
extends RefCounted
## The "catch & kill" guardrail. Given a schema-valid proposed action and its agent,
## returns a verdict on three axes:
##   - legality (state): is the verb possible for this agent right now?
##   - coherence: does it fit the agent's identity / faction / role?
##   - interestingness: does it advance or complicate the thread (vs. dead repetition)?
## Verdict ∈ { approve, amend, veto }. `amend` returns a corrected `action`. The runtime
## turns veto (and, for the slice, reroll-equivalents) into a schedule fallback.
## Deterministic and pure — the eventual LLM critic produces the same verdict shape.

## Resolve an autoload by name. In the headless `-s` test harness, `class_name` scripts
## compile before autoload singletons register, so a bare global reference fails to
## compile. Look it up on the scene tree root at call time instead.
static func _al(autoload_name: String) -> Node:
	return (Engine.get_main_loop() as SceneTree).root.get_node("/root/" + autoload_name)

static func _verdict(v: String, reason: String = "", action: Dictionary = {}) -> Dictionary:
	return {"verdict": v, "reason": reason, "action": action}

static func review(action: Dictionary, agent: Agent) -> Dictionary:
	var verb := String(action.get("verb", ""))
	var args: Dictionary = action.get("args", {})

	# --- Downed agents are incapacitated: nothing but idle is physically possible. This
	# overrides every other axis (a felled cultist cannot crawl to the rite or swing), so it
	# runs first. take_damage()/_attack downs the body; only idle survives until it is helped up.
	if agent.downed and verb != "idle":
		return _verdict("veto", "%s is downed and can only idle" % agent.id)

	# --- Coherence / state legality by role + faction ---
	var is_cultist := agent.faction == "cult"

	if verb == "perform_ritual_step":
		if not is_cultist:
			return _verdict("veto", "%s is not a cultist and cannot perform a ritual step" % agent.id)
	if verb == "recruit":
		if not is_cultist:
			return _verdict("veto", "%s is not a cultist and cannot recruit" % agent.id)
	if agent.role == "victim" and verb in ["perform_ritual_step", "recruit", "attack"]:
		return _verdict("veto", "the intended victim would not act as a cultist")

	# --- No-chance-exposure invariant ---
	if verb == "report" and _is_exposing(args) and not _al("Overseer").allows_exposure():
		return _verdict("veto", "the cell cannot be exposed without the player's involvement")

	# --- Interestingness: kill an agent re-issuing the identical action it just did. ---
	if not agent.current_action.is_empty() \
			and String(agent.current_action.get("verb", "")) == verb \
			and agent.current_action.get("args", {}) == args \
			and verb in ["hide", "idle"]:
		return _verdict("veto", "repeating a passive action is dramatically inert")

	return _verdict("approve")

## A report "exposes" the cell when it informs the law (e.g. the Nighthawks) or names the
## cult to an outside party.
static func _is_exposing(args: Dictionary) -> bool:
	var to := String(args.get("to", "")).to_lower()
	var info := String(args.get("info", "")).to_lower()
	if to in ["nighthawks", "police", "church", "authorities"]:
		return true
	return "cult" in info or "ritual" in info or "summon" in info
