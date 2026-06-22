class_name ResidueSightTool
extends OccultTool
## Residue Sight / Spirit Vision (灵视): reveals what lingers at the current place — for
## the slice, a local directional impression about recent agent activity. (Hidden-clue
## reveal on Interactables is wired in the scene-integration plan.)

func _perform() -> Dictionary:
	var lead := "Something was done here recently — the air still flinches."
	return {"ok": true, "kind": "residue", "text": lead, "lead": lead, "mislead": false}

func _apply_risk(result: Dictionary, rng: RandomNumberGenerator, corruption: float) -> void:
	if OccultRisk.roll_mislead(rng, corruption):
		result["text"] = "You sense residue — but it may be your own dread echoing back."
		result["mislead"] = true
