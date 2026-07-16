extends Node
## Renders the simulated world AROUND the player (autoload `RoomView`) — tingen_scene_graph_design.md §5.
##
## Agents live as DATA in rooms (Agent.room + position) and cross between rooms through portals whether
## or not their scene is loaded. RoomView is the bridge to what the player SEES: each beat it spawns an
## NPC body for every tracked agent whose room == the room the player is currently standing in, parks it
## at the agent's position, and despawns the body once that agent leaves the room. By DEFAULT it tracks
## EVERY registered non-player agent (empty _tracked list), so the whole civilian cast renders wherever
## it shares the player's room; set_tracked(subset) narrows that. Follow the cult down into the crypt
## and their bodies appear there; when they cross back out, they vanish from your scene.
## It also renders that room's ground items (RoomItems) as small labelled sprites — the supply cache in
## the City, the offerings laid at the altar.
##
## Bodies + item nodes parent under the live world scene (GameController.world_scene()), so a scene swap
## frees them automatically; RoomView sees the empty room on the next beat and repopulates. Inert in
## headless tests (there is no "game_controller" node, so every reconcile early-returns).

const NPC_SCENE := preload("res://scenes/NPC.tscn")

## A real sprite to use for an item, when one ships; otherwise RoomView draws a colored swatch.
const ITEM_TEX := {
	"candle": "res://assets/props/candle_0.png",
}
## Swatch color per material so the three offerings read apart at a glance (salt = pale, chalk =
## blue-white, candle = tallow-orange). Anything unlisted falls back to a neutral gray.
const ITEM_COLOR := {
	"ritual_salt": Color(0.86, 0.86, 0.92),
	"consecrated_chalk": Color(0.70, 0.85, 1.00),
	"candle": Color(1.00, 0.72, 0.32),
	# B1 (retro): the pathway Characteristic drops read distinctly where a Beyonder fell — the live
	# harvest cue for the walk-over gather (hunter = predator crimson, hermit = starlit violet,
	# tainted = spoiled green). Ammo keeps its own row so a round pile never reads as a harvest.
	"hunter_characteristic": Color(0.85, 0.30, 0.30),
	"hermit_characteristic": Color(0.62, 0.55, 0.95),
	"tainted_characteristic": Color(0.55, 0.72, 0.40),
	"revolver_round": Color(0.78, 0.66, 0.38),
}

## Agent ids RoomView renders. EMPTY = the DEFAULT: track EVERY registered non-player agent, so any
## civilian with a schedule gets a body whenever its room == the player's room — City.tscn shows the
## whole cast, not just the cult. A NON-empty list RESTRICTS rendering to that subset (a staging /
## test seam); set_tracked([]) or clear_tracked() returns to the track-all default.
var _tracked: Array[String] = []
var _bodies: Dictionary = {}              # agent_id -> NPC body node
var _item_nodes: Array[Node2D] = []       # ground-item sprites currently shown
var _room: String = ""                    # the room currently rendered
var _parent_id: int = 0                   # instance id of the scene we last parented bodies under

## N4 — the world facts that respawn the room the moment they land (the beat cadence alone left a
## dispatched hunter INVISIBLE for up to a whole 15-game-minute beat). Data table, no id branches.
const RECONCILE_EVENTS: Dictionary = {"threat_dispatched": true, "threat_resolved": true}

func _ready() -> void:
	# Agents move on beats, so reconcile bodies each beat; redraw ground items whenever they change.
	var clock := _al("Clock")
	if clock != null:
		clock.beat_ticked.connect(func(_b, _d): reconcile())
	var items := _al("RoomItems")
	if items != null:
		items.changed.connect(_render_items)
	# N4 (A6): EVENT-DRIVEN respawn passes on top of the beat cadence — a threat dispatched into
	# the player's room is ON SCREEN within a frame or two, the crypt roster stands the moment the
	# player enters, the backlash wave / half-landed avatar appear as they spawn. All of these are
	# idempotent reconcile() calls (headless harnesses stay inert: no game_controller -> early
	# return), so the pinned sims never change.
	var ws := _al("WorldState")
	if ws != null and ws.has_signal("room_changed"):
		# The scene swap frees the OLD world subtree at frame end — repopulate on the NEXT frame so
		# bodies parent under the NEW scene, never the dying one.
		ws.room_changed.connect(func(_room, _path): _reconcile_next_frame())
	var eb := _al("EventBus")
	if eb != null and not eb.event_logged.is_connected(_on_world_event):
		eb.event_logged.connect(_on_world_event)
	var rn := _al("RitualNight")
	if rn != null:
		if rn.has_signal("ritual_night_started"):
			rn.ritual_night_started.connect(func(_site, _early): reconcile())
		if rn.has_signal("avatar_half_landed"):
			rn.avatar_half_landed.connect(func(_id): reconcile())
		if rn.has_signal("backlash_spawned"):
			rn.backlash_spawned.connect(func(_ids): reconcile())

## The EventBus ear: any RECONCILE_EVENTS world fact respawns the room at once (the dispatched
## hunter is seen the frame it spawns). Cheap + idempotent; inert when no scene is loaded.
func _on_world_event(ev: Dictionary) -> void:
	if RECONCILE_EVENTS.has(String(ev.get("type", ""))):
		reconcile()

## Reconcile on the FIRST frame after the current one — the scene-swap window (room_changed fires
## while the old scene is still queue_free-pending as _world child 0, so an immediate pass would
## parent bodies under the dying subtree). Coalesces re-entrant requests.
var _swap_reconcile_pending: bool = false
func _reconcile_next_frame() -> void:
	if _swap_reconcile_pending:
		return
	_swap_reconcile_pending = true
	await get_tree().process_frame
	_swap_reconcile_pending = false
	reconcile()

## Restrict rendering to a subset of agents, or pass [] to return to the track-all default
## (every registered non-player agent). Reconciles immediately either way.
func set_tracked(ids: Array) -> void:
	_tracked = []
	for id in ids:
		_tracked.append(String(id))
	reconcile()

## Back to the track-all default, despawning everything first (the next reconcile repopulates).
func clear_tracked() -> void:
	_tracked = []
	_despawn_all()
	_room = ""

## Spawn/move/despawn bodies so the loaded scene shows exactly the tracked agents standing in it,
## then redraw the room's ground items. Safe to call any time; bails when no scene is loaded.
func reconcile() -> void:
	var parent: Node = _spawn_parent()
	var ag := _al("Agents")
	if parent == null or ag == null:
		return
	var room: String = _current_room()
	var pid: int = parent.get_instance_id()
	if pid != _parent_id or room != _room:
		# Scene swapped — OR the same room was re-instanced (a new node, same room id). Either way the
		# old bodies/items were freed with the old scene tree, so drop our now-dangling handles and
		# rebuild from scratch. Keying on the parent's instance id (not just the room) catches re-entry
		# into the same room, which a room-id compare alone would miss.
		_bodies.clear()
		_item_nodes.clear()
		_room = room
		_parent_id = pid
	# Resolve the render roster: an explicit tracked subset, else EVERYONE registered — every
	# non-player agent (the player proxy is the live player's mirror; it must never grow an NPC body).
	var ids: Array = _tracked
	if ids.is_empty():
		ids = []
		for a in ag.all():
			if String(a.id) != String(ag.PLAYER_ID):
				ids.append(String(a.id))
	for id in ids:
		var agent: Agent = ag.get_agent(id)
		var here: bool = agent != null and String(agent.room) == room
		var body: Node = _bodies.get(id, null)
		var valid: bool = body != null and is_instance_valid(body)
		if here:
			if not valid:
				body = _spawn_body(parent, id, agent.position)
				_bodies[id] = body
		elif valid:
			body.queue_free()
			_bodies.erase(id)
		elif body != null:
			_bodies.erase(id)
	# Despawn bodies whose agent left the roster (e.g. set_tracked narrowed from all to a subset).
	# Untyped local on purpose: a typed Node assignment of an externally-freed instance errors.
	for id in _bodies.keys().duplicate():
		if not ids.has(id):
			var stale = _bodies[id]
			if stale != null and is_instance_valid(stale):
				stale.queue_free()
			_bodies.erase(id)
	_render_items()

func _spawn_body(parent: Node, id: String, pos: Vector2) -> Node:
	var npc := NPC_SCENE.instantiate()
	npc.npc_id = id                       # bind BEFORE add_child so NPC._ready resolves the agent
	parent.add_child(npc)
	(npc as Node2D).global_position = pos  # drop it on its agent, not at the scene origin
	return npc

func _despawn_all() -> void:
	for id in _bodies.keys():
		var body: Node = _bodies[id]
		if body != null and is_instance_valid(body):
			body.queue_free()
	_bodies.clear()
	for n in _item_nodes:
		if is_instance_valid(n):
			n.queue_free()
	_item_nodes.clear()

## Redraw the ground items of the current room. Cheap enough to rebuild wholesale on each change.
func _render_items() -> void:
	var parent: Node = _spawn_parent()
	var ri := _al("RoomItems")
	if parent == null or ri == null:
		return
	for n in _item_nodes:
		if is_instance_valid(n):
			n.queue_free()
	_item_nodes.clear()
	var room: String = _current_room()
	for e in ri.items_in(room):
		var node := _make_item_node(String(e["item_id"]), int(e.get("qty", 1)))
		parent.add_child(node)
		node.global_position = e["pos"]
		_item_nodes.append(node)

## A ground item = a small sprite (real texture when one ships, else a colored swatch) with a label
## naming it, so the supply cache and the laid offerings are legible at a glance.
func _make_item_node(item_id: String, qty: int) -> Node2D:
	var holder := Node2D.new()
	holder.z_index = -1   # items sit under NPC bodies
	var spr := Sprite2D.new()
	var tex_path := String(ITEM_TEX.get(item_id, ""))
	if tex_path != "" and ResourceLoader.exists(tex_path):
		spr.texture = load(tex_path)
		spr.scale = Vector2(0.5, 0.5)
	else:
		spr.texture = _swatch(ITEM_COLOR.get(item_id, Color(0.8, 0.8, 0.8)))
	holder.add_child(spr)
	var label := Label.new()
	label.text = _pretty(item_id) if qty <= 1 else "%s x%d" % [_pretty(item_id), qty]
	label.position = Vector2(-28, 14)
	label.add_theme_font_size_override("font_size", 12)
	holder.add_child(label)
	return holder

## A 20x20 solid-color texture standing in for an item with no shipped sprite.
func _swatch(c: Color) -> ImageTexture:
	var img := Image.create(20, 20, false, Image.FORMAT_RGBA8)
	img.fill(c)
	return ImageTexture.create_from_image(img)

## "ritual_salt" -> "Ritual Salt" — a readable label without depending on ItemDB's accessor.
func _pretty(item_id: String) -> String:
	return item_id.replace("_", " ").capitalize()

## Where to parent spawned bodies + item sprites, working in BOTH boot modes:
##   * real game (Main.tscn): the World's live child, via GameController.world_scene();
##   * standalone (a world scene run on its own, swapped by StandaloneBoot.change_scene_to_file):
##     the whole current_scene IS the world scene.
## Null in headless -s runs (no scene) and before the first scene loads — so reconcile early-returns.
func _spawn_parent() -> Node:
	var gc := _game_controller()
	if gc != null:
		return gc.world_scene()
	return get_tree().current_scene

## The RoomGraph room id of the loaded scene, resolved the same two ways as _spawn_parent.
func _current_room() -> String:
	var gc := _game_controller()
	if gc != null:
		return gc.current_room()
	var cs := get_tree().current_scene
	return RoomGraph.room_for_scene(cs.scene_file_path) if cs != null else ""

func _game_controller() -> Node:
	var nodes := get_tree().get_nodes_in_group("game_controller")
	return nodes[0] if nodes.size() > 0 else null

func _al(autoload_name: String) -> Node:
	return get_node_or_null("/root/" + autoload_name)
