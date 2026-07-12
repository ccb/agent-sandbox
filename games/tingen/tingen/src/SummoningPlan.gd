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

## Materials that must be physically carried down and laid at the crypt altar before the descent
## can advance at all. This is the gather→deliver gate: the cult must pick these up from the supply
## cache (RoomItems, ground items), carry them across scenes to the altar, and deposit them. Until
## `materials_ready()`, a perform_ritual_step at the altar only lays materials (or no-ops) and never
## advances the clock — so the rite literally cannot progress on an empty altar.
const DEFAULT_RITUAL_REQUIREMENT := {"ritual_salt": 1, "consecrated_chalk": 1, "candle": 1}
var ritual_requirement: Dictionary = DEFAULT_RITUAL_REQUIREMENT.duplicate()
## What has actually been laid at the altar so far (item_id -> count).
var deposited: Dictionary = {}

var _initial_total: int = 8   # sum of starting ingredients, for the strength fraction

## TODO(doomsday-timer): the passive doomsday clock is DISABLED for now — the descent is driven
## PURELY by the cult's own rite work (advance_rite, fired by perform_ritual_step at the altar). With
## this off, stopping the cult — blocking their descent, downing them, or sabotaging ingredients —
## actually prevents the summoning. Flip this back to `true` to restore "the city falls on a schedule"
## time pressure, and rebalance START_COUNTDOWN for the combined timer+rite drive.
const PASSIVE_DOOMSDAY_TICK: bool = false

func _ready() -> void:
	Clock.beat_ticked.connect(_on_beat)

# _beat_index/_day intentionally unused. While PASSIVE_DOOMSDAY_TICK is off, a beat alone does NOT
# advance the clock — only the cult working the rite does (advance_rite). tick_countdown() is kept and
# still callable directly, ready to re-enable.
func _on_beat(_beat_index: int, _day: int) -> void:
	if PASSIVE_DOOMSDAY_TICK:
		tick_countdown()

## Advance the doomsday clock by one beat. At zero, fire the climax exactly once.
func tick_countdown() -> void:
	if climax_fired:
		return
	if countdown_beats > 0:
		countdown_beats -= 1
		countdown_changed.emit(countdown_beats)
	_fire_climax_if_due()

## True once every required material has been laid at the altar.
func materials_ready() -> bool:
	for item_id in ritual_requirement:
		if int(deposited.get(item_id, 0)) < int(ritual_requirement[item_id]):
			return false
	return true

## True when the altar still wants more of `item_id` (used to decide whether a carried unit
## should be laid down rather than hoarded).
func needs(item_id: String) -> bool:
	return int(deposited.get(item_id, 0)) < int(ritual_requirement.get(item_id, 0))

## Lay one unit of a material at the altar. Returns false when the altar wants no more of it.
func deposit(item_id: String) -> bool:
	if not needs(item_id):
		return false
	deposited[item_id] = int(deposited.get(item_id, 0)) + 1
	return true

## How many required units are laid vs. still wanted, for perception/log lines.
func materials_deposited_total() -> int:
	var n := 0
	for item_id in ritual_requirement:
		n += mini(int(deposited.get(item_id, 0)), int(ritual_requirement[item_id]))
	return n

func materials_required_total() -> int:
	var n := 0
	for item_id in ritual_requirement:
		n += int(ritual_requirement[item_id])
	return n

## The materials still missing from the altar (item_id -> remaining count) — fed to perception so
## the brain knows what is left to fetch.
func materials_outstanding() -> Dictionary:
	var out: Dictionary = {}
	for item_id in ritual_requirement:
		var short := int(ritual_requirement[item_id]) - int(deposited.get(item_id, 0))
		if short > 0:
			out[item_id] = short
	return out

## Hasten the descent by `beats` — the cult's own hands working the rite at the altar drive this
## (ActionCommit.perform_ritual_step), so the player watches the clock leap when the faithful work,
## not just tick on a timer. This is the low-level primitive; the materials gate (the altar must be
## fully stocked before any beat advances) is enforced by its sole caller, _perform_ritual_step.
## Clamps at zero and fires the climax once.
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
		# Log the descent BEFORE the signal: summoning_climax.emit drives EndGame to resolve the ending
		# synchronously (the `endgame` event), so the descent must be recorded first to read in order.
		EventBus.emit_event("summoning_climax", {"strength": strength})
		summoning_climax.emit(strength)

func reset() -> void:
	climax_fired = false
	countdown_beats = START_COUNTDOWN
	impede_score = 0.0
	ingredients = {"ritual_salt": 3, "consecrated_chalk": 2, "candle": 3}
	ritual_requirement = DEFAULT_RITUAL_REQUIREMENT.duplicate()
	deposited = {}
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
		"ritual_requirement": ritual_requirement.duplicate(true),
		"deposited": deposited.duplicate(true),
		"initial_total": _initial_total,
		"climax_fired": climax_fired,
	}

func from_dict(d: Dictionary) -> void:
	countdown_beats = int(d.get("countdown_beats", START_COUNTDOWN))
	impede_score = float(d.get("impede_score", 0.0))
	ingredients = (d.get("ingredients", {}) as Dictionary).duplicate(true)
	ritual_requirement = (d.get("ritual_requirement", DEFAULT_RITUAL_REQUIREMENT) as Dictionary).duplicate(true)
	deposited = (d.get("deposited", {}) as Dictionary).duplicate(true)
	_initial_total = int(d.get("initial_total", _total_ingredients()))
	climax_fired = bool(d.get("climax_fired", false))
