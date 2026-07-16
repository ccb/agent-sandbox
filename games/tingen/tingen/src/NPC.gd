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
	# N4: resolve the bound agent BEFORE skinning — a body bound to an agent already wearing a
	# monster form must render that form's art from frame one (_apply_sprite reads _agent).
	_agent = Agents.get_agent(npc_id)
	_apply_sprite()
	# N6 (B2): a def-less runtime body (meter threat, crypt roster) labels itself with its
	# bound agent's diegetic display_name — the raw id only when nothing better exists.
	var label := String(_def.get("name", ""))
	if label == "" and _agent != null and String(_agent.display_name) != "":
		label = String(_agent.display_name)
	_name_label.text = label if label != "" else npc_id
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
	# P3: the banded hp-pip widget is LIVE-ONLY (a real display) — headless bodies stay bare,
	# so the deterministic harnesses never see a cosmetic node.
	if DisplayServer.get_name() != "headless":
		_mount_pips()

## Skin this body: the bound agent's CURRENT combat_form art first (N4 — a dispatched hunter, the
## backlash wave, the half-landed avatar bind ALREADY monstrous and must read as the fightable
## threat from frame one; also a transformed Beyonder whose body respawns on room re-entry), then
## its real character portrait, else the tinted icon.svg placeholder. Convention/data driven
## through the SAME resolution seam the mask-drop swap uses (CombatExecutor.resolve_form_sprite_
## path + resolve_sprite_path) — no per-NPC logic. Real art carries its own colour, so the flat
## identity tint is dropped; the form standee is scaled to the mask-drop height, a portrait to a
## body-sized silhouette; otherwise the legacy tinted placeholder stands.
func _apply_sprite() -> void:
	if _agent != null:
		var form_path := CombatExecutor.resolve_form_sprite_path(String(_agent.combat_form))
		if form_path != "":
			var form_tex: Texture2D = load(form_path)
			if form_tex != null:
				_sprite.texture = form_tex
				_sprite.modulate = Color(1, 1, 1, 1)   # real art brings its own palette
				var fh := float(form_tex.get_height())
				if fh > 0.0:
					_sprite.scale = Vector2.ONE * (CombatExecutor.FORM_SPRITE_TARGET_H / fh)
				return
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

## ---- P3 combat readability: banded enemy hp pips (combat mode only) --------------------------
## The pip COUNT mirrors the ONE peer-hp banding (Perception.hp_band — the same coarse bands the
## LLM payloads expose; never exact numbers): healthy=3, hurt=2, critical=1, downed=0. The pip
## NODE is live-only (never spawned headless), so the deterministic harnesses see state only.
const PIPS_NODE_NAME: String = "HpPips"

func combat_pips() -> int:
	if _agent == null:
		return 0
	match Perception.hp_band(_agent.hp, _agent.max_hp, _agent.downed):
		"healthy":
			return 3
		"hurt":
			return 2
		"critical":
			return 1
	return 0

## Pips show ONLY while the agent fights (combat mode) and stands — a corpse needs no bar, and
## a calm street never leaks health bars.
func pips_visible_now() -> bool:
	return _agent != null and _agent.in_combat and not _agent.downed

## Mount the live-only pip widget (called from _ready when a real display exists).
func _mount_pips() -> void:
	if has_node(PIPS_NODE_NAME):
		return
	var pips := HpPips.new()
	pips.name = PIPS_NODE_NAME
	pips.owner_body = self
	pips.position = Vector2(0, -28)
	pips.z_index = 10
	add_child(pips)

## The segmented pip bar: three coarse slots above the body, filled per combat_pips(), tinted by
## band (3 = bone-green, 2 = amber, 1 = red). Redraws only when the band steps.
class HpPips:
	extends Node2D
	var owner_body: Node = null
	var _last: int = -1

	func _process(_delta: float) -> void:
		if owner_body == null:
			return
		visible = bool(owner_body.call("pips_visible_now"))
		if not visible:
			return
		var n: int = int(owner_body.call("combat_pips"))
		if n != _last:
			_last = n
			queue_redraw()

	func _draw() -> void:
		var n := maxi(0, _last)
		var w := 9.0
		var h := 3.5
		var gap := 2.0
		var total := w * 3.0 + gap * 2.0
		var x0 := -total / 2.0
		var filled := Color(0.62, 0.85, 0.44)
		if n == 2:
			filled = Color(0.95, 0.75, 0.30)
		elif n <= 1:
			filled = Color(0.95, 0.30, 0.25)
		draw_rect(Rect2(x0 - 1.5, -h / 2.0 - 1.5, total + 3.0, h + 3.0), Color(0.05, 0.05, 0.06, 0.6))
		for i in 3:
			var r := Rect2(x0 + float(i) * (w + gap), -h / 2.0, w, h)
			draw_rect(r, filled if i < n else Color(0.22, 0.20, 0.18, 0.85))

## ---- P4 staged opener: the spoken-line BARK bubble --------------------------------------------
## A one-line speech bubble above this body — how a spoken NPC line (e.g. the constable's door-knock
## tip) is SEEN in the world, not just read off the top bar. The bark TEXT is state (headless-
## observable via bark_text()); the bubble NODE is live-only (never mounted under --headless), the
## exact HpPips pattern — deterministic harnesses never see a cosmetic node. Content comes from the
## caller (scenario/dialogue data); nothing here names an NPC.
const BARK_NODE_NAME: String = "Bark"
const BARK_SECONDS: float = 7.0
var _bark_text: String = ""
var _bark_node: Control = null

func bark_text() -> String:
	return _bark_text

func show_bark(text: String, duration: float = BARK_SECONDS) -> void:
	if text == "":
		return
	_bark_text = text
	if DisplayServer.get_name() == "headless":
		return   # live-only visual; the state above is the headless-observable fact
	if _bark_node != null and is_instance_valid(_bark_node):
		_bark_node.queue_free()
	var lbl := Label.new()
	lbl.name = BARK_NODE_NAME
	lbl.text = text
	lbl.autowrap_mode = TextServer.AUTOWRAP_WORD_SMART
	lbl.horizontal_alignment = HORIZONTAL_ALIGNMENT_CENTER
	lbl.custom_minimum_size = Vector2(200, 0)
	lbl.size = Vector2(200, 0)
	lbl.position = Vector2(-100, -104)
	lbl.z_index = 20
	lbl.add_theme_font_size_override("font_size", 12)
	lbl.add_theme_color_override("font_color", Color(0.93, 0.90, 0.82))
	var sb := StyleBoxFlat.new()
	sb.bg_color = Color(0.07, 0.07, 0.09, 0.92)
	sb.border_color = Color(0.56, 0.50, 0.38, 0.9)
	sb.set_border_width_all(1)
	sb.set_corner_radius_all(4)
	sb.content_margin_left = 8.0
	sb.content_margin_right = 8.0
	sb.content_margin_top = 5.0
	sb.content_margin_bottom = 5.0
	lbl.add_theme_stylebox_override("normal", sb)
	add_child(lbl)
	_bark_node = lbl
	# Real-time expiry (immune to pause / the combat hit-stop time_scale dip).
	get_tree().create_timer(maxf(1.0, duration), true, false, true).timeout.connect(_clear_bark)

func _clear_bark() -> void:
	_bark_text = ""
	if _bark_node != null and is_instance_valid(_bark_node):
		_bark_node.queue_free()
	_bark_node = null

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
