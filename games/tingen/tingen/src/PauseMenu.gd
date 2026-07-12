extends CanvasLayer
## Pause menu (autoload `PauseMenu`) — M10 polish.
##
## An Esc-triggered overlay that pauses the SceneTree and offers Resume / Settings / Quit to Title.
## process_mode = ALWAYS (like EndGame / DevConsole) so its buttons still respond while the tree is
## paused. It is a UI shell only: pausing/resuming and settings are cosmetic — they NEVER touch the
## deterministic combat_sim (the world is frozen wholesale, not stepped differently).
##
## INERT guards (the spec's "must not pause during ending screens / boot"):
##   * an ending overlay is up (EndGame owns that freeze) -> open() is a no-op.
##   * no run is active (sitting at the title / boot) -> open() is a no-op.
## "Quit to Title" abandons the active run (RunManager.end_run("lose") — a clean full run-end that
## preserves meta) and returns to BootController's title via its run_ended("lose") handler.

const SETTINGS_PANEL: String = "res://src/SettingsPanel.gd"

var _open: bool = false
var _root: Control = null
var _settings_panel: Node = null

func _ready() -> void:
	process_mode = Node.PROCESS_MODE_ALWAYS
	layer = 9   # below the EndGame overlay (which mounts on its own CanvasLayer) but above the HUD.
	visible = false

## Esc opens the pause menu (when eligible) or, if a settings sub-panel is up, backs out of it; a
## second Esc while paused resumes. Routed here so the binding is coherent with the panel stack.
func _unhandled_input(event: InputEvent) -> void:
	if not event.is_action_pressed("pause"):
		return
	if _settings_panel != null and _settings_panel.has_method("is_open") and _settings_panel.is_open():
		_close_settings()
		get_viewport().set_input_as_handled()
		return
	if _open:
		resume()
	else:
		open()
	get_viewport().set_input_as_handled()

func is_open() -> bool:
	return _open

## Open the pause menu — pause the tree and raise the overlay. INERT when an ending is up or no run
## is active (title/boot). Returns silently in those cases (the spec's inert guard).
func open() -> void:
	if _open:
		return
	if not _eligible():
		return
	get_tree().paused = true
	_build()
	visible = true
	_open = true

## Resume — drop the overlay and lift the freeze.
func resume() -> void:
	_close_settings()
	if is_instance_valid(_root):
		_root.queue_free()
	_root = null
	visible = false
	_open = false
	# Only lift the freeze if no ending overlay wants it (defensive; open() already guards this).
	if not _ending_up():
		get_tree().paused = false

## Quit to Title — abandon the active run and return to the boot title. A clean full run-end that
## preserves meta (RunManager keeps the meta slot; end_run("lose") does not wipe it). No softlock:
## the freeze is lifted, the overlay torn down, and BootController's run_ended("lose") raises the title.
func quit_to_title() -> void:
	_close_settings()
	if is_instance_valid(_root):
		_root.queue_free()
	_root = null
	visible = false
	_open = false
	get_tree().paused = false
	var rm := _al("RunManager")
	if rm != null and rm.has_method("run_active") and rm.run_active():
		rm.end_run("lose")   # abandon -> full run-end -> boot title (meta preserved)

# --- Eligibility ------------------------------------------------------------------------------
## Pause is allowed ONLY during live play: a run is active AND no ending overlay is up.
func _eligible() -> bool:
	if _ending_up():
		return false
	var rm := _al("RunManager")
	return rm != null and rm.has_method("run_active") and rm.run_active()

func _ending_up() -> bool:
	var eg := _al("EndGame")
	return eg != null and eg.has_method("has_overlay") and eg.has_overlay()

# --- Overlay ----------------------------------------------------------------------------------
func _build() -> void:
	if is_instance_valid(_root):
		_root.queue_free()
	var s := _al("Settings")

	var overlay := Control.new()
	overlay.name = "PauseOverlay"
	overlay.set_anchors_preset(Control.PRESET_FULL_RECT)
	overlay.mouse_filter = Control.MOUSE_FILTER_STOP

	var dim := ColorRect.new()
	dim.color = Color(0.02, 0.02, 0.04, 0.85)
	dim.set_anchors_preset(Control.PRESET_FULL_RECT)
	overlay.add_child(dim)

	var center := CenterContainer.new()
	center.set_anchors_preset(Control.PRESET_FULL_RECT)
	overlay.add_child(center)

	var box := VBoxContainer.new()
	box.alignment = BoxContainer.ALIGNMENT_CENTER
	box.add_theme_constant_override("separation", 18)
	center.add_child(box)

	var title := Label.new()
	title.text = "PAUSED"
	title.horizontal_alignment = HORIZONTAL_ALIGNMENT_CENTER
	if s != null:
		s.apply_text_scale(title, 48)
	else:
		title.add_theme_font_size_override("font_size", 48)
	box.add_child(title)

	box.add_child(_menu_button("Resume", resume, s))
	box.add_child(_menu_button("Settings", _open_settings, s))
	box.add_child(_menu_button("Quit to Title", quit_to_title, s))

	add_child(overlay)
	_root = overlay

func _menu_button(text: String, cb: Callable, s: Node) -> Button:
	var b := Button.new()
	b.text = text
	b.custom_minimum_size = Vector2(260, 48)
	b.pressed.connect(cb)
	if s != null:
		s.apply_text_scale(b, 20)
	return b

# --- Settings sub-panel -----------------------------------------------------------------------
func _open_settings() -> void:
	_close_settings()
	var script := load(SETTINGS_PANEL) as GDScript
	if script == null:
		return
	_settings_panel = script.new()
	add_child(_settings_panel)
	if _settings_panel.has_method("open"):
		_settings_panel.open()

func _close_settings() -> void:
	if _settings_panel != null and is_instance_valid(_settings_panel):
		_settings_panel.queue_free()
	_settings_panel = null

func _al(autoload_name: String) -> Node:
	var ml := Engine.get_main_loop()
	if ml == null or not (ml is SceneTree):
		return null
	return (ml as SceneTree).root.get_node_or_null(autoload_name)
