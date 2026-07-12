extends Node
## Data-driven deed + consequence runner (autoload `DeedRunner`) — combat plan §M6.
##
## Consumes data/deeds.json, which authors TWO generic row kinds; the engine code here knows no
## agent, no clue id, and no prose — every identity string is data (the neutral-engine principle):
##
##   DEEDS — a witnessable act an agent's own schedule walks it into: when the named agent stands
##   at the deed waypoint (its room + radius) during one of the named phases, the deed FIRES once
##   per day: a `deed_performed` event carries the authored fact_line, Stimulus fans that line to
##   whoever can SEE it (the ONE shared vision gate — same room + witness's own vision_r), and the
##   PLAYER PROXY seeing it grants the authored clue (the proxy has no memory to fan into, so the
##   clue is its witness channel). Checked on Clock.minute_ticked — a minute is the finest
##   schedule-walk resolution, and the per-day latch makes repeat minutes free.
##
##   CONSEQUENCES — the world reacting to a published combat fact: rows keyed on `transformed`
##   (event form matches when the row authors one) or `downed` (agent_downed whose target wears
##   the authored form, when one is named). A matching row nudges the authored pressure variables
##   through WorldState.adjust and lands the authored clue — gated on the proxy actually
##   perceiving the agent when `clue_needs_sight` (seeing the flesh split is knowledge; a pressure
##   shift is the city's, sight or no sight).
##
## Deterministic — no RNG, no LLM, no wall time. The per-day deed latch round-trips through
## to_dict/from_dict (a reload mid-night must not re-drag the same burden twice); consequence
## rows carry no latch (a transform can only resolve into a NEW form, so `transformed` cannot
## repeat for the same agent+form; a repeat downing genuinely alarms the city again).

const DEEDS_PATH: String = "res://data/deeds.json"

var deeds: Array = []
var consequences: Array = []
var _fired: Dictionary = {}   # deed id -> last day it fired (once-per-day latch)

func _ready() -> void:
	_load_data()
	if not Clock.minute_ticked.is_connected(_on_minute):
		Clock.minute_ticked.connect(_on_minute)
	if not EventBus.event_logged.is_connected(_on_event):
		EventBus.event_logged.connect(_on_event)

func _load_data() -> void:
	if not FileAccess.file_exists(DEEDS_PATH):
		push_error("DeedRunner: missing data file %s" % DEEDS_PATH)
		return
	var parsed: Variant = JSON.parse_string(FileAccess.get_file_as_string(DEEDS_PATH))
	if typeof(parsed) != TYPE_DICTIONARY:
		push_error("DeedRunner: %s is not a JSON object" % DEEDS_PATH)
		return
	var d: Dictionary = parsed
	deeds = (d.get("deeds", []) as Array)
	consequences = (d.get("consequences", []) as Array)

func reset() -> void:
	_fired.clear()

## Fire a deed ON DEMAND (M5 §6): the PLAYER's acting ritual isn't schedule-walked — the player
## chooses to perform it. Looks up the authored `player_performed` deed by id, emits the standard
## `deed_performed` fact through EventBus (so Stimulus/log wiring stays identical to a walked deed),
## grants any authored clue if the proxy is in place, and returns {ok, reason}. Deterministic — no
## RNG, no schedule. The Madness accounting stays with the caller (Progression spikes +35 on the
## advance; the generic acting-deed relief is a separate DeedRunner-independent Meters call).
## Refuses an id that is not an authored `player_performed` deed.
func perform_deed(deed_id: String) -> Dictionary:
	for deed_v in deeds:
		if typeof(deed_v) != TYPE_DICTIONARY:
			continue
		var deed: Dictionary = deed_v
		if String(deed.get("id", "")) != deed_id:
			continue
		if not bool(deed.get("player_performed", false)):
			return {"ok": false, "reason": "not_player_performed"}
		var actor := String(deed.get("agent", "player"))
		EventBus.emit_event("deed_performed",
			{"actor": actor, "deed": deed_id, "line": String(deed.get("fact_line", "")),
			"room": String(deed.get("room", RoomGraph.DEFAULT_ROOM)), "player_performed": true})
		var clue := String(deed.get("clue", ""))
		if clue != "":
			ClueDB.collect(clue)
		return {"ok": true, "reason": ""}
	return {"ok": false, "reason": "unknown_deed"}

## ---- deeds (schedule-walked witnessable acts) ----

func _on_minute(_minute_of_day: int, day: int) -> void:
	for deed_v in deeds:
		if typeof(deed_v) != TYPE_DICTIONARY:
			continue
		var deed: Dictionary = deed_v
		var id := String(deed.get("id", ""))
		if id == "" or int(_fired.get(id, -1)) == day:
			continue
		if not (deed.get("phases", []) as Array).has(Clock.phase):
			continue
		var agent: Agent = Agents.get_agent(String(deed.get("agent", "")))
		if agent == null or agent.downed:
			continue
		if String(agent.room) != String(deed.get("room", RoomGraph.DEFAULT_ROOM)):
			continue
		var wp_v: Variant = deed.get("waypoint", [])
		if not (wp_v is Array) or (wp_v as Array).size() < 2:
			continue
		var wp := Vector2(float((wp_v as Array)[0]), float((wp_v as Array)[1]))
		if agent.position.distance_to(wp) > float(deed.get("radius", 80.0)):
			continue
		_fired[id] = day
		# The deed is now a world FACT: the event carries the authored line, Stimulus fans it
		# vision-gated from where the actor stands (exactly like a strike or a telegraph).
		EventBus.emit_event("deed_performed",
			{"actor": agent.id, "deed": id, "line": String(deed.get("fact_line", "")), "room": agent.room})
		# The proxy's witness channel: _fan_room skips the player proxy (it has no brain to
		# remember with) — what the PLAYER gets for seeing the deed is the clue.
		var clue := String(deed.get("clue", ""))
		if clue != "" and _proxy_sees(agent):
			ClueDB.collect(clue)

## ---- consequences (the world reacting to published combat facts) ----

func _on_event(ev: Dictionary) -> void:
	var t := String(ev.get("type", ""))
	var data: Dictionary = ev.get("data", {}) if ev.get("data") is Dictionary else {}
	var on := ""
	var agent_id := ""
	var event_form := ""
	if t == "transformed":
		on = "transformed"
		agent_id = String(data.get("agent", ""))
		event_form = String(data.get("form", ""))
	elif t == "agent_downed":
		on = "downed"
		agent_id = String(data.get("target", ""))
	else:
		return
	var agent: Agent = Agents.get_agent(agent_id)
	for row_v in consequences:
		if typeof(row_v) != TYPE_DICTIONARY:
			continue
		var row: Dictionary = row_v
		if String(row.get("agent", "")) != agent_id or String(row.get("on", "")) != on:
			continue
		# An authored form narrows the row: `transformed` matches the event's revealed form;
		# `downed` matches the shape the body WEARS as it falls (downing the still-human butcher
		# reveals no monster).
		var want_form := String(row.get("form", ""))
		if want_form != "":
			var worn := event_form if on == "transformed" else (agent.combat_form if agent != null else "")
			if worn != want_form:
				continue
		var adjust: Dictionary = row.get("adjust", {}) if row.get("adjust") is Dictionary else {}
		for var_name in adjust:
			WorldState.adjust(StringName(String(var_name)), float(adjust[var_name]))
		var clue := String(row.get("clue", ""))
		if clue != "" and (not bool(row.get("clue_needs_sight", false)) or _proxy_sees(agent)):
			ClueDB.collect(clue)

## Can the player proxy SEE this agent right now? The ONE shared perceiver gate
## (Perception.can_perceive: same room + within the proxy's own vision_r), measured from where
## the agent stands — no proxy in the world means nobody is playing, so nothing is seen.
func _proxy_sees(agent: Agent) -> bool:
	if agent == null:
		return false
	var proxy: Agent = Agents.get_agent(Agents.PLAYER_ID)
	return proxy != null and Perception.can_perceive(proxy, agent.room, agent.position)

func to_dict() -> Dictionary:
	return {"fired": _fired.duplicate(true)}

func from_dict(d: Dictionary) -> void:
	_fired = (d.get("fired", {}) as Dictionary).duplicate(true)
