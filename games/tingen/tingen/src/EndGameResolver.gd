class_name EndGameResolver
extends RefCounted
## The two-gate climax resolver — pure, static, deterministic. Given the manifestation strength
## at the doomsday deadline, it decides which of three endings the run reaches. It is the
## headless-testable seam under the `EndGame` autoload (which is just the pause + overlay shell).
##
## Gate 1 — was the descent (降临) stopped? Per *Lord of the Mysteries* canon, a fully manifested
## outer god (外神) consumes the whole city; there is no heroic fight. So strength above
## STOP_THRESHOLD means the descent completes and everyone dies ("city_dies"), with no combat.
## Gate 2 — did the player survive? A stopped descent leaves a weakened residual to fight
## (CombatEncounter). Winning is "all_good" (descent stopped AND you live); losing is "near_good"
## (descent stopped, but it takes you). Player interference is what drives strength under the
## threshold (Gate 1) and then tips the residual fight from lethal to survivable (Gate 2).

const STOP_THRESHOLD: float = 60.0

## Resolve the run. Returns { outcome, win, rounds, player_hp_left, strength } where
## outcome ∈ { "city_dies", "near_good", "all_good" }. A city death carries no fight
## (win=false, 0 rounds, 0 HP); the stopped outcomes carry the real CombatEncounter result.
static func resolve(strength: float) -> Dictionary:
	if strength > STOP_THRESHOLD:
		return {
			"outcome": "city_dies",
			"win": false,
			"rounds": 0,
			"player_hp_left": 0.0,
			"strength": strength,
		}
	var fight := CombatEncounter.new(strength)
	var r: Dictionary = fight.auto_resolve()
	return {
		"outcome": "all_good" if bool(r["win"]) else "near_good",
		"win": r["win"],
		"rounds": r["rounds"],
		"player_hp_left": r["player_hp_left"],
		"strength": strength,
	}
