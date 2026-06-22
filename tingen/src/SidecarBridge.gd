extends Node
## The single seam between the substrate and the LLM brain (autoload `SidecarBridge`).
## Holds one active SidecarClient, chosen at boot:
##   - TINGEN_SIDECAR_URL set -> HttpSidecar, the real LLM brain (Python agent-sidecar over HTTP),
##     with AmbientSidecar goal-seeking as its built-in fallback so nothing freezes if it is down;
##   - otherwise           -> AmbientSidecar, the offline brain that moves the district with no API.
## Tests pin a MockSidecar explicitly for deterministic scripted behavior. The agent runtime calls
## `propose(snapshots)` here and nowhere else.

const SIDECAR_URL_ENV: String = "TINGEN_SIDECAR_URL"

var client: SidecarClient = null

func _ready() -> void:
	if client == null:
		var url := OS.get_environment(SIDECAR_URL_ENV) if OS.has_environment(SIDECAR_URL_ENV) else ""
		if url != "":
			client = HttpSidecar.new(url)
			print("[sidecar] live brain: HttpSidecar -> %s" % url)
		else:
			client = AmbientSidecar.new()

func _exit_tree() -> void:
	if client != null and client.has_method("shutdown"):
		client.call("shutdown")

func set_client(c: SidecarClient) -> void:
	client = c

func is_ready() -> bool:
	return client != null and client.is_ready()

func propose(snapshots: Array) -> Array:
	if client == null:
		return []
	return client.propose(snapshots)

func adjudicate_prayer(request: Dictionary) -> Dictionary:
	if client == null:
		return {"god": String(request.get("god", "")), "outcome": "ignored", "outcome_zh": "无应", "severity": 0, "score": 0}
	return client.adjudicate_prayer(request)
