extends Node
## Live registry of every Agent in the district (autoload singleton `Agents`).
##
## Builds one Agent per NpcDB definition at startup (and on demand via `rebuild`),
## owns their lifetime, and answers spatial queries the rest of the sim needs:
## `get_agent`/`all` for lookup, `active` for "who is near here" (the cheap stand-in
## for the LLM's attention budget), and `tick_beat` to step every agent's fallback
## movement once per clock beat. Round-trips through to_dict()/from_dict() so a save
## restores each agent's runtime state on top of the freshly-built cast.

var fallback_speed: float = 48.0
var _agents: Dictionary = {}  # id -> Agent

func _ready() -> void:
	rebuild()

func rebuild() -> void:
	_agents.clear()
	for id in NpcDB.defs.keys():
		var def: Dictionary = NpcDB.defs[id]
		var a: Agent = Agent.new(id)
		a.display_name = String(def.get("name", id))
		a.role = String(def.get("role", ""))
		a.intent = String(def.get("intent", ""))
		a.description = String(def.get("description", ""))
		a.voice = String(def.get("voice", ""))
		a.knowledge = (def.get("knowledge", []) as Array).duplicate()
		a.secrets = (def.get("secrets", []) as Array).duplicate()
		# Data-driven NPC record fields (design §2). `goals` is folded into the brain's goal set by
		# Perception; `task` drives convergence + the no_rite_without_site invariant. Default to empty when absent.
		a.goals = (def.get("goals", []) as Array).duplicate(true)
		a.task = (def.get("task", {}) as Dictionary).duplicate(true)
		a.tier = String(def.get("tier", "light"))
		# Per-agent vision radius (agent-sandbox precedent): an npcs.json def MAY carry "vision_r";
		# absent, everyone sees the shared default. Radius is data — no role branches anywhere.
		a.vision_r = float(def.get("vision_r", Perception.DEFAULT_VISION_R))
		# Combat kit reference (combat plan §M1): an npcs.json def MAY name a "combat_form" (a key
		# in data/combat_forms.json). Pure data — the mask only matters once combat starts.
		a.combat_form = String(def.get("combat_form", ""))
		# Sequence pathway (direction v2 §6): pure DATA an npcs.json def MAY carry. Drives the
		# Characteristic a downed Beyonder drops (Progression) — no NPC-identity branch anywhere.
		a.pathway = String(def.get("pathway", ""))
		# Combat loadout (combat plan §M18): an npcs.json def MAY carry an optional "carried_items"
		# {item_id: count} block — the weapons/rounds/valuables this agent walks around with. Hydrated
		# into its per-agent inventory so the M18 cost provider pays ammo from it (a human gunman runs
		# dry) AND a downed body is lootable (loot = the inventory). Pure DATA, no NPC-identity branch;
		# re-hydrated every rebuild, so a fresh run re-arms with NO cross-run leak (rebuild clears the
		# roster first, and add_item is additive-from-empty).
		var carried: Variant = def.get("carried_items", {})
		if carried is Dictionary:
			for item_id in (carried as Dictionary):
				var n: Variant = (carried as Dictionary)[item_id]
				if typeof(n) in [TYPE_INT, TYPE_FLOAT] and int(n) > 0:
					a.add_item(String(item_id), int(n))
		a.position = NpcDB.waypoint_for(id, Clock.phase)
		_agents[id] = a

## The synthetic player proxy id. A non-deliberating Agent mirrored to the real player each frame, so
## the player is perceivable (shows up in agents' `nearby`) and attackable (`attack target="player"`
## resolves through ActionCommit). NEVER driven by the brain.
const PLAYER_ID: String = "player"

## Scenario source of the player's starting kit (see _player_loadout).
const SCENARIO_PATH: String = "res://data/scenario.json"
## Fallback loadout when scenario.json is absent or authors no player_loadout — headless
## harnesses must still arm the investigator with the same revolver + rounds.
const DEFAULT_PLAYER_LOADOUT: Dictionary = {"revolver": 1, "revolver_round": 12}

## Create the player proxy if missing, then sync it to the live player's position + room. Called each
## frame by GameController/StandaloneBoot. Returns the proxy. Reuses Agent's combat state (hp/downed) as
## the player's health, so the existing _attack path damages and downs the player with no new system.
## Creation grants the scenario's player_loadout ONCE (items, not built-in pools — the revolver and its
## rounds ride the SAME per-agent inventory NPCs use): re-ensuring an existing proxy never re-grants,
## so spent rounds stay spent across frames and room swaps, while a run restart (rebuild clears the
## ephemeral proxy) re-arms with the fresh proxy.
func ensure_player_proxy(pos: Vector2, room: String) -> Agent:
	var p: Agent = _agents.get(PLAYER_ID, null)
	if p == null:
		p = _new_player_proxy()
		var loadout := _player_loadout()
		for item_id in loadout:
			p.add_item(String(item_id), int(loadout[item_id]))
		_agents[PLAYER_ID] = p
	p.position = pos
	p.room = room
	return p

## Bare proxy construction, shared by ensure_player_proxy (which grants the fresh-run loadout) and
## from_dict (which hydrates a SAVED inventory instead — N2 A2: a restore must never re-grant day-1).
func _new_player_proxy() -> Agent:
	var p := Agent.new(PLAYER_ID)
	p.display_name = "The Investigator"
	p.role = "investigator"
	p.deliberates = false   # the brain never decides for the player
	return p

## The starting kit from data/scenario.json's "player_loadout" {item_id: count}, shape-guarded
## (non-numeric or non-positive counts are dropped); the built-in default when the file or the
## key is absent/empty. Read lazily at proxy creation — creation is rare (run start / restart).
func _player_loadout() -> Dictionary:
	if FileAccess.file_exists(SCENARIO_PATH):
		var parsed: Variant = JSON.parse_string(FileAccess.get_file_as_string(SCENARIO_PATH))
		if parsed is Dictionary and (parsed as Dictionary).get("player_loadout") is Dictionary:
			var out: Dictionary = {}
			var raw: Dictionary = (parsed as Dictionary)["player_loadout"]
			for k in raw:
				if typeof(raw[k]) in [TYPE_INT, TYPE_FLOAT] and int(raw[k]) > 0:
					out[String(k)] = int(raw[k])
			if not out.is_empty():
				return out
	return DEFAULT_PLAYER_LOADOUT.duplicate()

func get_agent(id: String) -> Agent:
	return _agents.get(id, null)

## Register a runtime-spawned Agent into the live roster (M7 Ritual Night stages crypt defenders /
## the avatar / backlash thralls this way — bodies with no NpcDB def). Keyed by the agent's id; a
## rebuild() (a fresh run) clears them, so they never leak across runs.
func register_agent(a: Agent) -> void:
	if a == null or a.id == "":
		return
	_agents[a.id] = a

func all() -> Array:
	return _agents.values()

func active(center: Vector2, radius: float) -> Array:
	var out: Array = []
	for a in _agents.values():
		if a.position.distance_to(center) <= radius:
			out.append(a)
	return out

func tick_beat() -> void:
	for a in _agents.values():
		a.tick_fallback(Clock.phase, fallback_speed)

func to_dict() -> Dictionary:
	var d: Dictionary = {}
	for id in _agents.keys():
		if id == PLAYER_ID:
			continue   # the player proxy is ephemeral — re-created from the live player each frame, never saved
		d[id] = (_agents[id] as Agent).to_dict()
	var out: Dictionary = {"agents": d}
	# N2 (A2): the player proxy's INVENTORY is real run state — rounds spent, shillings earned,
	# tools/ingredients gathered, harvested Characteristics (the advance fuel) — and this to_dict is
	# the ONE seam both persistence paths share (SaveManager.subsystem_dump feeds the disk save AND
	# RunManager's in-memory nightly checkpoint), so carrying it here fixes both at once. Every
	# restore used to wake the player with the day-1 loadout. The proxy ITSELF stays ephemeral
	# (position/room re-mirrored from the live body each frame); only its carried stock persists.
	var p: Agent = _agents.get(PLAYER_ID, null)
	if p != null:
		out["player_inventory"] = p.inventory.duplicate(true)
	return out

func from_dict(data: Dictionary) -> void:
	var d: Dictionary = data.get("agents", {})
	for id in d.keys():
		var a: Agent = _agents.get(id, null)
		if a == null:
			a = Agent.new(String(id))
		a.from_dict(d[id])
		_agents[id] = a
	# N2 (A2): restore the player proxy's carried stock. A restore rebuilds the roster first, so the
	# proxy usually does not exist yet — create it WITHOUT the fresh-run loadout grant (the saved
	# inventory IS the loadout); the per-frame ensure_player_proxy then sees it present and never
	# re-grants. Older saves without the key change nothing (the fresh grant covers them).
	if data.get("player_inventory") is Dictionary:
		var p: Agent = _agents.get(PLAYER_ID, null)
		if p == null:
			p = _new_player_proxy()
			_agents[PLAYER_ID] = p
		p.inventory = (data["player_inventory"] as Dictionary).duplicate(true)
