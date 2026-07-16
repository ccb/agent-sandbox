extends SceneTree
## Screenshot probe — captures REAL rendered frames so a human (or the main-loop
## agent) can eyeball what the game actually looks like. Run WINDOWED (no --headless):
##   GODOT --path tingen -s tests/screenshot_probe.gd [-- outdir=/abs/path]
## Captures: 01_title.png, 02_lodging.png (after New Run, AFTER the IntroCard cinematic
## has dissolved — so the rig + HUD are actually visible), 03_after_move.png,
## 04_bed_prompt.png (the lodging bed's "Rest until morning" prompt).
## P3 combat-readability beats (the §0 butcher fight staged in the lodging via the REAL
## seams — RoomView body spawn, damage→combat-mode flip, tactics executor, hp_below reflex):
## 05_combat_before.png (the butcher body standing near the player), 06_muzzle_flash.png
## (2 frames after the player's revolver cast_finished), 07_enemy_tell.png (mid-windup of
## the enemy's first cast — on-body pulse + ground indicator + HUD text), 08_maskdrop.png
## (right after `transformed` — the bieber_monster reveal), 09_attack_anim.png (mid-flight
## of the monster's attack strip), 10_death_hold.png (the held death-strip corpse frame).
## P4 staged-opener/fork/polish beats: 11_opener_door_bark.png (Constable Brom's body AT the
## lodging door with his spoken bark bubble up — the opener staged in the world),
## 12_harvest_fork_panel.png (the digest/sell/keep 3-choice panel at the first characteristic
## pickup), 13_fork_plan_marked.png (the chosen plan marked on the HUD lead line),
## 14_legend_keys.png (the [H] legend now folding in the panel keys — the always-on hotkey
## cheat-line is gone), 15_polished_digest_prompt.png (the reworded lodging digest prompt).
## P5 city place-ness beats (Clock-forced day AND night): 16_city_day.png (the painted city
## under the afternoon tint), 17_city_crowd_day.png (the market ambient crowd cluster),
## 18_city_night.png (the cold blue-grey night tint), 19_lamp_glow_night.png (a warm lamp
## glow up close at night), 20_map_lead_pin.png (the district map with the current-lead pin).
## N2 death beats (a checkpointed death costs the day, not the run): 21_death_screen.png (the
## Continue-style "Cut Down in the Dark" wake screen after a REAL lethal hit downs the player
## with a nightly checkpoint standing), 22_death_wake_lodging.png (after pressing the REAL
## Continue — the player woken back at the lodging on the checkpoint day).
## N5 DEATH-PATHWAY beats (the third playable build, driven through the REAL meta + picker seams):
## 23_second_win_payoff.png (the second win's ending screen — the payoff that unlocks Death),
## 24_death_picker.png (the New-Run pathway picker offering hunter+hermit+death),
## 25_death_run_lodging.png (a live Death run in the lodging — censer primary + the Spirit bar),
## 26_auber_human_tell.png (sister_auber's HUMAN phase winding up under fire — tell + pips),
## 27_auber_monster_reveal.png (the auber_descend mask-drop — the placed auber_monster.png art),
## 28_auber_monster_attack.png (the grave-power monster mid-attack),
## 29_cassian_human_tell.png / 30_cassian_monster_reveal.png / 31_cassian_monster_attack.png
## (the same three beats for brother_cassian -> cassian_monster.png).
## M_cast v2 CAST-ROULETTE beats (user correction: the panel is a FULL design-reference dossier —
## CastCodex.SHOW_ALL ships true, everything renders, the card body scrolls). Via the REAL title
## button on a FRESH meta: 32_cast_mundane_dossier.png (a mundane NPC's complete civilian card —
## voice/goals/knowledge/schedule/records), 33_cast_beyonder_dossier.png (a Beyonder's card
## revealed WITHOUT any codex — goals + secrets + pathway), 34_cast_dossier_scrolled.png (the
## same card scrolled deep into the numbers-bearing form kits), 35_cast_monster_flip.png (the
## beneath-the-mask flip, no codex needed), 36_cast_spin.png (a mid-spin shuffle frame).
## N3 CONTINUE-RESUME beats (Continue is a first-class resume — B-F1/B-F2/B-F5; the true
## two-process case is tests/continue_probe.sh): 37_title_continue_enabled.png (the title with
## Continue ENABLED — a nightly save waiting), 38_continue_resumed_lodging.png (the resumed
## lodging: run live again, day 2, HUD up), 39_continue_ritual_night_armed.png (Doom 100 on the
## RESUMED run arms and stages the Ritual Night climax).
## N4 THREATS-SEEN beats (threats render their real paintings at body-bind, arrive on-screen the
## frame they spawn, and are ANNOUNCED): 40_crypt_roster_on_entry.png (the armed climax's crypt
## roster standing there the MOMENT the player walks in — the room_changed reconcile),
## 41_avatar_half_landed.png (the fuse-threshold avatar wearing its translucent painting from
## frame one), 42_avatar_true_form.png (the REAL two-stage descent: the hp_below reflex casts
## avatar_ascend -> the placed descended_avatar_true painting swaps in), 43_threat_dispatch_
## nighthawk.png (Heat 100 on a fresh run: the pursuer IN FRAME wearing the aliased nighthawk
## standee the instant it spawns, dispatch toast up), 44_threat_resolved_toast.png (downing it —
## "The hunt has lost you" through the same channel).
## Also prints assert-style visibility facts ([probe][assert] ...) and the live Clock
## pace so pacing regressions are observable in a real run.
## NOT registered in run_tests.gd — this is a verification tool, not a test.

var out_dir := "user://probe_shots"

func _init() -> void:
	var args := OS.get_cmdline_user_args()
	for a in args:
		if a.begins_with("outdir="):
			out_dir = a.substr(7)
	_run()

func _shot(name_: String) -> void:
	await RenderingServer.frame_post_draw
	var img := root.get_viewport().get_texture().get_image()
	var dir := DirAccess.open(out_dir.get_base_dir() if out_dir.begins_with("/") else "user://")
	if out_dir.begins_with("/"):
		DirAccess.make_dir_recursive_absolute(out_dir)
	img.save_png(out_dir.path_join(name_))
	print("[probe] shot -> %s/%s (%dx%d)" % [out_dir, name_, img.get_width(), img.get_height()])

func _wait(frames: int) -> void:
	for i in frames:
		await process_frame

## The lodging entry plays the IntroCard establishing-shot cinematic (a CanvasLayer at
## layer 200, ~4s light-up/hold/dissolve) OVER the whole screen — world AND HUD. Any
## lodging shot taken while it is up shows ONLY the cinematic art. Wait (bounded) until
## the card frees itself, then settle a few frames.
func _wait_intro_card_gone(main: Node, max_frames: int = 900) -> void:
	var waited := 0
	while waited < max_frames:
		var card: Node = main.find_child("IntroCard", true, false)
		if card == null or not is_instance_valid(card):
			break
		await process_frame
		waited += 1
	print("[probe] intro card gone after %d frames" % waited)
	await _wait(10)

## Print the LIVE Clock pace (finding b: the run-length budget must be observable in a
## real run, not assumed from defaults).
func _print_pace() -> void:
	var cl: Node = root.get_node_or_null("/root/Clock")
	if cl == null:
		print("[probe][assert] FAIL Clock autoload missing")
		return
	print("[probe] clock pace: real_seconds_per_game_minute=%.3f minutes_per_beat=%d day=%d %s (%s)"
		% [cl.real_seconds_per_game_minute, cl.minutes_per_beat, cl.day, cl.hhmm(), cl.phase])

func _assert(cond: bool, label: String) -> void:
	print("[probe][assert] %s %s" % ["PASS" if cond else "FAIL", label])

## Assert-style visibility facts for the lodging beat: player rig present, on-screen,
## drawn ABOVE the painted room background; HUD mounted on the persistent UI layer.
func _print_visibility(main: Node) -> void:
	var players := get_nodes_in_group("player")
	_assert(players.size() > 0, "player rig node present (group 'player')")
	if players.size() > 0:
		var p: Node2D = players[0]
		_assert(p.visible, "player rig node visible flag")
		var screen_pos: Vector2 = p.get_global_transform_with_canvas().origin
		var vp_rect := Rect2(Vector2.ZERO, root.get_viewport().get_visible_rect().size)
		_assert(vp_rect.has_point(screen_pos),
			"player rig on-screen (canvas pos %s in viewport %s)" % [screen_pos, vp_rect.size])
		var photo: Node = main.find_child("RoomPhoto", true, false)
		if photo != null and photo is CanvasItem:
			var above: bool = p.z_index >= (photo as CanvasItem).z_index \
				and photo.get_parent() == p.get_parent() \
				and photo.get_index() < p.get_index()
			_assert(above, "player rig z-sorted ABOVE the painted room background")
		var sprite: Node = p.get_node_or_null("Sprite")
		_assert(sprite != null and (sprite as CanvasItem).visible, "player rig sprite visible")
	var ui: Node = main.get_node_or_null("UI")
	var hud: Node = ui.get_node_or_null("HUD") if ui != null else null
	_assert(hud != null, "HUD mounted on the persistent UI layer")
	if hud != null:
		var top: Node = hud.get_node_or_null("Top")
		_assert(top != null and (top as CanvasItem).visible and (hud as CanvasItem).visible,
			"HUD top bar visible")

func _run() -> void:
	await process_frame
	# N1 (sprint safety): sandbox EVERY persistent path (meta/save/settings/hints/playlog) into
	# user://test_sandbox/<run>/ so a probe run can never stomp the real player profile.
	preload("res://src/TestSandbox.gd").activate(root)
	# Mount the real entry scene (what a player double-clicking sees).
	var main: Node = (load("res://scenes/Main.tscn") as PackedScene).instantiate()
	root.add_child(main)
	await _wait(30)
	await _shot("01_title.png")

	# M_cast: THE CAST roulette lives on the title — capture its three beats before any run starts.
	await _cast_panel_beats(main)

	# New Run through the REAL flow (BootController), driving the picker if it appears.
	if main.has_method("start_new_run"):
		main.start_new_run()
		await _wait(10)
		if main.has_method("pathway_picker_active") and main.pathway_picker_active():
			main.choose_pathway("hunter")
		# Wait out the IntroCard cinematic — the 02 shot must show the REAL room + rig + HUD.
		await _wait_intro_card_gone(main)
		_print_pace()
		_print_visibility(main)
		await _shot("02_lodging.png")

		# P4: the staged opener — Brom hammers on the lodging door (knock + bark bubble).
		await _door_beat_shot()

		# Nudge the player so we see the rig + room from a second angle.
		var players := get_nodes_in_group("player")
		if players.size() > 0:
			var p: Node2D = players[0]
			p.position += Vector2(120, 40)
			await _wait(20)
			await _shot("03_after_move.png")

			# Finding (c): walk the rig onto the bed's RestSpot so its prompt shows.
			var rest: Node = main.find_child("RestSpot", true, false)
			if rest != null:
				p.global_position = (rest as Node2D).global_position + Vector2(0, 24)
				await _wait(30)   # physics overlap -> prompt visible
				var prompt: Node = rest.get_node_or_null("Prompt")
				_assert(prompt != null and (prompt as CanvasItem).visible,
					"bed RestSpot prompt visible while the player stands at the bed")
				await _shot("04_bed_prompt.png")
			else:
				print("[probe] no RestSpot in the lodging — skipping bed-prompt beat")
	else:
		print("[probe] no start_new_run on main — captured title only")

	# P4: end the door beat through the REAL verb before staging the fight, so the constable's
	# body is out of the line of fire (and the release seam is proven live: his body despawns).
	var gm_rel: Node = root.get_node_or_null("/root/GMOpening")
	if gm_rel != null and gm_rel.has_method("release_source") and bool(gm_rel.source_staged()):
		gm_rel.release_source()
		var rv_rel: Node = root.get_node_or_null("/root/RoomView")
		if rv_rel != null:
			rv_rel.reconcile()
		await _wait(5)
		_assert(_npc_body(String(gm_rel.OPENING.get("source_npc", ""))) == null,
			"released: the constable moved on (his body left the lodging)")

	await _combat_beats()
	await _fork_and_polish_beats(main)
	await _city_place_beats(main)
	await _death_beats(main)
	await _death_pathway_beats(main)
	await _continue_beats(main)
	await _n4_beats(main)
	await _n6_anim_beats(main)
	await _n6_room_art_beats(main)

	print("[probe] done")
	quit(0)

## ---- N6 attack-strip beats ---------------------------------------------------------------------
## THE FOUR PLACED ATTACK STRIPS (asset polish N6), seen MID-FLIGHT in-scene. Rides the fresh run
## _n4_beats leaves standing. Per form (wren_predator / mack_beast / neil_monster / beyond_hunter):
## a body in the player's room — the beyond hunter arrives through the REAL Notice-threshold
## dispatch; the three prey shapes are probe-staged agents (positions/ids only) — is flipped into
## combat through the real damage path, winds up an attack through the real intent layer, and the
## shot lands ~12 frames into the strip (hframes=8, the form's own _attack_side sheet, the FIGURE
## at standee height on the body position). The felling blow then pins the graceful degrade LIVE:
## no hurt/death strips ship for these forms, so the standee stands.
##   45_wren_predator_attack.png   46_mack_beast_attack.png
##   47_neil_monster_attack.png    48_beyond_hunter_attack.png
func _n6_anim_beats(_main: Node) -> void:
	print("[probe] === N6 attack-strip beats ===")
	var reg: Node = root.get_node_or_null("/root/Agents")
	var rv: Node = root.get_node_or_null("/root/RoomView")
	var RM: Node = root.get_node_or_null("/root/RunManager")
	var players := get_nodes_in_group("player")
	if reg == null or rv == null or RM == null or not bool(RM.run_active()) or players.is_empty():
		print("[probe] N6 anim beats skipped (no live run/player rig)")
		return
	var proxy: Agent = reg.get_agent("player")
	if proxy == null:
		print("[probe] N6 anim beats skipped (no player proxy)")
		return
	proxy.max_hp = 4000.0
	proxy.hp = 4000.0
	var shots := [["wren_predator", "45_wren_predator_attack.png"],
		["mack_beast", "46_mack_beast_attack.png"],
		["neil_monster", "47_neil_monster_attack.png"],
		["beyond_hunter", "48_beyond_hunter_attack.png"]]
	var k := 0
	for row in shots:
		await _n6_one_attack(String(row[0]), String(row[1]), reg, rv, proxy, k)
		k += 1
	print("[probe] N6 anim beats done")

func _n6_one_attack(form: String, shot: String, reg: Node, rv: Node, proxy: Agent, k: int) -> void:
	var a: Agent = null
	if form == "beyond_hunter":
		# The REAL dispatch seam: Notice at its threshold sends the hunter itself (in_combat,
		# engage->player, named off its form's data row — the B2 label in frame).
		var M: Node = root.get_node("/root/Meters")
		var MT: Node = root.get_node("/root/MeterThreats")
		M.set_meter("notice", 100.0)
		await _wait(2)
		var tid := String(MT.active_threat_id("notice"))
		_assert(tid != "", "N6: high Notice dispatched the beyond hunter (real threshold ear)")
		if tid == "":
			return
		a = reg.get_agent(tid)
		_assert(a != null and String(a.display_name) == "Beyond-touched hunter",
			"N6: the hunter is NAMED from its form's data row (got '%s')" % (String(a.display_name) if a != null else ""))
	else:
		# Probe staging: the prey monster shapes are normally REACHED mid-fight (wren/mack/neil
		# shed into them via their hp_below reflexes — the bieber seam, probed at 08/09); here a
		# staged agent wears each so the placed strip is seen without three full descents.
		a = Agent.new("n6_anim_%s" % form)
		a.display_name = String(form).capitalize()
		a.combat_form = form
		reg.register_agent(a)
	a.room = proxy.room
	a.position = proxy.position + Vector2(170, -20)
	rv.reconcile()
	await _wait(4)
	var body := _npc_body(a.id)
	_assert(body != null, "N6: %s body stands in the player's room (RoomView)" % form)
	if body == null:
		return
	var spr: Sprite2D = body.get_node_or_null("Sprite2D")
	if spr == null:
		_assert(false, "N6: %s body carries a Sprite2D" % form)
		return
	# The REAL-seam hunter is dispatched in_combat and may ALREADY be mid-swing by this frame —
	# only the probe-staged (idle) bodies pin the standee-first look here; the hunter's
	# standee-at-bind fact is unit-pinned in test_combat_readability (g).
	if form != "beyond_hunter":
		_assert(spr.texture != null
			and String(spr.texture.resource_path).ends_with("enemies/%s.png" % form),
			"N6: %s wears its own standee before the swing" % form)
	# The damage->combat flip arms the body's tactics executor (the real play seam); the SECOND
	# tap lands on that now-live executor and stamps the default posture's target, exactly like
	# sustained fire in real play (the _combat_beats shape) — the agent presses the attack itself.
	CombatExecutor.route_hit(proxy, a,
		{"id": "probe_n6_tap", "effects": [{"kind": "damage", "amount": 1.0}]}, Vector2.RIGHT)
	await _wait(3)
	CombatExecutor.route_hit(proxy, a,
		{"id": "probe_n6_tap2", "effects": [{"kind": "damage", "amount": 1.0}]}, Vector2.RIGHT)
	var adb: Node = root.get_node_or_null("/root/AbilityDB")
	var got_attack := false
	for tries in 4:
		var ev := await _wait_event("ability_cast_started", "caster", a.id, 900)
		if ev.is_empty():
			break
		var aid := String((ev.get("data", {}) as Dictionary).get("ability", ""))
		var anim := String((adb.ability_for(aid) as Dictionary).get("anim", "")) if adb != null else ""
		if anim == "attack":
			got_attack = true
			break
	_assert(got_attack, "N6: %s wound up an attack-anim ability (in_combat=%s)" % [form, str(a.in_combat)])
	await _wait(12)
	_assert(spr.hframes == 8 and spr.texture != null
		and String(spr.texture.resource_path).ends_with("anim/%s_attack_side.png" % form),
		"N6: %s attack strip MOUNTED mid-flight (hframes=%d)" % [form, spr.hframes])
	await _aim_mouse_at(body)
	await _shot(shot)
	# The felling blow pins the graceful degrade LIVE: no death strip ships for these forms, so
	# after any in-flight strip finishes (it still advances on a felled body) the STANDEE stands.
	CombatExecutor.route_hit(proxy, a,
		{"id": "probe_n6_finisher", "effects": [{"kind": "damage", "amount": 99999.0}]}, Vector2.RIGHT)
	_assert(a.downed, "N6: %s went down (real damage path)" % form)
	for i in 150:   # any in-flight attack strip still advances on the felled body, then restores
		if spr.hframes == 1:
			break
		await process_frame
	_assert(spr.hframes == 1 and spr.texture != null
		and String(spr.texture.resource_path).ends_with("enemies/%s.png" % form),
		"N6: no death strip for %s -> the STANDEE stands (graceful degrade)" % form)
	# Clear the stage for the next form's shot (probe staging; the corpse persists in data).
	a.position += Vector2(-260.0 + 90.0 * float(k), 620.0)
	body.global_position = a.position

## Drain any queued harvest-fork panels (downing the N6 prey shapes drops characteristics; a
## walk-over gather queues the 3-choice fork, and queued forks re-present as each closes) —
## 'keep' is the neutral, meter-silent choice. The room-art shots must show the ROOM, not a modal.
func _n6_drain_fork_panels(main: Node) -> void:
	for i in 8:
		var panel: Node = main.find_child("HarvestForkPanel", true, false)
		if panel == null or not bool(panel.is_open()):
			return
		panel.choose("keep")
		await _wait(8)

## ---- N6 room-art beats ---------------------------------------------------------------------------
## The two audit scene-ref fixes, seen in-scene: Old Neil wears old_neil.png at his piano (the
## scene shipped pointing at the archive clerk's painting) and Finch wears ledger_finch.png in
## the archive. 49_neil_home_art.png / 50_university_archive_art.png.
func _n6_room_art_beats(main: Node) -> void:
	print("[probe] === N6 room-art beats ===")
	var WS: Node = root.get_node_or_null("/root/WorldState")
	if WS == null:
		print("[probe] N6 room-art beats skipped (no WorldState)")
		return
	for row in [["res://scenes/NeilHome.tscn", "OldNeil", "49_neil_home_art.png"],
			["res://scenes/UniversityArchive.tscn", "Finch", "50_university_archive_art.png"]]:
		WS.transition_requested.emit(String(row[0]), "")
		await _wait(10)
		await _n6_drain_fork_panels(main)
		var npc: Node = main.find_child(String(row[1]), true, false)
		_assert(npc != null, "N6: %s stands in the scene" % String(row[1]))
		var players := get_nodes_in_group("player")
		if npc != null and not players.is_empty():
			(players[0] as Node2D).global_position = (npc as Node2D).global_position + Vector2(-90, 40)
			await _wait(15)
		await _n6_drain_fork_panels(main)
		await _shot(String(row[2]))
	print("[probe] N6 room-art beats done")

## ---- N4 threats-seen beats -------------------------------------------------------------------
## THREATS SEEN AND ANNOUNCED, eyeballed through the REAL seams. Rides the state _continue_beats
## leaves standing (a live resumed run with the Ritual Night climax ACTIVE and staged):
##   40 — walk into the crypt through the real transition; the staged roster (celebrant +
##        door defenders) is BOUND within ~3 frames of entry (the N4 room_changed reconcile).
##   41 — tick the fuse to its threshold: the avatar HALF-LANDS and its body appears within ~2
##        frames wearing the translucent descended_avatar painting (art at body-bind).
##   42 — the REAL second stage: damage flips it into combat, its authored hp_below(0.35) reflex
##        casts avatar_ascend, and the placed descended_avatar_true painting swaps in.
##   43 — a FRESH run, Heat driven to 100: the real threshold ear dispatches a nighthawk pursuer
##        into the player's room; its body is IN FRAME the instant it spawns, wearing the DATA-
##        aliased nighthawk standee, with the dispatch toast up ("The Nighthawks have your scent").
##   44 — downing the pursuer through the real damage path: threat_resolved + the resolve toast.
## Positions (only) are probe staging so every body sits in frame; every SPAWN/SWAP/ANNOUNCE beat
## runs through the shipped seams. Defensive skips keep the probe usable on older trees.
func _n4_beats(main: Node) -> void:
	print("[probe] === N4 threats-seen beats ===")
	var reg: Node = root.get_node_or_null("/root/Agents")
	var RN: Node = root.get_node_or_null("/root/RitualNight")
	var EB: Node = root.get_node_or_null("/root/EventBus")
	var RM: Node = root.get_node_or_null("/root/RunManager")
	if reg == null or RN == null or EB == null or RM == null:
		print("[probe] N4 beats skipped (missing autoloads)")
		return
	if not bool(RN.active()):
		print("[probe] N4 beats skipped (ritual night not active after the continue beats)")
		return
	# (40) crypt roster on entry.
	_assert(String(RN.site_room()) == "cathedral_crypt", "N4: the climax staged at the authored crypt")
	root.get_node("/root/WorldState").transition_requested.emit("res://scenes/CathedralCrypt.tscn", "")
	await _wait(3)
	var cele_id := String(RN.celebrant_id())
	_assert(_npc_body(cele_id) != null,
		"N4: the celebrant's body stands in the crypt within ~3 frames of entry")
	var all_defenders := true
	for i in range(int(RN.defender_count())):
		if _npc_body("ritual_defender_%d" % i) == null:
			all_defenders = false
	_assert(all_defenders,
		"N4: all %d door defenders stand in the crypt on entry" % int(RN.defender_count()))
	var players := get_nodes_in_group("player")
	if players.is_empty():
		print("[probe] N4 beats skipped (no player rig after crypt entry)")
		return
	var p: Node2D = players[0]
	var roster: Array = [cele_id]
	for i in range(int(RN.defender_count())):
		roster.append("ritual_defender_%d" % i)
	var k := 0
	for id in roster:
		var a: Agent = reg.get_agent(String(id))
		var b := _npc_body(String(id))
		if a == null or b == null:
			continue
		a.position = p.global_position + Vector2(110.0 + 70.0 * float(k % 3), -50.0 + 70.0 * float(k / 3))
		b.global_position = a.position
		k += 1
	await _wait(5)
	await _shot("40_crypt_roster_on_entry.png")
	# (41) the avatar half-lands at the fuse threshold — seen the moment it lands.
	if not bool(RN.avatar_present()):
		RN.tick_fuse(maxi(0, int(RN.fuse_remaining()) - int(RN.avatar_threshold())))
	_assert(bool(RN.avatar_present()), "N4: the avatar half-landed at the fuse threshold")
	if not bool(RN.avatar_present()) or bool(RN.resolved()):
		print("[probe] N4 avatar beats skipped (no half-landed avatar)")
		return
	var av_id := String(RN.avatar_id())
	await _wait(2)
	var av_body := _npc_body(av_id)
	_assert(av_body != null, "N4: the half-landed avatar's body appeared within ~2 frames")
	if av_body == null:
		return
	var av: Agent = reg.get_agent(av_id)
	av.position = p.global_position + Vector2(-150, -30)
	av_body.global_position = av.position
	RN._fuse = 12   # probe staging: hold the descent clock so LOSE can't fire mid-shot
	var spr: Sprite2D = av_body.get_node_or_null("Sprite2D")
	_assert(spr != null and spr.texture != null
		and String(spr.texture.resource_path).ends_with("enemies/descended_avatar.png"),
		"N4: the half-landed avatar wears the translucent descended_avatar painting from frame one")
	await _aim_mouse_at(av_body)
	await _wait(3)
	await _shot("41_avatar_half_landed.png")
	# (42) the true-form swap through the REAL hp_below reflex -> avatar_ascend.
	var proxy: Agent = reg.get_agent("player")
	proxy.max_hp = 4000.0
	proxy.hp = 4000.0
	CombatExecutor.route_hit(proxy, av,
		{"id": "probe_avatar_tap", "effects": [{"kind": "damage", "amount": 1.0}]}, Vector2.RIGHT)
	await _wait(3)   # the damage->combat flip binds the tactics executor on the body
	av.hp = minf(av.hp, av.max_hp * 0.30)
	var tf := await _wait_event("transformed", "agent", av_id, 900)
	_assert(not tf.is_empty(), "N4: the avatar ascended (hp_below reflex -> avatar_ascend)")
	_assert(String(av.combat_form) == "descended_avatar_true",
		"N4: the fully-descended form is worn (combat_form=%s)" % av.combat_form)
	await _wait(3)
	spr = av_body.get_node_or_null("Sprite2D")
	_assert(spr != null and spr.texture != null
		and String(spr.texture.resource_path).ends_with("enemies/descended_avatar_true.png"),
		"N4: the placed descended_avatar_true painting swapped in")
	await _aim_mouse_at(av_body)
	await _wait(2)
	await _shot("42_avatar_true_form.png")
	# (43) a FRESH run: Heat 100 dispatches the nighthawk — in frame, aliased art, announced.
	var EG: Node = root.get_node_or_null("/root/EndGame")
	if EG != null and EG.has_method("dismiss"):
		EG.dismiss()
	if bool(RM.run_active()):
		RM.end_run("lose")
	main.return_to_title()
	await _wait(5)
	main.start_new_run()
	await _wait(10)
	if main.has_method("pathway_picker_active") and main.pathway_picker_active():
		main.choose_pathway("hunter")
	await _wait_intro_card_gone(main)
	var proxy2: Agent = reg.get_agent("player")
	if proxy2 != null:
		proxy2.max_hp = 4000.0
		proxy2.hp = 4000.0
	var M: Node = root.get_node("/root/Meters")
	var MT: Node = root.get_node("/root/MeterThreats")
	M.set_meter("heat", 100.0)
	await _wait(2)
	var tid := String(MT.active_threat_id("heat"))
	_assert(tid != "", "N4: high Heat dispatched a pursuer through the real threshold ear")
	if tid == "":
		return
	var hb := _npc_body(tid)
	_assert(hb != null, "N4: the dispatched pursuer is IN the player's room within ~2 frames")
	var hspr: Sprite2D = hb.get_node_or_null("Sprite2D") if hb != null else null
	_assert(hspr != null and hspr.texture != null
		and String(hspr.texture.resource_path).ends_with("characters/nighthawk_captain.png"),
		"N4: the pursuer wears the DATA-aliased nighthawk standee from frame one")
	var toasts := get_nodes_in_group("toasts")
	_assert(toasts.size() > 0 and int(toasts[0].call("card_count")) > 0,
		"N4: the dispatch toast is up (The Nighthawks have your scent)")
	await _wait(14)   # let the card's 0.35s fade-in finish so the copy reads in the shot
	await _shot("43_threat_dispatch_nighthawk.png")
	# (44) down it through the real damage path: threat_resolved + the resolve toast.
	var hunter: Agent = reg.get_agent(tid)
	CombatExecutor.route_hit(proxy2, hunter,
		{"id": "probe_finisher_n4", "effects": [{"kind": "damage", "amount": 99999.0}]}, Vector2.RIGHT)
	await _wait(2)
	_assert(hunter != null and hunter.downed, "N4: the pursuer went down (real damage path)")
	_assert((EB.events("threat_resolved") as Array).size() > 0,
		"N4: threat_resolved world fact logged (the hunt has lost you)")
	await _wait(30)   # the resolve card's fade-in completes; the copy must READ in the shot
	await _shot("44_threat_resolved_toast.png")
	print("[probe] N4 beats done")

## ---- N3 Continue-resume beats --------------------------------------------------------------------
## CONTINUE IS A FIRST-CLASS RESUME (B-F1/B-F2/B-F5), eyeballed through the REAL seams in ONE
## process (the true fresh-autoload two-process case is tests/continue_probe.sh): a fresh run rests
## to day 2 (the nightly disk save), then the session is forced back to its cold-boot defaults and
## the REAL title Continue resumes it. Shots:
##   37_title_continue_enabled.png  — the title with Continue ENABLED (a save waiting to resume)
##   38_continue_resumed_lodging.png — the resumed lodging: live run, day 2, HUD up
##   39_continue_ritual_night_armed.png — Doom 100 on the RESUMED run: the climax arms and stages
func _continue_beats(main: Node) -> void:
	print("[probe] === N3 continue-resume beats ===")
	var RM: Node = root.get_node("/root/RunManager")
	var SM: Node = root.get_node("/root/SaveManager")
	var EG: Node = root.get_node_or_null("/root/EndGame")
	var M: Node = root.get_node("/root/Meters")

	# Clean slate after the death-pathway beats: drop any ending overlay, close the prior run
	# (this also proves invalidate_save leaves no ghost), fresh meta -> no picker on New Run.
	if EG != null and EG.has_method("dismiss"):
		EG.dismiss()
	if bool(RM.run_active()):
		RM.end_run("lose")
	main.return_to_title()
	await _wait(5)
	RM.reset_meta()

	# The "first sitting": New Run -> day 2 nightly save.
	main.start_new_run()
	await _wait(10)
	await _wait_intro_card_gone(main)
	root.get_node("/root/EventBus").emit_event("agent_downed", {"target": "bram_kell"})
	var rest: Dictionary = RM.rest_until_morning()
	_assert(bool(rest.get("ok", false)) and RM.current_day() == 2 and SM.has_save(),
		"continue beat: rest -> day 2, nightly checkpoint mirrored to the disk save")

	# The COLD BOOT (as far as one process can): back to the title, session to boot defaults.
	main.return_to_title()
	await _wait(5)
	RM._run_active = false
	RM._current_day = 1
	RM._checkpoint = {}
	RM._checkpoint_day = 0
	RM._ritual_night = false
	RM._run_knowledge = {}
	root.get_node("/root/Clock").set_time(1, 480)
	M.reset()
	root.get_node("/root/Progression").reset()
	main.return_to_title()   # refresh the Continue gating against the still-standing save
	await _wait(10)
	var cont_btn: Node = main.find_child("ContinueButton", true, false)
	_assert(cont_btn != null and not (cont_btn as Button).disabled,
		"continue beat: title Continue button ENABLED (a save waits)")
	await _shot("37_title_continue_enabled.png")

	# The REAL Continue -> a first-class resumed run.
	main.continue_run()
	await _wait(10)
	await _wait_intro_card_gone(main)
	_assert(bool(RM.run_active()), "continue beat: run_active TRUE after Continue")
	_assert(RM.current_day() == 2, "continue beat: day counter resumed at 2 (got %d)" % RM.current_day())
	_assert(bool(RM.has_checkpoint()) and RM.checkpoint_day() == 2,
		"continue beat: in-memory checkpoint rebuilt (day 2)")
	_assert((RM._run_knowledge as Dictionary).has("adversary:butcher_human"),
		"continue beat: run knowledge ledger survived the resume")
	_print_pace()
	_print_visibility(main)
	await _shot("38_continue_resumed_lodging.png")

	# Ritual Night ARMS AND FIRES on the resumed run (the B-F1 heart): Doom 100 -> staged climax.
	M.set_meter("doom", 100.0)
	await _wait(15)
	var RN: Node = root.get_node("/root/RitualNight")
	_assert(bool(RM.ritual_night_reached()), "continue beat: Doom 100 latched Ritual Night on the RESUMED run")
	_assert(bool(RN.active()), "continue beat: the Ritual Night climax STAGED on the RESUMED run")
	await _shot("39_continue_ritual_night_armed.png")

## ---- M_cast v2 Cast-roulette beats ---------------------------------------------------------------
## The title-screen NPC dossier panel as a FULL DESIGN-REFERENCE (user correction — SHOW_ALL ships
## true), eyeballed through the REAL seams on a FRESH meta: the title's The Cast button opens it;
## a mundane NPC's card carries the complete civilian dossier; a Beyonder's card stands revealed
## WITHOUT any codex (goals + secrets + pathway), scrolls down to its numbers-bearing form kits,
## and flips to the monster face; a spin is caught mid-shuffle.
## Defensive: any missing seam skips with a note so the probe stays usable on older trees.
func _cast_panel_beats(main: Node) -> void:
	var rm: Node = root.get_node_or_null("/root/RunManager")
	var db: Node = root.get_node_or_null("/root/NpcDB")
	if rm == null or db == null or not main.has_method("open_cast"):
		print("[probe] cast beats skipped (no RunManager/NpcDB/open_cast seam — pre-M_cast run)")
		return
	rm.reset_meta()   # a FRESH ledger (sandboxed by TestSandbox — the real profile is untouched)
	# Open through the REAL title button.
	var btns := main.find_children("CastButton", "", true, false)
	_assert(btns.size() == 1, "the title mounts The Cast button")
	if btns.size() == 1:
		(btns[0] as Button).pressed.emit()
	else:
		main.open_cast()
	await _wait(10)
	var panel: Node = main.cast_panel()
	_assert(panel != null and bool(panel.is_open()), "The Cast panel opened over the title")
	if panel == null:
		return
	# (a) a MUNDANE NPC's complete civilian dossier (voice/goals/knowledge/schedule/records).
	# Named pick per the capture brief, with a data-driven fallback to the first mundane card.
	var mun_idx := int(panel.index_of("maribel_hatch"))
	if mun_idx < 0:
		for i in int(panel.card_count()):
			panel.show_card(i)
			if not bool((panel.current_card() as Dictionary).get("is_beyonder", true)):
				mun_idx = i
				break
	panel.show_card(mun_idx)
	var mun: Dictionary = panel.current_card()
	_assert(String(mun.get("state", "")) == "mundane" and not (mun.get("goals", []) as Array).is_empty()
			and not (mun.get("schedule_lines", []) as Array).is_empty(),
		"the mundane card ('%s') carries the full civilian dossier (goals+schedule)" % String(mun.get("id", "")))
	await _wait(8)
	await _shot("32_cast_mundane_dossier.png")
	# (b) a BEYONDER's card, revealed on the FRESH meta — the SHOW_ALL design-reference default.
	var bey_idx := int(panel.index_of("old_neil"))
	if bey_idx < 0:
		for i in int(panel.card_count()):
			panel.show_card(i)
			if bool((panel.current_card() as Dictionary).get("is_beyonder", false)):
				bey_idx = i
				break
	panel.show_card(bey_idx)
	var bey: Dictionary = panel.current_card()
	var npc_id := String(bey.get("id", ""))
	_assert(String(bey.get("state", "")) == "revealed",
		"FRESH meta: %s stands fully revealed (SHOW_ALL default — no codex gating)" % npc_id)
	_assert(not (bey.get("secrets", []) as Array).is_empty(),
		"the card carries the actual SECRET strings")
	await _wait(8)
	await _shot("33_cast_beyonder_dossier.png")
	# (c) the SAME card scrolled deep — the numbers-bearing form kits inside the fixed frame.
	panel.scroll_dossier(100000)   # clamps to the content's end
	await _wait(4)
	_assert(int(panel.dossier_scroll_value()) > 0,
		"the dossier OVERFLOWS the card frame and scrolled down (scroll=%d)" % int(panel.dossier_scroll_value()))
	await _shot("34_cast_dossier_scrolled.png")
	# (d) the beneath-the-mask monster flip — offered with NO codex now.
	_assert(bool(panel.can_flip()), "the revealed card offers the beneath-the-mask flip (no codex needed)")
	panel.flip()
	_assert(bool(panel.is_flipped()), "the card is FLIPPED to its monster face (assets/enemies art)")
	await _wait(14)
	await _shot("35_cast_monster_flip.png")
	# (e) a mid-spin shuffle frame.
	var landed := int(panel.spin())
	_assert(landed >= 0 and landed < int(panel.card_count()),
		"spin picked a landing card (UI-layer randi — index %d)" % landed)
	await _wait(14)
	_assert(bool(panel.is_spinning()), "the shuffle is still mid-spin at the capture frame")
	await _shot("36_cast_spin.png")
	# Let the shuffle land (bounded), then leave the title clean for the run beats.
	for i in 600:
		if not bool(panel.is_spinning()):
			break
		await process_frame
	_assert(not bool(panel.is_spinning()) and int(panel.current_index()) == landed,
		"the shuffle LANDED on the spin's pick (%d)" % landed)
	panel.close()
	_assert(not bool(panel.is_open()), "the Cast panel closed back to the title")
	rm.reset_meta()
	print("[probe] cast beats done")

## ---- N5 Death-pathway beats ----------------------------------------------------------------------
## The THIRD playable build, eyeballed through the REAL seams end-to-end: two wins walk the
## WIN_UNLOCK_CHAIN (the second win's payoff screen names the Death unlock), the New-Run picker
## OFFERS death, picking it starts a live Death run (censer primary, Spirit bar), and BOTH Death prey
## are fought in-scene — human-phase tell, the descend mask-drop onto the PLACED monster art
## (auber_monster.png / cassian_monster.png), and a monster attack windup. Defensive: any missing
## seam skips with a note so the probe stays usable.
func _death_pathway_beats(main: Node) -> void:
	var rm: Node = root.get_node_or_null("/root/RunManager")
	var eg: Node = root.get_node_or_null("/root/EndGame")
	var prog: Node = root.get_node_or_null("/root/Progression")
	if rm == null or eg == null or prog == null or not main.has_method("start_new_run"):
		print("[probe] death-pathway beats skipped (missing RunManager/EndGame/Progression/boot seam)")
		return
	# TWO wins through the REAL meta seam (fresh sandboxed profile -> the roguelite drip).
	rm.reset_meta()
	for i in 2:
		rm.start_run()
		await _wait(5)
		rm.end_run("win", {"outcome": "descent_stopped"})
		rm.reload_meta()
		await _wait(10)
		if i == 1:
			# The SECOND win's payoff — the screen that names the Death unlock (MetaSurface copy).
			_assert(bool(rm.meta_unlocked_pathways().has("death")),
				"the second win unlocked the Death pathway (WIN_UNLOCK_CHAIN)")
			if bool(eg.has_overlay()):
				await _shot("23_second_win_payoff.png")
		# Clear the ending screen through its REAL button so the title stands for the next step.
		var back := _overlay_button(eg, "Return to Title")
		if back != null:
			back.pressed.emit()
			await _wait(10)
	_assert(bool(prog.available_pathways().has("death")), "Death stands among the New-Run pathway options")
	# The New-Run flow presents the picker; capture it OFFERING death, then pick Death for real.
	main.start_new_run()
	await _wait(10)
	if not bool(main.pathway_picker_active()):
		print("[probe] death-pathway beats: picker did not present — skipping")
		return
	_assert(bool(main.pathway_picker_options().has("death")), "the picker OFFERS the unlocked Death build")
	await _shot("24_death_picker.png")
	main.choose_pathway("death")
	await _wait(10)
	await _wait_intro_card_gone(main)
	_assert(String(prog.pathway()) == "death", "picking Death started a LIVE Death run")
	var pcs := get_nodes_in_group("player_combat")
	if not pcs.is_empty():
		_assert(String(pcs[0]._primary_attack_id()) == "censer_ember",
			"the Death build's attack primary is censer_ember (kit-aware, spirit-funded)")
	await _shot("25_death_run_lodging.png")
	# BOTH Death prey, fought in-scene over the PLACED monster art.
	await _death_prey_beats("sister_auber", "auber_monster",
		"26_auber_human_tell.png", "27_auber_monster_reveal.png", "28_auber_monster_attack.png")
	await _death_prey_beats("brother_cassian", "cassian_monster",
		"29_cassian_human_tell.png", "30_cassian_monster_reveal.png", "31_cassian_monster_attack.png")
	print("[probe] death-pathway beats done")

## One Death prey fought in the player's room through the real seams (the _combat_beats shape):
## RoomView body spawn, spirit-funded censer fire flips combat mode, the human phase winds up (tell),
## the authored hp_below reflex descends onto the MONSTER form (the placed art), the monster attacks.
func _death_prey_beats(prey_id: String, monster_form: String,
		tell_shot: String, reveal_shot: String, attack_shot: String) -> void:
	var reg: Node = root.get_node_or_null("/root/Agents")
	var rv: Node = root.get_node_or_null("/root/RoomView")
	var adb: Node = root.get_node_or_null("/root/AbilityDB")
	var pcs := get_nodes_in_group("player_combat")
	if reg == null or rv == null or pcs.is_empty():
		print("[probe] %s beats skipped (no registry/roomview/player rig)" % prey_id)
		return
	var proxy: Agent = reg.get_agent("player")
	var prey: Agent = reg.get_agent(prey_id)
	if proxy == null or prey == null:
		print("[probe] %s beats skipped (no player proxy / prey agent)" % prey_id)
		return
	var pc: Node = pcs[0]
	proxy.max_hp = 4000.0
	proxy.hp = 4000.0
	prey.room = proxy.room
	prey.position = proxy.position + Vector2(170, -10)
	prey.hp = prey.max_hp
	prey.downed = false
	rv.reconcile()
	await _wait(10)
	var body := _npc_body(prey_id)
	_assert(body != null, "%s body spawned in the player's room (RoomView)" % prey_id)
	if body == null:
		return
	# Sustained spirit-funded censer fire through the REAL input seam until the prey winds up a cast
	# (the cautious caster's tell). The pool is topped up per volley so the probe never runs dry.
	var eb: Node = root.get_node_or_null("/root/EventBus")
	var fb: Node = root.get_node_or_null("/root/CombatFeedback")
	var has_tell_api: bool = fb != null and fb.has_method("active_tells")
	var wound_up := false
	var got_tell := false
	var seen: int = (eb.events() as Array).size() if eb != null else 0
	for volley in 6:
		pc.set("spirituality", 40.0)
		await _wait(65)   # censer_ember cooldown 1.0s
		pc.on_attack_pressed((prey.position - proxy.position).normalized())
		for i in 240:
			await process_frame
			if eb != null:
				var evs: Array = eb.events()
				while seen < evs.size():
					var ev2: Dictionary = evs[seen]
					seen += 1
					var dd: Dictionary = ev2.get("data", {}) if ev2.get("data") is Dictionary else {}
					if String(ev2.get("type", "")) == "ability_cast_started" \
							and String(dd.get("caster", "")) == prey_id:
						wound_up = true
			if has_tell_api and (fb.active_tells() as Dictionary).has(prey_id):
				got_tell = true
			if wound_up and (got_tell or not has_tell_api):
				break
		if wound_up and (got_tell or not has_tell_api):
			break
	_assert(wound_up, "%s wound up a cast under fire (in_combat=%s)" % [prey_id, str(prey.in_combat)])
	await _aim_mouse_at(_npc_body(prey_id))
	await _wait(2)
	await _shot(tell_shot)
	# The mask-drop: the authored hp_below reflex descends onto the monster form (the placed art).
	if String(prey.combat_form) == monster_form:
		_assert(true, "%s descended to %s (landed during sustained fire)" % [prey_id, monster_form])
	else:
		prey.hp = minf(prey.hp, prey.max_hp * 0.2)
		var tf := await _wait_event("transformed", "agent", prey_id, 900)
		_assert(not tf.is_empty(), "%s descended via its authored hp_below reflex" % prey_id)
	_assert(String(prey.combat_form) == monster_form, "%s wears %s" % [prey_id, monster_form])
	await _wait(3)
	await _shot(reveal_shot)
	# The monster's attack windup, mid-flight.
	var got_attack := false
	for tries in 4:
		var ev := await _wait_event("ability_cast_started", "caster", prey_id, 900)
		if ev.is_empty():
			break
		var aid := String((ev.get("data", {}) as Dictionary).get("ability", ""))
		var anim := String((adb.ability_for(aid) as Dictionary).get("anim", "")) if adb != null else ""
		if anim == "attack":
			got_attack = true
			break
	_assert(got_attack, "the %s monster wound up an attack-anim art" % prey_id)
	await _wait(12)
	await _shot(attack_shot)
	# Put the prey down through the real seam so the next beat stages a clean room.
	CombatExecutor.route_hit(proxy, prey,
		{"id": "probe_death_finisher", "effects": [{"kind": "damage", "amount": 99999.0}]}, Vector2.RIGHT)
	_assert(prey.downed, "the lethal hit downed %s (body held, never deleted)" % prey_id)
	await _wait(30)
	print("[probe] %s beats done (form=%s downed=%s)" % [prey_id, prey.combat_form, str(prey.downed)])

## ---- N2 death beats: a checkpointed death -> the wake at the lodging ----------------------------
## The roguelite's core promise, staged IN the live run through the REAL seams: walk home, cross
## NIGHTFALL in the lodging (the live nightly auto-checkpoint), then cut the investigator down with
## a real lethal hit (CombatExecutor.route_hit emits the same agent_downed{target:"player"} a live
## fight does — the wire EndGame listens on). Captures the Continue-style wake screen and, after
## pressing the REAL Continue button, the woken-at-the-lodging frame. Defensive: a missing seam
## skips with a note so the probe stays usable for other phases.
func _death_beats(main: Node) -> void:
	var rm: Node = root.get_node_or_null("/root/RunManager")
	var eg: Node = root.get_node_or_null("/root/EndGame")
	var reg: Node = root.get_node_or_null("/root/Agents")
	var cl: Node = root.get_node_or_null("/root/Clock")
	if rm == null or eg == null or reg == null or cl == null or not main.has_method("load_world_at"):
		print("[probe] death beats skipped (missing RunManager/EndGame/Agents/Clock seam)")
		return
	if not bool(rm.run_active()):
		print("[probe] death beats skipped (no live run)")
		return
	# Home to the lodging (the safe house) and cross nightfall — the LIVE auto-checkpoint seam.
	main.load_world_at("res://scenes/IntroRoom.tscn", Vector2(415, 470))
	await _wait(30)
	cl.set_time(cl.day, 1140)   # 19:00 — the night phase begins; the player is resting at home
	await _wait(10)
	_assert(bool(rm.has_checkpoint()),
		"nightfall in the lodging took the nightly checkpoint (day %d)" % int(rm.checkpoint_day()))
	var day_checkpoint: int = int(rm.checkpoint_day())
	# The lethal blow, through the REAL seam (emits agent_downed{player} -> EndGame -> end_run).
	var proxy: Agent = reg.get_agent("player")
	var attacker: Agent = reg.get_agent("clerk_voss")
	if proxy == null or attacker == null:
		print("[probe] death beats skipped (no player proxy / attacker agent)")
		return
	proxy.hp = 5.0
	proxy.downed = false
	CombatExecutor.route_hit(attacker, proxy,
		{"id": "probe_death", "effects": [{"kind": "damage", "amount": 99999.0}]}, Vector2.LEFT)
	await _wait(20)
	_assert(eg.has_overlay() and paused, "the death raised a screen and froze the world")
	_assert(String(eg._last_result.get("outcome", "")) == "death_wake",
		"the screen is the Continue-style death_wake beat, not a run-ending (outcome '%s')"
		% String(eg._last_result.get("outcome", "")))
	_assert(bool(rm.run_active()) and int(rm.current_day()) == day_checkpoint,
		"the run CONTINUES on the checkpoint day (day %d — the death cost the day, not the run)"
		% int(rm.current_day()))
	await _shot("21_death_screen.png")
	# Press the REAL Continue: the freeze lifts and the player stands woken at the lodging.
	var cont := _overlay_button(eg, "Continue")
	_assert(cont != null, "the death screen offers CONTINUE (a setback, not Restart/Quit)")
	if cont != null:
		cont.pressed.emit()
	await _wait(15)
	_assert(not paused, "Continue lifted the freeze (the run plays on)")
	_assert(String(main.current_scene_path) == "res://scenes/IntroRoom.tscn",
		"the player WOKE at the lodging (the checkpoint's safe-house scene)")
	_assert(main.get_player() != null, "a live player body stands in the woken lodging")
	await _shot("22_death_wake_lodging.png")
	print("[probe] death beats done (day %d, %s '%s')" % [int(rm.current_day()), cl.hhmm(), cl.phase])

## Depth-first find a Button by exact label inside the EndGame overlay (the REAL button is pressed).
func _overlay_button(eg: Node, text: String) -> Button:
	if not bool(eg.has_overlay()):
		return null
	var stack: Array = [eg._overlay]
	while not stack.is_empty():
		var n: Node = stack.pop_back()
		if n is Button and String((n as Button).text) == text:
			return n
		for ch in n.get_children():
			stack.append(ch)
	return null

## ---- P5 city place-ness beats -------------------------------------------------------------------
## The live City as a PLACE: the day/night tint (Clock-forced to afternoon then night), the lamp
## glows after dark, the ambient crowd clusters, and the district map's current-lead pin. Defensive:
## a pre-P5 run captures the bare BEFORE state (the asserts print FAIL — that IS the audit finding)
## and never crashes the probe for later phases.
func _city_place_beats(main: Node) -> void:
	if not main.has_method("load_world_at"):
		print("[probe] no load_world_at — skipping city beats")
		return
	var cl: Node = root.get_node_or_null("/root/Clock")
	if cl == null:
		print("[probe] no Clock — skipping city beats")
		return
	# Walk out into the city: the market street (Laughing Eel west, Iron Cross Market east).
	main.load_world_at("res://scenes/City.tscn", Vector2(2680, 3820))
	await _wait(40)
	# DAY — force a bright afternoon and let the tint lerp settle.
	cl.set_time(cl.day, 13 * 60)
	await _wait(100)
	var tintn: Node = _city_node(main, "DayNightTint")
	_assert(tintn != null, "the live City carries the DayNightTint CanvasModulate")
	if tintn is CanvasModulate:
		print("[probe] day tint color=%s (phase %s)" % [str((tintn as CanvasModulate).color), cl.phase])
	await _shot("16_city_day.png")
	# The market ambient crowd cluster (non-interactive standee dressing).
	var crowd: Node = _city_node(main, "CrowdDressing")
	_assert(crowd != null, "the live City carries the CrowdDressing ambient clusters")
	if crowd != null and crowd.has_method("figure_count"):
		_assert(int(crowd.figure_count()) > 0,
			"crowd figures are mounted live (%d standees)" % int(crowd.figure_count()))
	var pl := get_nodes_in_group("player")
	if pl.size() > 0 and crowd != null and crowd.has_method("cluster_center"):
		(pl[0] as Node2D).global_position = (crowd.cluster_center("market") as Vector2) + Vector2(0, 170)
		await _wait(45)
	await _shot("17_city_crowd_day.png")
	# NIGHT — 21:00: the cold blue-grey tint stands and the lamps come on.
	cl.set_time(cl.day, 21 * 60)
	await _wait(160)
	if tintn is CanvasModulate:
		var c: Color = (tintn as CanvasModulate).color
		_assert(c.b > c.r, "the night tint reads cold blue-grey (b %.2f > r %.2f)" % [c.b, c.r])
	var lamps: Node = _city_node(main, "StreetLamps")
	_assert(lamps != null, "the live City carries the StreetLamps glow node")
	if lamps != null and lamps.has_method("lit_now"):
		_assert(bool(lamps.lit_now()) and int(lamps.glow_count()) > 0,
			"the lamps are LIT at night (%d glows)" % int(lamps.glow_count()))
	await _shot("18_city_night.png")
	# Up close on the nearest lamp so the warm glow pool is unmistakable.
	if pl.size() > 0 and lamps != null and lamps.has_method("nearest_glow_pos"):
		var gp: Vector2 = lamps.nearest_glow_pos((pl[0] as Node2D).global_position)
		(pl[0] as Node2D).global_position = gp + Vector2(30, 100)
		await _wait(45)
	await _shot("19_lamp_glow_night.png")
	# The district map (M): the player dot AND the current-lead pin.
	var map: Node = main.find_child("DistrictMap", true, false)
	_assert(map != null, "the HUD mounts the DistrictMap")
	if map != null and map.has_method("toggle"):
		map.toggle()
		await _wait(10)
		var ls: Node = root.get_node_or_null("/root/LeadSystem")
		if ls != null and ls.has_method("current_lead"):
			var lead: Dictionary = ls.current_lead()
			_assert(not lead.is_empty() and (lead.get("map_pos") is Array),
				"the current lead ('%s') carries a map_pos for the pin" % String(lead.get("id", "<none>")))
		else:
			print("[probe] no LeadSystem.current_lead — pre-P5 map (player dot only)")
		await _shot("20_map_lead_pin.png")
		map.toggle()
	# Leave the clock in daylight so any later phase starts neutral.
	cl.set_time(cl.day, 13 * 60)
	print("[probe] city place beats done")

## A named node on the live City scene root (the swappable World child), or null.
func _city_node(main: Node, name_: String) -> Node:
	var ws: Node = main.world_scene() if main.has_method("world_scene") else null
	return ws.get_node_or_null(NodePath(name_)) if ws != null else null

## ---- P3 combat-readability beats -----------------------------------------------------
## Stage the §0 butcher fight IN the live run through the real seams: move bram_kell (data)
## into the player's room, let RoomView spawn his body, shoot him (damage flips combat mode,
## the NPC spawns its tactics executor), drop his hp under the authored 0.5 hp_below reflex
## so assume_form fires, then land a lethal hit for the death strip. Every beat is captured
## as a real rendered frame. Defensive throughout — a missing seam skips with a note so the
## probe stays usable for other phases.

## Poll the EventBus until an event of `type` whose data[key] == value arrives (only events
## AFTER the current tail are considered). Returns the event, or {} on timeout.
func _wait_event(type: String, key: String, value: String, max_frames: int = 900) -> Dictionary:
	var eb: Node = root.get_node_or_null("/root/EventBus")
	if eb == null:
		return {}
	var start: int = (eb.events() as Array).size()
	for i in max_frames:
		await process_frame
		var evs: Array = eb.events()
		while start < evs.size():
			var ev: Dictionary = evs[start]
			start += 1
			var d: Dictionary = ev.get("data", {}) if ev.get("data") is Dictionary else {}
			if String(ev.get("type", "")) == type and String(d.get(key, "")) == value:
				return ev
	return {}

## The spawned body (group "npc") for an agent id, or null.
func _npc_body(id: String) -> Node2D:
	for b in get_nodes_in_group("npc"):
		if String(b.get("npc_id")) == id:
			return b
	return null

## The bram_kell NPC body currently spawned (group "npc"), or null.
func _kell_body() -> Node2D:
	return _npc_body("bram_kell")

## ---- P4 staged opener beat --------------------------------------------------------------------
## Wait (bounded) for GMOpening's LIVE door beat — the source NPC staged at the lodging door with
## his spoken bark bubble up — then capture it. The beat is scheduled `door_beat_delay` seconds
## after run start; the intro-card wait above consumed most of that. Also pins the knock AUDIO
## event (played_log) and prints what a player would see.
func _door_beat_shot() -> void:
	var gm: Node = root.get_node_or_null("/root/GMOpening")
	if gm == null or not gm.has_method("source_staged"):
		print("[probe] no GMOpening door-beat seam — skipping opener beat (pre-P4 run)")
		return
	var source := String(gm.OPENING.get("source_npc", ""))
	var am: Node = root.get_node_or_null("/root/AudioManager")
	var audio_checkable: bool = am != null and not bool(gm.source_staged())
	if audio_checkable:
		am.reset_played_log()   # isolate the knock from the room-change door sounds
	var body: Node2D = null
	var barked := false
	for i in 1200:
		await process_frame
		body = _npc_body(source)
		if body != null and body.get_node_or_null("Bark") != null:
			barked = true
			break
	_assert(bool(gm.source_staged()), "GMOpening staged the source NPC at the lodging door (live door beat)")
	_assert(body != null, "the source NPC's ('%s') body spawned in the lodging (RoomView)" % source)
	_assert(barked, "the spoken bark bubble is up at the door (not just the top-bar string)")
	if audio_checkable:
		_assert((am.played_log() as Array).has("door_close"),
			"the door-knock audio event played (played_log: %s)" % [am.played_log()])
	await _wait(5)
	await _shot("11_opener_door_bark.png")

## ---- P4 harvest-fork + text-polish beats --------------------------------------------------------
## After the combat beats downed the butcher, walk the rig onto his drop: the REAL walk-over gather
## fires `item_picked_up`, which is GMOpening's fork-panel trigger — the 3-choice panel presents.
## Choose 'digest' (guidance only) and pin the plan mark on the HUD lead line. Then capture the
## text polish: the hotkey cheat-line is gone, the [H] legend folds the keys in, and the lodging
## digest prompt reads like English.
func _fork_and_polish_beats(main: Node) -> void:
	var reg: Node = root.get_node_or_null("/root/Agents")
	var gm: Node = root.get_node_or_null("/root/GMOpening")
	var players := get_nodes_in_group("player")
	if reg == null or gm == null or players.is_empty():
		print("[probe] fork/polish beats skipped (no registry/GMOpening/player rig)")
		return
	var p: Node2D = players[0]
	var kell: Agent = reg.get_agent("bram_kell")
	if kell != null:
		p.global_position = kell.position   # stand on the harvest drop — the walk-over gather seam
	var panel: Node = null
	for i in 600:
		await process_frame
		panel = main.find_child("HarvestForkPanel", true, false)
		if panel != null and bool(panel.is_open()):
			break
	var panel_open: bool = panel != null and bool(panel.is_open())
	_assert(panel_open, "the harvest fork presented as a REAL 3-choice panel at the first characteristic pickup")
	if panel_open:
		_assert(int(panel.option_count()) == 3, "the panel offers the 3 authored choices")
	await _wait(5)
	# Pixel-true: the card's rendered rect must sit fully INSIDE the viewport (the P4 layout bug —
	# a state-open panel drawn off-screen — is exactly what a state assert alone cannot catch).
	var card: Control = main.find_child("ForkCard", true, false)
	var vp := Rect2(Vector2.ZERO, root.get_viewport().get_visible_rect().size)
	_assert(card != null and vp.encloses(card.get_global_rect()),
		"the fork card renders fully ON-SCREEN (rect %s in viewport %s)"
		% [str(card.get_global_rect()) if card != null else "<none>", str(vp.size)])
	await _shot("12_harvest_fork_panel.png")
	# Choose 'digest' — guidance only: the plan lands on the HUD lead line, nothing auto-executes.
	if panel_open:
		panel.choose("digest")
	await _wait(10)
	var lead_lbl: Node = main.find_child("Lead", true, false)
	var lead_text := String((lead_lbl as Label).text) if lead_lbl is Label else ""
	_assert(lead_text.find("plan:") != -1,
		"the chosen intent is marked on the HUD lead line (%s)" % lead_text)
	await _shot("13_fork_plan_marked.png")
	# Text polish: the always-on hotkey cheat-line is GONE; the [H] legend carries the keys now.
	_assert(main.find_child("Controls", true, false) == null,
		"the raw hotkey cheat-line is gone from the always-on HUD")
	var legend: Node = main.find_child("HudLegend", true, false)
	if legend != null and legend.has_method("toggle"):
		legend.toggle()
		await _wait(5)
		_assert(String(legend.legend_text()).find("investigation board") != -1,
			"the [H] legend panel folds in the panel keys")
		# Pixel-true: the legend card + its corner hint must actually sit inside the viewport.
		var lcard: Control = main.find_child("LegendPanel", true, false)
		var vp2 := Rect2(Vector2.ZERO, root.get_viewport().get_visible_rect().size)
		_assert(lcard != null and vp2.encloses(lcard.get_global_rect()),
			"the legend card renders fully ON-SCREEN (rect %s in viewport %s)"
			% [str(lcard.get_global_rect()) if lcard != null else "<none>", str(vp2.size)])
		var hint: Control = main.find_child("LegendHint", true, false)
		_assert(hint != null and hint.visible and vp2.encloses(hint.get_global_rect()),
			"the [H] corner hint renders ON-SCREEN (rect %s)"
			% [str(hint.get_global_rect()) if hint != null else "<none>"])
		await _shot("14_legend_keys.png")
		legend.toggle()
	# The polished lodging verb: stand at the digest spot so its reworded prompt shows.
	var digest_spot: Node = main.find_child("DigestSpot", true, false)
	if digest_spot != null:
		p.global_position = (digest_spot as Node2D).global_position + Vector2(0, 20)
		await _wait(30)
		var prompt: Node = digest_spot.get_node_or_null("Prompt")
		var prompt_text := String((prompt as Label).text) if prompt is Label else ""
		_assert(prompt != null and (prompt as CanvasItem).visible
				and prompt_text.find("advance the Sequence") != -1,
			"the digest prompt reads 'Digest a harvested Characteristic — advance the Sequence'")
		await _shot("15_polished_digest_prompt.png")
	print("[probe] fork/polish beats done")

## Warp the OS mouse onto a world-space node so the aim/reticle read sensibly in the shots.
## Input.warp_mouse takes WINDOW pixels while the canvas transform yields VIEWPORT coords —
## on a scaled (hidpi) window they differ by the content factor, so convert explicitly (the
## P3 reticle debug caught the cursor landing at ~2/3 of the intended spot without this).
func _aim_mouse_at(n: Node2D) -> void:
	if n == null:
		return
	var vp_pos: Vector2 = n.get_global_transform_with_canvas().origin
	var vp_size: Vector2 = root.get_viewport().get_visible_rect().size
	var win := Vector2(DisplayServer.window_get_size())
	if vp_size.x > 0.0 and vp_size.y > 0.0:
		Input.warp_mouse(vp_pos * (win / vp_size))
	else:
		Input.warp_mouse(vp_pos)
	await _wait(2)

func _combat_beats() -> void:
	var reg: Node = root.get_node_or_null("/root/Agents")
	var rv: Node = root.get_node_or_null("/root/RoomView")
	var players := get_nodes_in_group("player")
	var pcs := get_nodes_in_group("player_combat")
	if reg == null or rv == null or players.is_empty() or pcs.is_empty():
		print("[probe] combat beats skipped (no registry/roomview/player rig)")
		return
	var proxy: Agent = reg.get_agent("player")
	var kell: Agent = reg.get_agent("bram_kell")
	if proxy == null or kell == null:
		print("[probe] combat beats skipped (no player proxy / bram_kell agent)")
		return
	var pc: Node = pcs[0]
	# Staging: an over-provisioned proxy (the probe must survive the fight it photographs),
	# the butcher moved INTO the player's room, his body spawned by the real RoomView seam.
	proxy.max_hp = 4000.0
	proxy.hp = 4000.0
	kell.room = proxy.room
	kell.position = proxy.position + Vector2(150, -10)
	rv.reconcile()
	await _wait(10)
	var body := _kell_body()
	_assert(body != null, "bram_kell body spawned in the player's room (RoomView)")
	if body == null:
		return
	await _aim_mouse_at(body)
	await _shot("05_combat_before.png")

	# The opening shot: the player's revolver at the butcher. The muzzle flash belongs at
	# the STRIKE moment (cast_finished = the round leaving the barrel) — capture right after.
	var dir: Vector2 = (kell.position - proxy.position).normalized()
	print("[probe] attack verdict: %s (ammo %d)" % [str(pc.on_attack_pressed(dir)), pc.ammo_count()])
	var fin := await _wait_event("ability_cast_finished", "caster", "player", 120)
	_assert(not fin.is_empty(), "player revolver_shot cast_finished fired")
	await _wait(2)
	await _shot("06_muzzle_flash.png")

	# The damage→combat-mode flip arms the NPC's tactics executor; SUSTAINED fire lands hits
	# through that live executor and stamps last_attacker_id, so the no-intent default
	# posture has a target to engage (exactly like sustained fire in real play). A single
	# round can whiff under the probe's frame interleaving, so keep firing through the REAL
	# input seam (respecting the revolver's 0.9s cooldown) until his windup telegraph stands.
	var fb: Node = root.get_node_or_null("/root/CombatFeedback")
	var eb2: Node = root.get_node_or_null("/root/EventBus")
	var has_tell_api: bool = fb != null and fb.has_method("active_tells")
	var wound_up := false
	var got_tell := false
	var seen: int = (eb2.events() as Array).size() if eb2 != null else 0
	for volley in 6:
		await _wait(58)   # revolver cooldown 0.9s
		pc.on_attack_pressed((kell.position - proxy.position).normalized())
		for i in 300:
			await process_frame
			if eb2 != null:
				var evs: Array = eb2.events()
				while seen < evs.size():
					var ev2: Dictionary = evs[seen]
					seen += 1
					var dd: Dictionary = ev2.get("data", {}) if ev2.get("data") is Dictionary else {}
					if String(ev2.get("type", "")) == "ability_cast_started" \
							and String(dd.get("caster", "")) == "bram_kell":
						wound_up = true
			if has_tell_api and (fb.active_tells() as Dictionary).has("bram_kell"):
				got_tell = true
			if wound_up and (got_tell or not has_tell_api):
				break
		if wound_up and (got_tell or not has_tell_api):
			break
	_assert(wound_up, "bram_kell wound up a cast after the flip (in_combat=%s)" % str(kell.in_combat))
	if has_tell_api:
		_assert(got_tell, "CombatFeedback recorded a tell for bram_kell")
	else:
		print("[probe] (no CombatFeedback.active_tells yet — pre-fix run)")
	body = _kell_body()
	if body != null and body.has_method("combat_pips"):
		print("[probe] kell hp pips: %d/3 visible=%s" % [body.combat_pips(), str(body.pips_visible_now())])
	await _aim_mouse_at(body)
	await _wait(2)   # capture quickly — the windup (and its tell) must still be up
	await _shot("07_enemy_tell.png")

	# The mask-drop: drop his hp under the authored hp_below(0.5) reflex — assume_form fires
	# through the REAL reflex pipeline (1.2s windup), the transform swaps the worn form.
	# Sustained fire above may ALREADY have tripped the authored threshold — then the reveal
	# has landed (or is mid-windup) and the shot documents it either way.
	if String(kell.combat_form) == "bieber_monster":
		_assert(true, "bram_kell transformed (mask-drop) via the hp_below reflex (landed during sustained fire)")
	else:
		kell.hp = minf(kell.hp, kell.max_hp * 0.2)
		var tf := await _wait_event("transformed", "agent", "bram_kell", 900)
		_assert(not tf.is_empty(), "bram_kell transformed (mask-drop) via the hp_below reflex")
	await _wait(3)
	await _shot("08_maskdrop.png")

	# The monster's first attack-anim cast: capture ~12 frames in so the strip is mid-flight.
	var adb: Node = root.get_node_or_null("/root/AbilityDB")
	var got_attack := false
	for tries in 4:
		var ev := await _wait_event("ability_cast_started", "caster", "bram_kell", 900)
		if ev.is_empty():
			break
		var aid := String((ev.get("data", {}) as Dictionary).get("ability", ""))
		var anim := String((adb.ability_for(aid) as Dictionary).get("anim", "")) if adb != null else ""
		if anim == "attack":
			got_attack = true
			break
	_assert(got_attack, "the monster wound up an attack-anim art (strip should be playing)")
	await _wait(12)
	await _shot("09_attack_anim.png")

	# The felling blow — the death strip plays and HOLDS its last frame (the corpse stays).
	CombatExecutor.route_hit(proxy, kell,
		{"id": "probe_finisher", "effects": [{"kind": "damage", "amount": 99999.0}]}, Vector2.RIGHT)
	_assert(kell.downed, "the lethal hit downed bram_kell")
	await _wait(55)   # 8 frames @ 12fps = 0.67s — the strip has finished and is holding
	await _shot("10_death_hold.png")
	print("[probe] combat beats done (kell downed=%s form=%s)" % [str(kell.downed), kell.combat_form])
