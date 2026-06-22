extends Node
## The player's prayer verb (autoload `PrayerService`). The player petitions a god; the
## sidecar (mock now, LLM later) judges the prayer and returns one of four canon outcomes —
## Granted (应允), Cryptic (神秘应答), Ignored (无应), Punished (惩罚). This service builds the
## adjudication request (god + the player's standing + the prayer text), routes it through
## SidecarBridge, applies the mechanical effects, updates per-god standing, and logs a
## first-class `player_prayer` event so the overseer treats prayer like any other player
## involvement. (Autoload Node, so bare autoload refs are fine at runtime — see PlayerActions.)

## Per-god favor. Rises when a god answers well, falls when it punishes. Clamped -10..10.
var standing: Dictionary = {}   # god_id -> float

func get_standing(god_id: String) -> float:
	return float(standing.get(god_id, 0.0))

## Offer a prayer. Returns the full outcome dict for the UI:
##   { ok, god, outcome, outcome_zh, severity, message, struck_down }
## ok is false (with `reason`) when the god id or prayer is malformed.
func pray(god_id: String, text: String) -> Dictionary:
	if not GodDB.has(god_id):
		return {"ok": false, "reason": "unknown god '%s'" % god_id}
	var action := {"actor": "player", "verb": "pray", "args": {"god": god_id, "prayer": text}}
	var check: Dictionary = ActionSchema.validate(action)
	if not check["ok"]:
		return {"ok": false, "reason": String(check["reason"])}

	var verdict: Dictionary = SidecarBridge.adjudicate_prayer({
		"god": god_id, "prayer": text, "standing": get_standing(god_id),
	})
	var outcome := String(verdict.get("outcome", "ignored"))
	var severity := int(verdict.get("severity", 0))
	var god: Dictionary = GodDB.get_def(god_id)
	var struck_down := _apply_effects(god_id, god, outcome, severity)
	var message := _compose_message(god, outcome, severity)

	EventBus.emit_event("player_prayer", {
		"actor": "player", "god": god_id, "outcome": outcome, "severity": severity,
	})
	return {
		"ok": true, "god": god_id, "outcome": outcome,
		"outcome_zh": String(verdict.get("outcome_zh", "")),
		"severity": severity, "message": message, "struck_down": struck_down,
	}

## Apply the mechanical consequences. Returns true if the punishment struck the player down.
func _apply_effects(god_id: String, god: Dictionary, outcome: String, severity: int) -> bool:
	var opposes_cult := bool(god.get("opposes_cult", false))
	match outcome:
		"granted":
			WorldState.adjust(&"fatigue", -15.0)
			_bump_standing(god_id, 2.0)
			if opposes_cult:
				# A rival power lends strength against the descent.
				SummoningPlan.add_impede(8.0 * severity, "divine favor: %s" % god_id)
			elif god_id == "outer_god":
				# The descending god grants power, but you have fed its gate.
				WorldState.adjust(&"corruption", 12.0)
				WorldState.adjust(&"cult_readiness", 8.0)
			else:
				# Canon invariant: the only pro-cult god IS the 外神. A future god that is
				# neither opposing nor the outer god would grant with no world-tier effect.
				push_warning("PrayerService: '%s' granted but is neither opposing nor the outer god" % god_id)
		"cryptic":
			_bump_standing(god_id, 1.0)
		"ignored":
			pass
		"punished":
			WorldState.adjust(&"corruption", 10.0 * severity)
			WorldState.adjust(&"panic", 5.0 * severity)
			WorldState.adjust(&"fatigue", 8.0 * severity)
			_bump_standing(god_id, -2.0 * severity)
			if severity >= 3:
				EventBus.emit_event("player_struck_down", {"actor": "player", "god": god_id})
				return true
	return false

func _bump_standing(god_id: String, delta: float) -> void:
	standing[god_id] = clampf(get_standing(god_id) + delta, -10.0, 10.0)

## Flavor line per (register, outcome). The mechanical effects are already applied; this is
## just the god's voice for the panel.
func _compose_message(god: Dictionary, outcome: String, severity: int) -> String:
	var god_name := String(god.get("name", "the god"))
	var register := String(god.get("register", ""))
	match outcome:
		"granted":
			if register == "ravenous":
				return "%s answers. Power floods you — and somewhere, a gate widens." % god_name
			return "%s grants your plea; strength settles into your bones." % god_name
		"cryptic":
			if register == "tarot":
				return "The Fool turns a card — The Moon, reversed. What you seek wears a borrowed face."
			return "%s answers, but the meaning is veiled, like a shape behind frosted glass." % god_name
		"ignored":
			return "You speak into the dark. Nothing answers."
		"punished":
			if severity >= 3:
				return "%s does not suffer your insolence. The world goes white, then black." % god_name
			return "%s recoils from your words; cold dread floods in where the prayer should have gone." % god_name
	# Any future/unknown outcome (e.g. an LLM register we don't model yet) falls through here.
	return "%s answers in a way you cannot parse." % god_name

func reset() -> void:
	standing.clear()

func to_dict() -> Dictionary:
	return {"standing": standing.duplicate(true)}

func from_dict(d: Dictionary) -> void:
	standing = (d.get("standing", {}) as Dictionary).duplicate(true)
