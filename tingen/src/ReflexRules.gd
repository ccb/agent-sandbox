class_name ReflexRules
extends RefCounted
## Compiled-reflex rule engine (combat plan §M3) — PURE and static, the M9 vector surface.
##
## `evaluate(rules, event, self_state, now_ms, fired_counts)` matches data-authored reflex rows
## against ONE perceived event (or a bare frame evaluation, event = {}) and returns the due
## reactions [{do, delay_ms, fire_at_ms, rule_index}]. Everything is plain Dictionaries and ms
## ints — NO nodes, NO autoloads, NO randomness, inputs never mutated. The CALLER owns every
## clock and every piece of state: it feeds perceived events only (the shared
## Perception.can_perceive gate — reflexes react to what the agent can SEE, never to the raw
## world log), it increments fired_counts when it SCHEDULES a reaction, and it executes the
## reaction on its own executor clock when fire_at_ms comes due.
##
## Trigger vocabulary (plan §M3):
##   telegraph {of: ability class | ability: id, at_me: bool} — a perceived cast_started
##   hp_below {value: frac}   — reads SELF STATE (hp_frac), so it fires on any evaluation
##   ally_downed              — a perceived downing of someone the agent isn't fighting
##   band_entered {band}      — the fight crossed into melee/near/far (tactical layer reports)
##   cooldown_ready {ability} — a watched cooldown elapsed
## Action vocabulary (executed by the executor, never here): cast {ability}, dodge {dir:
## away|side}, style {style}, flee.
##
## delay_ms is the authored human-feel reaction time, clamped to [150, 800]; max_fires (absent
## or 0 = unlimited) is enforced against the caller-owned fired_counts {rule_index: fires}.

const DELAY_MIN_MS: int = 150
const DELAY_MAX_MS: int = 800
const DEFAULT_DELAY_MS: int = 250

static func evaluate(rules: Array, event: Dictionary, self_state: Dictionary, now_ms: int, fired_counts: Dictionary) -> Array:
	var due: Array = []
	for i in range(rules.size()):
		if typeof(rules[i]) != TYPE_DICTIONARY:
			continue
		var rule: Dictionary = rules[i]
		var max_fires := int(rule.get("max_fires", 0))
		if max_fires > 0 and int(fired_counts.get(i, 0)) >= max_fires:
			continue
		if not _matches(rule.get("when", {}), event, self_state):
			continue
		var delay := clampi(int(rule.get("delay_ms", DEFAULT_DELAY_MS)), DELAY_MIN_MS, DELAY_MAX_MS)
		var doo: Variant = rule.get("do", {})
		due.append({
			"do": (doo as Dictionary).duplicate(true) if doo is Dictionary else {},
			"delay_ms": delay,
			"fire_at_ms": now_ms + delay,
			"rule_index": i,
		})
	return due

## One trigger row against one event + the agent's own state. Unknown kinds never match —
## authoring drift stays inert instead of misfiring.
static func _matches(when_v: Variant, event: Dictionary, self_state: Dictionary) -> bool:
	if typeof(when_v) != TYPE_DICTIONARY:
		return false
	var when: Dictionary = when_v
	match String(when.get("kind", "")):
		"telegraph":
			if String(event.get("kind", "")) != "telegraph":
				return false
			if when.has("ability") and String(event.get("ability", "")) != String(when.get("ability")):
				return false
			if when.has("of") and String(event.get("class", "")) != String(when.get("of")):
				return false
			if bool(when.get("at_me", false)) and not bool(event.get("at_me", false)):
				return false
			return true
		"hp_below":
			return float(self_state.get("hp_frac", 1.0)) < float(when.get("value", 0.0))
		"ally_downed":
			return String(event.get("kind", "")) == "ally_downed"
		"band_entered":
			return String(event.get("kind", "")) == "band_entered" \
				and String(event.get("band", "")) == String(when.get("band", ""))
		"cooldown_ready":
			return String(event.get("kind", "")) == "cooldown_ready" \
				and String(event.get("ability", "")) == String(when.get("ability", ""))
	return false
