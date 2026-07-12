extends Node
## Runtime per-agent LLM model selection (autoload `ModelConfig`) — a TEMPORARY debug control.
##
## The emergent NPC behavior only shows on a capable model, so you need to run specific characters (the
## cult) on a stronger brain than the cheap default. The ModelPanel UI writes here; HttpSidecar reads
## `model_for(agent_id)` and stamps it on each /decide + /converse request, so the sidecar uses the
## per-agent model (absent → the sidecar's own env default).
##
## TODO: this autoload + its panel are a stopgap. After Tingen ships and we do the cognition refactor,
## replace them with a proper engine interface + a per-character node carrying its own model/tier.

## The "GM" row is the DEFAULT model — used by any agent without a per-character override.
const MODELS: Array[String] = ["claude-haiku-4-5", "claude-sonnet-4-6", "claude-opus-4-8"]

var default_model: String = "claude-sonnet-4-6"   # Sonnet by default so the emergent behavior shows
var overrides: Dictionary = {}                    # agent_id -> model (absent = use default_model)

## The model this agent's sidecar call should use: its override if set, else the GM/default.
func model_for(agent_id: String) -> String:
	return String(overrides.get(agent_id, default_model))

## Set the GM/default model (ignored if not a known model).
func set_default(m: String) -> void:
	if m in MODELS:
		default_model = m

## Override one agent's model. Pass "" or "default" to clear the override (fall back to the default).
func set_override(agent_id: String, m: String) -> void:
	if m == "" or m == "default":
		overrides.erase(agent_id)
	elif m in MODELS:
		overrides[agent_id] = m
