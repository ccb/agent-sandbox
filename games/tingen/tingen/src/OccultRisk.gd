class_name OccultRisk
extends RefCounted
## Seeded RNG primitives the occult tools call. Does NOT decide how risk manifests (each
## tool's _apply_risk does that) — it only rolls deterministically so tests are stable.

## True when this use should mislead. Probability rises with corruption above a floor.
static func roll_mislead(rng: RandomNumberGenerator, corruption: float) -> bool:
	if corruption <= 40.0:
		return false
	var p: float = clampf((corruption - 40.0) / 60.0, 0.0, 0.9)
	return rng.randf() < p

## Symmetric noise in [-magnitude, magnitude].
static func noise(rng: RandomNumberGenerator, magnitude: float) -> float:
	return (rng.randf() * 2.0 - 1.0) * magnitude
