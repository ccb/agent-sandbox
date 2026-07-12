extends Control
## On-screen dialogue panel. Renders the current line + options as buttons, PLUS a free-text box so the
## player can type their own reply (the hybrid input — design §2.6). Two option shapes share one panel:
## scripted tree options (carry "label" → DialogueManager.choose) and LLM reply chips (carry "text" →
## DialogueManager.send_utterance, i.e. the chip's text IS the player's line). An explicit "(Leave)" chip
## is always appended. Pauses player movement (via DialogueManager.active) while open. Lives in the HUD.

@onready var _speaker: Label = $Box/Margin/Body/Speaker
@onready var _text: Label = $Box/Margin/Body/Text
@onready var _options: VBoxContainer = $Box/Margin/Body/Options
@onready var _input: LineEdit = $Box/Margin/Body/InputRow/Input
@onready var _send: Button = $Box/Margin/Body/InputRow/Send
## M19 — the speaker's portrait slot (a reusable Portrait widget, left of the text). Shows the NPC
## you're talking to; falls back to a neutral silhouette for an artless speaker; clears on close.
@onready var _portrait: Portrait = $Box/Portrait

var _hotkey_count: int = 0   # number of badged reply chips (1–4) the digit keys may trigger
var _thinking: Label = null  # the "thinking…" pending indicator (built in code, shown while a turn is in flight)

func _ready() -> void:
	visible = false
	# A "thinking…" indicator shown while a converse turn is in flight (GAP-2.3): the LLM reply now
	# arrives asynchronously, so the panel must SHOW that it's waiting instead of appearing frozen.
	# Built in code (a sibling of the input row) so the single .tscn writer isn't disturbed.
	_thinking = Label.new()
	_thinking.text = "…thinking…"
	_thinking.modulate = Color(0.7, 0.7, 0.75)
	_thinking.visible = false
	var body := $Box/Margin/Body
	body.add_child(_thinking)
	body.move_child(_thinking, ($Box/Margin/Body/InputRow as Node).get_index())
	DialogueManager.dialogue_started.connect(_on_started)
	DialogueManager.node_changed.connect(_on_node_changed)
	DialogueManager.converse_pending.connect(_on_converse_pending)
	DialogueManager.dialogue_ended.connect(_on_ended)
	# Enter-to-send via text_submitted, which fires only on a COMMITTED line — so an IME composition's
	# commit Enter never ships half-composed text (the Yumina IME bug, avoided structurally rather than
	# by guarding a raw KEY_ENTER).
	_input.text_submitted.connect(_on_text_submitted)
	_send.pressed.connect(_on_send_pressed)

func _on_started(npc_id: String) -> void:
	visible = true
	get_tree().paused = false   # gate the player, not the whole tree
	_input.clear()
	# M19: the instant a conversation opens we KNOW who is speaking (the npc id) — show their face.
	# dialogue_started re-fires whenever the active NPC switches, so this keeps the portrait in sync.
	if _portrait != null:
		_portrait.show_npc(npc_id)

## Test seam / observers: the texture in the portrait slot (null when the silhouette is showing).
func portrait_texture() -> Texture2D:
	return _portrait.current_texture() if _portrait != null else null

## A converse turn was kicked (GAP-2.3): flip to the "thinking…" pending state — disable the send
## button, dim/lock the input, and show the indicator — until node_changed lands with the reply. This
## replaces the old hard freeze: the window keeps painting and accepting the (Leave) chip while the
## worker thread runs the LLM round-trip.
func _on_converse_pending(speaker: String) -> void:
	if speaker != "":
		_speaker.text = speaker
		_speaker.visible = true
	_set_thinking(true)

## Enter/leave the pending UI. In 'thinking': the Send button is disabled, the input is read-only, and
## the indicator shows — so the player can't double-send while a turn is in flight. The LAST option
## chip is always "(Leave)"; it stays enabled so the player can ALWAYS exit mid-think (leaving is now
## safe — a reply that lands after _end() is ignored). Leaving 'thinking' restores an interactive panel.
func _set_thinking(on: bool) -> void:
	if _thinking != null:
		_thinking.visible = on
	_send.disabled = on
	_input.editable = not on
	var kids := _options.get_children()
	for i in kids.size():
		# The (Leave) chip (last child) stays clickable even while thinking; the reply chips lock.
		(kids[i] as Button).disabled = on and i < kids.size() - 1

func _on_node_changed(speaker: String, text: String, options: Array) -> void:
	_set_thinking(false)   # a reply landed — leave the pending state and render it
	_speaker.text = speaker
	_speaker.visible = speaker != ""
	# An empty say (a timed-out/errored round-trip, or a wordless refusal) shows a neutral beat, never blank.
	_text.text = text if text != "" else "…"
	for c in _options.get_children():
		c.queue_free()
	var node_id := DialogueManager.current_node_id()
	var hotkey := 1
	for i in options.size():
		if not (options[i] is Dictionary):
			continue   # a non-dict reply element would crash the typed assignment below — skip it
		var opt: Dictionary = options[i]
		var b := Button.new()
		if opt.has("label"):
			# Scripted tree option: choose by index (legacy fallback path).
			var label := String(opt.get("label", "..."))
			if bool(opt.get("contradiction", false)):
				label = "[!] " + label
				b.add_theme_color_override("font_color", Color(0.95, 0.7, 0.5))
			b.text = label
			b.pressed.connect(DialogueManager.choose.bind(node_id, i))
		elif opt.has("text"):
			# LLM reply chip: the chip's text IS the player's line. Capped 1–4 hotkey badge.
			var rtext := String(opt.get("text", "..."))
			b.text = ("%d. %s" % [hotkey, rtext]) if hotkey <= 4 else rtext
			hotkey += 1
			b.pressed.connect(_say.bind(rtext))
		else:
			b.queue_free()
			continue   # malformed option (neither "label" nor "text") — drop it rather than show junk
		_options.add_child(b)
	# Only the badged reply chips (the first up-to-4) are number-key targets — NEVER the appended
	# "(Leave)" chip, so pressing a digit can't silently end the conversation.
	_hotkey_count = mini(hotkey - 1, 4)
	# Always offer an explicit exit (decided: engine appends a leave chip so the player can always go).
	var leave := Button.new()
	leave.text = "(Leave)"
	leave.pressed.connect(DialogueManager._end)
	_options.add_child(leave)
	_input.editable = true
	_input.grab_focus()

func _say(text: String) -> void:
	DialogueManager.send_utterance(DialogueManager.active_npc(), text)

func _on_text_submitted(text: String) -> void:
	_submit(text)

func _on_send_pressed() -> void:
	_submit(_input.text)

func _submit(text: String) -> void:
	var t := text.strip_edges()
	if t == "":
		return
	_input.clear()
	DialogueManager.send_utterance(DialogueManager.active_npc(), t)

## 1–4 number-key hotkeys for the first reply chips. _unhandled_input only fires for keys the focused
## LineEdit did NOT consume, so while the player is typing the digits go into the box; the hotkeys fire
## only when the box is unfocused — no conflict.
func _unhandled_input(event: InputEvent) -> void:
	if not visible:
		return
	if event is InputEventKey and event.pressed and not event.echo:
		var k: int = (event as InputEventKey).keycode
		if k >= KEY_1 and k <= KEY_4:
			var idx: int = k - KEY_1
			if idx < _hotkey_count:   # only the real reply chips, never "(Leave)"
				var chips := _options.get_children()
				if idx < chips.size():
					(chips[idx] as Button).pressed.emit()
					get_viewport().set_input_as_handled()

func _on_ended() -> void:
	visible = false
	if _portrait != null:
		_portrait.clear()   # M19: no speaker on screen once the conversation closes
