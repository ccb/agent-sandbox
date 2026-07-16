extends SceneTree
## P3 (experiential wave) — COMBAT READABILITY. Runs headless:
##   godot --headless --path tingen -s tests/test_combat_readability.gd
## Also folded into the main suite (run_tests.gd `_test_combat_readability`) via the SAME
## run_all() entry point, so both share one set of assertions.
##
## Six pins (all state/asset asserts — the PIXELS are proven by tests/screenshot_probe.gd):
##   (a) the bieber_monster anim strips on disk are ALPHA-KEYED (the audit's grey-sliver bug:
##       RGB strips render every anim cue as an opaque grey panel);
##   (b) CombatExecutor._play_anim scales a strip so the FIGURE (the alpha bbox band, not the
##       gen sheet's huge transparent cell) renders at the standee height — no more ~8px
##       sliver — and the death strip still HOLDS its last frame;
##   (c) enemy TELLS: ability_cast_started/finished/interrupted drive CombatFeedback's tell
##       ledger (arc for a strike, circle otherwise; the player's own casts never tell) —
##       the VISUAL nodes are live-only (_is_live), so headless spawns nothing;
##   (d) enemy HP PIPS: the NPC body exposes a BANDED pip count that mirrors the ONE peer-hp
##       banding (Perception.hp_band — never exact numbers), shown in combat mode only; the
##       pip NODE is live-only;
##   (e) MUZZLE FLASH: an ammo-costing art finishing spawns a CombatFx muzzle-flash transient
##       at the cached cast dir (data-driven off cost.ammo — engine-neutral, any gun user);
##       a free art spawns none;
##   (f) RETICLE: CombatFeedback.reticle_active() is true exactly when a live non-player
##       combatant shares the player proxy's room; the reticle NODE is live-only.

const DT: float = 1.0 / 60.0

func _init() -> void:
	await process_frame
	await process_frame
	# N1 (sprint safety): sandbox EVERY persistent path (meta/save/settings/hints/playlog) into
	# user://test_sandbox/<run>/ and arm the write guard — see src/TestSandbox.gd.
	preload("res://src/TestSandbox.gd").activate(root)
	var r: Dictionary = await run_all()
	print("\n=== combat_readability: %d passed, %d failed ===" % [int(r["passed"]), int(r["failed"])])
	quit(1 if int(r["failed"]) > 0 else 0)

## The one entry point (returns {passed, failed}); folded into run_tests.gd. A coroutine (the
## pips step awaits a frame to stage an NPC body), so callers must `await run_all()`.
static func run_all() -> Dictionary:
	var c := {"passed": 0, "failed": 0}
	var root: Node = (Engine.get_main_loop() as SceneTree).root
	_a_bieber_strips_are_alpha_keyed(c)
	_b_strip_scaling_matches_standee(c)
	_g_n6_attack_strips_place_and_degrade(c)
	_c_tells_ride_the_telegraph_events(c, root)
	await _d_hp_pips_mirror_peer_banding(c, root)
	_e_muzzle_flash_on_ammo_cost_cast(c, root)
	_f_reticle_active_in_combat_rooms(c, root)
	return c

# --- (a) the anim strips must carry alpha (the grey-sliver audit bug) ---------------------------
static func _a_bieber_strips_are_alpha_keyed(c: Dictionary) -> void:
	print("[a: the bieber_monster anim strips are ALPHA-KEYED (no opaque grey panels)]")
	for suffix in ["attack_side", "hurt_down", "death_down"]:
		var path := "res://assets/anim/bieber_monster_%s.png" % suffix
		_check(c, ResourceLoader.exists(path), "strip exists: %s" % path)
		var tex: Texture2D = load(path)
		var img: Image = tex.get_image() if tex != null else null
		_check(c, img != null and img.detect_alpha() != Image.ALPHA_NONE,
			"strip is alpha-keyed (not RGB-opaque): %s" % path)

# --- (b) the strip figure renders at standee height, never a sliver -----------------------------
static func _b_strip_scaling_matches_standee(c: Dictionary) -> void:
	print("[b: _play_anim scales the strip FIGURE to standee height; death holds its last frame]")
	var a := Agent.new("readability_anim_probe")
	a.combat_form = "bieber_monster"
	var body := Node2D.new()
	var spr := Sprite2D.new()
	body.add_child(spr)
	var ex := CombatExecutor.new()
	ex.bind(a, body)
	ex._play_anim("hurt")
	var ok_strip: bool = spr.hframes == 8 and spr.texture != null
	_check(c, ok_strip, "hurt strip mounted (hframes=8, texture set)")
	if ok_strip:
		# The FIGURE band: the strip image's used (non-transparent) rect — the same measure the
		# fix keys scale on. With RGB source art this is the full 1024 cell; with keyed art the
		# ~400px monster band. Either way the RENDERED figure must land at standee height.
		var img: Image = spr.texture.get_image()
		var fig_h := float(img.get_used_rect().size.y) if img != null else 0.0
		var rendered_fig_h := fig_h * spr.scale.y
		_check(c, absf(rendered_fig_h - 64.0) <= 2.0,
			"the rendered FIGURE height ~= the 64px standee (got %.1fpx)" % rendered_fig_h)
		var frame_w := float(spr.texture.get_width()) / 8.0 * spr.scale.x
		_check(c, frame_w >= 20.0,
			"the rendered frame is body-wide, not a sliver (got %.1fpx wide)" % frame_w)
	# The death strip HOLDS its final frame (the corpse) at the same corrected scale.
	ex._play_anim("death")
	var death_scale: Vector2 = spr.scale
	for i in 90:   # 1.5s at the executor's fixed dt — well past 8 frames @ 12fps
		ex.step_combat(DT)
	_check(c, spr.frame == 7 and spr.scale == death_scale,
		"the death strip holds frame 7 at the corrected scale (frame=%d)" % spr.frame)
	ex.free()
	body.free()

# --- (g) N6: the four placed attack strips mount true; missing cues degrade to the standee ------
## The N6 asset drop: wren_predator / mack_beast / neil_monster / beyond_hunter each shipped an
## 8-frame attack_side strip (attack ONLY — no hurt/death strips exist for them). Pins, per form:
##   * the strip exists on disk and is ALPHA-KEYED (the grey-sliver audit bug);
##   * _play_anim("attack") mounts it with the FIGURE (used-rect band) at standee height AND the
##     figure's vertical CENTER on the body position (these strips author the figure at the
##     BOTTOM of the gen cell — without the used-rect offset rule the monster teleports ~160px
##     below its standee for every swing);
##   * a cue with NO authored strip ("hurt"/"death") is a SILENT no-op: the standee texture,
##     hframes and scale stay untouched (never a broken mount, never a stolen frame).
const N6_STRIP_FORMS: Array = ["wren_predator", "mack_beast", "neil_monster", "beyond_hunter"]

static func _g_n6_attack_strips_place_and_degrade(c: Dictionary) -> void:
	print("[g: N6 attack strips — four forms mount at standee height/center; hurt/death degrade]")
	for form in N6_STRIP_FORMS:
		var path := "res://assets/anim/%s_attack_side.png" % form
		_check(c, ResourceLoader.exists(path), "strip exists: %s" % path)
		if not ResourceLoader.exists(path):
			continue
		var strip_tex: Texture2D = load(path)
		var strip_img: Image = strip_tex.get_image() if strip_tex != null else null
		_check(c, strip_img != null and strip_img.detect_alpha() != Image.ALPHA_NONE,
			"strip is alpha-keyed (not RGB-opaque): %s" % path)
		# Anti-bisection pin (N6 review): EVERY frame's used-alpha band must be body-wide.
		# The beyond_hunter frame-0 audit bug was a razor-cut 49px half-figure in a 192px
		# cell — one sliver frame in an otherwise-sound sheet, invisible to one-frame probe
		# shots. Rule: no frame may be narrower than HALF the sheet's widest frame.
		if strip_img != null:
			var cell_w: int = strip_img.get_width() / 8
			var min_used_w: int = cell_w + 1
			var max_used_w: int = 0
			var worst_frame: int = -1
			for f in 8:
				var cell: Image = strip_img.get_region(
					Rect2i(f * cell_w, 0, cell_w, strip_img.get_height()))
				var used_w: int = cell.get_used_rect().size.x
				if used_w < min_used_w:
					min_used_w = used_w
					worst_frame = f
				max_used_w = maxi(max_used_w, used_w)
			_check(c, min_used_w * 2 >= max_used_w,
				"%s: every frame body-wide, no bisected sliver (worst frame %d: %dpx vs widest %dpx)"
				% [form, worst_frame, min_used_w, max_used_w])
		# Mount through the REAL binding (bind() skins the standee first — N4).
		var a := Agent.new("n6_strip_probe_%s" % form)
		a.combat_form = String(form)
		var body := Node2D.new()
		var spr := Sprite2D.new()
		body.add_child(spr)
		var ex := CombatExecutor.new()
		ex.bind(a, body)
		var standee_tex: Texture2D = spr.texture
		var standee_scale: Vector2 = spr.scale
		var standee_offset: Vector2 = spr.offset
		_check(c, standee_tex != null and standee_tex.resource_path.ends_with("%s.png" % form),
			"%s: bind() wears the standee painting first" % form)
		ex._play_anim("attack")
		var mounted: bool = spr.hframes == 8 and spr.texture == strip_tex
		_check(c, mounted, "%s: attack strip mounted (hframes=8)" % form)
		if mounted and strip_img != null:
			var used: Rect2i = strip_img.get_used_rect()
			var fig_h := float(used.size.y)
			_check(c, absf(fig_h * spr.scale.y - 64.0) <= 2.0,
				"%s: rendered FIGURE height ~= the 64px standee (got %.1fpx)" % [form, fig_h * spr.scale.y])
			# The offset rule: the figure band's center must land ON the body position.
			var fig_center_y := (float(used.position.y) + fig_h * 0.5 + spr.offset.y) - \
				float(strip_tex.get_height()) * 0.5
			_check(c, absf(fig_center_y * spr.scale.y) <= 3.0,
				"%s: figure CENTER sits on the body position (drift %.1fpx)" % [form, fig_center_y * spr.scale.y])
		# Missing cues (no hurt/death strips shipped): a silent no-op on the standee.
		for cue in ["hurt", "death"]:
			ex._play_anim("attack")   # a strip in flight…
			for i in 90:
				ex.step_combat(1.0 / 60.0)   # …ends; the standee restores
			ex._play_anim(String(cue))
			_check(c, spr.texture == standee_tex and spr.hframes == 1 and spr.scale == standee_scale
				and spr.offset == standee_offset,
				"%s: '%s' has no strip -> the standee stands untouched (offset restored too)" % [form, cue])
		# The LIVE downed-mid-swing seam (probe-caught): a downing blow drops in_combat and the
		# body FREES its executor (NPC._physics_process) — an executor dying with a NON-hold
		# strip still in flight must not freeze the corpse on a mid-swing frame. The standee
		# (the only resting look these death-strip-less forms own) must stand.
		ex._play_anim("attack")
		_check(c, spr.hframes == 8, "%s: strip in flight before the executor dies" % form)
		ex.free()
		_check(c, spr.texture == standee_tex and spr.hframes == 1 and spr.scale == standee_scale
			and spr.offset == standee_offset,
			"%s: executor died mid-swing -> the STANDEE stands (no frozen mid-attack corpse)" % form)
		body.free()
	# The counter-pin: a HOLD strip (death, hold_last) is the felled body's resting look — an
	# executor dying with it mounted must LEAVE it (bieber's corpse keeps its death frame).
	var ba := Agent.new("n6_strip_probe_bieber")
	ba.combat_form = "bieber_monster"
	var bbody := Node2D.new()
	var bspr := Sprite2D.new()
	bbody.add_child(bspr)
	var bex := CombatExecutor.new()
	bex.bind(ba, bbody)
	bex._play_anim("death")
	var death_tex: Texture2D = bspr.texture
	_check(c, bspr.hframes == 8 and death_tex != null
		and death_tex.resource_path.ends_with("bieber_monster_death_down.png"),
		"bieber: the death strip mounted (hold_last)")
	bex.free()
	_check(c, bspr.texture == death_tex and bspr.hframes == 8,
		"bieber: executor died with the HOLD strip mounted -> the corpse keeps its death frame")
	bbody.free()

# --- (c) enemy tells ride the SAME telegraph events the HUD text uses ---------------------------
static func _c_tells_ride_the_telegraph_events(c: Dictionary, root: Node) -> void:
	print("[c: cast_started -> an on-enemy tell (arc/circle); finished/interrupted clears it]")
	var FB: Object = root.get_node_or_null("/root/CombatFeedback")
	var AG: Object = root.get_node("/root/Agents")
	var EB: Object = root.get_node("/root/EventBus")
	EB.clear()
	if not (FB != null and FB.has_method("active_tells")):
		_check(c, false, "CombatFeedback.active_tells API present")
		return
	FB.clear_tells()
	var _caster := _stage(AG, "readability_tell_caster", Vector2(300, 200), "readability_room")
	# A strike windup -> an ARC tell at the caster along the cast dir, sized by the art's range.
	CombatEvents.cast_started("readability_tell_caster", "cleaver_swipe", "player", Vector2.RIGHT, 0.45)
	var tells: Dictionary = FB.active_tells()
	_check(c, tells.has("readability_tell_caster"), "cast_started recorded a tell for the caster")
	var t: Dictionary = tells.get("readability_tell_caster", {})
	_check(c, String(t.get("kind", "")) == "arc", "a strike windup tells as an ARC (got '%s')" % String(t.get("kind", "")))
	_check(c, float(t.get("range", 0.0)) == 70.0, "the arc carries the art's authored range (70)")
	# The strike resolves -> the tell clears.
	CombatEvents.cast_finished("readability_tell_caster", "cleaver_swipe")
	_check(c, not (FB.active_tells() as Dictionary).has("readability_tell_caster"),
		"cast_finished cleared the tell")
	# A projectile windup -> a CIRCLE tell; an interrupt clears it too.
	CombatEvents.cast_started("readability_tell_caster", "hook_throw", "", Vector2.DOWN, 0.5)
	var t2: Dictionary = (FB.active_tells() as Dictionary).get("readability_tell_caster", {})
	_check(c, String(t2.get("kind", "")) == "circle", "a projectile windup tells as a CIRCLE")
	CombatEvents.cast_interrupted("readability_tell_caster", "hook_throw", "stagger")
	_check(c, not (FB.active_tells() as Dictionary).has("readability_tell_caster"),
		"cast_interrupted cleared the tell")
	# The player's own casts never alarm the tell layer (mirrors the HUD text rule).
	CombatEvents.cast_started("player", "revolver_shot", "", Vector2.RIGHT, 0.25)
	_check(c, not (FB.active_tells() as Dictionary).has("player"), "the player's own cast tells NOTHING")
	CombatEvents.cast_finished("player", "revolver_shot")
	# Headless-gated visuals: recording state spawned NO scene nodes under --headless.
	_check(c, root.get_node_or_null("CombatTellLayer") == null,
		"headless: no tell layer node was spawned (visuals are live-only)")
	FB.clear_tells()
	EB.clear()
	AG.rebuild()

# --- (d) hp pips mirror the ONE peer banding, combat-mode only ----------------------------------
static func _d_hp_pips_mirror_peer_banding(c: Dictionary, root: Node) -> void:
	print("[d: NPC hp pips mirror Perception.hp_band (banded, never exact), combat mode only]")
	var AG: Object = root.get_node("/root/Agents")
	var a := _stage(AG, "readability_pips_probe", Vector2(80, 80), "readability_room")
	a.max_hp = 90.0
	a.hp = 90.0
	var npc = load("res://scenes/NPC.tscn").instantiate()
	npc.npc_id = "readability_pips_probe"
	root.add_child(npc)
	await (Engine.get_main_loop() as SceneTree).process_frame
	if not npc.has_method("combat_pips"):
		_check(c, false, "NPC.combat_pips API present")
		npc.queue_free()
		AG.rebuild()
		return
	a.in_combat = true
	_check(c, int(npc.combat_pips()) == 3, "healthy (>2/3) -> 3 pips")
	a.hp = 45.0
	_check(c, int(npc.combat_pips()) == 2, "hurt (>1/3) -> 2 pips")
	a.hp = 20.0
	_check(c, int(npc.combat_pips()) == 1, "critical -> 1 pip")
	_check(c, bool(npc.pips_visible_now()), "pips SHOW while the agent is in combat mode")
	a.downed = true
	_check(c, int(npc.combat_pips()) == 0 and not bool(npc.pips_visible_now()),
		"downed -> 0 pips and hidden (a corpse needs no bar)")
	a.downed = false
	a.in_combat = false
	_check(c, not bool(npc.pips_visible_now()), "pips HIDE outside combat mode")
	# Headless-gated visuals: no pip node was mounted on the body under --headless.
	_check(c, npc.get_node_or_null("HpPips") == null,
		"headless: no pip node was spawned (visuals are live-only)")
	npc.queue_free()
	await (Engine.get_main_loop() as SceneTree).process_frame
	AG.rebuild()

# --- (e) muzzle flash on an ammo-costing art's strike moment ------------------------------------
static func _e_muzzle_flash_on_ammo_cost_cast(c: Dictionary, root: Node) -> void:
	print("[e: an ammo-costing art finishing spawns a muzzle flash at the cached cast dir]")
	var FX: Object = root.get_node_or_null("/root/CombatFx")
	var AG: Object = root.get_node("/root/Agents")
	var EB: Object = root.get_node("/root/EventBus")
	EB.clear()
	if not (FX != null and FX.has_method("last_muzzle")):
		_check(c, false, "CombatFx.last_muzzle API present")
		return
	FX.set_enabled(true)
	FX.clear_transients()
	var gunman := _stage(AG, "readability_muzzle_probe", Vector2(500, 300), "readability_room")
	var before: int = FX.transient_count()
	# The telegraph carries the aim; the STRIKE moment (cast_finished) fires the flash.
	CombatEvents.cast_started("readability_muzzle_probe", "revolver_shot", "", Vector2.RIGHT, 0.25)
	_check(c, FX.transient_count() == before, "the windup alone spawns NO flash (the shot hasn't left)")
	CombatEvents.cast_finished("readability_muzzle_probe", "revolver_shot")
	_check(c, FX.transient_count() == before + 1, "cast_finished spawned ONE muzzle-flash transient")
	var m: Dictionary = FX.last_muzzle()
	_check(c, String(m.get("caster", "")) == "readability_muzzle_probe"
		and String(m.get("ability", "")) == "revolver_shot", "the flash records its caster + art")
	var at_v: Variant = m.get("at", Vector2.ZERO)
	var at: Vector2 = at_v if at_v is Vector2 else Vector2.ZERO
	_check(c, at.x > gunman.position.x and absf(at.y - gunman.position.y) < 1.0,
		"the flash sits AHEAD of the muzzle along the cached aim dir (at %s)" % str(at))
	# A FREE art (no ammo cost) finishing spawns nothing — the flash is data-driven off cost.ammo.
	var before2: int = FX.transient_count()
	CombatEvents.cast_started("readability_muzzle_probe", "cleaver_swipe", "", Vector2.RIGHT, 0.45)
	CombatEvents.cast_finished("readability_muzzle_probe", "cleaver_swipe")
	_check(c, FX.transient_count() == before2, "a free (no-ammo) art finishing spawns NO flash")
	FX.clear_transients()
	EB.clear()
	AG.rebuild()

# --- (f) the combat reticle: active exactly when a combatant shares the player's room -----------
static func _f_reticle_active_in_combat_rooms(c: Dictionary, root: Node) -> void:
	print("[f: reticle_active() true only while a live non-player combatant shares the room]")
	var FB: Object = root.get_node_or_null("/root/CombatFeedback")
	var AG: Object = root.get_node("/root/Agents")
	if not (FB != null and FB.has_method("reticle_active")):
		_check(c, false, "CombatFeedback.reticle_active API present")
		return
	AG.rebuild()
	var _proxy: Agent = AG.ensure_player_proxy(Vector2(100, 100), "readability_ret_room")
	var foe := _stage(AG, "readability_ret_foe", Vector2(200, 100), "readability_ret_room")
	_check(c, not bool(FB.reticle_active()), "no combatant -> reticle inactive")
	foe.in_combat = true
	_check(c, bool(FB.reticle_active()), "a combatant in the player's room -> reticle ACTIVE")
	foe.room = "readability_elsewhere"
	_check(c, not bool(FB.reticle_active()), "the combatant left the room -> reticle inactive")
	foe.room = "readability_ret_room"
	foe.downed = true
	_check(c, not bool(FB.reticle_active()), "a downed combatant does not hold the reticle up")
	# Headless-gated visuals: no reticle node exists under --headless.
	_check(c, root.get_node_or_null("CombatReticleLayer") == null,
		"headless: no reticle layer node was spawned (visuals are live-only)")
	AG.rebuild()

static func _stage(AG: Object, id: String, pos: Vector2, room_id: String) -> Agent:
	var a := Agent.new(id)
	a.display_name = id
	a.room = room_id
	a.position = pos
	AG._agents[id] = a
	return a

static func _check(c: Dictionary, cond: bool, label: String) -> void:
	if cond:
		c["passed"] = int(c["passed"]) + 1
		print("  PASS  %s" % label)
	else:
		c["failed"] = int(c["failed"]) + 1
		printerr("  FAIL  %s" % label)
