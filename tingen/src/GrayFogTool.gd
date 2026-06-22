class_name GrayFogTool
extends OccultTool
## Gray-Fog Reconstruction (灰雾重构): the precious, hard-capped reading. Surfaces the
## single most useful directional lead — never the answer. (The Gray-Fog Hypothesis Board
## is cut; this survives as a costed perception verb.)

func _perform() -> Dictionary:
	var lead := "Through the fog, the threads converge on the iron district — but not on which door."
	return {"ok": true, "kind": "gray_fog", "text": lead, "lead": lead, "mislead": false}

func _apply_risk(result: Dictionary, rng: RandomNumberGenerator, corruption: float) -> void:
	if OccultRisk.roll_mislead(rng, corruption):
		result["lead"] = "Through the fog, a false convergence pulls you the wrong way."
		result["text"] = result["lead"]
		result["mislead"] = true
