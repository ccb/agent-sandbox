class_name SidecarClient
extends RefCounted
## Abstract boundary to the LLM brain. The substrate hands the client a batch of
## perception snapshots and receives one proposed action per snapshot. All
## nondeterminism (LLM calls, batching, caching) lives behind this interface in concrete
## subclasses; the substrate stays deterministic. Subclasses: MockSidecar (tests/offline),
## and later HttpSidecar (talks to the Python service).

## True when the client can serve proposals (a network client may be still connecting).
func is_ready() -> bool:
	return true

## Deliberation stagger factor (orchestrator/GM design §4.1): agents deliberate only on beats where
## md5(id) % k == beat % k, CONTINUING their committed action in between. Decorrelation is a property
## of the BRAIN — N identical-context LLM calls converge on the modal action, so the LLM client
## staggers (k=2); a deterministic brain (mock/ambient) gains nothing from it, so the base is 1
## (deliberate every beat), which keeps every scripted test and the offline demo unchanged.
func stagger_k() -> int:
	return 1

## snapshots: Array of perception dicts (each must carry an "agent_id"). Returns an
## Array of action dicts aligned 1:1 with `snapshots`. Base returns idle for each.
func propose(snapshots: Array) -> Array:
	var out: Array = []
	for s in snapshots:
		out.append({"actor": String((s as Dictionary).get("agent_id", "")), "verb": "idle", "args": {}})
	return out

## Adjudicate a player's prayer. `request` carries { god, prayer, standing }. Returns
## { god, outcome, outcome_zh, severity, score }. Base is a neutral "ignored"; MockSidecar
## models the four canon outcomes deterministically and a future HttpSidecar defers to the LLM.
func adjudicate_prayer(request: Dictionary) -> Dictionary:
	return {
		"god": String(request.get("god", "")),
		"outcome": "ignored", "outcome_zh": "无应", "severity": 0, "score": 0,
	}

## One player↔NPC conversation turn (design §2). `request` is built by Perception.converse_request and
## carries the agent's persona/goals/memory + the player's utterance. Returns
## { say: String, action: Dictionary|null, replies: Array }. The `say` is spoken verbatim (never
## governed); the optional `action` has already passed the hard veto in the brain. Base is a no-op.
func converse(_request: Dictionary) -> Dictionary:
	return {"say": "", "action": null, "replies": []}

## Narrate one GM digest into a short player-facing paragraph (the GM panel's hybrid seam).
## `request` carries { events: Array[String], world: Dictionary }. Returns { summary: String };
## an EMPTY dict — the base/offline default — means "no narration available" and the panel keeps
## its deterministic digest. Only HttpSidecar (live LLM) produces real summaries; MockSidecar can
## script one for tests.
func narrate(_request: Dictionary) -> Dictionary:
	return {}
