extends Control
## M_cast (user request) — THE CAST: the title-screen NPC dossier roulette panel.
##
## Opened from the TITLE (BootController's "The Cast" button — outside any run): one large
## character card center-stage in the Victorian-occult dossier styling (the shared tingen_theme +
## the MetaSurface ledger's gilt/ink palette), ◀ ▶ buttons and ←/→/A/D keys cycling the whole
## roster, a name/dot strip showing the deck position, and a SPIN button that shuffles fast and
## lands on a random card.
##
## v2 (user correction): "write everything on there" — the card is a FULL DESIGN-REFERENCE
## DOSSIER. Every authored field renders in headed sections (VOICE / GOALS / SECRETS /
## KNOWLEDGE / SCHEDULE / RECORDS), and the BENEATH THE MASK layer (pathway, both forms' kits
## with real numbers, the monster flip, learned ledger lines) shows on every Beyonder by
## default: CastCodex.SHOW_ALL ships true. The codex-gated redaction block is KEPT behind that
## one flag for a later player-facing mode. The dossier overflows the fixed card frame, so the
## text column scrolls (mouse wheel + scrollbar — the DossierScroll container).
##
## Engineering shape (the SettingsPanel/MetaSurface patterns):
##   * ALL content decisions live in the pure CastCodex builder (data in -> card models out); this
##     node only renders models. No NPC-id branches anywhere (§8).
##   * Headless-driveable: open/close/show_card/next/prev/spin_to/spin/flip are plain state; every
##     ANIMATION (card slide, the spin shuffle, the flip) is live-only (_is_live — the
##     CombatFeedback pattern), so the deterministic gates never see a tween.
##   * SPIN randomness is a UI-LAYER RandomNumberGenerator private to this panel — it never
##     touches the sim RNG streams (no global randi/randomize), and the sims never mount this
##     panel. Tests drive selection deterministically through spin_to/show_card.
##   * The caller owns mounting/freeing (BootController.open_cast); process_mode ALWAYS so the
##     panel would also survive a paused tree.

const GILT := Color(0.82, 0.66, 0.35, 1.0)        # the theme's gilt accent (MetaSurface header)
const GILT_DIM := Color(0.7, 0.56, 0.29, 0.9)
const INK_TEXT := Color(0.87, 0.82, 0.7, 1.0)
const DIM_TEXT := Color(0.62, 0.58, 0.5, 1.0)
const CODEX_TEXT := Color(0.78, 0.74, 0.64, 1.0)

var _open: bool = false
var _view: Control = null
var _cards: Array = []
var _index: int = 0
var _flipped: bool = false
var _spinning: bool = false
var _spin_tween: Tween = null
## UI-layer RNG only (the spin's shuffle landing). NEVER the sim streams.
var _ui_rng := RandomNumberGenerator.new()

# Card-view node refs (rebuilt per open()).
var _name_lbl: Label = null
var _role_lbl: Label = null
var _portrait_img: TextureRect = null
var _portrait_silhouette: Label = null
var _doss_scroll: ScrollContainer = null
var _doss_box: VBoxContainer = null
var _dots_lbl: Label = null
var _pos_lbl: Label = null
var _card_panel: PanelContainer = null

func _ready() -> void:
	process_mode = Node.PROCESS_MODE_ALWAYS
	set_anchors_preset(Control.PRESET_FULL_RECT)
	mouse_filter = Control.MOUSE_FILTER_IGNORE
	_ui_rng.randomize()

func is_open() -> bool:
	return _open

## Open (or re-open, re-reading the ledger) the dossier. `codex_override` is the TEST seam: an
## Array stands in for the persistent codex so harnesses never touch a profile; null (live) reads
## RunManager.meta_codex() — the M27 ledger.
func open(codex_override: Variant = null) -> void:
	if _open:
		close()
	_fit_to_viewport()
	_cards = _build_cards(codex_override)
	_build_ui()
	_open = true
	_show_card(0)

## Pin this root overlay to the WHOLE viewport. A runtime-built Control mounted under a
## CanvasLayer is NOT sized by anchors applied after add_child (the title's own bg works only
## because its preset lands BEFORE mounting) — the probe caught the panel collapsed to content
## size at top-left. Set the rect explicitly and track window resizes.
func _fit_to_viewport() -> void:
	set_anchors_preset(Control.PRESET_FULL_RECT)
	if not is_inside_tree():
		return
	position = Vector2.ZERO
	size = get_viewport_rect().size
	var vp := get_viewport()
	if vp != null and not vp.size_changed.is_connected(_on_viewport_resized):
		vp.size_changed.connect(_on_viewport_resized)

func _on_viewport_resized() -> void:
	if is_inside_tree():
		position = Vector2.ZERO
		size = get_viewport_rect().size

func close() -> void:
	if _spin_tween != null and _spin_tween.is_valid():
		_spin_tween.kill()
	_spin_tween = null
	_spinning = false
	_flipped = false
	if is_instance_valid(_view):
		_view.queue_free()
	_view = null
	_open = false

# --- Deck state (the headless/test seams) -------------------------------------------------------
func card_count() -> int:
	return _cards.size()

func current_index() -> int:
	return _index

## The current card MODEL (a deep copy — models are read-only content).
func current_card() -> Dictionary:
	if _cards.is_empty():
		return {}
	return (_cards[_index] as Dictionary).duplicate(true)

## The deck index of an NPC id, -1 when absent.
func index_of(npc_id: String) -> int:
	for i in _cards.size():
		if String((_cards[i] as Dictionary).get("id", "")) == npc_id:
			return i
	return -1

## Jump the deck straight to a card (wraps; the test/probe seam and the arrows' landing).
func show_card(i: int) -> void:
	if _cards.is_empty() or _spinning:
		return
	_show_card(i)
	_slide_anim()

func next() -> void:
	show_card(_index + 1)

func prev() -> void:
	show_card(_index - 1)

## SPIN: pick a random deck index with the panel's private UI-layer RNG and land on it. Live play
## shuffles fast through the deck first; headless lands instantly. Returns the landing index.
func spin() -> int:
	if _cards.is_empty() or _spinning:
		return -1
	var target := _ui_rng.randi_range(0, _cards.size() - 1)
	spin_to(target)
	return target

## Deterministic landing seam (tests/probe drive this directly).
func spin_to(i: int) -> void:
	if _cards.is_empty() or _spinning:
		return
	var n := _cards.size()
	var target := ((i % n) + n) % n
	if not _is_live():
		_show_card(target)
		return
	_begin_spin_anim(target)

func is_spinning() -> bool:
	return _spinning

# --- The beneath-the-mask flip -------------------------------------------------------------------
## Only a REVEALED card with monster art has a flip side.
func can_flip() -> bool:
	if _cards.is_empty():
		return false
	var card: Dictionary = _cards[_index]
	var secret: Dictionary = card.get("secret", {}) if card.get("secret") is Dictionary else {}
	return String(card.get("state", "")) == "revealed" and String(secret.get("monster_art", "")) != ""

func is_flipped() -> bool:
	return _flipped

func flip() -> void:
	if not can_flip() or _spinning:
		return
	_flipped = not _flipped
	_apply_portrait()
	if _is_live() and _portrait_img != null:
		# The flip squeeze: a quick horizontal collapse/expand sells the card turning over.
		var host := _portrait_img.get_parent()
		if host is Control:
			var tw := create_tween()
			(host as Control).scale = Vector2(0.05, 1.0)
			(host as Control).pivot_offset = (host as Control).size * 0.5
			tw.tween_property(host, "scale", Vector2.ONE, 0.18).set_trans(Tween.TRANS_QUAD)

# --- Input (arrows / A / D / Esc) ----------------------------------------------------------------
func _unhandled_input(event: InputEvent) -> void:
	if not _open:
		return
	if event is InputEventKey and (event as InputEventKey).pressed and not (event as InputEventKey).echo:
		var k := (event as InputEventKey).keycode
		if k == KEY_LEFT or k == KEY_A:
			prev()
			get_viewport().set_input_as_handled()
		elif k == KEY_RIGHT or k == KEY_D:
			next()
			get_viewport().set_input_as_handled()
		elif k == KEY_ESCAPE:
			close()
			get_viewport().set_input_as_handled()

# --- Model building (all content through the pure builder) ---------------------------------------
func _build_cards(codex_override: Variant) -> Array:
	var cc := load("res://src/CastCodex.gd") as GDScript
	if cc == null:
		return []
	var npcs := _npc_defs()
	var forms: Dictionary = {}
	var abilities: Dictionary = {}
	var adb := get_node_or_null("/root/AbilityDB")
	if adb != null and adb.has_method("all_form_ids"):
		for f in adb.all_form_ids():
			forms[String(f)] = adb.form_def(String(f))
	if adb != null:
		for aid in adb.all_ability_ids():
			abilities[String(aid)] = adb.ability_for(String(aid))
	var codex: Array = []
	if codex_override is Array:
		codex = codex_override
	else:
		var rm := get_node_or_null("/root/RunManager")
		if rm != null and rm.has_method("meta_codex"):
			codex = rm.meta_codex()
	return cc.build_cards(npcs, forms, abilities, _districts(), codex)

func _npc_defs() -> Dictionary:
	var db := get_node_or_null("/root/NpcDB")
	if db != null and db.get("defs") is Dictionary:
		return db.defs
	var parsed: Variant = JSON.parse_string(FileAccess.get_file_as_string("res://data/npcs.json"))
	return parsed if parsed is Dictionary else {}

func _districts() -> Array:
	var parsed: Variant = JSON.parse_string(FileAccess.get_file_as_string("res://data/districts.json"))
	return parsed if parsed is Array else []

# --- UI build (the shared occult theme styles panels/buttons; colors mirror the title ledger) -----
func _build_ui() -> void:
	var dim := ColorRect.new()
	dim.name = "CastDim"
	dim.color = Color(0.03, 0.028, 0.045, 0.97)
	dim.set_anchors_preset(Control.PRESET_FULL_RECT)
	dim.mouse_filter = Control.MOUSE_FILTER_STOP
	add_child(dim)
	_view = dim

	var margin := MarginContainer.new()
	margin.set_anchors_preset(Control.PRESET_FULL_RECT)
	for m in ["margin_left", "margin_right"]:
		margin.add_theme_constant_override(m, 28)
	for m in ["margin_top", "margin_bottom"]:
		margin.add_theme_constant_override(m, 14)
	dim.add_child(margin)

	var col := VBoxContainer.new()
	col.add_theme_constant_override("separation", 8)
	margin.add_child(col)

	# Header row: title + subtitle + Close.
	var head := HBoxContainer.new()
	head.add_theme_constant_override("separation", 14)
	col.add_child(head)
	var title := Label.new()
	title.text = "THE CAST"
	title.add_theme_font_size_override("font_size", 30)
	title.add_theme_color_override("font_color", GILT)
	head.add_child(title)
	var sub := Label.new()
	sub.text = "— a dossier of Tingen's people, and of what walks beneath."
	sub.add_theme_color_override("font_color", DIM_TEXT)
	sub.size_flags_vertical = Control.SIZE_SHRINK_END
	head.add_child(sub)
	var spring := Control.new()
	spring.size_flags_horizontal = Control.SIZE_EXPAND_FILL
	head.add_child(spring)
	var close_btn := Button.new()
	close_btn.name = "CastCloseButton"
	close_btn.text = "Close  [Esc]"
	close_btn.pressed.connect(close)
	head.add_child(close_btn)

	# Center row: ◀ | the card | ▶.
	var center := HBoxContainer.new()
	center.size_flags_vertical = Control.SIZE_EXPAND_FILL
	center.add_theme_constant_override("separation", 16)
	col.add_child(center)
	var prev_btn := Button.new()
	prev_btn.name = "CastPrevButton"
	prev_btn.text = "◀"
	prev_btn.custom_minimum_size = Vector2(52, 96)
	prev_btn.size_flags_vertical = Control.SIZE_SHRINK_CENTER
	prev_btn.pressed.connect(prev)
	center.add_child(prev_btn)

	var card_center := CenterContainer.new()
	card_center.size_flags_horizontal = Control.SIZE_EXPAND_FILL
	card_center.size_flags_vertical = Control.SIZE_EXPAND_FILL
	center.add_child(card_center)
	_card_panel = PanelContainer.new()
	_card_panel.name = "CastCard"
	_card_panel.custom_minimum_size = Vector2(760, 520)
	card_center.add_child(_card_panel)
	_build_card_view(_card_panel)

	var next_btn := Button.new()
	next_btn.name = "CastNextButton"
	next_btn.text = "▶"
	next_btn.custom_minimum_size = Vector2(52, 96)
	next_btn.size_flags_vertical = Control.SIZE_SHRINK_CENTER
	next_btn.pressed.connect(next)
	center.add_child(next_btn)

	# Footer: the deck strip (dots + position) and the Spin button.
	var foot := VBoxContainer.new()
	foot.add_theme_constant_override("separation", 4)
	col.add_child(foot)
	_dots_lbl = Label.new()
	_dots_lbl.name = "DeckStrip"
	_dots_lbl.horizontal_alignment = HORIZONTAL_ALIGNMENT_CENTER
	_dots_lbl.add_theme_font_size_override("font_size", 16)
	_dots_lbl.add_theme_color_override("font_color", GILT_DIM)
	foot.add_child(_dots_lbl)
	_pos_lbl = Label.new()
	_pos_lbl.name = "DeckPos"
	_pos_lbl.horizontal_alignment = HORIZONTAL_ALIGNMENT_CENTER
	_pos_lbl.add_theme_font_size_override("font_size", 13)
	_pos_lbl.add_theme_color_override("font_color", DIM_TEXT)
	foot.add_child(_pos_lbl)
	var spin_row := CenterContainer.new()
	foot.add_child(spin_row)
	var spin_btn := Button.new()
	spin_btn.name = "CastSpinButton"
	spin_btn.text = "Spin the Deck"
	spin_btn.custom_minimum_size = Vector2(220, 40)
	spin_btn.pressed.connect(func() -> void: spin())
	spin_row.add_child(spin_btn)

## The card's inner layout: name/role header, then portrait | dossier text columns.
func _build_card_view(host: PanelContainer) -> void:
	var pad := MarginContainer.new()
	for m in ["margin_left", "margin_right", "margin_top", "margin_bottom"]:
		pad.add_theme_constant_override(m, 18)
	host.add_child(pad)
	var box := VBoxContainer.new()
	box.add_theme_constant_override("separation", 6)
	pad.add_child(box)

	_name_lbl = Label.new()
	_name_lbl.name = "CardName"
	_name_lbl.add_theme_font_size_override("font_size", 26)
	_name_lbl.add_theme_color_override("font_color", GILT)
	box.add_child(_name_lbl)
	_role_lbl = Label.new()
	_role_lbl.name = "CardRole"
	_role_lbl.add_theme_font_size_override("font_size", 13)
	_role_lbl.add_theme_color_override("font_color", DIM_TEXT)
	box.add_child(_role_lbl)
	box.add_child(HSeparator.new())

	var body := HBoxContainer.new()
	body.add_theme_constant_override("separation", 18)
	body.size_flags_vertical = Control.SIZE_EXPAND_FILL
	box.add_child(body)

	# Left column: the framed portrait (flips to the monster face when the mask drops).
	var frame := Panel.new()
	frame.name = "PortraitFrame"
	frame.custom_minimum_size = Vector2(240, 330)
	frame.size_flags_vertical = Control.SIZE_SHRINK_BEGIN
	frame.clip_contents = true
	body.add_child(frame)
	_portrait_silhouette = Label.new()
	_portrait_silhouette.name = "PortraitSilhouette"
	_portrait_silhouette.text = "?"
	_portrait_silhouette.set_anchors_preset(Control.PRESET_FULL_RECT)
	_portrait_silhouette.horizontal_alignment = HORIZONTAL_ALIGNMENT_CENTER
	_portrait_silhouette.vertical_alignment = VERTICAL_ALIGNMENT_CENTER
	_portrait_silhouette.add_theme_font_size_override("font_size", 48)
	_portrait_silhouette.add_theme_color_override("font_color", Color(0.45, 0.43, 0.38, 0.8))
	frame.add_child(_portrait_silhouette)
	_portrait_img = TextureRect.new()
	_portrait_img.name = "PortraitImage"
	_portrait_img.set_anchors_preset(Control.PRESET_FULL_RECT)
	_portrait_img.expand_mode = TextureRect.EXPAND_IGNORE_SIZE
	_portrait_img.stretch_mode = TextureRect.STRETCH_KEEP_ASPECT_CENTERED
	frame.add_child(_portrait_img)

	# Right column: the FULL dossier text, scrolling inside the fixed card frame (v2 — the
	# show-everything card overflows by design; mouse wheel + scrollbar via ScrollContainer).
	_doss_scroll = ScrollContainer.new()
	_doss_scroll.name = "DossierScroll"
	_doss_scroll.size_flags_horizontal = Control.SIZE_EXPAND_FILL
	_doss_scroll.size_flags_vertical = Control.SIZE_EXPAND_FILL
	_doss_scroll.horizontal_scroll_mode = ScrollContainer.SCROLL_MODE_DISABLED
	_doss_scroll.vertical_scroll_mode = ScrollContainer.SCROLL_MODE_AUTO
	body.add_child(_doss_scroll)
	_doss_box = VBoxContainer.new()
	_doss_box.name = "DossierBody"
	_doss_box.size_flags_horizontal = Control.SIZE_EXPAND_FILL
	_doss_box.add_theme_constant_override("separation", 5)
	_doss_scroll.add_child(_doss_box)

# --- Rendering the current model -------------------------------------------------------------------
func _show_card(i: int) -> void:
	if _cards.is_empty():
		return
	var n := _cards.size()
	_index = ((i % n) + n) % n
	_flipped = false
	_render_card()

func _render_card() -> void:
	if _view == null or _name_lbl == null:
		return
	var card: Dictionary = _cards[_index]
	_name_lbl.text = String(card.get("name", ""))
	_role_lbl.text = "%s   ·   Haunts: %s" % [String(card.get("role", "")), String(card.get("haunts", ""))]
	_apply_portrait()
	_render_dossier(card)
	if _doss_scroll != null:
		_doss_scroll.scroll_vertical = 0   # a fresh card always opens at the top
	_render_strip()

# --- The dossier scroll seams (tests/probe drive these; live play uses the wheel/scrollbar) ------
func scroll_dossier(px: int) -> void:
	if _doss_scroll != null:
		_doss_scroll.scroll_vertical = px

func dossier_scroll_value() -> int:
	return int(_doss_scroll.scroll_vertical) if _doss_scroll != null else 0

## The big portrait slot: the public face, or (flipped, revealed only) the monster art.
func _apply_portrait() -> void:
	if _portrait_img == null:
		return
	var card: Dictionary = _cards[_index]
	var path := String(card.get("portrait", ""))
	if _flipped:
		var secret: Dictionary = card.get("secret", {}) if card.get("secret") is Dictionary else {}
		path = String(secret.get("monster_art", ""))
	var tex: Texture2D = null
	if path != "" and ResourceLoader.exists(path):
		var res := load(path)
		if res is Texture2D:
			tex = res
	_portrait_img.texture = tex
	_portrait_img.visible = tex != null
	if _portrait_silhouette != null:
		_portrait_silhouette.visible = tex == null

## The FULL dossier body (v2 — user: "write everything on there"): persona, then every authored
## section under a clear header, then the Beyond layer — revealed by default (SHOW_ALL), with the
## kept redaction block only when the gate flag is off and the codex has not learned this NPC.
func _render_dossier(card: Dictionary) -> void:
	if _doss_box == null:
		return
	for ch in _doss_box.get_children():
		ch.queue_free()
	# Persona: the description leads, the voice line under its own header.
	_doss_box.add_child(_lbl(String(card.get("description", "")), 13, INK_TEXT, true))
	_add_section("VOICE", [String(card.get("voice", ""))], false)
	_add_section("GOALS", card.get("goals", []), true)
	var secrets: Array = card.get("secrets", []) if card.get("secrets") is Array else []
	if secrets.is_empty():
		_add_section("SECRETS", ["None recorded."], false)
	else:
		_add_section("SECRETS", secrets, true)
	_add_section("KNOWLEDGE", card.get("knowledge", []), true)
	_add_section("SCHEDULE", card.get("schedule_lines", []), false)
	_add_section("RECORDS", card.get("records", []), false)
	# The Beyond layer.
	var state := String(card.get("state", ""))
	if state == "revealed":
		var secret: Dictionary = card.get("secret", {}) if card.get("secret") is Dictionary else {}
		_doss_box.add_child(_hline())
		_doss_box.add_child(_lbl("BENEATH THE MASK", 14, GILT))
		var pw := String(secret.get("pathway", ""))
		var seq := int(secret.get("sequence", 0))
		var pw_line := "Pathway: %s" % (pw.capitalize() if pw != "" else "unrecorded")
		if seq > 0:
			pw_line += "   ·   Sequence %d" % seq
		_doss_box.add_child(_lbl(pw_line, 13, INK_TEXT))
		var forms: Array = secret.get("forms", []) if secret.get("forms") is Array else []
		var fnames: Array = []
		for f in forms:
			fnames.append(String(f).capitalize())
		if not fnames.is_empty():
			_doss_box.add_child(_lbl("Combat forms: %s" % " → ".join(PackedStringArray(fnames)), 13, INK_TEXT))
		# v2: EACH phase's own kit, every ability with its flavor line AND its real numbers.
		var fks: Array = secret.get("form_kits", []) if secret.get("form_kits") is Array else []
		for fk in fks:
			var fkd: Dictionary = fk
			var phase := "the monster beneath" if bool(fkd.get("monster", false)) else "the human phase"
			_doss_box.add_child(_lbl("◈  %s — %s" % [String(fkd.get("form", "")).capitalize(), phase],
				12, GILT_DIM))
			var abl: Array = fkd.get("abilities", []) if fkd.get("abilities") is Array else []
			for a in abl:
				var ad: Dictionary = a
				_doss_box.add_child(_lbl("•  %s — %s" % [String(ad.get("name", "")), String(ad.get("description", ""))],
					12, CODEX_TEXT, true))
				var stats := String(ad.get("stats", ""))
				if stats != "":
					_doss_box.add_child(_lbl("       %s" % stats, 11, DIM_TEXT))
		if can_flip():
			var flip_btn := Button.new()
			flip_btn.name = "FlipButton"
			flip_btn.text = "Turn the card — see beneath the mask"
			flip_btn.pressed.connect(flip)
			_doss_box.add_child(flip_btn)
		var lines: Array = card.get("codex_lines", []) if card.get("codex_lines") is Array else []
		if not lines.is_empty():
			_doss_box.add_child(_lbl("The ledger records:", 12, GILT_DIM))
			for l in lines:
				_doss_box.add_child(_lbl("“%s”" % String(l), 12, CODEX_TEXT, true))
	elif state == "redacted":
		# The KEPT gated mode (CastCodex.SHOW_ALL=false / a false show_all arg) — unchanged.
		_doss_box.add_child(_hline())
		_doss_box.add_child(_lbl("BENEATH THE MASK", 14, GILT_DIM))
		_doss_box.add_child(_lbl("████████████████████████████", 13, Color(0.32, 0.3, 0.34, 1.0)))
		_doss_box.add_child(_lbl(String(card.get("secret_line", "")), 13, DIM_TEXT, true))
		_doss_box.add_child(_lbl("██████████████████████", 13, Color(0.32, 0.3, 0.34, 1.0)))
	else:
		_doss_box.add_child(_hline())
		_doss_box.add_child(_lbl(String(card.get("secret_line", "")), 13, DIM_TEXT, true))

## One headed dossier section: a gilt header + its lines (bulleted for list-ish sections).
## An EMPTY section renders nothing — no header noise for unauthored fields.
func _add_section(header: String, lines_v: Variant, bullets: bool) -> void:
	var lines: Array = lines_v if lines_v is Array else []
	var clean: Array = []
	for l in lines:
		if String(l).strip_edges() != "":
			clean.append(String(l))
	if clean.is_empty():
		return
	_doss_box.add_child(_hline())
	_doss_box.add_child(_lbl(header, 13, GILT))
	for l in clean:
		_doss_box.add_child(_lbl(("•  %s" % l) if bullets else l, 12,
			CODEX_TEXT if bullets else INK_TEXT, true))

## The deck strip: a dot per card (the current one gilt-marked) + "n / N — Name".
func _render_strip() -> void:
	if _dots_lbl == null:
		return
	var dots := ""
	for i in _cards.size():
		dots += "●" if i == _index else "·"
	_dots_lbl.text = dots
	_pos_lbl.text = "%d / %d   —   %s" % [_index + 1, _cards.size(), String((_cards[_index] as Dictionary).get("name", ""))]

func _lbl(text: String, size: int, color: Color, wrap: bool = false) -> Label:
	var l := Label.new()
	l.text = text
	l.add_theme_font_size_override("font_size", size)
	l.add_theme_color_override("font_color", color)
	if wrap:
		l.autowrap_mode = TextServer.AUTOWRAP_WORD_SMART
		l.custom_minimum_size = Vector2(420, 0)
	return l

func _hline() -> HSeparator:
	return HSeparator.new()

# --- Live-only animation ---------------------------------------------------------------------------
## A quick slide-in nudge as a card lands (arrows). Cosmetic; never runs headless.
func _slide_anim() -> void:
	if not _is_live() or _card_panel == null or _spinning:
		return
	var tw := create_tween()
	_card_panel.modulate = Color(1, 1, 1, 0.35)
	tw.tween_property(_card_panel, "modulate", Color(1, 1, 1, 1.0), 0.16)

## The SPIN shuffle: rattle forward through the deck on a growing interval and LAND on `target`
## (2 full laps + the distance), then settle. Live-only; the state seam is _show_card.
func _begin_spin_anim(target: int) -> void:
	var n := _cards.size()
	_spinning = true
	var steps: int = 2 * n + ((target - _index) % n + n) % n
	var tw := create_tween()
	_spin_tween = tw
	var delay := 0.022
	for s in steps:
		tw.tween_interval(delay)
		tw.tween_callback(_spin_step)
		delay = minf(0.16, delay * 1.09)
	tw.tween_callback(func() -> void:
		_spinning = false
		_spin_tween = null
		_slide_anim())

func _spin_step() -> void:
	if _cards.is_empty():
		return
	_index = (_index + 1) % _cards.size()
	_flipped = false
	_render_card()

## True only with a real display attached (live play); false under --headless — where every
## animation must collapse to instant state (the CombatFeedback._is_live pattern).
func _is_live() -> bool:
	return DisplayServer.get_name() != "headless"
