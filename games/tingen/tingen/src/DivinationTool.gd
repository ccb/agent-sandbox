class_name DivinationTool
extends OccultTool
## Divination (占卜): a vague directional hint biased toward the district that actually
## holds the true primary_ritual_site — never the site's name. At high corruption the
## bias can flip to a wrong district (mislead).

## Site -> a directional line that does NOT contain the site id.
const SITE_HINTS: Dictionary = {
	"iron_cross_warehouse": "Cold iron and rust — look where cargo waits unclaimed.",
	"st_selena_crypt": "Old stone and older prayers — look beneath the cathedral.",
	"harbor_customs_house": "Salt and ledgers — look where the harbor counts its dead.",
}

func _perform() -> Dictionary:
	var true_site := String(_al("WorldManager").slots.get("primary_ritual_site", "iron_cross_warehouse"))
	var lead := String(SITE_HINTS.get(true_site, "The city's drift is hard to read."))
	return {"ok": true, "kind": "divination", "text": lead, "lead": lead, "mislead": false}

func _apply_risk(result: Dictionary, rng: RandomNumberGenerator, corruption: float) -> void:
	if not OccultRisk.roll_mislead(rng, corruption):
		return
	# Mislead: point at a different site's hint.
	var true_site := String(_al("WorldManager").slots.get("primary_ritual_site", ""))
	for site in SITE_HINTS.keys():
		if site != true_site:
			result["lead"] = String(SITE_HINTS[site])
			result["text"] = result["lead"]
			result["mislead"] = true
			return
