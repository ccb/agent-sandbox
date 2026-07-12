extends Node2D
## Boot controller — the game's main scene (Main.tscn). M2 boot flow.
##
## Fixes GAP-2.8: the game used to boot straight into the dev City scene, skipping any intro. Now
## the game boots HERE, into a minimal Title screen (New Run / Continue-if-a-checkpoint-exists /
## Quit) painted over the city backdrop. "New Run" seeds a fresh run (RunManager.start_run()) and
## drops the player into the LODGING (the reused IntroRoom / Klein's bedroom); from there the player
## walks out into the City and the existing City/interior/combat flow takes over unchanged.
##
## Structure: this node owns a swappable `World` subtree + a persistent `UI` (HUD) layer and doubles
## as the GameController (group "game_controller") so WorldState transitions, SaveManager, and the
## agent player-proxy all work exactly as before once a run is underway. The Title is a CanvasLayer
## overlay on top; it is torn down when a run starts and re-raised on a full run-end.

const LODGING_SCENE: String = "res://scenes/IntroRoom.tscn"
const CITY_SCENE: String = "res://scenes/City.tscn"
const HUD_SCENE: String = "res://ui/HUD.tscn"

@onready var _world: Node2D = get_node_or_null("World")
@onready var _ui: CanvasLayer = get_node_or_null("UI")

var current_scene_path: String = ""
var _title: CanvasLayer = null
var _continue_btn: Button = null

func _ready() -> void:
	add_to_group("game_controller")
	WorldState.transition_requested.connect(_on_transition_requested)
	# A full run-end (win/lose) returns to the title.
	if not RunManager.run_ended.is_connected(_on_run_ended):
		RunManager.run_ended.connect(_on_run_ended)
	_show_title()

func _process(_delta: float) -> void:
	# Only sync the player proxy once a world (with a player) is live.
	if _world != null and _world.get_child_count() > 0:
		sync_player_position()

# --- Title screen -----------------------------------------------------------------------------
func _show_title() -> void:
	if is_instance_valid(_title):
		return
	var layer := CanvasLayer.new()
	layer.name = "Title"
	layer.layer = 10

	var bg := ColorRect.new()
	bg.color = Color(0.04, 0.035, 0.05, 1.0)
	bg.set_anchors_preset(Control.PRESET_FULL_RECT)
	layer.add_child(bg)

	var center := CenterContainer.new()
	center.set_anchors_preset(Control.PRESET_FULL_RECT)
	layer.add_child(center)

	var box := VBoxContainer.new()
	box.alignment = BoxContainer.ALIGNMENT_CENTER
	box.add_theme_constant_override("separation", 20)
	center.add_child(box)

	var title := Label.new()
	title.text = "TINGEN"
	title.horizontal_alignment = HORIZONTAL_ALIGNMENT_CENTER
	title.add_theme_font_size_override("font_size", 72)
	box.add_child(title)

	var subtitle := Label.new()
	subtitle.text = "An occult-noir descent."
	subtitle.horizontal_alignment = HORIZONTAL_ALIGNMENT_CENTER
	box.add_child(subtitle)

	var spacer := Control.new()
	spacer.custom_minimum_size = Vector2(0, 24)
	box.add_child(spacer)

	var new_btn := Button.new()
	new_btn.name = "NewRunButton"
	new_btn.text = "New Run"
	new_btn.custom_minimum_size = Vector2(240, 48)
	new_btn.pressed.connect(start_new_run)
	box.add_child(new_btn)

	var cont_btn := Button.new()
	cont_btn.name = "ContinueButton"
	cont_btn.text = "Continue"
	cont_btn.custom_minimum_size = Vector2(240, 48)
	cont_btn.disabled = not has_continue()
	cont_btn.pressed.connect(continue_run)
	box.add_child(cont_btn)
	_continue_btn = cont_btn

	# Settings reachable from the TITLE as well as the pause menu (M10). Opens the same panel.
	var settings_btn := Button.new()
	settings_btn.name = "SettingsButton"
	settings_btn.text = "Settings"
	settings_btn.custom_minimum_size = Vector2(240, 48)
	settings_btn.pressed.connect(open_settings)
	box.add_child(settings_btn)

	var quit_btn := Button.new()
	quit_btn.name = "QuitButton"
	quit_btn.text = "Quit"
	quit_btn.custom_minimum_size = Vector2(240, 48)
	quit_btn.pressed.connect(func() -> void: get_tree().quit())
	box.add_child(quit_btn)

	# B3 (retro): the persistent-meta LEDGER — the title-screen surface of the M27 payoff (currency /
	# earned pathways / codex learnings). Reads ONLY the RunManager meta getters, rendered through the
	# pure MetaSurface view-model builder; the shared occult-noir theme styles the PanelContainer.
	var meta_panel := _build_meta_panel()
	if meta_panel != null:
		layer.add_child(meta_panel)

	add_child(layer)
	_title = layer

## B3 (retro): build the title LEDGER panel from the persistent meta. Headless-safe and null-tolerant
## (returns null when RunManager/MetaSurface are unavailable, e.g. a bare F6 scene run) so the title
## never hard-depends on the meta stack. Copy comes from MetaSurface (title_model); the codex lines
## themselves were authored in data/scenario.json's codex block and stored in the meta at run end.
func _build_meta_panel() -> Control:
	var rm := get_node_or_null("/root/RunManager")
	var ms: GDScript = load("res://src/MetaSurface.gd") as GDScript
	if rm == null or ms == null:
		return null
	var vm: Dictionary = ms.title_model(int(rm.meta_currency()), int(rm.meta_runs_played()),
		rm.meta_unlocked_pathways(), rm.meta_codex())

	var panel := PanelContainer.new()
	panel.name = "MetaCodexPanel"
	panel.anchor_left = 0.0
	panel.anchor_right = 0.0
	panel.anchor_top = 1.0
	panel.anchor_bottom = 1.0
	panel.grow_horizontal = Control.GROW_DIRECTION_END
	panel.grow_vertical = Control.GROW_DIRECTION_BEGIN
	panel.offset_left = 24.0
	panel.offset_bottom = -24.0
	panel.custom_minimum_size = Vector2(420, 0)

	var ledger := VBoxContainer.new()
	ledger.name = "Ledger"
	ledger.add_theme_constant_override("separation", 6)
	panel.add_child(ledger)

	var head := Label.new()
	head.name = "Header"
	head.text = String(vm.get("header", ""))
	head.add_theme_font_size_override("font_size", 17)
	head.add_theme_color_override("font_color", Color(0.82, 0.66, 0.35, 1.0))   # the theme's gilt accent
	ledger.add_child(head)

	var summary := Label.new()
	summary.name = "Summary"
	summary.text = String(vm.get("summary", ""))
	ledger.add_child(summary)

	ledger.add_child(HSeparator.new())

	var lines: Array = vm.get("codex_lines", [])
	if lines.is_empty():
		var none := Label.new()
		none.name = "EmptyLine"
		none.text = String(vm.get("empty_line", ""))
		none.add_theme_color_override("font_color", Color(0.62, 0.58, 0.5, 1.0))
		ledger.add_child(none)
		return panel
	var ch := Label.new()
	ch.name = "CodexHeader"
	ch.text = String(vm.get("codex_header", ""))
	ch.add_theme_color_override("font_color", Color(0.7, 0.56, 0.29, 0.9))
	ledger.add_child(ch)
	var lines_box := VBoxContainer.new()
	lines_box.name = "CodexLines"
	lines_box.add_theme_constant_override("separation", 2)
	ledger.add_child(lines_box)
	for l in lines:
		var lab := Label.new()
		lab.text = "• %s" % String(l)
		lab.autowrap_mode = TextServer.AUTOWRAP_WORD_SMART
		lab.custom_minimum_size = Vector2(420, 0)
		lab.add_theme_font_size_override("font_size", 13)
		lab.add_theme_color_override("font_color", Color(0.78, 0.74, 0.64, 1.0))
		lines_box.add_child(lab)
	if String(vm.get("codex_more", "")) != "":
		var more := Label.new()
		more.name = "CodexMore"
		more.text = String(vm.get("codex_more", ""))
		more.add_theme_font_size_override("font_size", 12)
		more.add_theme_color_override("font_color", Color(0.62, 0.58, 0.5, 1.0))
		lines_box.add_child(more)
	return panel

## True while the boot title screen is up (no run underway). The pause menu / harness read this to
## confirm quit-to-title returned to the title.
func is_at_title() -> bool:
	return is_instance_valid(_title)

## Open the settings panel over the title (M10 — settings reachable from title AND pause).
var _title_settings: Node = null
func open_settings() -> void:
	if _title_settings != null and is_instance_valid(_title_settings):
		return
	var script := load("res://src/SettingsPanel.gd") as GDScript
	if script == null:
		return
	_title_settings = script.new()
	if is_instance_valid(_title):
		_title.add_child(_title_settings)
	else:
		add_child(_title_settings)
	if _title_settings.has_method("open"):
		_title_settings.open()

func _hide_title() -> void:
	if is_instance_valid(_title):
		_title.queue_free()
	_title = null

# --- Pathway picker (M30 G1) ------------------------------------------------------------------
## The pathway-choice overlay, raised by start_new_run() only when >1 pathway is unlocked. A minimal
## button-per-pathway menu built from the passed options (already Progression.available_pathways()), so
## the presentation carries NO pathway-id literal — the labels come from the ids themselves.
var _pathway_picker: CanvasLayer = null
var _picker_options: Array = []

func _show_pathway_picker(opts: Array) -> void:
	if is_instance_valid(_pathway_picker):
		return
	_picker_options = opts.duplicate()
	var layer := CanvasLayer.new()
	layer.name = "PathwayPicker"
	layer.layer = 11

	var bg := ColorRect.new()
	bg.color = Color(0.04, 0.035, 0.05, 1.0)
	bg.set_anchors_preset(Control.PRESET_FULL_RECT)
	layer.add_child(bg)

	var center := CenterContainer.new()
	center.set_anchors_preset(Control.PRESET_FULL_RECT)
	layer.add_child(center)

	var box := VBoxContainer.new()
	box.alignment = BoxContainer.ALIGNMENT_CENTER
	box.add_theme_constant_override("separation", 16)
	center.add_child(box)

	var title := Label.new()
	title.text = "Choose your pathway"
	title.horizontal_alignment = HORIZONTAL_ALIGNMENT_CENTER
	title.add_theme_font_size_override("font_size", 36)
	box.add_child(title)

	for p in opts:
		var pid := String(p)
		var b := Button.new()
		b.name = "Pathway_" + pid
		b.text = pid.capitalize()
		b.custom_minimum_size = Vector2(240, 48)
		b.pressed.connect(choose_pathway.bind(pid))
		box.add_child(b)

	add_child(layer)
	_pathway_picker = layer

## The picker's button callback (also the live-reachability test seam). Guarded on the offered set so a
## stale/bogus id can never start an unlocked pathway. Starts the run on the chosen pathway.
func choose_pathway(pathway_id: String) -> void:
	if not is_instance_valid(_pathway_picker):
		return
	if not _picker_options.has(pathway_id):
		return
	_begin_run_with_pathway(pathway_id)

## True while the pathway picker is up (the New-Run flow offered a choice).
func pathway_picker_active() -> bool:
	return is_instance_valid(_pathway_picker)

## The pathway ids the picker is currently offering (a copy), or [] when no picker is up.
func pathway_picker_options() -> Array:
	return _picker_options.duplicate() if is_instance_valid(_pathway_picker) else []

func _hide_pathway_picker() -> void:
	if is_instance_valid(_pathway_picker):
		_pathway_picker.queue_free()
	_pathway_picker = null
	_picker_options = []

## A "Continue" is offered only when a nightly safe-house save exists to resume from.
func has_continue() -> bool:
	return SaveManager.has_save()

# --- Entry points -----------------------------------------------------------------------------
## New Run: fresh run (resets the world — the GAP-2.9 fix lives in RunManager.start_run), then wake
## in the LODGING. The player walks out of the bedroom into the City via the existing door portal.
##
## M30 G1 — the PATHWAY PICK. Read the pathways the meta has unlocked (Progression.available_pathways:
## Hunter always; Hermit once the first-win unlock is present). One pathway -> start it directly (no
## needless menu); more than one -> present a picker so the player chooses which build to play. Engine-
## neutral: the flow iterates available_pathways() and NEVER names a pathway id — a future unlock
## (Fool, …) rides this for free the moment the meta lists it.
func start_new_run() -> void:
	var opts: Array = Progression.available_pathways()
	if opts.size() <= 1:
		_begin_run_with_pathway(String(opts[0]) if opts.size() == 1 else "")
	else:
		_show_pathway_picker(opts)

## Actually START the run on the chosen pathway: tear down any picker/title, ensure the HUD, thread the
## pathway through RunManager.start_run (M30 G1 — it applies AFTER the run reset so it isn't clobbered),
## then wake in the lodging. "" falls back to the shipped Hunter build inside start_run.
func _begin_run_with_pathway(pathway_id: String) -> void:
	_hide_pathway_picker()
	_hide_title()
	_ensure_hud()
	RunManager.start_run(pathway_id)
	_swap_world(LODGING_SCENE)

## Continue: resume the last nightly safe-house checkpoint from disk, dropping back into its scene.
func continue_run() -> void:
	if not has_continue():
		return
	_hide_title()
	_ensure_hud()
	SaveManager.load_game()

func _on_run_ended(reason: String) -> void:
	# death / lost_control restore to the checkpoint inside RunManager (the run continues); only a
	# full run-end (win/lose, Ritual Night) drops back to the title.
	if reason == "win" or reason == "lose":
		_teardown_world()
		_show_title()
		if _continue_btn != null:
			_continue_btn.disabled = not has_continue()
	elif reason == "death" or reason == "lost_control":
		# M9 Gap 3: the run CONTINUES (RunManager has already done the data restore/day-1 reset by the
		# time this fires), but nothing had swapped the world scene or moved the player — so a death in
		# the crypt left the body stranded there on a grafted day-1 world. Wake the player back in the
		# checkpoint's safe house (the lodging for a day-1 restart), mirroring start_new_run.
		var wake_scene := LODGING_SCENE
		if RunManager.has_method("checkpoint_scene"):
			wake_scene = String(RunManager.checkpoint_scene())
		var wake_pos := Vector2.ZERO
		if RunManager.has_method("checkpoint_player_pos"):
			wake_pos = RunManager.checkpoint_player_pos()
		_ensure_hud()
		if wake_pos != Vector2.ZERO:
			load_world_at(wake_scene, wake_pos)
		else:
			_swap_world(wake_scene)

# --- World subtree (GameController role) -------------------------------------------------------
func _ensure_hud() -> void:
	if _ui == null:
		_ui = CanvasLayer.new()
		_ui.name = "UI"
		add_child(_ui)
	if _ui.get_child_count() == 0:
		_ui.add_child(load(HUD_SCENE).instantiate())

func _teardown_world() -> void:
	if _world != null:
		for child in _world.get_children():
			child.queue_free()
	current_scene_path = ""

func _on_transition_requested(scene_path: String, lead: String) -> void:
	if _swap_world(scene_path):
		if lead != "":
			WorldState.set_lead(lead)

## Swap the active world scene. Returns true on success. Mirrors the original GameController.
func _swap_world(scene_path: String) -> bool:
	if _world == null:
		_world = Node2D.new()
		_world.name = "World"
		add_child(_world)
		move_child(_world, 0)
	var packed: PackedScene = load(scene_path)
	if packed == null:
		push_error("BootController: could not load scene %s" % scene_path)
		return false
	for child in _world.get_children():
		child.queue_free()
	_world.add_child(packed.instantiate())
	current_scene_path = scene_path
	WorldState.room_changed.emit(RoomGraph.room_for_scene(scene_path), scene_path)
	return true

func sync_player_position() -> void:
	var p := get_player()
	if p:
		AgentRuntime.player_position = p.global_position
		Agents.ensure_player_proxy(p.global_position, current_room())

func world_scene() -> Node:
	if _world == null or _world.get_child_count() == 0:
		return null
	return _world.get_child(0)

func current_room() -> String:
	return RoomGraph.room_for_scene(current_scene_path)

func get_player() -> Node2D:
	var players := get_tree().get_nodes_in_group("player")
	return players[0] if players.size() > 0 else null

func player_position() -> Vector2:
	var p := get_player()
	return p.global_position if p else Vector2.ZERO

## Load a scene and drop the player at `pos` (used by SaveManager). Deferred so the newly instanced
## player exists before we move it.
func load_world_at(scene_path: String, pos: Vector2) -> void:
	if not _swap_world(scene_path):
		return
	await get_tree().process_frame
	var p := get_player()
	if p:
		p.global_position = pos
