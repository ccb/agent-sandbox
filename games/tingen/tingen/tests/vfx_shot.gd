extends SceneTree
## Headless VISUAL PROOF harness (combat plan §M1) — the gameplay-test artifact that PROVES the
## FX wiring makes a fight legible. Run it directly (NOT part of the main suite):
##   godot --headless --path tingen -s tests/vfx_shot.gd
##
## It stages a real slice of a fight — a revolver_shot projectile IN FLIGHT, a paper_charm zone
## on the ground, and the transform's spark burst — using the actual CombatProjectile/CombatZone
## scenes and the CombatFx spawner, steps a few combat frames, then saves a screenshot to
##   asset-gen/out_vfx/vfx_proof.png
##
## WHY CPU compositing (not a GPU screengrab): under --headless Godot loads the "dummy" rendering
## driver, so a viewport texture grab comes back blank. To produce a real, non-empty proof PNG on
## any machine we composite the SAME textures the live scenes carry — read straight off the staged
## Sprite2D nodes at their staged transforms — onto an Image with blend_rect. The image therefore
## mirrors exactly what the running scene would draw: the tracer where the round is, the glyph over
## the zone, the burst on the transformed body.

const DT: float = 1.0 / 60.0
const OUT_DIR: String = "res://../asset-gen/out_vfx"          # sibling of tingen/
const OUT_ABS: String = "/Users/markma/Desktop/Internship/Purm 2026/Tingen-Game/asset-gen/out_vfx/vfx_proof.png"
const CANVAS_W: int = 900
const CANVAS_H: int = 420
## World→canvas offset so the staged fight (origin-centred) lands nicely in frame.
const ORIGIN := Vector2(120, 210)

func _init() -> void:
	await process_frame
	await process_frame

	var AG: Object = root.get_node("/root/Agents")
	var EB: Object = root.get_node("/root/EventBus")
	var FX: Object = root.get_node("/root/CombatFx")
	AG.rebuild()
	EB.clear()
	FX.set_enabled(true)
	FX.clear_transients()

	# --- stage a fight slice in one room ---
	var shooter := _stage("vfx_shooter", "vfx_room", Vector2(0, 0))
	var mark := _stage("vfx_mark", "vfx_room", Vector2(520, 0))
	var caster := _stage("vfx_caster", "vfx_room", Vector2(120, 120))
	var morph := _stage("vfx_morph", "vfx_room", Vector2(360, -40))
	morph.combat_form = "butcher_human"

	var sx := CombatExecutor.new()
	sx.bind(shooter)
	var cx := CombatExecutor.new()
	cx.bind(caster)
	var mox := CombatExecutor.new()
	mox.bind(morph)

	# paper_charm: plant the glyph zone on the ground (its zone persists 4s — stays in frame).
	cx.try_cast("paper_charm", "vfx_caster")   # self-centred point cast for a clean placement
	_step([cx, mox], 0.7)                       # windup resolves, zone lands

	# the transform: fire the burst FX at the morphing body (cosmetic listener).
	mox.try_cast("assume_form", "")
	_step([cx, mox], 1.3)

	# revolver_shot LAST so the tracer is still IN FLIGHT at compose time: telegraph -> spawn ->
	# fly ~1/3 of the way to the mark (245px of the 520px gap), mid-frame and legible.
	sx.try_cast("revolver_shot", "vfx_mark")
	_step([sx], 0.25)   # windup resolves, round spawns
	_step([sx], 0.35)   # round travels into open frame (well short of the mark — still alive)
	# Advance the transform burst to a PEAK flipbook frame (~0.3s at 24fps -> frame ~7, the brightest
	# of the keyed spark_burst) while it is still well within its 0.7s lifetime, so the proof shows a
	# legible burst — the M10 fix — rather than the dim opening frame or an opaque boxy panel.
	FX.step_fx(0.30)

	# --- gather what the running scene would draw and composite it ---
	var img := Image.create(CANVAS_W, CANVAS_H, false, Image.FORMAT_RGBA8)
	img.fill(Color(0.06, 0.05, 0.08, 1.0))   # a dim arena backdrop

	var drawn := 0
	drawn += _blit_sprites_under(sx, img)          # the projectile's tracer
	drawn += _blit_sprites_under(cx, img)          # the charm glyph zone
	drawn += _blit_fx_layer(img)                   # the transient bursts/sparks

	# Mark the agents so the frame reads as a fight (small dots).
	for a in [shooter, mark, caster, morph]:
		_dot(img, _to_canvas(a.position), Color(0.9, 0.85, 0.4, 1.0))

	_ensure_out_dir()
	var err := img.save_png(OUT_ABS)
	print("[vfx_shot] composited %d fx sprites; projectiles=%d zones=%d fx_transients=%d"
		% [drawn, sx.projectiles.size(), cx.zones.size(), FX.transient_count()])
	print("[vfx_shot] save_png -> %s  (err=%d)" % [OUT_ABS, err])

	sx.free()
	cx.free()
	mox.free()
	AG.rebuild()
	quit(0 if err == OK else 1)

## Composite every Sprite2D under an executor's spawned projectiles/zones onto the image.
func _blit_sprites_under(ex: CombatExecutor, img: Image) -> int:
	var n := 0
	for p in ex.projectiles:
		n += _blit_node_sprites(p, img)
	for z in ex.zones:
		n += _blit_node_sprites(z, img)
	return n

func _blit_fx_layer(img: Image) -> int:
	var layer := root.get_node_or_null("CombatFxLayer")
	if layer == null:
		return 0
	var n := 0
	for c in layer.get_children():
		if c is Sprite2D:
			_blit_sprite(c as Sprite2D, img)
			n += 1
		elif c is AnimatedSprite2D:
			# M10: the transform burst is now an ANIMATED, alpha-keyed flipbook (not the raw sheet
			# drawn whole). Composite its CURRENT frame so the proof shows the burst, not a boxy panel.
			_blit_animated(c as AnimatedSprite2D, img)
			n += 1
	return n

## Composite an AnimatedSprite2D's current frame (an AtlasTexture region off the keyed sheet) at its
## staged position + scale. The keyed sheet carries real alpha, so the burst reads as a burst.
func _blit_animated(a: AnimatedSprite2D, img: Image) -> void:
	var frames := a.sprite_frames
	if frames == null:
		return
	var tex := frames.get_frame_texture("default", a.frame)
	if tex == null:
		return
	var src := tex.get_image()
	if src == null:
		return
	src.convert(Image.FORMAT_RGBA8)
	var sc: Vector2 = a.scale
	var tw := maxi(1, int(round(float(src.get_width()) * absf(sc.x))))
	var th := maxi(1, int(round(float(src.get_height()) * absf(sc.y))))
	src.resize(tw, th, Image.INTERPOLATE_BILINEAR)
	var center := _to_canvas(a.position)
	var top_left := Vector2i(int(center.x) - tw / 2, int(center.y) - th / 2)
	img.blend_rect(src, Rect2i(0, 0, tw, th), top_left)

func _blit_node_sprites(host: Node, img: Image) -> int:
	var n := 0
	for c in host.get_children():
		if c is Sprite2D:
			_blit_sprite(c as Sprite2D, img)
			n += 1
	return n

## Blit one Sprite2D's texture at its staged world position, honoring its scale (rotation is
## approximated as axis-aligned — enough to prove the asset is placed and legible in-frame).
func _blit_sprite(s: Sprite2D, img: Image) -> void:
	var tex: Texture2D = s.texture
	if tex == null:
		return
	var src := tex.get_image()
	if src == null:
		return
	src.convert(Image.FORMAT_RGBA8)
	var sc: Vector2 = s.scale
	var tw := maxi(1, int(round(float(src.get_width()) * absf(sc.x))))
	var th := maxi(1, int(round(float(src.get_height()) * absf(sc.y))))
	src.resize(tw, th, Image.INTERPOLATE_BILINEAR)
	var host_pos: Vector2 = (s.get_parent() as Node2D).position if s.get_parent() is Node2D else Vector2.ZERO
	var center := _to_canvas(host_pos + s.position)
	var top_left := Vector2i(int(center.x) - tw / 2, int(center.y) - th / 2)
	img.blend_rect(src, Rect2i(0, 0, tw, th), top_left)

func _dot(img: Image, at: Vector2, col: Color) -> void:
	var r := 4
	for dy in range(-r, r + 1):
		for dx in range(-r, r + 1):
			if dx * dx + dy * dy > r * r:
				continue
			var x := int(at.x) + dx
			var y := int(at.y) + dy
			if x >= 0 and x < CANVAS_W and y >= 0 and y < CANVAS_H:
				img.set_pixel(x, y, col)

func _to_canvas(world: Vector2) -> Vector2:
	return ORIGIN + world * 1.4

func _ensure_out_dir() -> void:
	var abs_dir := "/Users/markma/Desktop/Internship/Purm 2026/Tingen-Game/asset-gen/out_vfx"
	DirAccess.make_dir_recursive_absolute(abs_dir)

func _stage(id: String, room_id: String, pos: Vector2) -> Agent:
	var a := Agent.new(id)
	a.display_name = id
	a.room = room_id
	a.position = pos
	a.in_combat = true
	root.get_node("/root/Agents")._agents[id] = a
	return a

func _step(executors: Array, seconds: float) -> void:
	var steps := int(round(seconds * 60.0))
	for i in steps:
		for ex in executors:
			ex.step_combat(DT)
