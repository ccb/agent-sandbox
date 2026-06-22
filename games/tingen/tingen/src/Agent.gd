class_name Agent
extends RefCounted
## Runtime representation of one inhabitant of the district.
##
## An Agent is the live, mutable counterpart to a static NpcDB definition: it holds the
## NPC's current position, intent, in-progress action, short-term memory and plan. In
## later plans an LLM decides each agent's actions per beat; until then `tick_fallback`
## gives cheap deterministic behaviour by walking the agent toward its scheduled
## waypoint. Agents round-trip through to_dict()/from_dict() so the AgentRegistry can
## persist the whole cast in a save file.

var id: String = ""
var display_name: String = ""
var faction: String = "civilian"
var role: String = ""
var intent: String = ""
var position: Vector2 = Vector2.ZERO
var current_action: Dictionary = {}
var short_memory: Array = []
var plan: Array = []
var thought: String = ""   # latest read-out: set by sidecar/critic, else synthesized
## Combat state. The cast is a fixed, saved roster, so a felled agent is incapacitated
## (downed), never deleted — unlike Yumina, which removes a dead entity from the world.
var hp: float = 100.0
var max_hp: float = 100.0
var downed: bool = false
## Per-agent inventory (Yumina-faithful: a flat id->count store the agent carries). Distinct
## from the player Inventory autoload and from the cult's shared rite cache (SummoningPlan).
var inventory: Dictionary = {}  # item_id -> int

func _init(agent_id: String = "") -> void:
	id = agent_id

func tick_fallback(phase: String, speed: float) -> void:
	# A downed agent is incapacitated: it holds its ground until helped up, so the cheap
	# scheduled walk skips it entirely. Mirrors the Critic veto that lets a felled agent only
	# idle — both keep a downed body from drifting around the district.
	if downed:
		return
	# Resolve the NpcDB autoload via the engine singleton table rather than the bare
	# global identifier: when this class_name script is compiled as a dependency of the
	# headless `-s` test runner, autoload globals aren't registered yet, so a bare
	# `NpcDB` reference fails to compile. The singleton lookup is ordering-independent.
	var npc_db: Object = (Engine.get_main_loop() as SceneTree).root.get_node("/root/NpcDB")
	var target: Vector2 = npc_db.waypoint_for(id, phase)
	if target == Vector2.ZERO and position == Vector2.ZERO:
		return
	var to_target: Vector2 = target - position
	var dist: float = to_target.length()
	if dist <= speed or dist == 0.0:
		position = target
	else:
		position += to_target / dist * speed

func distance_to(p: Vector2) -> float:
	return position.distance_to(p)

func remember(entry: String, cap: int = 20) -> void:
	short_memory.append(entry)
	if short_memory.size() > cap:
		short_memory = short_memory.slice(short_memory.size() - cap)

## Apply flat combat damage (ActionCommit.attack drives this). Clamps to [0, max_hp] and
## downs the agent at zero — mirroring Yumina's clamp-to-zero HP mutation, but incapacitating
## rather than deleting, since our cast is fixed and persisted.
func take_damage(amount: float) -> void:
	if amount <= 0.0:
		return
	hp = clampf(hp - amount, 0.0, max_hp)
	if hp <= 0.0:
		downed = true

## Add to this agent's own carried stock (ActionCommit.gather_item drives this).
func add_item(item_id: String, count: int = 1) -> void:
	if item_id == "" or count <= 0:
		return
	inventory[item_id] = int(inventory.get(item_id, 0)) + count

## How many of an item this agent is currently carrying.
func item_count(item_id: String) -> int:
	return int(inventory.get(item_id, 0))

## The agent's moment-to-moment read-out for the character card. Returns an explicit
## thought when one was set (by a sidecar/critic), otherwise synthesizes one from the
## current action. Distinct from `intent`, which is the long-horizon goal. Always
## returns a non-empty string, so the card never shows a blank thought line.
func describe_thought() -> String:
	if thought != "":
		return thought
	var verb := String(current_action.get("verb", ""))
	var args: Dictionary = current_action.get("args", {})
	match verb:
		"move_to": return "Making my way to %s." % args.get("target", "somewhere")
		"talk_to": return "I should have words with %s." % args.get("agent", "them")
		"gather_item": return "I still need the %s." % args.get("item_id", "supplies")
		"perform_ritual_step": return "The rite must go on: %s." % args.get("step", "the next step")
		"recruit": return "Could %s be brought into the fold?" % args.get("agent", "them")
		"report": return "I must get word to %s." % args.get("to", "my contact")
		"hide": return "Best I am not seen just now."
		"flee": return "I have to get clear of %s." % args.get("from", "here")
		"attack": return "No choice left but to strike."
		_: return "Keeping to my own business... for now."

func to_dict() -> Dictionary:
	return {
		"id": id,
		"display_name": display_name,
		"faction": faction,
		"role": role,
		"intent": intent,
		"position": [position.x, position.y],
		"current_action": current_action.duplicate(true),
		"short_memory": short_memory.duplicate(),
		"plan": plan.duplicate(true),
		"thought": thought,
		"hp": hp,
		"max_hp": max_hp,
		"downed": downed,
		"inventory": inventory.duplicate(true),
	}

func from_dict(d: Dictionary) -> void:
	id = String(d.get("id", id))
	display_name = String(d.get("display_name", display_name))
	faction = String(d.get("faction", faction))
	role = String(d.get("role", role))
	intent = String(d.get("intent", intent))
	var p: Variant = d.get("position", [0, 0])
	if typeof(p) == TYPE_ARRAY and (p as Array).size() >= 2:
		position = Vector2(float(p[0]), float(p[1]))
	current_action = (d.get("current_action", {}) as Dictionary).duplicate(true)
	short_memory = (d.get("short_memory", []) as Array).duplicate()
	plan = (d.get("plan", []) as Array).duplicate(true)
	thought = String(d.get("thought", thought))
	hp = float(d.get("hp", hp))
	max_hp = float(d.get("max_hp", max_hp))
	downed = bool(d.get("downed", downed))
	inventory = (d.get("inventory", {}) as Dictionary).duplicate(true)
