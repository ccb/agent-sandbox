class_name MockSidecar
extends SidecarClient
## Deterministic test/offline sidecar. Returns a scripted action per actor; agents with
## no script idle. A scripted value may be a single action dict (returned every beat) or
## an Array used as a queue (one popped per beat, idle when empty). Lets headless tests
## drive exact agent behavior with no LLM.

var scripted: Dictionary = {}   # actor_id -> action dict OR Array[action dict]

func set_action(actor_id: String, action: Variant) -> void:
	scripted[actor_id] = action

func clear() -> void:
	scripted.clear()

func propose(snapshots: Array) -> Array:
	var out: Array = []
	for s in snapshots:
		var actor := String((s as Dictionary).get("agent_id", ""))
		out.append(_next_for(actor))
	return out

func _next_for(actor: String) -> Dictionary:
	if not scripted.has(actor):
		return _idle(actor)
	var v: Variant = scripted[actor]
	if typeof(v) == TYPE_ARRAY:
		var q: Array = v
		if q.is_empty():
			return _idle(actor)
		return (q.pop_front() as Dictionary).duplicate(true)
	return (v as Dictionary).duplicate(true)

func _idle(actor: String) -> Dictionary:
	return {"actor": actor, "verb": "idle", "args": {}}

# --- Prayer adjudication (deterministic stand-in for the LLM's judgment) -----------------
# Mirrored EXACTLY by agent-sidecar/prayer_adjudicator.py — keep the marker lists,
# thresholds, and the decision order identical, or the parity test (E4) fails.
const PRAYER_RESPECT: PackedStringArray = [
	"please", "humbly", "beseech", "guide", "protect", "mercy",
	"grant", "thank", "praise", "honor", "i offer", "i beg",
]
const PRAYER_DISRESPECT: PackedStringArray = [
	"demand", "command", "obey", "serve me", "worthless",
	"weak", "kneel", "i curse", "mock", "useless",
]
const GRANT_THRESHOLD: int = 3
const CRYPTIC_THRESHOLD: int = 1
const OUTCOME_ZH: Dictionary = {
	"granted": "应允", "cryptic": "神秘应答", "ignored": "无应", "punished": "惩罚",
}

## Judge one prayer. request: { god, prayer, standing }. Returns
## { god, outcome, outcome_zh, severity, score }. Pure + deterministic.
func adjudicate_prayer(request: Dictionary) -> Dictionary:
	var god_id := String(request.get("god", ""))
	var text := String(request.get("prayer", "")).to_lower()
	var standing := float(request.get("standing", 0.0))
	var god: Dictionary = GodDB.get_def(god_id)

	var respect := _count_markers(text, PRAYER_RESPECT)
	var disrespect := _count_markers(text, PRAYER_DISRESPECT)
	var domain_hit := _domain_hit(text, god.get("domain", []))

	var score := respect * 2 - disrespect * 5
	score += 1 if domain_hit else 0
	score += int(clampf(standing, -3.0, 3.0))

	var register := String(god.get("register", ""))
	var wrath := float(god.get("wrath", 0.5))

	var outcome := "ignored"
	var severity := 0
	if disrespect > 0:
		outcome = "punished"
		severity = clampi(disrespect + int(round(wrath * 2.0)), 1, 3)
	elif register == "tarot":
		outcome = "cryptic"          # the Fool answers obliquely, if at all
		severity = 1
	elif score >= GRANT_THRESHOLD:
		outcome = "granted"
		severity = 2 if god_id == "outer_god" else 1
	elif score >= CRYPTIC_THRESHOLD:
		outcome = "cryptic"
		severity = 1
	else:
		outcome = "ignored"
		severity = 0

	return {
		"god": god_id, "outcome": outcome,
		"outcome_zh": String(OUTCOME_ZH.get(outcome, "")),
		"severity": severity, "score": score,
	}

func _count_markers(text: String, markers: PackedStringArray) -> int:
	var n := 0
	for m in markers:
		if text.contains(m):
			n += 1
	return n

func _domain_hit(text: String, domain: Array) -> bool:
	for kw in domain:
		if text.contains(String(kw).to_lower()):
			return true
	return false
