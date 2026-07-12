class_name CameraRig
extends Camera2D
## M29 — the player's PRESENTATION-ONLY camera brain (attached to the Camera2D under Player.tscn).
##
## PRESENTATION ONLY. This node never reads or writes combat state, meters, RNG, agent brains, or
## anything the simulation observes; it keys purely on GEOMETRY (the painted map rect, the player's
## position, the nearest visible body) and lifecycle EVENTS (combat_started/ended, room_changed) —
## never on any NPC identity. combat_sim (71/0) and run_combat_vectors (95/0) stay byte-identical
## because nothing here can perturb the deterministic fixed-dt sim.
##
## LIVE-ONLY visuals. Every time-based / pixel-moving effect — the reframe + lookahead offset, the
## zoom tween, and the smoothing reset — happens ONLY when a real display is attached (_is_live(),
## the same DisplayServer=="headless" gate CombatFeedback uses). Under --headless (every test
## harness) this node is inert: _ready wires nothing and _process returns immediately, so the four
## deterministic gates are untouched. The MATH is pure + static so the headless harness asserts it
## (map-rect derivation, view clamp, reframe midpoint, lookahead offset) with zero pixel motion, and
## the snap-fix is a plain observable flag.
##
## Framing is applied via the camera's LOCAL `position`, deliberately NOT `offset` — CombatFeedback
## owns `offset` for its screen-shake, so the two never fight.

# --- Tunables (presentation) ------------------------------------------------------------------
## Gentle combat zoom-IN (Godot Camera2D: zoom > 1 = closer). The reframe pulls the view toward the
## midpoint between the player and the active threat; this tightens it a touch for the fight.
const COMBAT_ZOOM: float = 1.15
const REST_ZOOM: float = 1.0
## Mouse-aim lookahead: how far (world px) the view leads the player toward where they are aiming.
const LOOKAHEAD_DISTANCE: float = 96.0
## Live easing rates (fraction/second) for the framing offset and the zoom. Presentation only.
const FRAME_LERP: float = 6.0
const ZOOM_LERP: float = 4.0

# --- Snap-fix state (headless-observable) -----------------------------------------------------
## Armed on (re-)instantiation and on every room entry. Because each room re-instances Player.tscn
## (a fresh Camera2D with default smoothing state), the first LIVE frame must jump the camera to its
## target with reset_smoothing() instead of gliding in from the old/spawn position — that glide is
## the visible per-room "snap" this milestone kills.
var _snap_pending: bool = true

# --- Live framing state -----------------------------------------------------------------------
var _in_combat: bool = false
var _threat_pos: Vector2 = Vector2.ZERO
var _wired: bool = false

# ============================ PURE MATH (headless-testable) ===================================

## The painted City extents, read from the AUTHORED world-rect constant (MapProjection): the ground
## is a 1254px map image at CITY_SCALE world-units/px, i.e. (0,0)..(6270,6270). Not a guessed
## literal — this is the same rect the waypoint-legality tests clamp against.
static func city_map_rect() -> Rect2:
	return Rect2(Vector2.ZERO, MapProjection.MAP_SIZE * MapProjection.CITY_SCALE)

## Derive a room's map rect from its authored ground/background sprite (the painted extents the
## camera must not show past). Composes the sprite's LOCAL transform chain up to the scene root, so
## it is pure and needs no SceneTree. Returns an empty Rect2 (size 0) when the scene has no such
## ground — the live limiter then leaves that room unclamped. Engine-neutral: keys on the scene's
## geometry (a "Ground"/"Floor" node with a Sprite2D), never on any agent identity.
static func derive_map_rect(world_scene: Node) -> Rect2:
	if world_scene == null:
		return Rect2()
	var host: Node = world_scene.get_node_or_null("Ground")
	if host == null:
		host = world_scene.get_node_or_null("Floor")
	if host == null:
		host = world_scene
	var spr: Sprite2D = _find_ground_sprite(host)
	if spr == null or spr.texture == null:
		return Rect2()
	var xf: Transform2D = _local_chain_transform(world_scene, spr)
	var size: Vector2 = spr.texture.get_size()
	var tl: Vector2 = (-size * 0.5) if spr.centered else Vector2.ZERO
	var c0: Vector2 = xf * tl
	var c1: Vector2 = xf * (tl + Vector2(size.x, 0.0))
	var c2: Vector2 = xf * (tl + Vector2(0.0, size.y))
	var c3: Vector2 = xf * (tl + size)
	var mn: Vector2 = c0
	var mx: Vector2 = c0
	for c in [c1, c2, c3]:
		mn = Vector2(minf(mn.x, c.x), minf(mn.y, c.y))
		mx = Vector2(maxf(mx.x, c.x), maxf(mx.y, c.y))
	return Rect2(mn, mx - mn)

## Clamp a desired camera CENTER so the visible rect [center - half_view, center + half_view] stays
## inside map_rect. When the map is smaller than the view on an axis, center on the map (no jitter
## against impossible limits). half_view = viewport_size * 0.5 / zoom. Pure. An empty map_rect
## (no bounds) passes the center through unchanged.
static func clamp_center(center: Vector2, map_rect: Rect2, half_view: Vector2) -> Vector2:
	if map_rect.size.x <= 0.0 or map_rect.size.y <= 0.0:
		return center
	var min_c: Vector2 = map_rect.position + half_view
	var max_c: Vector2 = map_rect.end - half_view
	var cx: float
	if min_c.x > max_c.x:
		cx = map_rect.position.x + map_rect.size.x * 0.5
	else:
		cx = clampf(center.x, min_c.x, max_c.x)
	var cy: float
	if min_c.y > max_c.y:
		cy = map_rect.position.y + map_rect.size.y * 0.5
	else:
		cy = clampf(center.y, min_c.y, max_c.y)
	return Vector2(cx, cy)

## The combat reframe target: the midpoint between the player and the active threat.
static func reframe_target(player_pos: Vector2, threat_pos: Vector2) -> Vector2:
	return (player_pos + threat_pos) * 0.5

## The gentle uniform combat zoom-in (Godot zoom > 1 = closer) and the resting zoom.
static func combat_zoom() -> Vector2:
	return Vector2(COMBAT_ZOOM, COMBAT_ZOOM)

static func rest_zoom() -> Vector2:
	return Vector2(REST_ZOOM, REST_ZOOM)

## The screen-space lookahead offset: lead `distance` px along the (normalized) aim. A zero aim
## yields no offset. Pure.
static func lookahead_offset(aim: Vector2, distance: float = LOOKAHEAD_DISTANCE) -> Vector2:
	if aim.length() < 0.0001:
		return Vector2.ZERO
	return aim.normalized() * distance

static func lookahead_default_distance() -> float:
	return LOOKAHEAD_DISTANCE

# --- Snap-fix (headless-observable) -----------------------------------------------------------
func is_snap_pending() -> bool:
	return _snap_pending

## Re-arm the snap (called on room entry): the next live frame jumps to target instead of gliding.
func arm_snap() -> void:
	_snap_pending = true

## Consume the pending snap: returns whether one was armed, and clears it so the reset fires once.
func consume_snap() -> bool:
	var was: bool = _snap_pending
	_snap_pending = false
	return was

# ============================ LIVE (display-only) =============================================

func _ready() -> void:
	add_to_group("camera_rig")
	# Headless: stay inert. The harness drives the pure helpers + snap state directly; wiring nothing
	# here (and returning from _process) keeps every deterministic gate byte-identical.
	if not _is_live():
		return
	_wire_signals()

func _wire_signals() -> void:
	if _wired:
		return
	_wired = true
	var ws := _al("WorldState")
	if ws != null and ws.has_signal("room_changed") and not ws.room_changed.is_connected(_on_room_changed):
		ws.room_changed.connect(_on_room_changed)
	var eb := _al("EventBus")
	if eb != null and eb.has_signal("event_logged") and not eb.event_logged.is_connected(_on_event):
		eb.event_logged.connect(_on_event)

## Live per-frame framing. Fully gated: headless returns immediately (no pixel motion, no state
## reads the sim can observe). Applies the reframe + lookahead as the camera's LOCAL position, eases
## the zoom, sets the map limits, and fires the one-shot smoothing reset on (re-)entry.
func _process(delta: float) -> void:
	if not _is_live():
		return
	_wire_signals()
	var player := get_parent() as Node2D
	if player == null:
		return
	# Framing offset = combat reframe (toward the player↔threat midpoint) + mouse-aim lookahead.
	var target_local: Vector2 = Vector2.ZERO
	if _in_combat:
		target_local = reframe_target(player.global_position, _threat_pos) - player.global_position
	target_local += lookahead_offset(_aim())
	position = position.lerp(target_local, clampf(FRAME_LERP * delta, 0.0, 1.0))
	# Gentle combat zoom.
	var zt: Vector2 = combat_zoom() if _in_combat else rest_zoom()
	zoom = zoom.lerp(zt, clampf(ZOOM_LERP * delta, 0.0, 1.0))
	# Map limits from the current room's painted extents.
	_apply_limits()
	# Snap-fix: on (re-)instantiation / room entry, jump to target — no smoothing glide.
	if consume_snap():
		reset_smoothing()

func _on_room_changed(_room_id: String, _scene_path: String) -> void:
	arm_snap()

## React to the combat lifecycle. Reads only the event TYPE + (live) body GEOMETRY — never combat
## state. Engine-neutral: the threat is the nearest visible body to the player, not an id branch.
func _on_event(ev: Dictionary) -> void:
	match String(ev.get("type", "")):
		"combat_started":
			_in_combat = true
			_refresh_threat()
		"combat_ended":
			_in_combat = false

## The active threat's position = the nearest visible NPC body to the player. Geometry only.
func _refresh_threat() -> void:
	var player := get_parent() as Node2D
	if player == null:
		return
	var best: float = INF
	for b in get_tree().get_nodes_in_group("npc"):
		if b is Node2D:
			var d: float = player.global_position.distance_to((b as Node2D).global_position)
			if d < best:
				best = d
				_threat_pos = (b as Node2D).global_position

## The player's current mouse-aim, reusing the existing PlayerCombat.aim_dir() seam.
func _aim() -> Vector2:
	var parent := get_parent()
	if parent == null:
		return Vector2.ZERO
	var pc := parent.get_node_or_null("Combat")
	if pc != null and pc.has_method("aim_dir"):
		return pc.aim_dir()
	return Vector2.ZERO

## Set the Camera2D limits from the current room's painted map rect so the view cannot show past the
## painted edges. Leaves an unbounded room's limits alone.
func _apply_limits() -> void:
	var rect: Rect2 = _current_map_rect()
	if rect.size.x <= 0.0 or rect.size.y <= 0.0:
		return
	limit_left = int(round(rect.position.x))
	limit_top = int(round(rect.position.y))
	limit_right = int(round(rect.end.x))
	limit_bottom = int(round(rect.end.y))

## The current room's map rect: derived from its ground sprite, falling back to the authored City
## rect for the city, else empty (unbounded).
func _current_map_rect() -> Rect2:
	var gc := _game_controller()
	if gc != null:
		var scene: Node = gc.world_scene()
		if scene != null:
			var r: Rect2 = derive_map_rect(scene)
			if r.size.x > 0.0 and r.size.y > 0.0:
				return r
		if String(gc.current_room()) == "city":
			return city_map_rect()
	return Rect2()

# --- Static geometry helpers ------------------------------------------------------------------
static func _find_ground_sprite(n: Node) -> Sprite2D:
	if n is Sprite2D:
		return n as Sprite2D
	var direct := n.get_node_or_null("Sprite")
	if direct is Sprite2D:
		return direct as Sprite2D
	for child in n.get_children():
		if child is Sprite2D:
			return child as Sprite2D
	return null

## Compose the LOCAL Node2D transform chain from `root` down to `node` (inclusive), mapping
## node-local coords into root space. Uses the .transform local property, so no SceneTree is needed.
static func _local_chain_transform(root: Node, node: Node) -> Transform2D:
	var chain: Array = []
	var cur: Node = node
	while cur != null:
		chain.append(cur)
		if cur == root:
			break
		cur = cur.get_parent()
	var xf: Transform2D = Transform2D.IDENTITY
	for i in range(chain.size() - 1, -1, -1):
		var c = chain[i]
		if c is Node2D:
			xf = xf * (c as Node2D).transform
	return xf

# --- Environment ------------------------------------------------------------------------------
## True only when a real display is attached (live play). False under --headless — where this whole
## node stays inert, keeping every deterministic harness byte-identical.
func _is_live() -> bool:
	return DisplayServer.get_name() != "headless"

func _game_controller() -> Node:
	var nodes := get_tree().get_nodes_in_group("game_controller")
	return nodes[0] if nodes.size() > 0 else null

func _al(autoload_name: String) -> Node:
	return get_node_or_null("/root/" + autoload_name)
