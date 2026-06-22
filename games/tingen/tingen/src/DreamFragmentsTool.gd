class_name DreamFragmentsTool
extends OccultTool
## Dream Fragments (梦境碎片): a soft cross-association nudging toward the thread, paid in
## exhaustion (high fatigue, zero attention). Produces a dream_residue reagent on success.

func _perform() -> Dictionary:
	var lead := "In the dream, two strangers carried the same gray salt to the same dark door."
	return {"ok": true, "kind": "dream", "text": lead, "lead": lead, "mislead": false}

func _apply_risk(result: Dictionary, rng: RandomNumberGenerator, corruption: float) -> void:
	if OccultRisk.roll_mislead(rng, corruption):
		result["lead"] = "In the dream, the wrong face wears the cult's mark."
		result["text"] = result["lead"]
		result["mislead"] = true
