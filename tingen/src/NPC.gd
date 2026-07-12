extends CharacterBody2D
## Stub NPC agent (GDD §15 / §22.3). Reads its definition + phase schedule from NpcDB,
## re-targets its waypoint on Clock.phase_changed, and paths toward it along the city
## navmesh via a NavigationAgent2D, falling back to straight-line steering when no path
## exists (an NPC spawned outside the live district, or before the nav map has synced).
## The schedule/binding logic is the art-agnostic part.
##
## If its definition has a dialogue_id, the player can talk to it (E when near).

@export var npc_id: String = ""
@export var move_speed: float = 60.0
@export var arrive_radius: float = 8.0

## M16 visual foundation — the per-NPC sprite SEAM (data/convention, zero id branches).
## Where character art lives, and the on-screen height a real portrait is scaled down to.
const CHAR_SPRITE_DIR: String = "res://assets/characters/"
const PLACEHOLDER_TEX: String = "res://icon.svg"
const REAL_SPRITE_TARGET_H: float = 48.0

## Resolve a real character sprite for an NPC by DATA, never by identity branch:
##   1. an explicit `sprite` path on the npcs.json def wins (author override), if the file exists;
##   2. else the CONVENTION assets/characters/<npc_id>.png, if it exists;
##   3. else "" — the caller keeps the icon.svg + tint placeholder.
## Pure + defensive: only ever returns a path ResourceLoader can open, so a missing asset can
## never crash the body. Static so tests can exercise the resolution rules directly.
static func resolve_sprite_path(id: String, def: Dictionary) -> String:
	var explicit := String(def.get("sprite", ""))
	if explicit != "" and ResourceLoader.exists(explicit):
		return explicit
	var conv := "%s%s.png" % [CHAR_SPRITE_DIR, id]
	if id != "" and ResourceLoader.exists(conv):
		return conv
	return ""

@onready var _sprite: Sprite2D = $Sprite2D
@onready var _name_label: Label = $Name
@onready var _prompt: Label = $TalkArea/Prompt
@onready var _nav: NavigationAgent2D = $NavigationAgent2D

## M24 combat juice: a brief hit-flash on this body's sprite (the struck-enemy whiten). Cosmetic +
## live-only — never touches agent/combat state. The flash overbrightens the sprite toward white so
## it reads on ANY base (a tinted placeholder OR full-colour real art), then restores the base.
const HIT_FLASH_WHITEN: float = 1.75      # overbright target (>1 = brighter than white)
const HIT_FLASH_DURATION: float = 0.06    # ~60ms, per the M24 spec
var _hit_flash_t: float = 0.0
var _hit_flash_base: Color = Color(1, 1, 1, 1)
var _hit_flash_active: bool = false

var _def: Dictionary = {}
var _target: Vector2
var _player_near: bool = false
var _agent = null   # bound Agent (from the registry) or null = schedule fallback
var _executor: CombatExecutor = null   # combat body authority while _agent.in_combat (plan §M2)

func _ready() -> void:
	_def = NpcDB.get_def(npc_id)
	if _def.is_empty():
		push_warning("NPC: no def for '%s'" % npc_id)
	_apply_sprite()
	_name_label.text = String(_def.get("name", npc_id))
	_prompt.visible = false
	_prompt.text = "Talk"
	_target = global_position
	if Clock.phase != "":
		_retarget(Clock.phase)
	Clock.phase_changed.connect(func(p, _d): _retarget(p))
	var area: Area2D = $TalkArea
	area.body_entered.connect(_on_body_entered)
	area.body_exited.connect(_on_body_exited)
	area.input_pickable = true
	area.input_event.connect(_on_talk_area_input)
	_agent = Agents.get_agent(npc_id)

## Skin this body: show its real character portrait the moment art exists, else the tinted
## icon.svg placeholder. Convention/data driven (resolve_sprite_path) — no per-NPC logic. When a
## real sprite loads it carries its own colour, so the flat identity tint is dropped and the
## portrait is scaled to a body-sized silhouette; otherwise the legacy tinted placeholder stands.
func _apply_sprite() -> void:
	var path := resolve_sprite_path(npc_id, _def)
	if path != "":
		var tex: Texture2D = load(path)
		if tex != null:
			_sprite.texture = tex
			_sprite.modulate = Color(1, 1, 1, 1)   # real art brings its own palette
			var h := float(tex.get_height())
			if h > 0.0:
				_sprite.scale = Vector2.ONE * (REAL_SPRITE_TARGET_H / h)
			return
	# Placeholder: keep the default icon.svg (already set in the scene) tinted by the def's identity colour.
	var tint: Array = _def.get("tint", [1, 1, 1])
	if tint.size() >= 3:
		_sprite.modulate = Color(tint[0], tint[1], tint[2])

## M24 combat juice (b): whiten this body for a beat on a landed hit, then restore. Called by the
## CombatFeedback autoload on `agent_attacked` (gated under hit_flash). Cosmetic + read-only on
## combat state — it only writes the sprite's modulate. Re-triggering re-latches the SAME base (so a
## rapid second hit mid-flash can never freeze an overbright tint), and it self-restores via _process.
func flash_hit(duration: float = HIT_FLASH_DURATION) -> void:
	if _sprite == null:
		return
	if not _hit_flash_active:
		_hit_flash_base = _sprite.modulate
		_hit_flash_active = true
	_hit_flash_t = maxf(0.0, duration)
	_sprite.modulate = Color(HIT_FLASH_WHITEN, HIT_FLASH_WHITEN, HIT_FLASH_WHITEN, _hit_flash_base.a)

## Decay the hit-flash back to base. Runs every frame (live). Uses a SEPARATE _process, not
## _physics_process, because the latter early-returns during combat/dialogue — the flash must still
## restore while the body is fighting (exactly when it gets hit).
func _process(delta: float) -> void:
	_step_hit_flash(delta)

## Headless-driveable flash step (no _process ticks under the -s harness). Restores the base once
## the window elapses; a no-op when no flash is active.
func step_hit_flash(delta: float) -> void:
	_step_hit_flash(delta)

func _step_hit_flash(delta: float) -> void:
	if not _hit_flash_active or _sprite == null:
		return
	_hit_flash_t = maxf(0.0, _hit_flash_t - delta)
	if _hit_flash_t <= 0.0:
		_sprite.modulate = _hit_flash_base
		_hit_flash_active = false

## True when this node is the rendered body of a live registry Agent.
func is_bound() -> bool:
	return _agent != null

## The live CombatExecutor child while the bound agent is in combat, else null.
func combat_executor() -> CombatExecutor:
	return _executor

## Where the node should walk this frame: its Agent's beat-driven position when bound,
## otherwise its scheduled waypoint.
func steer_goal() -> Vector2:
	return _agent.position if _agent != null else _target

func _on_talk_area_input(_viewport: Node, event: InputEvent, _shape_idx: int) -> void:
	if event is InputEventMouseButton and event.button_index == MOUSE_BUTTON_LEFT and event.pressed:
		if Agents.get_agent(npc_id) != null:
			WorldState.inspect_requested.emit(npc_id)

func _retarget(phase: String) -> void:
	var wp := NpcDB.waypoint_for(npc_id, phase)
	if wp != Vector2.ZERO:
		_target = wp

func _physics_process(delta: float) -> void:
	if DialogueManager.active:
		velocity = Vector2.ZERO
		return
	# COMBAT SEAM (plan §M1 -> M2): when the bound agent is in combat mode, position authority is
	# handed off to a CombatExecutor child piloting this body at frame rate (it writes
	# agent.position from motions and glides the body onto it) — the puppet glide below must NOT
	# fight it by dragging the body back to the beat-rate data position. Leaving combat frees the
	# executor and the strict-puppet glide resumes.
	if _agent != null and _agent.in_combat:
		velocity = Vector2.ZERO
		if _executor == null:
			_executor = CombatExecutor.new()
			_executor.bind(_agent, self)
			_executor.enable_tactics()   # M3: bound bodies fight with the tactical layer on
			# M18: NPC combat costs are REAL — a generic cost provider pays ammo-costed arts from
			# THIS agent's own inventory (a human gunman runs dry; monster free kits are untouched).
			# Engine-neutral: the provider keys off item DATA, not NPC identity.
			_executor.cost_provider = AgentCostProvider.new(_agent)
			add_child(_executor)
		return
	if _executor != null:
		_executor.queue_free()
		_executor = null
	var goal := steer_goal()
	if global_position.distance_to(goal) <= arrive_radius:
		velocity = Vector2.ZERO
		if _agent != null:
			global_position = goal   # settle exactly on the data position when bound
		return
	if _agent != null:
		# Bound: this body is a strict PUPPET of its registry Agent. The data sim
		# (ActionCommit/tick_fallback) owns logical pathing at <= fallback_speed per beat; the body
		# just glides to the agent's CURRENT position at move_speed (60 px/s easily keeps up with the
		# 48 px/beat data step). It must NEVER consult the navmesh or the schedule waypoint here —
		# doing so made bound bodies chase stale per-scene schedule coords / take odd navmesh detours,
		# the "flying left/up on scene entry" bug. Portal jumps are handled by despawn/respawn (the
		# agent leaves the room), so the body never has to glide across a teleport.
		global_position = global_position.move_toward(goal, move_speed * delta)
		return
	# Unbound (an NPC instantiated outside the live district / the isolated bind test): the legacy
	# schedule-walker — path around the city's buildings/water on the baked navmesh, straight-line
	# when no path exists, so isolated behavior still holds.
	_nav.target_position = goal
	var steer_point := goal
	if not _nav.is_navigation_finished() and _nav.is_target_reachable():
		steer_point = _nav.get_next_path_position()
	velocity = (steer_point - global_position).normalized() * move_speed
	move_and_slide()

func _on_body_entered(body: Node) -> void:
	if body.is_in_group("player") and _can_talk():
		_player_near = true
		_prompt.visible = true

func _on_body_exited(body: Node) -> void:
	if body.is_in_group("player"):
		_player_near = false
		_prompt.visible = false

## Any live registry agent is conversable now (the LLM can voice any persona — design open-Q3), so the
## old dialogue_id gate is gone; you can talk to anyone you can walk up to — except the synthetic
## "player" proxy (you can't converse with yourself).
func _can_talk() -> bool:
	return npc_id != Agents.PLAYER_ID and Agents.get_agent(npc_id) != null

func _unhandled_input(event: InputEvent) -> void:
	if not _player_near or not _can_talk():
		return
	if event.is_action_pressed("interact"):
		# Open a real LLM conversation with this agent (by AGENT id), not the scripted tree.
		DialogueManager.open(npc_id)
		get_viewport().set_input_as_handled()
