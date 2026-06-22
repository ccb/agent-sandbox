class_name CombatEncounter
extends RefCounted
## Minimal but real climax resolution. The player has HP, two attacks (a basic strike and
## a stronger occult ability), against a manifestation whose HP and damage scale with
## SummoningPlan.manifestation_strength(). `auto_resolve` plays a deterministic exchange
## used by tests and as the headless backbone of the real-time fight (the scene/UI wraps
## this in a later plan). Higher impede -> weaker enemy -> the player ends with more HP.

const PLAYER_MAX_HP: float = 100.0
const ATTACK_DAMAGE: float = 18.0
const OCCULT_DAMAGE: float = 30.0
const OCCULT_EVERY: int = 3   # the occult ability lands every 3rd round

var enemy_max_hp: float
var enemy_damage: float
var player_hp: float

func _init(strength: float) -> void:
	# The fight only ever runs at residual strength <= EndGameResolver.STOP_THRESHOLD (60): a
	# fully-manifested descent kills the city outright, with no fight. Tuned so the mid-50s are
	# lethal and the low-40s are survivable, making player interference the difference between
	# near-good (you die) and all-good (you live).
	enemy_max_hp = strength * 2.5           # residual manifestation's HP pool
	enemy_damage = strength * 0.40          # and how hard it hits back
	player_hp = PLAYER_MAX_HP

## Deterministic exchange: each round the player strikes (occult every OCCULT_EVERY),
## then the enemy strikes back if still alive. Returns { win, rounds, player_hp_left }.
func auto_resolve() -> Dictionary:
	var enemy_hp := enemy_max_hp
	var rounds := 0
	while enemy_hp > 0.0 and player_hp > 0.0:
		rounds += 1
		var dmg := OCCULT_DAMAGE if rounds % OCCULT_EVERY == 0 else ATTACK_DAMAGE
		enemy_hp -= dmg
		if enemy_hp <= 0.0:
			break
		player_hp -= enemy_damage
	player_hp = maxf(player_hp, 0.0)
	return {"win": player_hp > 0.0, "rounds": rounds, "player_hp_left": player_hp}
