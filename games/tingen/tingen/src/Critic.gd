class_name Critic
extends RefCounted
## The "catch & kill" guardrail. Given a schema-valid proposed action and its agent,
## returns a verdict on three axes:
##   - legality (state): is the verb possible for this agent right now?
##   - coherence: does it fit the agent's identity / role?
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

	# --- Coherence / state legality ---
	# A rite is work only an agent with a TASK can do (a legality gate, mirrored in governance). WHO
	# recruits is NOT gated here — that's behavioral: a character recruits only if its persona drives it
	# (the LLM decides), so there is no hard "may recruit" check.
	if verb == "perform_ritual_step" and agent.task.is_empty():
		return _verdict("veto", "%s has no task that involves a rite" % agent.id)
	# `engage` mirrors the victim's attack gate: the intended victim never opens hostilities
	# (disengage/protect stay open — fleeing a fight or shielding someone is coherent for prey).
	if agent.role == "victim" and verb in ["perform_ritual_step", "recruit", "attack", "engage"]:
		return _verdict("veto", "the intended victim would not take such an action")
	# `cast_ability` is a combat act (combat plan §M4): legal from a PROPOSAL only for an agent
	# already in a fight. Overseer directives bypass the Critic by design (AgentRuntime
	# _apply_directive checks only the schema), so the GM/Director can still force a cast on a
	# not-yet-fighting agent — the corruption loss-of-control transform.
	if verb == "cast_ability" and not agent.in_combat:
		return _verdict("veto", "%s is not in a fight — no art to work outside one" % agent.id)
	# In a LIVE fight the executor is the damage channel (combat plan §M6, the M4 live-gate
	# finding): an engaged LLM keeps proposing the legacy beat-level `attack` each beat, which
	# would land flat damage ON TOP of the frame-rate abilities — double-dipping. AMEND the
	# proposal into the intent it is really expressing: `engage {target}`, keeping a standing
	# style (the re-mask keeps fighting HOW it was fighting; _engage refreshes set_at_beat).
	# Gated on a live executor: an in-combat agent with no executor bound (no body fighting for
	# it yet) still has only the legacy attack channel, so that proposal stands unchanged.
	if verb == "attack" and agent.in_combat and CombatExecutor.for_agent(agent.id) != null:
		var amended: Dictionary = {"actor": agent.id, "verb": "engage",
			"args": {"target": String(args.get("target", ""))}}
		var standing_style := String(agent.combat_intent.get("style", ""))
		if standing_style != "":
			(amended["args"] as Dictionary)["style"] = standing_style
		if action.has("thought"):
			amended["thought"] = action["thought"]
		return _verdict("amend",
			"a live fight's damage flows through the executor — attack re-expressed as engage", amended)

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
