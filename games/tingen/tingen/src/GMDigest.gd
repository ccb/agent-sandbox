class_name GMDigest
extends RefCounted
## Deterministic GM digest builder — the engine-side half of the GM panel's hybrid log.
##
## `build_digest` is a PURE static function of an event batch (EventBus shape:
## {type, data, day, minute, beat, seq}): notable beats each become one readable line, the
## agent-deliberation firehose collapses to a single aggregated count, and vetoes/rejections to
## another. No autoload access, no clock, no RNG — the same batch always digests identically, so
## it unit-tests without a timer and renders instantly whether or not the LLM sidecar is up.
##
## Phrasing is ADAPTED from DebugLogPanel._story_line but deliberately NOT shared with it: the
## debug overlay narrates single events live (and may look up live display names), while this
## digest summarizes a 30s window purely from the event data. Keeping them decoupled lets either
## evolve without breaking the other.

## The raw agent-deliberation events (see DebugLogPanel.AGENT_ACTION_TYPES): per-line they are
## noise; the digest reports only how many there were.
const NOISE_TYPES: Array = ["agent_action", "agent_action_amended", "overseer_directive"]
## Critic vetoes + schema/directive rejections: aggregated to one count line.
const VETO_TYPES: Array = ["action_vetoed", "action_rejected", "directive_rejected"]

## events: EventBus event dicts (already filtered to the window since the last digest).
## Returns {"lines": Array[String], "stats": Dictionary}. Empty batch -> empty lines.
static func build_digest(events: Array) -> Dictionary:
	var lines: Array = []
	var noise: int = 0
	var vetoes: int = 0
	var casts: int = 0
	var stats: Dictionary = {
		"events": events.size(),
		"moves": 0, "said": 0, "items": 0, "attacks": 0, "world_vars": 0, "combat": 0,
	}
	for ev in events:
		if typeof(ev) != TYPE_DICTIONARY:
			continue
		var t := String((ev as Dictionary).get("type", ""))
		var data_v: Variant = (ev as Dictionary).get("data", {})
		var data: Dictionary = data_v if data_v is Dictionary else {}
		if t in NOISE_TYPES:
			noise += 1
			continue
		if t in VETO_TYPES:
			vetoes += 1
			continue
		match t:
			"agent_moved_room":
				lines.append("%s moved from the %s to the %s." % [
					_name(String(data.get("actor", ""))),
					_words(String(data.get("from", ""))), _words(String(data.get("to", "")))])
				stats["moves"] += 1
			"npc_said":
				lines.append('%s: "%s"' % [
					_name(String(data.get("agent", ""))), String(data.get("text", ""))])
				stats["said"] += 1
			"item_gathered":
				lines.append("%s picked up %s." % [
					_name(String(data.get("actor", ""))), _words(String(data.get("item_id", "")))])
				stats["items"] += 1
			"material_deposited":
				lines.append("%s laid %s at the altar." % [
					_name(String(data.get("actor", ""))), _words(String(data.get("item_id", "")))])
				stats["items"] += 1
			"agent_attacked":
				lines.append("%s was struck (hp %d)." % [
					_name(String(data.get("target", ""))), int(data.get("target_hp", 0))])
				stats["attacks"] += 1
			"agent_downed":
				lines.append("%s was downed." % _name(String(data.get("target", ""))))
				stats["attacks"] += 1
			# Combat mode transitions + the transform reveal read as story beats (combat plan
			# §M4): a fight starting/ending is one line each; the transform names no form — the
			# digest reports that someone changed, not what the data calls the new shape.
			"combat_started":
				lines.append("%s entered a fight." % _name(String(data.get("agent", ""))))
				stats["combat"] += 1
			"combat_ended":
				lines.append("%s left the fight." % _name(String(data.get("agent", ""))))
				stats["combat"] += 1
			"transformed":
				lines.append("%s became something else." % _name(String(data.get("agent", ""))))
				stats["combat"] += 1
			# A data-authored deed (DeedRunner, combat plan §M6) narrates itself: the event
			# carries its authored fact_line verbatim — the digest adds no reading of it.
			"deed_performed":
				var deed_line := String(data.get("line", ""))
				if deed_line != "":
					lines.append(deed_line)
			# Individual casts are frame-rate noise at digest scale — aggregated to one count
			# line below (finished/interrupted stay unnarrated: one cast, one count).
			"ability_cast_started":
				casts += 1
			"world_var_changed":
				lines.append("%s: %s → %s." % [
					_words(String(data.get("var", ""))),
					str(data.get("from", "")), str(data.get("to", ""))])
				stats["world_vars"] += 1
			_:
				pass   # other event types are neither narrated nor counted as noise
	# The aggregates go LAST so the story lines lead the entry.
	if casts > 0:
		lines.append("%d combat art%s loosed." % [casts, "" if casts == 1 else "s"])
	if vetoes > 0:
		lines.append("%d proposal%s vetoed or rejected." % [vetoes, "" if vetoes == 1 else "s"])
	if noise > 0:
		lines.append("%d agent action%s this period." % [noise, "" if noise == 1 else "s"])
	stats["agent_actions"] = noise
	stats["vetoes"] = vetoes
	stats["casts"] = casts
	return {"lines": lines, "stats": stats}

## An agent id -> a short readable name: titlecase the last id segment ("fishwife_dalia" -> "Dalia").
## PURE (no Agents autoload lookup, unlike DebugLogPanel._name), so the digest stays a pure function.
static func _name(agent_id: String) -> String:
	if agent_id == "":
		return "Someone"
	var seg := agent_id.get_slice("_", agent_id.get_slice_count("_") - 1)
	return seg.capitalize() if seg != "" else agent_id.capitalize()

## An id -> readable words ("cathedral_crypt" -> "cathedral crypt").
static func _words(id: String) -> String:
	return id.replace("_", " ") if id != "" else "?"
