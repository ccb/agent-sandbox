extends Node
## The cult's summoning attempt (autoload `SummoningPlan`). Holds the beat countdown to
## the ritual, the cell's gathered ingredient stock, and the hidden `impede_score` that
## the player drives down through interference. `manifestation_strength()` combines the
## two: fewer ingredients and more impede mean a weaker descent (an easier climax). The
## score is never shown as a number — the player feels it through how the world reacts.

const BASE_STRENGTH: float = 100.0
const MIN_STRENGTH: float = 8.0
const COUNTDOWN_SETBACK_PER_INGREDIENT: int = 3
## Beats from the cult's start to the summoning — the denominator for closeness_ratio().
const START_COUNTDOWN: int = 40

signal countdown_changed(beats_left: int)
signal summoning_climax(strength: float)

var climax_fired: bool = false

## Default countdown to the summoning, in beats.
var countdown_beats: int = START_COUNTDOWN
var impede_score: float = 0.0
## What the cell has gathered. Sabotage strips from here.
var ingredients: Dictionary = {"ritual_salt": 3, "consecrated_chalk": 2, "candle": 3}

var _initial_total: int = 8   # sum of starting ingredients, for the strength fraction

func _ready() -> void:
	Clock.beat_ticked.connect(_on_beat)

# _beat_index/_day intentionally unused: every beat advances the doomsday clock equally.
func _on_beat(_beat_index: int, _day: int) -> void:
	tick_countdown()

## Advance the doomsday clock by one beat. At zero, fire the climax exactly once.
func tick_countdown() -> void:
	if climax_fired:
		return
	if countdown_beats > 0:
		countdown_beats -= 1
		countdown_changed.emit(countdown_beats)
	_fire_climax_if_due()

## Hasten the descent by `beats` — the cult's own hands working the rite at the warehouse
## drive this (ActionCommit.perform_ritual_step), so the player watches the clock leap when
## the faithful gather, not just tick on a timer. Clamps at zero and fires the climax once.
func advance_rite(beats: int = 1) -> void:
	if climax_fired or beats <= 0:
		return
	if countdown_beats > 0:
		countdown_beats = maxi(0, countdown_beats - beats)
		countdown_changed.emit(countdown_beats)
	_fire_climax_if_due()

## Fire the summoning climax exactly once, the moment the countdown reaches zero. Shared by
## the steady tick and the cult-driven rite so both paths resolve the descent identically.
func _fire_climax_if_due() -> void:
	if countdown_beats <= 0 and not climax_fired:
		climax_fired = true
		var strength := manifestation_strength()
		summoning_climax.emit(strength)
		EventBus.emit_event("summoning_climax", {"strength": strength})

func reset() -> void:
	climax_fired = false
	countdown_beats = START_COUNTDOWN
	impede_score = 0.0
	ingredients = {"ritual_salt": 3, "consecrated_chalk": 2, "candle": 3}
	_initial_total = _total_ingredients()

func _total_ingredients() -> int:
	var t := 0
	for k in ingredients.keys():
		t += int(ingredients[k])
	return t

func add_impede(amount: float, reason: String = "") -> void:
	impede_score += maxf(0.0, amount)

## Strip ingredients from the cell. Returns false if the cell doesn't hold that many.
## Success also sets the summoning back (the cell must re-gather).
func remove_ingredient(item_id: String, count: int = 1) -> bool:
	if int(ingredients.get(item_id, 0)) < count:
		return false
	ingredients[item_id] = int(ingredients[item_id]) - count
	if int(ingredients[item_id]) <= 0:
		ingredients.erase(item_id)
	countdown_beats += COUNTDOWN_SETBACK_PER_INGREDIENT * count
	return true

func add_ingredient(item_id: String, count: int = 1) -> void:
	ingredients[item_id] = int(ingredients.get(item_id, 0)) + count

## Strength of the descent at the climax. Scales with remaining-ingredient fraction,
## reduced by impede, clamped to [MIN_STRENGTH, BASE_STRENGTH].
func manifestation_strength() -> float:
	var frac: float = float(_total_ingredients()) / float(maxi(1, _initial_total))
	return clampf(BASE_STRENGTH * frac - impede_score, MIN_STRENGTH, BASE_STRENGTH)

## How close the cult is to the summoning, 0 (just begun) .. 1 (imminent). Setbacks that
## push countdown_beats back above START_COUNTDOWN clamp the bar back toward 0 — the player
## sees their interference rewind the clock.
func closeness_ratio() -> float:
	return clampf(1.0 - float(countdown_beats) / float(START_COUNTDOWN), 0.0, 1.0)

## Fraction of the starting ritual stock the cell still holds, 0 .. 1.
func ingredients_ratio() -> float:
	return clampf(float(_total_ingredients()) / float(maxi(1, _initial_total)), 0.0, 1.0)

## Qualitative band for the hidden impede score — shown as words, never a raw number.
func interference_band() -> String:
	if impede_score <= 0.0:
		return "none"
	elif impede_score < 15.0:
		return "minor"
	elif impede_score < 35.0:
		return "significant"
	return "heavy"

func to_dict() -> Dictionary:
	return {
		"countdown_beats": countdown_beats,
		"impede_score": impede_score,
		"ingredients": ingredients.duplicate(true),
		"initial_total": _initial_total,
		"climax_fired": climax_fired,
	}

func from_dict(d: Dictionary) -> void:
	countdown_beats = int(d.get("countdown_beats", START_COUNTDOWN))
	impede_score = float(d.get("impede_score", 0.0))
	ingredients = (d.get("ingredients", {}) as Dictionary).duplicate(true)
	_initial_total = int(d.get("initial_total", _total_ingredients()))
	climax_fired = bool(d.get("climax_fired", false))
