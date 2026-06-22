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
