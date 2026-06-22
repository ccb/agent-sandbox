extends Panel
## Cult progress panel (toggle: C). Shows how close the cult is to summoning the descending
## god (外神) — a closeness bar from the countdown, the ritual stock they hold, and the
## qualitative dent the player's interference has made — plus recent publicly-known events
## and the player's own collected leads/clues. The hidden manifestation strength is never a
## raw number here; the player reads the threat through these proxies.

## Allow-list (default-deny) of EventBus types the player would plausibly know. The cult's
## secret moves — agent_action / agent_action_amended and the runtime's action_rejected /
## action_vetoed / directive_rejected reasoning — are NOT listed, so they can never leak here.
const PUBLIC_TYPES: Array = [
	"player_sabotage", "player_social", "player_occult",   # the player's own deeds
	"summoning_climax", "endgame",                         # climactic, unmissable
	# District news + pressure shifts — the prime "publicly-known" feed. Their emitters
	# (EventManager narrative events / world-pressure broadcasts) aren't on the bus yet, so
	# these match nothing today; pre-allowed so they surface the moment those land.
	"event", "world_pressure",
]
const RECENT: int = 10

@onready var _closeness: ProgressBar = $Margin/Body/Closeness/Bar
@onready var _summary: Label = $Margin/Body/Summary
@onready var _ingredients: Label = $Margin/Body/Ingredients
@onready var _events: VBoxContainer = $Margin/Body/Events/List
@onready var _intel: VBoxContainer = $Margin/Body/Intel/List

func _ready() -> void:
	visible = false
	EventBus.event_logged.connect(func(_e): if visible: refresh())
	WorldState.state_changed.connect(func(): if visible: refresh())

func toggle() -> void:
	visible = not visible
	if visible:
		refresh()

func refresh() -> void:
	_closeness.value = SummoningPlan.closeness_ratio() * 100.0
	_summary.text = _summary_line()
	_ingredients.text = _ingredients_line()
	_fill(_events, public_event_lines())
	_fill(_intel, intel_lines())

func _summary_line() -> String:
	var pct := int(round(SummoningPlan.closeness_ratio() * 100.0))
	return "Summoning readiness: %d%%   ·   your interference: %s" % [pct, SummoningPlan.interference_band()]

func _ingredients_line() -> String:
	var parts: PackedStringArray = []
	for k in SummoningPlan.ingredients.keys():
		parts.append("%s ×%d" % [String(k).replace("_", " "), int(SummoningPlan.ingredients[k])])
	if parts.is_empty():
		return "Ritual stock: stripped bare."
	return "Ritual stock: " + ", ".join(parts)

func public_event_lines() -> Array:
	var out: Array = []
	for e in EventBus.latest(RECENT):
		if String(e.get("type", "")) in PUBLIC_TYPES:
			out.append("• " + _format_event(e))
	if out.is_empty():
		out.append("• Nothing of public note yet.")
	return out

func _format_event(e: Dictionary) -> String:
	var t := String(e.get("type", "")).replace("_", " ")
	var who := String((e.get("data", {}) as Dictionary).get("actor", ""))
	return "%s — %s" % [t, who] if who != "" else t

func intel_lines() -> Array:
	var out: Array = ["Lead: " + WorldState.current_lead, "Clues collected: %d" % ClueDB.collected_count()]
	for clue in ClueDB.collected_clues():
		if String(clue.get("importance", "")) == "pivotal":
			out.append("  ★ " + String(clue.get("name", "?")))
	return out

func _fill(box: VBoxContainer, lines: Array) -> void:
	# free() synchronously, not queue_free: the panel refreshes on both event_logged and
	# state_changed, which can both fire in one frame. queue_free defers removal to end-of-
	# frame, so the second refresh would stack a duplicate list on children not yet reaped.
	for c in box.get_children():
		c.free()
	for line in lines:
		var l := Label.new()
		l.text = String(line)
		l.autowrap_mode = TextServer.AUTOWRAP_WORD_SMART
		box.add_child(l)

func _unhandled_input(event: InputEvent) -> void:
	if visible and event.is_action_pressed("ui_cancel"):
		visible = false
		get_viewport().set_input_as_handled()
