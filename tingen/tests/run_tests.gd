extends SceneTree
## Dependency-free headless test runner. Run with:
##   godot --headless --path tingen -s tests/run_tests.gd
##
## Exercises the data-driven systems that don't need a rendered scene: the clock's
## phase math, pressure clamping + stability, the world-manager stage machine and
## seeded slots, clue collection + topic unlock, event scoring, and a full
## save -> mutate -> load round-trip. Autoloads are available because they are
## registered in project.godot. Exits non-zero on any failure so CI can gate on it.

var _passed: int = 0
var _failed: int = 0
var _skipped: int = 0

# B3 (retro): the REAL user profile's pre-suite state, captured before any test runs so the final
# _test_real_meta_untouched() can prove the whole suite never read-modified or wiped it.
var _real_meta_existed: bool = false
var _real_meta_before: String = ""

func _init() -> void:
	# Let autoloads finish their _ready before asserting against them.
	await process_frame
	await process_frame

	# B3 (retro): NEVER touch the player's REAL persistent profile (user://meta.json) — redirect the
	# meta slot to a test-scoped file before ANY test drives RunManager, and record the real profile's
	# bytes so the suite proves at the very end it never touched them (tests/test_meta_isolation.gd).
	var _rm_b3: Object = root.get_node("/root/RunManager")
	_rm_b3.set("meta_path", "user://meta_test.json")
	_rm_b3.reload_meta()
	_real_meta_existed = FileAccess.file_exists(String(_rm_b3.META_PATH))
	_real_meta_before = FileAccess.get_file_as_string(String(_rm_b3.META_PATH)) if _real_meta_existed else ""

	_test_clock_phases()
	_test_pressure_clamp_and_stability()
	_test_world_manager_stages()
	_test_seeded_slots_are_deterministic()
	_test_clue_collection()
	_test_event_scoring()
	_test_save_load_roundtrip()
	_test_clock_beats()
	_test_event_bus()
	_test_agent_fallback()
	_test_agent_registry()
	_test_agent_thought()
	_test_agent_combat_state()
	_test_agent_inventory()
	_test_agent_downed_freeze()
	_test_cult_cell_seeded()
	_test_roster_hydration()
	_test_substrate_save_load()
	_test_item_db()
	_test_inventory_add_remove()
	_test_inventory_use()
	_test_inventory_save_load()
	_test_action_schema()
	_test_mock_sidecar()
	_test_ambient_sidecar()
	_test_ambient_sidecar_performs_rite()
	_test_ambient_sidecar_task_ladder()
	_test_offline_descent_completes()
	_test_cathedral_rite_mvp()
	_test_room_traversal()
	_test_interior_rooms()
	_test_spawn_formation()
	_test_concurrency_phase1()
	_test_coordinator_focus()
	_test_http_sidecar()
	_test_brain_decide_request()
	_test_sidecar_bridge()
	_test_perception_snapshot()
	_test_action_commit()
	_test_coordinate_anchors_consistent()
	_test_city_scene_placements_legal()
	_test_city_buildings()
	_test_city_layout()
	_test_city_layout_data()
	_test_npc_waypoints_walkable()
	_test_roster_waypoints_legal()
	await _test_navmesh_routing()
	_test_ritual_step_advances_summoning()
	_test_commit_sets_thought()
	_test_action_attack()
	_test_action_adopt_drop_goal()
	_test_adopted_goals_reach_brain()
	_test_typed_defection_marker()
	_test_persona_fields_plumbed()
	_test_data_driven_npc_fields_inert()
	_test_converse_request_shape()
	_test_converse_seam()
	_test_converse_action_gating()
	_test_ambient_converse()
	_test_send_utterance_advances()
	_test_dialogue_async()
	_test_player_proxy_and_combat()
	_test_perception_stimulus()
	_test_vision_nearby_gating()
	_test_vision_r_data_and_roundtrip()
	_test_vision_stimulus_gating()
	_test_action_cross_room_guard()
	_test_model_config()
	_test_action_gather_item()
	_test_room_items_store()
	_test_gather_capacity_and_ground()
	_test_action_talk_to_rumor()
	_test_agent_runtime_beat()
	_test_overseer_state()
	_test_critic_verdicts()
	_test_critic_downed_veto()
	_test_perception_health()
	_test_intent_verbs_schema()
	_test_combat_intent_commit()
	_test_critic_victim_engage()
	_test_runtime_combat_intent_hold()
	_test_telegraph_events()
	_test_telegraph_stimulus_fan()
	_test_combat_mode_flip()
	_test_m1_review_fixes()
	_test_combat_form_hydration()
	await _test_npc_puppet_combat_hold()
	_test_ability_db()
	_test_resolver_damage_and_shield()
	_test_resolver_statuses()
	_test_resolver_cooldown_ledger()
	_test_resolver_poise_iframes_transform()
	_test_executor_fsm()
	_test_executor_windup_interruption()
	_test_executor_projectile()
	_test_executor_zone()
	_test_executor_melee_dedup()
	_test_executor_dash_iframes()
	_test_executor_damage_downs()
	await _test_npc_spawns_executor()
	_test_perceiver_gate()
	_test_reflex_rules_vectors()
	_test_tactical_bands()
	_test_tactical_style_masks()
	_test_combat_vectors()
	_test_tactical_default_posture()
	_test_tactical_protect()
	_test_tactical_disengage()
	_test_reflex_executor_wiring()
	_test_transform_execution()
	_test_transform_reflex_guard()
	_test_civilian_flees()
	_test_m2_review_fixes()
	_test_perception_combat_forwarding()
	_test_ambient_combat_ladder()
	_test_coordinator_skips_combatants()
	_test_cast_ability_seam()
	_test_corruption_transform_directive()
	_test_runtime_with_overseer()
	_test_summoning_plan()
	_test_rituals_match_staged_requirement()
	_test_gods_db()
	_test_prayer_adjudication()
	_test_prayer_service()
	_test_summoning_countdown_and_climax()
	_test_summoning_advance_rite()
	_test_summoning_progress_readouts()
	await _test_cult_progress_panel()
	await _test_npc_binds_to_agent()
	_test_roomview_tracks_all()
	_test_inspect_signal()
	await _test_character_card_opens()
	await _test_city_blocks_scene()
	_test_occult_divination()
	_test_divination_hints_never_name_site()
	_test_occult_other_tools()
	_test_occult_tool_views()
	await _test_ritual_panel()
	_test_player_actions()
	_test_player_sabotage_any()
	_test_dialogue_social_influence_effect()
	_test_orin_persuade_dialogue()
	_test_captain_briefing_grants_tools()
	_test_dev_console_interference_commands()
	_test_combat_scaled_by_impede()
	_test_endgame_resolver()
	_test_endgame_ending_bands()
	_test_endgame_autoload()
	_test_map_projection_world_to_map()
	_test_map_projection_canvas_fit()
	_test_district_map_polygons()
	_test_map_texture_imported()
	_test_player_state_save_load()
	_test_schema_parity_with_sidecar()
	_test_prayer_parity_with_sidecar()
	await _test_prayer_panel()
	await _test_debug_log_panel()
	_test_gm_digest()
	_test_gm_digest_combat()
	await _test_gm_panel()
	await _test_inventory_panel()
	await _test_dialogue_panel_hybrid()
	await _test_hud_toggle_keys()
	await _test_district_map_panel()
	await _test_toasts()
	await _test_player_position_sync()
	await _test_player_stamina()
	await _test_player_8way_facing()
	_test_combat_input_actions()
	_test_player_combat_casts()
	_test_player_combat_ammo()
	_test_player_loadout()
	_test_player_combat_dash()
	_test_player_combat_charm()
	await _test_combat_hud_binds()
	await _test_hud_telegraph_vision_gate()
	_test_player_lethal_downs_endgame()
	_test_deed_runner_night_deed()
	_test_kell_consequences()
	_test_critic_attack_amend()
	_test_combat_anim_wiring()
	_test_combat_fx_scenes_have_visuals()
	await _test_combat_fx_spawner_transient()
	_test_abilities_fx_field_and_resolver()
	await _test_combat_fx_determinism_guard()
	_test_run_manager_run_shell()
	_test_meters_clamp_reset_and_ladder()
	_test_meters_panic_derived_and_doom_driver()
	await _test_meters_rampage_ends_run()
	_test_progression_advance_loop()
	_test_progression_characteristic_drop()
	_test_progression_new_abilities_shapes()
	_test_leads_run_start_and_source_gate()
	_test_leads_perish_cold_respawn()
	_test_leads_follow_resolve_and_snapshot()
	_test_leads_determinism_fixed_seed()
	_test_ritual_night_climax()
	_test_meta_payoff()
	_test_meta_profile_isolation()
	await _test_live_bugs_m20()
	_test_opening_contract()
	_test_polish_settings()
	_test_polish_combat_feedback_gates()
	await _test_polish_pause_menu()
	await _test_polish_hud_legend()
	_test_polish_spark_burst_fix()
	await _test_polish_combat_fx_determinism_still_holds()
	await _test_meter_teeth_spawns_and_doom_fill()
	_test_adversary2_hunter_prey()
	_test_adversary3_mack_docks()
	_test_adversary3_seq7_advance_loop()
	_test_reload_ammo_spawn_registered()
	_test_reload_pickup_seeds_deterministic()
	_test_reload_empty_gun_event()
	_test_reload_flash_toggle()
	_test_reload_reset_per_run()
	_test_reload_determinism_try_pay()
	_test_reload_city_bootstrap_preserves_ammo()
	_test_reload_player_proximity_pickup()
	_test_npc_cost_provider()
	_test_npc_loadout_and_loot()
	_test_shop_buy_costed_and_latched()
	_test_shop_sell_real_coin_and_fuel_forfeit()
	_test_shop_reset_and_snapshot()
	_test_shop_fork_sell_and_counter_wired()
	_test_shop_live_fork_presented()
	await _test_visual_npc_sprite_seam()
	_test_visual_form_sprite_seam()
	await _test_visual_theme_and_settings()
	_test_portrait_helper_resolves()
	await _test_dialogue_portrait_slot()
	await _test_portrait_hardening()
	_test_save_spend_seed()
	_test_combat_deadends()
	_test_hud_single_meter_panel()
	_test_converse_redaction()
	await _test_combat_juice()
	_test_system_rewire()
	_test_balance()
	_test_hermit_pathway()
	await _test_hermit_live()
	_test_counter_rite()
	_test_counter_rite_usability()
	_test_combat_camera()
	_test_spirituality_pool()
	_test_hermit_primary()
	_test_no_spirit_cue()
	_test_hermit_save_load()
	await _test_hermit_full_run()
	await _test_ground_gather()
	await _test_onboarding()
	_test_dry_art_fallback()
	_test_earned_reveal()
	_test_meter_counterplay()
	_test_meta_surface_builder()
	await _test_meta_surface_title_wire()
	_test_meta_surface_endgame_payoff()
	# B3: MUST stay the LAST test — proves no test above touched the real user profile.
	_test_real_meta_untouched()

	print("\n=== %d passed, %d failed, %d skipped ===" % [_passed, _failed, _skipped])
	quit(1 if _failed > 0 else 0)

# --- M16 Visual Foundation ---------------------------------------------------------------------
## (a) a mapped NPC shows real art (path != icon.svg, tint dropped); (b) an unmapped NPC keeps the
## icon.svg placeholder + its identity tint, and a bogus id falls back without crashing.
func _test_visual_npc_sprite_seam() -> void:
	print("[visual npc sprite seam]")
	var icon := "res://icon.svg"
	# constable_brom -> CONVENTION file; ledger_finch -> explicit `sprite` field. Both real art.
	for id in ["constable_brom", "ledger_finch"]:
		var npc = load("res://scenes/NPC.tscn").instantiate()
		npc.npc_id = id
		root.add_child(npc)
		await process_frame
		var spr: Sprite2D = npc.get_node("Sprite2D")
		var path := spr.texture.resource_path if spr.texture != null else ""
		_ok(path != "" and path != icon, "%s shows a real sprite (%s)" % [id, path])
		_ok(spr.modulate.r == 1.0 and spr.modulate.g == 1.0 and spr.modulate.b == 1.0,
			"%s drops the flat tint under real art" % id)
		npc.queue_free()
		await process_frame
	# unmapped id: placeholder icon.svg + identity tint, no crash
	var neil = load("res://scenes/NPC.tscn").instantiate()
	neil.npc_id = "zz_artless_probe"
	root.add_child(neil)
	await process_frame
	var nspr: Sprite2D = neil.get_node("Sprite2D")
	_ok(nspr.texture != null and nspr.texture.resource_path == icon, "an artless npc keeps the icon placeholder")
	_ok(load("res://src/NPC.gd").resolve_sprite_path("zz_artless_probe", {}) == "",
		"the seam resolves NO art for an artless id (placeholder contract)")
	neil.queue_free()
	var bogus = load("res://scenes/NPC.tscn").instantiate()
	bogus.npc_id = "no_such_npc_xyz"
	root.add_child(bogus)
	await process_frame
	var bspr: Sprite2D = bogus.get_node("Sprite2D")
	_ok(bspr.texture != null and bspr.texture.resource_path == icon, "unknown id falls back without crashing")
	bogus.queue_free()
	await process_frame

## (c) a combat_form with enemies/<form>.png swaps the body sprite; one without falls back cleanly.
func _test_visual_form_sprite_seam() -> void:
	print("[visual form sprite seam]")
	var body := Node2D.new()
	var spr := Sprite2D.new()
	spr.texture = load("res://icon.svg")
	body.add_child(spr)
	root.add_child(body)
	var ex := CombatExecutor.new()
	var ag := Agent.new("form_probe_vf")
	ex.bind(ag, body)
	ex._apply_form_sprite("bieber_monster")
	_ok(spr.texture != null and spr.texture.resource_path.ends_with("bieber_monster.png"),
		"a form with enemies/<form>.png shows it")
	var before := spr.texture
	ex._apply_form_sprite("zz_artless_form_probe")   # a synthetic form id with no enemies/<form>.png
	_ok(spr.texture == before, "a form without art falls back cleanly (no crash, sprite unchanged)")
	ex.free()
	body.queue_free()

## (d) the shared Theme loads + a probe Control under a themed root inherits it, and it is the
## project-wide gui theme; (e) the M10 Settings seams (text_scale + colorblind) still bite with it active.
func _test_visual_theme_and_settings() -> void:
	print("[visual theme + settings seams]")
	var theme_path := "res://assets/ui/tingen_theme.tres"
	_ok(ResourceLoader.exists(theme_path), "theme resource exists")
	var th = load(theme_path)
	_ok(th is Theme and th.default_font_size > 0, "theme loads with a default font size")
	_ok(String(ProjectSettings.get_setting("gui/theme/custom", "")) == theme_path,
		"theme is the project-wide gui theme")
	var host := Control.new()
	host.theme = th
	var probe := Label.new()
	host.add_child(probe)
	root.add_child(host)
	await process_frame
	_ok(probe.get_theme_default_font_size() == th.default_font_size, "a probe under a themed root inherits it")
	var Settings_al: Object = root.get_node("/root/Settings")
	Settings_al.set_value("text_scale", 2.0)
	Settings_al.apply_text_scale(probe, 12)
	_ok(probe.get_theme_font_size("font_size") == 24, "text_scale override beats the theme default")
	Settings_al.set_value("colorblind", true)
	var cb: Color = Settings_al.meter_color("doom")
	_ok(abs(cb.r) < 0.01 and abs(cb.g - 0.45) < 0.01 and abs(cb.b - 0.70) < 0.01,
		"colorblind palette still applies with the theme active")
	Settings_al.set_value("text_scale", 1.0)
	Settings_al.set_value("colorblind", false)
	host.queue_free()
	await process_frame

# --- M19 NPC Portrait in the UI ----------------------------------------------------------------
## The reusable Portrait resolver (src/Portrait.gd) maps an npc id -> its painterly portrait by the
## SAME M16 convention (assets/characters/<id>.png), with a graceful null fallback for an artless id.
func _test_portrait_helper_resolves() -> void:
	print("[portrait helper: id -> texture with fallback]")
	var P = load("res://src/Portrait.gd")
	for id in ["bram_kell", "old_neil"]:
		_ok(P.resolve_path(id) == "res://assets/characters/%s.png" % id, "%s resolves by convention" % id)
		_ok(P.resolve_texture(id) is Texture2D, "%s resolves to a real texture" % id)
	_ok(P.resolve_texture("zz_artless_probe") == null, "an artless id resolves to NO texture (fallback)")
	_ok(P.resolve_path("zz_artless_probe") == "", "an artless id resolves to an empty path")

## The dialogue panel shows the speaker's portrait on open, swaps it on a speaker change, and clears
## it on close; an artless speaker falls back to an empty slot without crashing the dialogue.
func _test_dialogue_portrait_slot() -> void:
	print("[dialogue panel: speaker portrait slot]")
	var panel: Control = load("res://ui/DialoguePanel.tscn").instantiate()
	root.add_child(panel)
	await process_frame
	panel._on_started("bram_kell")   # dialogue_started(npc_id) handler — fires on open + on switch
	await process_frame
	var t1: Texture2D = panel.portrait_texture()
	_ok(t1 != null and t1.resource_path == "res://assets/characters/bram_kell.png",
		"opening with bram_kell shows their character png in the slot")
	panel._on_started("old_neil")    # speaker changes
	await process_frame
	var t2: Texture2D = panel.portrait_texture()
	_ok(t2 != null and t2.resource_path == "res://assets/characters/old_neil.png",
		"the portrait swaps to old_neil on a speaker change")
	panel._on_started("zz_artless_probe")   # an artless speaker
	await process_frame
	_ok(panel.portrait_texture() == null, "an artless speaker leaves the slot empty (silhouette fallback)")
	panel._on_node_changed("Nobody", "A voice with no face.", [{"text": "Go on."}])
	await process_frame
	_ok((panel.get_node("Box/Margin/Body/Text") as Label).text == "A voice with no face.",
		"dialogue still renders for an artless speaker (no crash)")
	panel._on_ended()
	await process_frame
	_ok(panel.portrait_texture() == null, "the portrait clears when the conversation closes")
	panel.queue_free()
	await process_frame

## FIXER regressions: (LOW) the Portrait's Settings.changed connect is idempotent under a re-parent
## re-_ready() — was an unguarded lambda that double-connected; (COSMETIC) the leads-board headshot
## crop clamps its atlas region to the shorter side so a wider-than-tall portrait can't overrun bounds.
func _test_portrait_hardening() -> void:
	print("[portrait hardening: idempotent settings connect + clamped headshot crop]")
	var s := root.get_node_or_null("/root/Settings")
	if s != null and s.has_signal("changed"):
		var p: Control = load("res://src/Portrait.gd").new()
		root.add_child(p)          # first _ready() -> one connection
		await process_frame
		p._ready(); p._ready()     # simulate a re-parent re-running _ready()
		var n := 0
		for c in s.get_signal_connection_list("changed"):
			if c.get("callable") is Callable and (c["callable"] as Callable).get_object() == p:
				n += 1
		_ok(n == 1, "Portrait connects Settings.changed exactly once across three _ready() calls (got %d)" % n)
		p.queue_free()
		await process_frame
	var Board := load("res://src/InvestigationBoard.gd")
	var wide: Texture2D = ImageTexture.create_from_image(Image.create(100, 40, false, Image.FORMAT_RGBA8))
	_ok(Board.headshot_side(wide) == 40.0 and Board.headshot_side(wide) <= float(wide.get_height()),
		"leads-board headshot crop clamps a wide portrait to its height (region never overruns)")

## M21 (B3/B4/B5): save integrity + LLM budget cap + per-run reseed. The full harness lives in
## tests/test_save_spend_seed.gd; its run_all() shares this suite's pass/fail totals.
func _test_save_spend_seed() -> void:
	print("[M21 save/spend/seed: B3 disk round-trip, B4 budget+pause gate, B5 per-run reseed]")
	var runner := load("res://tests/test_save_spend_seed.gd")
	var r: Dictionary = runner.run_all()
	_passed += int(r.get("passed", 0))
	_failed += int(r.get("failed", 0))
	_ok(int(r.get("failed", 1)) == 0 and int(r.get("passed", 0)) > 0,
		"M21 save/spend/seed green (%d checks)" % int(r.get("passed", 0)))

## M26 — the DATA-ONLY BALANCE RETUNE sanity pins. The full harness lives in tests/test_balance.gd;
## its run_all() shares this suite's pass/fail totals (idle Doom pacer ~day 6-7 + one-monster-survivable,
## hidden-Beyonder Doom cost, the sell-fork trap removed by the pity margin, two-advance Madness tension,
## the ~48-beat Ritual Night fuse, and the combat-pin invariant).
func _test_balance() -> void:
	print("[M26 balance retune: Doom pacer, hidden-Beyonder cost, sell-fork pity, Madness tension, ritual fuse]")
	var runner := load("res://tests/test_balance.gd")
	var r: Dictionary = runner.run_all()
	_passed += int(r.get("passed", 0))
	_failed += int(r.get("failed", 0))
	_ok(int(r.get("failed", 1)) == 0 and int(r.get("passed", 0)) > 0,
		"M26 balance retune green (%d checks)" % int(r.get("passed", 0)))

## M22 (B8/B9): the two combat DEAD-ENDS. The full harness lives in tests/test_combat_deadends.gd;
## its run_all() shares this suite's pass/fail totals (a dry player always has an ammo-free melee
## floor; an interrupted-then-abandoned Ritual Night always resolves via the backlash backstop).
func _test_combat_deadends() -> void:
	print("[M22 combat dead-ends: B8 ammo-free melee floor, B9 backlash backstop]")
	var runner := load("res://tests/test_combat_deadends.gd")
	var r: Dictionary = runner.run_all()
	_passed += int(r.get("passed", 0))
	_failed += int(r.get("failed", 0))
	_ok(int(r.get("failed", 1)) == 0 and int(r.get("passed", 0)) > 0,
		"M22 combat dead-ends green (%d checks)" % int(r.get("passed", 0)))

## M24 (backlog "M19") — Tier-1 combat JUICE: live-only, Settings-gated, zero combat-determinism
## impact. The full harness lives in tests/test_combat_juice.gd; its run_all() (a coroutine — one
## step awaits a frame to stage an NPC body) shares this suite's pass/fail totals. Pins: a
## player-landed hit -> hit-stop + kick; the struck enemy whitens then restores; transformed -> a
## big shake, agent_downed -> a medium shake + a beat of hit-stop; and the juice never perturbs a
## fixed-dt fight transcript (byte-identical juice-on vs juice-off).
func _test_combat_juice() -> void:
	print("[M24 combat juice: player-hit hit-stop+kick, enemy whiten, transform/downed tiers, determinism]")
	var runner := load("res://tests/test_combat_juice.gd")
	var r: Dictionary = await runner.run_all()
	_passed += int(r.get("passed", 0))
	_failed += int(r.get("failed", 0))
	_ok(int(r.get("failed", 1)) == 0 and int(r.get("passed", 0)) > 0,
		"M24 combat juice green (%d checks)" % int(r.get("passed", 0)))

## B10 (M23): the duplicate meter panel is gone. The legacy 3-meter panel (Stability/Corruption/Panic)
## mirrored the new 4-meter MeterHUD (Corruption aliases Doom), stacking two panels on the right. The
## HUD scene must now carry EXACTLY ONE meter readout — MeterHUD — with the legacy `Meters` node removed
## and its HUD.gd driver excised; MeterHUD progressive disclosure (Doom shown, the rest revealed on
## trigger) must still work.
func _test_hud_single_meter_panel() -> void:
	print("[B10 HUD: exactly one meter panel (MeterHUD kept, legacy Meters removed)]")
	var M: Object = root.get_node("/root/Meters")
	M.reset()
	var hud: Control = (load("res://ui/HUD.tscn") as PackedScene).instantiate()
	root.add_child(hud)
	# The legacy Stability/Corruption/Panic panel node is GONE; the M4 MeterHUD is the sole keeper.
	_ok(not hud.has_node("Meters"), "the legacy Meters panel node (Stability/Corruption/Panic) is removed from HUD.tscn")
	_ok(hud.has_node("MeterHUD"), "the M4 MeterHUD panel is the one meter readout that remains")
	# Progressive disclosure still holds: at run-start Doom is revealed, Madness/Notice/Heat are hidden.
	var mh: Control = hud.get_node("MeterHUD")
	_ok(mh.get_node("Doom").visible, "MeterHUD: Doom is revealed at run-start")
	_ok(not mh.get_node("Madness").visible, "MeterHUD: Madness stays hidden until its first trigger")
	# A Madness trigger reveals its row — progressive disclosure is intact after the cleanup.
	M.add_madness(60.0)
	await process_frame
	_ok(mh.get_node("Madness").visible, "MeterHUD: a Madness trigger reveals the Madness row (disclosure intact)")
	hud.free()
	M.reset()

## B2 retro-audit finding 1 (M18 overclaim): the DRY-ART FALLBACK harness. The full body lives in
## tests/test_dry_art_fallback.gd; its run_all_on() shares this suite's pass/fail totals (a dry
## gunman NPC under enable_tactics falls back to its FREE arts instead of livelocking on the
## refused pick; try_cast's no-cooldown-burned refusal contract stays untouched; a mid-fight
## resupply re-enables the costed art).
func _test_dry_art_fallback() -> void:
	print("[B2 dry-art fallback: a dry gunman leans on free arts (M18 claim made true)]")
	var runner := load("res://tests/test_dry_art_fallback.gd")
	var r: Dictionary = runner.run_all_on(root)
	_passed += int(r.get("passed", 0))
	_failed += int(r.get("failed", 0))
	_ok(int(r.get("failed", 1)) == 0 and int(r.get("passed", 0)) > 0,
		"B2 dry-art fallback green (%d checks)" % int(r.get("passed", 0)))

## B2 retro-audit finding 2 (M23 dead channel): the EARNED-REVEAL harness. The full body lives in
## tests/test_earned_reveal.gd; its run_all_on() shares this suite's pass/fail totals (a
## gate-approved converse `reveal_secret` action finally calls Agent.reveal_secret so the
## redaction stops scrubbing THAT earned secret for THAT agent; everything un-earned stays
## default-deny — prose alone never reveals, a mismatched action reveals nothing).
func _test_earned_reveal() -> void:
	print("[B2 earned reveal: the converse action layer wires Agent.reveal_secret (M23)]")
	var runner := load("res://tests/test_earned_reveal.gd")
	var r: Dictionary = runner.run_all_on(root)
	_passed += int(r.get("passed", 0))
	_failed += int(r.get("failed", 0))
	_ok(int(r.get("failed", 1)) == 0 and int(r.get("passed", 0)) > 0,
		"B2 earned reveal green (%d checks)" % int(r.get("passed", 0)))

## B5 (retro, the live playtest's major finding): meter-threat COUNTERPLAY. The full harness lives
## in tests/test_meter_counterplay.gd; its run_all() shares this suite's pass/fail totals (Notice
## gates on OCCULT casts like Madness gates on HEAVY_CLASSES; fighting a dispatched hunter no longer
## compounds its own meter and the kill relieves it below the respawn rung; no hunter spawns into a
## live Ritual Night, resuming after).
func _test_meter_counterplay() -> void:
	print("[B5 meter counterplay: occult Notice gate, winnable hunts, Ritual Night spawn shield]")
	var runner := load("res://tests/test_meter_counterplay.gd")
	var r: Dictionary = runner.run_all_on(root)
	_passed += int(r.get("passed", 0))
	_failed += int(r.get("failed", 0))
	_ok(int(r.get("failed", 1)) == 0 and int(r.get("passed", 0)) > 0,
		"B5 meter counterplay green (%d checks)" % int(r.get("passed", 0)))

## B11 (M23): the converse secret-leak REDACTION harness. The full body lives in
## tests/test_converse_redaction.gd; its run_all() shares this suite's pass/fail totals (a leaking
## model reply is scrubbed engine-side on the return path; a revealed secret stays discussable; the
## converse perception never carries an in-combat NPC's kit/combat_intent).
func _test_converse_redaction() -> void:
	print("[M23 converse redaction: engine-side secret-leak backstop (B11)]")
	var runner := load("res://tests/test_converse_redaction.gd")
	var r: Dictionary = runner.run_all_on(root)
	_passed += int(r.get("passed", 0))
	_failed += int(r.get("failed", 0))
	_ok(int(r.get("failed", 1)) == 0 and int(r.get("passed", 0)) > 0,
		"M23 converse redaction green (%d checks)" % int(r.get("passed", 0)))

## M25 (backlog "M18"): reconnect the three orphaned player systems (prayer / occult tools / ambient
## events) to the LIVE v2 economy (Meters + LeadSystem). The full harness lives in
## tests/test_system_rewire.gd; its run_all() shares this suite's pass/fail totals (a prayer/tool/event
## effect now moves a live meter and NO LONGER drives the dead legacy pressure; occult leads land in
## LeadSystem.active_leads, not WorldState.set_lead; the mappings clamp + reset per run).
func _test_system_rewire() -> void:
	print("[M25 system rewire: prayer/occult/events -> live meters + LeadSystem (backlog M18)]")
	var runner := load("res://tests/test_system_rewire.gd")
	var r: Dictionary = runner.run_all()
	_passed += int(r.get("passed", 0))
	_failed += int(r.get("failed", 0))
	_ok(int(r.get("failed", 1)) == 0 and int(r.get("passed", 0)) > 0,
		"M25 system rewire green (%d checks)" % int(r.get("passed", 0)))

## M28 (backlog "M26") — the HERMIT package: the SECOND playable pathway + the old_neil adversary. The
## full harness lives in tests/test_hermit_pathway.gd; its run_all() shares this suite's pass/fail totals
## (selecting Hermit gives a DISTINCT star/ritual base kit via the SAME kit seam; the advance loop closes
## through old_neil -> hermit_characteristic -> the acting rite -> the Hermit ladder; old_neil is a real
## two-phase adversary with a lead + deed; a first win unlocks + plays the build).
func _test_hermit_pathway() -> void:
	print("[M28 hermit pathway: 2nd playable build (star/ritual kit) + old_neil adversary + advance loop]")
	var runner := load("res://tests/test_hermit_pathway.gd")
	var r: Dictionary = runner.run_all()
	_passed += int(r.get("passed", 0))
	_failed += int(r.get("failed", 0))
	_ok(int(r.get("failed", 1)) == 0 and int(r.get("passed", 0)) > 0,
		"M28 hermit pathway green (%d checks)" % int(r.get("passed", 0)))

## M30 — HERMIT LIVE REACHABILITY: the M28 Hermit layer made actually reachable + completable in LIVE
## play. The full harness lives in tests/test_hermit_live.gd; its run_all() is a COROUTINE (mounts the
## real BootController to drive the New-Run pathway pick), so this wrapper AWAITS it and shares the
## suite's totals. Proves G1 (start_run threads the chosen pathway + it survives reset; the New-Run flow
## gates the picker on the meta unlock), G2 (the 9->8->7 ladder fed by TWO real kills — old_neil then
## ledger_finch — digested through the SAME live Interactable verb the Hunter uses), and bug#3
## (slot_run pathway-gates prey leads: hermit prey never in a Hunter run, hunter prey never in a Hermit run).
func _test_hermit_live() -> void:
	print("[M30 hermit live reachability: New-Run pathway pick + 2nd prey (ledger_finch) + pathway-gated leads]")
	var runner := load("res://tests/test_hermit_live.gd")
	var r: Dictionary = await runner.run_all()
	_passed += int(r.get("passed", 0))
	_failed += int(r.get("failed", 0))
	_ok(int(r.get("failed", 1)) == 0 and int(r.get("passed", 0)) > 0,
		"M30 hermit live reachability green (%d checks)" % int(r.get("passed", 0)))

## M28 (backlog "M26") — the COUNTER-RITE: the ONLY player verb that pushes Doom DOWN. The full harness
## lives in tests/test_counter_rite.gd; its run_all() shares this suite's pass/fail totals (performing it
## spends occult ingredients, reduces Doom, adds impede, and taxes Notice; refuses cleanly without them).
func _test_counter_rite() -> void:
	print("[M28 counter-rite: the anti-Doom verb — spend ingredients, reduce Doom, add impede, tax Notice]")
	var runner := load("res://tests/test_counter_rite.gd")
	var r: Dictionary = runner.run_all()
	_passed += int(r.get("passed", 0))
	_failed += int(r.get("failed", 0))
	_ok(int(r.get("failed", 1)) == 0 and int(r.get("passed", 0)) > 0,
		"M28 counter-rite green (%d checks)" % int(r.get("passed", 0)))

## M32 — make the COUNTER-RITE USABLE: (A) a once-per-run diegetic discoverability hint that fires
## EXACTLY once at the first moment the player holds BOTH ingredients (driven through the real
## Inventory.add acquire seam, surfaced on the HUD thought channel), and (B) a reliable ingredient
## SOURCE at Franky's counter (the real buy flow debits coin + delivers the ingredient into the ritual
## Inventory the counter-rite reads, so after buying both CounterRite.can_perform passes + perform
## drops Doom). The full harness lives in tests/test_counter_rite_usability.gd; its run_all() shares
## this suite's pass/fail totals. Live-reachability proofs: hint via the real acquire seam, ingredient
## source via the real buy -> perform chain.
func _test_counter_rite_usability() -> void:
	print("[M32 counter-rite usability: once-per-run discoverability hint + Franky's ingredient source (buy -> performable -> Doom down)]")
	var runner := load("res://tests/test_counter_rite_usability.gd")
	var r: Dictionary = runner.run_all()
	_passed += int(r.get("passed", 0))
	_failed += int(r.get("failed", 0))
	_ok(int(r.get("failed", 1)) == 0 and int(r.get("passed", 0)) > 0,
		"M32 counter-rite usability green (%d checks)" % int(r.get("passed", 0)))

## M35 AFFORDANCE & ONBOARDING: the Interactable highlight STATE (the affordance the live glow/bob rides)
## + the reusable once-only HintDirector framework (dedup by key, persisted once-ever, the real
## ability_cast_started cast/telegraph seam fires first-dash/fire/telegraph once each) + M32's counter-rite
## hint routed THROUGH that framework (no parallel system). Full harness in tests/test_onboarding.gd; its
## run_all() (a coroutine — one tree frame for the Interactable scene) shares this suite's pass/fail totals.
## All visuals are LIVE-ONLY behind _is_live(), so the pinned sims are untouched.
func _test_onboarding() -> void:
	print("[M35 affordance & onboarding: interactable highlight STATE + once-only HintDirector framework (dedup/persist/real-trigger) + counter-rite routed through it]")
	var runner := load("res://tests/test_onboarding.gd")
	var r: Dictionary = await runner.run_all()
	_passed += int(r.get("passed", 0))
	_failed += int(r.get("failed", 0))
	_ok(int(r.get("failed", 1)) == 0 and int(r.get("passed", 0)) > 0,
		"M35 affordance & onboarding green (%d checks)" % int(r.get("passed", 0)))

## M29 combat CAMERA: presentation-only framing brain — derived map-rect view clamp, combat reframe
## midpoint + gentle zoom-in, mouse-aim lookahead (reusing PlayerCombat.aim_dir), and the room-entry
## snap-fix flag. The full harness lives in tests/test_combat_camera.gd; its run_all() (pure math +
## the snap-state invariant, zero pixel motion) shares this suite's pass/fail totals. All visuals are
## LIVE-ONLY behind _is_live(), so the combat sim is untouched.
func _test_combat_camera() -> void:
	print("[M29 combat camera: view clamp, reframe midpoint+zoom, aim lookahead, room-entry snap fix]")
	var runner := load("res://tests/test_combat_camera.gd")
	var r: Dictionary = runner.run_all()
	_passed += int(r.get("passed", 0))
	_failed += int(r.get("failed", 0))
	_ok(int(r.get("failed", 1)) == 0 and int(r.get("passed", 0)) > 0,
		"M29 combat camera green (%d checks)" % int(r.get("passed", 0)))

## M31 — the PLAYER'S SPIRITUALITY (mana) POOL: a regenerating reservoir OWNED by the PlayerCombat node
## and enforced EXCLUSIVELY inside PlayerCombat.try_pay, giving the Hermit's star/ritual casts a real
## cadence (no dead-end). The full harness lives in tests/test_spirituality_pool.gd; its run_all() shares
## this suite's pass/fail totals (try_pay enforces + debits check-all-then-deduct; an empty-pool cast is
## refused 'no_spirit' burning NO cooldown; step_spirituality(dt) is a pure clamped regen; two green
## guards pin determinism — an enemy AgentCostProvider caster is NOT gated, and the Hunter kit + the
## spirit-costed set stay put so the pinned sims can't shift).
func _test_spirituality_pool() -> void:
	print("[M31 spirituality pool: PlayerCombat mana pool (enforce+debit+regen) — Hermit resource identity]")
	var runner := load("res://tests/test_spirituality_pool.gd")
	var r: Dictionary = runner.run_all()
	_passed += int(r.get("passed", 0))
	_failed += int(r.get("failed", 0))
	_ok(int(r.get("failed", 1)) == 0 and int(r.get("passed", 0)) > 0,
		"M31 spirituality pool green (%d checks)" % int(r.get("passed", 0)))

## M34 — the HERMIT'S LIVE COMBAT IDENTITY (the headline fix). The full harness lives in
## tests/test_hermit_primary.gd; its run_all() shares this suite's totals: driving the REAL primary-attack
## input, a Hermit-kitted player CASTS star_brand (spirit debited, no revolver round spent) and a Hunter
## still FIRES revolver_shot (ammo, no spirit) — the _primary_attack_id "player"-form short-circuit that
## made a live Hermit fire the loadout revolver is gone. Also pins the kit-aware melee floor (Hermit inert
## "", Hunter pistol_whip).
func _test_hermit_primary() -> void:
	print("[M34 hermit primary: the attack button is kit-aware — a live Hermit casts star_brand, a Hunter fires revolver_shot]")
	var runner := load("res://tests/test_hermit_primary.gd")
	var r: Dictionary = runner.run_all()
	_passed += int(r.get("passed", 0))
	_failed += int(r.get("failed", 0))
	_ok(int(r.get("failed", 1)) == 0 and int(r.get("passed", 0)) > 0,
		"M34 hermit primary green (%d checks)" % int(r.get("passed", 0)))

## M34 — the NO_SPIRIT CUE (the spirit counterpart to the M13 no_ammo cue). The full harness lives in
## tests/test_no_spirit_cue.gd; its run_all() shares this suite's totals: a drained Hermit casting the
## primary OR the charm emits a distinct spirit_empty event + pulses the HUD's OWN Spirit bar red (its own
## channel, never the ammo pulse or the hit-flash), the flash is hit_flash-gated but the EVENT always
## fires, and the two dry-resource cues never cross-fire.
func _test_no_spirit_cue() -> void:
	print("[M34 no_spirit cue: a drained Hermit cast pulses spirit_empty on its own channel (event ungated, flash gated)]")
	var runner := load("res://tests/test_no_spirit_cue.gd")
	var r: Dictionary = runner.run_all()
	_passed += int(r.get("passed", 0))
	_failed += int(r.get("failed", 0))
	_ok(int(r.get("failed", 1)) == 0 and int(r.get("passed", 0)) > 0,
		"M34 no_spirit cue green (%d checks)" % int(r.get("passed", 0)))

## M33 — the HERMIT SAVE->LOAD ROUNDTRIP (the Hermit counterpart to test_save_spend_seed's B3). The full
## harness lives in tests/test_hermit_save_load.gd; its run_all() shares this suite's pass/fail totals: a
## Hermit run advanced to Seq 7 (both ladder arts) + dirtied meters/leads/shop round-trips through the disk
## save (pathway=="hermit" + rung + granted arts + meters + leads + shop all survive), and the player's
## spirituality pool is proven INTENTIONALLY transient (not in the manifest; a fresh body re-inits to full).
func _test_hermit_save_load() -> void:
	print("[M33 hermit save/load: a Hermit run (Seq 7 + arts + meters + leads + shop) round-trips the disk save; spirituality transient]")
	var runner := load("res://tests/test_hermit_save_load.gd")
	var r: Dictionary = runner.run_all()
	_passed += int(r.get("passed", 0))
	_failed += int(r.get("failed", 0))
	_ok(int(r.get("failed", 1)) == 0 and int(r.get("passed", 0)) > 0,
		"M33 hermit save/load green (%d checks)" % int(r.get("passed", 0)))

## M33 — the HERMIT FULL-RUN INTEGRATION HARNESS (the Hermit counterpart to full_run.gd, which is
## Hunter-only). The full harness lives in tests/hermit_full_run.gd; its run_all() is a COROUTINE (mounts
## the real BootController to drive the New-Run pathway pick), so this wrapper AWAITS it and shares the
## suite's totals. Proves the WHOLE Hermit loop closes in ONE continuous run: pick Hermit at the New-Run
## picker -> hunt old_neil AND ledger_finch DOWN through real combat (two-phase descent live) -> harvest
## each drop off the ground -> digest via the LIVE advance verb -> climb Seq 9->8->7 (astral_chains,
## collapsing_star) -> reach a Ritual Night WIN (end_run once, no softlock).
func _test_hermit_full_run() -> void:
	print("[M33 hermit full-run: pick Hermit -> hunt neil+finch (real combat) -> harvest+digest -> Seq 9->8->7 -> Ritual Night win]")
	var runner := load("res://tests/hermit_full_run.gd")
	var r: Dictionary = await runner.run_all()
	_passed += int(r.get("passed", 0))
	_failed += int(r.get("failed", 0))
	_ok(int(r.get("failed", 1)) == 0 and int(r.get("passed", 0)) > 0,
		"M33 hermit full-run green (%d checks)" % int(r.get("passed", 0)))

## B1 (retro patch wave) — the LIVE GROUND-GATHER seam. The full harness lives in
## tests/test_ground_gather.gd; its run_all() is a COROUTINE (mounts a real Player body and lets the
## physics-frame walk-over pickup do the gathering), so this wrapper AWAITS it and shares the suite's
## totals: a downed Beyonder's dropped Characteristic is gathered by the LIVE walk-over seam (the
## items.json "gatherable" tag — data, not an engine list), digested via the live Interactable verb,
## sellable at the live counter for the authored coin, and the cult supply cache is stocked onto the
## city floor at run start by the LIVE RunManager placement (the dead CitySummoning path replaced).
func _test_ground_gather() -> void:
	print("[B1 ground gather: dropped Characteristics gathered by the LIVE walk-over seam; supply cache stocked at run start]")
	var runner := load("res://tests/test_ground_gather.gd")
	var r: Dictionary = await runner.run_all()
	_passed += int(r.get("passed", 0))
	_failed += int(r.get("failed", 0))
	_ok(int(r.get("failed", 1)) == 0 and int(r.get("passed", 0)) > 0,
		"B1 ground gather green (%d checks)" % int(r.get("passed", 0)))

func _ok(cond: bool, label: String) -> void:
	if cond:
		_passed += 1
		print("  PASS  %s" % label)
	else:
		_failed += 1
		printerr("  FAIL  %s" % label)

## Record a test that could not run in this environment (e.g. an external tool is
## absent). Visible in the output and the summary so an unrun check is never mistaken
## for a passing one, but does NOT fail the suite.
func _skip(label: String) -> void:
	_skipped += 1
	print("  SKIP  %s" % label)

func _test_clock_phases() -> void:
	print("[clock]")
	var Clk: Object = root.get_node("/root/Clock")
	_ok(Clk.phase_for_minute(0) == "late-night", "00:00 -> late-night")
	_ok(Clk.phase_for_minute(360) == "early-morning", "06:00 -> early-morning")
	_ok(Clk.phase_for_minute(540) == "morning", "09:00 -> morning")
	_ok(Clk.phase_for_minute(780) == "afternoon", "13:00 -> afternoon")
	_ok(Clk.phase_for_minute(1080) == "dusk", "18:00 -> dusk")
	_ok(Clk.phase_for_minute(1200) == "night", "20:00 -> night")
	_ok(Clk.phase_for_minute(1439) == "late-night", "23:59 -> late-night")

func _test_pressure_clamp_and_stability() -> void:
	print("[pressures]")
	var WS: Object = root.get_node("/root/WorldState")
	WS.set_pressure(&"corruption", 200.0)
	_ok(WS.get_pressure(&"corruption") == 100.0, "clamps high to 100")
	WS.set_pressure(&"corruption", -50.0)
	_ok(WS.get_pressure(&"corruption") == 0.0, "clamps low to 0")
	WS.set_pressure(&"corruption", 0.0)
	WS.set_pressure(&"panic", 0.0)
	WS.set_pressure(&"cult_readiness", 0.0)
	_ok(abs(WS.stability() - 100.0) < 0.01, "all-zero -> stability 100")
	WS.set_pressure(&"corruption", 100.0)
	_ok(abs(WS.stability() - 50.0) < 0.01, "corruption 100 -> stability 50")

func _test_world_manager_stages() -> void:
	print("[world manager]")
	var WM: Object = root.get_node("/root/WorldManager")
	var WS: Object = root.get_node("/root/WorldState")
	WM.from_dict({"seed_value": 12345})  # reset bookkeeping deterministically
	WM.current_stage_id = "disturbance"
	WM.refresh_count = 0
	WS.set_pressure(&"cult_readiness", 100.0)
	WM.force_advance_stage()
	_ok(WM.current_stage_id == "awakening", "force_advance from disturbance -> awakening")
	var before: int = WM.stage_index()
	WM.force_advance_stage()
	_ok(int(WM.stage_index()) == before + 1, "force_advance increments stage index")

func _test_seeded_slots_are_deterministic() -> void:
	print("[slots]")
	var WM: Object = root.get_node("/root/WorldManager")
	WM.from_dict({"seed_value": 999})
	WM._start_run(false)
	var first: Dictionary = WM.slots.duplicate(true)
	WM.from_dict({"seed_value": 999})
	WM._start_run(false)
	_ok(WM.slots == first, "same seed -> identical slot resolution")
	_ok(WM.slots.has("primary_ritual_site"), "primary_ritual_site resolved at world-start")

func _test_clue_collection() -> void:
	print("[clues]")
	var CD: Object = root.get_node("/root/ClueDB")
	CD.from_dict({})  # clear
	var ok: bool = CD.collect("antigonus_notebook")
	_ok(ok, "collect known clue returns true")
	_ok(not CD.collect("antigonus_notebook"), "double-collect returns false")
	_ok(CD.collected_count() == 1, "collected_count == 1")
	_ok(CD.unlocked_topics().size() > 0, "collecting unlocked at least one topic")

func _test_event_scoring() -> void:
	print("[events]")
	var EM: Object = root.get_node("/root/EventManager")
	_ok(EM.library.size() > 0, "event library loaded")
	# An always-eligible event (no conditions) should be pickable on a fresh count.
	EM._cooldowns.clear()
	var pick: Dictionary = EM._pick(0)
	_ok(not pick.is_empty(), "picks an eligible event at refresh 0")

func _test_save_load_roundtrip() -> void:
	print("[save/load]")
	var WS: Object = root.get_node("/root/WorldState")
	var SM: Object = root.get_node("/root/SaveManager")
	var CD: Object = root.get_node("/root/ClueDB")
	WS.set_pressure(&"panic", 42.0)
	CD.from_dict({})
	CD.collect("spent_revolver")
	var tmp := "user://test_save.json"
	_ok(SM.save_game(tmp), "save_game writes file")
	WS.set_pressure(&"panic", 7.0)
	CD.from_dict({})
	_ok(SM.load_game(tmp), "load_game reads file")
	_ok(abs(WS.get_pressure(&"panic") - 42.0) < 0.01, "panic restored to 42")
	_ok(CD.is_collected("spent_revolver"), "clue restored after load")
	DirAccess.remove_absolute(ProjectSettings.globalize_path(tmp))

func _test_clock_beats() -> void:
	print("[clock beats]")
	var Clk: Object = root.get_node("/root/Clock")
	Clk.minutes_per_beat = 15
	Clk.beat_index = 0
	Clk._beat_accum_minutes = 0
	var seen := {"n": 0}
	var cb := func(_bi: int, _d: int) -> void: seen["n"] += 1
	Clk.beat_ticked.connect(cb)
	Clk.advance_minutes(15)
	_ok(Clk.beat_index == 1, "15 minutes -> 1 beat")
	_ok(seen["n"] == 1, "beat_ticked emitted once")
	Clk.advance_minutes(30)
	_ok(Clk.beat_index == 3, "45 minutes total -> 3 beats")
	Clk.beat_ticked.disconnect(cb)

func _test_event_bus() -> void:
	print("[event bus]")
	var EB: Object = root.get_node("/root/EventBus")
	EB.clear()
	var ev: Dictionary = EB.emit_event("test_action", {"actor": "voss"})
	_ok(ev["type"] == "test_action", "event records its type")
	_ok(int(ev["seq"]) == 1, "first event seq is 1")
	_ok(EB.events().size() == 1, "one event logged")
	EB.emit_event("other", {})
	_ok(EB.events("test_action").size() == 1, "filter by type returns only matches")
	_ok(EB.latest(1).size() == 1, "latest(1) returns one event")

func _test_agent_fallback() -> void:
	print("[agent fallback]")
	var ND: Object = root.get_node("/root/NpcDB")
	var target: Vector2 = ND.waypoint_for("lamplighter_orin", "morning")
	var a: Agent = Agent.new("lamplighter_orin")
	a.position = Vector2.ZERO
	var before: float = a.distance_to(target)
	a.tick_fallback("morning", 100.0)
	var after: float = a.distance_to(target)
	_ok(after < before, "fallback step moves agent toward its waypoint")
	for _i in range(100):
		a.tick_fallback("morning", 100.0)
	_ok(a.position == target, "fallback converges onto the waypoint")
	a.remember("saw the player near the warehouse")
	_ok(a.short_memory.size() == 1, "remember() appends to short memory")

func _test_agent_downed_freeze() -> void:
	print("[agent downed freeze]")
	var a: Agent = Agent.new("lamplighter_orin")
	a.position = Vector2.ZERO
	# Upright, it steps toward its waypoint (waypoint is non-zero for orin/morning).
	a.tick_fallback("morning", 100.0)
	_ok(a.position != Vector2.ZERO, "an upright agent steps toward its waypoint")
	# Down it, then confirm it no longer drifts no matter how many beats pass.
	var resting: Vector2 = a.position
	a.downed = true
	for _i in range(50):
		a.tick_fallback("morning", 100.0)
	_ok(a.position == resting, "a downed agent does not move on tick")

func _test_agent_registry() -> void:
	print("[agent registry]")
	var AG: Object = root.get_node("/root/Agents")
	AG.rebuild()
	_ok(AG.get_agent("lamplighter_orin") != null, "registry builds a known agent")
	_ok(AG.all().size() >= 2, "registry holds at least the seeded npcs")
	var orin: Agent = AG.get_agent("lamplighter_orin")
	var near: Array = AG.active(orin.position, 1.0)
	_ok(near.has(orin), "active() finds an agent at its own position")
	var far: Array = AG.active(orin.position + Vector2(99999, 0), 1.0)
	_ok(not far.has(orin), "active() excludes agents outside the radius")

func _test_agent_thought() -> void:
	print("[agent thought]")
	var a := Agent.new("voss")
	a.intent = "Complete the warehouse summoning."
	_ok(a.describe_thought().length() > 0, "idle agent has a synthesized thought")
	a.current_action = {"verb": "move_to", "args": {"target": "warehouse"}}
	_ok("warehouse" in a.describe_thought(), "thought reflects the current move target")
	a.thought = "I sense I am being watched."
	_ok(a.describe_thought() == "I sense I am being watched.", "explicit thought overrides synthesis")
	var b := Agent.new()
	b.from_dict(a.to_dict())
	_ok(b.thought == a.thought, "thought round-trips through save")

func _test_agent_combat_state() -> void:
	print("[agent combat state]")
	var a := Agent.new("voss")
	_ok(a.hp == 100.0 and a.max_hp == 100.0, "new agent starts at full HP")
	_ok(a.downed == false, "new agent is not downed")
	a.take_damage(34.0)
	_ok(a.hp == 66.0, "take_damage subtracts flat damage from HP")
	_ok(a.downed == false, "an agent above 0 HP is not downed")
	a.take_damage(100.0)
	_ok(a.hp == 0.0, "HP clamps at 0 and never goes negative")
	_ok(a.downed == true, "an agent reduced to 0 HP is downed")
	a.take_damage(20.0)
	_ok(a.hp == 0.0, "further damage to a downed agent keeps HP at 0")
	var b := Agent.new()
	b.from_dict(a.to_dict())
	_ok(b.hp == 0.0 and b.downed == true, "hp and downed round-trip through save")

func _test_agent_inventory() -> void:
	print("[agent inventory]")
	var a := Agent.new("fishwife_dalia")
	_ok(a.item_count("ritual_salt") == 0, "a new agent carries nothing")
	a.add_item("ritual_salt", 2)
	_ok(a.item_count("ritual_salt") == 2, "add_item adds the given count")
	a.add_item("ritual_salt")
	_ok(a.item_count("ritual_salt") == 3, "add_item defaults to one and stacks")
	a.add_item("candle")
	_ok(a.item_count("candle") == 1, "a second item is tracked independently")
	var b := Agent.new()
	b.from_dict(a.to_dict())
	_ok(b.item_count("ritual_salt") == 3 and b.item_count("candle") == 1, "inventory round-trips through save")

func _test_cult_cell_seeded() -> void:
	print("[cult cell]")
	var ND: Object = root.get_node("/root/NpcDB")
	_ok((ND.get_def("clerk_voss").get("secrets", []) as Array).size() > 0, "voss has secrets it keeps hidden")
	_ok(ND.get_def("clerk_voss").get("role", "") == "leader", "voss is the leader")
	_ok(ND.get_def("dockhand_pell").get("role", "") == "victim", "pell is the victim")
	_ok(String(ND.get_def("lamplighter_orin").get("intent", "")) != "", "orin has an intent")
	_ok(String(ND.get_def("fishwife_dalia").get("role", "")) == "logistics", "dalia is logistics")

## The full 19-character cast (5 originals + 9 ordinary townsfolk + 5 hidden ones) hydrates into
## live Agents on rebuild. Ordinary folk are PUBLIC LAYER ONLY — empty secrets, no task; their
## allegiance/disposition lives in persona PROSE, never in a flag. Hidden characters carry
## secrets[] + goals[] but still NO task: they are not in the summoning cell's task loop — their
## menace is persona, surfaced behaviorally by the brain, not by the convergence machinery.
func _test_roster_hydration() -> void:
	print("[roster hydration]")
	var ND: Object = root.get_node("/root/NpcDB")
	var AG: Object = root.get_node("/root/Agents")
	AG.rebuild()
	# M14 added the THIRD adversary (leland_mack, the Seq-8 Hunter-pathway meal) as the 21st character.
	_ok(ND.defs.size() == 21, "npcs.json defines exactly 21 characters (got %d)" % ND.defs.size())
	var live := 0
	for a in AG.all():
		if String(a.id) != "player":
			live += 1
	_ok(live == 21, "all 21 defs hydrate into live agents (got %d)" % live)
	# Spot-check an ORDINARY townsfolk: public layer only.
	var hawker: Agent = AG.get_agent("hawker_neille")
	_ok(hawker != null and hawker.role == "hawker", "hawker_neille hydrates with its role")
	_ok(hawker.secrets.is_empty(), "an ordinary townsfolk has EMPTY secrets (public layer only)")
	_ok(hawker.task.is_empty(), "an ordinary townsfolk carries no task")
	_ok(hawker.tier == "light", "ordinary folk run on the light cognition tier")
	_ok(hawker.description != "" and hawker.voice != "" and hawker.knowledge.size() > 0,
		"hawker_neille carries persona prose (description/voice/knowledge)")
	# Spot-check a HIDDEN character: persona + secrets + prose goals, but NO task.
	var bram: Agent = AG.get_agent("bram_kell")
	_ok(bram != null and bram.role == "butcher", "bram_kell hydrates with its public-facing role")
	_ok(bram.secrets.size() > 0, "a hidden character carries secrets")
	_ok(bram.goals.size() > 0, "a hidden character carries prose goals")
	_ok(bram.task.is_empty(), "a hidden character has NO task — not in the summoning cell's loop")
	_ok(bram.tier == "full", "hidden characters run on the full cognition tier")
	# Rename guard: the roster doc's 'Old Neille' ships as hawker_neille so it can never be
	# confused with (or collide with) the alchemist old_neil.
	_ok(ND.defs.has("old_neil") and ND.defs.has("hawker_neille"),
		"old_neil and hawker_neille coexist as distinct ids")

func _test_substrate_save_load() -> void:
	print("[substrate save/load]")
	var EB: Object = root.get_node("/root/EventBus")
	var AG: Object = root.get_node("/root/Agents")
	var SM: Object = root.get_node("/root/SaveManager")
	AG.rebuild()
	EB.clear()
	EB.emit_event("seed_event", {"x": 1})
	AG.get_agent("clerk_voss").position = Vector2(123, 456)
	var tmp := "user://test_substrate.json"
	_ok(SM.save_game(tmp), "save_game writes file")
	EB.clear()
	AG.get_agent("clerk_voss").position = Vector2.ZERO
	_ok(SM.load_game(tmp), "load_game reads file")
	_ok(EB.events("seed_event").size() == 1, "event log restored after load")
	_ok(AG.get_agent("clerk_voss").position == Vector2(123, 456), "agent position restored")
	DirAccess.remove_absolute(ProjectSettings.globalize_path(tmp))

func _test_item_db() -> void:
	print("[item db]")
	var DB: Object = root.get_node("/root/ItemDB")
	_ok(DB.has_def("rye_bread"), "items.json loaded rye_bread")
	var d: ItemDef = DB.get_def("rye_bread")
	_ok(d != null, "get_def returns an ItemDef")
	_ok(d.category == "sustenance", "rye_bread is sustenance")
	_ok(d.stackable == true, "rye_bread is stackable")
	_ok(d.max_stack == 5, "rye_bread max_stack is 5")
	var pen: ItemDef = DB.get_def("spirit_pendulum")
	_ok(pen.stackable == false, "spirit_pendulum is not stackable")
	_ok(DB.get_def("does_not_exist") == null, "unknown id returns null")
	# Weapon/tool items: ammo is NOT a built-in pool — it rides the item system. The revolver
	# GRANTS revolver_shot and feeds on revolver_round; the cost seam resolves through here.
	var rev: ItemDef = DB.get_def("revolver")
	_ok(rev != null and rev.category == "weapon", "items.json carries the revolver (category 'weapon')")
	# The revolver grants revolver_shot AND the Hunter Seq-7 incendiary_round (M5 — the stronger
	# variant fires from the SAME service revolver, so the granted art is usable once unlocked).
	_ok(rev != null and rev.get("grants") is Array and (rev.get("grants") as Array).has("revolver_shot"),
		"the revolver grants revolver_shot")
	_ok(rev != null and (rev.get("grants") as Array).has("incendiary_round"),
		"the revolver also grants the Hunter Seq-7 incendiary_round (M5)")
	_ok(rev != null and str(rev.get("ammo_item")) == "revolver_round",
		"…and names revolver_round as its ammo_item")
	var rnd: ItemDef = DB.get_def("revolver_round")
	_ok(rnd != null and rnd.category == "ammo", "revolver_round is an 'ammo' item")
	_ok(DB.has_method("weapon_for_ability"), "ItemDB exposes weapon_for_ability(agent, ability_id)")
	if DB.has_method("weapon_for_ability"):
		var carrier := Agent.new("t_item_carrier")
		_ok((DB.weapon_for_ability(carrier, "revolver_shot") as Dictionary).is_empty(),
			"weapon_for_ability resolves {} when no granting weapon is carried")
		carrier.add_item("revolver", 1)
		var w: Dictionary = DB.weapon_for_ability(carrier, "revolver_shot")
		_ok(String(w.get("id", "")) == "revolver", "…and the carried revolver once held")
		_ok(String(w.get("ammo_item", "")) == "revolver_round", "…exposing its ammo_item")
		_ok((DB.weapon_for_ability(carrier, "cleaver_swipe") as Dictionary).is_empty(),
			"an ability no carried weapon grants resolves to {}")
		_ok((DB.weapon_for_ability(RefCounted.new(), "revolver_shot") as Dictionary).is_empty(),
			"an agent without item_count resolves to {} (duck-type guard, never a hard error)")

func _test_inventory_add_remove() -> void:
	print("[inventory add/remove]")
	var INV: Object = root.get_node("/root/Inventory")
	INV.clear()
	_ok(INV.add("candle", 3), "add 3 candles succeeds")
	_ok(INV.count_of("candle") == 3, "count is 3")
	_ok(INV.add("candle", 100) == false, "add past max_stack (9) is rejected")
	_ok(INV.count_of("candle") == 3, "count unchanged after rejected add")
	_ok(INV.add("spirit_pendulum"), "add non-stackable succeeds")
	_ok(INV.add("spirit_pendulum") == false, "second non-stackable add rejected (cap 1)")
	_ok(INV.has("candle", 3), "has(candle,3) true")
	_ok(INV.has("candle", 4) == false, "has(candle,4) false")
	_ok(INV.remove("candle", 2), "remove 2 candles succeeds")
	_ok(INV.count_of("candle") == 1, "count is 1 after remove")
	_ok(INV.remove("candle", 5) == false, "remove more than held is rejected")
	_ok(INV.count_of("candle") == 1, "count unchanged after rejected remove")

func _test_inventory_use() -> void:
	print("[inventory use]")
	var INV: Object = root.get_node("/root/Inventory")
	var WS: Object = root.get_node("/root/WorldState")
	INV.clear()
	WS.set_pressure(&"fatigue", 50.0)
	INV.add("rye_bread", 2)
	_ok(INV.use("rye_bread"), "use rye_bread succeeds")
	_ok(abs(WS.get_pressure(&"fatigue") - 38.0) < 0.01, "fatigue dropped by on_use delta (12)")
	_ok(INV.count_of("rye_bread") == 1, "consumable decremented by 1")
	# Non-consumable (no on_use): use does not decrement.
	INV.add("spirit_pendulum")
	_ok(INV.use("spirit_pendulum"), "use non-consumable returns true")
	_ok(INV.count_of("spirit_pendulum") == 1, "non-consumable not decremented")
	# Unknown effect: warns, no-ops, still treated as used (not consumed by default).
	INV.clear()
	_ok(INV.use("candle") == false, "use of unheld item returns false")

func _test_inventory_save_load() -> void:
	print("[inventory save/load]")
	var INV: Object = root.get_node("/root/Inventory")
	var SM: Object = root.get_node("/root/SaveManager")
	INV.clear()
	INV.add("candle", 4)
	INV.add("spirit_pendulum")
	var tmp := "user://test_inventory.json"
	_ok(SM.save_game(tmp), "save_game writes file")
	INV.clear()
	_ok(INV.count_of("candle") == 0, "inventory cleared before load")
	_ok(SM.load_game(tmp), "load_game reads file")
	_ok(INV.count_of("candle") == 4, "candle count restored")
	_ok(INV.has("spirit_pendulum"), "pendulum restored")
	DirAccess.remove_absolute(ProjectSettings.globalize_path(tmp))

func _test_action_schema() -> void:
	print("[action schema]")
	var ok := ActionSchema.validate({"actor": "voss", "verb": "move_to", "args": {"target": "iron_cross_warehouse"}})
	_ok(ok["ok"] == true, "valid move_to accepted")
	var no_verb := ActionSchema.validate({"actor": "voss", "verb": "teleport", "args": {}})
	_ok(no_verb["ok"] == false, "unknown verb rejected")
	var missing := ActionSchema.validate({"actor": "voss", "verb": "talk_to", "args": {"agent": "orin"}})
	_ok(missing["ok"] == false, "talk_to missing 'topic' rejected")
	var idle := ActionSchema.validate({"actor": "voss", "verb": "idle", "args": {}})
	_ok(idle["ok"] == true, "idle needs no args")
	var no_actor := ActionSchema.validate({"verb": "idle", "args": {}})
	_ok(no_actor["ok"] == false, "missing actor rejected")
	_ok(ActionSchema.is_verb("attack"), "attack is a known verb")
	_ok(not ActionSchema.is_verb("nope"), "nope is not a known verb")

func _test_mock_sidecar() -> void:
	print("[mock sidecar]")
	var mock := MockSidecar.new()
	mock.set_action("voss", {"actor": "voss", "verb": "move_to", "args": {"target": "iron_cross_warehouse"}})
	var snaps := [{"agent_id": "voss"}, {"agent_id": "orin"}]
	var out: Array = mock.propose(snaps)
	_ok(out.size() == 2, "one proposal per snapshot")
	_ok(out[0]["verb"] == "move_to", "scripted action returned for voss")
	_ok(out[1]["verb"] == "idle", "unscripted agent defaults to idle")
	_ok(out[1]["actor"] == "orin", "idle proposal is attributed to the right actor")
	# Queue support: pop one action per beat.
	mock.set_action("orin", [{"actor": "orin", "verb": "hide", "args": {}}])
	var out2: Array = mock.propose([{"agent_id": "orin"}])
	_ok(out2[0]["verb"] == "hide", "queued action consumed")
	var out3: Array = mock.propose([{"agent_id": "orin"}])
	_ok(out3[0]["verb"] == "idle", "empty queue falls back to idle")

func _parse_xy(s: String) -> Vector2:
	var p := s.split(",")
	return Vector2(float(p[0]), float(p[1]))

## Index of the first option whose label contains `needle`, or -1. Lets dialogue tests find a
## specific choice (e.g. "Persuade") without hard-coding option order.
func _option_index_with(options: Array, needle: String) -> int:
	for i in options.size():
		if needle in String((options[i] as Dictionary).get("label", "")):
			return i
	return -1

func _test_ambient_sidecar() -> void:
	print("[ambient sidecar]")
	var amb := AmbientSidecar.new()
	# Batch of two: a cultist drawn to the rite, a civilian on their daily round.
	var cult_snap := {"agent_id": "clerk_voss", "task": {"ritual": "summoning_descent"}, "position": [200.0, 200.0], "phase": "morning", "beat": 7}
	var civ_snap := {"agent_id": "fishwife_dalia", "position": [120.0, 120.0], "phase": "morning", "beat": 7}
	var out: Array = amb.propose([cult_snap, civ_snap])
	_ok(out.size() == 2, "one proposal per snapshot")
	_ok(out[0]["verb"] == "move_to", "ambient agents move — they never freeze on idle")
	_ok(ActionSchema.validate(out[0])["ok"], "cult proposal is schema-valid")
	_ok(ActionSchema.validate(out[1])["ok"], "civilian proposal is schema-valid")
	# Cultists converge on the warehouse: target lands within a scatter of the rite site.
	var cult_t: Vector2 = _parse_xy(out[0]["args"]["target"])
	_ok(cult_t.distance_to(AmbientSidecar.WAREHOUSE) <= AmbientSidecar.WANDER * 1.5, "cult target sits at the rite site")
	# Civilians follow their schedule: target lands near their phase waypoint.
	var ND: Object = root.get_node("/root/NpcDB")
	var wp: Vector2 = ND.waypoint_for("fishwife_dalia", "morning")
	var civ_t: Vector2 = _parse_xy(out[1]["args"]["target"])
	_ok(civ_t.distance_to(wp) <= AmbientSidecar.WANDER * 1.5, "civilian target follows the day's schedule")
	# Deterministic: identical snapshot -> identical proposal (pure function of inputs).
	var again: Array = amb.propose([cult_snap])
	_ok(again[0]["args"]["target"] == out[0]["args"]["target"], "same beat replays the same proposal")
	# A new beat re-scatters the goal so the crowd doesn't stand stock still — by a VISIBLE amount.
	# (String inequality alone once passed on rounding luck while the djb2-based scatter moved a
	# fixed 0.028px/beat; the md5 scatter must genuinely move the goal.)
	var later: Dictionary = cult_snap.duplicate()
	later["beat"] = 8
	var moved: Array = amb.propose([later])
	_ok(_parse_xy(moved[0]["args"]["target"]).distance_to(_parse_xy(out[0]["args"]["target"])) > 1.0,
		"a new beat re-scatters the goal by a visible amount")
	# Prayer adjudication is inherited from MockSidecar, so the live brain still answers prayers.
	var verdict: Dictionary = amb.adjudicate_prayer({"god": "outer_god", "prayer": "I humbly beseech you, grant mercy", "standing": 1.0})
	_ok(verdict.has("outcome"), "ambient brain still adjudicates prayers (inherited from mock)")

func _test_http_sidecar() -> void:
	print("[http sidecar]")
	var EB: Object = root.get_node("/root/EventBus")
	# URL parsing (pure/static) — host, port, and scheme.
	var u: Dictionary = HttpSidecar._split_url("http://127.0.0.1:8777")
	_ok(u["host"] == "127.0.0.1" and int(u["port"]) == 8777 and not bool(u["use_ssl"]), "parses host/port from an http url")
	var s: Dictionary = HttpSidecar._split_url("https://sidecar.example.com/propose")
	_ok(s["host"] == "sidecar.example.com" and int(s["port"]) == 443 and bool(s["use_ssl"]), "https defaults to 443 and strips the path")
	# Unconfigured (no URL): it IS the ambient brain — every agent moves, nothing networks.
	var off := HttpSidecar.new("")
	var out: Array = off.propose([{"agent_id": "clerk_voss", "task": {"ritual": "summoning_descent"}, "position": [200.0, 200.0], "phase": "morning", "beat": 3}])
	_ok(out.size() == 1 and out[0]["verb"] == "move_to", "unconfigured http sidecar falls back to ambient movement")
	# ...and conversation likewise degrades to the ambient offline dialogue, never to silence.
	var off_say: Dictionary = off.converse({"agent_id": "clerk_voss",
		"perception": {"display_name": "Voss"}, "utterance": "Cold night.", "history": []})
	_ok(String(off_say.get("say", "")) != "", "unconfigured http sidecar falls back to the ambient conversation")
	# Configured: a completed LLM reply is cached + logged; agents not yet heard from ambient-fill.
	var cli := HttpSidecar.new("http://127.0.0.1:8777")
	EB.clear()
	cli.apply_reply([{"actor": "clerk_voss", "verb": "hide", "args": {}}], "")
	_ok(EB.events("sidecar_proposed").size() == 1, "a valid LLM action is logged as sidecar_proposed")
	var picked: Array = cli.pick([
		{"agent_id": "clerk_voss", "task": {"ritual": "summoning_descent"}, "position": [200.0, 200.0], "phase": "morning", "beat": 3},
		{"agent_id": "fishwife_dalia", "position": [120.0, 120.0], "phase": "morning", "beat": 3}])
	_ok(picked[0]["verb"] == "hide", "the cached LLM action is served for that agent")
	_ok(picked[1]["verb"] == "move_to", "an agent with no LLM action yet ambient-fills (keeps moving)")
	# Invalid LLM actions are dropped (never cached) and surfaced as sidecar_error.
	EB.clear()
	cli.apply_reply([{"actor": "lamplighter_orin", "verb": "teleport", "args": {}}], "")
	_ok(EB.events("sidecar_error").size() == 1, "an invalid LLM action is logged as sidecar_error")
	var picked2: Array = cli.pick([{"agent_id": "lamplighter_orin", "task": {"ritual": "summoning_descent"}, "position": [300.0, 300.0], "phase": "morning", "beat": 4}])
	_ok(picked2[0]["verb"] == "move_to", "a rejected LLM action does not stick; the agent ambient-fills")
	# A transport failure is surfaced as sidecar_error too.
	EB.clear()
	cli.apply_reply([], "connect timeout")
	_ok(EB.events("sidecar_error").size() == 1, "a transport error is logged as sidecar_error")
	cli.shutdown()

func _test_brain_decide_request() -> void:
	print("[brain decide request]")
	# A snapshot shaped like Perception.build_snapshot, standing ON the crypt altar (in the crypt room).
	var snap := {
		"agent_id": "clerk_voss", "display_name": "Clerk Voss", "task": {"ritual": "summoning_descent"}, "role": "leader",
		"intent": "move to the crypt", "position": [691.0, 600.0], "room": "cathedral_crypt", "beat": 7,
		"short_memory": ["the bell tolled", "a Nighthawk watched the cathedral"], "mem_total": 2,
		"nearby": [{"id": "fishwife_dalia"}], "pressures": {"corruption": 10},
		# Goals come from the agent's DATA (forwarded by build_snapshot) — a flat tiered list (goals are goals).
		"goals": [
			{"description": "Gather the ritual offerings (ritual_salt, consecrated_chalk, candle) from the supply cache, carry them down to the cathedral crypt altar, and lay them there", "tier": "medium"},
			{"description": "Once the altar holds every offering, work the rite at the crypt altar to complete the summoning", "tier": "medium"},
			{"description": "Summon the descending god and escape mortality", "tier": "long"},
		],
	}
	# The whole current window is sent each beat, tagged with absolute seq; the brain dedups by seq.
	var r0: Dictionary = Perception.decide_request(snap, "sess1")
	_ok(r0["session_id"] == "sess1" and r0["agent_id"] == "clerk_voss" and int(r0["turn"]) == 7, "decide request carries session/agent/turn")
	_ok((r0["events"] as Array).size() == 2, "events = the full current short_memory window")
	# seq tagging: mem_total 2, 2 entries -> base_seq 0 -> seqs 0,1.
	_ok(int((r0["events"][0] as Dictionary)["seq"]) == 0 and int((r0["events"][1] as Dictionary)["seq"]) == 1, "events carry absolute seq ids derived from mem_total")
	var imp_by_text := {}
	for e in r0["events"]:
		imp_by_text[String(e["text"])] = float(e["importance"])
	_ok(imp_by_text["a Nighthawk watched the cathedral"] == 6.0, "occult/rite line scores importance 6")
	_ok(imp_by_text["the bell tolled"] == 3.0, "a plain line scores importance 3")
	# After the cap evicts old entries (mem_total 25, window still 2), seqs reflect TRUE absolute
	# position (23,24) — so the brain keeps receiving new observations in a long game (the #1 fix).
	var capped: Dictionary = snap.duplicate(true)
	capped["mem_total"] = 25
	var rc2: Dictionary = Perception.decide_request(capped, "sess1")
	_ok(int((rc2["events"][0] as Dictionary)["seq"]) == 23 and int((rc2["events"][1] as Dictionary)["seq"]) == 24, "post-cap window entries carry their true absolute seq (long-game fix)")
	# Goals are a flat tiered list from data (goals are goals — no public/secret split): two operational
	# mediums, the long aim, then the per-beat intent as a short goal.
	var goals: Array = r0["goals"]
	_ok(goals.size() == 4, "agent gets its 4 data goals (2 medium + long aim + short intent)")
	_ok((goals[0] as Dictionary)["tier"] == "medium", "first goal is gather→deliver (medium)")
	_ok((goals[1] as Dictionary)["tier"] == "medium", "second goal is working the rite (medium)")
	_ok((goals[2] as Dictionary)["tier"] == "long" and String((goals[2] as Dictionary)["description"]).contains("Summon"),
		"the long aim is a goal like any other — no secret flag")
	_ok(not (goals[2] as Dictionary).has("secret"), "goals carry no secret flag (goals are goals)")
	_ok((goals[3] as Dictionary)["tier"] == "short" and String((goals[3] as Dictionary)["description"]) == "move to the crypt", "short goal is the current intent")
	# world_state derived from position: standing on the crypt -> at a rite site.
	_ok(bool((r0["world_state"] as Dictionary)["actor_at_rite_site"]), "at the crypt -> world_state.actor_at_rite_site true")
	_ok(not bool((r0["world_state"] as Dictionary)["player_triggered"]), "player_triggered defaults false -> exposure is treated as incidental (AI-driven), so cult_secrecy can veto it")
	_ok((r0["perception"]["locations"] as Array).has("crypt_altar"), "locations include crypt_altar as a move target")
	# Non-cult agent far from any site: a single short goal, not on a rite site.
	var civ := {"agent_id": "dockhand_pell", "role": "", "intent": "go home",
		"position": [50000.0, 50000.0], "beat": 7, "short_memory": [], "mem_total": 0, "nearby": [], "pressures": {}}
	var rc: Dictionary = Perception.decide_request(civ, "sess1")
	_ok((rc["goals"] as Array).size() == 1 and (rc["goals"][0] as Dictionary)["tier"] == "short", "non-cult agent gets only its intent as a short goal")
	_ok(not bool((rc["world_state"] as Dictionary)["actor_at_rite_site"]), "far from any site -> not at rite site")

func _test_sidecar_bridge() -> void:
	print("[sidecar bridge]")
	var SB: Object = root.get_node("/root/SidecarBridge")
	_ok(SB.client != null, "bridge has a default client")
	var mock := MockSidecar.new()
	mock.set_action("voss", {"actor": "voss", "verb": "attack", "args": {"target": "pell"}})
	SB.set_client(mock)
	var out: Array = SB.propose([{"agent_id": "voss"}])
	_ok(out.size() == 1, "bridge routes one proposal")
	_ok(out[0]["verb"] == "attack", "bridge returns the active client's proposal")
	# Every proposal the bridge returns must be schema-valid for the mock to be useful.
	_ok(ActionSchema.validate(out[0])["ok"], "bridged proposal is schema-valid")

func _test_perception_snapshot() -> void:
	print("[perception]")
	var AG: Object = root.get_node("/root/Agents")
	var EB: Object = root.get_node("/root/EventBus")
	AG.rebuild()
	EB.clear()
	EB.emit_event("test_seed", {"x": 1})
	var voss: Agent = AG.get_agent("clerk_voss")
	var snap: Dictionary = Perception.build_snapshot(voss, voss.position)
	_ok(snap.get("agent_id", "") == "clerk_voss", "snapshot carries agent_id")
	_ok(snap.has("intent"), "snapshot includes intent")
	_ok(snap.has("position"), "snapshot includes position")
	_ok(snap.has("nearby"), "snapshot includes nearby agents")
	# recent_events was a dead payload: computed every beat, never forwarded to any brain. Peer
	# awareness rides the vision-gated Stimulus channel instead (a global event feed would leak
	# omnisciently past each agent's vision_r).
	_ok(not snap.has("recent_events"), "snapshot does NOT carry the dead recent_events payload")
	_ok(snap.has("stage"), "snapshot includes world stage")
	_ok(snap.has("pressures"), "snapshot includes pressures")
	# Another agent placed at voss's position should show up as nearby.
	var pell: Agent = AG.get_agent("dockhand_pell")
	pell.position = voss.position
	var snap2: Dictionary = Perception.build_snapshot(voss, voss.position)
	var nearby_ids: Array = []
	for n in snap2["nearby"]:
		nearby_ids.append(n["id"])
	_ok(nearby_ids.has("dockhand_pell"), "co-located agent appears in nearby")
	_ok(not nearby_ids.has("clerk_voss"), "agent does not list itself as nearby")

func _test_action_commit() -> void:
	print("[action commit]")
	var AG: Object = root.get_node("/root/Agents")
	AG.rebuild()
	var voss: Agent = AG.get_agent("clerk_voss")
	voss.position = Vector2.ZERO
	var site: Vector2 = ActionCommit.SITES["iron_cross_warehouse"]
	var before: float = voss.position.distance_to(site)
	var out: Dictionary = ActionCommit.commit(
		{"actor": "clerk_voss", "verb": "move_to", "args": {"target": "iron_cross_warehouse"}}, voss)
	_ok(out.has("moved_to"), "move_to reports a new position")
	_ok(voss.position.distance_to(site) < before, "agent moved toward the site")
	_ok(voss.current_action.get("verb", "") == "move_to", "current_action is recorded")
	# talk_to records memory, no movement.
	var pos_before: Vector2 = voss.position
	ActionCommit.commit({"actor": "clerk_voss", "verb": "talk_to", "args": {"agent": "lamplighter_orin", "topic": "ritual"}}, voss)
	_ok(voss.position == pos_before, "talk_to does not move the agent")
	_ok(voss.short_memory.size() >= 1, "talk_to records a memory")
	# move_to with an unresolved target is a safe no-op.
	var out2: Dictionary = ActionCommit.commit({"actor": "clerk_voss", "verb": "move_to", "args": {"target": "nowhere_xyz"}}, voss)
	_ok(out2.has("noop"), "unresolved move target is a no-op")
	# coordinate-string target resolves.
	ActionCommit.commit({"actor": "clerk_voss", "verb": "move_to", "args": {"target": "100,100"}}, voss)
	_ok(true, "coordinate target does not error")

func _test_coordinate_anchors_consistent() -> void:
	print("[coordinate anchors]")
	var site_world: Vector2 = MapProjection.map_to_world(MapProjection.WAREHOUSE_MAP)
	_ok(site_world.distance_to(Vector2(5366.65, 2378.09)) < 1.0,
		"rite site resolves to the live Warehouse cache ~(5366.65,2378.09)")
	_ok((ActionCommit.SITES["iron_cross_warehouse"] as Vector2).is_equal_approx(site_world),
		"ActionCommit.SITES rite == map_to_world(WAREHOUSE_MAP)")
	_ok(AmbientSidecar.WAREHOUSE.is_equal_approx(site_world),
		"AmbientSidecar.WAREHOUSE == map_to_world(WAREHOUSE_MAP)")

## Coordinate unification: every staged point the sim relies on (cult spawn SPOTS, cache items, the
## cache nav target, the rite anchor, npcs.json schedule waypoints) must be INSIDE the live
## City.tscn world and CLEAR of its building colliders. This is the contract that placements are
## authored in the live scene's space — the old 3.5-space put the rite anchor inside Blackthorn's
## collider, 3723px from the visual Warehouse, and the cult spawns inside the chapel nave wall.
func _test_city_scene_placements_legal() -> void:
	print("[city placements legal in the live scene]")
	var scene: Node = (load("res://scenes/City.tscn") as PackedScene).instantiate()
	# Added to the tree so global transforms resolve; freed synchronously below, BEFORE
	# CitySummoning's two-frame-deferred bootstrap can fire and mutate global demo state.
	root.add_child(scene)
	var colliders: Array = []
	_collect_rect_colliders(scene, colliders)
	_ok(colliders.size() >= 5, "the city has building colliders to test against (got %d)" % colliders.size())
	# Gather every staged point the sim relies on.
	var CS: GDScript = load("res://src/CitySummoning.gd")
	var points: Dictionary = {}
	for id in CS.SPOTS:
		points["spot:" + String(id)] = CS.SPOTS[id]
	for item in CS.CACHE_ITEMS:
		points["cache:" + String(item)] = CS.CACHE_ITEMS[item]
	points["cache_nav"] = CS.CACHE_NAV_POS
	points["site:iron_cross_warehouse"] = ActionCommit.SITES["iron_cross_warehouse"]
	# EVERY scheduled waypoint of the WHOLE roster (npcs.json is the source of truth, not a
	# hardcoded id list) — this is what catches a civilian's waypoint landing under a newly
	# placed building footprint.
	var npc_defs: Dictionary = JSON.parse_string(FileAccess.get_file_as_string("res://data/npcs.json"))
	for aid in npc_defs:
		var sched: Dictionary = (npc_defs[aid] as Dictionary).get("schedule", {})
		for ph in sched:
			var arr: Array = sched[ph]
			points["sched:%s:%s" % [aid, ph]] = Vector2(float(arr[0]), float(arr[1]))
	_ok(points.size() >= 12, "gathered the staged points (%d)" % points.size())
	var world_rect := Rect2(Vector2.ZERO, MapProjection.MAP_SIZE * MapProjection.CITY_SCALE)
	var out_of_bounds: Array = []
	var buried: Array = []
	for label in points:
		var pt: Vector2 = points[label]
		if not world_rect.has_point(pt):
			out_of_bounds.append(label)
		var hit := _point_in_any_collider(pt, colliders)
		if hit != "":
			buried.append("%s inside %s" % [label, hit])
	_ok(out_of_bounds.is_empty(), "every staged point is inside the live world " + str(out_of_bounds))
	_ok(buried.is_empty(), "no staged point is buried in a building collider " + str(buried))
	# The live-scene rite agreement (moved off the retired CityBlocks): the sabotage cache
	# interactable sits within rite range of the SITES anchor.
	var cache: Node2D = scene.get_node_or_null("Warehouse/RiteCache")
	_ok(cache != null, "the live city has the Warehouse/RiteCache sabotage interactable")
	if cache != null:
		_ok(cache.global_position.distance_to(ActionCommit.SITES["iron_cross_warehouse"]) \
			<= ActionCommit.RITE_RADIUS,
			"the sabotage cache sits within rite range of the SITES anchor")
	scene.free()   # synchronous, before CitySummoning's deferred bootstrap

## Collect every RectangleShape2D CollisionShape2D under a StaticBody2D (building bodies + edge
## walls; Area2D door triggers are NOT blockers and are skipped).
func _collect_rect_colliders(node: Node, out: Array) -> void:
	for c in node.get_children():
		if c is CollisionShape2D and (c as CollisionShape2D).shape is RectangleShape2D \
				and c.get_parent() is StaticBody2D:
			out.append(c)
		_collect_rect_colliders(c, out)

## The "Body/Shape" name of the first collider containing world-point p, or "" when clear.
func _point_in_any_collider(p: Vector2, colliders: Array) -> String:
	for c in colliders:
		var cs := c as CollisionShape2D
		var local: Vector2 = cs.global_transform.affine_inverse() * p
		var half: Vector2 = (cs.shape as RectangleShape2D).size * 0.5
		if absf(local.x) <= half.x and absf(local.y) <= half.y:
			return String(cs.get_parent().name) + "/" + String(cs.name)
	return ""

## Per-texture opaque bounding box, as FRACTIONS of the texture rect (x, y, w, h), precomputed
## with PIL (alpha > 16) because headless GDScript cannot decode the imported .ctex pixel data.
## Two special entries:
##   • chapel_test.png — the bbox of the CHURCH BUILDING itself (nave + tower, hand-measured px
##     330,55..870,765 of 1186x980): the canvas is a whole walled churchyard whose grounds are
##     deliberately walkable, so the footprint contract is against the building, not the yard.
##   • klein_house.png — the only sprite with transparent padding (px 42,46..932,981 of 1024²).
## Every other building sprite is tight-cropped: opaque bbox == full canvas.
const CITY_SPRITE_OPAQUE := {
	"chapel_test.png": Rect2(0.278246, 0.056122, 0.455312, 0.724490),
	"klein_house.png": Rect2(0.041016, 0.044922, 0.869141, 0.913086),
	"blackthorn.png": Rect2(0, 0, 1, 1),
	"university.png": Rect2(0, 0, 1, 1),
	"warehouse.png": Rect2(0, 0, 1, 1),
	"laughing_eel.png": Rect2(0, 0, 1, 1),
	"iron_cross_market.png": Rect2(0, 0, 1, 1),
	"raphael_cemetery.png": Rect2(0, 0, 1, 1),
	"selena_almshouse.png": Rect2(0, 0, 1, 1),
	"tingen_docks.png": Rect2(0, 0, 1, 1),
	"river_wharves.png": Rect2(0, 0, 1, 1),
	"police_station.png": Rect2(0, 0, 1, 1),
	"mr_frankys.png": Rect2(0, 0, 1, 1),
	"coal_yard.png": Rect2(0, 0, 1, 1),
	"ironworks.png": Rect2(0, 0, 1, 1),
	"globe_works.png": Rect2(0, 0, 1, 1),
	"rowhouse_a.png": Rect2(0, 0, 1, 1),
	"rowhouse_b.png": Rect2(0, 0, 1, 1),
	"rowhouse_c.png": Rect2(0, 0, 1, 1),
	# City density fill blocks (asset-gen/out_image2/buildings/fill pipeline): keyed by
	# key_building.py which autocrops to the opaque bbox, so full-rect like the others.
	"fill_01.png": Rect2(0, 0, 1, 1),
	"fill_02.png": Rect2(0, 0, 1, 1),
	"fill_03.png": Rect2(0, 0, 1, 1),
	"fill_04.png": Rect2(0, 0, 1, 1),
	"fill_05.png": Rect2(0, 0, 1, 1),
	"fill_06.png": Rect2(0, 0, 1, 1),
	"fill_07.png": Rect2(0, 0, 1, 1),
	"fill_08.png": Rect2(0, 0, 1, 1),
	"fill_09.png": Rect2(0, 0, 1, 1),
	"fill_10.png": Rect2(0, 0, 1, 1),
	"fill_11.png": Rect2(0, 0, 1, 1),
	"fill_12.png": Rect2(0, 0, 1, 1),
	"fill_13.png": Rect2(0, 0, 1, 1),
	"fill_14.png": Rect2(0, 0, 1, 1),
}

## City buildout contract: every building StaticBody2D in the live City.tscn has (i) real art (a
## textured Sprite2D), (ii) a FOOTPRINT collider — RectangleShape2D(s) whose summed world AABB
## covers 45–105% of the sprite's world opaque AABB (a base, not a sliver; not wildly bigger than
## the art either — iso roofs lean north, so the rect hugs the lower body of the sprite), and
## (iii) a UNIFORM body scale (2D physics does not support non-uniform collider scale). Also pins
## every door/portal/cache WORLD position so buildout refactors (e.g. moving a parent's scale onto
## its sprite) can never drift where the player enters buildings or spoils the rite cache.
func _test_city_buildings() -> void:
	print("[city buildings: art + footprint colliders + door pins]")
	var scene: Node = (load("res://scenes/City.tscn") as PackedScene).instantiate()
	# Freed synchronously below, before CitySummoning's deferred bootstrap fires (same pattern as
	# _test_city_scene_placements_legal).
	root.add_child(scene)
	_ok((scene as Node2D).y_sort_enabled, "City root y-sorts walkers against buildings")
	var bodies: Array = []
	for c in scene.get_children():
		if c is StaticBody2D and String(c.name) != "Ground":   # Ground = terrain slab + edge walls
			bodies.append(c)
	_ok(bodies.size() >= 19, "the city has at least 19 building bodies (got %d)" % bodies.size())
	for body in bodies:
		var b := body as StaticBody2D
		var bn := String(b.name)
		_ok(is_equal_approx(b.scale.x, b.scale.y), "%s body scale is uniform (%s)" % [bn, str(b.scale)])
		var sprite: Sprite2D = null
		for ch in b.get_children():
			if ch is Sprite2D:
				sprite = ch
		_ok(sprite != null and sprite.texture != null, "%s has a textured Sprite2D" % bn)
		if sprite == null or sprite.texture == null:
			continue
		var tex_file: String = sprite.texture.resource_path.get_file()
		_ok(CITY_SPRITE_OPAQUE.has(tex_file), "%s texture '%s' has a precomputed opaque bbox" % [bn, tex_file])
		if not CITY_SPRITE_OPAQUE.has(tex_file):
			continue
		var ts: Vector2 = sprite.texture.get_size()
		var fr: Rect2 = CITY_SPRITE_OPAQUE[tex_file]
		var top_left: Vector2 = sprite.offset - (ts * 0.5 if sprite.centered else Vector2.ZERO)
		var opaque_local := Rect2(top_left + Vector2(fr.position.x * ts.x, fr.position.y * ts.y),
			Vector2(fr.size.x * ts.x, fr.size.y * ts.y))
		var s_aabb := _world_aabb(sprite.get_global_transform(), opaque_local)
		var covered := 0.0
		var rects := 0
		for ch in b.get_children():
			if ch is CollisionShape2D and (ch as CollisionShape2D).shape is RectangleShape2D:
				rects += 1
				var cs := ch as CollisionShape2D
				var size: Vector2 = (cs.shape as RectangleShape2D).size
				var c_aabb := _world_aabb(cs.get_global_transform(), Rect2(size * -0.5, size))
				covered += c_aabb.size.x * c_aabb.size.y
		_ok(rects >= 1, "%s has a RectangleShape2D footprint collider" % bn)
		if rects == 0:
			continue
		var ratio: float = covered / (s_aabb.size.x * s_aabb.size.y)
		_ok(ratio >= 0.45 and ratio <= 1.05,
			"%s collider covers its footprint (%.1f%% of opaque AABB, want 45-105%%)" % [bn, ratio * 100.0])
	# Door/portal + cache world-position pins (values read from the pre-buildout scene).
	var pins := {
		"Chapel/ChapelDoor": Vector2(1959, 5257),
		"Chapel/ChapelDoor/DoorShape": Vector2(2172.5, 5284.5),
		"Blackthorn/HQDoor": Vector2(1586, 2224),
		"NeilHomeDoor": Vector2(2700, 3600),
		"University/UniversityDoor": Vector2(2979.1178, 1579.0782),
		"KleinHouse/KleinHouseDoor": Vector2(3070, 2655),
		"Warehouse/RiteCache": Vector2(5366.6548, 2378.0856),
	}
	for path in pins:
		var node: Node2D = scene.get_node_or_null(NodePath(path))
		_ok(node != null, "City has %s" % path)
		if node != null:
			_ok(node.global_position.distance_to(pins[path]) < 0.5,
				"%s world position pinned at %s (got %s)" % [path, str(pins[path]), str(node.global_position)])
	# The NeilHome twin (rowhouse_a) gives the once-floating NeilHomeDoor a building; the door
	# Area2D itself must stay a direct City child (test_neil_home.gd walks root children for it).
	var neil: Node = scene.get_node_or_null("NeilHome")
	_ok(neil is StaticBody2D, "NeilHome building houses the NeilHomeDoor portal")
	# The nighthawk_warning clue: a street interactable at Blackthorn's south side opening the
	# 'nighthawk' dialogue (its dialogue effects collect clue 'nighthawk_warning' — the reference
	# configuration lives in the retired CityBlocks.tscn 'Nighthawk' node).
	var hawk: Node = scene.get_node_or_null("Nighthawk")
	_ok(hawk is Area2D and String(hawk.get("dialogue_id")) == "nighthawk",
		"Nighthawk interactable offers the clue-granting 'nighthawk' dialogue")
	scene.free()   # synchronous, before CitySummoning's deferred bootstrap

## Axis-aligned world bounds of a local rect under a Transform2D (rotation/scale aware).
func _world_aabb(t: Transform2D, local: Rect2) -> Rect2:
	var out := Rect2(t * local.position, Vector2.ZERO)
	out = out.expand(t * (local.position + Vector2(local.size.x, 0)))
	out = out.expand(t * (local.position + Vector2(0, local.size.y)))
	out = out.expand(t * (local.position + local.size))
	return out

func _test_city_layout() -> void:
	print("[city layout loader]")
	var sample := {
		"city_outline": [0, 0, 100, 0, 100, 100, 0, 100],
		"water": [[80, 0, 100, 0, 100, 50, 80, 50]],
		"blocks": [[10, 10, 30, 10, 30, 30, 10, 30], [40, 40, 60, 40, 60, 60, 40, 60]],
		"landmarks": [{ "pos": [50, 50], "label": "Test Site" }],
	}
	var layout := CityLayout.from_dict(sample)
	_ok(layout.outline().size() == 4, "outline parsed to 4 vertices")
	_ok(layout.water().size() == 1, "one water polygon parsed")
	_ok(layout.blocks().size() == 2, "two block polygons parsed")
	# Transform correctness: a known map vertex comes back xCITY_SCALE in world space (expressed
	# via the constant so the layout loader always agrees with the global projection).
	_ok(layout.outline()[1].is_equal_approx(Vector2(100.0, 0.0) * MapProjection.CITY_SCALE),
		"map (100,0) -> world (100,0) x CITY_SCALE")
	_ok((layout.landmarks()[0]["pos"] as Vector2).is_equal_approx(Vector2(50.0, 50.0) * MapProjection.CITY_SCALE),
		"landmark map (50,50) -> world (50,50) x CITY_SCALE")
	_ok(String(layout.landmarks()[0]["label"]) == "Test Site", "landmark label preserved")

func _test_city_layout_data() -> void:
	print("[city layout data integrity]")
	var path := "res://data/city_layout.json"
	_ok(FileAccess.file_exists(path), "city_layout.json exists")
	var data: Variant = JSON.parse_string(FileAccess.get_file_as_string(path))
	_ok(typeof(data) == TYPE_DICTIONARY, "city_layout.json parses to a Dictionary")
	var d: Dictionary = data
	_ok((d.get("blocks", []) as Array).size() >= 20, "at least 20 building blocks (a real city, not mega-blocks)")
	# Every coordinate list is even-length and inside the map bounds (0,0)-(1000,706).
	var all_polys: Array = []
	all_polys.append(d.get("city_outline", []))
	for w in d.get("water", []): all_polys.append(w)
	for b in d.get("blocks", []): all_polys.append(b)
	var clean := true
	for poly in all_polys:
		if (poly as Array).size() % 2 != 0 or (poly as Array).size() < 6:
			clean = false
		for i in range((poly as Array).size()):
			var v := float(poly[i])
			var bound := 1000.0 if i % 2 == 0 else 706.0
			if v < 0.0 or v > bound:
				clean = false
	_ok(clean, "all outline/water/block vertices are even-length and within map bounds")

## SUPERSEDED by _test_city_scene_placements_legal (coordinate unification): schedule waypoints are
## now authored in the LIVE City.tscn space and validated against the actual scene colliders there.
## This test's old body validated them against data/city_layout.json — polygons authored for the
## RETIRED procedural map (tingen_map.png space), which no longer describes the live painted city.
## What survives here is the layout data's own internal contract; a water-aware walkability check
## returns when city_layout.json is re-authored for map_v3 (city buildout task).
func _test_npc_waypoints_walkable() -> void:
	print("[npc waypoints walkable — superseded; see city placements legal]")
	var raw: Variant = JSON.parse_string(FileAccess.get_file_as_string("res://data/npcs.json"))
	var npcs: Dictionary = raw
	var world_rect := Rect2(Vector2.ZERO, MapProjection.MAP_SIZE * MapProjection.CITY_SCALE)
	for npc_id in npcs:
		var sched: Dictionary = (npcs[npc_id] as Dictionary).get("schedule", {})
		for phase in sched:
			var arr: Array = sched[phase]
			var wp := Vector2(float(arr[0]), float(arr[1]))
			_ok(world_rect.has_point(wp), "%s/%s waypoint is inside the live world" % [npc_id, phase])

## Every npcs.json schedule waypoint lands INSIDE the playable rect and OUTSIDE the five EXISTING
## buildings. The AABBs are hardcoded, conservatively padded envelopes of the City.tscn colliders:
##   Chapel/cathedral (2118,5015):     x 1900-2290, y 4600-5414 (nave+tower; collider reach y<=5414)
##   Blackthorn Security (1677,1648):  x 1183-2171, y 1183-2114
##   University (2947,1020):           x 2415-3479, y  586-1454
##   KleinHouse (3070,2171):           x 2692-3448, y 1786-2556
##   Warehouse (5397,1875):            x 4965-5829, y 1479-2271
## This is the fast data-side guard; the merged city-scene legality test validates every staged
## point against the LIVE scene colliders (including the new venue buildings the city buildout adds).
func _test_roster_waypoints_legal() -> void:
	print("[roster schedule waypoints legal]")
	var aabbs := {
		"chapel": Rect2(1900, 4600, 390, 814),
		"blackthorn": Rect2(1183, 1183, 988, 931),
		"university": Rect2(2415, 586, 1064, 868),
		"kleinhouse": Rect2(2692, 1786, 756, 770),
		"warehouse": Rect2(4965, 1479, 864, 792),
	}
	# The playable band: inside the 60px edge walls on all four sides of the 6270x6270 city.
	var playable := Rect2(60, 60, 6150, 6150)
	var raw: Variant = JSON.parse_string(FileAccess.get_file_as_string("res://data/npcs.json"))
	var npcs: Dictionary = raw
	var bad: Array = []
	var checked := 0
	for npc_id in npcs:
		var sched: Dictionary = (npcs[npc_id] as Dictionary).get("schedule", {})
		for phase in sched:
			var arr: Array = sched[phase]
			var wp := Vector2(float(arr[0]), float(arr[1]))
			checked += 1
			if not playable.has_point(wp):
				bad.append("%s/%s outside the playable rect" % [npc_id, phase])
			for b in aabbs:
				if (aabbs[b] as Rect2).has_point(wp):
					bad.append("%s/%s buried in %s" % [npc_id, phase, b])
	_ok(checked >= 80, "the roster carries a real schedule spread (%d waypoints)" % checked)
	_ok(bad.is_empty(), "every waypoint is in-world and outside the existing buildings " + str(bad))
	# old_neil used to have NO schedule and spawned at the origin; he now resolves real waypoints.
	var db: Object = root.get_node("/root/NpcDB")
	_ok((npcs["old_neil"] as Dictionary).has("schedule"), "old_neil has a schedule (no longer spawns at (0,0))")
	_ok(db.waypoint_for("old_neil", "morning") != Vector2.ZERO, "old_neil resolves a morning waypoint")
	_ok(db.waypoint_for("old_neil", "late-night") != Vector2.ZERO, "a sparse phase falls back to a defined waypoint")

## NavigationServer2D commits region changes on a physics-frame boundary, so a single fixed sleep
## after map_force_update is racy under the headless test loop (occasionally an empty path). Force-
## update and step real frames until the map returns a path, or a small budget runs out — usually
## one iteration, never flaky.
func _await_nav_path(map: RID, from: Vector2, to: Vector2) -> PackedVector2Array:
	var path := PackedVector2Array()
	for _i in range(20):
		NavigationServer2D.map_force_update(map)
		await create_timer(0.02).timeout
		path = NavigationServer2D.map_get_path(map, from, to, true)
		if path.size() >= 2:
			break
	return path

func _test_navmesh_routing() -> void:
	print("[navmesh routing]")
	# A 400x400 walkable square with a 120x120 block dead center.
	var outline := PackedVector2Array([Vector2(0, 0), Vector2(400, 0), Vector2(400, 400), Vector2(0, 400)])
	var hole := PackedVector2Array([Vector2(140, 140), Vector2(260, 140), Vector2(260, 260), Vector2(140, 260)])
	var nav := CityLayout.build_nav_polygon(outline, [hole])
	_ok(nav.get_polygon_count() > 0, "baked navigation polygon has polygons")
	# Stand up a standalone nav map, attach a region, and query a path that must pass the block.
	var map := NavigationServer2D.map_create()
	NavigationServer2D.map_set_active(map, true)
	# Align the map's cell size with the NavigationPolygon bake default (1.0) so the region's
	# polygons register cleanly. If a path is unexpectedly empty, this is the first knob to check.
	NavigationServer2D.map_set_cell_size(map, 1.0)
	var region := NavigationServer2D.region_create()
	NavigationServer2D.region_set_map(region, map)
	NavigationServer2D.region_set_navigation_polygon(region, nav)
	var path := await _await_nav_path(map, Vector2(20, 200), Vector2(380, 200))
	_ok(path.size() >= 2, "a path exists across the square")
	_ok(path.size() >= 3, "the path bends around the central block (has an intermediate waypoint)")
	var inside_block := false
	for p in path:
		if p.x > 140.0 and p.x < 260.0 and p.y > 140.0 and p.y < 260.0:
			inside_block = true
	_ok(not inside_block, "no path point lies inside the block")
	NavigationServer2D.free_rid(region)
	NavigationServer2D.free_rid(map)

func _test_commit_sets_thought() -> void:
	print("[commit thought]")
	var a := Agent.new("voss")
	ActionCommit.commit({"actor": "voss", "verb": "idle", "args": {}, "thought": "All proceeds as foreseen."}, a)
	_ok(a.describe_thought() == "All proceeds as foreseen.", "commit stores the action's thought")
	ActionCommit.commit({"actor": "voss", "verb": "move_to", "args": {"target": "iron_cross_warehouse"}}, a)
	_ok(a.thought == "", "an action without a thought clears the stored one")
	_ok(a.describe_thought().length() > 0, "describe_thought() falls back to synthesis")

func _test_action_attack() -> void:
	print("[action attack]")
	var AG: Object = root.get_node("/root/Agents")
	var EB: Object = root.get_node("/root/EventBus")
	AG.rebuild()
	var voss: Agent = AG.get_agent("clerk_voss")
	var pell: Agent = AG.get_agent("dockhand_pell")
	# A strike within reach connects, damages the target, and logs the blow.
	voss.position = Vector2(400, 300)
	pell.position = Vector2(410, 300)   # inside ATTACK_RADIUS
	pell.hp = 100.0
	pell.downed = false
	EB.clear()
	var out: Dictionary = ActionCommit.commit(
		{"actor": "clerk_voss", "verb": "attack", "args": {"target": "dockhand_pell"}}, voss)
	_ok(out.get("hit", false) == true, "a strike in reach connects")
	_ok(pell.hp < 100.0, "the target loses HP")
	_ok(EB.events("agent_attacked").size() == 1, "an agent_attacked event is logged")
	_ok(EB.events("agent_attacked")[0]["data"]["target"] == "dockhand_pell", "the event names the target")
	# A swing from out of reach is flavor only — no damage, no event.
	pell.position = Vector2(2000, 2000)
	var hp_before: float = pell.hp
	EB.clear()
	var out_far: Dictionary = ActionCommit.commit(
		{"actor": "clerk_voss", "verb": "attack", "args": {"target": "dockhand_pell"}}, voss)
	_ok(out_far.get("hit", false) == false, "a strike out of reach does not connect")
	_ok(pell.hp == hp_before, "an out-of-reach target takes no damage")
	_ok(EB.events("agent_attacked").is_empty(), "no event for an out-of-reach swing")
	# Enough strikes fell the target and log a downed event exactly once.
	pell.position = Vector2(410, 300)
	pell.hp = 100.0
	pell.downed = false
	EB.clear()
	for _i in range(5):
		ActionCommit.commit({"actor": "clerk_voss", "verb": "attack", "args": {"target": "dockhand_pell"}}, voss)
	_ok(pell.downed == true, "enough strikes fell the target")
	_ok(pell.hp == 0.0, "a felled target sits at 0 HP")
	_ok(EB.events("agent_downed").size() == 1, "the target is reported downed exactly once")
	# An unknown target is a safe no-op.
	var out_unknown: Dictionary = ActionCommit.commit(
		{"actor": "clerk_voss", "verb": "attack", "args": {"target": "nobody"}}, voss)
	_ok(out_unknown.get("hit", false) == false, "attacking an unknown target is a no-op")

func _test_action_adopt_drop_goal() -> void:
	print("[action adopt/drop goal]")
	var AG: Object = root.get_node("/root/Agents")
	AG.rebuild()
	var orin: Agent = AG.get_agent("lamplighter_orin")
	# adopt_goal records a new goal the agent now carries (agent-sandbox AdoptGoal precedent) — the
	# engine-side of goal-changing dialogue. The outcome reports it before we touch any agent state.
	var out: Dictionary = ActionCommit.commit(
		{"actor": "lamplighter_orin", "verb": "adopt_goal", "args": {"goal": "Help the investigator stop the rite"}}, orin)
	_ok(out.get("adopted", "") == "Help the investigator stop the rite", "adopt_goal reports the adopted goal")
	_ok(orin.has_adopted_goal("Help the investigator stop the rite"), "the goal lands in the agent's adopted_goals")
	# Adopting the same goal twice does not duplicate it.
	ActionCommit.commit({"actor": "lamplighter_orin", "verb": "adopt_goal", "args": {"goal": "Help the investigator stop the rite"}}, orin)
	_ok(orin.adopted_goals.size() == 1, "adopting the same goal twice does not duplicate")
	# drop_goal removes a held goal and reports it.
	var d: Dictionary = ActionCommit.commit(
		{"actor": "lamplighter_orin", "verb": "drop_goal", "args": {"goal": "Help the investigator stop the rite"}}, orin)
	_ok(d.get("dropped", "") == "Help the investigator stop the rite", "drop_goal reports the dropped goal")
	_ok(orin.adopted_goals.is_empty(), "the goal is removed from adopted_goals")
	# Dropping a goal not held is a safe no-op.
	var d2: Dictionary = ActionCommit.commit(
		{"actor": "lamplighter_orin", "verb": "drop_goal", "args": {"goal": "nonexistent"}}, orin)
	_ok(d2.get("dropped", "") == "" and orin.adopted_goals.is_empty(), "dropping an unheld goal is a no-op")
	# Adopted goals persist across save/load — each is a {"text","kind"} entry.
	orin.adopted_goals = [{"text": "Lie low", "kind": "other"}]
	var snap: Dictionary = orin.to_dict()
	var fresh := Agent.new("lamplighter_orin")
	fresh.from_dict(snap)
	_ok(fresh.adopted_goals == [{"text": "Lie low", "kind": "other"}], "adopted_goals round-trips through to_dict/from_dict")

func _test_converse_seam() -> void:
	print("[converse seam: DialogueManager.send_utterance -> LLM]")
	var AG: Object = root.get_node("/root/Agents")
	var DM: Object = root.get_node("/root/DialogueManager")
	var SB: Object = root.get_node("/root/SidecarBridge")
	AG.rebuild()
	var orin: Agent = AG.get_agent("lamplighter_orin")
	orin.adopted_goals.clear()
	# A scripted converse reply: Orin is persuaded — he speaks AND adopts a defection goal.
	var mock := MockSidecar.new()
	mock.set_converse("lamplighter_orin", {
		"say": "You're right. I can't carry their lamp another night.",
		"action": {"verb": "adopt_goal", "args": {"goal": "Help the investigator stop the rite"}},
		"replies": [{"id": "ok", "text": "Then let's go — now."}],
	})
	SB.set_client(mock)
	var captured: Dictionary = {"speaker": "", "text": "", "options": []}
	var cb := func(sp, tx, opts):
		captured["speaker"] = sp
		captured["text"] = tx
		captured["options"] = opts
	DM.node_changed.connect(cb)
	DM.send_utterance("lamplighter_orin", "You don't have to go through with this.")
	DM.flush_converse()   # GAP-2.3: converse is async now — join the worker + apply the reply
	DM.node_changed.disconnect(cb)
	_ok(captured["text"] == "You're right. I can't carry their lamp another night.",
		"the NPC's spoken line is emitted through node_changed")
	_ok((captured["options"] as Array).size() == 1, "the suggested replies are emitted as options")
	_ok(orin.has_adopted_goal("Help the investigator stop the rite"),
		"the approved adopt_goal is applied to the agent")
	_ok(orin.has_adopted_goal("Help the investigator stop the cell"), "persuading the waverer adopts a defection goal (turned) via social_influence")
	_ok(DM.active == true, "the conversation stays active after a turn")
	# A non-waverer adopting a goal does NOT stop concealing (social_influence self-gates on role).
	var voss: Agent = AG.get_agent("clerk_voss")
	mock.set_converse("clerk_voss", {"say": "Never.", "action": {"verb": "adopt_goal", "args": {"goal": "rest"}}, "replies": []})
	DM.send_utterance("clerk_voss", "Give it up.")
	DM.flush_converse()
	_ok(not voss.has_adopted_goal("Help the investigator stop the cell"), "a non-waverer is not turned by adopt_goal")
	DM._end()
	SB.set_client(MockSidecar.new())

func _test_dialogue_panel_hybrid() -> void:
	print("[dialogue panel: hybrid chips + free-text]")
	var DM: Object = root.get_node("/root/DialogueManager")
	var SB: Object = root.get_node("/root/SidecarBridge")
	var AG: Object = root.get_node("/root/Agents")
	AG.rebuild()
	var mock := MockSidecar.new()
	mock.set_converse("lamplighter_orin", {"say": "Keep your voice down.", "action": null,
		"replies": [{"id": "a", "text": "What are they planning?"}, {"id": "b", "text": "Help me stop them."}]})
	SB.set_client(mock)
	var panel: Control = load("res://ui/DialoguePanel.tscn").instantiate()
	root.add_child(panel)
	await process_frame
	DM.open("lamplighter_orin")   # opening turn -> mock reply -> node_changed -> panel renders
	DM.flush_converse()           # GAP-2.3: join the async converse worker + apply its reply now
	await process_frame
	_ok(panel.visible, "panel becomes visible on open")
	var options: VBoxContainer = panel.get_node("Box/Margin/Body/Options")
	_ok(options.get_child_count() == 3, "renders 2 reply chips + a leave chip")
	_ok((options.get_child(0) as Button).text.ends_with("What are they planning?"), "first chip carries the reply text")
	_ok((options.get_child(2) as Button).text == "(Leave)", "the last chip is the leave exit")
	_ok(panel.get_node("Box/Margin/Body/InputRow/Input") is LineEdit, "a free-text input exists")
	_ok((panel.get_node("Box/Margin/Body/Text") as Label).text == "Keep your voice down.", "the NPC's say renders")
	# Free-text submit routes through send_utterance (mock replies again -> options rebuilt).
	var input: LineEdit = panel.get_node("Box/Margin/Body/InputRow/Input")
	input.text = "I can protect you."
	panel._on_send_pressed()
	DM.flush_converse()
	await process_frame
	_ok(options.get_child_count() == 3, "free-text submit routes through send_utterance and re-renders")
	_ok(panel._hotkey_count == 2, "two reply chips are hotkey-eligible; the (Leave) chip is not")
	# A non-dict reply element is skipped, not crashed (latent-crash guard).
	DM.node_changed.emit("Orin the Lamplighter", "Hm?", [{"text": "A"}, "junk-string", {"text": "B"}])
	await process_frame
	_ok(options.get_child_count() == 3, "a non-dict reply element is skipped (2 chips + leave, no crash)")
	_ok(panel._hotkey_count == 2, "hotkey count counts only the valid reply chips")
	DM._end()
	_ok(not panel.visible, "panel hides when the conversation ends")
	panel.queue_free()
	SB.set_client(MockSidecar.new())

func _short_mem_has(agent: Agent, substr: String) -> bool:
	for m in agent.short_memory:
		if String(m).to_lower().contains(substr.to_lower()):
			return true
	return false

func _test_model_config() -> void:
	print("[model config: per-agent model selection]")
	var MC: Object = root.get_node("/root/ModelConfig")
	var saved_default: String = MC.default_model
	var saved_overrides: Dictionary = MC.overrides.duplicate()
	MC.overrides = {}
	MC.default_model = "claude-sonnet-4-6"
	_ok(MC.model_for("clerk_voss") == "claude-sonnet-4-6", "model_for falls back to the GM/default with no override")
	MC.set_override("clerk_voss", "claude-opus-4-8")
	_ok(MC.model_for("clerk_voss") == "claude-opus-4-8", "set_override makes model_for return the override")
	_ok(MC.model_for("dockhand_pell") == "claude-sonnet-4-6", "an un-overridden agent still follows the default")
	MC.set_override("clerk_voss", "default")
	_ok(MC.model_for("clerk_voss") == "claude-sonnet-4-6", "override 'default' clears it -> back to the GM model")
	MC.set_default("not-a-model")
	_ok(MC.default_model == "claude-sonnet-4-6", "set_default ignores an unknown model")
	MC.set_default("claude-haiku-4-5")
	_ok(MC.default_model == "claude-haiku-4-5", "set_default accepts a known model")
	MC.default_model = saved_default
	MC.overrides = saved_overrides

func _test_perception_stimulus() -> void:
	print("[perception stimulus: neutral facts into agent memory]")
	var AG: Object = root.get_node("/root/Agents")
	var WS: Object = root.get_node("/root/WorldState")
	var EB: Object = root.get_node("/root/EventBus")
	AG.rebuild()
	AG.ensure_player_proxy(Vector2.ZERO, "cathedral_crypt")
	# Witnesses stand within their vision_r of the events below (perception is same-room AND
	# within the witness's own vision radius — see the [vision:] tests for the gating itself).
	var voss: Agent = AG.get_agent("clerk_voss"); voss.room = "cathedral_crypt"; voss.position = Vector2(50, 0); voss.short_memory.clear()
	var dalia: Agent = AG.get_agent("fishwife_dalia"); dalia.room = "cathedral_crypt"; dalia.position = Vector2(100, 0); dalia.short_memory.clear()
	var pell: Agent = AG.get_agent("dockhand_pell"); pell.room = "city"; pell.position = Vector2.ZERO; pell.short_memory.clear()
	# Player entered the crypt -> agents IN the crypt with the doorway in sight perceive it as a
	# neutral fact; agents in other rooms don't (even at close local coords).
	WS.room_changed.emit("cathedral_crypt", "res://scenes/CathedralCrypt.tscn")
	_ok(_short_mem_has(voss, "entered"), "an agent in the entered room (within vision) perceives the player entering")
	_ok(not _short_mem_has(pell, "entered"), "an agent in another room does not perceive it")
	_ok(not _short_mem_has(voss, "attack"), "the entry stimulus is a neutral FACT, never a scripted reaction")
	# Combat: a struck cultist perceives the blow; a cultist with the victim in sight witnesses a downing.
	voss.short_memory.clear(); dalia.short_memory.clear()
	EB.emit_event("agent_attacked", {"actor": "clerk_voss", "target": "fishwife_dalia", "damage": 34})
	_ok(_short_mem_has(dalia, "struck"), "the struck cultist perceives the blow")
	voss.short_memory.clear()
	# Vision, NOT faction: a non-cult agent watching from the same room also perceives the downing.
	var neil: Agent = AG.get_agent("old_neil"); neil.room = "cathedral_crypt"; neil.position = Vector2(150, 0); neil.short_memory.clear()
	EB.emit_event("agent_downed", {"actor": "x", "target": "fishwife_dalia"})
	_ok(_short_mem_has(voss, "struck down"), "a cultist with the victim in sight perceives an ally struck down")
	_ok(_short_mem_has(neil, "struck down"), "a NON-cult agent with the victim in sight also perceives the downing (vision, not faction)")

## The ids in an agent's perception `nearby` roster (Perception._nearby helper for the vision tests).
func _nearby_ids(agent: Agent) -> Array:
	var out: Array = []
	for n in Perception._nearby(agent):
		out.append(String((n as Dictionary).get("id", "")))
	return out

## Per-agent vision radius (agent-sandbox port): vision_r is per-agent DATA gating which same-room
## peers enter `nearby`. Rooms are separate scenes with LOCAL coordinate spaces, so an agent in
## another room is NEVER nearby — however close its local coords coincidentally are.
func _test_vision_nearby_gating() -> void:
	print("[vision: nearby gated by room + the viewer's vision_r]")
	var AG: Object = root.get_node("/root/Agents")
	AG.rebuild()
	var voss: Agent = AG.get_agent("clerk_voss")
	var pell: Agent = AG.get_agent("dockhand_pell")
	voss.room = "city"
	voss.position = Vector2(400, 300)
	# Same room + within the viewer's vision_r -> in nearby.
	pell.room = "city"
	pell.position = Vector2(500, 300)   # d = 100 <= 160
	_ok(_nearby_ids(voss).has("dockhand_pell"), "same room + within vision_r -> in nearby")
	# Same room + beyond the viewer's vision_r -> excluded.
	pell.position = Vector2(400.0 + voss.vision_r + 1.0, 300)
	_ok(not _nearby_ids(voss).has("dockhand_pell"), "same room + beyond vision_r -> excluded")
	# REGRESSION: two agents at IDENTICAL local coords in different rooms are NOT near each other —
	# a cross-room distance compares unrelated local spaces (the false-positive this port fixes).
	pell.room = "cathedral_nave"
	pell.position = voss.position
	_ok(not _nearby_ids(voss).has("dockhand_pell"),
		"identical local coords, city vs cathedral_nave -> not in the city agent's nearby")
	_ok(not _nearby_ids(pell).has("clerk_voss"),
		"identical local coords, city vs cathedral_nave -> not in the nave agent's nearby either")

## vision_r is data: hydrated from a def's optional "vision_r" on rebuild, defaulting to
## Perception.DEFAULT_VISION_R when absent, and round-tripping through save.
func _test_vision_r_data_and_roundtrip() -> void:
	print("[vision: vision_r is per-agent data]")
	var AG: Object = root.get_node("/root/Agents")
	var ND: Object = root.get_node("/root/NpcDB")
	_ok(is_equal_approx(Perception.DEFAULT_VISION_R, 160.0), "the default vision radius is 160 (absorbs NEARBY_RADIUS)")
	# An npcs.json def MAY carry "vision_r" — rebuild hydrates it; a def without one gets the default.
	ND.defs["test_dim_watcher"] = {"name": "Dim Watcher", "vision_r": 40}
	AG.rebuild()
	_ok(is_equal_approx(AG.get_agent("test_dim_watcher").vision_r, 40.0), "a def with vision_r: 40 hydrates onto the agent")
	_ok(is_equal_approx(AG.get_agent("clerk_voss").vision_r, 160.0), "a def without vision_r gets the 160 default")
	ND.defs.erase("test_dim_watcher")
	AG.rebuild()   # leave the registry clean for later tests
	# vision_r round-trips through to_dict/from_dict; a save without it keeps the default.
	var a := Agent.new("x")
	a.vision_r = 42.0
	var b := Agent.new("x")
	b.from_dict(a.to_dict())
	_ok(is_equal_approx(b.vision_r, 42.0), "vision_r round-trips through to_dict/from_dict")
	var c := Agent.new("y")
	c.from_dict({"id": "y"})
	_ok(is_equal_approx(c.vision_r, 160.0), "a save without vision_r keeps the default")

## Stimulus fan-out is perceiver-centric: an event reaches a witness's memory only when the witness
## is in the SAME ROOM and within its OWN vision_r of where the event happened. The direct victim
## of a blow ALWAYS perceives it — a strike on your body is felt, not seen.
func _test_vision_stimulus_gating() -> void:
	print("[vision: stimulus fan-out gated by each witness's own vision_r]")
	var AG: Object = root.get_node("/root/Agents")
	var EB: Object = root.get_node("/root/EventBus")
	AG.rebuild()
	var dalia: Agent = AG.get_agent("fishwife_dalia")   # the victim
	var voss: Agent = AG.get_agent("clerk_voss")        # near witness
	var neil: Agent = AG.get_agent("old_neil")          # far witness, same room
	var pell: Agent = AG.get_agent("dockhand_pell")     # other room, identical local coords
	dalia.room = "cathedral_crypt"
	dalia.position = Vector2(600, 400)
	dalia.short_memory.clear()
	voss.room = "cathedral_crypt"
	voss.position = Vector2(650, 400)   # d = 50, within voss's 160
	voss.short_memory.clear()
	neil.room = "cathedral_crypt"
	neil.position = Vector2(600.0 + neil.vision_r + 400.0, 400)   # same room, beyond neil's vision
	neil.short_memory.clear()
	pell.room = "city"
	pell.position = dalia.position   # identical LOCAL coords, different room
	pell.short_memory.clear()
	EB.emit_event("agent_attacked", {"actor": "x", "target": "fishwife_dalia", "damage": 34})
	_ok(_short_mem_has(dalia, "struck"), "the victim always perceives the blow")
	_ok(_short_mem_has(voss, "struck"), "a same-room witness within its vision_r of the victim perceives it")
	_ok(not _short_mem_has(neil, "struck"), "a same-room witness beyond its vision_r does not")
	_ok(not _short_mem_has(pell, "struck"), "an other-room agent never perceives it (even at identical local coords)")
	# Radius is per-agent DATA: two witnesses at the SAME distance from the SAME event see differently
	# because each is gated by its OWN vision_r.
	voss.short_memory.clear()
	neil.short_memory.clear()
	voss.vision_r = 200.0
	voss.position = Vector2(750, 400)   # d = 150 <= 200 -> sees
	neil.vision_r = 100.0
	neil.position = Vector2(450, 400)   # d = 150 >  100 -> blind to it
	EB.emit_event("agent_downed", {"actor": "x", "target": "fishwife_dalia"})
	_ok(_short_mem_has(voss, "struck down"), "a keen witness (vision_r 200) at d=150 sees the downing")
	_ok(not _short_mem_has(neil, "struck down"), "a dim witness (vision_r 100) at the same d=150 does not")
	AG.rebuild()   # restore default vision_r/rooms for later tests

## Companion fix (same bug class as cross-room nearby): attack and talk are same-room gated —
## positions in two different rooms live in unrelated local spaces, so a cross-room blow or talk
## fails exactly like an out-of-reach one.
func _test_action_cross_room_guard() -> void:
	print("[action: cross-room attack/talk fails]")
	var AG: Object = root.get_node("/root/Agents")
	var EB: Object = root.get_node("/root/EventBus")
	AG.rebuild()
	var voss: Agent = AG.get_agent("clerk_voss")
	var pell: Agent = AG.get_agent("dockhand_pell")
	var orin: Agent = AG.get_agent("lamplighter_orin")
	voss.room = "city"
	voss.position = Vector2(400, 300)
	# Attack: the target stands at coincidentally-close LOCAL coords in another room.
	pell.room = "cathedral_crypt"
	pell.position = Vector2(410, 300)
	pell.hp = 100.0
	pell.downed = false
	EB.clear()
	var out: Dictionary = ActionCommit.commit(
		{"actor": "clerk_voss", "verb": "attack", "args": {"target": "dockhand_pell"}}, voss)
	_ok(out.get("hit", false) == false, "a cross-room strike does not connect")
	_ok(pell.hp == 100.0, "a cross-room target takes no damage")
	_ok(EB.events("agent_attacked").is_empty(), "no agent_attacked event across rooms")
	# Talk: the listener stands at coincidentally-close LOCAL coords in another room.
	voss.short_memory.clear()
	voss.remember("saw the player prowling the harbor")
	orin.room = "cathedral_nave"
	orin.position = Vector2(410, 300)
	orin.short_memory.clear()
	EB.clear()
	var t: Dictionary = ActionCommit.commit(
		{"actor": "clerk_voss", "verb": "talk_to", "args": {"agent": "lamplighter_orin", "topic": "the player"}}, voss)
	_ok(t.get("shared", false) == false, "a cross-room talk does not carry")
	_ok(orin.short_memory.is_empty(), "no rumor lands across rooms")
	_ok(EB.events("rumor_spread").is_empty(), "no rumor_spread event across rooms")

func _test_player_proxy_and_combat() -> void:
	print("[player proxy + full combat + bad ending]")
	var AG: Object = root.get_node("/root/Agents")
	var ART: Object = root.get_node("/root/AgentRuntime")
	var EG: Object = root.get_node("/root/EndGame")
	AG.rebuild()
	var p: Agent = AG.ensure_player_proxy(Vector2(100, 100), "city")
	_ok(p != null and p.id == "player", "ensure_player_proxy registers a 'player' agent")
	_ok(p.deliberates == false and p.role == "investigator", "the proxy is a non-deliberating 'investigator' agent")
	# The runtime never deliberates the proxy, even when the player is right next to it.
	ART.player_position = p.position
	var active_ids: Array = []
	for a in ART._active_agents():
		active_ids.append(a.id)
	_ok(not active_ids.has("player"), "the runtime never deliberates the player proxy")
	# The proxy shows up in another agent's perception (the cult can SEE the player).
	var voss: Agent = AG.get_agent("clerk_voss")
	voss.room = "city"
	voss.position = Vector2(120, 100)
	var snap: Dictionary = Perception.build_snapshot(voss, voss.position)
	var nearby_ids: Array = []
	for n in snap["nearby"]:
		nearby_ids.append(String((n as Dictionary).get("id", "")))
	_ok(nearby_ids.has("player"), "the player proxy appears in a nearby agent's perception")
	# attack target="player" resolves + damages the proxy (full combat reuses _attack).
	voss.position = p.position
	var hp_before: float = p.hp
	ActionCommit.commit({"actor": "clerk_voss", "verb": "attack", "args": {"target": "player"}}, voss)
	_ok(p.hp < hp_before, "a cultist can attack the player proxy")
	# Downing the player fires the dedicated bad ending.
	var ended: Dictionary = {"n": 0, "outcome": ""}
	var cb := func(o, _r):
		ended["n"] += 1
		ended["outcome"] = o
	EG.ending_reached.connect(cb)
	for i in 5:
		ActionCommit.commit({"actor": "clerk_voss", "verb": "attack", "args": {"target": "player"}}, voss)
	_ok(p.downed, "enough strikes down the player")
	_ok(ended["n"] == 1 and String(ended["outcome"]) == "player_downed",
		"downing the player triggers the player_downed bad ending")
	# Terminal + latched: a repeat agent_downed{player} does NOT re-fire the ending.
	root.get_node("/root/EventBus").emit_event("agent_downed", {"actor": "x", "target": "player"})
	_ok(ended["n"] == 1, "player_downed is terminal — fires once, not again on a repeat down")
	# The ephemeral proxy is never persisted (it is re-created from the live player each frame).
	_ok(not ((AG.to_dict()["agents"]) as Dictionary).has("player"), "the player proxy is not saved")
	EG.ending_reached.disconnect(cb)
	EG.restart()
	paused = false   # the bad ending paused the tree (SceneTree.paused); clear it for later tests

func _test_ambient_converse() -> void:
	print("[ambient converse fallback (offline default)]")
	var amb := AmbientSidecar.new()
	var r: Dictionary = amb.converse({"agent_id": "lamplighter_orin",
		"perception": {"display_name": "Orin the Lamplighter", "task": {"ritual": "summoning_descent"}}})
	_ok(String(r.get("say", "")) != "", "offline ambient converse returns a non-empty say (no dead panel)")
	_ok((r.get("replies", []) as Array).size() >= 1, "offline ambient converse offers reply chips")
	var r2: Dictionary = amb.converse({"agent_id": "x",
		"perception": {"display_name": "Pell"}})
	_ok(String(r2.get("say", "")) != "", "a civilian also speaks in the offline build")
	# The offline reply must DEPEND on the player's utterance and VARY by turn — it must never read as a
	# single frozen greeting (the reported "typing does nothing" bug). Same agent, two different lines on
	# two different turns proves the panel would advance.
	var t0: Dictionary = amb.converse({"agent_id": "lamplighter_orin",
		"perception": {"display_name": "Orin"}, "utterance": "What happened at the warehouse?", "history": []})
	var t1: Dictionary = amb.converse({"agent_id": "lamplighter_orin",
		"perception": {"display_name": "Orin"}, "utterance": "Who else was there?",
		"history": ["Player: What happened at the warehouse?", "Orin: ..."]})
	_ok(String(t0.get("say", "")) != String(t1.get("say", "")),
		"offline converse varies by turn — successive sends are not the same frozen line")
	_ok(String(t0.get("say", "")).contains("warehouse"),
		"offline converse echoes the player's utterance (it depends on what was typed)")

## A send must ALWAYS advance the conversation: given an utterance, send_utterance surfaces a non-empty
## response (a spoken `say` and/or reply chips) through node_changed. Driven via MockSidecar scripted
## converse so it is deterministic and offline. This is the regression guard for "typing does nothing."
func _test_send_utterance_advances() -> void:
	print("[send_utterance advances the conversation]")
	var AG: Object = root.get_node("/root/Agents")
	var DM: Object = root.get_node("/root/DialogueManager")
	var SB: Object = root.get_node("/root/SidecarBridge")
	var EB: Object = root.get_node("/root/EventBus")
	AG.rebuild()
	var mock := MockSidecar.new()
	mock.set_converse("lamplighter_orin", {
		"say": "The lamps were already lit when I got there.",
		"action": null,
		"replies": [{"id": "more", "text": "And then?"}],
	})
	SB.set_client(mock)
	# Capture the node_changed payload the panel renders, and the npc_said log-hook event.
	var captured: Dictionary = {"say": "", "replies": [], "fired": false}
	var cb := func(_sp, tx, opts):
		captured["say"] = tx
		captured["replies"] = opts
		captured["fired"] = true
	DM.node_changed.connect(cb)
	var heard: Dictionary = {"agent": "", "text": "", "fired": false}
	var ecb := func(ev: Dictionary):
		if String(ev.get("type", "")) == "npc_said":
			var d: Dictionary = ev.get("data", {})
			heard["agent"] = String(d.get("agent", ""))
			heard["text"] = String(d.get("text", ""))
			heard["fired"] = true
	EB.event_logged.connect(ecb)
	DM.send_utterance("lamplighter_orin", "Tell me what you saw.")
	DM.flush_converse()   # GAP-2.3: converse is async — join the worker + apply the reply
	DM.node_changed.disconnect(cb)
	EB.event_logged.disconnect(ecb)
	_ok(captured["fired"], "send_utterance re-renders the panel (node_changed fires)")
	_ok(String(captured["say"]) != "" or (captured["replies"] as Array).size() > 0,
		"send_utterance yields a non-empty response (say or replies) — the conversation advances")
	_ok(String(captured["say"]) == "The lamps were already lit when I got there.",
		"the NPC's scripted line reaches the panel")
	_ok(heard["fired"] and String(heard["text"]) == "The lamps were already lit when I got there.",
		"npc_said fires with the resolved say")
	_ok(String(heard["agent"]) == "lamplighter_orin", "npc_said carries the npc id under 'agent'")
	DM._end()
	SB.set_client(MockSidecar.new())

## GAP-2.3 de-freeze: send_utterance must NOT block the main thread on the LLM round-trip. It kicks a
## worker (main thread stamps context first), returns immediately, and the reply lands later via a
## signal. This exercises (a) non-blocking send, (b) the reply applied on the main thread leaving
## 'thinking' state, (c) timeout/error → a graceful fallback line (no hang/crash), (d) an instant
## offline client still works, (e) the secrecy payload is unchanged.
func _test_dialogue_async() -> void:
	print("[dialogue async: send_utterance never blocks the main thread]")
	var AG: Object = root.get_node("/root/Agents")
	var DM: Object = root.get_node("/root/DialogueManager")
	var SB: Object = root.get_node("/root/SidecarBridge")
	AG.rebuild()

	# (a) NON-BLOCKING: a mock that BLOCKS 250ms in converse. If send_utterance ran the round-trip on
	# the main thread, the call would take >= 250ms; on a worker it returns in well under that.
	var slow := _SlowMockSidecar.new()
	slow.delay_ms = 250
	slow.set_converse("lamplighter_orin", {
		"say": "The lamps were lit before I arrived.", "action": null,
		"replies": [{"id": "more", "text": "And then?"}],
	})
	SB.set_client(slow)
	var got: Dictionary = {"say": "", "replies": [], "fired": false}
	var cb := func(_sp, tx, opts):
		got["say"] = tx; got["replies"] = opts; got["fired"] = true
	DM.node_changed.connect(cb)
	var t0 := Time.get_ticks_msec()
	DM.send_utterance("lamplighter_orin", "Tell me what you saw.")
	var elapsed := Time.get_ticks_msec() - t0
	_ok(elapsed < 200, "send_utterance returns immediately (%dms) — the 250ms round-trip did NOT block the caller" % elapsed)
	_ok(DM.is_converse_pending(), "the conversation is in a pending ('thinking') state right after send")
	_ok(not got["fired"], "the reply has NOT arrived yet (it is still in flight on the worker)")
	# The reply lands later. flush_converse joins the worker + applies the reply on the main thread.
	DM.flush_converse()
	_ok(got["fired"], "the reply lands via node_changed after the worker completes")
	_ok(String(got["say"]) == "The lamps were lit before I arrived.", "the async reply carries the NPC's line")
	_ok((got["replies"] as Array).size() == 1, "the async reply carries the suggested replies")
	_ok(not DM.is_converse_pending(), "the panel leaves 'thinking' state once the reply is applied")

	# (c) TIMEOUT/ERROR → graceful in-fiction fallback, not a hang or a crash. An empty say + no
	# replies is the transport-failure shape (HttpSidecar returns {say:"", action:null, replies:[]}
	# on any error). The manager must surface a non-empty fallback line and leave 'thinking' cleanly.
	got["say"] = ""; got["replies"] = []; got["fired"] = false   # mutate in place — the lambda captured THIS dict
	slow.set_converse("lamplighter_orin", {"say": "", "action": null, "replies": []})
	DM.send_utterance("lamplighter_orin", "Are you still there?")
	DM.flush_converse()
	_ok(got["fired"], "an errored/empty round-trip still re-renders the panel (no silent hang)")
	_ok(String(got["say"]) != "", "an errored/empty reply yields a graceful in-fiction fallback line, not blank")
	# Pin the EXACT fallback string (finding #3): a future accidental non-empty leak (e.g. echoing the
	# utterance) must not sneak past a mere non-empty check.
	_ok(String(got["say"]) == String(DM._FALLBACK_SAY), "the fallback line is exactly _FALLBACK_SAY, not some other non-empty leak")
	_ok(not DM.is_converse_pending(), "the panel leaves 'thinking' state after a fallback")

	# (d) OFFLINE / INSTANT client: an AmbientSidecar returns instantly (no real thread work). The
	# async wrapper must still deliver the reply without deadlock.
	got["say"] = ""; got["replies"] = []; got["fired"] = false   # mutate in place (see the lambda-capture gotcha)
	SB.set_client(AmbientSidecar.new())
	DM.send_utterance("lamplighter_orin", "What happened at the warehouse?")
	DM.flush_converse()
	_ok(got["fired"] and String(got["say"]) != "", "an instant offline client still delivers a reply through the async path (no deadlock)")
	_ok(not DM.is_converse_pending(), "the instant-client path also leaves 'thinking' state cleared (finding #3)")

	# (f) LEAVE-AND-RESWITCH during a slow live call (GAP-2.3 finding #1): the player leaves NPC-A while
	# its slow worker is still running, then immediately opens a NEW conversation. The new turn must NOT
	# be silently dropped — cancel_converse() in _end() must free the bridge so the reswitch proceeds.
	got["say"] = ""; got["replies"] = []; got["fired"] = false
	var slow2 := _SlowMockSidecar.new()
	slow2.delay_ms = 250
	slow2.set_converse("lamplighter_orin", {"say": "A-line (should be dropped).", "action": null, "replies": []})
	slow2.set_converse("clerk_voss", {"say": "B-line (must arrive).", "action": null, "replies": []})
	SB.set_client(slow2)
	DM.send_utterance("lamplighter_orin", "First question.")   # NPC-A worker starts (slow, in flight)
	_ok(DM.is_converse_pending(), "NPC-A turn is in flight (thinking)")
	DM._end()                                                  # player leaves while A's worker still runs
	_ok(not DM.is_converse_pending(), "leaving clears the pending state immediately")
	DM.send_utterance("clerk_voss", "Second question.")       # immediate reswitch to NPC-B
	_ok(DM.is_converse_pending(), "the reswitched NPC-B turn is accepted, NOT silently dropped (finding #1)")
	DM.flush_converse()
	_ok(got["fired"], "NPC-B's reply lands after the reswitch (no lost turn)")
	_ok(String(got["say"]) == "B-line (must arrive).", "the delivered reply is NPC-B's, and A's stale reply was dropped")
	_ok(not DM.is_converse_pending(), "the panel leaves 'thinking' after the reswitched reply")
	DM._end()
	DM.node_changed.disconnect(cb)

	# (e) SECRECY payload unchanged: the request the async path builds carries the SAME fields as the
	# synchronous path did — secrets ride converse behind the revealed gate. Capture what the client
	# actually received.
	var spy := _SlowMockSidecar.new()
	spy.delay_ms = 0
	spy.set_converse("lamplighter_orin", {"say": "…", "action": null, "replies": []})
	SB.set_client(spy)
	DM.send_utterance("lamplighter_orin", "Who else was there?")
	DM.flush_converse()
	var sent: Dictionary = spy.last_converse_request
	_ok(String(sent.get("utterance", "")) == "Who else was there?", "the utterance is forwarded unchanged")
	_ok(String(sent.get("speaker", "")) == "player", "speaker=player is preserved on the async path")
	_ok((sent.get("perception", {}) as Dictionary).has("secrets"), "secrets still ride converse (revealed gate intact)")
	_ok(bool((sent.get("world_state", {}) as Dictionary).get("player_triggered", false)), "player_triggered still set on the async path")
	DM._end()
	SB.set_client(MockSidecar.new())

func _test_converse_action_gating() -> void:
	print("[converse action gating: schema + Critic; say always survives]")
	var AG: Object = root.get_node("/root/Agents")
	var DM: Object = root.get_node("/root/DialogueManager")
	var SB: Object = root.get_node("/root/SidecarBridge")
	var SP: Object = root.get_node("/root/SummoningPlan")
	AG.rebuild()
	var mock := MockSidecar.new()
	SB.set_client(mock)
	var pell: Agent = AG.get_agent("dockhand_pell")   # role "victim"
	var got: Dictionary = {"say": ""}
	var cb := func(_sp, tx, _opts): got["say"] = tx
	DM.node_changed.connect(cb)
	# A victim "performing the rite" is Critic-vetoed → not committed → but he still SPEAKS.
	mock.set_converse("dockhand_pell", {"say": "I just want to go home.",
		"action": {"verb": "perform_ritual_step", "args": {"step": "x"}}, "replies": []})
	var cd_before: int = SP.countdown_beats
	DM.send_utterance("dockhand_pell", "Are you one of them?")
	DM.flush_converse()
	_ok(got["say"] == "I just want to go home.", "the say survives a Critic-vetoed action")
	_ok(SP.countdown_beats == cd_before, "a Critic-vetoed converse action is not committed")
	# A malformed `args` does not crash; the action is schema-rejected and dropped, the say survives.
	got["say"] = ""
	pell.adopted_goals.clear()
	mock.set_converse("dockhand_pell", {"say": "Weather's turning.",
		"action": {"verb": "adopt_goal", "args": "not-a-dict"}, "replies": []})
	DM.send_utterance("dockhand_pell", "...")
	DM.flush_converse()
	_ok(got["say"] == "Weather's turning.", "the say survives a malformed action without crashing")
	_ok(pell.adopted_goals.is_empty(), "a malformed adopt_goal (bad args) is not applied")
	DM.node_changed.disconnect(cb)
	DM._end()
	SB.set_client(MockSidecar.new())

func _test_converse_request_shape() -> void:
	print("[converse request shape]")
	var AG: Object = root.get_node("/root/Agents")
	AG.rebuild()
	var orin: Agent = AG.get_agent("lamplighter_orin")
	var snap: Dictionary = Perception.build_snapshot(orin, orin.position)
	var rc: Dictionary = Perception.converse_request(snap, "sess_conv", "what are you doing?", [])
	_ok(String(rc.get("utterance", "")) == "what are you doing?", "request carries the player's utterance")
	_ok(String(rc.get("speaker", "")) == "player", "request marks the player as the speaker")
	_ok(bool((rc.get("world_state", {}) as Dictionary).get("player_triggered", false)),
		"converse sets player_triggered true (a reveal/defection is player-earned)")
	_ok((rc.get("perception", {}) as Dictionary).has("secrets"),
		"converse forwards secrets (the brain gates rendering by revealed)")

func _test_persona_fields_plumbed() -> void:
	print("[persona fields plumbed to the brain]")
	var AG: Object = root.get_node("/root/Agents")
	AG.rebuild()
	var orin: Agent = AG.get_agent("lamplighter_orin")
	# Persona fields are read off the NpcDB def into the live Agent.
	_ok(orin.description != "", "agent carries a description from its def")
	_ok(orin.voice != "", "agent carries a voice")
	_ok(orin.knowledge.size() > 0, "agent carries knowledge facts")
	_ok(orin.tier == "full" or orin.tier == "light", "agent carries a cognition tier")
	# They flow into the perception snapshot.
	var snap: Dictionary = Perception.build_snapshot(orin, orin.position)
	_ok(String(snap.get("description", "")) != "", "snapshot includes description")
	_ok((snap.get("knowledge", []) as Array).size() > 0, "snapshot includes knowledge")
	# decide_request forwards the NON-secret persona into the prompt perception, but NOT secrets
	# (the autonomous loop is a hidden context — secrets only surface in converse, with the revealed gate).
	var rc: Dictionary = Perception.decide_request(snap, "s")
	var p: Dictionary = rc["perception"]
	_ok(String(p.get("description", "")) != "", "decide_request forwards description")
	_ok(String(p.get("voice", "")) != "", "decide_request forwards voice")
	_ok((p.get("knowledge", []) as Array).size() > 0, "decide_request forwards knowledge")
	_ok(not p.has("secrets"), "decide_request does NOT forward secrets in the autonomous path")
	# Persona persists across save/load.
	orin.description = "X"; orin.voice = "Y"; orin.knowledge = ["k"]; orin.secrets = ["s"]; orin.tier = "full"
	orin.deliberates = false
	# Data-driven NPC fields also round-trip through save/load.
	orin.goals = [{"description": "g1", "tier": "medium"}]
	orin.task = {"ritual": "summoning_descent"}
	var fresh := Agent.new("lamplighter_orin")
	fresh.from_dict(orin.to_dict())
	_ok(fresh.description == "X" and fresh.voice == "Y" and fresh.knowledge == ["k"] and fresh.secrets == ["s"] and fresh.tier == "full",
		"persona fields round-trip through to_dict/from_dict")
	_ok(fresh.deliberates == false, "the deliberates flag round-trips through save/load")
	_ok(fresh.goals == [{"description": "g1", "tier": "medium"}], "goals round-trip through to_dict/from_dict")
	_ok(fresh.task == {"ritual": "summoning_descent"}, "task round-trips through to_dict/from_dict")

func _test_data_driven_npc_fields_inert() -> void:
	print("[data-driven NPC fields populated from npcs.json (Phase A, inert)]")
	var AG: Object = root.get_node("/root/Agents")
	AG.rebuild()
	# The cult leader's new data-driven fields mirror what Perception._goals_for hardcodes — present
	# in data this phase, but no engine code reads them yet, so behavior is unchanged.
	var voss: Agent = AG.get_agent("clerk_voss")
	_ok(voss.goals.size() == 3, "clerk_voss reads its 3 goals (2 operational + the long aim) from its npc def")
	_ok(voss.task == {"ritual": "summoning_descent", "site": "crypt_altar", "cache": "ritual_cache"}, "clerk_voss reads its task from its npc def")

func _test_adopted_goals_reach_brain() -> void:
	print("[adopted goals reach the brain]")
	var AG: Object = root.get_node("/root/Agents")
	AG.rebuild()
	var orin: Agent = AG.get_agent("lamplighter_orin")
	orin.adopted_goals = [{"text": "Help the investigator stop the rite", "kind": "defection"}]
	var snap: Dictionary = Perception.build_snapshot(orin, orin.position)
	var snap_goals: Array = snap.get("adopted_goals", []) as Array
	_ok(snap_goals.size() == 1 and String((snap_goals[0] as Dictionary).get("text", "")) == "Help the investigator stop the rite",
		"build_snapshot carries the agent's adopted_goals")
	var rc: Dictionary = Perception.decide_request(snap, "sess1")
	var descs: Array = []
	for g in (rc["goals"] as Array):
		descs.append(String((g as Dictionary).get("description", "")))
	_ok(descs.has("Help the investigator stop the rite"),
		"an adopted goal is forwarded to the brain as a goal")

## Regression for the defection-detection desync: a waverer is "turned" by the KIND stamped on the goal it
## adopts (decided once, persisted), NOT by substring-scanning the goal text. Covers both failure modes the
## old keyword scan had: an off-keyword defection that was missed, and a keyword-in-text non-defection that
## was a false positive.
func _test_typed_defection_marker() -> void:
	print("[typed defection marker — kind, not keywords, decides a turn]")
	var AG: Object = root.get_node("/root/Agents")
	var EB: Object = root.get_node("/root/EventBus")
	var DM: Object = root.get_node("/root/DialogueManager")
	AG.rebuild()
	var orin: Agent = AG.get_agent("lamplighter_orin")   # the scout_waverer
	# CASE 1 — an off-keyword DEFECTION goal: its text matches NONE of the legacy keyword list, but the
	# action carries an explicit kind="defection" (the brain's call). The turn must still fire — exactly the
	# desync the typed marker fixes; a keyword scan of this text would have missed it and left him un-turned.
	orin.adopted_goals.clear()
	EB.clear()
	var off_kw := "Sabotage the descending rite"
	_ok(ActionCommit._classify_goal_kind(off_kw) == "other",
		"precondition: the goal text alone does not read as defection (no keyword hit)")
	DM._apply_converse_action({"verb": "adopt_goal", "args": {"goal": off_kw, "kind": "defection"}}, orin)
	_ok(DM._has_defection_goal(orin), "an off-keyword goal tagged kind=defection marks the waverer turned (persuade spent)")
	_ok(orin.has_adopted_goal("Help the investigator stop the cell"),
		"the off-keyword defection still fires social_influence (the turn goal is adopted)")
	_ok(EB.events("player_social").size() == 1, "social_influence ran (one player_social turn event logged)")
	# CASE 2 — the inverse desync: a goal whose text DOES contain a keyword ("stop") but is explicitly
	# kind="other" must NOT turn him. The persisted marker is authoritative; keyword presence no longer
	# forces a false turn.
	orin.adopted_goals.clear()
	EB.clear()
	DM._apply_converse_action({"verb": "adopt_goal", "args": {"goal": "stop by the market for bread", "kind": "other"}}, orin)
	_ok(not DM._has_defection_goal(orin), "a keyword-in-text goal tagged kind=other does NOT turn the waverer")
	_ok(EB.events("player_social").size() == 0, "no spurious social_influence fired for the non-defection goal")

func _test_action_gather_item() -> void:
	print("[action gather_item]")
	var AG: Object = root.get_node("/root/Agents")
	var EB: Object = root.get_node("/root/EventBus")
	var RI: Object = root.get_node("/root/RoomItems")
	var SP: Object = root.get_node("/root/SummoningPlan")
	AG.rebuild(); RI.clear(); SP.reset()
	var dalia: Agent = AG.get_agent("fishwife_dalia")   # cult / logistics
	dalia.inventory.clear()
	dalia.room = "city"
	dalia.position = Vector2(500, 500)
	EB.clear()
	# A known NON-ritual item forages out of fieldwork even with nothing on the ground (Yumina-style).
	var out: Dictionary = ActionCommit.commit(
		{"actor": "fishwife_dalia", "verb": "gather_item", "args": {"item_id": "rye_bread"}}, dalia)
	_ok(out.get("added", false) == true and out.get("from_ground", true) == false,
		"a known non-ritual item forages successfully with nothing on the ground")
	_ok(dalia.item_count("rye_bread") == 1, "the item lands in the agent's own inventory")
	_ok(EB.events("item_gathered").size() == 1, "an item_gathered event is logged")
	_ok(EB.events("item_gathered")[0]["data"]["actor"] == "fishwife_dalia", "the event names the gatherer")
	# Gathering again stacks in the agent's own inventory.
	ActionCommit.commit({"actor": "fishwife_dalia", "verb": "gather_item", "args": {"item_id": "rye_bread"}}, dalia)
	_ok(dalia.item_count("rye_bread") == 2, "repeated gathering stacks")
	# An unknown item is a safe no-op — no inventory change, no event.
	EB.clear()
	var out_unknown: Dictionary = ActionCommit.commit(
		{"actor": "fishwife_dalia", "verb": "gather_item", "args": {"item_id": "moonbeam"}}, dalia)
	_ok(out_unknown.get("added", false) == false, "gathering an unknown item is a no-op")
	_ok(dalia.item_count("moonbeam") == 0, "an unknown item is not added")
	_ok(EB.events("item_gathered").is_empty(), "no event for an unknown item")
	# A RITUAL offering may NOT be foraged from thin air: with no ground pile in the room the gather
	# fails, so the cult must draw from the supply cache (and the player can starve them by emptying it).
	dalia.inventory.clear()
	RI.clear()
	EB.clear()
	var no_pile: Dictionary = ActionCommit.commit(
		{"actor": "fishwife_dalia", "verb": "gather_item", "args": {"item_id": "ritual_salt"}}, dalia)
	_ok(no_pile.get("added", false) == false and no_pile.get("reason", "") == "none_here",
		"a ritual offering cannot be foraged from thin air")
	_ok(dalia.item_count("ritual_salt") == 0, "the un-forageable offering is not added")
	_ok(EB.events("item_gathered").is_empty(), "no event when an offering can't be picked up")
	# With a real ground pile it gathers off the ground and depletes it — and never restocks the
	# cult's separate shared rite cache (SummoningPlan.ingredients).
	var cache_salt_before: int = int(SP.ingredients.get("ritual_salt", 0))
	RI.place("city", "ritual_salt", dalia.position, 2)
	var from_pile: Dictionary = ActionCommit.commit(
		{"actor": "fishwife_dalia", "verb": "gather_item", "args": {"item_id": "ritual_salt"}}, dalia)
	_ok(from_pile.get("added", false) == true and from_pile.get("from_ground", false) == true,
		"a ritual offering gathers off a real ground pile")
	_ok(RI.count("city", "ritual_salt") == 1, "the ground pile depletes by one")
	_ok(int(SP.ingredients.get("ritual_salt", 0)) == cache_salt_before, "gathering does not restock the shared rite cache")
	SP.reset(); RI.clear()

func _test_room_items_store() -> void:
	print("[room items — ground store]")
	var RI: Object = root.get_node("/root/RoomItems")
	RI.clear()
	_ok(RI.count("city") == 0, "a fresh room has no ground items")
	RI.place("city", "ritual_salt", Vector2(100, 100), 2)
	RI.place("city", "candle", Vector2(400, 400), 1)
	_ok(RI.count("city") == 3, "place adds to the room's ground count")
	_ok(RI.count("city", "ritual_salt") == 2, "count filters by item id")
	# A like item dropped on the same spot stacks rather than duplicating.
	RI.place("city", "ritual_salt", Vector2(103, 100), 1)
	_ok(RI.items_in("city").size() == 2, "a nearby like item stacks into one entry")
	_ok(RI.count("city", "ritual_salt") == 3, "the stack count grows")
	# take_near pulls the nearest matching unit within radius.
	var got: String = RI.take_near("city", "ritual_salt", Vector2(110, 100), 80.0)
	_ok(got == "ritual_salt", "take_near returns the taken item id")
	_ok(RI.count("city", "ritual_salt") == 2, "take_near removes one unit")
	# Out of range -> nothing taken.
	var miss: String = RI.take_near("city", "candle", Vector2(0, 0), 50.0)
	_ok(miss == "", "take_near out of range takes nothing")
	# A non-gatherable pile (a deposited offering) renders but can't be picked up.
	RI.place("cathedral_crypt", "ritual_salt", Vector2(691, 600), 1, false)
	_ok(RI.count("cathedral_crypt") == 1, "a non-gatherable pile still counts (it renders)")
	var laid: String = RI.take_near("cathedral_crypt", "ritual_salt", Vector2(691, 600), 80.0)
	_ok(laid == "", "a non-gatherable (laid) offering cannot be re-gathered")
	RI.clear()

func _test_gather_capacity_and_ground() -> void:
	print("[gather — carry capacity + ground depletion]")
	var AG: Object = root.get_node("/root/Agents")
	var RI: Object = root.get_node("/root/RoomItems")
	var EB: Object = root.get_node("/root/EventBus")
	AG.rebuild(); RI.clear()
	var dalia: Agent = AG.get_agent("fishwife_dalia")
	dalia.inventory.clear()
	dalia.carry_capacity = 2
	dalia.room = "city"
	dalia.position = Vector2(500, 500)
	# Stock a cache the cultist is standing in.
	RI.place("city", "ritual_salt", Vector2(500, 500), 3)
	EB.clear()
	# First two gathers succeed and DEPLETE the ground cache.
	var g1: Dictionary = ActionCommit.commit({"actor": "fishwife_dalia", "verb": "gather_item", "args": {"item_id": "ritual_salt"}}, dalia)
	_ok(g1.get("added") == true and g1.get("from_ground") == true, "gathering picks the salt off the ground")
	_ok(RI.count("city", "ritual_salt") == 2, "the ground cache depletes by one")
	ActionCommit.commit({"actor": "fishwife_dalia", "verb": "gather_item", "args": {"item_id": "ritual_salt"}}, dalia)
	_ok(dalia.inventory_count() == 2, "the cultist is now carrying two (at capacity)")
	# The third gather is refused — hands full — and leaves the cache untouched.
	var g3: Dictionary = ActionCommit.commit({"actor": "fishwife_dalia", "verb": "gather_item", "args": {"item_id": "ritual_salt"}}, dalia)
	_ok(g3.get("added") == false and g3.get("reason", "") == "full", "a full pack refuses to gather more")
	_ok(RI.count("city", "ritual_salt") == 1, "a refused gather leaves the cache alone")
	_ok(dalia.inventory_count() == 2, "carrying never exceeds capacity")
	# Foraging a NON-ritual item with no ground pile still works (per-agent fieldwork), capacity-gated.
	# (A ritual offering would NOT forage here — that gate is covered in _test_action_gather_item.)
	dalia.remove_item("ritual_salt", 1)   # free a hand
	var gf: Dictionary = ActionCommit.commit({"actor": "fishwife_dalia", "verb": "gather_item", "args": {"item_id": "rye_bread"}}, dalia)
	_ok(gf.get("added") == true and gf.get("from_ground") == false, "with no ground item, a non-ritual item still forages")
	RI.clear()

func _test_action_talk_to_rumor() -> void:
	print("[action talk_to rumor]")
	var AG: Object = root.get_node("/root/Agents")
	var EB: Object = root.get_node("/root/EventBus")
	AG.rebuild()
	var voss: Agent = AG.get_agent("clerk_voss")
	var orin: Agent = AG.get_agent("lamplighter_orin")
	voss.position = Vector2(400, 300)
	orin.position = Vector2(420, 300)   # within TALK_RADIUS
	orin.short_memory.clear()
	voss.short_memory.clear()
	voss.remember("saw the player prowling the harbor")
	EB.clear()
	var out: Dictionary = ActionCommit.commit(
		{"actor": "clerk_voss", "verb": "talk_to", "args": {"agent": "lamplighter_orin", "topic": "the player"}}, voss)
	_ok(out.get("shared", false) == true, "a speaker with real knowledge shares it")
	_ok(orin.short_memory.size() >= 1, "the rumor lands in the listener's memory")
	_ok("harbor" in String(orin.short_memory[-1]), "the listener hears what the speaker knew")
	_ok(voss.short_memory.size() >= 1, "the speaker still records the exchange")
	_ok(EB.events("rumor_spread").size() == 1, "a rumor_spread event is logged")
	_ok(EB.events("rumor_spread")[0]["data"]["to"] == "lamplighter_orin", "the event names the listener")
	var dalia: Agent = AG.get_agent("fishwife_dalia")
	dalia.short_memory.clear()
	dalia.position = Vector2(400, 300)
	orin.short_memory.clear()
	EB.clear()
	var out_empty: Dictionary = ActionCommit.commit(
		{"actor": "fishwife_dalia", "verb": "talk_to", "args": {"agent": "lamplighter_orin", "topic": "the player"}}, dalia)
	_ok(out_empty.get("shared", false) == false, "a speaker with nothing to tell shares nothing")
	_ok(orin.short_memory.is_empty(), "no rumor lands when the speaker knows nothing")
	_ok(EB.events("rumor_spread").is_empty(), "no rumor_spread event without real knowledge")
	voss.short_memory.clear()
	voss.remember("the warehouse is nearly ready")
	orin.short_memory.clear()
	orin.position = Vector2(3000, 3000)
	EB.clear()
	var out_far: Dictionary = ActionCommit.commit(
		{"actor": "clerk_voss", "verb": "talk_to", "args": {"agent": "lamplighter_orin", "topic": "the rite"}}, voss)
	_ok(out_far.get("shared", false) == false, "a talk across the district does not carry")
	_ok(orin.short_memory.is_empty(), "an out-of-reach listener hears nothing")
	_ok(voss.short_memory.size() >= 1, "the speaker still records trying to talk")

func _test_agent_runtime_beat() -> void:
	print("[agent runtime]")
	var AG: Object = root.get_node("/root/Agents")
	var EB: Object = root.get_node("/root/EventBus")
	var SB: Object = root.get_node("/root/SidecarBridge")
	var ART: Object = root.get_node("/root/AgentRuntime")
	AG.rebuild()
	EB.clear()
	# Isolation: an earlier test's start_run may have staged the M8 opening butcher into always_active
	# (GMOpening keeps bram_kell present so the opening fight is reachable). This test asserts ONLY voss
	# acts (activation by radius), so scrub the always_active override it doesn't own.
	ART.always_active.clear()
	var voss: Agent = AG.get_agent("clerk_voss")
	voss.position = Vector2(400, 300)
	ART.player_position = Vector2(400, 300)
	ART.active_radius = 50.0   # only voss is active

	# Mock proposes a valid move for voss.
	var mock := MockSidecar.new()
	mock.set_action("clerk_voss", {"actor": "clerk_voss", "verb": "move_to", "args": {"target": "iron_cross_warehouse"}})
	SB.set_client(mock)

	var before: Vector2 = voss.position
	ART.run_beat()
	_ok(voss.position != before, "active agent acted on its proposal")
	_ok(EB.events("agent_action").size() == 1, "one agent_action logged")
	_ok(EB.events("agent_action")[0]["data"]["actor"] == "clerk_voss", "logged actor is voss")

	# Invalid proposal -> rejected -> fallback.
	EB.clear()
	mock.set_action("clerk_voss", {"actor": "clerk_voss", "verb": "teleport", "args": {}})
	ART.run_beat()
	_ok(EB.events("action_rejected").size() == 1, "invalid action is rejected, not committed")
	_ok(EB.events("agent_action").size() == 0, "no agent_action for the rejected proposal")

	# Idle proposal -> no movement. Re-pin voss onto the player first so it is unambiguously
	# active this beat; prior beats' schedule-fallback drift is a separate concern from whether
	# an idle verb moves the agent (it must not).
	EB.clear()
	mock.set_action("clerk_voss", {"actor": "clerk_voss", "verb": "idle", "args": {}})
	voss.position = Vector2(400, 300)
	var pos_idle: Vector2 = voss.position
	ART.run_beat()
	_ok(voss.position == pos_idle, "idle proposal leaves the agent in place")

func _test_overseer_state() -> void:
	print("[overseer]")
	var OV: Object = root.get_node("/root/Overseer")
	var EB: Object = root.get_node("/root/EventBus")
	OV.reset()
	# Directives: one-shot, keyed by agent.
	OV.issue_directive("clerk_voss", {"actor": "clerk_voss", "verb": "hide", "args": {}})
	_ok(OV.has_directive("clerk_voss"), "directive queued")
	var d: Dictionary = OV.take_directive("clerk_voss")
	_ok(d.get("verb", "") == "hide", "directive returned")
	_ok(not OV.has_directive("clerk_voss"), "directive is one-shot")
	_ok(OV.take_directive("nobody").is_empty(), "no directive returns empty dict")
	# Coordinate: issue the same directive to several agents.
	OV.coordinate(["fishwife_dalia", "lamplighter_orin"], {"verb": "move_to", "args": {"target": "iron_cross_warehouse"}})
	_ok(OV.has_directive("fishwife_dalia"), "coordinate queues for agent 1")
	_ok(OV.has_directive("lamplighter_orin"), "coordinate queues for agent 2")
	_ok(OV.take_directive("fishwife_dalia").get("actor", "") == "fishwife_dalia", "coordinate sets actor per agent")
	# Player involvement is initially false, flips on a player_ event.
	OV.reset()
	_ok(OV.allows_exposure() == false, "exposure disallowed until player is involved")
	EB.emit_event("player_sabotage", {"actor": "player", "item": "ritual_salt"})
	_ok(OV.allows_exposure() == true, "a player_ event marks the player involved")

func _test_critic_verdicts() -> void:
	print("[critic]")
	var AG: Object = root.get_node("/root/Agents")
	var OV: Object = root.get_node("/root/Overseer")
	AG.rebuild()
	OV.reset()
	var voss: Agent = AG.get_agent("clerk_voss")        # has a task / leader
	var pell: Agent = AG.get_agent("dockhand_pell")     # no task / victim
	var orin: Agent = AG.get_agent("lamplighter_orin")  # has a task / scout_waverer
	var neil: Agent = AG.get_agent("old_neil")          # no task, not a victim / alchemist

	# An agent with a task (rebuilt from data) may work the rite — regardless of any group label.
	_ok(voss.task.is_empty() == false, "clerk_voss has a task (precondition)")
	_ok(Critic.review({"actor": "clerk_voss", "verb": "perform_ritual_step", "args": {"step": "draw_circle"}}, voss)["verdict"] == "approve",
		"an agent with a task may perform a ritual step")
	# Recruit is NOT hard-gated — WHO recruits is behavioral (persona-driven, the LLM decides). Critic
	# approves a recruit for any non-victim agent, cult or not.
	_ok(Critic.review({"actor": "clerk_voss", "verb": "recruit", "args": {"agent": "dockhand_pell"}}, voss)["verdict"] == "approve",
		"recruit has no identity gate — an agent may attempt it (who actually recruits is behavioral)")
	# An agent with NO task cannot work a rite (pell has no task, independent of role).
	_ok(pell.task.is_empty(), "dockhand_pell has no task (precondition)")
	_ok(Critic.review({"actor": "dockhand_pell", "verb": "perform_ritual_step", "args": {"step": "draw_circle"}}, pell)["verdict"] == "veto",
		"an agent with no task cannot perform a ritual step")
	_ok(Critic.review({"actor": "old_neil", "verb": "recruit", "args": {"agent": "dockhand_pell"}}, neil)["verdict"] == "approve",
		"a non-cult, non-victim agent's recruit is also approved (recruit has no identity gate)")
	# The rite gate is the task itself, not a group label: clear orin's task and the rite is vetoed;
	# restoring the task re-allows it.
	orin.task = {}
	_ok(Critic.review({"actor": "lamplighter_orin", "verb": "perform_ritual_step", "args": {"step": "draw_circle"}}, orin)["verdict"] == "veto",
		"an agent whose task was cleared cannot perform a ritual step")
	orin.task = {"ritual": "summoning_descent"}
	_ok(Critic.review({"actor": "lamplighter_orin", "verb": "perform_ritual_step", "args": {"step": "draw_circle"}}, orin)["verdict"] == "approve",
		"restoring the task re-allows the ritual step")
	# Exposing report without player involvement -> veto; with involvement -> approve.
	var expose := {"actor": "clerk_voss", "verb": "report", "args": {"to": "nighthawks", "info": "the cult meets at the warehouse"}}
	_ok(Critic.review(expose, voss)["verdict"] == "veto", "no caught-by-chance: exposing report vetoed")
	OV.player_involved = true
	_ok(Critic.review(expose, voss)["verdict"] == "approve", "exposing report allowed once player is involved")
	# Ordinary move is always fine.
	_ok(Critic.review({"actor": "clerk_voss", "verb": "move_to", "args": {"target": "iron_cross_warehouse"}}, voss)["verdict"] == "approve",
		"ordinary move approved")

func _test_critic_downed_veto() -> void:
	print("[critic downed]")
	var AG: Object = root.get_node("/root/Agents")
	AG.rebuild()
	var voss: Agent = AG.get_agent("clerk_voss")  # cult / leader
	# Upright, the leader acts normally.
	_ok(Critic.review({"actor": "clerk_voss", "verb": "move_to", "args": {"target": "iron_cross_warehouse"}}, voss)["verdict"] == "approve",
		"an upright agent may move")
	# Felled, every active verb is vetoed — a downed body cannot move, work the rite, or strike.
	voss.downed = true
	_ok(Critic.review({"actor": "clerk_voss", "verb": "move_to", "args": {"target": "iron_cross_warehouse"}}, voss)["verdict"] == "veto",
		"a downed agent cannot move")
	_ok(Critic.review({"actor": "clerk_voss", "verb": "perform_ritual_step", "args": {"step": "draw_circle"}}, voss)["verdict"] == "veto",
		"a downed agent cannot work the rite")
	_ok(Critic.review({"actor": "clerk_voss", "verb": "attack", "args": {"target": "dockhand_pell"}}, voss)["verdict"] == "veto",
		"a downed agent cannot attack")
	# Only idle survives — the one coherent thing a felled agent can do.
	_ok(Critic.review({"actor": "clerk_voss", "verb": "idle", "args": {}}, voss)["verdict"] == "approve",
		"a downed agent may still idle")

## ---- Combat M1 (enablers): perception health, intent verbs, telegraphs, combat mode, abilities ----

## Perception health (plan §M1): the snapshot carries the agent's OWN exact hp/max_hp/downed;
## peers in `nearby` carry a coarse hp_band only (healthy/hurt/critical/downed — an agent can see
## a neighbor limp, never read their hit points); decide_request forwards self health to the brain.
func _test_perception_health() -> void:
	print("[perception health (combat M1)]")
	var AG: Object = root.get_node("/root/Agents")
	AG.rebuild()
	var voss: Agent = AG.get_agent("clerk_voss")
	var pell: Agent = AG.get_agent("dockhand_pell")
	var orin: Agent = AG.get_agent("lamplighter_orin")
	var neil: Agent = AG.get_agent("old_neil")
	var dalia: Agent = AG.get_agent("fishwife_dalia")
	# Self health rides the snapshot exactly.
	voss.hp = 61.0
	voss.room = "city"
	voss.position = Vector2(400, 300)
	var snap: Dictionary = Perception.build_snapshot(voss, voss.position)
	_ok(float(snap.get("hp", -1.0)) == 61.0, "snapshot carries the agent's own exact hp")
	_ok(float(snap.get("max_hp", -1.0)) == 100.0, "snapshot carries max_hp")
	_ok(snap.get("downed") == false, "snapshot carries downed")
	# The band rule itself (language-neutral; mirrored in brain.py).
	_ok(Perception.hp_band(70.0, 100.0, false) == "healthy", "hp > 2/3 -> healthy")
	_ok(Perception.hp_band(66.0, 100.0, false) == "hurt", "hp in (1/3, 2/3] -> hurt")
	_ok(Perception.hp_band(34.0, 100.0, false) == "hurt", "just above 1/3 is still hurt")
	_ok(Perception.hp_band(33.0, 100.0, false) == "critical", "hp in (0, 1/3] -> critical")
	_ok(Perception.hp_band(0.0, 100.0, false) == "downed", "0 hp -> downed")
	_ok(Perception.hp_band(90.0, 100.0, true) == "downed", "the downed flag wins regardless of hp")
	# Peers are BANDED, never exact: four peers in vision at distinct bands.
	for a in [pell, orin, neil, dalia]:
		a.room = "city"
		a.position = Vector2(410, 300)
	pell.hp = 100.0
	pell.downed = false
	orin.hp = 50.0
	orin.downed = false
	neil.hp = 10.0
	neil.downed = false
	dalia.hp = 0.0
	dalia.downed = true
	var snap2: Dictionary = Perception.build_snapshot(voss, voss.position)
	var bands := {}
	var leaks_exact := false
	for n in snap2["nearby"]:
		bands[String(n["id"])] = String((n as Dictionary).get("hp_band", ""))
		if (n as Dictionary).has("hp") or (n as Dictionary).has("max_hp"):
			leaks_exact = true
	_ok(bands.get("dockhand_pell", "") == "healthy", "a full-hp peer reads healthy")
	_ok(bands.get("lamplighter_orin", "") == "hurt", "a mid-hp peer reads hurt")
	_ok(bands.get("old_neil", "") == "critical", "a low-hp peer reads critical")
	_ok(bands.get("fishwife_dalia", "") == "downed", "a felled peer reads downed")
	_ok(not leaks_exact, "no exact hp ever rides a nearby entry — peers are banded only")
	# decide_request forwards self health inside perception (the brain renders the condition fact).
	var req: Dictionary = Perception.decide_request(snap2, "s")
	var perc: Dictionary = req["perception"]
	_ok(float(perc.get("hp", -1.0)) == 61.0, "decide_request forwards exact self hp")
	_ok(float(perc.get("max_hp", -1.0)) == 100.0, "decide_request forwards max_hp")
	_ok(perc.get("downed") == false, "decide_request forwards downed")
	var fwd_band := ""
	for n in (perc.get("nearby", []) as Array):
		if String((n as Dictionary).get("id", "")) == "lamplighter_orin":
			fwd_band = String((n as Dictionary).get("hp_band", ""))
	_ok(fwd_band == "hurt", "the banded peer roster reaches the brain via perception.nearby")
	AG.rebuild()

## Intent verbs (plan §M1): engage/disengage/protect are schema-legal; style/via are OPTIONAL
## args (the validator only requires listed args and passes extras through).
func _test_intent_verbs_schema() -> void:
	print("[intent verbs schema (combat M1)]")
	_ok(ActionSchema.is_verb("engage"), "engage is a known verb")
	_ok(ActionSchema.is_verb("disengage"), "disengage is a known verb")
	_ok(ActionSchema.is_verb("protect"), "protect is a known verb")
	_ok(ActionSchema.required_args("engage") == ["target"], "engage requires target")
	_ok(ActionSchema.required_args("protect") == ["agent"], "protect requires agent")
	_ok((ActionSchema.required_args("disengage") as Array).is_empty(), "disengage has no required args")
	_ok(ActionSchema.validate({"actor": "a", "verb": "engage", "args": {"target": "player"}})["ok"],
		"engage with a target validates")
	_ok(ActionSchema.validate({"actor": "a", "verb": "engage", "args": {"target": "player", "style": "cautious"}})["ok"],
		"the optional style arg is accepted (extra args pass through)")
	_ok(not ActionSchema.validate({"actor": "a", "verb": "engage", "args": {}})["ok"],
		"engage without a target is rejected")
	_ok(ActionSchema.validate({"actor": "a", "verb": "disengage", "args": {"via": "the alley"}})["ok"],
		"the optional via arg is accepted")
	_ok(ActionSchema.validate({"actor": "a", "verb": "disengage", "args": {}})["ok"], "bare disengage validates")
	_ok(ActionSchema.validate({"actor": "a", "verb": "protect", "args": {"agent": "old_neil"}})["ok"],
		"protect with its ward validates")

## Committing an intent verb publishes Agent.combat_intent as a FACT — no damage, no movement.
## Style is validated at commit (default aggressive); disengage also exits combat mode.
func _test_combat_intent_commit() -> void:
	print("[combat intent commit (combat M1)]")
	var AG: Object = root.get_node("/root/Agents")
	var EB: Object = root.get_node("/root/EventBus")
	var CLK: Object = root.get_node("/root/Clock")
	AG.rebuild()
	var voss: Agent = AG.get_agent("clerk_voss")
	var pell: Agent = AG.get_agent("dockhand_pell")
	voss.room = "city"
	pell.room = "city"
	voss.position = Vector2(400, 300)
	pell.position = Vector2(405, 300)   # in strike reach — proves engage still deals NO damage
	pell.hp = 100.0
	pell.downed = false
	voss.short_memory.clear()
	var pos_before: Vector2 = voss.position
	var out: Dictionary = ActionCommit.commit(
		{"actor": "clerk_voss", "verb": "engage", "args": {"target": "dockhand_pell", "style": "cautious"}}, voss)
	_ok(String(voss.combat_intent.get("mode", "")) == "engage", "engage writes combat_intent.mode")
	_ok(String(voss.combat_intent.get("target", "")) == "dockhand_pell", "…with its target")
	_ok(String(voss.combat_intent.get("style", "")) == "cautious", "a valid style is kept")
	_ok(int(voss.combat_intent.get("set_at_beat", -1)) == int(CLK.beat_index), "the intent is stamped with the beat")
	_ok(pell.hp == 100.0, "engage applies NO damage — a published fact only")
	_ok(voss.position == pos_before, "engage moves nothing")
	_ok(String(out.get("engaged", "")) == "dockhand_pell", "the outcome is descriptive")
	_ok(voss.short_memory.size() == 1, "one neutral memory line is recorded")
	ActionCommit.commit({"actor": "clerk_voss", "verb": "engage", "args": {"target": "dockhand_pell"}}, voss)
	_ok(String(voss.combat_intent.get("style", "")) == "aggressive", "absent style defaults to aggressive")
	ActionCommit.commit({"actor": "clerk_voss", "verb": "engage", "args": {"target": "dockhand_pell", "style": "berserk"}}, voss)
	_ok(String(voss.combat_intent.get("style", "")) == "aggressive", "an unknown style falls back to aggressive")
	# protect publishes its ward.
	var outp: Dictionary = ActionCommit.commit(
		{"actor": "clerk_voss", "verb": "protect", "args": {"agent": "dockhand_pell"}}, voss)
	_ok(String(voss.combat_intent.get("mode", "")) == "protect"
		and String(voss.combat_intent.get("agent", "")) == "dockhand_pell", "protect writes mode + ward")
	_ok(String(outp.get("protecting", "")) == "dockhand_pell", "protect outcome is descriptive")
	# disengage publishes mode+via AND clears combat mode (the LLM's way out of the mask).
	voss.in_combat = true
	EB.clear()
	var outd: Dictionary = ActionCommit.commit(
		{"actor": "clerk_voss", "verb": "disengage", "args": {"via": "the alley"}}, voss)
	_ok(String(voss.combat_intent.get("mode", "")) == "disengage"
		and String(voss.combat_intent.get("via", "")) == "the alley", "disengage writes mode + via")
	_ok(voss.in_combat == false, "disengage CLEARS combat mode")
	_ok(EB.events("combat_ended").size() == 1, "leaving combat publishes combat_ended")
	_ok(bool(outd.get("disengaged", false)) and String(outd.get("via", "")) == "the alley",
		"disengage outcome is descriptive")
	EB.clear()
	ActionCommit.commit({"actor": "clerk_voss", "verb": "disengage", "args": {}}, voss)
	_ok(EB.events("combat_ended").is_empty(), "disengage while not in combat emits no combat_ended")
	AG.rebuild()

## Critic coherence (plan §M1): the intended victim may not engage (mirrors its attack gate);
## the downed gate already covers every verb but idle.
func _test_critic_victim_engage() -> void:
	print("[critic: victim engage gate (combat M1)]")
	var AG: Object = root.get_node("/root/Agents")
	AG.rebuild()
	var pell: Agent = AG.get_agent("dockhand_pell")
	var voss: Agent = AG.get_agent("clerk_voss")
	_ok(pell.role == "victim", "precondition: dockhand_pell is the victim")
	_ok(Critic.review({"actor": "dockhand_pell", "verb": "engage", "args": {"target": "clerk_voss"}}, pell)["verdict"] == "veto",
		"the intended victim may not engage (mirrors the attack gate)")
	_ok(Critic.review({"actor": "dockhand_pell", "verb": "disengage", "args": {}}, pell)["verdict"] == "approve",
		"a victim may still disengage")
	_ok(Critic.review({"actor": "dockhand_pell", "verb": "protect", "args": {"agent": "old_neil"}}, pell)["verdict"] == "approve",
		"a victim may still protect")
	_ok(Critic.review({"actor": "clerk_voss", "verb": "engage", "args": {"target": "player"}}, voss)["verdict"] == "approve",
		"a non-victim's engage is approved")
	voss.downed = true
	_ok(Critic.review({"actor": "clerk_voss", "verb": "engage", "args": {"target": "player"}}, voss)["verdict"] == "veto",
		"a downed agent cannot engage (the downed gate holds)")
	voss.downed = false
	AG.rebuild()

## Off-cohort continuation (plan §M1): an engage/protect intent holder HOLDS between deliberations
## (the M2 executor owns its frame-rate acting) — never a schedule fallback that walks it off the
## fight. A disengage holder resumes normal continuation (it is leaving).
func _test_runtime_combat_intent_hold() -> void:
	print("[runtime: combat-intent holders hold off-beat (combat M1)]")
	var AG: Object = root.get_node("/root/Agents")
	var ART: Object = root.get_node("/root/AgentRuntime")
	AG.rebuild()
	var voss: Agent = AG.get_agent("clerk_voss")
	voss.task = {}   # no task: a one-shot verb would otherwise schedule-fallback
	voss.room = "city"
	voss.position = Vector2(100, 100)
	voss.current_action = {"verb": "engage", "args": {"target": "player"}}
	voss.combat_intent = {"mode": "engage", "target": "player", "style": "aggressive", "set_at_beat": 0}
	var before: Vector2 = voss.position
	ART._continue_action(voss)
	_ok(voss.position == before, "an engage-intent holder HOLDS off-beat (no schedule fallback)")
	voss.combat_intent = {"mode": "protect", "agent": "old_neil", "set_at_beat": 0}
	ART._continue_action(voss)
	_ok(voss.position == before, "a protect-intent holder holds too")
	voss.combat_intent = {"mode": "disengage", "set_at_beat": 0}
	voss.current_action = {}
	ART._continue_action(voss)
	_ok(voss.position != before, "a disengage holder falls back to its schedule (it is leaving the fight)")
	AG.rebuild()

## Telegraph events (plan §M1): CombatEvents is the ONE emitter of the ability-cast lifecycle,
## so M2 code and tests share a single shape.
func _test_telegraph_events() -> void:
	print("[telegraph events (combat M1)]")
	var EB: Object = root.get_node("/root/EventBus")
	EB.clear()
	CombatEvents.cast_started("player", "revolver_shot", "bram_kell", Vector2(1, 0), 0.25)
	var evs: Array = EB.events("ability_cast_started")
	_ok(evs.size() == 1, "cast_started emits ability_cast_started")
	var d: Dictionary = evs[0]["data"]
	_ok(String(d.get("caster", "")) == "player" and String(d.get("ability", "")) == "revolver_shot",
		"…naming caster + ability")
	_ok(String(d.get("target", "")) == "bram_kell", "…and the target")
	_ok(d.get("dir") == [1.0, 0.0], "…and the aim direction (JSON-safe array)")
	_ok(float(d.get("cast_time", 0.0)) == 0.25, "…and the telegraph window")
	CombatEvents.cast_finished("player", "revolver_shot")
	var evf: Array = EB.events("ability_cast_finished")
	_ok(evf.size() == 1 and String((evf[0]["data"] as Dictionary).get("caster", "")) == "player",
		"cast_finished emits with its caster")
	CombatEvents.cast_interrupted("bram_kell", "cleaver_swipe", "stagger")
	var evi: Array = EB.events("ability_cast_interrupted")
	_ok(evi.size() == 1 and String((evi[0]["data"] as Dictionary).get("reason", "")) == "stagger",
		"cast_interrupted emits with its reason")
	EB.clear()

## Stimulus fans cast_started as a vision-gated neutral FACT from the caster's position — an
## in-range witness remembers the wind-up; out-of-range/other-room agents never learn of it.
func _test_telegraph_stimulus_fan() -> void:
	print("[telegraph stimulus fan (combat M1)]")
	var AG: Object = root.get_node("/root/Agents")
	AG.rebuild()
	var bram: Agent = AG.get_agent("bram_kell")     # caster
	var voss: Agent = AG.get_agent("clerk_voss")    # in-range witness
	var neil: Agent = AG.get_agent("old_neil")      # same room, out of its vision
	var pell: Agent = AG.get_agent("dockhand_pell") # other room, same local coords
	bram.room = "city"
	bram.position = Vector2(500, 500)
	bram.short_memory.clear()
	voss.room = "city"
	voss.position = Vector2(550, 500)   # d = 50, within voss's vision_r
	voss.short_memory.clear()
	neil.room = "city"
	neil.position = Vector2(500.0 + neil.vision_r + 400.0, 500)
	neil.short_memory.clear()
	pell.room = "cathedral_crypt"
	pell.position = Vector2(500, 500)
	pell.short_memory.clear()
	CombatEvents.cast_started("bram_kell", "cleaver_swipe", "clerk_voss", Vector2.ZERO, 0.45)
	_ok(_short_mem_has(voss, "begins to loose"), "an in-range witness perceives the telegraph")
	_ok(_short_mem_has(voss, "Bram Kell"), "the line names the caster")
	_ok(not _short_mem_has(voss, "dodge") and not _short_mem_has(voss, "attack"),
		"the telegraph line is a neutral fact, never a scripted reaction")
	_ok(not _short_mem_has(neil, "begins to loose"), "an out-of-range witness does not perceive it")
	_ok(not _short_mem_has(pell, "begins to loose"), "an other-room agent never perceives it")
	_ok(not _short_mem_has(bram, "begins to loose"), "the caster is not its own witness")
	AG.rebuild()

## Combat mode (plan §0/§M1): damage that lands on a STANDING agent flips in_combat and publishes
## combat_started {agent} exactly once — flag + event ONLY, never a form/sprite swap (transformation
## is an ability). A downing blow downs without starting combat; disciplined enter/exit are idempotent.
func _test_combat_mode_flip() -> void:
	print("[combat mode flip (combat M1)]")
	var AG: Object = root.get_node("/root/Agents")
	var EB: Object = root.get_node("/root/EventBus")
	var CM: Object = root.get_node("/root/CombatMode")
	AG.rebuild()
	var bram: Agent = AG.get_agent("bram_kell")
	var form_before: String = bram.combat_form
	bram.hp = 100.0
	bram.downed = false
	bram.in_combat = false
	EB.clear()
	bram.take_damage(26.0)
	_ok(bram.in_combat == true, "damage that lands flips in_combat")
	var evs: Array = EB.events("combat_started")
	_ok(evs.size() == 1, "combat_started is emitted once")
	_ok(String((evs[0]["data"] as Dictionary).get("agent", "")) == "bram_kell", "…naming the agent")
	_ok(not (evs[0]["data"] as Dictionary).has("form"),
		"combat_started carries NO form — transformation is an ability, not a damage side-effect")
	_ok(bram.combat_form == form_before, "the authored combat_form data is untouched by the flip")
	bram.take_damage(10.0)
	_ok(EB.events("combat_started").size() == 1, "further damage while already in combat emits nothing new")
	# A blow that DOWNS the agent does not start combat for a felled body.
	var neil: Agent = AG.get_agent("old_neil")
	neil.hp = 20.0
	neil.downed = false
	neil.in_combat = false
	EB.clear()
	neil.take_damage(50.0)
	_ok(neil.downed and not neil.in_combat, "a downing blow downs — it does not start combat")
	_ok(EB.events("combat_started").is_empty(), "…and emits no combat_started")
	# exit_combat clears + publishes once; both transitions are idempotent.
	EB.clear()
	CM.exit_combat(bram)
	_ok(bram.in_combat == false, "exit_combat clears the flag")
	var eve: Array = EB.events("combat_ended")
	_ok(eve.size() == 1 and String((eve[0]["data"] as Dictionary).get("agent", "")) == "bram_kell",
		"…and publishes combat_ended naming the agent")
	CM.exit_combat(bram)
	_ok(EB.events("combat_ended").size() == 1, "exit while not in combat is a no-op")
	EB.clear()
	CM.enter_combat(bram)
	CM.enter_combat(bram)
	_ok(bram.in_combat and EB.events("combat_started").size() == 1, "enter_combat is idempotent (one event)")
	EB.clear()   # review M1 #8: leave no combat_started for downstream EventBus readers
	AG.rebuild()

## Pins for the M1 review fixes (SHIP-WITH-FIXES): stale-intent supersession, combat exit on
## downing, engage target validation + combat entry, player-proxy exemption, AbilityDB shape guards.
func _test_m1_review_fixes() -> void:
	print("[combat M1 review fixes]")
	var AG: Object = root.get_node("/root/Agents")
	var EB: Object = root.get_node("/root/EventBus")
	var ADB: Object = root.get_node("/root/AbilityDB")
	AG.rebuild()
	var bram: Agent = AG.get_agent("bram_kell")
	var orin: Agent = AG.get_agent("lamplighter_orin")
	bram.hp = 100.0; bram.downed = false; bram.in_combat = false; bram.combat_intent = {}
	EB.clear()
	# (#5/#6) a VALID engage publishes intent AND enters combat mode; junk targets publish nothing.
	ActionCommit.commit({"actor": "bram_kell", "verb": "engage",
		"args": {"target": "lamplighter_orin", "style": "cautious"}}, bram)
	_ok(String(bram.combat_intent.get("mode", "")) == "engage", "valid engage publishes the intent fact")
	_ok(bram.in_combat, "engage ENTERS combat mode (choosing the fight flips the stance)")
	_ok(EB.events("combat_started").size() == 1, "…and publishes combat_started")
	var junk: Dictionary = ActionCommit.commit({"actor": "bram_kell", "verb": "engage",
		"args": {"target": "no_such_agent"}}, bram)
	_ok(String(junk.get("reason", "")) == "no_such_target", "an unresolvable engage target is a no-op")
	var selfy: Dictionary = ActionCommit.commit({"actor": "bram_kell", "verb": "engage",
		"args": {"target": "bram_kell"}}, bram)
	_ok(String(selfy.get("reason", "")) == "no_such_target", "self-engage is a no-op")
	# (#1) a fresh committed NON-intent decision supersedes the standing stance.
	ActionCommit.commit({"actor": "bram_kell", "verb": "engage",
		"args": {"target": "lamplighter_orin"}}, bram)
	_ok(not bram.combat_intent.is_empty(), "precondition: intent standing")
	ActionCommit.commit({"actor": "bram_kell", "verb": "move_to", "args": {"target": "100,100"}}, bram)
	_ok(bram.combat_intent.is_empty(), "a fresh non-intent decision clears the stale stance")
	# (#2) a downing blow EXITS combat (combat_ended fires; no phantom fight persists).
	bram.hp = 20.0; bram.downed = false
	if not bram.in_combat:
		ActionCommit.commit({"actor": "bram_kell", "verb": "engage",
			"args": {"target": "lamplighter_orin"}}, bram)
	EB.clear()
	bram.take_damage(50.0)
	_ok(bram.downed and not bram.in_combat, "a downing blow downs AND exits combat")
	_ok(EB.events("combat_ended").size() == 1, "…publishing combat_ended for the felled agent")
	_ok(bram.combat_intent.is_empty(), "…and clears the standing intent")
	# (#4) the player proxy never latches combat mode (no brain; M5 owns player combat).
	AG.ensure_player_proxy(Vector2(400, 300), "city")
	var proxy: Agent = AG.get_agent("player")
	proxy.hp = 100.0; proxy.downed = false; proxy.in_combat = false
	EB.clear()
	proxy.take_damage(10.0)
	_ok(not proxy.in_combat, "the player proxy does not latch in_combat on damage")
	_ok(EB.events("combat_started").is_empty(), "…and emits no combat_started")
	# (#3/#7) AbilityDB shape guards: malformed shapes become reported problems, never hard errors.
	var bad_forms: Dictionary = {
		"broken_kit": {"kit": "cleaver_swipe"},
		"broken_reflexes": {"kit": [], "reflexes": "oops"},
		"broken_do": {"kit": [], "reflexes": [{"when": {}, "do": "dodge"}]},
	}
	var probs: Array = ADB.validate_refs({"a": {"effects": "nope"}}, bad_forms)
	var text := " | ".join(PackedStringArray(probs))
	_ok(text.contains("kit must be an array"), "string kit reported, not hard-errored")
	_ok(text.contains("reflexes must be an array"), "string reflexes reported")
	_ok(text.contains("'do' must be an object"), "string reflex do reported")
	_ok(text.contains("effects must be an array"), "string effects reported")
	AG.rebuild()
	EB.clear()

## combat_form hydrates from npcs.json (bram_kell only, for the Kell slice) and the new combat
## fields round-trip through to_dict/from_dict; older saves keep safe defaults.
func _test_combat_form_hydration() -> void:
	print("[combat form hydration (combat M1)]")
	var AG: Object = root.get_node("/root/Agents")
	AG.rebuild()
	var bram: Agent = AG.get_agent("bram_kell")
	# M6 rebind: Kell WEARS the human butcher; bieber_monster is what assume_form makes of him.
	_ok(bram.combat_form == "butcher_human", "bram_kell hydrates combat_form from npcs.json (the worn human form)")
	_ok(AG.get_agent("clerk_voss").combat_form == "", "an npc without the key hydrates an empty combat_form")
	_ok(bram.in_combat == false, "a fresh agent is not in combat")
	bram.in_combat = true
	bram.combat_intent = {"mode": "engage", "target": "player", "style": "desperate", "set_at_beat": 9}
	var b := Agent.new()
	b.from_dict(bram.to_dict())
	_ok(b.in_combat == true, "in_combat round-trips")
	_ok(b.combat_form == "butcher_human", "combat_form round-trips")
	_ok(String(b.combat_intent.get("mode", "")) == "engage" and int(b.combat_intent.get("set_at_beat", -1)) == 9,
		"combat_intent round-trips")
	var c := Agent.new()
	c.from_dict({"id": "x"})
	_ok(c.in_combat == false and c.combat_form == "" and c.combat_intent.is_empty(),
		"older saves default the combat fields")
	AG.rebuild()

## The bound puppet body defers when its agent is in combat: NO glide (the M2 CombatExecutor will
## own position), and leaving combat resumes the strict-puppet glide.
func _test_npc_puppet_combat_hold() -> void:
	print("[npc puppet holds in combat (combat M1)]")
	var Ag: Object = root.get_node("/root/Agents")
	Ag.rebuild()
	var agent = Ag.all()[0]
	agent.in_combat = true
	agent.position = Vector2(777, 333)
	var npc = load("res://scenes/NPC.tscn").instantiate()
	npc.npc_id = agent.id
	root.add_child(npc)
	await process_frame
	_ok(npc.is_bound(), "bound to an in-combat agent")
	npc.global_position = Vector2.ZERO
	for i in 20:
		npc._physics_process(1.0 / 60.0)
	_ok(npc.global_position == Vector2.ZERO,
		"an in-combat body does NOT puppet-glide (position authority left to the M2 executor)")
	agent.in_combat = false
	for i in 20:
		npc._physics_process(1.0 / 60.0)
	_ok(npc.global_position != Vector2.ZERO
		and npc.global_position.distance_to(agent.position) < Vector2(777, 333).length(),
		"leaving combat resumes the glide toward the agent")
	npc.queue_free()
	await process_frame
	Ag.rebuild()

## AbilityDB (plan §M1): abilities.json + combat_forms.json load with honest typed fields; kits
## resolve per form; reflex rows are DATA (consumed in M3); references validate at load.
func _test_ability_db() -> void:
	print("[ability db (combat M1)]")
	var DB: Object = root.get_node("/root/AbilityDB")
	_ok(DB.has_ability("revolver_shot"), "abilities.json loaded revolver_shot")
	var shot: Dictionary = DB.ability_for("revolver_shot")
	_ok(String(shot.get("class", "")) == "projectile", "revolver_shot is a projectile")
	_ok(float(shot.get("cast_time", 0.0)) == 0.25, "…with its 0.25s telegraph")
	_ok(float((shot.get("projectile", {}) as Dictionary).get("speed", 0.0)) == 700.0,
		"…and a projectile speed (collision-dodgeable)")
	var fx: Array = shot.get("effects", [])
	_ok(fx.size() == 1 and String((fx[0] as Dictionary).get("kind", "")) == "damage",
		"…and one typed damage effect")
	var dash: Dictionary = DB.ability_for("dash")
	_ok(String((dash.get("motion", {}) as Dictionary).get("kind", "")) == "dash" and dash.has("i_frames"),
		"dash carries motion + i_frames")
	var charm: Dictionary = DB.ability_for("paper_charm")
	var zone: Dictionary = (charm.get("effects", []) as Array)[0]
	_ok(String(zone.get("kind", "")) == "zone" and (zone.get("statuses", []) as Array).has("slow"),
		"paper_charm's typed zone effect slows")
	# Transformation is an ABILITY (design correction): a long-cast transform with a typed effect.
	var af: Dictionary = DB.ability_for("assume_form")
	_ok(String(af.get("class", "")) == "transform" and float(af.get("cast_time", 0.0)) == 1.2,
		"assume_form is a long-cast transform ability")
	_ok(String(((af.get("effects", []) as Array)[0] as Dictionary).get("form", "")) == "bieber_monster",
		"…whose transform effect names the form")
	# Every ability authors a player-facing display name — the HUD telegraph line renders it
	# (arc-review nit: raw snake_case ids leaked into "X winds up hook_throw!").
	var unnamed: Array = []
	for aid in ["revolver_shot", "dash", "paper_charm", "cleaver_swipe", "charge",
			"hook_throw", "blood_frenzy", "assume_form"]:
		if String((DB.ability_for(aid) as Dictionary).get("name", "")).strip_edges() == "":
			unnamed.append(aid)
	_ok(unnamed.is_empty(), "every ability authors a display name (missing: %s)" % str(unnamed))
	_ok(DB.display_name("revolver_shot") != "" and DB.display_name("revolver_shot") != "revolver_shot",
		"AbilityDB.display_name renders the authored name")
	_ok(DB.display_name("mystery_art") == "mystery art",
		"…and falls back to a de-snaked id for unknown abilities")
	# Kits per combat_form.
	var kit: Array = DB.kit_for("bieber_monster")
	for a in ["cleaver_swipe", "charge", "hook_throw", "blood_frenzy", "assume_form"]:
		_ok(kit.has(a), "bieber_monster kit holds %s" % a)
	_ok((DB.kit_for("player") as Array).has("revolver_shot"), "player kit holds revolver_shot")
	_ok((DB.kit_for("no_such_form") as Array).is_empty(), "unknown form -> empty kit")
	_ok((DB.ability_for("no_such_ability") as Dictionary).is_empty(), "unknown ability -> empty def")
	# Form defs: default style + data reflex rows (schema only tonight; the M3 rule engine consumes
	# them). The assume_form escape hatch belongs to the WORN shape (butcher_human) — the monster
	# carrying a row that casts into itself was the final-review #2 self-stun loop, so the shipped
	# data is pinned both ways: authored on the human, absent from the monster.
	var form: Dictionary = DB.form_def("bieber_monster")
	_ok(String(form.get("default_style", "")) == "aggressive", "bieber_monster defaults aggressive")
	var reflexes: Array = form.get("reflexes", [])
	_ok(reflexes.size() >= 2, "reflex rows load as data")
	var has_dodge := false
	var has_assume := false
	var monster_self_cast := false
	var delays_ok := true
	for r in reflexes:
		var w: Dictionary = (r as Dictionary).get("when", {})
		var doo: Dictionary = (r as Dictionary).get("do", {})
		if delays_ok and (int((r as Dictionary).get("delay_ms", 0)) < 150 or int((r as Dictionary).get("delay_ms", 0)) > 800):
			delays_ok = false
		if String(w.get("kind", "")) == "telegraph" and bool(w.get("at_me", false)) \
				and String(doo.get("kind", "")) == "dodge":
			has_dodge = true
		if String(doo.get("ability", "")) == "assume_form":
			monster_self_cast = true
	for r in (DB.form_def("butcher_human").get("reflexes", []) as Array):
		var w: Dictionary = (r as Dictionary).get("when", {})
		var doo: Dictionary = (r as Dictionary).get("do", {})
		if delays_ok and (int((r as Dictionary).get("delay_ms", 0)) < 150 or int((r as Dictionary).get("delay_ms", 0)) > 800):
			delays_ok = false
		if String(w.get("kind", "")) == "hp_below" and float(w.get("value", 0.0)) == 0.5 \
				and String(doo.get("kind", "")) == "cast" and String(doo.get("ability", "")) == "assume_form":
			has_assume = true
	_ok(has_dodge, "the telegraph-at-me -> dodge reflex row is authored on the monster")
	_ok(has_assume, "butcher_human authors the hp_below 0.5 -> cast assume_form escape hatch")
	_ok(not monster_self_cast, "bieber_monster authors NO row casting assume_form into itself (review #2)")
	_ok(delays_ok, "every reflex delay sits within the 150-800ms human-feel clamp")
	# Reference validation: shipped data is clean; a dangling kit id is caught by name.
	_ok((DB.validate_refs(DB._abilities, DB._forms) as Array).is_empty(),
		"shipped ability/form data has no dangling references")
	var dangle: Array = DB.validate_refs({}, {"x": {"kit": ["no_such"], "reflexes": []}})
	_ok(dangle.size() >= 1 and String(dangle[0]).contains("no_such"),
		"a dangling kit id is reported by name")

## ---- Combat M2 (action layer): pure resolver, executor FSM, projectiles, zones, melee ----
## The resolver tests below are the M9 vector seeds: plain dict in, plain dict out, no nodes.

## A fresh resolver-shape combat state.
func _combat_state(hp: float = 100.0) -> Dictionary:
	return {"hp": hp, "max_hp": 100.0, "statuses": [], "poise": 0.0, "i_frame_until_ms": 0}

## Stage a synthetic fighter in the registry (M2 tests use private rooms so the roster
## never intercepts a projectile). Cleaned up by _end_m2's rebuild().
func _stage_m2(id: String, room_id: String, pos: Vector2, fighting: bool = true) -> Agent:
	var a := Agent.new(id)
	a.display_name = id
	a.room = room_id
	a.position = pos
	a.in_combat = fighting
	root.get_node("/root/Agents")._agents[id] = a
	return a

## Fixed-dt deterministic stepping (60Hz), the same cadence the live _physics_process runs.
func _step_m2(executors: Array, seconds: float) -> void:
	var steps := int(round(seconds * 60.0))
	for i in steps:
		for ex in executors:
			ex.step_combat(1.0 / 60.0)

## Free the staged executors (Nodes, not RefCounted) and restore the real roster.
func _end_m2(executors: Array) -> void:
	for ex in executors:
		ex.free()
	root.get_node("/root/Agents").rebuild()

func _test_resolver_damage_and_shield() -> void:
	print("[resolver damage + shield (combat M2)]")
	var DB: Object = root.get_node("/root/AbilityDB")
	var shot: Dictionary = DB.ability_for("revolver_shot")
	var d: Dictionary = CombatResolver.apply_ability(_combat_state(), _combat_state(), shot,
		{"now_ms": 0, "dir": [1, 0]})
	_ok(float(d.get("damage_dealt", -1.0)) == 26.0, "revolver_shot deals its authored 26")
	_ok(float((d.get("target_state", {}) as Dictionary).get("hp", -1.0)) == 74.0, "target_state hp drops to 74")
	_ok(float((d.get("caster_state", {}) as Dictionary).get("hp", -1.0)) == 100.0, "the caster is untouched")
	_ok(not bool(d.get("dodged", true)) and not bool(d.get("staggered", true)), "no dodge, no stagger")
	var d2: Dictionary = CombatResolver.apply_ability(_combat_state(), _combat_state(), shot,
		{"now_ms": 0, "dir": [1, 0]})
	_ok(float(d2.get("damage_dealt", -1.0)) == 26.0, "the resolver is deterministic (no RNG in damage)")
	# A 20-point shield absorbs BEFORE hp; the remainder lands; the depleted pool is pruned.
	var shielded: Dictionary = CombatResolver.apply_status(_combat_state(),
		{"kind": "shield", "magnitude": 20.0, "duration_ms": 5000, "applied_at_ms": 0})
	d = CombatResolver.apply_ability(_combat_state(), shielded, shot, {"now_ms": 100, "dir": [1, 0]})
	_ok(float(d.get("damage_dealt", -1.0)) == 6.0, "a 20 shield absorbs first (26 -> 6)")
	_ok(float((d.get("target_state", {}) as Dictionary).get("hp", -1.0)) == 94.0, "hp only pays the remainder")
	_ok(not CombatResolver.has_status(d.get("target_state", {}), "shield", 100), "a depleted shield is pruned")
	# A larger shield eats the whole hit and keeps the remainder of its pool.
	var big: Dictionary = CombatResolver.apply_status(_combat_state(),
		{"kind": "shield", "magnitude": 40.0, "duration_ms": 5000, "applied_at_ms": 0})
	d = CombatResolver.apply_ability(_combat_state(), big, shot, {"now_ms": 100, "dir": [1, 0]})
	_ok(float(d.get("damage_dealt", -1.0)) == 0.0, "a 40 shield eats the whole 26")
	_ok(CombatResolver.status_magnitude(d.get("target_state", {}), "shield", 100) == 14.0,
		"…and keeps its remaining 14-point pool")

func _test_resolver_statuses() -> void:
	print("[resolver statuses: stronger-wins stacking, dot ticks, expiry (combat M2)]")
	var s: Dictionary = CombatResolver.apply_status(_combat_state(),
		{"kind": "slow", "magnitude": 0.3, "duration_ms": 1000, "applied_at_ms": 0})
	s = CombatResolver.apply_status(s, {"kind": "slow", "magnitude": 0.6, "duration_ms": 2000, "applied_at_ms": 500})
	_ok((s.get("statuses", []) as Array).size() == 1, "same-kind statuses merge — no stacking multiplication")
	_ok(CombatResolver.status_magnitude(s, "slow", 600) == 0.6, "the STRONGER magnitude wins")
	s = CombatResolver.apply_status(s, {"kind": "slow", "magnitude": 0.2, "duration_ms": 3000, "applied_at_ms": 1000})
	_ok(CombatResolver.has_status(s, "slow", 3500), "a weaker re-apply still refreshes the window")
	_ok(CombatResolver.status_magnitude(s, "slow", 3500) == 0.6, "…but never weakens the magnitude")
	_ok(not CombatResolver.has_status(s, "slow", 4200), "the status expires at the refreshed deadline")
	# Dot ticks accumulate per tick_ms, never double-count, and stop at expiry; expired
	# statuses are pruned. hp is untouched — the CALLER lands dot damage via its damage pipe.
	var burn: Dictionary = CombatResolver.apply_status(_combat_state(),
		{"kind": "dot", "magnitude": 3.0, "duration_ms": 2000, "applied_at_ms": 0, "tick_ms": 500})
	var r: Dictionary = CombatResolver.tick_statuses(burn, 1000)
	_ok(float(r.get("dot_damage", -1.0)) == 6.0, "dot ticks twice by 1000ms (2 x 3)")
	_ok(float((r.get("state", {}) as Dictionary).get("hp", -1.0)) == 100.0,
		"tick_statuses never touches hp (the caller lands it via take_damage)")
	r = CombatResolver.tick_statuses(r.get("state", {}), 1000)
	_ok(float(r.get("dot_damage", -1.0)) == 0.0, "re-ticking the same moment double-counts nothing")
	r = CombatResolver.tick_statuses(r.get("state", {}), 10000)
	_ok(float(r.get("dot_damage", -1.0)) == 6.0, "the remaining ticks land up to expiry, never beyond")
	_ok(((r.get("state", {}) as Dictionary).get("statuses", [null]) as Array).is_empty(),
		"expired statuses are pruned")

func _test_resolver_cooldown_ledger() -> void:
	print("[resolver cooldown ledger (combat M2)]")
	var led: Dictionary = {}
	_ok(CombatResolver.ledger_ready(led, "revolver_shot", 0), "an unmarked ability is ready")
	led = CombatResolver.ledger_mark(led, "revolver_shot", 0, 900)
	_ok(not CombatResolver.ledger_ready(led, "revolver_shot", 899), "marked -> not ready inside the cooldown")
	_ok(CombatResolver.ledger_ready(led, "revolver_shot", 900), "ready again the instant the cooldown ends")
	_ok(CombatResolver.ledger_ready(led, "dash", 0), "other abilities are untouched")
	led = CombatResolver.ledger_mark(led, "revolver_shot", 900, 900)
	_ok(not CombatResolver.ledger_ready(led, "revolver_shot", 1700), "re-marking restarts the clock")

func _test_resolver_poise_iframes_transform() -> void:
	print("[resolver poise -> stagger, i-frames, transform (combat M2)]")
	var DB: Object = root.get_node("/root/AbilityDB")
	var cleaver: Dictionary = DB.ability_for("cleaver_swipe")
	# Poise accumulates across hits; crossing POISE_BREAK staggers and RESETS the pool.
	var d: Dictionary = CombatResolver.apply_ability(_combat_state(), _combat_state(), cleaver,
		{"now_ms": 0, "dir": [1, 0]})
	_ok(float(d.get("poise_damage", 0.0)) > 0.0, "melee carries poise damage")
	_ok(not bool(d.get("staggered", true)), "one hit does not stagger")
	d = CombatResolver.apply_ability(_combat_state(), d.get("target_state", {}), cleaver,
		{"now_ms": 500, "dir": [1, 0]})
	d = CombatResolver.apply_ability(_combat_state(), d.get("target_state", {}), cleaver,
		{"now_ms": 1000, "dir": [1, 0]})
	_ok(bool(d.get("staggered", false)), "accumulated poise past the break threshold staggers")
	_ok(float((d.get("target_state", {}) as Dictionary).get("poise", -1.0)) == 0.0,
		"…and the poise pool resets")
	var kb: Array = d.get("knockback", [])
	_ok(kb.size() == 2 and float(kb[0]) > 0.0 and float(kb[1]) == 0.0,
		"knockback rides the hit direction as [x, y]")
	# I-frames: a hit inside the target's dodge window lands NOTHING.
	var dodge: Dictionary = _combat_state()
	dodge["i_frame_until_ms"] = 400
	var shot: Dictionary = DB.ability_for("revolver_shot")
	d = CombatResolver.apply_ability(_combat_state(), dodge, shot, {"now_ms": 250, "dir": [1, 0]})
	_ok(bool(d.get("dodged", false)), "a hit inside the i-frame window is dodged")
	_ok(float(d.get("damage_dealt", -1.0)) == 0.0, "…dealing zero")
	_ok(float((d.get("target_state", {}) as Dictionary).get("hp", -1.0)) == 100.0
		and float((d.get("target_state", {}) as Dictionary).get("poise", -1.0)) == 0.0,
		"…and leaving hp AND poise untouched")
	d = CombatResolver.apply_ability(_combat_state(), dodge, shot, {"now_ms": 400, "dir": [1, 0]})
	_ok(not bool(d.get("dodged", true)) and float(d.get("damage_dealt", 0.0)) == 26.0,
		"the instant the window closes, hits land again")
	# Transform is a DELTA, not an execution: the resolver only reports transform_to.
	var af: Dictionary = DB.ability_for("assume_form")
	d = CombatResolver.apply_ability(_combat_state(), _combat_state(), af, {"now_ms": 0, "dir": [0, 0]})
	_ok(String(d.get("transform_to", "")) == "bieber_monster", "the transform effect returns transform_to")
	_ok(float(d.get("damage_dealt", -1.0)) == 0.0, "…and deals nothing")

func _test_executor_fsm() -> void:
	print("[executor FSM: windup -> active -> recovery -> idle (combat M2)]")
	var EB: Object = root.get_node("/root/EventBus")
	EB.clear()
	var caster := _stage_m2("m2_caster", "m2_arena", Vector2.ZERO)
	var victim := _stage_m2("m2_victim", "m2_arena", Vector2(40, 0))
	var ex := CombatExecutor.new()
	ex.bind(caster)
	var vex := CombatExecutor.new()
	vex.bind(victim)
	var res: Dictionary = ex.try_cast("cleaver_swipe", "m2_victim")
	_ok(bool(res.get("ok", false)), "an idle executor accepts a cast")
	_ok(ex.phase == "windup", "the cast enters windup")
	_ok(EB.events("ability_cast_started").size() == 1, "windup emits the telegraph (cast_started)")
	_ok(not bool(ex.try_cast("cleaver_swipe", "m2_victim").get("ok", true)), "a busy executor refuses")
	_step_m2([ex, vex], 0.30)
	_ok(ex.phase == "windup", "still winding up before cast_time elapses")
	_ok(victim.hp == 100.0, "no damage lands before the telegraph resolves")
	_step_m2([ex, vex], 0.20)
	_ok(EB.events("ability_cast_finished").size() == 1, "the strike moment emits cast_finished")
	_ok(victim.hp == 66.0, "the melee strike lands its 34 via Agent.take_damage")
	var atk: Array = EB.events("agent_attacked")
	_ok(atk.size() == 1, "the strike emits agent_attacked")
	if atk.size() == 1:
		var pay: Dictionary = atk[0].get("data", {})
		_ok(String(pay.get("actor", "")) == "m2_caster" and String(pay.get("target", "")) == "m2_victim"
			and float(pay.get("damage", 0.0)) == 34.0 and float(pay.get("target_hp", -1.0)) == 66.0
			and pay.has("downed"),
			"…with the existing {actor,target,damage,target_hp,downed} shape (Stimulus keeps working)")
	_step_m2([ex, vex], 0.5)
	_ok(ex.phase == "idle", "active + recovery return the FSM to idle")
	_ok(not bool(ex.try_cast("cleaver_swipe", "m2_victim").get("ok", true)), "the cooldown ledger gates a recast")
	_ok(String(ex.try_cast("cleaver_swipe", "m2_victim").get("reason", "")) == "cooldown", "…named as such")
	_ok(not bool(ex.try_cast("no_such_ability").get("ok", true)), "an unknown ability is refused")
	_end_m2([ex, vex])

func _test_executor_windup_interruption() -> void:
	print("[executor: stagger interrupts windup, silence blocks it (combat M2)]")
	var EB: Object = root.get_node("/root/EventBus")
	EB.clear()
	var caster := _stage_m2("m2_icaster", "m2_arena_i", Vector2.ZERO)
	var attacker := _stage_m2("m2_iattacker", "m2_arena_i", Vector2(200, 0))
	var ex := CombatExecutor.new()
	ex.bind(caster)
	_ok(bool(ex.try_cast("assume_form").get("ok", false)), "the long transform cast starts")
	_step_m2([ex], 0.1)
	_ok(ex.phase == "windup", "mid-windup")
	# A poise-breaking blow mid-windup: interrupt + brief stun + knockback over ~150ms.
	var slam: Dictionary = {"id": "test_slam", "cast_time": 0.0, "cooldown": 0.0,
		"effects": [{"kind": "damage", "amount": 5}], "poise_damage": 100.0, "knockback": 30.0}
	var deltas: Dictionary = ex.receive_hit(attacker, slam, Vector2(1, 0))
	_ok(bool(deltas.get("staggered", false)), "the blow breaks poise")
	_ok(ex.phase == "idle", "the windup is interrupted")
	var ints: Array = EB.events("ability_cast_interrupted")
	_ok(ints.size() == 1 and String((ints[0].get("data", {}) as Dictionary).get("reason", "")) == "stagger",
		"cast_interrupted is emitted with reason=stagger")
	_ok(CombatResolver.has_status(ex.state, "stun", ex.now_ms()), "the stagger leaves a brief stun")
	_ok(String(ex.try_cast("assume_form").get("reason", "")) == "stunned", "stunned blocks a new cast")
	_ok(caster.hp == 95.0, "the blow's damage still landed through take_damage")
	_step_m2([ex], 0.2)
	_ok(caster.position.x > 25.0, "the knockback shoved the agent along the hit direction")
	_step_m2([ex], 0.3)
	# Silence blocks the START of any windup, never an instant motion (dash has no windup).
	ex.receive_status({"kind": "silence", "magnitude": 1.0, "duration_ms": 800, "applied_at_ms": 0})
	_ok(String(ex.try_cast("assume_form").get("reason", "")) == "silenced", "silence blocks a windup start")
	_ok(bool(ex.try_cast("dash", "", Vector2(0, 1)).get("ok", false)), "…but never a windup-less movement")
	_step_m2([ex], 0.9)
	_ok(ex.phase == "idle", "the dash ran to completion")
	_ok(caster.position.y > 100.0, "…moving the agent its authored distance")
	# Silence expired -> the transform finally goes through and flips combat_form.
	_ok(bool(ex.try_cast("assume_form").get("ok", false)), "with silence expired, the cast starts")
	_step_m2([ex], 1.3)
	_ok(caster.combat_form == "bieber_monster", "the transform delta updates Agent.combat_form")
	_end_m2([ex])

func _test_executor_projectile() -> void:
	print("[executor projectile: hit, miss-by-displacement, max range (combat M2)]")
	var EB: Object = root.get_node("/root/EventBus")
	EB.clear()
	var shooter := _stage_m2("m2_shooter", "m2_range", Vector2.ZERO)
	var mark := _stage_m2("m2_mark", "m2_range", Vector2(300, 0))
	var sx := CombatExecutor.new()
	sx.bind(shooter)
	var mx := CombatExecutor.new()
	mx.bind(mark)
	_ok(bool(sx.try_cast("revolver_shot", "m2_mark").get("ok", false)), "the shot casts")
	_step_m2([sx, mx], 0.3)
	_ok(sx.projectiles.size() == 1, "the windup's end spawns the projectile")
	_ok(mark.hp == 100.0, "nothing lands before the projectile arrives (telegraph -> travel -> hit)")
	_step_m2([sx, mx], 0.5)
	_ok(mark.hp == 74.0, "the projectile hit lands via take_damage")
	_ok(EB.events("agent_attacked").size() == 1, "…emitting agent_attacked")
	_ok(sx.projectiles.is_empty(), "the projectile despawns on hit")
	# Miss purely by geometry: the flight line is locked at spawn; the mark steps aside.
	_step_m2([sx, mx], 0.2)
	_ok(bool(sx.try_cast("revolver_shot", "m2_mark").get("ok", false)), "the cooldown elapsed; recast")
	_step_m2([sx, mx], 0.3)
	_ok(sx.projectiles.size() == 1, "second projectile in flight")
	mark.position.y += 60.0
	_step_m2([sx, mx], 1.0)
	_ok(mark.hp == 74.0, "displacement out of the locked path dodges the projectile entirely")
	_ok(EB.events("agent_attacked").size() == 1, "no second agent_attacked")
	_ok(sx.projectiles.is_empty(), "the missed projectile despawns at max range")
	_end_m2([sx, mx])

func _test_executor_zone() -> void:
	print("[executor zone: tick application + silence integration (combat M2)]")
	var EB: Object = root.get_node("/root/EventBus")
	EB.clear()
	var caster := _stage_m2("m2_zcaster", "m2_zone", Vector2.ZERO)
	var victim := _stage_m2("m2_zvictim", "m2_zone", Vector2(50, 0))
	var cx := CombatExecutor.new()
	cx.bind(caster)
	var vx := CombatExecutor.new()
	vx.bind(victim)
	_ok(bool(cx.try_cast("paper_charm", "m2_zvictim").get("ok", false)), "the charm casts")
	_step_m2([cx, vx], 0.7)
	_ok(cx.zones.size() == 1, "the cast plants the zone")
	_ok(CombatResolver.has_status(vx.state, "slow", vx.now_ms()), "a zone tick applies slow to whoever stands inside")
	_ok(CombatResolver.has_status(vx.state, "silence", vx.now_ms()), "…and silence")
	_ok(not CombatResolver.has_status(cx.state, "slow", cx.now_ms()), "the zone never bites its owner")
	_ok(String(vx.try_cast("assume_form").get("reason", "")) == "silenced",
		"the silenced victim cannot START a windup (charm counters the transform)")
	_step_m2([cx, vx], 4.2)
	_ok(cx.zones.is_empty(), "the zone expires after its authored duration")
	_end_m2([cx, vx])

func _test_executor_melee_dedup() -> void:
	print("[executor melee: one swing hits once (combat M2)]")
	var EB: Object = root.get_node("/root/EventBus")
	EB.clear()
	var basher := _stage_m2("m2_basher", "m2_dedup", Vector2.ZERO)
	var victim := _stage_m2("m2_dvictim", "m2_dedup", Vector2(30, 0))
	var bx := CombatExecutor.new()
	bx.bind(basher)
	var vx := CombatExecutor.new()
	vx.bind(victim)
	_ok(bool(bx.try_cast("cleaver_swipe", "m2_dvictim").get("ok", false)), "the swing casts")
	_step_m2([bx, vx], 0.8)
	_ok(EB.events("agent_attacked").size() == 1,
		"the whole active window lands ONE hit (per-swing dedup)")
	_ok(victim.hp == 66.0, "damage applied exactly once")
	_end_m2([bx, vx])

func _test_executor_dash_iframes() -> void:
	print("[executor dash i-frames zero a projectile hit (combat M2)]")
	var EB: Object = root.get_node("/root/EventBus")
	EB.clear()
	var shooter := _stage_m2("m2_ishooter", "m2_dash", Vector2.ZERO)
	var dodger := _stage_m2("m2_idodger", "m2_dash", Vector2(200, 0))
	var sx := CombatExecutor.new()
	sx.bind(shooter)
	var dx := CombatExecutor.new()
	dx.bind(dodger)
	_ok(bool(sx.try_cast("revolver_shot", "m2_idodger").get("ok", false)), "the shot casts")
	_step_m2([sx, dx], 0.3)
	_ok(sx.projectiles.size() == 1, "projectile in flight")
	# The dodger dashes INTO the projectile's path — geometry alone would be a hit; the
	# dash's i-frame window is what zeroes it.
	_ok(bool(dx.try_cast("dash", "", Vector2(-1, 0)).get("ok", false)), "the dodger dashes")
	_step_m2([sx, dx], 0.9)
	_ok(dodger.hp == 100.0, "the i-frame window zeroes the projectile hit")
	_ok(EB.events("agent_attacked").is_empty(), "no agent_attacked was emitted")
	_ok(dodger.position.x < 200.0, "the dash really moved the dodger through the path")
	_ok(sx.projectiles.is_empty(), "the projectile flew on and despawned at max range")
	_end_m2([sx, dx])

func _test_executor_damage_downs() -> void:
	print("[executor damage downs + existing event wiring (combat M2)]")
	var EB: Object = root.get_node("/root/EventBus")
	EB.clear()
	var brute := _stage_m2("m2_brute", "m2_downs", Vector2.ZERO)
	var frail := _stage_m2("m2_frail", "m2_downs", Vector2(40, 0), false)   # NOT in combat, NO executor
	var bx := CombatExecutor.new()
	bx.bind(brute)
	_ok(bool(bx.try_cast("cleaver_swipe", "m2_frail").get("ok", false)), "the swing casts")
	_step_m2([bx], 0.6)
	_ok(frail.hp == 66.0, "an executor-less agent is still hit (fallback path, take_damage)")
	_ok(frail.in_combat, "damage flips the victim into combat mode (M1 wiring intact)")
	_ok(EB.events("combat_started").size() == 1, "combat_started published once")
	frail.hp = 20.0
	_step_m2([bx], 0.7)
	_ok(bool(bx.try_cast("cleaver_swipe", "m2_frail").get("ok", false)), "cooldown elapsed; second swing")
	_step_m2([bx], 0.6)
	_ok(frail.downed, "the lethal strike downs (never deletes)")
	var downs: Array = EB.events("agent_downed")
	_ok(downs.size() == 1, "agent_downed emitted exactly once (EndGame-compatible shape)")
	if downs.size() == 1:
		var pay: Dictionary = downs[0].get("data", {})
		_ok(String(pay.get("actor", "")) == "m2_brute" and String(pay.get("target", "")) == "m2_frail",
			"…with {actor, target}")
	var atk: Array = EB.events("agent_attacked")
	_ok(atk.size() == 2 and bool((atk[1].get("data", {}) as Dictionary).get("downed", false))
		and float((atk[1].get("data", {}) as Dictionary).get("target_hp", -1.0)) == 0.0,
		"the felling blow's agent_attacked reports downed + target_hp 0")
	_end_m2([bx])

## NPC.gd fills the M1 seam: entering combat spawns a bound CombatExecutor child (which
## adds the body's Hurtbox); leaving combat frees it and the puppet glide resumes.
func _test_npc_spawns_executor() -> void:
	print("[npc spawns/frees executor on combat enter/exit (combat M2)]")
	var AG: Object = root.get_node("/root/Agents")
	AG.rebuild()
	var agent = AG.all()[0]
	agent.in_combat = false
	var npc = load("res://scenes/NPC.tscn").instantiate()
	npc.npc_id = agent.id
	root.add_child(npc)
	await process_frame
	_ok(npc.combat_executor() == null, "out of combat there is no executor")
	agent.in_combat = true
	npc._physics_process(1.0 / 60.0)
	var ex = npc.combat_executor()
	_ok(ex != null, "entering combat spawns a CombatExecutor child")
	_ok(ex != null and ex.agent == agent, "…bound to the agent")
	_ok(ex != null and ex.body == npc, "…and to this body")
	_ok(npc.has_node("CombatHurtbox"), "the body gains a Hurtbox Area2D child")
	_ok(ex != null and ex.hurtbox_radius > 0.0, "…sized from the body's existing collision")
	agent.in_combat = false
	npc._physics_process(1.0 / 60.0)
	_ok(npc.combat_executor() == null, "leaving combat frees the executor (puppet resumes)")
	npc.queue_free()
	await process_frame
	AG.rebuild()

## ---- Combat M3 (tactical layer + compiled reflexes) ----
## TacticalBrain/ReflexRules pure cores are the M9 vector seeds; the staged blocks pin the
## executor wiring (perceiver gate, scheduled reactions, steering, transform execution).

## Events of `type` whose data[key] == val — the M3 blocks filter the log constantly.
func _events_by(EB: Object, type: String, key: String, val: String) -> Array:
	return EB.events(type).filter(func(e: Dictionary) -> bool:
		return String((e.get("data", {}) as Dictionary).get(key, "")) == val)

func _test_perceiver_gate() -> void:
	print("[perceiver gate: ONE shared vision function (combat M3)]")
	var viewer := Agent.new("m3_viewer")
	viewer.room = "m3_room"
	viewer.position = Vector2.ZERO
	viewer.vision_r = 100.0
	_ok(Perception.can_perceive(viewer, "m3_room", Vector2(80, 0)), "same room, inside vision_r -> perceived")
	_ok(not Perception.can_perceive(viewer, "m3_room", Vector2(101, 0)), "same room, beyond the VIEWER's vision_r -> blocked")
	_ok(not Perception.can_perceive(viewer, "other_room", Vector2(10, 0)), "another room -> blocked (rooms are separate spaces)")
	_ok(Perception.can_perceive(viewer, "m3_room", null), "no event position -> room co-location alone decides")
	_ok(not Perception.can_perceive(null, "m3_room", null), "a null viewer perceives nothing")

func _test_reflex_rules_vectors() -> void:
	print("[reflex rules: pure trigger/action vectors (combat M3)]")
	var rules: Array = [
		{"when": {"kind": "telegraph", "of": "projectile", "at_me": true}, "do": {"kind": "dodge"}, "delay_ms": 220, "max_fires": 2},
		{"when": {"kind": "hp_below", "value": 0.5}, "do": {"kind": "cast", "ability": "assume_form"}, "delay_ms": 250, "max_fires": 1},
		{"when": {"kind": "ally_downed"}, "do": {"kind": "style", "style": "desperate"}, "delay_ms": 100},
		{"when": {"kind": "band_entered", "band": "melee"}, "do": {"kind": "cast", "ability": "cleaver_swipe"}, "delay_ms": 5000},
		{"when": {"kind": "cooldown_ready", "ability": "charge"}, "do": {"kind": "cast", "ability": "charge"}, "delay_ms": 300},
		{"when": {"kind": "telegraph", "ability": "paper_charm"}, "do": {"kind": "flee"}, "delay_ms": 200},
	]
	var healthy := {"hp_frac": 1.0}
	var tele := {"kind": "telegraph", "ability": "revolver_shot", "class": "projectile", "at_me": true, "caster": "x"}
	var due: Array = ReflexRules.evaluate(rules, tele, healthy, 1000, {})
	_ok(due.size() == 1, "a projectile telegraph at me matches exactly the dodge row")
	if due.size() == 1:
		var r: Dictionary = due[0]
		_ok(String((r.get("do", {}) as Dictionary).get("kind", "")) == "dodge", "…returning its authored action")
		_ok(int(r.get("delay_ms", 0)) == 220 and int(r.get("fire_at_ms", 0)) == 1220,
			"…with its delay and fire_at_ms = now + delay")
		_ok(int(r.get("rule_index", -1)) == 0, "…and the rule's index (the caller's fired_counts key)")
	var aside := tele.duplicate(true)
	aside["at_me"] = false
	_ok((ReflexRules.evaluate(rules, aside, healthy, 0, {}) as Array).is_empty(),
		"a telegraph aimed elsewhere never matches an at_me row")
	var spell_tele := {"kind": "telegraph", "ability": "some_spell", "class": "spell", "at_me": true}
	_ok((ReflexRules.evaluate(rules, spell_tele, healthy, 0, {}) as Array).is_empty(),
		"a wrong-class telegraph never matches an of-keyed row")
	var charm_tele := {"kind": "telegraph", "ability": "paper_charm", "class": "spell", "at_me": false}
	var charm_due: Array = ReflexRules.evaluate(rules, charm_tele, healthy, 0, {})
	_ok(charm_due.size() == 1 and int((charm_due[0] as Dictionary).get("rule_index", -1)) == 5,
		"an ability-keyed telegraph row matches by ability id")
	# hp_below reads SELF STATE (evaluated each frame), not an event.
	var low := {"hp_frac": 0.4}
	var hp_due: Array = ReflexRules.evaluate(rules, {}, low, 5000, {})
	_ok(hp_due.size() == 1 and int((hp_due[0] as Dictionary).get("rule_index", -1)) == 1,
		"hp below the threshold fires the hp_below row on a bare frame evaluation")
	_ok(int((hp_due[0] as Dictionary).get("fire_at_ms", 0)) == 5250, "…scheduled at now + its delay")
	_ok((ReflexRules.evaluate(rules, {}, {"hp_frac": 0.6}, 0, {}) as Array).is_empty(),
		"hp above the threshold fires nothing")
	_ok((ReflexRules.evaluate(rules, {}, low, 0, {1: 1}) as Array).is_empty(),
		"max_fires: an exhausted row never fires again (fired_counts enforced)")
	_ok((ReflexRules.evaluate(rules, tele, healthy, 0, {0: 2}) as Array).is_empty(),
		"…the dodge row too, at its own cap")
	var both: Array = ReflexRules.evaluate(rules, tele, low, 0, {})
	_ok(both.size() == 2, "one evaluation returns EVERY due row (telegraph + hp_below)")
	var ally_due: Array = ReflexRules.evaluate(rules, {"kind": "ally_downed", "agent": "y"}, healthy, 0, {})
	_ok(ally_due.size() == 1 and int((ally_due[0] as Dictionary).get("delay_ms", 0)) == 150,
		"ally_downed fires; a 100ms delay is clamped UP to the 150ms floor")
	var band_due: Array = ReflexRules.evaluate(rules, {"kind": "band_entered", "band": "melee"}, healthy, 0, {})
	_ok(band_due.size() == 1 and int((band_due[0] as Dictionary).get("delay_ms", 0)) == 800,
		"band_entered fires; a 5000ms delay is clamped DOWN to the 800ms ceiling")
	_ok((ReflexRules.evaluate(rules, {"kind": "band_entered", "band": "near"}, healthy, 0, {}) as Array).is_empty(),
		"the wrong band never matches")
	var cd_due: Array = ReflexRules.evaluate(rules, {"kind": "cooldown_ready", "ability": "charge"}, healthy, 0, {})
	_ok(cd_due.size() == 1 and int((cd_due[0] as Dictionary).get("rule_index", -1)) == 4, "cooldown_ready fires by ability")
	_ok((ReflexRules.evaluate(rules, {"kind": "cooldown_ready", "ability": "hook_throw"}, healthy, 0, {}) as Array).is_empty(),
		"…and only for ITS ability")
	# Purity: evaluate never mutates its inputs — the CALLER owns clocks and counts.
	var counts := {0: 1}
	var before_rules: Array = rules.duplicate(true)
	ReflexRules.evaluate(rules, tele, healthy, 0, counts)
	_ok(counts == {0: 1}, "evaluate never increments fired_counts (the caller does, at schedule time)")
	_ok(rules == before_rules, "evaluate never mutates the rules")

func _test_tactical_bands() -> void:
	print("[tactical bands derive from kit DATA (combat M3)]")
	var DB: Object = root.get_node("/root/AbilityDB")
	var kit_defs: Array = []
	for a in DB.kit_for("bieber_monster"):
		kit_defs.append(DB.ability_for(String(a)))
	var bands: Dictionary = TacticalBrain.bands_for(kit_defs)
	_ok(float(bands.get("melee", 0.0)) == 70.0, "melee band = the kit's max strike range (cleaver 70)")
	_ok(float(bands.get("near", 0.0)) == 420.0, "near band = the kit's max projectile range (hook 420)")
	var empty: Dictionary = TacticalBrain.bands_for([])
	_ok(float(empty.get("melee", 0.0)) == 48.0 and float(empty.get("near", 0.0)) == 160.0,
		"an empty kit degrades to the engine defaults (48/160)")
	var strike_only: Dictionary = TacticalBrain.bands_for([{"id": "x", "class": "strike", "range": 90}])
	_ok(float(strike_only.get("melee", 0.0)) == 90.0 and float(strike_only.get("near", 0.0)) == 180.0,
		"a projectile-less kit derives near = 2x melee (floored at the default)")
	_ok(TacticalBrain.band_of(50.0, bands) == "melee" and TacticalBrain.band_of(70.0, bands) == "melee",
		"inside (and at) melee range -> melee band")
	_ok(TacticalBrain.band_of(300.0, bands) == "near" and TacticalBrain.band_of(420.0, bands) == "near",
		"between melee and projectile range -> near band")
	_ok(TacticalBrain.band_of(500.0, bands) == "far", "beyond projectile range -> far")

func _test_tactical_style_masks() -> void:
	print("[tactical style masks: one selector, four postures (combat M3)]")
	var DB: Object = root.get_node("/root/AbilityDB")
	var kit_defs: Array = []
	for a in DB.kit_for("bieber_monster"):
		kit_defs.append(DB.ability_for(String(a)))
	var bands: Dictionary = TacticalBrain.bands_for(kit_defs)
	# THE fixed scenario: melee-range standoff, everything off cooldown, full hp, no recent hit.
	var view := {"kit": kit_defs, "dist": 60.0, "ledger": {}, "now_ms": 0, "hp_frac": 1.0,
		"recent_hit": false, "bands": bands, "current_form": "bieber_monster"}
	var agg: Dictionary = TacticalBrain.choose(view, "aggressive")
	var cau: Dictionary = TacticalBrain.choose(view, "cautious")
	var def: Dictionary = TacticalBrain.choose(view, "defensive")
	var des: Dictionary = TacticalBrain.choose(view, "desperate")
	_ok(String(agg.get("cast", "")) == "cleaver_swipe"
		and String((agg.get("steer", {}) as Dictionary).get("kind", "")) == "strafe",
		"aggressive: highest-damage strike + stays on top (cleaver_swipe / strafe)")
	_ok(String(cau.get("cast", "")) == "hook_throw"
		and String((cau.get("steer", {}) as Dictionary).get("kind", "")) == "back_away",
		"cautious: prefers the projectile + restores the near band (hook_throw / back_away)")
	_ok(String(def.get("cast", "")) == ""
		and String((def.get("steer", {}) as Dictionary).get("kind", "")) == "hold",
		"defensive: counters only — no hit taken in 2s, no cast, holds ground")
	_ok(String(des.get("cast", "")) == "cleaver_swipe"
		and String((des.get("steer", {}) as Dictionary).get("kind", "")) == "pursue",
		"desperate: shortest cooldown + closes recklessly (cleaver_swipe / pursue)")
	_ok(agg != cau and agg != def and agg != des and cau != def and cau != des and def != des,
		"the SAME state under four masks yields four pairwise-distinct decisions")
	# Counter window: the moment defensive HAS been hit, it answers.
	var struck := view.duplicate(true)
	struck["recent_hit"] = true
	_ok(String((TacticalBrain.choose(struck, "defensive") as Dictionary).get("cast", "")) == "cleaver_swipe",
		"defensive casts once a hit landed within the 2s counter window")
	# Range fall-through: out of melee, aggressive closes with the damaging gap-closer.
	var far_view := view.duplicate(true)
	far_view["dist"] = 300.0
	var agg_far: Dictionary = TacticalBrain.choose(far_view, "aggressive")
	_ok(String(agg_far.get("cast", "")) == "charge"
		and String((agg_far.get("steer", {}) as Dictionary).get("kind", "")) == "pursue"
		and float((agg_far.get("steer", {}) as Dictionary).get("stop_at", -1.0)) == 70.0,
		"aggressive at 300px: charge to close + pursue to the melee band")
	var cau_far: Dictionary = TacticalBrain.choose(far_view, "cautious")
	_ok(String(cau_far.get("cast", "")) == "hook_throw"
		and String((cau_far.get("steer", {}) as Dictionary).get("kind", "")) == "strafe",
		"cautious at 300px sits happily in its near band: projectile + strafe")
	# Cooldown mask: with the strike cooling, aggressive falls through its class preference.
	var cooling := view.duplicate(true)
	cooling["ledger"] = {"cleaver_swipe": 10000}
	_ok(String((TacticalBrain.choose(cooling, "aggressive") as Dictionary).get("cast", "")) == "charge",
		"a cooling preferred class falls through to the next ready one")
	# Hp policy: cautious retreats when critical; desperate never preserves itself.
	var hurt_view := view.duplicate(true)
	hurt_view["hp_frac"] = 0.2
	_ok(String((TacticalBrain.choose(hurt_view, "cautious") as Dictionary).get("steer", {}).get("kind", "")) == "back_away",
		"cautious at critical hp retreats")
	_ok(String((TacticalBrain.choose(hurt_view, "desperate") as Dictionary).get("steer", {}).get("kind", "")) == "pursue",
		"desperate at critical hp still closes (ignores hp preservation)")
	# The monster reveal is NEVER an engine rule (§0): the deterministic tactical layer must
	# not choose a transform on its own — only reflex rows / the LLM / a GM directive cast it.
	var human_view := view.duplicate(true)
	human_view["current_form"] = "butcher_human"
	human_view["ledger"] = {"cleaver_swipe": 10000, "charge": 10000, "hook_throw": 10000, "blood_frenzy": 10000}
	_ok(String((TacticalBrain.choose(human_view, "aggressive") as Dictionary).get("cast", "")) == "",
		"a transform is never a tactical pick, even as the only ready ability")
	_ok(String((TacticalBrain.choose(human_view, "desperate") as Dictionary).get("cast", "")) == "",
		"…under any mask (the reveal belongs to reflex data / the LLM / the GM)")
	_ok(TacticalBrain.choose(view, "no_such_style") == agg, "an unknown style degrades to aggressive")

## M9: the language-neutral combat vectors (agent-sidecar/cognition/combat_test_vectors.json)
## run IN-SUITE for CI-equivalence — the standalone runner (tests/run_combat_vectors.gd) and
## this block share the same fill/compare statics, and its pass/fail counts fold into ours.
## The SAME fixtures must pass in Yumina's TS port (COMBAT_SPEC.md); expected values are
## machine-generated by tests/dump_combat_vectors.gd — never hand-edit them.
func _test_combat_vectors() -> void:
	print("[combat vectors (M9 back-port spec)]")
	var runner := load("res://tests/run_combat_vectors.gd")
	var r: Dictionary = runner.run_all()
	_passed += int(r.get("passed", 0))
	_failed += int(r.get("failed", 0))
	_ok(int(r.get("failed", 1)) == 0 and int(r.get("passed", 0)) > 0,
		"combat vectors green (%d checks against the shipped fixtures)" % int(r.get("passed", 0)))

func _test_tactical_default_posture() -> void:
	print("[tactical default posture: no intent -> face the last attacker (combat M3)]")
	var EB: Object = root.get_node("/root/EventBus")
	EB.clear()
	var kell := _stage_m2("m3_kell", "m3_posture", Vector2.ZERO)
	kell.combat_form = "bieber_monster"
	var thug := _stage_m2("m3_thug", "m3_posture", Vector2(300, 0))
	var kx := CombatExecutor.new()
	kx.bind(kell)
	kx.enable_tactics()
	var tx := CombatExecutor.new()
	tx.bind(thug)
	_step_m2([kx, tx], 0.5)
	_ok(kell.position == Vector2.ZERO, "no intent + no attacker yet -> the tactical layer holds ground")
	_ok(_events_by(EB, "ability_cast_started", "caster", "m3_kell").is_empty(), "…and casts nothing")
	kx.receive_hit(thug, {"id": "test_jab", "cast_time": 0.0, "effects": [{"kind": "damage", "amount": 5}]}, Vector2(-1, 0))
	_ok(kx.last_attacker_id == "m3_thug", "a routed hit records last_attacker_id on the executor")
	_step_m2([kx, tx], 1.0)
	_ok(kell.position.x > 0.0, "default posture: closes on the most recent attacker (form default aggressive)")
	var casts: Array = _events_by(EB, "ability_cast_started", "caster", "m3_kell")
	_ok(casts.size() >= 1
		and String((casts[0].get("data", {}) as Dictionary).get("target", "")) == "m3_thug",
		"…and casts against that attacker, unprompted by any intent")
	_end_m2([kx, tx])

func _test_tactical_protect() -> void:
	print("[tactical protect: body between ward and threat (combat M3)]")
	var EB: Object = root.get_node("/root/EventBus")
	EB.clear()
	# The pure post math first (M9-seedable).
	_ok(TacticalBrain.protect_post(Vector2.ZERO, Vector2(200, 0)) == Vector2(48, 0),
		"the guard post sits on the ward->threat line, guard_r out")
	_ok(TacticalBrain.protect_post(Vector2(100, 100), Vector2(100, 300)) == Vector2(100, 148), "…on any axis")
	_ok(TacticalBrain.protect_post(Vector2.ZERO, Vector2(60, 0)) == Vector2(30, 0),
		"a close threat halves the gap instead of overshooting past it")
	_ok(TacticalBrain.protect_post(Vector2(5, 5), Vector2(5, 5)) == Vector2(5, 5), "a threat ON the ward -> stand at the ward")
	# Staged: guard with a protect intent, ward, and a brute who strikes the ward.
	var guard := _stage_m2("m3_guard", "m3_protect", Vector2(0, 200))
	guard.combat_form = "bieber_monster"
	guard.combat_intent = {"mode": "protect", "agent": "m3_ward", "set_at_beat": 0}
	var ward := _stage_m2("m3_ward", "m3_protect", Vector2(200, 200), false)
	var brute := _stage_m2("m3_brute", "m3_protect", Vector2(500, 200))
	var gx := CombatExecutor.new()
	gx.bind(guard)
	gx.enable_tactics()
	var bx := CombatExecutor.new()
	bx.bind(brute)
	_step_m2([gx, bx], 2.0)
	_ok(guard.position.distance_to(ward.position) <= 60.0,
		"with no known threat the guard closes to and holds near the ward")
	CombatExecutor.land_fallback_hit(brute, ward,
		{"id": "test_jab", "effects": [{"kind": "damage", "amount": 5}]}, Vector2(-1, 0))
	_ok(CombatExecutor.last_attacker_of("m3_ward") == "m3_brute",
		"whoever last damaged the ward is a cheap static lookup")
	_step_m2([gx, bx], 2.0)
	var post := TacticalBrain.protect_post(ward.position, brute.position)
	_ok(guard.position.distance_to(post) <= 12.0, "the guard takes the post between ward and threat")
	_ok(_events_by(EB, "ability_cast_started", "caster", "m3_guard").is_empty(),
		"a threat outside the ward's melee band is watched, not engaged")
	brute.position = Vector2(260, 200)
	_step_m2([gx, bx], 1.0)
	var gcasts: Array = _events_by(EB, "ability_cast_started", "caster", "m3_guard")
	_ok(gcasts.size() >= 1
		and String((gcasts[0].get("data", {}) as Dictionary).get("target", "")) == "m3_brute",
		"a threat entering the ward's melee band is engaged")
	_end_m2([gx, bx])

func _test_tactical_disengage() -> void:
	print("[tactical disengage: sustained distance exits combat (combat M3)]")
	var EB: Object = root.get_node("/root/EventBus")
	EB.clear()
	var runner := _stage_m2("m3_runner", "m3_disengage", Vector2.ZERO)
	runner.combat_form = "bieber_monster"
	runner.combat_intent = {"mode": "disengage", "via": "", "set_at_beat": 0}
	var chaser := _stage_m2("m3_chaser", "m3_disengage", Vector2(100, 0))
	var rx := CombatExecutor.new()
	rx.bind(runner)
	rx.enable_tactics()
	_step_m2([rx], 1.0)
	_ok(runner.position.x < 0.0, "disengage backs away from the nearest combatant")
	_ok(runner.in_combat, "…but stays in combat inside the exit radius")
	# Exit needs > 2x the far band (2x420 = 840px) SUSTAINED for 2s: at 140px/s from 100px,
	# the runner crosses 840 at ~5.3s and may exit from ~7.3s.
	_step_m2([rx], 5.0)
	_ok(runner.in_combat, "beyond the radius but inside the 2s dwell -> still in combat")
	_step_m2([rx], 4.0)
	_ok(not runner.in_combat, "sustained >2x far-band for 2s exits combat")
	_ok(_events_by(EB, "combat_ended", "agent", "m3_runner").size() == 1, "…via CombatMode (combat_ended published)")
	_end_m2([rx])
	# A named via nav point steers the retreat toward it (ActionCommit.NAV_SITES).
	ActionCommit.set_nav_site("m3_bolt_hole", Vector2(0, 900), "m3_disengage2")
	var bolter := _stage_m2("m3_bolter", "m3_disengage2", Vector2.ZERO)
	bolter.combat_form = "bieber_monster"
	bolter.combat_intent = {"mode": "disengage", "via": "m3_bolt_hole", "set_at_beat": 0}
	var foe := _stage_m2("m3_foe", "m3_disengage2", Vector2(120, 0))
	var bx2 := CombatExecutor.new()
	bx2.bind(bolter)
	bx2.enable_tactics()
	_step_m2([bx2], 2.0)
	_ok(bolter.position.y > 200.0, "a named via nav point steers the retreat toward it")
	_end_m2([bx2])
	# A via point in ANOTHER room is wrong-space — ignored in favor of the away vector.
	ActionCommit.set_nav_site("m3_wrong_room", Vector2(0, 900), "elsewhere")
	var wary := _stage_m2("m3_wary_runner", "m3_disengage3", Vector2.ZERO)
	wary.combat_form = "bieber_monster"
	wary.combat_intent = {"mode": "disengage", "via": "m3_wrong_room", "set_at_beat": 0}
	var foe2 := _stage_m2("m3_foe2", "m3_disengage3", Vector2(120, 0))
	var wx := CombatExecutor.new()
	wx.bind(wary)
	wx.enable_tactics()
	_step_m2([wx], 1.0)
	_ok(wary.position.x < 0.0 and wary.position.y == 0.0,
		"a via point in another room is ignored (away vector instead, never wrong-space coords)")
	_end_m2([wx])
	ActionCommit.NAV_SITES.erase("m3_bolt_hole")
	ActionCommit.NAV_SITES.erase("m3_wrong_room")

func _test_reflex_executor_wiring() -> void:
	print("[reflexes ride the perceived channel + executor clock (combat M3)]")
	var EB: Object = root.get_node("/root/EventBus")
	EB.clear()
	# (a) The perceiver gate: an OUT-OF-VISION telegraph schedules nothing.
	var dodger := _stage_m2("m3_dodger", "m3_reflex", Vector2.ZERO)
	dodger.combat_form = "bieber_monster"
	dodger.vision_r = 100.0
	var sniper := _stage_m2("m3_sniper", "m3_reflex", Vector2(400, 0))
	var dx := CombatExecutor.new()
	dx.bind(dodger)
	var sx := CombatExecutor.new()
	sx.bind(sniper)
	_ok(bool(sx.try_cast("revolver_shot", "m3_dodger").get("ok", false)), "the sniper fires from beyond the dodger's vision")
	_step_m2([dx, sx], 0.5)
	_ok(dodger.position == Vector2.ZERO, "an out-of-vision telegraph fires NO reflex (perceiver gate)")
	_step_m2([dx, sx], 0.5)
	_ok(dodger.hp == 74.0, "…and the unseen round lands")
	# (b) In vision, the SAME telegraph dodges — no dash in the bieber kit -> strafe burst.
	dodger.vision_r = 500.0
	_ok(bool(sx.try_cast("revolver_shot", "m3_dodger").get("ok", false)), "second shot, now within vision")
	_step_m2([dx, sx], 0.4)
	_ok(dodger.position.y != 0.0, "an in-vision telegraph at me dodges: no dash in kit -> strafe burst")
	var hp_before := dodger.hp
	_step_m2([dx, sx], 0.8)
	_ok(dodger.hp == hp_before, "…and the burst displaces out of the locked flight line (no hit)")
	_end_m2([dx, sx])
	# (c) A dodge with dash IN the kit casts dash (i-frames + displacement).
	EB.clear()
	var cat := _stage_m2("m3_cat", "m3_reflex2", Vector2.ZERO)
	cat.combat_form = "player"
	cat.vision_r = 500.0   # the gunman must be SEEN for the telegraph to reach the reflex
	var cx := CombatExecutor.new()
	cx.bind(cat)
	cx.set_reflex_rules([{"when": {"kind": "telegraph", "of": "projectile", "at_me": true},
		"do": {"kind": "dodge"}, "delay_ms": 200, "max_fires": 5}])
	var gunman := _stage_m2("m3_gunman", "m3_reflex2", Vector2(300, 0))
	var gx2 := CombatExecutor.new()
	gx2.bind(gunman)
	gx2.try_cast("revolver_shot", "m3_cat")
	_step_m2([cx, gx2], 0.35)
	_ok(_events_by(EB, "ability_cast_started", "caster", "m3_cat").size() == 1
		and String(((_events_by(EB, "ability_cast_started", "caster", "m3_cat")[0]).get("data", {}) as Dictionary).get("ability", "")) == "dash",
		"a dodge with dash in kit CASTS dash instead of strafing")
	_end_m2([cx, gx2])
	# (d) A style reaction overrides combat_intent.style in place.
	EB.clear()
	var wary2 := _stage_m2("m3_wary", "m3_reflex3", Vector2.ZERO)
	wary2.combat_form = "bieber_monster"
	wary2.combat_intent = {"mode": "engage", "target": "m3_gunman3", "style": "aggressive", "set_at_beat": 0}
	var gunman3 := _stage_m2("m3_gunman3", "m3_reflex3", Vector2(100, 0))
	var friend := _stage_m2("m3_friend", "m3_reflex3", Vector2(50, 50))
	var wx2 := CombatExecutor.new()
	wx2.bind(wary2)
	wx2.set_reflex_rules([{"when": {"kind": "ally_downed"}, "do": {"kind": "style", "style": "desperate"}, "delay_ms": 150}])
	friend.hp = 3.0
	CombatExecutor.land_fallback_hit(gunman3, friend,
		{"id": "test_jab", "effects": [{"kind": "damage", "amount": 10}]}, Vector2(1, 0))
	_ok(friend.downed, "the bystander falls in view")
	_step_m2([wx2], 0.3)
	_ok(String(wary2.combat_intent.get("style", "")) == "desperate",
		"an ally_downed style reaction overrides combat_intent.style in place")
	_end_m2([wx2])
	# (e) A flee reaction latches disengage behavior on the tactical layer.
	EB.clear()
	var mouse := _stage_m2("m3_mouse", "m3_reflex4", Vector2.ZERO)
	mouse.combat_form = "bieber_monster"
	var mx := CombatExecutor.new()
	mx.bind(mouse)
	mx.enable_tactics()
	mx.set_reflex_rules([{"when": {"kind": "telegraph", "of": "projectile", "at_me": true},
		"do": {"kind": "flee"}, "delay_ms": 150}])
	var wolf := _stage_m2("m3_wolf", "m3_reflex4", Vector2(150, 0))
	var wfx := CombatExecutor.new()
	wfx.bind(wolf)
	wfx.try_cast("revolver_shot", "m3_mouse")
	_step_m2([mx, wfx], 1.0)
	_ok(mx.reflex_flee, "a flee reaction latches the executor's flee mode")
	_ok(mouse.position.x < 0.0, "…and the tactical layer backs away (disengage behavior)")
	_end_m2([mx, wfx])

func _test_transform_execution() -> void:
	print("[transform executes: form swap + kit reload + transformed event (combat M3)]")
	var EB: Object = root.get_node("/root/EventBus")
	EB.clear()
	var shape := _stage_m2("m3_shape", "m3_transform", Vector2.ZERO)
	shape.combat_form = "butcher_human"
	var sx := CombatExecutor.new()
	sx.bind(shape)
	_ok(sx._reflex_rules.size() == 2, "bind loads the current form's reflex rows")
	_ok(bool(sx.try_cast("assume_form").get("ok", false)), "the transform ability casts")
	_ok(shape.combat_form == "butcher_human", "nothing swaps during the telegraph")
	_step_m2([sx], 1.4)
	_ok(shape.combat_form == "bieber_monster", "the transform's resolution swaps Agent.combat_form")
	var tevents: Array = EB.events("transformed")
	_ok(tevents.size() == 1, "a `transformed` event is emitted")
	if tevents.size() == 1:
		var d: Dictionary = tevents[0].get("data", {})
		_ok(String(d.get("agent", "")) == "m3_shape" and String(d.get("form", "")) == "bieber_monster",
			"…carrying {agent, form}")
	_ok((root.get_node("/root/AbilityDB").kit_for(shape.combat_form) as Array).has("charge"),
		"the kit reloads with the new form's abilities")
	_ok(sx._reflex_rules.size() == 2, "…and the new form's reflex rows take over")
	_step_m2([sx], 0.4)
	_ok(bool(sx.try_cast("assume_form").get("ok", false)), "a recast is accepted (no cooldown authored)")
	_step_m2([sx], 1.8)
	_ok(EB.events("transformed").size() == 1,
		"transforming into the CURRENT form re-emits nothing (no transform loop)")
	_end_m2([sx])

## Final-review #2's durable half: even if a form's DATA authors a transform reflex into the very
## form being worn (the shipped row was removed; a future author may reintroduce one), the executor
## consumes the reaction unfired — no 1.2s self-stun cast loop. The worn shape's genuine escape
## hatch (butcher_human -> bieber_monster) must keep firing through the same path.
func _test_transform_reflex_guard() -> void:
	print("[a transform reflex into the worn form is consumed unfired (final-review #2)]")
	var EB: Object = root.get_node("/root/EventBus")
	EB.clear()
	var looper := _stage_m2("m3_looper", "m3_selfcast", Vector2.ZERO)
	looper.combat_form = "bieber_monster"
	looper.vision_r = 500.0
	var lx := CombatExecutor.new()
	lx.bind(looper)
	lx.set_reflex_rules([{"when": {"kind": "hp_below", "value": 0.5},
		"do": {"kind": "cast", "ability": "assume_form"}, "delay_ms": 150}])
	var goon := _stage_m2("m3_goon", "m3_selfcast", Vector2(80, 0))
	CombatExecutor.land_fallback_hit(goon, looper,
		{"id": "test_jab", "effects": [{"kind": "damage", "amount": 60}]}, Vector2(1, 0))
	_ok(looper.hp < 50.0, "the monster is beaten below the trigger line")
	_step_m2([lx], 1.0)
	var self_casts := 0
	for e in (EB.events("ability_cast_started") as Array):
		var d: Dictionary = e.get("data", {})
		if String(d.get("caster", "")) == "m3_looper" and String(d.get("ability", "")) == "assume_form":
			self_casts += 1
	_ok(self_casts == 0, "a reflex casting into the CURRENT form is consumed unfired (no self-stun loop)")
	_ok(String(looper.combat_form) == "bieber_monster" and not looper.downed,
		"…the worn form stands untouched")
	_end_m2([lx])
	# The genuine hatch still fires: the same rule on the WORN human shape transforms as authored.
	EB.clear()
	var kell := _stage_m2("m3_kell", "m3_selfcast2", Vector2.ZERO)
	kell.combat_form = "butcher_human"
	kell.vision_r = 500.0
	var kx := CombatExecutor.new()
	kx.bind(kell)
	kx.set_reflex_rules([{"when": {"kind": "hp_below", "value": 0.5},
		"do": {"kind": "cast", "ability": "assume_form"}, "delay_ms": 150}])
	var goon2 := _stage_m2("m3_goon2", "m3_selfcast2", Vector2(80, 0))
	CombatExecutor.land_fallback_hit(goon2, kell,
		{"id": "test_jab", "effects": [{"kind": "damage", "amount": 60}]}, Vector2(1, 0))
	_step_m2([kx], 2.0)
	_ok(String(kell.combat_form) == "bieber_monster",
		"the worn shape's escape hatch still fires through the same reflex path")
	_end_m2([kx])

func _test_civilian_flees() -> void:
	print("[civilian: empty kit -> immediate flight (combat M3)]")
	var EB: Object = root.get_node("/root/EventBus")
	EB.clear()
	var DB: Object = root.get_node("/root/AbilityDB")
	_ok((DB.kit_for("civilian") as Array).is_empty()
		and String((DB.form_def("civilian") as Dictionary).get("default_style", "")) == "cautious",
		"the civilian form is authored: empty kit, cautious default")
	var civ := _stage_m2("m3_civ", "m3_civ_room", Vector2.ZERO)
	civ.combat_form = "civilian"
	var cvx := CombatExecutor.new()
	cvx.bind(civ)
	cvx.enable_tactics()
	var thug := _stage_m2("m3_thug2", "m3_civ_room", Vector2(80, 0))
	_step_m2([cvx], 1.0)
	_ok(civ.position.x < -50.0, "a combat-flipped civilian (empty kit) immediately flees")
	_ok(_events_by(EB, "ability_cast_started", "caster", "m3_civ").is_empty(), "…and never casts")
	_step_m2([cvx], 4.5)
	_ok(not civ.in_combat, "…and exits combat once clear (sustained 2x far-band)")
	_ok(_events_by(EB, "combat_ended", "agent", "m3_civ").size() == 1, "combat_ended published")
	_end_m2([cvx])

## ---- M2 adversarial review: SHIP-WITH-FIXES items, folded into M3 (TDD'd here) ----
func _test_m2_review_fixes() -> void:
	print("[m2 review fixes (folded into M3)]")
	var EB: Object = root.get_node("/root/EventBus")
	# (1) MUST: a downed caster finishes NOTHING — mid-windup downing interrupts the cast.
	EB.clear()
	var gunner := _stage_m2("m3_gunner", "m3_review", Vector2.ZERO)
	var bystander := _stage_m2("m3_bystander", "m3_review", Vector2(200, 0))
	var gx := CombatExecutor.new()
	gx.bind(gunner)
	var bx := CombatExecutor.new()
	bx.bind(bystander)
	_ok(bool(gx.try_cast("revolver_shot", "m3_bystander").get("ok", false)), "the shot starts")
	_step_m2([gx, bx], 0.1)
	gunner.hp = 4.0
	gx.receive_hit(bystander, {"id": "test_finisher", "effects": [{"kind": "damage", "amount": 10}]}, Vector2(-1, 0))
	_ok(gunner.downed, "the counter-blow downs the caster mid-windup")
	_step_m2([gx, bx], 1.5)
	var ints: Array = _events_by(EB, "ability_cast_interrupted", "caster", "m3_gunner")
	_ok(ints.size() == 1
		and String((ints[0].get("data", {}) as Dictionary).get("reason", "")) == "downed",
		"downing mid-windup emits cast_interrupted reason=downed")
	_ok(gx.projectiles.is_empty(), "no projectile ever spawns from a downed caster")
	_ok(bystander.hp == 100.0, "…and the intended victim is untouched")
	_end_m2([gx, bx])
	# (2) MUST: in-flight rounds outlive their caster's executor (neutral orphan stepper).
	EB.clear()
	var shooter := _stage_m2("m3_shooter", "m3_review2", Vector2.ZERO)
	var target := _stage_m2("m3_target", "m3_review2", Vector2(400, 0))
	var shx := CombatExecutor.new()
	shx.bind(shooter)
	var tgx := CombatExecutor.new()
	tgx.bind(target)
	shx.try_cast("revolver_shot", "m3_target")
	_step_m2([shx, tgx], 0.3)
	_ok(shx.projectiles.size() == 1, "round in flight")
	# Earlier M3 blocks may legitimately have orphaned strays of their own — count relatively.
	var orphans_before := CombatExecutor.orphan_count()
	shx.free()
	_ok(CombatExecutor.orphan_count() == orphans_before + 1,
		"the surviving round is adopted by the neutral stepper")
	for i in 60:
		CombatExecutor.step_orphans(1.0 / 60.0)
		tgx.step_combat(1.0 / 60.0)
	_ok(target.hp == 74.0, "an orphaned round still lands (its caster's death doesn't erase it)")
	_ok(CombatExecutor.orphan_count() == 0, "…and the spent rounds are freed")
	_end_m2([tgx])
	# (3) MUST: a follow-up `attack` commit no longer wipes the standing combat intent.
	var striker := _stage_m2("m3_striker", "m3_review3", Vector2.ZERO)
	var foe_a := _stage_m2("m3_foe_a", "m3_review3", Vector2(30, 0))
	ActionCommit.commit({"verb": "engage", "args": {"target": "m3_foe_a", "style": "cautious"}}, striker)
	_ok(String(striker.combat_intent.get("mode", "")) == "engage", "engage publishes the intent")
	ActionCommit.commit({"verb": "attack", "args": {"target": "m3_foe_a"}}, striker)
	_ok(String(striker.combat_intent.get("mode", "")) == "engage"
		and String(striker.combat_intent.get("style", "")) == "cautious",
		"attack is a combat verb: the stance survives it")
	ActionCommit.commit({"verb": "idle", "args": {}}, striker)
	_ok(striker.combat_intent.is_empty(), "a non-combat decision still supersedes the stance")
	_end_m2([])
	# (5) Zone status names must carry authored defaults, or the zone silently no-ops.
	var DB: Object = root.get_node("/root/AbilityDB")
	var doctored := {"bad_zone": {"id": "bad_zone", "class": "spell",
		"effects": [{"kind": "zone", "radius": 10, "duration": 1.0, "tick": 0.5, "statuses": ["dot"]}]}}
	var problems: Array = DB.validate_refs(doctored, {})
	_ok(problems.size() == 1 and String(problems[0]).contains("dot"),
		"a zone naming a status with no authored default is reported by name")
	_ok((DB.validate_refs(DB._abilities, DB._forms) as Array).is_empty(), "shipped data stays clean")
	# (6) The telegraph advertises the EFFECTIVE windup, not the authored one.
	EB.clear()
	var speedy := _stage_m2("m3_speedy", "m3_review4", Vector2.ZERO)
	var px := CombatExecutor.new()
	px.bind(speedy)
	px.receive_status({"kind": "frenzy", "magnitude": 2.0, "duration_ms": 5000, "applied_at_ms": 0})
	px.try_cast("cleaver_swipe")
	var tel: Array = _events_by(EB, "ability_cast_started", "caster", "m3_speedy")
	_ok(tel.size() == 1
		and absf(float((tel[0].get("data", {}) as Dictionary).get("cast_time", 0.0)) - 0.225) < 0.0001,
		"a frenzied cast telegraphs its EFFECTIVE windup (0.45 -> 0.225)")
	_step_m2([px], 0.24)
	_ok(px.phase != "windup", "…matching the real strike moment (reflex windows depend on it)")
	_end_m2([px])
	# (LOW, pinned) An interrupted cast still burns its cooldown.
	EB.clear()
	var mage := _stage_m2("m3_mage", "m3_review5", Vector2.ZERO)
	var mgx := CombatExecutor.new()
	mgx.bind(mage)
	mgx.try_cast("cleaver_swipe")
	mgx.receive_status({"kind": "stun", "magnitude": 1.0, "duration_ms": 100, "applied_at_ms": 0})
	_ok(mgx.phase == "idle", "the stun interrupted the windup")
	_step_m2([mgx], 0.2)
	_ok(String(mgx.try_cast("cleaver_swipe").get("reason", "")) == "cooldown",
		"an interrupted cast still burns its cooldown (pinned as designed)")
	_end_m2([mgx])
	# (LOW) A cross-room target is wrong-space: the cast never aims by its coordinates.
	EB.clear()
	var archer := _stage_m2("m3_archer", "m3_review6", Vector2.ZERO)
	var ghost := _stage_m2("m3_ghost", "m3_review_other_room", Vector2(500, 500))
	var ax := CombatExecutor.new()
	ax.bind(archer)
	_ok(bool(ax.try_cast("revolver_shot", "m3_ghost").get("ok", false)), "the cast is accepted")
	var atel: Array = _events_by(EB, "ability_cast_started", "caster", "m3_archer")
	_ok(atel.size() == 1 and (atel[0].get("data", {}) as Dictionary).get("dir") == [1.0, 0.0],
		"…but a cross-room target never aims it (falls back to the default axis)")
	_end_m2([ax])

## ---- M4: intent integration (combat plan §M4) ----

func _test_perception_combat_forwarding() -> void:
	print("[perception combat forwarding (combat M4)]")
	var AG: Object = root.get_node("/root/Agents")
	var DB: Object = root.get_node("/root/AbilityDB")
	AG.rebuild()
	CombatExecutor.reset_last_attackers()
	var voss: Agent = AG.get_agent("clerk_voss")
	var dalia: Agent = AG.get_agent("fishwife_dalia")
	var pell: Agent = AG.get_agent("dockhand_pell")
	voss.room = "city"
	voss.position = Vector2(400, 300)
	dalia.room = "city"
	dalia.position = Vector2(410, 300)
	dalia.in_combat = true
	pell.room = "city"
	pell.position = Vector2(420, 300)
	pell.in_combat = false
	for a in AG.all():   # park the rest out of vision so the roster is exactly {dalia, pell}
		if not a.id in ["clerk_voss", "fishwife_dalia", "dockhand_pell"]:
			a.position = Vector2(9000, 9000)
	var beat_now: int = int(root.get_node("/root/Clock").beat_index)
	voss.in_combat = true
	voss.combat_form = "butcher_human"
	voss.combat_intent = {"mode": "engage", "target": "player", "style": "aggressive",
		"set_at_beat": beat_now - 2}
	CombatExecutor._last_attacker["clerk_voss"] = "player"   # the executor hit ledger's fact
	var snap: Dictionary = Perception.build_snapshot(voss, voss.position)
	_ok(bool(snap.get("in_combat", false)), "snapshot carries in_combat")
	_ok(String(snap.get("combat_form", "")) == "butcher_human", "snapshot carries combat_form")
	_ok(String(snap.get("last_attacker", "")) == "player",
		"snapshot carries the executor ledger's last_attacker")
	_ok(String((snap.get("combat_intent", {}) as Dictionary).get("target", "")) == "player",
		"snapshot carries the OWN combat_intent in full detail")
	# The kit summary is data straight from AbilityDB — id + class + the authored description.
	var ids := {}
	for k in (snap.get("kit", []) as Array):
		ids[String((k as Dictionary).get("id", ""))] = k
	_ok(ids.has("cleaver_swipe") and ids.has("assume_form"), "the worn form's kit rides the snapshot")
	_ok(String((ids.get("cleaver_swipe", {}) as Dictionary).get("class", "")) == "strike",
		"a kit entry carries its class")
	var authored := String((DB.ability_for("assume_form") as Dictionary).get("description", ""))
	_ok(authored != ""
		and String((ids.get("assume_form", {}) as Dictionary).get("description", "")) == authored,
		"a kit entry's description IS the authored abilities.json text (assume_form: neutral-but-known)")
	# nearby: whether a peer is visibly fighting is a public fact, like `doing`.
	var by_id := {}
	for n in (snap.get("nearby", []) as Array):
		by_id[String((n as Dictionary).get("id", ""))] = n
	_ok(bool((by_id.get("fishwife_dalia", {}) as Dictionary).get("in_combat", false)),
		"a visibly fighting neighbor carries in_combat true in nearby")
	_ok(not bool((by_id.get("dockhand_pell", {}) as Dictionary).get("in_combat", true)),
		"a peaceful neighbor carries in_combat false")
	# /decide forwarding: the mask + the combat detail; set_beats_ago is computed for the brain.
	var rc: Dictionary = Perception.decide_request(snap, "sess-m4")
	var perc: Dictionary = rc["perception"]
	_ok(bool(perc.get("in_combat", false)), "decide_request forwards in_combat")
	_ok(String(perc.get("last_attacker", "")) == "player", "decide_request forwards last_attacker")
	_ok(int((perc.get("combat_intent", {}) as Dictionary).get("set_beats_ago", -1)) == 2,
		"decide_request computes set_beats_ago from the beat clock")
	_ok((perc.get("kit", []) as Array).size() == (snap.get("kit", []) as Array).size(),
		"decide_request forwards the kit summary")
	# Out of combat: the flag is false and NO combat detail rides (lean legacy shape) — the
	# static ledger outlives fights, so its stale fact must not leak into a peaceful beat.
	voss.in_combat = false
	voss.combat_intent = {}
	var snap2: Dictionary = Perception.build_snapshot(voss, voss.position)
	_ok(String(snap2.get("last_attacker", "")) == "",
		"outside combat the stale ledger fact is not forwarded")
	_ok((snap2.get("kit", []) as Array).is_empty(), "outside combat no kit rides the snapshot")
	var rc2: Dictionary = Perception.decide_request(snap2, "sess-m4")
	var perc2: Dictionary = rc2["perception"]
	_ok(not bool(perc2.get("in_combat", true)), "decide_request forwards in_combat false")
	_ok(not perc2.has("combat_intent") and not perc2.has("last_attacker") and not perc2.has("kit"),
		"a peaceful request carries none of the combat detail keys")
	# A legacy snapshot shape (no combat keys at all) still round-trips.
	var legacy := {"agent_id": "x", "beat": 3, "short_memory": [], "mem_total": 0, "nearby": [],
		"pressures": {}, "position": [0.0, 0.0]}
	var rl: Dictionary = Perception.decide_request(legacy, "sess-m4")
	_ok(not bool((rl["perception"] as Dictionary).get("in_combat", true)),
		"a legacy snapshot defaults to in_combat false")
	CombatExecutor.reset_last_attackers()
	AG.rebuild()

func _test_ambient_combat_ladder() -> void:
	print("[ambient combat ladder (combat M4)]")
	var amb := AmbientSidecar.new()
	# A task-bearer struck by a known attacker STILL IN VIEW engages it, aggressive — its work is
	# threatened. (The attacker rides `nearby`: a remembered name alone is not a target, below.)
	var struck := {"agent_id": "cult_a", "beat": 3, "in_combat": true,
		"task": {"ritual": "summoning_descent", "site": "crypt_altar"},
		"last_attacker": "player", "kit": [],
		"nearby": [{"id": "player", "distance": 60.0, "in_combat": true}], "position": [0.0, 0.0]}
	var a0: Dictionary = amb.propose([struck])[0]
	_ok(String(a0.get("verb", "")) == "engage", "task-bearer in combat -> engage")
	_ok(String((a0.get("args", {}) as Dictionary).get("target", "")) == "player", "…the last attacker")
	_ok(String((a0.get("args", {}) as Dictionary).get("style", "")) == "aggressive", "…aggressively")
	# No known attacker: the nearest visibly FIGHTING neighbor wins over a nearer bystander;
	# downed bodies are never threats.
	var unknown := {"agent_id": "cult_b", "beat": 3, "in_combat": true,
		"task": {"ritual": "summoning_descent"},
		"nearby": [
			{"id": "bystander", "distance": 10.0, "in_combat": false},
			{"id": "downed_foe", "distance": 5.0, "in_combat": true, "hp_band": "downed"},
			{"id": "investigator", "distance": 40.0, "in_combat": true},
		], "position": [0.0, 0.0]}
	var a1: Dictionary = amb.propose([unknown])[0]
	_ok(String(a1.get("verb", "")) == "engage"
		and String((a1.get("args", {}) as Dictionary).get("target", "")) == "investigator",
		"no attacker known -> engage the nearest standing combatant (downed bodies skipped)")
	# A kit-bearing taskless agent also fights — its body has arts (only the true civilian flees).
	var armed := {"agent_id": "brute", "beat": 3, "in_combat": true,
		"kit": [{"id": "cleaver_swipe", "class": "strike", "description": "x"}],
		"last_attacker": "player",
		"nearby": [{"id": "player", "distance": 60.0, "in_combat": true}], "position": [0.0, 0.0]}
	var a2: Dictionary = amb.propose([armed])[0]
	_ok(String(a2.get("verb", "")) == "engage", "a taskless agent with arts still engages")
	# HIT-AND-RUN (final-review #1): the attacker struck and LEFT — the remembered name is absent
	# from this snapshot's roster. Without the visibility check the fighter froze at the fight spot
	# forever, engaging a target its tactical layer could never reach. Alone -> break off…
	var ghosted := {"agent_id": "cult_g", "beat": 4, "in_combat": true,
		"task": {"ritual": "summoning_descent"},
		"last_attacker": "player", "nearby": [], "position": [0.0, 0.0]}
	var ag: Dictionary = amb.propose([ghosted])[0]
	_ok(String(ag.get("verb", "")) == "disengage",
		"a vanished attacker is no target: struck-and-abandoned fighter breaks off (review #1)")
	# …but with another combatant standing in view, the fight passes to the visible threat.
	var ghosted2 := {"agent_id": "cult_h", "beat": 4, "in_combat": true,
		"task": {"ritual": "summoning_descent"},
		"last_attacker": "player",
		"nearby": [{"id": "investigator", "distance": 40.0, "in_combat": true}], "position": [0.0, 0.0]}
	var ah: Dictionary = amb.propose([ghosted2])[0]
	_ok(String(ah.get("verb", "")) == "engage"
		and String((ah.get("args", {}) as Dictionary).get("target", "")) == "investigator",
		"…unless another combatant stands in view — the fight passes to the visible threat")
	# A true civilian — no task, no arts — breaks off.
	var civ := {"agent_id": "civ", "beat": 3, "in_combat": true, "kit": [],
		"last_attacker": "player", "nearby": [], "position": [0.0, 0.0]}
	var a3: Dictionary = amb.propose([civ])[0]
	_ok(String(a3.get("verb", "")) == "disengage", "civilian (no task, empty kit) -> disengage")
	# A task-bearer with no one visible to fight also breaks off (nothing to engage).
	var alone := {"agent_id": "cult_c", "beat": 3, "in_combat": true,
		"task": {"ritual": "summoning_descent"}, "nearby": [], "position": [0.0, 0.0]}
	var a4: Dictionary = amb.propose([alone])[0]
	_ok(String(a4.get("verb", "")) == "disengage", "a fighter with no visible threat breaks off")
	# The ladder emits only schema-legal intent verbs — they ride the NORMAL pipeline.
	_ok(bool(ActionSchema.validate({"actor": "x", "verb": "engage",
			"args": {"target": "t", "style": "aggressive"}})["ok"])
		and bool(ActionSchema.validate({"actor": "x", "verb": "disengage", "args": {}})["ok"]),
		"the ladder emits only schema-legal intent verbs")
	# Out of combat the ladder is untouched: the same task-bearer walks its errand.
	var peaceful := {"agent_id": "cult_a", "beat": 3, "in_combat": false,
		"task": {"ritual": "summoning_descent", "site": "crypt_altar"},
		"nearby": [], "position": [0.0, 0.0]}
	var a5: Dictionary = amb.propose([peaceful])[0]
	_ok(String(a5.get("verb", "")) != "engage" and String(a5.get("verb", "")) != "disengage",
		"a peaceful beat never emits a combat intent")

func _test_coordinator_skips_combatants() -> void:
	print("[coordinator skips in-combat agents (combat M4)]")
	var AG: Object = root.get_node("/root/Agents")
	var SP: Object = root.get_node("/root/SummoningPlan")
	var CO: Object = root.get_node("/root/Coordinator")
	AG.rebuild()
	SP.reset()
	SP.ritual_requirement = {"ritual_salt": 1, "consecrated_chalk": 1, "candle": 1}
	SP.deposited = {}
	var voss: Agent = AG.get_agent("clerk_voss")
	var dalia: Agent = AG.get_agent("fishwife_dalia")
	var orin: Agent = AG.get_agent("lamplighter_orin")
	for a in [voss, dalia, orin]:
		a.inventory.clear()
		a.downed = false
		a.in_combat = false
	# An engaged member gets no allocation; the free members still cover distinct materials.
	voss.in_combat = true
	_ok(CO.focus_for(voss.id).is_empty(), "an engaged cult member gets NO allocation")
	var fd: Dictionary = CO.focus_for(dalia.id)
	var fo: Dictionary = CO.focus_for(orin.id)
	_ok(not fd.is_empty() and not fo.is_empty(), "the free members still get allocations")
	_ok(String(fd.get("subtask", "")) != String(fo.get("subtask", "")),
		"…covering distinct materials (the partition routes around the fighter)")
	# What a fighter CARRIES stays claimed — it rides in their pack, unfetchable — and
	# all_claimed is unaffected when carriers (fighting or not) hold everything outstanding.
	voss.inventory.clear()
	voss.add_item("ritual_salt", 1)
	dalia.inventory.clear()
	dalia.add_item("consecrated_chalk", 1)
	dalia.add_item("candle", 1)
	orin.inventory.clear()
	_ok(String(CO.focus_for(orin.id).get("subtask", "")) != "ritual_salt",
		"a material in the FIGHTER's pack is never allocated to a walker")
	_ok(bool(CO.focus_for(orin.id).get("all_claimed", false)),
		"all_claimed unaffected: every outstanding material is in plan-members' hands")
	voss.in_combat = false
	voss.inventory.clear()
	dalia.inventory.clear()
	SP.reset()
	AG.rebuild()

func _test_cast_ability_seam() -> void:
	print("[cast_ability: schema + critic gate + commit routes to the executor (combat M4)]")
	var EB: Object = root.get_node("/root/EventBus")
	EB.clear()
	# Schema: the verb exists (shared verbatim with the sidecar; parity is tested separately).
	_ok(ActionSchema.is_verb("cast_ability"), "cast_ability is a known verb")
	_ok(ActionSchema.required_args("cast_ability") == ["ability"], "cast_ability requires its ability")
	# Critic: a PROPOSAL is legal only in a fight; a directive bypasses the Critic (schema only).
	var shape := _stage_m2("m4_shape", "m4_cast", Vector2.ZERO, false)
	shape.combat_form = "butcher_human"
	var proposal := {"actor": "m4_shape", "verb": "cast_ability", "args": {"ability": "assume_form"}}
	_ok(String(Critic.review(proposal, shape)["verdict"]) == "veto",
		"the Critic vetoes a proposed cast_ability outside combat")
	shape.in_combat = true
	_ok(String(Critic.review(proposal, shape)["verdict"]) == "approve",
		"…and approves it for an agent already in a fight")
	shape.in_combat = false
	# Commit on a NOT-yet-fighting agent (the GM-forced case): enters combat, parks the cast.
	var out: Dictionary = ActionCommit.commit(proposal, shape)
	_ok(shape.in_combat, "cast_ability on a peaceful agent ENTERS combat first")
	_ok(_events_by(EB, "combat_started", "agent", "m4_shape").size() == 1, "…publishing combat_started")
	_ok(bool(out.get("ok", false)) and bool(out.get("pending", false)),
		"…and PARKS the cast (no executor is live yet)")
	_ok(shape.pending_cast == "assume_form", "the parked cast waits on the agent")
	# The executor consumes the parked cast on its own clock -> telegraph -> transform (M3 stack).
	var ex := CombatExecutor.new()
	ex.bind(shape)
	_step_m2([ex], 2.0)
	_ok(_events_by(EB, "ability_cast_started", "caster", "m4_shape").size() == 1,
		"the executor telegraphs the parked cast")
	_ok(shape.combat_form == "bieber_monster", "…and the transform resolves through the M3 machinery")
	_ok(EB.events("transformed").size() == 1, "transformed is published once")
	_ok(shape.pending_cast == "", "the parked cast is consumed")
	# A LIVE idle executor takes the cast immediately (pending=false), aimed by the standing intent.
	var mark := _stage_m2("m4_mark", "m4_cast", Vector2(50, 0))
	shape.combat_intent = {"mode": "engage", "target": "m4_mark", "style": "aggressive", "set_at_beat": 0}
	var out2: Dictionary = ActionCommit.commit(
		{"actor": "m4_shape", "verb": "cast_ability", "args": {"ability": "cleaver_swipe"}}, shape)
	_ok(bool(out2.get("ok", false)) and not bool(out2.get("pending", false)),
		"a live idle executor takes the cast immediately")
	_ok(not shape.combat_intent.is_empty(), "cast_ability never wipes the standing stance (like attack)")
	_ok(mark.id == "m4_mark", "a mark stands in reach for the swing")
	# An unknown art is a safe no-op that flips nothing.
	var calm := _stage_m2("m4_calm", "m4_cast", Vector2(400, 0), false)
	var out3: Dictionary = ActionCommit.commit(
		{"actor": "m4_calm", "verb": "cast_ability", "args": {"ability": "nonsense"}}, calm)
	_ok(not bool(out3.get("ok", true)) and String(out3.get("reason", "")) == "unknown_ability"
		and not calm.in_combat, "an unknown art is refused without entering combat")
	# Leaving the fight abandons a parked cast.
	calm.pending_cast = "assume_form"
	calm.in_combat = true
	root.get_node("/root/CombatMode").exit_combat(calm)
	_ok(calm.pending_cast == "", "exit_combat clears a parked cast")
	_end_m2([ex])

func _test_corruption_transform_directive() -> void:
	print("[corruption loss-of-control -> GM transform directive (combat M4)]")
	var AG: Object = root.get_node("/root/Agents")
	var EB: Object = root.get_node("/root/EventBus")
	var OV: Object = root.get_node("/root/Overseer")
	var WS: Object = root.get_node("/root/WorldState")
	var ART: Object = root.get_node("/root/AgentRuntime")
	var SB: Object = root.get_node("/root/SidecarBridge")
	AG.rebuild()
	OV.reset()
	EB.clear()
	var was_corruption: float = WS.corruption
	# Stand-ins: the butcher-human seam (M6 binds the real Kell), an already-transformed
	# monster (its assume_form points back at the worn form), and a form with no transform art.
	var kell: Agent = AG.get_agent("clerk_voss")
	kell.combat_form = "butcher_human"
	var monster: Agent = AG.get_agent("lamplighter_orin")
	monster.combat_form = "bieber_monster"
	var meek: Agent = AG.get_agent("dockhand_pell")
	meek.combat_form = "civilian"
	# Below the threshold the Director does nothing.
	_ok((OV.check_corruption_transforms(AG.all(), 84.9) as Array).is_empty(),
		"below the threshold no one is directed")
	_ok(not OV.has_directive(kell.id), "…no directive queued")
	# The threshold crossing DIRECTS the still-untransformed transform-capable agent — only it.
	WS.set_pressure("corruption", 80.0)
	WS.adjust("corruption", 10.0)   # 80 -> 90 emits world_var_changed; the Overseer sweeps
	_ok(OV.has_directive(kell.id), "crossing the threshold issues the transform directive")
	_ok(not OV.has_directive(monster.id), "an already-transformed form is never re-directed")
	_ok(not OV.has_directive(meek.id), "a form with no transform art is skipped")
	var directive: Dictionary = OV.take_directive(kell.id)
	_ok(String(directive.get("verb", "")) == "cast_ability"
		and String((directive.get("args", {}) as Dictionary).get("ability", "")) == "assume_form",
		"the directive is the schema-legal cast_ability {ability: assume_form}")
	# M6 REBIND: the REAL bram_kell def (straight from npcs.json, no stand-in dressing) now wears
	# butcher_human, whose kit still holds a transform art into a DIFFERENT form — so the same
	# sweep judges HIM not-yet-transformed and directs him too. (Before the rebind he wore
	# bieber_monster directly and the sweep skipped him.)
	_ok(OV.has_directive("bram_kell"), "the rebound bram_kell (real npcs.json def) is directed by the same sweep")
	var kell_directive: Dictionary = OV.take_directive("bram_kell")
	_ok(String(kell_directive.get("verb", "")) == "cast_ability"
		and String((kell_directive.get("args", {}) as Dictionary).get("ability", "")) == "assume_form",
		"…with the schema-legal cast_ability {ability: assume_form} against his real worn form")
	# Latch: further corruption movement never re-issues, and the latch survives save/load.
	WS.adjust("corruption", 5.0)
	_ok(not OV.has_directive(kell.id), "the crossing fires ONCE per agent (latch)")
	OV.from_dict(OV.to_dict())
	WS.adjust("corruption", 1.0)
	_ok(not OV.has_directive(kell.id), "…and the latch survives a to_dict/from_dict round-trip")
	# FULL CHAIN, headless: re-arm (reset clears the latch), cross the threshold again, run the
	# beat (directive -> ActionCommit -> combat mode + parked cast), then step an executor.
	OV.reset()
	EB.clear()
	WS.set_pressure("corruption", 80.0)
	WS.adjust("corruption", 10.0)
	_ok(OV.has_directive(kell.id), "a cleared latch re-arms the Director (fresh run)")
	var mock := MockSidecar.new()
	SB.set_client(mock)
	ART.player_position = Vector2(90000, 90000)   # nobody deliberates; directives still apply
	ART.run_beat()
	_ok(_events_by(EB, "overseer_directive", "actor", kell.id).size() == 1,
		"the runtime commits the directive")
	_ok(kell.in_combat, "the GM-forced cast ENTERS combat")
	_ok(kell.pending_cast == "assume_form", "…and parks the cast for the executor")
	var ex := CombatExecutor.new()
	ex.bind(kell)
	_step_m2([ex], 2.0)
	_ok(kell.combat_form == "bieber_monster", "the executor casts it: the form swaps")
	_ok(EB.events("transformed").size() == 1, "transformed is published exactly once")
	_end_m2([ex])
	OV.reset()
	WS.set_pressure("corruption", was_corruption)

func _test_runtime_with_overseer() -> void:
	print("[runtime + overseer]")
	var AG: Object = root.get_node("/root/Agents")
	var EB: Object = root.get_node("/root/EventBus")
	var SB: Object = root.get_node("/root/SidecarBridge")
	var OV: Object = root.get_node("/root/Overseer")
	var ART: Object = root.get_node("/root/AgentRuntime")
	AG.rebuild()
	OV.reset()
	var voss: Agent = AG.get_agent("clerk_voss")
	voss.position = Vector2(400, 300)
	ART.player_position = Vector2(400, 300)
	ART.active_radius = 50.0

	# 1) Critic veto: a tasked agent stripped of its task proposes a ritual step -> vetoed -> no commit.
	var orin: Agent = AG.get_agent("lamplighter_orin")
	orin.task = {}
	orin.position = Vector2(400, 300)   # make orin active too
	var mock := MockSidecar.new()
	mock.set_action("lamplighter_orin", {"actor": "lamplighter_orin", "verb": "perform_ritual_step", "args": {"step": "x"}})
	mock.set_action("clerk_voss", {"actor": "clerk_voss", "verb": "idle", "args": {}})
	SB.set_client(mock)
	EB.clear()
	ART.run_beat()
	_ok(EB.events("action_vetoed").size() >= 1, "incoherent action is vetoed")
	var ritual_actions: Array = EB.events("agent_action").filter(func(e): return e["data"]["verb"] == "perform_ritual_step")
	_ok(ritual_actions.size() == 0, "vetoed ritual step is never committed")

	# 2) Overseer directive overrides the agent's own proposal.
	AG.rebuild(); OV.reset()
	var voss2: Agent = AG.get_agent("clerk_voss")
	voss2.position = Vector2(800, 800)              # far from player -> not active
	ART.player_position = Vector2(0, 0)
	ART.active_radius = 10.0
	var before: Vector2 = voss2.position
	OV.issue_directive("clerk_voss", {"actor": "clerk_voss", "verb": "move_to", "args": {"target": "iron_cross_warehouse"}})
	EB.clear()
	ART.run_beat()
	_ok(EB.events("overseer_directive").size() == 1, "directive committed even for an inactive agent")
	_ok(voss2.position != before, "directed agent moved per the directive")

	# 3) End-to-end exposure invariant: exposing report blocked, then allowed.
	AG.rebuild(); OV.reset()
	var voss3: Agent = AG.get_agent("clerk_voss")
	voss3.position = Vector2(0, 0)
	ART.player_position = Vector2(0, 0)
	ART.active_radius = 50.0
	mock.clear()
	mock.set_action("clerk_voss", {"actor": "clerk_voss", "verb": "report", "args": {"to": "nighthawks", "info": "the cult meets at the warehouse"}})
	# make only voss active: move others away
	for a in AG.all():
		if a.id != "clerk_voss":
			a.position = Vector2(9000, 9000)
	EB.clear()
	ART.run_beat()
	_ok(EB.events("action_vetoed").size() == 1, "exposing report vetoed without player involvement")
	# Player gets involved, then the same report is allowed.
	EB.emit_event("player_investigate", {"actor": "player"})
	EB.clear()
	mock.set_action("clerk_voss", {"actor": "clerk_voss", "verb": "report", "args": {"to": "nighthawks", "info": "the cult meets at the warehouse"}})
	ART.run_beat()
	_ok(EB.events("agent_action").size() == 1, "report committed once the player is involved")

func _test_summoning_plan() -> void:
	print("[summoning plan]")
	var SP: Object = root.get_node("/root/SummoningPlan")
	SP.reset()
	var base: float = SP.manifestation_strength()
	# Impede weakens the manifestation.
	SP.add_impede(20.0, "test")
	_ok(SP.manifestation_strength() < base, "impede lowers manifestation strength")
	_ok(SP.impede_score == 20.0, "impede accumulates")
	# Removing an ingredient weakens it further AND sets back the countdown.
	var cd_before: int = SP.countdown_beats
	var strength_before: float = SP.manifestation_strength()
	_ok(SP.remove_ingredient("ritual_salt", 1), "ritual_salt removed from cult stock")
	_ok(SP.manifestation_strength() < strength_before, "fewer ingredients -> weaker")
	_ok(SP.countdown_beats > cd_before, "removing an ingredient sets back the countdown")
	# Removing more than held fails and changes nothing.
	var cd_now: int = SP.countdown_beats
	_ok(SP.remove_ingredient("ritual_salt", 999) == false, "cannot remove more than held")
	_ok(SP.countdown_beats == cd_now, "failed removal does not set back the countdown")
	# Strength is clamped to a floor.
	SP.add_impede(1000.0, "overkill")
	_ok(SP.manifestation_strength() >= SP.MIN_STRENGTH, "strength never drops below the floor")

## data/rituals.json must agree with the staged run: CitySummoning stocks exactly ONE of each
## offering and derives SummoningPlan.ritual_requirement from those cache keys (1 each), so a
## recipe file still saying 3/2/3 would lie to the RitualPanel about what the rite needs.
## Locks all three sources — rituals.json, CitySummoning's cache, SummoningPlan's default — to 1/1/1.
func _test_rituals_match_staged_requirement() -> void:
	print("[rituals.json matches the staged 1/1/1 requirement]")
	var raw: Variant = JSON.parse_string(FileAccess.get_file_as_string("res://data/rituals.json"))
	_ok(typeof(raw) == TYPE_DICTIONARY and (raw as Dictionary).has("summoning_descent"),
		"rituals.json parses and defines summoning_descent")
	var ing: Dictionary = ((raw as Dictionary).get("summoning_descent", {}) as Dictionary).get("ingredients", {})
	var ing_norm: Dictionary = {}
	for k in ing:
		ing_norm[String(k)] = int(ing[k])
	# The staged requirement CitySummoning derives: one of each cache item.
	var CS: GDScript = load("res://src/CitySummoning.gd")
	var staged: Dictionary = {}
	for item_id in CS.CACHE_ITEMS:
		staged[String(item_id)] = 1
	_ok(ing_norm == staged, "rituals.json ingredient counts == CitySummoning's staged requirement (1/1/1)")
	var SP: Object = root.get_node("/root/SummoningPlan")
	var def_norm: Dictionary = {}
	for k in SP.DEFAULT_RITUAL_REQUIREMENT:
		def_norm[String(k)] = int(SP.DEFAULT_RITUAL_REQUIREMENT[k])
	_ok(ing_norm == def_norm, "rituals.json agrees with SummoningPlan.DEFAULT_RITUAL_REQUIREMENT")

func _test_summoning_countdown_and_climax() -> void:
	print("[summoning countdown]")
	var SP: Object = root.get_node("/root/SummoningPlan")
	var EB: Object = root.get_node("/root/EventBus")
	SP.reset()
	SP.countdown_beats = 3
	var fired: Array = []
	var cb := func(strength: float): fired.append(strength)
	SP.summoning_climax.connect(cb)
	var beats_reported: Array = []
	var cc := func(n: int): beats_reported.append(n)
	SP.countdown_changed.connect(cc)
	EB.clear()
	SP.tick_countdown()
	_ok(SP.countdown_beats == 2, "tick decrements 3 -> 2")
	_ok(fired.is_empty(), "no climax before zero")
	_ok(beats_reported == [2], "countdown_changed emits new beats_left")
	SP.tick_countdown()
	SP.tick_countdown()
	_ok(SP.countdown_beats == 0, "reaches zero")
	_ok(fired.size() == 1, "climax fires exactly once")
	_ok(is_equal_approx(fired[0], SP.manifestation_strength()), "climax strength == manifestation_strength()")
	_ok(SP.climax_fired, "climax_fired latched true")
	var saw := false
	for e in EB.events("summoning_climax"):
		saw = true
	_ok(saw, "summoning_climax event logged")
	SP.tick_countdown()
	_ok(fired.size() == 1, "does not re-fire after climax")
	_ok(beats_reported == [2, 1, 0], "countdown_changed fired only on real decrements, not on the zero/climax tick")
	SP.summoning_climax.disconnect(cb)
	SP.countdown_changed.disconnect(cc)
	SP.reset()
	# Passive doomsday timer is disabled (TODO): a beat alone must NOT advance the clock — only the
	# cult's rite work does. The descent is purely agent-action-driven now.
	var cd0: int = SP.countdown_beats
	SP._on_beat(1, 1)
	SP._on_beat(2, 1)
	_ok(SP.countdown_beats == cd0, "a beat does not passively advance the doomsday clock (timer off)")
	SP.advance_rite(1)
	_ok(SP.countdown_beats == cd0 - 1, "the cult's rite work is the ONLY thing that advances the clock")
	SP.reset()
	paused = false   # the climax now drives EndGame to pause the tree; clear it for later tests

func _test_summoning_progress_readouts() -> void:
	print("[summoning progress]")
	var SP: Object = root.get_node("/root/SummoningPlan")
	SP.reset()
	_ok(is_equal_approx(SP.closeness_ratio(), 0.0), "fresh plan = 0 closeness")
	SP.countdown_beats = SP.START_COUNTDOWN / 2
	_ok(is_equal_approx(SP.closeness_ratio(), 0.5), "halfway countdown = 0.5 closeness")
	SP.countdown_beats = 0
	_ok(is_equal_approx(SP.closeness_ratio(), 1.0), "zero countdown = full closeness")
	_ok(is_equal_approx(SP.ingredients_ratio(), 1.0), "fresh stock = full ratio")
	_ok(SP.interference_band() == "none", "no impede = none band")
	SP.add_impede(40.0)
	_ok(SP.interference_band() == "heavy", "large impede = heavy band")
	SP.reset()

func _test_summoning_advance_rite() -> void:
	print("[summoning advance_rite]")
	var SP: Object = root.get_node("/root/SummoningPlan")
	var EB: Object = root.get_node("/root/EventBus")
	SP.reset()
	SP.countdown_beats = 5
	var fired: Array = []
	var cb := func(strength: float): fired.append(strength)
	SP.summoning_climax.connect(cb)
	var beats_reported: Array = []
	var cc := func(n: int): beats_reported.append(n)
	SP.countdown_changed.connect(cc)
	EB.clear()
	# Working the rite hastens the descent — by more than one beat when several hands work it.
	SP.advance_rite(2)
	_ok(SP.countdown_beats == 3, "advance_rite(2) hastens 5 -> 3")
	_ok(beats_reported == [3], "advance_rite emits countdown_changed with the new beats_left")
	_ok(fired.is_empty(), "no climax before zero")
	# Default step is a single beat.
	SP.advance_rite()
	_ok(SP.countdown_beats == 2, "advance_rite() defaults to one beat (3 -> 2)")
	# Overshooting zero clamps to zero and fires the climax exactly once.
	SP.advance_rite(10)
	_ok(SP.countdown_beats == 0, "advance_rite clamps at zero, never negative")
	_ok(fired.size() == 1, "climax fires exactly once when the rite completes the descent")
	_ok(is_equal_approx(fired[0], SP.manifestation_strength()), "climax strength == manifestation_strength()")
	_ok(SP.climax_fired, "climax_fired latched true")
	var saw := false
	for e in EB.events("summoning_climax"):
		saw = true
	_ok(saw, "summoning_climax event logged")
	# After the climax, further rite work is inert.
	SP.advance_rite(3)
	_ok(fired.size() == 1, "advance_rite does not re-fire after the climax")
	_ok(SP.countdown_beats == 0, "countdown stays at zero after the climax")
	SP.summoning_climax.disconnect(cb)
	SP.countdown_changed.disconnect(cc)
	SP.reset()
	paused = false   # the climax now drives EndGame to pause the tree; clear it for later tests

func _test_ritual_step_advances_summoning() -> void:
	print("[ritual step -> two-phase rite (lay materials, then advance)]")
	var AG: Object = root.get_node("/root/Agents")
	var SP: Object = root.get_node("/root/SummoningPlan")
	var RI: Object = root.get_node("/root/RoomItems")
	var EB: Object = root.get_node("/root/EventBus")
	AG.rebuild()
	SP.reset()
	RI.clear()
	# The requirement is the three offerings; lay them at the altar before the descent can move.
	SP.ritual_requirement = {"ritual_salt": 1, "consecrated_chalk": 1, "candle": 1}
	SP.deposited = {}
	var altar: Vector2 = ActionCommit.SITES["crypt_altar"]
	var voss: Agent = AG.get_agent("clerk_voss")   # has a task / leader
	_ok(voss.task.is_empty() == false, "clerk_voss has a rite task (precondition)")
	voss.room = "cathedral_crypt"
	voss.position = altar

	# PHASE 0 — at the altar empty-handed: the rite cannot advance (no offerings laid yet).
	var cd_start: int = SP.countdown_beats
	EB.clear()
	var empty: Dictionary = ActionCommit.commit(
		{"actor": "clerk_voss", "verb": "perform_ritual_step", "args": {"step": "Invoke."}}, voss)
	_ok(SP.countdown_beats == cd_start, "an empty altar does not advance the clock")
	_ok(empty.get("advanced", false) == false and empty.get("awaiting_materials", false) == true,
		"empty-handed at an unstocked altar is a no-op awaiting materials")
	_ok(EB.events("ritual_advanced").is_empty(), "no ritual_advanced before materials are laid")

	# PHASE 1 — carrying the offerings, each rite step LAYS one (no clock movement yet).
	voss.inventory = {"ritual_salt": 1, "consecrated_chalk": 1, "candle": 1}
	EB.clear()
	var lay1: Dictionary = ActionCommit.commit(
		{"actor": "clerk_voss", "verb": "perform_ritual_step", "args": {"step": "Lay the salt."}}, voss)
	_ok(lay1.has("deposited") and lay1.get("advanced", false) == false, "a carried offering is laid, not invoked")
	_ok(SP.countdown_beats == cd_start, "laying a material does not advance the clock")
	_ok(SP.materials_deposited_total() == 1, "one offering is now on the altar")
	_ok(EB.events("material_deposited").size() == 1, "a material_deposited event is logged")
	_ok(RI.count("cathedral_crypt") == 1, "the laid offering renders as a ground pile at the altar")
	# Lay the remaining two.
	ActionCommit.commit({"actor": "clerk_voss", "verb": "perform_ritual_step", "args": {"step": "Lay the chalk."}}, voss)
	ActionCommit.commit({"actor": "clerk_voss", "verb": "perform_ritual_step", "args": {"step": "Lay the candle."}}, voss)
	_ok(SP.materials_ready(), "all three offerings laid -> materials ready")
	_ok(voss.inventory_count() == 0, "the cultist's hands are now empty")
	_ok(SP.countdown_beats == cd_start, "laying materials never moved the clock")

	# PHASE 2 — altar fully stocked: now the rite advances the descent and logs it.
	EB.clear()
	var inv: Dictionary = ActionCommit.commit(
		{"actor": "clerk_voss", "verb": "perform_ritual_step", "args": {"step": "Speak the Name."}}, voss)
	_ok(SP.countdown_beats < cd_start, "a stocked altar lets the rite advance the summoning clock")
	_ok(inv.get("advanced", false) == true, "outcome reports the rite advanced the summoning")
	_ok(EB.events("ritual_advanced").size() == 1, "a ritual_advanced event is logged")
	_ok(EB.events("ritual_advanced")[0]["data"]["actor"] == "clerk_voss", "the event names the performing cultist")

	# A cultist far from the altar cannot advance the rite even with the altar stocked — flavor only.
	voss.position = altar + Vector2(1000, 1000)
	var cd_far: int = SP.countdown_beats
	EB.clear()
	var out_far: Dictionary = ActionCommit.commit(
		{"actor": "clerk_voss", "verb": "perform_ritual_step", "args": {"step": "Mutter the name."}}, voss)
	_ok(SP.countdown_beats == cd_far, "a cultist away from the altar does not advance the clock")
	_ok(out_far.get("advanced", false) == false, "an off-site rite is flavor-only")
	_ok(EB.events("ritual_advanced").is_empty(), "no ritual_advanced event off-site")
	# A task-less agent standing on the stocked altar still cannot drive the summoning.
	var pell: Agent = AG.get_agent("dockhand_pell")   # no task / victim
	_ok(pell.task.is_empty(), "dockhand_pell has no rite task (precondition)")
	pell.room = "cathedral_crypt"
	pell.position = altar
	var cd_civ: int = SP.countdown_beats
	EB.clear()
	var out_civ: Dictionary = ActionCommit.commit(
		{"actor": "dockhand_pell", "verb": "perform_ritual_step", "args": {"step": "Watch the chalk."}}, pell)
	_ok(SP.countdown_beats == cd_civ, "a task-less agent at the altar does not advance the clock")
	_ok(out_civ.get("advanced", false) == false, "a task-less agent's rite is flavor-only")
	SP.reset()
	RI.clear()

func _test_ambient_sidecar_performs_rite() -> void:
	print("[ambient sidecar rite]")
	var amb := AmbientSidecar.new()
	# A cultist standing ON the rite site should work the ritual, not keep walking.
	var at_site := {"agent_id": "clerk_voss", "task": {"ritual": "summoning_descent"},
		"position": [AmbientSidecar.WAREHOUSE.x, AmbientSidecar.WAREHOUSE.y], "phase": "night", "beat": 11}
	var out: Array = amb.propose([at_site])
	_ok(out[0]["verb"] == "perform_ritual_step", "a cultist at the warehouse performs the rite")
	_ok(ActionSchema.validate(out[0])["ok"], "the rite proposal is schema-valid")
	_ok(String((out[0]["args"] as Dictionary).get("step", "")) != "", "the rite proposal carries a step")
	# A cultist still far from the site keeps converging (move_to), not performing.
	var far := {"agent_id": "clerk_voss", "task": {"ritual": "summoning_descent"}, "position": [200.0, 200.0], "phase": "night", "beat": 11}
	var out_far: Array = amb.propose([far])
	_ok(out_far[0]["verb"] == "move_to", "a distant cultist is still walking to the warehouse")
	# Deterministic: the same snapshot replays the same rite step.
	var again: Array = amb.propose([at_site])
	_ok(again[0]["args"]["step"] == out[0]["args"]["step"], "the same beat replays the same rite step")

## The offline brain's task LADDER (live_sim regression: the cult reached the altar EMPTY-HANDED and
## worked the rite forever with nothing to deposit — AmbientSidecar never gathered): gather what the
## site needs when it is in reach, deliver when carrying, fetch from the cache when empty-handed,
## and only work the rite at the site when there is something to lay (or everything is laid).
func _test_ambient_sidecar_task_ladder() -> void:
	print("[ambient sidecar task ladder]")
	var amb := AmbientSidecar.new()
	var task := {"ritual": "summoning_descent", "site": "crypt_altar", "cache": "ritual_cache"}
	var out_mats := {"ready": false, "outstanding": {"candle": 1, "ritual_salt": 1}}
	# 1) outstanding + a needed item in reach + hands free -> gather it.
	var s_reach := {"agent_id": "clerk_voss", "task": task, "room": "city", "position": [300.0, 300.0],
		"phase": "morning", "beat": 3, "inventory": {}, "can_carry_more": true,
		"ground_items": [{"item_id": "candle", "in_reach": true}], "rite_materials": out_mats}
	var p1: Dictionary = amb.propose([s_reach])[0]
	_ok(p1["verb"] == "gather_item" and String((p1["args"] as Dictionary).get("item_id", "")) == "candle",
		"a needed item within reach is gathered")
	# 2) carrying a needed item -> deliver to the task's named site.
	var s_carry := {"agent_id": "clerk_voss", "task": task, "room": "city", "position": [300.0, 300.0],
		"phase": "morning", "beat": 3, "inventory": {"candle": 1}, "can_carry_more": true,
		"ground_items": [], "rite_materials": out_mats}
	var p2: Dictionary = amb.propose([s_carry])[0]
	_ok(p2["verb"] == "move_to" and String((p2["args"] as Dictionary).get("target", "")) == "crypt_altar",
		"a carrier delivers to the task's named site")
	# 3) empty hands + outstanding + nothing in reach -> fetch from the task's cache.
	var s_empty := {"agent_id": "clerk_voss", "task": task, "room": "city", "position": [300.0, 300.0],
		"phase": "morning", "beat": 3, "inventory": {}, "can_carry_more": true,
		"ground_items": [], "rite_materials": out_mats}
	var p3: Dictionary = amb.propose([s_empty])[0]
	_ok(p3["verb"] == "move_to" and String((p3["args"] as Dictionary).get("target", "")) == "ritual_cache",
		"an empty-handed task-bearer heads for the task's cache")
	# 4) AT the site, empty-handed, materials still outstanding -> leave to fetch, don't mime the rite.
	var s_at_empty := {"agent_id": "clerk_voss", "task": task, "room": "cathedral_crypt",
		"position": [691.0, 600.0], "phase": "morning", "beat": 3, "inventory": {},
		"can_carry_more": true, "ground_items": [], "rite_materials": out_mats}
	var p4: Dictionary = amb.propose([s_at_empty])[0]
	_ok(p4["verb"] == "move_to", "at the site with empty hands and materials outstanding, it goes fetching")
	# 5) AT the site carrying a needed item -> the rite (which lays it).
	var s_at_carry := {"agent_id": "clerk_voss", "task": task, "room": "cathedral_crypt",
		"position": [691.0, 600.0], "phase": "morning", "beat": 3, "inventory": {"candle": 1},
		"can_carry_more": true, "ground_items": [], "rite_materials": out_mats}
	var p5: Dictionary = amb.propose([s_at_carry])[0]
	_ok(p5["verb"] == "perform_ritual_step", "at the site with a needed item in hand, it works the rite")

## End-to-end OFFLINE descent: stage the demo exactly like CitySummoning (data only), drive the real
## runtime + ambient brain for up to 90 beats, and require actual deposits AND a moving countdown —
## the regression that the free offline build can still complete the summoning by itself.
func _test_offline_descent_completes() -> void:
	print("[offline descent completes]")
	var AG: Object = root.get_node("/root/Agents")
	var SP: Object = root.get_node("/root/SummoningPlan")
	var RI: Object = root.get_node("/root/RoomItems")
	var ART: Object = root.get_node("/root/AgentRuntime")
	var SB: Object = root.get_node("/root/SidecarBridge")
	var CL: Object = root.get_node("/root/Clock")
	AG.rebuild()
	SP.reset()
	SP.ritual_requirement = {"ritual_salt": 1, "consecrated_chalk": 1, "candle": 1}
	SP.deposited = {}
	var saved_speed: float = AG.fallback_speed   # restored below — a 170 leak strides later tests' agents out of their active radii
	AG.fallback_speed = 170.0
	RI.clear()
	var CS: GDScript = load("res://src/CitySummoning.gd")
	ActionCommit.set_nav_site("ritual_cache", CS.CACHE_NAV_POS, "city")
	for item_id in CS.CACHE_ITEMS:
		RI.place("city", item_id, CS.CACHE_ITEMS[item_id], 1)
	for id in ["clerk_voss", "fishwife_dalia", "lamplighter_orin"]:
		var a: Agent = AG.get_agent(id)
		a.position = CS.SPOTS[id]
		a.room = "city"
		a.carry_capacity = 2
		a.inventory.clear()
		a.intent = "Complete the summoning at the site named 'crypt_altar', drawing from the cache 'ritual_cache'."
		ART.always_active[id] = true
	SB.set_client(AmbientSidecar.new())
	ART.player_position = Vector2(-4000, -4000)   # only always_active agents deliberate
	var start_countdown: int = SP.countdown_beats
	for beat in 90:
		CL.beat_index = beat
		ART.run_beat()
		if SP.countdown_beats < start_countdown - 3:
			break   # rite demonstrably advancing; no need to run the clock down
	_ok(SP.materials_deposited_total() == 3, "the offline cult lays all three offerings (got %d)" % SP.materials_deposited_total())
	_ok(SP.countdown_beats < start_countdown, "the offline rite advances the countdown (%d -> %d)" % [start_countdown, SP.countdown_beats])
	for id in ["clerk_voss", "fishwife_dalia", "lamplighter_orin"]:
		ART.always_active.erase(id)
	SB.set_client(MockSidecar.new())
	AG.fallback_speed = saved_speed
	ActionCommit.clear_nav_sites()   # the ritual_cache registration must not leak into later tests
	SP.reset()
	RI.clear()
	CL.beat_index = 0

func _test_cathedral_rite_mvp() -> void:
	print("[cathedral rite — crypt only, no City-surface shortcut]")
	# The old City-surface chapel rite site is GONE: the only cathedral rite site is the crypt altar,
	# which lives in the crypt room — so the cult MUST descend through the portals to work the rite.
	_ok(not ActionCommit.SITES.has("cathedral_crypt"), "the City-surface chapel rite site is removed")
	_ok(ActionCommit.SITES.has("crypt_altar"), "crypt_altar is the cathedral rite site")
	_ok(ActionCommit._site_room("crypt_altar") == "cathedral_crypt", "crypt_altar lives in the crypt room")

	# A cultist standing on the chapel coordinate IN THE CITY cannot work the rite — there is no site
	# there anymore; only the crypt room's altar bites the clock.
	var SP: Object = root.get_node("/root/SummoningPlan"); SP.reset()
	var surface := Agent.new("clerk_voss"); surface.task = {"ritual": "summoning_descent"}; surface.room = "city"
	surface.position = Vector2(2118, 5015)   # the chapel body origin in the City — not a rite site
	ActionCommit.commit({"verb": "perform_ritual_step", "args": {"step": "x"}}, surface)
	_ok(SP.countdown_beats == SP.START_COUNTDOWN, "a cultist on the City chapel steps does NOT advance the rite")

	# Offline brain (C1 regression guard): a cultist whose intent names crypt_altar heads there BY NAME
	# (so the room-aware move can traverse scenes), not to the warehouse or a raw coordinate.
	var amb := AmbientSidecar.new()
	var intent := "descend to the site named 'crypt_altar' and work the rite"
	var away := {"agent_id": "clerk_voss", "task": {"ritual": "summoning_descent"}, "intent": intent, "room": "city",
		"position": [2000.0, 5180.0], "phase": "morning", "beat": 3}
	var mv: Dictionary = amb.propose([away])[0]
	_ok(mv["verb"] == "move_to" and String((mv["args"] as Dictionary).get("target", "")) == "crypt_altar",
		"offline cult heads to the crypt altar by name, not a coordinate or the warehouse")
	SP.reset()

func _test_room_traversal() -> void:
	print("[room traversal — cross-scene]")
	# RoomGraph BFS finds the path City -> Nave -> Crypt one hop at a time.
	_ok(RoomGraph.next_hop("city", "cathedral_crypt") == "cathedral_nave", "first hop city->crypt is the nave")
	_ok(RoomGraph.next_hop("cathedral_nave", "cathedral_crypt") == "cathedral_crypt", "next hop nave->crypt is the crypt")
	_ok(RoomGraph.next_hop("city", "city") == "", "no hop needed when already in the room")
	_ok(not RoomGraph.portal("city", "cathedral_nave").is_empty(), "there is a portal city->nave")

	# An agent in the City, targeting the crypt altar, walks to each door and CROSSES it — its room
	# changes City -> cathedral_nave -> cathedral_crypt without any scene ever being loaded.
	var a := Agent.new("voss"); a.task = {"ritual": "summoning_descent"}; a.room = "city"
	a.position = Vector2(2000, 5180)   # a staging spot near the chapel steps
	var rooms_seen: Dictionary = {}
	var arrived := false
	for i in 600:
		rooms_seen[a.room] = true
		ActionCommit.commit({"verb": "move_to", "args": {"target": "crypt_altar"}}, a)
		if a.room == "cathedral_crypt" and ActionCommit._near_any_rite_site(a.room, a.position):
			arrived = true
			break
	_ok(rooms_seen.has("city") and rooms_seen.has("cathedral_nave") and rooms_seen.has("cathedral_crypt"),
		"the agent passed through city -> cathedral_nave -> cathedral_crypt")
	_ok(arrived and a.room == "cathedral_crypt", "the agent ended standing on the crypt altar")

	# The rite now bites ONLY in the crypt room (room-aware gate): the same agent off in the city does
	# not advance the clock; on the altar it does. Stock the altar first so the materials gate is open
	# (the materials loop itself is covered by _test_ritual_step_advances_summoning).
	var SP: Object = root.get_node("/root/SummoningPlan"); SP.reset()
	SP.deposited = SP.ritual_requirement.duplicate(true)   # offerings already laid
	var city_ghost := Agent.new("ghost"); city_ghost.task = {"ritual": "summoning_descent"}; city_ghost.room = "city"
	city_ghost.position = ActionCommit.SITES["crypt_altar"]   # same coordinate, WRONG room
	ActionCommit.commit({"verb": "perform_ritual_step", "args": {"step": "x"}}, city_ghost)
	_ok(SP.countdown_beats == SP.START_COUNTDOWN, "the altar coordinate in the wrong room does NOT bite the clock")
	var before: int = SP.countdown_beats
	ActionCommit.commit({"verb": "perform_ritual_step", "args": {"step": "x"}}, a)
	_ok(SP.countdown_beats < before, "the rite worked in the crypt room drives the doomsday clock")
	SP.reset()

	# Portal-ONLY exit: the room never changes except by reaching and crossing a portal. A cultist far
	# from the chapel portal does not teleport — it stays in the City and just walks toward the door.
	var far := Agent.new("far"); far.room = "city"; far.position = Vector2(1000, 4000)
	var moved := ActionCommit.commit({"verb": "move_to", "args": {"target": "crypt_altar"}}, far)
	_ok(far.room == "city", "a cultist far from the portal stays in the City (no teleport across scenes)")
	_ok(moved.has("moved_to") and not moved.has("crossed_to"), "an off-portal step does not cross a room")
	# A bare coordinate move never crosses a room boundary — only a portal can change the room.
	var coord := Agent.new("coord"); coord.room = "city"; coord.position = Vector2(2118, 5015)
	ActionCommit.commit({"verb": "move_to", "args": {"target": "691,600"}}, coord)
	_ok(coord.room == "city", "a raw-coordinate move never crosses a room (portals are the only exit)")
	# But standing ON the portal and moving toward the far room DOES cross it.
	var atdoor := Agent.new("atdoor"); atdoor.room = "city"; atdoor.position = RoomGraph.portal("city", "cathedral_nave")["from_pos"]
	var crossed := ActionCommit.commit({"verb": "move_to", "args": {"target": "crypt_altar"}}, atdoor)
	_ok(atdoor.room == "cathedral_nave" and crossed.has("crossed_to"), "reaching the portal crosses into the next scene")

## The 7 painted interiors (city buildout follow-up): each is a first-class RoomGraph room
## with a TWO-WAY portal pair, a walk-in exit Portal standing on the same doorway the data
## agents cross, a city-side door Area2D on its building's street edge, and a scale-aware
## world extent (the warehouse floor ~3x a Klein house room; tavern/police/butcher mid;
## almshouse + Franky's modest). The Klein house layers: city -> parlor (klein_living_room)
## -> bedroom (klein_room = IntroRoom.tscn), with NO direct city -> bedroom edge. Deep
## per-scene wiring (room photo, Solids blobs, cameras) lives in tests/test_interiors.gd.
const INTERIOR_ROOMS := {
	"klein_living_room": "res://scenes/KleinLivingRoom.tscn",
	"butcher_shop_inner": "res://scenes/ButcherShopInner.tscn",
	"laughing_eel_tavern": "res://scenes/LaughingEelTavern.tscn",
	"police_station_inner": "res://scenes/PoliceStationInner.tscn",
	"selena_almshouse_inner": "res://scenes/SelenaAlmshouseInner.tscn",
	"mr_frankys_inner": "res://scenes/MrFrankysInner.tscn",
	"warehouse_inner": "res://scenes/WarehouseInner.tscn",
}

func _test_interior_rooms() -> void:
	print("[interior rooms: graph edges + round trips + city doors]")
	# (a) Registration + two-way portal pairs, and a data-agent ROUND TRIP through the real
	# crossing code for every room: in (room id flips), back (city again) — the same
	# mechanic _test_room_traversal proves for the cathedral chain.
	for room_id in INTERIOR_ROOMS:
		_ok(RoomGraph.has_room(room_id), "%s is a RoomGraph room" % room_id)
		_ok(RoomGraph.scene_for(room_id) == INTERIOR_ROOMS[room_id],
			"%s -> %s" % [room_id, INTERIOR_ROOMS[room_id]])
		var pin: Dictionary = RoomGraph.portal("city", room_id)
		var pout: Dictionary = RoomGraph.portal(room_id, "city")
		_ok(not pin.is_empty(), "portal city -> %s" % room_id)
		_ok(not pout.is_empty(), "portal %s -> city" % room_id)
		if pin.is_empty() or pout.is_empty():
			continue
		var a := Agent.new("rt_" + String(room_id)); a.room = "city"
		a.position = (pin["from_pos"] as Vector2) + Vector2(0, -120)
		ActionCommit.set_nav_site("rt_in", pin["to_pos"], room_id)
		for i in 200:
			ActionCommit.commit({"verb": "move_to", "args": {"target": "rt_in"}}, a)
			if a.room == room_id:
				break
		_ok(a.room == room_id, "%s: agent walked in through the door" % room_id)
		ActionCommit.set_nav_site("rt_out", pin["from_pos"], "city")
		for i in 200:
			ActionCommit.commit({"verb": "move_to", "args": {"target": "rt_out"}}, a)
			if a.room == "city":
				break
		_ok(a.room == "city" and a.position.distance_to(pout["to_pos"]) <= 80.0,
			"%s: agent walked back out to the city door" % room_id)
		ActionCommit.NAV_SITES.erase("rt_in")
		ActionCommit.NAV_SITES.erase("rt_out")
	# (b) The layered Klein house: the bedroom hangs OFF the parlor, never off the street.
	_ok(RoomGraph.scene_for("klein_room") == "res://scenes/IntroRoom.tscn",
		"klein_room (the bedroom, IntroRoom.tscn) is a room")
	_ok(RoomGraph.portal("city", "klein_room").is_empty(), "no direct city -> bedroom edge")
	_ok(RoomGraph.next_hop("city", "klein_room") == "klein_living_room",
		"city -> bedroom passes through the parlor")
	_ok(RoomGraph.next_hop("klein_room", "city") == "klein_living_room",
		"bedroom -> city passes through the parlor")
	_ok(not RoomGraph.portal("klein_living_room", "klein_room").is_empty()
		and not RoomGraph.portal("klein_room", "klein_living_room").is_empty(),
		"parlor <-> bedroom edges are two-way")
	# The cathedral layering predates this work and must not have drifted.
	_ok((RoomGraph.portal("city", "cathedral_nave").get("from_pos", Vector2.INF) as Vector2) \
		== Vector2(2172, 5284), "chapel door portal untouched")
	# (c) Scale-aware grounds: world extent comes from the background sprite's scale.
	var widths: Dictionary = {}
	for room_id in INTERIOR_ROOMS:
		var packed: PackedScene = load(INTERIOR_ROOMS[room_id])
		if packed == null:
			_ok(false, "%s loads" % INTERIOR_ROOMS[room_id])
			continue
		var n: Node = packed.instantiate()
		var photo: Sprite2D = n.get_node_or_null("RoomPhoto")
		if photo != null and photo.texture != null:
			widths[room_id] = photo.texture.get_size().x * photo.scale.x
		# The scene's own exit door stands where the graph says the agents cross.
		var exit_area: Node2D = null
		for c in n.get_children():
			if c is Area2D and String(c.get("target_scene")) == "res://scenes/City.tscn":
				exit_area = c
				break
		var from_pos: Vector2 = RoomGraph.portal(room_id, "city").get("from_pos", Vector2.INF)
		_ok(exit_area != null and exit_area.position.distance_to(from_pos) <= 40.0,
			"%s exit Portal stands on the RoomGraph doorway" % room_id)
		n.free()
	_ok(widths.has("warehouse_inner") and widths.has("klein_living_room")
		and widths["warehouse_inner"] >= 2.9 * widths["klein_living_room"],
		"warehouse floor ~3x a Klein house room")
	_ok(widths.has("laughing_eel_tavern")
		and widths["laughing_eel_tavern"] > 1.3 * widths["klein_living_room"],
		"tavern mid-sized (bigger than a house room)")
	# (d) City-side doors: every interior's door Area2D sits on its building at the exact
	# from_pos the graph carries, with its mouth in the street (not buried in a collider).
	var city: Node = (load("res://scenes/City.tscn") as PackedScene).instantiate()
	root.add_child(city)   # in-tree so global transforms resolve; freed synchronously below
	var colliders: Array = []
	_collect_rect_colliders(city, colliders)
	for room_id in INTERIOR_ROOMS:
		var door := _find_scene_door(city, String(INTERIOR_ROOMS[room_id]))
		_ok(door != null, "City has a door -> %s" % INTERIOR_ROOMS[room_id])
		if door == null:
			continue
		var from_pos: Vector2 = RoomGraph.portal("city", room_id).get("from_pos", Vector2.INF)
		_ok(door.global_position.distance_to(from_pos) < 1.0,
			"%s city door at the RoomGraph from_pos (got %s)" % [room_id, str(door.global_position)])
		var hit := _point_in_any_collider(door.global_position, colliders)
		_ok(hit == "", "%s city door mouth is street-side (not inside %s)" % [room_id, hit])
	# The Klein house door now opens into the parlor, NOT straight into the bedroom.
	var kdoor: Node2D = city.get_node_or_null("KleinHouse/KleinHouseDoor")
	_ok(kdoor != null and String(kdoor.get("target_scene")) == "res://scenes/KleinLivingRoom.tscn",
		"KleinHouseDoor -> KleinLivingRoom.tscn (layered house)")
	city.free()   # synchronous, before CitySummoning's deferred bootstrap

## First Area2D under `node` (recursively) whose target_scene is `scene_path`.
func _find_scene_door(node: Node, scene_path: String) -> Node2D:
	for c in node.get_children():
		if c is Area2D and String(c.get("target_scene")) == scene_path:
			return c
		var hit := _find_scene_door(c, scene_path)
		if hit != null:
			return hit
	return null

func _test_spawn_formation() -> void:
	print("[spawn formation — the cult never stacks on one pixel]")
	# (a) The formation offset is a pure function of the agent id: deterministic and bounded by
	# FORMATION_RADIUS — strictly inside PORTAL_CROSS_RADIUS (40) and RITE_RADIUS (80), so it can
	# never break either gate.
	var det := true
	var bounded := true
	for i in 25:
		var nid := "npc_%d" % i
		var off: Vector2 = ActionCommit._formation_offset(nid)
		if off != ActionCommit._formation_offset(nid):
			det = false
		if off.length() > ActionCommit.FORMATION_RADIUS or off.length() >= ActionCommit.PORTAL_CROSS_RADIUS \
				or off.length() >= ActionCommit.RITE_RADIUS:
			bounded = false
	_ok(det, "_formation_offset is deterministic (same id -> same offset)")
	_ok(bounded, "|offset| <= FORMATION_RADIUS for every id (< PORTAL_CROSS_RADIUS and < RITE_RADIUS)")
	var ids: Array = ["cultist_a", "cultist_b", "cultist_c"]
	_ok(ActionCommit._formation_offset(ids[0]) != ActionCommit._formation_offset(ids[1])
		and ActionCommit._formation_offset(ids[1]) != ActionCommit._formation_offset(ids[2])
		and ActionCommit._formation_offset(ids[0]) != ActionCommit._formation_offset(ids[2]),
		"distinct ids get distinct offsets")
	# Roster guard: the WHOLE current cast (npcs.json + the player proxy + this suite's cult ids)
	# must separate pairwise by > 8px in offset space. _FORMATION_SALT was chosen to make exactly
	# this true — if a future NPC lands in a colliding formation slot, this fails loudly and the
	# fix is to bump ActionCommit._FORMATION_SLOTS / _FORMATION_SALT until the cast separates again.
	# NOTE: M14 (25-id cast, K=48, salt 422736): reviewer-measured min pairwise = 8.85px. Threshold
	# raised from 4px -> 8px: catches near-collisions that 4px misses; comfortably below the 8.85px
	# floor (same-slot items separate by only the 0.5px jitter, well below 8px).
	var cast_ids: Array = ids.duplicate()
	cast_ids.append("player")
	var npcs_raw: Variant = JSON.parse_string(FileAccess.get_file_as_string("res://data/npcs.json"))
	for npc_id in (npcs_raw as Dictionary):
		cast_ids.append(String(npc_id))
	var cast_spread := true
	for i in cast_ids.size():
		for j in range(i + 1, cast_ids.size()):
			if ActionCommit._formation_offset(cast_ids[i]).distance_to(
					ActionCommit._formation_offset(cast_ids[j])) <= 8.0:
				cast_spread = false
	_ok(cast_spread, "every pair of the current cast separates by > 8px in offset space")

	# (b/c/d) Three task-bearing cultists whose intent names crypt_altar, from DISTINCT city spots —
	# two of them EQUIDISTANT from the chapel door, so they cross the portal on the same beat (the
	# historical worst case: identical exit pixel). Drive move_to beats until all three stand in the
	# crypt within rite range. No two same-room agents may share a pixel right after a crossing, and
	# at rest the cell must be spread out (> 10px pairwise), never stacked on one point.
	var altar: Vector2 = ActionCommit.SITES["crypt_altar"]
	var door: Vector2 = RoomGraph.portal("city", "cathedral_nave")["from_pos"]
	var starts: Array = [Vector2(1900, 5100), door + Vector2(-100, 0), door + Vector2(100, 0)]
	var cult: Array = []
	for i in ids.size():
		var a := Agent.new(ids[i])
		a.task = {"ritual": "summoning_descent", "site": "crypt_altar"}
		a.intent = "descend to the site named 'crypt_altar' and work the rite"
		a.room = "city"
		a.position = starts[i]
		cult.append(a)
	var never_coincident_on_cross := true
	var all_arrived := false
	for _beat in 600:
		for a in cult:
			var out: Dictionary = ActionCommit.commit({"verb": "move_to", "args": {"target": "crypt_altar"}}, a)
			if out.has("crossed_to"):
				for other in cult:
					if other != a and other.room == a.room and (other.position as Vector2).distance_to(a.position) == 0.0:
						never_coincident_on_cross = false
		all_arrived = true
		for a in cult:
			if a.room != "cathedral_crypt" or (a.position as Vector2).distance_to(altar) > ActionCommit.RITE_RADIUS:
				all_arrived = false
		if all_arrived:
			break
	_ok(all_arrived, "all three cultists reached the crypt within rite range of the altar")
	_ok(never_coincident_on_cross, "no two same-room agents share a pixel right after a portal crossing")
	# Let the walk settle (arrivals snap onto their spot), then measure the resting spread.
	for _i in 3:
		for a in cult:
			ActionCommit.commit({"verb": "move_to", "args": {"target": "crypt_altar"}}, a)
	var spread := true
	for i in cult.size():
		for j in range(i + 1, cult.size()):
			if ((cult[i] as Agent).position).distance_to((cult[j] as Agent).position) <= 10.0:
				spread = false
	_ok(spread, "at rest every pairwise distance > 10px (no single-pixel cluster)")
	var gate_still_bites := true
	for a in cult:
		if not ActionCommit._near_any_rite_site(a.room, a.position):
			gate_still_bites = false
	_ok(gate_still_bites, "every offset resting spot still stands within RITE_RADIUS (the rite gate bites)")

	# The offset must never strand an agent: standing at a door pixel PLUS its offset, the agent
	# still counts as at the door and crosses (offset < PORTAL_CROSS_RADIUS)...
	var back := Agent.new("cultist_a")
	back.room = "cathedral_crypt"
	back.position = (RoomGraph.portal("cathedral_crypt", "cathedral_nave")["from_pos"] as Vector2) \
		+ ActionCommit._formation_offset(back.id)
	var out_back: Dictionary = ActionCommit.commit({"verb": "move_to", "args": {"target": "iron_cross_warehouse"}}, back)
	_ok(String(out_back.get("crossed_to", "")) == "cathedral_nave",
		"an agent offset from the reverse door still crosses in one beat (offset < PORTAL_CROSS_RADIUS)")
	# ...and a full return leg: from the nave ARRIVAL pixel (+offset) back out into the City.
	back.room = "cathedral_nave"
	back.position = (RoomGraph.portal("city", "cathedral_nave")["to_pos"] as Vector2) \
		+ ActionCommit._formation_offset(back.id)
	var returned := false
	for _i in 6:
		ActionCommit.commit({"verb": "move_to", "args": {"target": "iron_cross_warehouse"}}, back)
		if back.room == "city":
			returned = true
			break
	_ok(returned, "an agent at to_pos+offset walks back out through the reverse portal")

	# (e) The schedule fallback walks CITY-space waypoints (npcs.json); in any other room it must
	# hold position instead of darting toward a wrong-space coordinate.
	var orin := Agent.new("lamplighter_orin")
	orin.room = "cathedral_nave"
	orin.position = Vector2(500, 500)
	orin.tick_fallback("morning", 100.0)
	_ok(orin.position == Vector2(500, 500), "tick_fallback holds position when the agent is not in the city")
	orin.room = "city"
	orin.tick_fallback("morning", 100.0)
	_ok(orin.position != Vector2(500, 500), "tick_fallback still walks the schedule in the city")

	# (f) Two offerings laid by the same cultist land on two spots, not one pixel.
	var SP: Object = root.get_node("/root/SummoningPlan"); SP.reset()
	var RI: Object = root.get_node("/root/RoomItems"); RI.clear()
	SP.ritual_requirement = {"ritual_salt": 1, "consecrated_chalk": 1}
	SP.deposited = {}
	var layer := Agent.new("cultist_b")
	layer.task = {"ritual": "summoning_descent"}
	layer.room = "cathedral_crypt"
	layer.position = altar + ActionCommit._formation_offset(layer.id)
	layer.inventory = {"ritual_salt": 1, "consecrated_chalk": 1}
	ActionCommit.commit({"verb": "perform_ritual_step", "args": {"step": "lay salt"}}, layer)
	ActionCommit.commit({"verb": "perform_ritual_step", "args": {"step": "lay chalk"}}, layer)
	var piles: Array = RI.items_in("cathedral_crypt")
	_ok(piles.size() == 2, "both offerings landed as ground piles")
	if piles.size() == 2:
		_ok((piles[0]["pos"] as Vector2).distance_to(piles[1]["pos"]) > 0.0,
			"the two altar piles do not render on one pixel")
	SP.reset()
	RI.clear()

## Concurrency Phase 1 (orchestrator/GM design §4): decorrelate the per-beat decision monoculture.
## Staggering is a property of the BRAIN (an LLM needs decorrelation, a deterministic brain does not),
## so the stagger factor comes from the sidecar client; off-beat agents CONTINUE their committed
## continuous action instead of re-deciding; peers' committed actions are objective `doing` facts in
## nearby; gather/deposit facts fan to vision-gated witnesses; a consumed LLM action never replays.
func _test_concurrency_phase1() -> void:
	print("[concurrency phase 1 — stagger, continuation, doing, peer stimulus, cache consume]")
	var AG: Object = root.get_node("/root/Agents")
	var EB: Object = root.get_node("/root/EventBus")
	var SB: Object = root.get_node("/root/SidecarBridge")
	var ART: Object = root.get_node("/root/AgentRuntime")
	var CL: Object = root.get_node("/root/Clock")
	var RI: Object = root.get_node("/root/RoomItems")
	AG.rebuild()
	EB.clear()
	RI.clear()
	# --- stagger_k lives on the client.
	_ok(SidecarClient.new().stagger_k() == 1, "base client stagger_k is 1 (no stagger)")
	_ok(MockSidecar.new().stagger_k() == 1, "mock defaults to no stagger")
	_ok(HttpSidecar.new("").stagger_k() == 2, "the LLM brain staggers deliberation (k=2)")
	# --- cohort partition: deterministic, 2-periodic, honestly mixed (md5, not djb2 hash()).
	var vc: bool = ART.in_cohort("clerk_voss", 0, 2)
	_ok(ART.in_cohort("clerk_voss", 0, 2) == vc, "cohort membership is deterministic")
	_ok(ART.in_cohort("clerk_voss", 1, 2) != vc, "k=2 alternates beats for the same agent")
	_ok(ART.in_cohort("clerk_voss", 7, 1), "k=1 puts everyone in every beat")
	_ok(ART.in_cohort("clerk_voss", 0, 2) != ART.in_cohort("lamplighter_orin", 0, 2),
		"the cult cast splits across cohorts (voss vs orin)")
	# --- off-beat agents CONTINUE a continuous action instead of re-deciding.
	var mock := MockSidecar.new()
	mock.stagger_k_value = 2
	SB.set_client(mock)
	var voss: Agent = AG.get_agent("clerk_voss")
	voss.room = "city"
	voss.position = Vector2(400, 300)
	voss.current_action = {}
	var saved_player_pos: Vector2 = ART.player_position   # restored below (test hygiene)
	var saved_radius: float = ART.active_radius
	ART.player_position = Vector2(400, 300)
	ART.active_radius = 50.0   # only voss is active
	mock.set_action("clerk_voss", {"actor": "clerk_voss", "verb": "move_to", "args": {"target": "iron_cross_warehouse"}})
	var on_beat: int = 0 if ART.in_cohort("clerk_voss", 0, 2) else 1
	CL.beat_index = on_beat
	EB.clear()
	ART.run_beat()
	_ok(EB.events("agent_action").size() == 1, "cohort agent deliberates and acts on its beat")
	var p1: Vector2 = voss.position
	# The off beat: the mock is NOT consulted (a fresh, different action must not fire); the move continues.
	mock.set_action("clerk_voss", {"actor": "clerk_voss", "verb": "gather_item", "args": {"item_id": "rye_bread"}})
	CL.beat_index = on_beat + 1
	EB.clear()
	ART.run_beat()
	_ok(voss.position != p1, "off-beat: the in-flight move_to CONTINUES (no freeze)")
	var offbeat_acts: Array = EB.events("agent_action")
	_ok(offbeat_acts.size() == 1 and String((offbeat_acts[0]["data"] as Dictionary).get("verb", "")) == "move_to",
		"off-beat commit is the continuation, not a fresh decision")
	_ok(voss.item_count("rye_bread") == 0, "off-beat: the newly scripted one-shot verb did NOT fire")
	# One-shot verbs do not auto-repeat on the off beat. Re-pin voss onto the player each beat —
	# the earlier moves genuinely moved him, and a drifted agent drops out of the active radius.
	voss.position = Vector2(400, 300)
	CL.beat_index = on_beat + 2
	ART.run_beat()   # deliberation beat: the gather fires once
	var n_bread: int = voss.item_count("rye_bread")
	_ok(n_bread == 1, "deliberation beat: the scripted gather fires once")
	voss.position = Vector2(400, 300)
	CL.beat_index = on_beat + 3
	ART.run_beat()   # off beat: gather is one-shot, must not repeat
	_ok(voss.item_count("rye_bread") == n_bread, "off-beat: a one-shot gather does NOT repeat")
	# --- `doing`: a peer's committed action is an objective fact in nearby. (Re-pin voss first —
	# the beat sequence above walked him away from the meeting point.)
	voss.position = Vector2(400, 300)
	var dalia: Agent = AG.get_agent("fishwife_dalia")
	dalia.room = "city"
	dalia.position = Vector2(420, 300)
	voss.current_action = {"verb": "move_to", "args": {"target": "crypt_altar"}}
	var snap: Dictionary = Perception.build_snapshot(dalia, dalia.position)
	var doing := "MISSING"
	for n in (snap["nearby"] as Array):
		if String((n as Dictionary).get("id", "")) == "clerk_voss":
			doing = String((n as Dictionary).get("doing", "ABSENT"))
	_ok(doing == "move_to crypt_altar", "nearby carries the peer's committed action as an objective fact")
	voss.current_action = {}
	snap = Perception.build_snapshot(dalia, dalia.position)
	for n in (snap["nearby"] as Array):
		if String((n as Dictionary).get("id", "")) == "clerk_voss":
			doing = String((n as Dictionary).get("doing", "ABSENT"))
	_ok(doing == "", "an idle/actionless peer reads as doing nothing")
	# --- peer-action stimulus: gather/deposit facts fan to same-room witnesses within THEIR vision.
	var orin: Agent = AG.get_agent("lamplighter_orin")
	orin.room = "city"
	orin.position = Vector2(430, 300)   # within orin's vision_r (160) of voss
	orin.short_memory.clear()
	var pell: Agent = AG.get_agent("dockhand_pell")
	pell.room = "city"
	pell.position = Vector2(3000, 3000)   # far beyond vision
	pell.short_memory.clear()
	voss.short_memory.clear()
	EB.emit_event("item_gathered", {"actor": "clerk_voss", "item_id": "candle", "count": 1, "from_ground": true})
	_ok(_memory_mentions(orin, "candle"), "a witness within vision sees the pickup")
	_ok(not _memory_mentions(pell, "candle"), "an out-of-vision agent does not")
	_ok(not _memory_mentions(voss, "picked up"), "the actor is not re-told its own act (except list)")
	EB.emit_event("material_deposited", {"actor": "clerk_voss", "item_id": "ritual_salt", "room": "city"})
	_ok(_memory_mentions(orin, "ritual salt"), "a deposit fans as a fact to vision-gated witnesses")
	# --- contention: a gather that finds nothing leaves an informed memory (agent-sandbox precedent).
	voss.short_memory.clear()
	var out_none: Dictionary = ActionCommit.commit(
		{"actor": "clerk_voss", "verb": "gather_item", "args": {"item_id": "ritual_salt"}}, voss)
	_ok(out_none.get("added", true) == false, "precondition: the contended gather came up empty")
	_ok(_memory_mentions(voss, "none left"), "the losing gatherer is told WHY (informed retry)")
	# --- full hands are also an informed fact (live finding: Sonnet re-gathered forever without it).
	voss.short_memory.clear()
	voss.inventory.clear()
	voss.carry_capacity = 1
	voss.add_item("rye_bread", 1)
	var out_full: Dictionary = ActionCommit.commit(
		{"actor": "clerk_voss", "verb": "gather_item", "args": {"item_id": "candle"}}, voss)
	_ok(String(out_full.get("reason", "")) == "full", "precondition: the gather failed on a full pack")
	_ok(_memory_mentions(voss, "full"), "a full-handed gatherer is told its hands are full")
	voss.inventory.clear()
	voss.carry_capacity = 2
	# --- off-beat task-bearers HOLD instead of drifting to their day-job schedule (live finding:
	# voss walked 700px toward his warehouse waypoint mid-summoning between deliberations).
	voss.room = "city"
	voss.position = Vector2(400, 300)
	voss.current_action = {"verb": "gather_item", "args": {"item_id": "candle"}}   # one-shot: no continuation
	_ok(not voss.task.is_empty(), "precondition: voss carries a task")
	CL.beat_index = on_beat + 1   # voss's OFF beat
	var hold_pos: Vector2 = voss.position
	ART.run_beat()
	_ok(voss.position == hold_pos, "an off-beat task-bearer holding a one-shot action HOLDS (no schedule drift)")
	# A DOWNED agent is never animated by continuation (review finding): its committed continuous
	# action must not re-commit on the off beat — that would bypass the Critic's downed-can-only-idle.
	voss.current_action = {"verb": "move_to", "args": {"target": "iron_cross_warehouse"}}
	voss.downed = true
	voss.position = Vector2(400, 300)
	CL.beat_index = on_beat + 1
	EB.clear()
	ART.run_beat()
	_ok(voss.position == Vector2(400, 300), "a downed agent is not walked by continuation")
	_ok(EB.events("agent_action").is_empty(), "no continuation commit is logged for a downed agent")
	voss.downed = false
	voss.current_action = {}
	# --- HttpSidecar cache is consume-once: a stale LLM action never replays.
	var hs := HttpSidecar.new("")
	hs.apply_reply([{"actor": "clerk_voss", "verb": "move_to", "args": {"target": "iron_cross_warehouse"}}], "")
	var vsnap: Dictionary = Perception.build_snapshot(voss, voss.position)
	var first: Dictionary = hs.pick([vsnap])[0]
	_ok(String((first.get("args", {}) as Dictionary).get("target", "")) == "iron_cross_warehouse",
		"pick serves the cached LLM action once")
	var second: Dictionary = hs.pick([vsnap])[0]
	_ok(String((second.get("args", {}) as Dictionary).get("target", "")) != "iron_cross_warehouse",
		"a consumed action is never replayed (ambient fallback instead)")
	SB.set_client(MockSidecar.new())
	ART.player_position = saved_player_pos
	ART.active_radius = saved_radius
	CL.beat_index = 0

## Coordinator v1 (orchestrator/GM design §4.2): a deterministic work partition over the agents
## sharing a task. It PUBLISHES an allocation as a perception FACT (never a command) so same-task
## agents divide the outstanding materials instead of converging; the LLM still chooses in character.
func _test_coordinator_focus() -> void:
	print("[coordinator focus — deterministic work partition]")
	var AG: Object = root.get_node("/root/Agents")
	var SP: Object = root.get_node("/root/SummoningPlan")
	var CO: Object = root.get_node("/root/Coordinator")
	AG.rebuild()
	SP.reset()
	SP.ritual_requirement = {"ritual_salt": 1, "consecrated_chalk": 1, "candle": 1}
	SP.deposited = {}
	var voss: Agent = AG.get_agent("clerk_voss")
	var dalia: Agent = AG.get_agent("fishwife_dalia")
	var orin: Agent = AG.get_agent("lamplighter_orin")
	for a in [voss, dalia, orin]:
		a.inventory.clear()
		a.downed = false
	# 3 same-task agents x 3 outstanding materials -> a bijective, deterministic allocation.
	var seen: Dictionary = {}
	for a in [voss, dalia, orin]:
		var f: Dictionary = CO.focus_for(a.id)
		_ok(not f.is_empty(), "%s gets a focus" % a.id)
		seen[String(f.get("subtask", ""))] = true
	_ok(seen.size() == 3, "the three allocations cover three DISTINCT materials (bijective)")
	var again: Dictionary = CO.focus_for("clerk_voss")
	_ok(again == CO.focus_for("clerk_voss"), "allocation is deterministic across calls")
	# A bystander with no task gets no focus.
	var pell: Agent = AG.get_agent("dockhand_pell")
	_ok(CO.focus_for(pell.id).is_empty(), "a task-less bystander gets no focus")
	# A carrier is allocated the material it already holds (deliver, not re-fetch).
	dalia.inventory.clear()
	dalia.add_item("candle", 1)
	var fd: Dictionary = CO.focus_for(dalia.id)
	_ok(String(fd.get("subtask", "")) == "candle" and String(fd.get("why", "")) == "you carry it",
		"a carrier is allocated the material it already carries")
	dalia.inventory.clear()
	# Deposited materials leave the pool: with two deposited, only one agent holds a SUBTASK
	# (the others learn everything left is claimed — a non-empty fact, but not an allocation).
	SP.deposit("ritual_salt")
	SP.deposit("consecrated_chalk")
	var focused := 0
	var empties := 0
	for a in [voss, dalia, orin]:
		var f1: Dictionary = CO.focus_for(a.id)
		if String(f1.get("subtask", "")) != "":
			focused += 1
		elif f1.is_empty():
			empties += 1
		# Review finding: while the last material lies UNCLAIMED on the ground (merely allocated to
		# a peer), telling the others "everything is carried" would be a FALSE published fact.
		_ok(not bool(f1.get("all_claimed", false)),
			"no false all_claimed while a material lies unclaimed on the ground")
	_ok(focused == 1, "with one material outstanding, exactly one agent holds a subtask")
	_ok(empties == 2, "the unallocated agents simply hold no focus (design §6: extras get none)")
	# A downed agent is skipped by the partition.
	SP.deposited = {}
	voss.downed = true
	_ok(CO.focus_for(voss.id).is_empty(), "a downed agent gets no focus")
	voss.downed = false
	# When every outstanding material is already in plan-members' hands, the empty-handed agent is
	# told THAT (live finding: dalia looped move_to an empty cache with no way to know why).
	SP.deposited = {}
	voss.inventory.clear(); voss.add_item("ritual_salt", 1)
	orin.inventory.clear(); orin.add_item("consecrated_chalk", 1); orin.add_item("candle", 1)
	dalia.inventory.clear()
	var f_claimed: Dictionary = CO.focus_for(dalia.id)
	_ok(bool(f_claimed.get("all_claimed", false)),
		"an empty-handed agent learns every outstanding material is already carried")
	voss.inventory.clear(); orin.inventory.clear()
	# The focus rides the snapshot as data and is forwarded on the /decide path only with a task.
	SP.deposited = {}
	var snap: Dictionary = Perception.build_snapshot(voss, voss.position)
	_ok(not (snap.get("focus", {}) as Dictionary).is_empty(), "build_snapshot carries the task-bearer's focus")
	var rc: Dictionary = Perception.decide_request(snap, "sess-co")
	_ok(not ((rc["perception"] as Dictionary).get("focus", {}) as Dictionary).is_empty(),
		"decide_request forwards focus for a task-bearer")
	var psnap: Dictionary = Perception.build_snapshot(pell, pell.position)
	_ok((psnap.get("focus", {}) as Dictionary).is_empty(), "a bystander's snapshot has no focus")
	SP.reset()

## True when any line of the agent's short_memory contains `needle` (case-insensitive).
func _memory_mentions(agent: Agent, needle: String) -> bool:
	for line in agent.short_memory:
		if String(line).to_lower().contains(needle.to_lower()):
			return true
	return false

func _test_cult_progress_panel() -> void:
	print("[cult panel]")
	var SP: Object = root.get_node("/root/SummoningPlan"); SP.reset()
	var EB: Object = root.get_node("/root/EventBus"); EB.clear()
	var panel = load("res://ui/CultProgressPanel.tscn").instantiate()
	root.add_child(panel)
	await process_frame
	_ok(not panel.visible, "panel hidden by default")
	SP.countdown_beats = SP.START_COUNTDOWN / 2
	panel.toggle()
	await process_frame
	_ok(panel.visible, "panel toggles visible")
	_ok(is_equal_approx(panel.get_node("Margin/Body/Closeness/Bar").value, 50.0), "closeness bar at 50%")
	_ok("50%" in panel.get_node("Margin/Body/Summary").text, "summary line shows the readiness percentage")
	# Both secret cult-move types (raw + Critic-amended) must be filtered out; only the
	# public player deed survives. Assert against the rendered TYPE name, not the verb.
	EB.emit_event("agent_action", {"actor": "clerk_voss", "verb": "perform_ritual_step"})
	EB.emit_event("agent_action_amended", {"actor": "masked_acolyte", "verb": "perform_ritual_step"})
	EB.emit_event("player_sabotage", {"actor": "player", "item": "candle"})
	var joined := ""
	for line in panel.public_event_lines():
		joined += String(line) + "\n"
	_ok("player sabotage" in joined, "public player event is listed")
	_ok(not ("agent action" in joined), "secret agent_action move is excluded")
	_ok(not ("amended" in joined), "secret agent_action_amended move is excluded")
	panel.queue_free()
	await process_frame
	SP.reset(); EB.clear()

func _test_npc_binds_to_agent() -> void:
	print("[npc bind]")
	var Ag: Object = root.get_node("/root/Agents")
	Ag.rebuild()
	var agent = Ag.all()[0]
	agent.position = Vector2(777, 333)
	var npc = load("res://scenes/NPC.tscn").instantiate()
	npc.npc_id = agent.id
	root.add_child(npc)
	await process_frame
	_ok(npc.is_bound(), "node bound to a registry agent")
	_ok(npc.steer_goal() == Vector2(777, 333), "bound node steers toward its agent's position")
	# Unknown id falls back to schedule mode (not bound).
	var loose = load("res://scenes/NPC.tscn").instantiate()
	loose.npc_id = "no_such_agent"
	root.add_child(loose)
	await process_frame
	_ok(not loose.is_bound(), "unknown id is not bound (schedule fallback)")
	# A bound body is a strict PUPPET of its agent: each physics step it glides DIRECTLY toward
	# agent.position (the data sim owns pathing), IGNORING the schedule waypoint and the navmesh. This
	# is the fix for cult bodies "flying" toward stale per-scene schedule coordinates on scene entry.
	agent.position = Vector2(777, 333)
	npc.global_position = Vector2.ZERO
	npc._target = Vector2(-900, -900)   # a stale waypoint pointing the OPPOSITE way; must be ignored
	for i in 20:
		npc._physics_process(1.0 / 60.0)
	_ok(npc.global_position.x > 0.0 and npc.global_position.y > 0.0,
		"a bound body glides toward its agent, never the schedule waypoint")
	_ok(npc.global_position.distance_to(agent.position) < Vector2.ZERO.distance_to(agent.position),
		"a bound body closes distance to its agent's position each step")
	npc.queue_free()
	loose.queue_free()
	await process_frame

## Minimal stand-in for GameController's RoomView contract: a node in group "game_controller"
## exposing world_scene() (where bodies parent) and current_room() (the player's room id).
class _StubGameController extends Node:
	var scene: Node2D = null
	var room: String = "city"
	func world_scene() -> Node: return scene
	func current_room() -> String: return room

## A faithful stand-in for the 7 real `ui_cancel` close-panels (InventoryPanel/PrayerPanel/etc.):
## Control that, when visible, consumes Escape in _unhandled_input via set_input_as_handled(). Used by
## the pause-menu test (review finding #1) to prove Escape with a panel open closes the PANEL and does
## NOT let pause stack on top — the shared-Escape ordering contract the real panels all rely on.
class _PolishEscPanel extends Control:
	var consumed_escape: bool = false
	func _ready() -> void:
		visible = false
	func _unhandled_input(event: InputEvent) -> void:
		if visible and event.is_action_pressed("ui_cancel"):
			visible = false
			consumed_escape = true
			get_viewport().set_input_as_handled()

## A MockSidecar whose converse() BLOCKS for `delay_ms` (via OS.delay_msec) before returning the
## scripted reply. Used to prove send_utterance does NOT block the caller: if converse ran on the
## MAIN thread, the send call would take >= delay_ms; on a worker thread it returns immediately and
## the reply lands later. The block runs only OFF the main thread (the async wrapper's worker), so
## the frame is never stalled.
class _SlowMockSidecar extends MockSidecar:
	var delay_ms: int = 250
	func converse(request: Dictionary) -> Dictionary:
		OS.delay_msec(delay_ms)
		return super.converse(request)

## RoomView's DEFAULT (empty tracked list) tracks EVERY registered non-player agent: a civilian
## sharing the player's room gets a body, one in another room does not, and the spawn still keys
## on agent.room == the player's room. set_tracked(subset) remains available to narrow rendering.
func _test_roomview_tracks_all() -> void:
	print("[roomview tracks everyone by default]")
	var AG: Object = root.get_node("/root/Agents")
	var RV: Object = root.get_node("/root/RoomView")
	AG.rebuild()
	AG.ensure_player_proxy(Vector2(100, 100), "city")
	var gc := _StubGameController.new()
	var world := Node2D.new()
	gc.scene = world
	gc.add_child(world)
	gc.add_to_group("game_controller")
	root.add_child(gc)
	# One civilian shares the player's room; another is elsewhere.
	var hawker: Agent = AG.get_agent("hawker_neille")
	var bram: Agent = AG.get_agent("bram_kell")
	hawker.room = "city"
	bram.room = "cathedral_nave"
	RV.set_tracked([])   # [] = the track-all default
	_ok(RV._bodies.has("hawker_neille"), "a civilian sharing the player's room gets a body")
	_ok(RV._bodies.get("hawker_neille") != null and is_instance_valid(RV._bodies["hawker_neille"]),
		"the spawned body is a live node parented under the world scene")
	_ok(not RV._bodies.has("bram_kell"), "an agent in another room gets no body")
	_ok(not RV._bodies.has("player"), "the player proxy never grows an NPC body")
	# Body spawn keys on agent.room == the player's room: swap the two and reconcile.
	bram.room = "city"
	hawker.room = "cathedral_nave"
	RV.reconcile()
	_ok(RV._bodies.has("bram_kell"), "an agent entering the player's room gains a body on reconcile")
	_ok(not RV._bodies.has("hawker_neille"), "an agent leaving the player's room loses its body")
	# The restriction seam still works: a non-empty tracked list narrows rendering to that subset.
	RV.set_tracked(["bram_kell"])
	_ok(RV._bodies.has("bram_kell") and RV._bodies.size() == 1,
		"a non-empty tracked list restricts rendering to that subset")
	# Teardown: despawn while the bodies are still live (clear_tracked assigns them to typed vars,
	# so it must run BEFORE the stub world frees them), then drop the stub controller so RoomView is
	# inert again for later tests (no game_controller in the tree -> reconcile bails on null parent).
	RV.clear_tracked()
	gc.remove_from_group("game_controller")
	root.remove_child(gc)
	gc.free()
	AG.rebuild()

func _test_inspect_signal() -> void:
	print("[inspect signal]")
	var WS: Object = root.get_node("/root/WorldState")
	var got: Array = []
	var cb := func(id: String): got.append(id)
	WS.inspect_requested.connect(cb)
	WS.inspect_requested.emit("clerk_voss")
	_ok(got == ["clerk_voss"], "inspect_requested carries the agent id")
	WS.inspect_requested.disconnect(cb)

func _test_character_card_opens() -> void:
	print("[character card]")
	var Ag: Object = root.get_node("/root/Agents"); Ag.rebuild()
	var WS: Object = root.get_node("/root/WorldState")
	var id: String = Ag.all()[0].id
	var card = load("res://ui/CharacterCard.tscn").instantiate()
	root.add_child(card)
	await process_frame
	_ok(not card.visible, "card hidden by default")
	WS.inspect_requested.emit(id)
	await process_frame
	_ok(card.visible, "card opens on inspect_requested")
	_ok(card.shows_agent(id), "card is showing the inspected agent")
	# _refresh() actually bound the agent's data, not just toggled visibility:
	var agent_obj: Object = Ag.get_agent(id)
	_ok(card._name.text == agent_obj.display_name, "card shows the inspected agent's name")
	_ok(card._thought.text != "", "card shows a non-empty thought line")
	card.queue_free()
	await process_frame

func _test_city_blocks_scene() -> void:
	print("[city blocks scene]")
	# Hand-authored traversal map: ~50 building bodies + a player, all real nodes baked into the
	# scene file (no runtime/procedural construction). Guard the authored structure so it can't
	# silently regress: the Buildings container exists, every building is a solid StaticBody2D with
	# a collision polygon, and a Player is present so the scene is walkable on its own.
	var packed: PackedScene = load("res://scenes/CityBlocks.tscn")
	_ok(packed != null, "CityBlocks.tscn exists and loads")
	if packed == null:
		return
	var scene = packed.instantiate()
	root.add_child(scene)
	await process_frame
	await process_frame
	var buildings: Node = scene.get_node_or_null("Buildings")
	_ok(buildings != null, "scene has a Buildings container")
	var bodies: Array = []
	if buildings != null:
		for c in buildings.get_children():
			if c is StaticBody2D:
				bodies.append(c)
	_ok(bodies.size() >= 45 and bodies.size() <= 60,
		"~50 building bodies authored (got %d)" % bodies.size())
	var all_have_collider := bodies.size() > 0
	for b in bodies:
		var cp: Node = b.get_node_or_null("CollisionPolygon2D")
		if cp == null or (cp as CollisionPolygon2D).polygon.size() < 3:
			all_have_collider = false
	_ok(all_have_collider, "every building has a CollisionPolygon2D collider (>= 3 pts)")
	_ok(scene.get_node_or_null("Player") != null, "scene includes a Player for traversal")
	# Demo parts moved here from the retired City.tscn hub: the city-edge wall ring keeps the
	# player on the map, two interior-room transition doors lead to the Nighthawks HQ and the
	# University archive, and at least the demo NPCs (Orin, Dalia) populate the streets -- all
	# authored editor nodes living directly in this scene.
	var walls: Node = scene.get_node_or_null("Walls")
	var wall_bodies := 0
	if walls != null:
		for c in walls.get_children():
			if c is StaticBody2D:
				wall_bodies += 1
	_ok(wall_bodies == 4, "four city-edge boundary walls keep the player on the map (got %d)" % wall_bodies)
	var door_targets: Array = []
	var npc_count := 0
	for n in scene.get_children():
		if n.is_in_group("npc"):
			npc_count += 1
		if n.is_in_group("interactable"):
			var t: Variant = n.get("target_scene")
			if typeof(t) == TYPE_STRING and t != "":
				door_targets.append(t)
	_ok(npc_count >= 2, "demo NPCs authored into the city (got %d)" % npc_count)
	_ok(door_targets.has("res://scenes/NighthawksHQ.tscn"),
		"a transition door leads to the Nighthawks HQ interior")
	_ok(door_targets.has("res://scenes/UniversityArchive.tscn"),
		"a transition door leads to the University archive interior")
	# DECOUPLED from ActionCommit.SITES: CityBlocks is the retired hub with its OWN local space, and
	# the sim's rite anchor now lives in the live City.tscn's space (coordinate-unification pass —
	# the live-scene agreement is asserted in _test_city_scene_placements_legal). Here we only check
	# the retired scene's internal authoring: a Warehouse marker, a sabotage interactable near it,
	# and that point clear of the scene's own colliders.
	_ok(scene.get_node_or_null("Warehouse") != null, "scene has a Warehouse rite-site marker")
	var sabotage: Node = null
	for n in scene.get_children():
		if n.is_in_group("interactable") and bool(n.get("sabotage_cache")):
			sabotage = n
			break
	_ok(sabotage != null, "scene has a sabotage-the-cache interactable")
	if sabotage != null:
		var rite: Vector2 = (sabotage as Node2D).position
		var wh: Node2D = scene.get_node_or_null("Warehouse")
		if wh != null:
			_ok(rite.distance_to(wh.position) <= 600.0,
				"the sabotage point sits by the retired hub's own Warehouse marker")
		var buried := false
		if buildings != null:
			for b in buildings.get_children():
				var cp: CollisionPolygon2D = b.get_node_or_null("CollisionPolygon2D")
				if cp != null and Geometry2D.is_point_in_polygon(rite - (b as Node2D).position, cp.polygon):
					buried = true
		_ok(not buried, "the retired hub's sabotage point is clear of its own building colliders")
	scene.queue_free()
	await process_frame

func _test_occult_divination() -> void:
	print("[occult divination]")
	var OTM: Object = root.get_node("/root/OccultToolManager")
	var INV: Object = root.get_node("/root/Inventory")
	var WS: Object = root.get_node("/root/WorldState")
	var WM: Object = root.get_node("/root/WorldManager")
	var M: Object = root.get_node("/root/Meters")
	OTM.rebuild()
	INV.clear()
	WS.set_pressure(&"fatigue", 0.0)
	WS.set_pressure(&"attention", 0.0)
	WS.set_pressure(&"corruption", 0.0)   # no mislead at zero corruption
	M.reset()                             # M25: costs now land on the live meters; start them clean
	var mad0: float = M.get_meter("madness")
	var notice0: float = M.get_meter("notice")
	# Gating: cannot use without owning the kit + the candle ingredient.
	_ok(OTM.can_use("divination") == false, "divination blocked without tool item")
	INV.add("divination_kit")
	_ok(OTM.can_use("divination") == false, "divination blocked without candle ingredient")
	INV.add("candle", 1)
	_ok(OTM.can_use("divination") == true, "divination usable once kit + candle present")
	# Use: pays cost, consumes the candle, yields a directional lead.
	var res: Dictionary = OTM.use("divination")
	_ok(res.get("ok", false), "divination returns ok")
	_ok(String(res.get("lead", "")) != "", "divination yields a directional lead")
	# M25 (backlog "M18"): the tool's fatigue/attention cost now pays the LIVE meters (Madness/Notice),
	# not the dead legacy WorldState pressures (which stay put).
	_ok(M.get_meter("madness") > mad0, "divination spent Madness for its fatigue cost")
	_ok(M.get_meter("notice") > notice0, "divination spent Notice for its attention cost")
	_ok(is_equal_approx(WS.get_pressure(&"fatigue"), 0.0), "divination no longer drives the dead legacy fatigue")
	_ok(INV.count_of("candle") == 0, "divination consumed the candle")
	# No-name guarantee: the lead never contains the true resolved site id.
	var true_site: String = String(WM.slots.get("primary_ritual_site", ""))
	_ok(true_site == "" or not String(res["lead"]).contains(true_site), "lead never names the true site")

func _test_divination_hints_never_name_site() -> void:
	print("[divination no-name guarantee]")
	for site in DivinationTool.SITE_HINTS.keys():
		var hint: String = String(DivinationTool.SITE_HINTS[site])
		_ok(not hint.to_lower().contains(String(site).to_lower()),
			"hint for '%s' never contains its own site id" % site)

func _test_occult_other_tools() -> void:
	print("[occult other tools]")
	var OTM: Object = root.get_node("/root/OccultToolManager")
	var INV: Object = root.get_node("/root/Inventory")
	var WS: Object = root.get_node("/root/WorldState")
	OTM.rebuild()
	INV.clear()
	WS.set_pressure(&"fatigue", 0.0)
	WS.set_pressure(&"corruption", 0.0)
	# Residue sight: owns lens, no ingredient cost.
	INV.add("spirit_lens")
	_ok(OTM.can_use("residue_sight"), "residue sight usable with just the lens")
	var r1: Dictionary = OTM.use("residue_sight")
	_ok(r1.get("ok", false), "residue sight returns ok")
	# Dream fragments: produces dream_residue.
	INV.add("dream_draught")
	INV.add("dream_herb", 1)
	var r2: Dictionary = OTM.use("dream_fragments")
	_ok(r2.get("ok", false), "dream fragments returns ok")
	_ok(INV.count_of("dream_residue") == 1, "dream fragments produces dream_residue")
	_ok(INV.count_of("dream_herb") == 0, "dream fragments consumes dream_herb")
	# Gray fog: hard-capped at 3 uses per run.
	INV.add("gray_fog_focus")
	INV.add("consecrated_chalk", 9)
	_ok(OTM.use("gray_fog").get("ok", false), "gray fog use 1 ok")
	OTM.use("gray_fog")
	OTM.use("gray_fog")
	_ok(OTM.can_use("gray_fog") == false, "gray fog refused after 3 uses")
	_ok(OTM.use("gray_fog").get("ok", false) == false, "gray fog 4th use blocked")

func _test_occult_tool_views() -> void:
	print("[occult tool views]")
	var OTM: Object = root.get_node("/root/OccultToolManager")
	var views: Array = OTM.tool_views()
	_ok(views.size() == 4, "four occult tools surfaced")
	var div: Variant = null
	for v in views:
		if v["id"] == "divination":
			div = v
	_ok(div != null, "divination present")
	_ok(String(div["name"]) == "Divination", "name surfaced")
	_ok(String(div["description"]) != "", "description surfaced")
	_ok(is_equal_approx(float(div["cost"]["fatigue"]), 8.0), "fatigue cost surfaced")
	_ok((div["cost"]["items"] as Dictionary).has("candle"), "ingredient cost surfaced")
	_ok(div.has("can_use") and div.has("uses_left"), "availability fields surfaced")

func _test_ritual_panel() -> void:
	print("[ritual panel]")
	var panel = load("res://ui/RitualPanel.tscn").instantiate()
	root.add_child(panel)
	await process_frame
	_ok(not panel.visible, "panel hidden by default")
	panel.toggle()
	await process_frame
	_ok(panel.visible, "panel toggles visible")
	_ok(panel.tool_row_count() == 4, "renders one row per occult tool")
	_ok(panel.rite_step_count() >= 3, "summoning rite lists its steps")
	panel.queue_free()
	await process_frame

func _test_player_actions() -> void:
	print("[player actions]")
	var PA: Object = root.get_node("/root/PlayerActions")
	var SP: Object = root.get_node("/root/SummoningPlan")
	var OV: Object = root.get_node("/root/Overseer")
	var EB: Object = root.get_node("/root/EventBus")
	var AG: Object = root.get_node("/root/Agents")
	AG.rebuild(); SP.reset(); OV.reset(); EB.clear()

	# Sabotage: strips a cult ingredient, raises impede, sets back the countdown, and
	# marks the player involved (so the overseer will now allow exposure).
	var cd_before: int = SP.countdown_beats
	var impede_before: float = SP.impede_score
	_ok(PA.sabotage("ritual_salt"), "sabotage of a held ingredient succeeds")
	_ok(SP.countdown_beats > cd_before, "sabotage sets back the summoning countdown")
	_ok(SP.impede_score > impede_before, "sabotage raises impede")
	_ok(EB.events("player_sabotage").size() == 1, "sabotage logs a player event")
	_ok(OV.allows_exposure(), "sabotage marks the player involved")
	# Sabotage of an absent ingredient fails and changes nothing.
	_ok(PA.sabotage("does_not_exist") == false, "sabotage of an unheld ingredient fails")

	# Social influence: turning the waverer stops his concealment and raises impede.
	var orin: Agent = AG.get_agent("lamplighter_orin")
	_ok(not orin.has_adopted_goal("Help the investigator stop the cell"), "orin starts un-turned (with the cell)")
	var impede2: float = SP.impede_score
	_ok(PA.social_influence("lamplighter_orin"), "turning the waverer succeeds")
	_ok(orin.has_adopted_goal("Help the investigator stop the cell"), "the waverer is turned (adopts a defection goal)")
	_ok(SP.impede_score > impede2, "turning the waverer raises impede")
	_ok(EB.events("player_social").size() == 1, "social influence logs a player event")
	# A non-waverer cannot be turned.
	_ok(PA.social_influence("clerk_voss") == false, "the committed leader cannot be turned")

func _test_player_sabotage_any() -> void:
	print("[player sabotage_any]")
	var PA: Object = root.get_node("/root/PlayerActions")
	var SP: Object = root.get_node("/root/SummoningPlan")
	var EB: Object = root.get_node("/root/EventBus")
	SP.reset(); EB.clear()
	# The warehouse interactable gives the player a single "strip the cache" verb — they don't
	# name an ingredient. sabotage_any picks one of the held items and routes it through sabotage.
	var total_before: int = SP._total_ingredients()
	var impede_before: float = SP.impede_score
	var stripped: String = PA.sabotage_any()
	_ok(stripped in ["candle", "consecrated_chalk", "ritual_salt"], "sabotage_any strips a real cache ingredient")
	_ok(SP._total_ingredients() == total_before - 1, "sabotage_any removes exactly one item from the cache")
	_ok(SP.impede_score > impede_before, "sabotage_any raises impede (it routes through sabotage)")
	_ok(EB.events("player_sabotage").size() == 1, "sabotage_any logs a player_sabotage event")
	# Drain the cache, then sabotage_any must no-op cleanly — nothing left to strip.
	while PA.sabotage_any() != "":
		pass
	EB.clear()
	impede_before = SP.impede_score
	_ok(PA.sabotage_any() == "", "sabotage_any returns empty when the cache is bare")
	_ok(SP.impede_score == impede_before, "a no-op sabotage_any does not change impede")
	_ok(EB.events("player_sabotage").size() == 0, "a no-op sabotage_any logs nothing")
	SP.reset(); EB.clear()

func _test_dialogue_social_influence_effect() -> void:
	print("[dialogue social_influence]")
	var DM: Object = root.get_node("/root/DialogueManager")
	var AG: Object = root.get_node("/root/Agents")
	var SP: Object = root.get_node("/root/SummoningPlan")
	var EB: Object = root.get_node("/root/EventBus")
	AG.rebuild(); SP.reset(); EB.clear()
	var orin: Agent = AG.get_agent("lamplighter_orin")
	_ok(orin.role == "scout_waverer" and not orin.has_adopted_goal("Help the investigator stop the cell"), "orin starts as an un-turned waverer (precondition)")
	var impede_before: float = SP.impede_score
	# A dialogue effect of type social_influence routes through PlayerActions: the waverer is
	# won over to the player's side and the hidden impede score rises — the diegetic counterpart
	# to the console/`PA.social_influence` path, so persuasion in conversation actually bites.
	DM._apply_effect({"type": "social_influence", "agent": "lamplighter_orin"})
	_ok(orin.has_adopted_goal("Help the investigator stop the cell"), "social_influence dialogue effect turns orin to the player's side")
	_ok(SP.impede_score > impede_before, "turning the waverer in dialogue raises the hidden impede score")
	_ok(EB.events("player_social").size() == 1, "the dialogue turn logs a player_social event")
	AG.rebuild(); SP.reset(); EB.clear()

func _test_orin_persuade_dialogue() -> void:
	print("[orin persuade dialogue]")
	var DM: Object = root.get_node("/root/DialogueManager")
	var AG: Object = root.get_node("/root/Agents")
	var SP: Object = root.get_node("/root/SummoningPlan")
	var ND: Object = root.get_node("/root/NpcDB")
	AG.rebuild(); SP.reset()
	# Orin must be wired to his own dialogue tree, otherwise the player can never reach the
	# persuade option in-world (an NPC with an empty dialogue_id can't be talked to at all).
	_ok(String(ND.get_def("lamplighter_orin").get("dialogue_id", "")) == "orin_waverer",
		"orin is wired to the orin_waverer dialogue tree")
	_ok(DM.trees.has("orin_waverer"), "the orin_waverer dialogue tree is authored")
	var tree: Dictionary = DM.trees.get("orin_waverer", {})
	var nodes: Dictionary = tree.get("nodes", {})
	var root_node: Dictionary = nodes.get(String(tree.get("start", "root")), {})
	var orin: Agent = AG.get_agent("lamplighter_orin")
	_ok(not orin.has_adopted_goal("Help the investigator stop the cell"), "orin starts un-turned (precondition)")
	# While orin is still un-turned the persuade line is on offer (gated requires_agent_unturned).
	var visible_cult: Array = DM._visible_options(root_node)
	var idx: int = _option_index_with(visible_cult, "Persuade")
	_ok(idx >= 0, "the persuade option is visible while orin is a cultist")
	# Choosing it carries a social_influence effect that turns him to the player's side — the same
	# verb the console/world use, so the conversation actually stops his concealment and adds impede.
	var impede_before: float = SP.impede_score
	for e in (visible_cult[idx] as Dictionary).get("effects", []):
		DM._apply_effect(e)
	_ok(orin.has_adopted_goal("Help the investigator stop the cell"), "choosing the persuade option turns orin to the player's side")
	_ok(SP.impede_score > impede_before, "persuading orin in conversation raises the impede score")
	# Once he's turned, the persuade option is gated away — you can't re-persuade an ally, and the
	# vanishing option reads as the conversation having moved past the moment of doubt.
	var visible_ally: Array = DM._visible_options(root_node)
	_ok(_option_index_with(visible_ally, "Persuade") < 0,
		"the persuade option is hidden once orin is already an ally")
	AG.rebuild(); SP.reset()

## The Nighthawk Captain's briefing physically issues the two ready occult tools (previously
## unobtainable in-world): walking the captain tree to its 'charge' node fires grant_item dialogue
## effects for divination_kit + spirit_lens. Both are non-stackable (cap 1), so a replayed briefing
## — or a re-applied effect — is a refused no-op: the grant is idempotent by construction.
func _test_captain_briefing_grants_tools() -> void:
	print("[captain briefing grants occult tools]")
	var DM: Object = root.get_node("/root/DialogueManager")
	var INV: Object = root.get_node("/root/Inventory")
	INV.clear()
	_ok(not INV.has("divination_kit") and not INV.has("spirit_lens"),
		"no occult tools held before the briefing (precondition)")
	DM.start("captain")
	# Root option 1 is the briefing ask ("What do you need from me?") -> the 'charge' node,
	# whose node-enter effects carry the clue, the lead, and the two grants.
	DM.choose("root", 1)
	_ok(DM.current_node_id() == "charge", "the briefing walk lands on the charge node")
	_ok(INV.count_of("divination_kit") == 1, "the briefing grants the divination kit")
	_ok(INV.count_of("spirit_lens") == 1, "the briefing grants the spirit lens")
	# Replay the effect directly: the non-stackable cap refuses the duplicate.
	DM._apply_effect({"type": "grant_item", "item": "divination_kit"})
	DM._apply_effect({"type": "grant_item", "item": "spirit_lens"})
	_ok(INV.count_of("divination_kit") == 1 and INV.count_of("spirit_lens") == 1,
		"replaying the grant cannot dupe a non-stackable tool")
	# The other two tools stay ungranted for now (see the grant_item TODO in DialogueManager).
	_ok(not INV.has("dream_draught") and not INV.has("gray_fog_focus"),
		"dream_draught and gray_fog_focus remain deliberately ungranted")
	DM.choose("charge", 0)   # "Understood." -> end
	_ok(not DM.active, "the briefing dialogue closes cleanly")
	INV.clear()

func _test_dev_console_interference_commands() -> void:
	print("[dev console interference]")
	var DC: Object = root.get_node("/root/DevConsole")
	var SP: Object = root.get_node("/root/SummoningPlan")
	var EB: Object = root.get_node("/root/EventBus")
	var AG: Object = root.get_node("/root/Agents")
	AG.rebuild(); SP.reset(); EB.clear()
	# `sabotage <item>` strips that named ingredient through PlayerActions.sabotage — the console
	# counterpart to the warehouse interactable, for poking the rite without walking there.
	var salt_before: int = int(SP.ingredients.get("ritual_salt", 0))
	DC._run("sabotage ritual_salt")
	_ok(int(SP.ingredients.get("ritual_salt", 0)) == salt_before - 1, "console `sabotage <item>` strips the named ingredient")
	_ok(EB.events("player_sabotage").size() == 1, "console sabotage logs a player_sabotage event")
	# `sabotage` with no argument strips whatever the cache still holds (sabotage_any).
	var total_before: int = SP._total_ingredients()
	DC._run("sabotage")
	_ok(SP._total_ingredients() == total_before - 1, "console `sabotage` with no arg strips one held item")
	_ok(EB.events("player_sabotage").size() == 2, "the bare console sabotage also logs an event")
	# `turn <agent>` routes through social_influence: the waverer flips, anyone else is refused.
	var orin: Agent = AG.get_agent("lamplighter_orin")
	_ok(not orin.has_adopted_goal("Help the investigator stop the cell"), "orin starts un-turned (precondition)")
	DC._run("turn lamplighter_orin")
	_ok(orin.has_adopted_goal("Help the investigator stop the cell"), "console `turn <agent>` turns the waverer to the player's side")
	_ok(EB.events("player_social").size() == 1, "console turn logs a player_social event")
	# Turning a committed leader is refused and changes nothing.
	var voss: Agent = AG.get_agent("clerk_voss")
	DC._run("turn clerk_voss")
	_ok(not voss.has_adopted_goal("Help the investigator stop the cell"), "console `turn` cannot flip a committed leader")
	_ok(EB.events("player_social").size() == 1, "a refused console turn logs no new event")
	AG.rebuild(); SP.reset(); EB.clear()

func _test_combat_scaled_by_impede() -> void:
	print("[combat]")
	var SP: Object = root.get_node("/root/SummoningPlan")

	# Strong manifestation (no impede): hard fight.
	SP.reset()
	var hard := CombatEncounter.new(SP.manifestation_strength())
	var hard_result: Dictionary = hard.auto_resolve()

	# Weakened manifestation (heavy impede + stripped ingredients): easy fight.
	SP.reset()
	SP.add_impede(70.0, "test")
	SP.remove_ingredient("ritual_salt", 3)
	var easy := CombatEncounter.new(SP.manifestation_strength())
	var easy_result: Dictionary = easy.auto_resolve()

	_ok(easy.enemy_max_hp < hard.enemy_max_hp, "more impede -> weaker enemy")
	_ok(easy_result["player_hp_left"] > hard_result["player_hp_left"], "more impede -> player ends with more HP")
	_ok(easy_result["win"] == true, "a heavily-impeded summoning is winnable")
	_ok(hard_result.has("rounds"), "result reports the round count")
	# The occult ability hits harder than a basic attack.
	var enc := CombatEncounter.new(50.0)
	_ok(enc.OCCULT_DAMAGE > enc.ATTACK_DAMAGE, "occult ability beats a basic attack")

	# --- Retuned scaling. The residual fight only ever runs at strength <= STOP_THRESHOLD (60),
	# so it must be lethal in the mid-50s and survivable in the low-40s. Enemy HP = 2.5x strength,
	# enemy damage = 0.40x strength (player unchanged: 100 HP, 18 basic / 30 occult every 3rd round).
	var probe := CombatEncounter.new(50.0)
	_ok(is_equal_approx(probe.enemy_max_hp, 125.0), "enemy HP scales at 2.5x strength")
	_ok(is_equal_approx(probe.enemy_damage, 20.0), "enemy damage scales at 0.40x strength")
	# Crossover: a strength-55 residual is lethal; a strength-43 residual is survivable. This is
	# what makes turning Orin (43) the lever that upgrades near-good -> all-good over 2 sabotages (55).
	_ok(CombatEncounter.new(55.0).auto_resolve()["win"] == false, "strength 55 residual is lethal (near-good)")
	_ok(CombatEncounter.new(43.0).auto_resolve()["win"] == true, "strength 43 residual is survivable (all-good)")

## The two-gate climax resolver (pure logic). Gate 1: above the stop threshold the descent
## completes and the city dies (no fight). Gate 2: a stopped descent runs the residual fight,
## and surviving it is the difference between near-good (you die) and all-good (you live).
func _test_endgame_resolver() -> void:
	print("[endgame resolver]")
	_ok(is_equal_approx(EndGameResolver.STOP_THRESHOLD, 60.0), "stop threshold is 60")
	# Gate 1 — descent completes above the threshold: the city dies, with no fight.
	_ok(String(EndGameResolver.resolve(100.0).get("outcome", "")) == "city_dies", "strength 100 (no interference) -> city dies")
	_ok(String(EndGameResolver.resolve(77.5).get("outcome", "")) == "city_dies", "strength 77.5 (1 sabotage) -> city dies")
	# Boundary — exactly at the threshold the descent is *stopped*, not a city death.
	_ok(String(EndGameResolver.resolve(60.0).get("outcome", "")) != "city_dies", "strength 60 is stopped, not a city death")
	# Gate 2 — a stopped descent runs the residual fight: mid-50s lethal, low-40s survivable.
	_ok(String(EndGameResolver.resolve(55.0).get("outcome", "")) == "near_good", "strength 55 stopped but lethal -> near-good")
	_ok(String(EndGameResolver.resolve(43.0).get("outcome", "")) == "all_good", "strength 43 stopped and survived -> all-good")
	_ok(String(EndGameResolver.resolve(32.5).get("outcome", "")) == "all_good", "strength 32.5 (3 sabotages) -> all-good")
	# city-dies carries no fight; stopped outcomes carry the fight-result fields.
	var cd: Dictionary = EndGameResolver.resolve(100.0)
	_ok(bool(cd.get("win", true)) == false and int(cd.get("rounds", -1)) == 0, "city-dies has no fight (win=false, 0 rounds)")
	var ag: Dictionary = EndGameResolver.resolve(43.0)
	_ok(bool(ag.get("win", false)) == true and int(ag.get("rounds", 0)) > 0, "all-good carries a won fight with rounds")
	_ok(float(ag.get("player_hp_left", 0.0)) > 0.0, "all-good reports surviving HP")
	_ok(is_equal_approx(float(ag.get("strength", 0.0)), 43.0), "result echoes the resolved strength")

## End-to-end guard over the whole chain: player levers -> manifestation_strength -> ending.
## This locks the ending *table* so that a future tweak to SABOTAGE_IMPEDE/SOCIAL_IMPEDE, the
## ingredient counts, or the resolver thresholds can't silently move which ending each play reaches.
func _test_endgame_ending_bands() -> void:
	print("[endgame ending bands]")
	var PA: Object = root.get_node("/root/PlayerActions")
	var SP: Object = root.get_node("/root/SummoningPlan")
	var AG: Object = root.get_node("/root/Agents")
	var EB: Object = root.get_node("/root/EventBus")

	# No interference: the descent (降临) completes — the whole city dies, with no fight.
	AG.rebuild(); SP.reset(); EB.clear()
	_ok(is_equal_approx(SP.manifestation_strength(), 100.0), "no interference -> strength 100")
	_ok(String(EndGameResolver.resolve(SP.manifestation_strength()).get("outcome", "")) == "city_dies",
		"no interference -> city dies")

	# Two sabotages stop the descent, but the residual manifestation still kills the player.
	AG.rebuild(); SP.reset(); EB.clear()
	PA.sabotage_any(); PA.sabotage_any()
	_ok(is_equal_approx(SP.manifestation_strength(), 55.0), "2 sabotages -> strength 55")
	_ok(String(EndGameResolver.resolve(SP.manifestation_strength()).get("outcome", "")) == "near_good",
		"2 sabotages -> near-good (descent stopped, you die)")

	# Two sabotages PLUS turning Orin (the 邪教 waverer) buys back the player's life.
	AG.rebuild(); SP.reset(); EB.clear()
	PA.sabotage_any(); PA.sabotage_any()
	_ok(PA.social_influence("lamplighter_orin"), "turning Orin succeeds")
	_ok(is_equal_approx(SP.manifestation_strength(), 43.0), "2 sabotages + turn Orin -> strength 43")
	_ok(String(EndGameResolver.resolve(SP.manifestation_strength()).get("outcome", "")) == "all_good",
		"turning Orin upgrades near-good -> all-good")

	# Three sabotages alone also reach the all-good ending.
	AG.rebuild(); SP.reset(); EB.clear()
	PA.sabotage_any(); PA.sabotage_any(); PA.sabotage_any()
	_ok(is_equal_approx(SP.manifestation_strength(), 32.5), "3 sabotages -> strength 32.5")
	_ok(String(EndGameResolver.resolve(SP.manifestation_strength()).get("outcome", "")) == "all_good",
		"3 sabotages -> all-good")

	AG.rebuild(); SP.reset(); EB.clear()

## The EndGame autoload: the thin pause + overlay shell over EndGameResolver. Firing the climax
## signal must drive it to the resolved ending, freeze the world, and log an `endgame` event;
## restart()/_reset_world_state() must reset the cult plan and lift the freeze. We drive those
## methods directly (rather than clicking the overlay buttons) and unpause in teardown so the
## later panel tests still run.
func _test_endgame_autoload() -> void:
	print("[endgame autoload]")
	var EG: Object = root.get_node("/root/EndGame")
	var SP: Object = root.get_node("/root/SummoningPlan")
	var EB: Object = root.get_node("/root/EventBus")
	var AG: Object = root.get_node("/root/Agents")

	var reached: Array = []
	var cb := func(outcome: String, _result: Dictionary): reached.append(outcome)
	EG.ending_reached.connect(cb)

	# A full-strength descent: reaching the ending dooms the city, freezes the world, logs the event.
	AG.rebuild(); SP.reset(); EB.clear()
	paused = false
	SP.summoning_climax.emit(100.0)
	_ok(reached.size() == 1 and String(reached[-1]) == "city_dies", "climax at strength 100 -> city_dies ending")
	_ok(paused, "reaching an ending pauses the world")
	_ok(EB.events("endgame").size() == 1, "EndGame logs an endgame event")

	# A heavily-interfered descent routes to the all-good ending.
	paused = false
	EB.clear()
	SP.summoning_climax.emit(32.5)
	_ok(reached.size() == 2 and String(reached[-1]) == "all_good", "climax at strength 32.5 -> all_good ending")

	# _reset_world_state returns the cult plan to defaults (re-arming the summoning); restart lifts the freeze.
	SP.add_impede(50.0, "test"); SP.remove_ingredient("ritual_salt", 2); SP.climax_fired = true
	EG._reset_world_state()
	_ok(is_equal_approx(SP.impede_score, 0.0), "reset clears the summoning impede")
	_ok(is_equal_approx(SP.manifestation_strength(), 100.0), "reset restores full manifestation strength")
	_ok(SP.climax_fired == false, "reset re-arms the summoning (climax_fired cleared)")
	paused = true
	EG.restart()
	_ok(paused == false, "restart unpauses the world")

	EG.ending_reached.disconnect(cb)
	AG.rebuild(); SP.reset(); EB.clear()
	paused = false

func _test_player_state_save_load() -> void:
	print("[player state save/load]")
	var SP: Object = root.get_node("/root/SummoningPlan")
	var OV: Object = root.get_node("/root/Overseer")
	var OTM: Object = root.get_node("/root/OccultToolManager")
	var SM: Object = root.get_node("/root/SaveManager")
	SP.reset(); OV.reset(); OTM.rebuild()
	SP.add_impede(33.0, "test")
	SP.remove_ingredient("candle", 1)
	OV.player_involved = true
	var tmp := "user://test_player_state.json"
	_ok(SM.save_game(tmp), "save_game writes file")
	SP.reset(); OV.reset()
	_ok(SP.impede_score == 0.0, "impede cleared before load")
	_ok(SM.load_game(tmp), "load_game reads file")
	_ok(abs(SP.impede_score - 33.0) < 0.01, "impede restored")
	_ok(SP.ingredients.get("candle", 0) == 2, "cult ingredient stock restored")
	_ok(OV.player_involved == true, "overseer player-involvement restored")
	DirAccess.remove_absolute(ProjectSettings.globalize_path(tmp))

## Guards the GDScript<->Python boundary: the engine's ActionSchema and the sidecar's
## contract read the same data/action_schema.json, but the two *validators* are written
## independently and could silently diverge. This runs the REAL sidecar code over a
## fixture battery and asserts identical verb sets, identical required-args, and identical
## (ok, reason) verdicts. Skips (does not fail) when no Python interpreter is available.
func _test_gods_db() -> void:
	print("[gods db]")
	_ok(GodDB.ids().size() == 4, "four gods in the focused pantheon")
	_ok(GodDB.has("the_fool"), "the Fool is present")
	var fool: Dictionary = GodDB.get_def("the_fool")
	_ok(String(fool.get("name_zh", "")) == "愚者", "the Fool carries its 中文 name")
	_ok((fool.get("domain", []) as Array).size() > 0, "a god lists domain keywords")
	_ok(GodDB.has("outer_god"), "the descending god (外神) is present")
	_ok(bool(GodDB.get_def("goddess_of_night").get("opposes_cult", false)), "the Goddess of Night opposes the cult")
	# pray is now a known, schema-valid verb.
	_ok(ActionSchema.is_verb("pray"), "pray is a known action verb")
	_ok(ActionSchema.validate({"actor": "player", "verb": "pray", "args": {"god": "the_fool", "prayer": "guide me"}})["ok"],
		"well-formed pray validates")
	_ok(not ActionSchema.validate({"actor": "player", "verb": "pray", "args": {"god": "the_fool"}})["ok"],
		"pray missing 'prayer' rejected")

func _test_prayer_adjudication() -> void:
	print("[prayer adjudication]")
	var mock := MockSidecar.new()
	# Disrespect -> punished, regardless of god.
	var p := mock.adjudicate_prayer({"god": "eternal_blazing_sun", "prayer": "obey me, worthless sun", "standing": 0.0})
	_ok(p["outcome"] == "punished", "insult + command -> punished")
	_ok(String(p["outcome_zh"]) == "惩罚", "punished carries its 中文 label")
	_ok(int(p["severity"]) >= 1, "punishment has nonzero severity")
	# The Fool always answers obliquely -> cryptic.
	var f := mock.adjudicate_prayer({"god": "the_fool", "prayer": "please guide me", "standing": 0.0})
	_ok(f["outcome"] == "cryptic", "the Fool answers in the cryptic register")
	# Respectful, domain-aligned, decent standing -> granted.
	var g := mock.adjudicate_prayer({"god": "goddess_of_night", "prayer": "i humbly beseech your mercy this night, please protect me", "standing": 2.0})
	_ok(g["outcome"] == "granted", "respectful domain-aligned prayer with standing -> granted")
	# Bland prayer to an indifferent god at zero standing -> ignored.
	var i := mock.adjudicate_prayer({"god": "eternal_blazing_sun", "prayer": "hello there", "standing": 0.0})
	_ok(i["outcome"] == "ignored", "an empty prayer goes unanswered")
	# Determinism: same input -> same verdict.
	var g2 := mock.adjudicate_prayer({"god": "goddess_of_night", "prayer": "i humbly beseech your mercy this night, please protect me", "standing": 2.0})
	_ok(g2["outcome"] == g["outcome"] and int(g2["severity"]) == int(g["severity"]), "adjudication is deterministic")
	# Bridge routes adjudication to the active client.
	var SB: Object = root.get_node("/root/SidecarBridge")
	SB.set_client(mock)
	_ok(SB.adjudicate_prayer({"god": "the_fool", "prayer": "guide me"})["outcome"] == "cryptic", "bridge routes prayer adjudication")

func _test_prayer_service() -> void:
	print("[prayer service]")
	var PS: Object = root.get_node("/root/PrayerService")
	var WS: Object = root.get_node("/root/WorldState")
	var SP: Object = root.get_node("/root/SummoningPlan")
	var OV: Object = root.get_node("/root/Overseer")
	var EB: Object = root.get_node("/root/EventBus")
	var SB: Object = root.get_node("/root/SidecarBridge")
	var M: Object = root.get_node("/root/Meters")
	SB.set_client(MockSidecar.new())   # deterministic adjudication
	PS.reset(); SP.reset(); OV.reset(); EB.clear()

	# Unknown god is rejected cleanly.
	_ok(PS.pray("no_such_god", "hi")["ok"] == false, "praying to an unknown god is rejected")

	# Granted by an opposing god: impedes the descent, eases Madness (M25: the old fatigue relief now
	# lands on the live meter), raises standing, and marks the player involved.
	M.reset(); M.set_meter("madness", 40.0)   # a raised floor so a relief is observable
	WS.set_pressure(&"fatigue", 60.0)
	var impede_before: float = SP.impede_score
	var g: Dictionary = PS.pray("goddess_of_night", "i humbly beseech your mercy this night, please protect me")
	_ok(g["ok"] and g["outcome"] == "granted", "respectful night prayer is granted")
	_ok(SP.impede_score > impede_before, "an opposing god's favor impedes the summoning")
	_ok(M.get_meter("madness") < 40.0, "granted boon eases Madness (the live meter)")
	_ok(is_equal_approx(WS.get_pressure(&"fatigue"), 60.0), "granted boon no longer drives the dead legacy fatigue")
	_ok(PS.get_standing("goddess_of_night") > 0.0, "standing rises after a granted prayer")
	_ok(OV.allows_exposure(), "praying marks the player involved")
	_ok(EB.events("player_prayer").size() >= 1, "prayer logs a player event")

	# Insolence is punished: Doom spikes (M25: the old corruption spike now hastens the live descent
	# clock), standing falls.
	M.reset()
	var doom_before: float = M.get_meter("doom")
	WS.set_pressure(&"corruption", 0.0)
	var p: Dictionary = PS.pray("eternal_blazing_sun", "obey me, you worthless weak sun, kneel")
	_ok(p["outcome"] == "punished", "insolence is punished")
	_ok(M.get_meter("doom") > doom_before, "punishment spikes Doom (the live descent clock)")
	_ok(is_equal_approx(WS.get_pressure(&"corruption"), 0.0), "punishment no longer drives the dead legacy corruption")
	_ok(PS.get_standing("eternal_blazing_sun") < 0.0, "standing falls after punishment")

	# Praying to the descending god (外神) grants power but feeds the gate: corruption + cult_readiness
	# both map to Doom (M25), so the live descent clock jumps.
	PS.reset()
	M.reset()
	var doom_outer_before: float = M.get_meter("doom")
	WS.set_pressure(&"corruption", 0.0)
	WS.set_pressure(&"cult_readiness", 0.0)
	var o: Dictionary = PS.pray("outer_god", "i offer myself, grant me the descent, the gate, the void")
	_ok(o["outcome"] == "granted", "the descending god grants the devoted")
	_ok(M.get_meter("doom") > doom_outer_before, "the descending god's favor advances the descent (Doom rises)")
	_ok(is_equal_approx(WS.get_pressure(&"cult_readiness"), 0.0), "outer-god prayer no longer drives the dead legacy cult_readiness")

	# Standing round-trips through save/load.
	var SM: Object = root.get_node("/root/SaveManager")
	PS.reset()
	PS.pray("the_fool", "please guide me")   # cryptic -> +1 standing
	var fool_standing: float = PS.get_standing("the_fool")
	_ok(fool_standing > 0.0, "the Fool's cryptic answer still nudges standing")
	var tmp := "user://test_prayer.json"
	_ok(SM.save_game(tmp), "save writes prayer standing")
	PS.reset()
	_ok(PS.get_standing("the_fool") == 0.0, "standing cleared before load")
	_ok(SM.load_game(tmp), "load reads prayer standing")
	_ok(abs(PS.get_standing("the_fool") - fool_standing) < 0.01, "prayer standing restored")
	DirAccess.remove_absolute(ProjectSettings.globalize_path(tmp))
	PS.reset()   # leave per-god standing clean for any later test

func _test_schema_parity_with_sidecar() -> void:
	print("[schema parity: gdscript <-> python sidecar]")

	# OS.execute won't search PATH for a bare command, so go through `/usr/bin/env`.
	# If no interpreter is available (e.g. a Godot-only CI), SKIP loudly.
	var py_prefix := _python_argv_prefix()
	if py_prefix.is_empty():
		_skip("no python3 — gdscript<->python schema parity not verified")
		return

	# One valid action per verb, then every rejection path the two independently
	# hand-written validators must agree on.
	var fixtures: Array = [
		{"actor": "voss", "verb": "move_to", "args": {"target": "iron_cross_warehouse"}},
		{"actor": "voss", "verb": "talk_to", "args": {"agent": "orin", "topic": "ritual"}},
		{"actor": "voss", "verb": "gather_item", "args": {"item_id": "candle"}},
		{"actor": "voss", "verb": "perform_ritual_step", "args": {"step": "anoint"}},
		{"actor": "voss", "verb": "hide", "args": {}},
		{"actor": "voss", "verb": "flee", "args": {"from": "pell"}},
		{"actor": "voss", "verb": "attack", "args": {"target": "pell"}},
		{"actor": "voss", "verb": "recruit", "args": {"agent": "orin"}},
		{"actor": "voss", "verb": "report", "args": {"to": "nighthawks", "info": "cult"}},
		{"actor": "voss", "verb": "pray", "args": {"god": "the_fool", "prayer": "guide me"}},
		{"actor": "voss", "verb": "pray", "args": {"god": "the_fool"}},   # missing required 'prayer'
		{"actor": "voss", "verb": "adopt_goal", "args": {"goal": "help the investigator"}},
		{"actor": "voss", "verb": "drop_goal", "args": {}},               # missing required 'goal'
		{"actor": "voss", "verb": "idle", "args": {}},
		{"actor": "voss", "verb": "teleport", "args": {}},               # unknown verb
		{"verb": "idle", "args": {}},                                    # missing actor
		{"actor": "", "verb": "idle", "args": {}},                       # empty actor
		{"actor": "voss", "verb": "talk_to", "args": {"agent": "orin"}}, # missing required arg
		{"actor": "voss", "verb": "move_to", "args": "nope"},            # args not an object
		{"actor": "voss", "verb": "move_to"},                            # args omitted
	]

	# Write fixtures to a temp file and pass its PATH (not inline JSON — a quote-laden
	# JSON string does not survive an argv intact), then run
	# `/usr/bin/env python3 <helper> <fixtures-file>`.
	var fixtures_path := "user://_parity_fixtures.json"
	var ff := FileAccess.open(fixtures_path, FileAccess.WRITE)
	ff.store_string(JSON.stringify(fixtures))
	ff.close()
	var fixtures_os := ProjectSettings.globalize_path(fixtures_path)
	var helper := ProjectSettings.globalize_path("res://").path_join("../agent-sidecar/schema_parity_check.py")
	var argv: Array = py_prefix.duplicate()
	argv.append(helper)
	argv.append(fixtures_os)
	var out: Array = []
	var code := OS.execute("/usr/bin/env", argv, out, true)
	DirAccess.remove_absolute(fixtures_os)
	var joined := "\n".join(out).strip_edges()
	_ok(code == 0, "python parity helper exited 0")
	if code != 0:
		printerr("    helper output: %s" % joined)
		return

	var parsed: Variant = JSON.parse_string(joined)
	if typeof(parsed) != TYPE_DICTIONARY:
		_ok(false, "python helper emitted parseable JSON (got: %s)" % joined)
		return
	var py_schema: Dictionary = parsed.get("schema", {})
	var py_verdicts: Array = parsed.get("verdicts", [])

	# 1) Verb-set parity: the engine loaded exactly the verbs the sidecar loaded.
	var gd_verbs: Array = ActionSchema.verbs()
	gd_verbs.sort()
	var py_verbs: Array = py_schema.keys()
	py_verbs.sort()
	_ok(gd_verbs == py_verbs, "verb sets identical: %s" % str(gd_verbs))

	# 2) Required-args parity per verb (engine's loaded map vs the sidecar's).
	var args_parity := true
	for v in gd_verbs:
		var gd_args: Array = ActionSchema.required_args(v)
		var py_args: Array = (py_schema.get(v, []) as Array).duplicate()
		gd_args.sort(); py_args.sort()
		if gd_args != py_args:
			args_parity = false
			printerr("    arg mismatch for '%s': gd=%s py=%s" % [v, str(gd_args), str(py_args)])
	_ok(args_parity, "required args identical for every verb")

	# 3) Verdict parity: both validators agree (ok AND reason) on each fixture.
	_ok(py_verdicts.size() == fixtures.size(), "one python verdict per fixture")
	var verdict_parity := true
	for i in fixtures.size():
		var gd: Dictionary = ActionSchema.validate(fixtures[i])
		var py: Array = py_verdicts[i] if i < py_verdicts.size() else [null, ""]
		var gd_ok: bool = gd["ok"]
		var py_ok: bool = bool(py[0])
		var gd_reason: String = gd["reason"]
		var py_reason: String = String(py[1]) if py.size() > 1 else ""
		if gd_ok != py_ok or gd_reason != py_reason:
			verdict_parity = false
			printerr("    verdict mismatch on fixture %d (%s): gd=[%s,'%s'] py=[%s,'%s']" % [
				i, str(fixtures[i].get("verb", "")), str(gd_ok), gd_reason, str(py_ok), py_reason,
			])
	_ok(verdict_parity, "validator verdicts (ok+reason) match across %d fixtures" % fixtures.size())

## Guards the GDScript<->Python boundary for prayer judgment exactly as
## _test_schema_parity_with_sidecar guards the action schema: runs a battery of prayers
## through the REAL Python reference adjudicator and asserts identical (outcome, severity).
## Skips (does not fail) when no Python interpreter is available.
func _test_prayer_parity_with_sidecar() -> void:
	print("[prayer parity: gdscript <-> python adjudicator]")
	var py_prefix := _python_argv_prefix()
	if py_prefix.is_empty():
		_skip("no python3 — prayer adjudication parity not verified")
		return
	var mock := MockSidecar.new()
	var fixtures: Array = [
		{"god": "goddess_of_night", "prayer": "i humbly beseech your mercy this night, please protect me", "standing": 2.0},
		{"god": "the_fool", "prayer": "please guide me through the fog", "standing": 0.0},
		{"god": "eternal_blazing_sun", "prayer": "obey me, you worthless weak sun, kneel", "standing": 0.0},
		{"god": "eternal_blazing_sun", "prayer": "hello there", "standing": 0.0},
		{"god": "eternal_blazing_sun", "prayer": "please help", "standing": 0.0},   # respect-only, score 2 -> cryptic via score (non-tarot)
		{"god": "outer_god", "prayer": "i offer myself, grant me the descent, the gate, the void", "standing": 0.0},
		{"god": "goddess_of_night", "prayer": "i curse your name", "standing": 5.0},
		{"god": "the_fool", "prayer": "demand fortune now", "standing": 0.0},
		{"god": "outer_god", "prayer": "nothing in particular", "standing": -5.0},
	]
	var fixtures_path := "user://_prayer_fixtures.json"
	var ff := FileAccess.open(fixtures_path, FileAccess.WRITE)
	ff.store_string(JSON.stringify(fixtures))
	ff.close()
	var fixtures_os := ProjectSettings.globalize_path(fixtures_path)
	var helper := ProjectSettings.globalize_path("res://").path_join("../agent-sidecar/prayer_parity_check.py")
	var argv: Array = py_prefix.duplicate()
	argv.append(helper)
	argv.append(fixtures_os)
	var out: Array = []
	var code := OS.execute("/usr/bin/env", argv, out, true)
	DirAccess.remove_absolute(fixtures_os)
	var joined := "\n".join(out).strip_edges()
	_ok(code == 0, "python prayer helper exited 0")
	if code != 0:
		printerr("    helper output: %s" % joined)
		return
	var parsed: Variant = JSON.parse_string(joined)
	if typeof(parsed) != TYPE_DICTIONARY:
		_ok(false, "python helper emitted parseable JSON (got: %s)" % joined)
		return
	var py_verdicts: Array = parsed.get("verdicts", [])
	_ok(py_verdicts.size() == fixtures.size(), "one python verdict per prayer fixture")
	var parity := true
	for i in fixtures.size():
		var gd: Dictionary = mock.adjudicate_prayer(fixtures[i])
		var py: Array = py_verdicts[i] if i < py_verdicts.size() else ["", -1]
		var gd_out: String = gd["outcome"]
		var gd_sev: int = int(gd["severity"])
		var py_out: String = String(py[0]) if py.size() > 0 else ""
		var py_sev: int = int(py[1]) if py.size() > 1 else -1
		if gd_out != py_out or gd_sev != py_sev:
			parity = false
			printerr("    prayer mismatch %d (%s): gd=[%s,%d] py=[%s,%d]" % [
				i, str(fixtures[i].get("god", "")), gd_out, gd_sev, py_out, py_sev])
	_ok(parity, "adjudicator outcomes (outcome+severity) match across %d prayers" % fixtures.size())

## load() (not preload): preload resolves at parse time, before autoloads register, which
## breaks a scene whose script uses bare autoload refs (PrayerService/GodDB) under the -s harness.
func _test_prayer_panel() -> void:
	print("[prayer panel]")
	var SB: Object = root.get_node("/root/SidecarBridge")
	var PS: Object = root.get_node("/root/PrayerService")
	SB.set_client(MockSidecar.new())   # deterministic adjudication
	PS.reset()
	var panel = load("res://ui/PrayerPanel.tscn").instantiate()
	root.add_child(panel)
	await process_frame
	_ok(not panel.visible, "panel hidden by default")
	panel.toggle()
	await process_frame
	_ok(panel.visible, "panel toggles visible")
	_ok(panel.god_button_count() == 4, "one button per god in the pantheon")
	# A respectful, domain-aligned prayer is granted and rendered.
	var g: Dictionary = panel.submit_prayer("goddess_of_night", "i humbly beseech your mercy this night, please protect me")
	_ok(g["outcome"] == "granted", "panel routes a granted prayer")
	_ok(panel.last_outcome() == "granted", "panel records the rendered outcome")
	# An insulting prayer is punished.
	panel.submit_prayer("eternal_blazing_sun", "obey me, you worthless weak sun, kneel")
	_ok(panel.last_outcome() == "punished", "panel renders a punishment")
	# Offering a prayer updates the selection seam.
	panel.submit_prayer("the_fool", "what will fate bring?")
	_ok(panel.selected_god() == "the_fool", "submit_prayer updates selection")
	panel.toggle()  # hide
	await process_frame
	_ok(not panel.visible, "panel toggles back hidden")
	panel.queue_free()
	await process_frame

## The debug overlay mirrors the WHOLE EventBus (no allow-list), newest first, and refreshes
## live while open. Distinct from the cult panel, which filters to publicly-known events.
func _test_debug_log_panel() -> void:
	print("[debug log panel]")
	var EB: Object = root.get_node("/root/EventBus")
	EB.clear()
	var panel = load("res://ui/DebugLogPanel.tscn").instantiate()
	root.add_child(panel)
	await process_frame
	_ok(not panel.visible, "debug panel hidden by default")
	panel.toggle()
	await process_frame
	_ok(panel.visible, "debug panel toggles visible")
	_ok(panel.line_count() == 1, "empty log shows a single placeholder line")
	# The per-beat agent_action firehose is HIDDEN from the panel (it stays in the after-game .md).
	EB.emit_event("agent_action", {"actor": "clerk_voss", "verb": "move_to", "args": {"target": "iron_cross_warehouse"}})
	await process_frame
	_ok(panel.line_count() == 1, "a raw per-beat agent_action is HIDDEN from the panel (still logged to the .md)")
	# Meaningful consequence events DO render — a scene transition + a rejection (newest first).
	EB.emit_event("agent_moved_room", {"actor": "fishwife_dalia", "from": "city", "to": "cathedral_crypt"})
	EB.emit_event("action_rejected", {"actor": "lamplighter_orin", "verb": "teleport", "reason": "unknown verb"})
	await process_frame
	_ok(panel.line_count() == 2, "meaningful events render (scene transition + rejection); the agent_action does not")
	_ok(panel.newest_line().contains("action rejected"), "newest event is shown first")
	_ok(panel.newest_line().contains("reason: unknown verb"), "rejection reason is surfaced")
	panel.toggle()  # hide
	await process_frame
	_ok(not panel.visible, "debug panel toggles back hidden")
	panel.queue_free()
	await process_frame

## The deterministic GM digest: a PURE function of the event batch — notable beats become readable
## lines, the agent-deliberation firehose collapses to ONE aggregated count, vetoes to one count line.
func _test_gm_digest() -> void:
	print("[gm digest]")
	# Notable beats -> one readable line each, in event order.
	var d: Dictionary = GMDigest.build_digest([
		{"seq": 1, "type": "agent_moved_room", "data": {"actor": "fishwife_dalia", "from": "city", "to": "cathedral_crypt"}, "day": 1, "minute": 480, "beat": 3},
		{"seq": 2, "type": "npc_said", "data": {"agent": "clerk_voss", "text": "The hour is close."}, "day": 1, "minute": 485, "beat": 3},
		{"seq": 3, "type": "world_var_changed", "data": {"var": "gate_sealed", "from": false, "to": true}, "day": 1, "minute": 490, "beat": 4},
	])
	var lines: Array = d["lines"]
	_ok(lines.size() == 3, "three notable events -> three digest lines")
	_ok(String(lines[0]).contains("Dalia") and String(lines[0]).contains("cathedral crypt"),
		"room transition names the mover and the destination")
	_ok(String(lines[1]).contains("Voss") and String(lines[1]).contains("The hour is close."),
		"dialogue line quotes the speech")
	_ok(String(lines[2]).contains("gate sealed") and String(lines[2]).contains("true"),
		"world-var change shows the variable and the new value")
	var stats: Dictionary = d["stats"]
	_ok(int(stats["events"]) == 3 and int(stats["moves"]) == 1 and int(stats["said"]) == 1
		and int(stats["world_vars"]) == 1, "stats count each notable category")
	# The agent-deliberation noise aggregates to ONE count line — never per-line spam.
	var noisy: Array = []
	for i in 5:
		noisy.append({"seq": i + 1, "type": "agent_action", "data": {"actor": "a%d" % i, "verb": "move_to"}})
	noisy.append({"seq": 6, "type": "overseer_directive", "data": {"actor": "overseer"}})
	var dn: Dictionary = GMDigest.build_digest(noisy)
	_ok((dn["lines"] as Array).size() == 1, "noise-only batch collapses to a single line")
	_ok(String((dn["lines"] as Array)[0]).contains("6 agent actions"), "the noise line carries the count")
	_ok(int((dn["stats"] as Dictionary)["agent_actions"]) == 6, "stats carry the aggregated action count")
	# Vetoes/rejections aggregate to one count line too.
	var dv: Dictionary = GMDigest.build_digest([
		{"seq": 1, "type": "action_vetoed", "data": {"actor": "clerk_voss", "reason": "downed"}},
		{"seq": 2, "type": "action_rejected", "data": {"actor": "clerk_voss", "reason": "unknown verb"}},
	])
	_ok((dv["lines"] as Array).size() == 1 and String((dv["lines"] as Array)[0]).contains("2"),
		"vetoes + rejections collapse to one count line")
	_ok(int((dv["stats"] as Dictionary)["vetoes"]) == 2, "stats carry the veto count")
	# Combat + items narrate like the debug overlay's story lines.
	var dc: Dictionary = GMDigest.build_digest([
		{"seq": 1, "type": "item_gathered", "data": {"actor": "fishwife_dalia", "item_id": "ritual_salt"}},
		{"seq": 2, "type": "material_deposited", "data": {"actor": "fishwife_dalia", "item_id": "ritual_salt"}},
		{"seq": 3, "type": "agent_attacked", "data": {"target": "clerk_voss", "target_hp": 2}},
		{"seq": 4, "type": "agent_downed", "data": {"target": "clerk_voss"}},
	])
	_ok((dc["lines"] as Array).size() == 4, "items + attack + down each get a line")
	_ok(String((dc["lines"] as Array)[0]).contains("ritual salt"), "item ids render as readable words")
	# Empty events -> empty digest (the tick appends no entry).
	var de: Dictionary = GMDigest.build_digest([])
	_ok((de["lines"] as Array).is_empty(), "empty batch -> no lines")
	_ok(int((de["stats"] as Dictionary)["events"]) == 0, "empty batch -> zero event count")

func _test_gm_digest_combat() -> void:
	print("[gm digest combat lines (combat M4)]")
	var d: Dictionary = GMDigest.build_digest([
		{"seq": 1, "type": "combat_started", "data": {"agent": "bram_kell"}},
		{"seq": 2, "type": "ability_cast_started", "data": {"caster": "bram_kell", "ability": "cleaver_swipe"}},
		{"seq": 3, "type": "ability_cast_finished", "data": {"caster": "bram_kell", "ability": "cleaver_swipe"}},
		{"seq": 4, "type": "ability_cast_started", "data": {"caster": "player", "ability": "revolver_shot"}},
		{"seq": 5, "type": "transformed", "data": {"agent": "bram_kell", "form": "bieber_monster"}},
		{"seq": 6, "type": "agent_downed", "data": {"actor": "bram_kell", "target": "player"}},
		{"seq": 7, "type": "combat_ended", "data": {"agent": "bram_kell"}},
	])
	var lines: Array = d["lines"]
	var joined := "\n".join(lines)
	_ok(joined.contains("Kell entered a fight."), "combat_started narrates who the fight broke out around")
	_ok(joined.contains("Kell became something else."), "the transform narrates WITHOUT naming the form")
	_ok(not joined.contains("bieber"), "…the data's form id never leaks into the digest")
	_ok(joined.contains("Player was downed."), "agent_downed keeps its existing phrasing")
	_ok(joined.contains("Kell left the fight."), "combat_ended narrates the fight closing")
	_ok(joined.contains("2 combat arts loosed."),
		"casts aggregate to ONE count line (finished/interrupted uncounted: one cast, one count)")
	var stats: Dictionary = d["stats"]
	_ok(int(stats.get("combat", -1)) == 3, "stats count the combat story beats")
	_ok(int(stats.get("casts", -1)) == 2, "stats carry the aggregated cast count")
	_ok(String(lines[lines.size() - 1]).contains("combat arts"),
		"story lines lead; the cast aggregate trails")

## The GM panel autoload: toggling, the 30s digest tick consuming only NEW events (seq cursor),
## and the hybrid narration seam (deterministic digest always; LLM paragraph appended only when
## the client's narrate() returns one — offline clients leave the digest bare, with no error).
func _test_gm_panel() -> void:
	print("[gm panel]")
	var EB: Object = root.get_node("/root/EventBus")
	var SB: Object = root.get_node("/root/SidecarBridge")
	var panel: Object = root.get_node("/root/GMPanel")
	var prev_client: Object = SB.client
	EB.clear()
	panel.reset()
	# The wall-clock cadence is wired: a 30s autostarted timer drives the tick.
	_ok(is_equal_approx(panel._timer.wait_time, 30.0), "digest timer fires every 30 wall-clock seconds")
	_ok(not panel._timer.is_stopped(), "digest timer is running without the panel ever being opened")
	# Toggling: hidden by default, opens and closes via the toggle_gm action (full input path).
	_ok(not panel.is_open(), "gm panel hidden by default")
	_send_action("toggle_gm")
	await process_frame
	_ok(panel.is_open(), "toggle_gm (G) opens the gm panel")
	_send_action("toggle_gm")
	await process_frame
	_ok(not panel.is_open(), "toggle_gm (G) again closes it")
	# Digest tick with an offline client: the deterministic entry renders, no narration, no error.
	var mock := MockSidecar.new()
	SB.set_client(mock)
	EB.emit_event("agent_moved_room", {"actor": "fishwife_dalia", "from": "city", "to": "cathedral_crypt"})
	EB.emit_event("agent_action", {"actor": "clerk_voss", "verb": "move_to", "args": {"target": "x"}})
	panel._digest_tick()
	panel.flush_narration()
	_ok(panel.entry_count() == 1, "a tick with fresh events appends one digest entry (panel closed)")
	var e0: Dictionary = panel.entry(0)
	_ok((e0["lines"] as Array).size() == 2, "entry carries the story line + the aggregated noise line")
	_ok(String((e0["lines"] as Array)[0]).contains("cathedral crypt"), "the story line survives into the entry")
	_ok(String(e0["narration"]) == "", "offline client (no set_narrate) leaves no narration and no error")
	# Second tick sees ONLY events after the seq cursor.
	EB.emit_event("npc_said", {"agent": "clerk_voss", "text": "It begins."})
	panel._digest_tick()
	panel.flush_narration()
	_ok(panel.entry_count() == 2, "a second tick appends a second entry")
	var e1: Dictionary = panel.entry(1)
	_ok((e1["lines"] as Array).size() == 1, "the second tick digests only the NEW event")
	_ok(String((e1["lines"] as Array)[0]).contains("It begins."), "and that event is the newly logged one")
	# A tick with nothing new appends nothing.
	panel._digest_tick()
	_ok(panel.entry_count() == 2, "a tick with no new events appends no entry")
	# The hybrid seam: a scripted narration lands appended to the entry it narrates. B4 (M21) gates the
	# LLM narration call behind panel-open OR the explicit opt-in Setting; opt in here (the panel is
	# closed) so the hybrid-narration contract is exercised without opening the panel.
	root.get_node("/root/Settings").set_value("gm_narration", true)
	mock.set_narrate("The city holds its breath as the faithful gather below.")
	EB.emit_event("agent_moved_room", {"actor": "clerk_voss", "from": "city", "to": "cathedral_nave"})
	panel._digest_tick()
	panel.flush_narration()
	var e2: Dictionary = panel.entry(2)
	_ok(String(e2["narration"]) == "The city holds its breath as the faithful gather below.",
		"scripted narration is appended to its digest entry")
	_ok((mock.last_narrate_request.get("events", []) as Array).size() > 0,
		"the narrate request carries the digest lines")
	var world: Dictionary = mock.last_narrate_request.get("world", {})
	_ok(world.has("beat") and world.has("phase") and world.has("pressures"),
		"the narrate request carries the world state (beat/phase/pressures)")
	# Entries accumulated while closed all render once opened (header + lines + narration).
	panel.toggle()
	await process_frame
	_ok(panel.is_open(), "panel.toggle() opens for rendering")
	_ok(panel.rendered_line_count() >= 3 + 4 + 1, "opened panel renders every accumulated entry")
	panel.toggle()
	await process_frame
	# The log is capped: old digests fall off past MAX_DIGESTS.
	for i in panel.MAX_DIGESTS + 2:
		EB.emit_event("npc_said", {"agent": "clerk_voss", "text": "line %d" % i})
		panel._digest_tick()
	panel.flush_narration()
	_ok(panel.entry_count() == panel.MAX_DIGESTS, "digest history is capped at MAX_DIGESTS")
	# Cleanup.
	root.get_node("/root/Settings").set_value("gm_narration", false)   # restore the B4 opt-in default
	panel.reset()
	SB.set_client(prev_client)
	EB.clear()
	await process_frame

func _test_inventory_panel() -> void:
	print("[inventory panel]")
	var INV: Object = root.get_node("/root/Inventory")
	INV.clear()
	var panel = load("res://ui/InventoryPanel.tscn").instantiate()
	root.add_child(panel)
	await process_frame
	_ok(not panel.visible, "inventory hidden by default")
	panel.toggle()
	await process_frame
	_ok(panel.visible, "inventory toggles visible")
	_ok(panel.line_count() == 1, "empty inventory shows a single placeholder line")
	# Items appear live while the panel is open: one row per held item type.
	INV.add("candle", 2)
	INV.add("spirit_pendulum", 1)
	await process_frame
	_ok(panel.line_count() == 2, "panel renders one row per held item type")
	panel.toggle()
	await process_frame
	_ok(not panel.visible, "inventory toggles back hidden")
	panel.queue_free()
	INV.clear()
	await process_frame

func _test_hud_toggle_keys() -> void:
	print("[hud toggle keys]")
	var hud = load("res://ui/HUD.tscn").instantiate()
	root.add_child(hud)
	await process_frame
	var map: Node = hud.get_node("DistrictMap")
	var inv: Node = hud.get_node("InventoryPanel")
	_ok(not map.visible and not inv.visible, "map + inventory hidden initially")
	# Push the toggle_map action through the root viewport, exactly as a real M press arrives,
	# so this exercises the full _unhandled_input path (not just a direct handler call).
	_send_action("toggle_map")
	await process_frame
	_ok(map.visible, "toggle_map (M) opens the District map")
	_send_action("toggle_map")
	await process_frame
	_ok(not map.visible, "toggle_map (M) again closes it")
	_send_action("toggle_inventory")
	await process_frame
	_ok(inv.visible, "toggle_inventory (I) opens the inventory")
	hud.queue_free()
	await process_frame

## Push a press+release of an InputMap action through the root viewport, so the HUD panel
## toggles fire from _unhandled_input exactly as they do for a real key press.
func _send_action(action: StringName) -> void:
	for pressed in [true, false]:
		var ev := InputEventAction.new()
		ev.action = action
		ev.pressed = pressed
		root.push_input(ev)

func _test_toasts() -> void:
	print("[toasts]")
	var EM: Object = root.get_node("/root/EventManager")
	var WM: Object = root.get_node("/root/WorldManager")
	var toasts = load("res://ui/Toasts.tscn").instantiate()
	root.add_child(toasts)
	await process_frame
	_ok(toasts.card_count() == 0, "toast stack starts empty")
	# Wiring: the toast layer subscribes to the three simulation signals it surfaces.
	_ok(EM.is_connected("event_fired", Callable(toasts, "_on_event")),
		"toasts listen to EventManager.event_fired")
	_ok(WM.is_connected("pressure_threshold_crossed", Callable(toasts, "_on_threshold")),
		"toasts listen to WorldManager.pressure_threshold_crossed")
	_ok(WM.is_connected("stage_advanced", Callable(toasts, "_on_stage")),
		"toasts listen to WorldManager.stage_advanced")
	# Behavior: each handler turns its signal into exactly one card. Called directly (rather
	# than emitting the global signals) so no other live listener is disturbed by the test.
	toasts._on_event({"title": "A scream in the fog", "body": "Night Market.",
		"effects": [{"type": "notify", "channel": "alert"}]})
	toasts._on_threshold("panic", 60.0)
	toasts._on_stage("disturbance", "awakening")
	await process_frame
	_ok(toasts.card_count() == 3, "event + threshold + stage each push one toast card")
	# The stack never shows more than MAX_VISIBLE (4) cards at once.
	for i in 5:
		toasts.push("spam %d" % i)
	await process_frame
	_ok(toasts.card_count() <= 4, "the stack is capped at MAX_VISIBLE (4)")
	toasts.queue_free()
	await process_frame

func _test_player_position_sync() -> void:
	print("[player position sync]")
	var ART: Object = root.get_node("/root/AgentRuntime")
	var saved: Vector2 = ART.player_position
	_ok(get_nodes_in_group("player").is_empty(), "no stray player nodes leaked from earlier tests")
	var gc = load("res://src/GameController.gd").new()
	root.add_child(gc)
	await process_frame
	# With no player in the tree, sync leaves the last known position untouched.
	ART.player_position = Vector2(1, 1)
	gc.sync_player_position()
	_ok(ART.player_position == Vector2(1, 1), "sync with no player keeps the last position")
	# A player in the group: sync pushes its live position into AgentRuntime.
	var player := Node2D.new()
	player.add_to_group("player")
	player.global_position = Vector2(123, 456)
	root.add_child(player)
	gc.sync_player_position()
	_ok(ART.player_position == Vector2(123, 456), "sync pushes the live player position into AgentRuntime")
	player.queue_free()
	gc.queue_free()
	await process_frame
	ART.player_position = saved

func _test_player_stamina() -> void:
	print("[player stamina]")
	var p = load("res://scenes/Player.tscn").instantiate()
	root.add_child(p)
	await process_frame
	_ok(is_equal_approx(p.stamina, p.max_stamina), "starts at full stamina")
	# Sprinting drains; not-sprinting regenerates; both clamp to [0, max].
	p.step_stamina(1.0, true)
	_ok(is_equal_approx(p.stamina, p.max_stamina - p.stamina_drain),
		"sprinting drains one second of stamina")
	p.stamina = 5.0
	p.step_stamina(1.0, true)
	_ok(p.stamina == 0.0, "stamina clamps at 0 (never negative)")
	p.stamina = 0.0
	p.step_stamina(1.0, false)
	_ok(is_equal_approx(p.stamina, p.stamina_regen), "regenerates one second while not sprinting")
	p.stamina = p.max_stamina - 1.0
	p.step_stamina(1.0, false)
	_ok(p.stamina == p.max_stamina, "stamina clamps at max")
	# Exhaustion latch: empty disarms an active sprint and blocks re-engage until recovered.
	p.stamina = 0.0
	p._sprinting = true
	_ok(p._resolve_sprint(Vector2.RIGHT) == false, "empty stamina disarms an active sprint")
	_ok(p._exhausted, "draining to empty sets the exhausted latch")
	p.stamina = p.sprint_recharge_threshold
	p._resolve_sprint(Vector2.RIGHT)
	_ok(not p._exhausted, "exhaustion clears once stamina recovers to the threshold")
	# Floating stamina bar: fades in while recovering, fades out once the pool is full.
	p.stamina = 50.0
	p._bar_alpha = 0.0
	p._update_stamina_bar(1.0, false)
	_ok(p._bar_alpha > 0.0, "stamina bar fades in while recovering")
	p.stamina = p.max_stamina
	p._update_stamina_bar(10.0, false)
	_ok(p._bar_alpha == 0.0, "stamina bar fades out once stamina is full")
	p.queue_free()
	await process_frame

func _test_player_8way_facing() -> void:
	print("[player 8-way facing]")
	var p = load("res://scenes/Player.tscn").instantiate()
	root.add_child(p)
	await process_frame
	# (movement vector) -> (direction key, mirror?). +y is DOWN in screen space.
	var cases := [
		[Vector2(0, 1), "s", false],     # down  / south
		[Vector2(1, 0), "e", false],     # right / east
		[Vector2(0, -1), "n", false],    # up    / north
		[Vector2(-1, 0), "e", true],     # left  / west  (east mirrored)
		[Vector2(1, 1), "se", false],    # down-right
		[Vector2(-1, 1), "se", true],    # down-left (se mirrored)
		[Vector2(1, -1), "ne", false],   # up-right
		[Vector2(-1, -1), "ne", true],   # up-left   (ne mirrored)
	]
	for c in cases:
		p._face(c[0])
		_ok(p._dir == c[1] and p._flip == c[2],
			"%s -> dir=%s flip=%s" % [str(c[0]), str(c[1]), str(c[2])])
	# Zero input keeps the last facing.
	p._face(Vector2(1, -1))
	p._face(Vector2.ZERO)
	_ok(p._dir == "ne", "zero movement keeps the last facing")
	# Every drawn idle animation the facing logic can ask for exists in the SpriteFrames.
	var frames: SpriteFrames = p.get_node("Sprite").sprite_frames
	var all_present := true
	for d in ["s", "n", "e", "se", "ne"]:
		if not frames.has_animation("idle_%s" % d):
			all_present = false
	_ok(all_present, "SpriteFrames has all 5 drawn idle_* animations")
	p.queue_free()
	await process_frame

func _test_map_texture_imported() -> void:
	print("[map texture]")
	var tex: Variant = load("res://assets/maps/map_v3.png")
	_ok(tex is Texture2D, "map_v3.png is imported and loads as a Texture2D")
	if tex is Texture2D:
		_ok((tex as Texture2D).get_size().is_equal_approx(MapProjection.MAP_SIZE),
			"texture size matches MAP_SIZE (1254x1254)")

func _test_district_map_polygons() -> void:
	print("[district map_polygons]")
	var raw: String = FileAccess.get_file_as_string("res://data/districts.json")
	var parsed: Variant = JSON.parse_string(raw)
	_ok(typeof(parsed) == TYPE_ARRAY, "districts.json parses to an array")
	var districts: Array = parsed if typeof(parsed) == TYPE_ARRAY else []
	_ok(districts.size() == 5, "five districts present")
	var ids: Array = []
	var all_valid := true
	var all_in_bounds := true
	var risk_model_intact := true
	for d in districts:
		var dd: Dictionary = d
		ids.append(String(dd.get("id", "")))
		var mp: Array = dd.get("map_polygon", [])
		if mp.size() < 6 or mp.size() % 2 != 0:
			all_valid = false
		for i in range(0, mp.size() - 1, 2):
			var x: float = float(mp[i])
			var y: float = float(mp[i + 1])
			if x < 0.0 or x > MapProjection.MAP_SIZE.x or y < 0.0 or y > MapProjection.MAP_SIZE.y:
				all_in_bounds = false
		if not (dd.has("base_risk") and dd.has("risk_pressure")):
			risk_model_intact = false
	_ok(all_valid, "every district has an even-length map_polygon of >= 6 numbers (>= 3 vertices)")
	_ok(all_in_bounds, "every map_polygon vertex sits within [0,1254] x [0,1254]")
	for expected in ["iron_cross", "harbor", "st_selena", "night_market", "uptown"]:
		_ok(ids.has(expected), "district '%s' is present" % expected)
	_ok(risk_model_intact, "base_risk / risk_pressure still present on every district (risk model unbroken)")

func _test_map_projection_canvas_fit() -> void:
	print("[map projection canvas fit]")
	# A canvas twice as wide as the map (same height): letterboxed left/right at uniform scale 1.
	# Derived from MAP_SIZE so it stays correct across map swaps (now the square map_v3, 1254x1254).
	var ms: Vector2 = MapProjection.MAP_SIZE
	var canvas := Vector2(ms.x * 2.0, ms.y)
	var scale: float = minf(canvas.x / ms.x, canvas.y / ms.y)
	_ok(is_equal_approx(scale, 1.0), "uniform scale is the limiting (height) ratio")
	# Image origin maps to the centering offset, not the canvas origin.
	var origin: Vector2 = MapProjection.image_to_canvas(canvas, Vector2.ZERO)
	_ok(origin.is_equal_approx(Vector2(ms.x * 0.5, 0.0)), "image origin maps to the letterbox offset")
	# The far map corner stays within the canvas and sits at the far letterbox edge.
	var corner: Vector2 = MapProjection.image_to_canvas(canvas, ms)
	_ok(corner.x <= canvas.x + 0.01 and corner.y <= canvas.y + 0.01, "MAP_SIZE corner stays within the canvas")
	_ok(corner.is_equal_approx(Vector2(ms.x * 1.5, ms.y)), "MAP_SIZE corner sits at the far letterbox edge")
	# Aspect-preserving: a step in image x and an equal step in image y scale identically.
	var dx: Vector2 = MapProjection.image_to_canvas(canvas, Vector2(10.0, 0.0)) - origin
	var dy: Vector2 = MapProjection.image_to_canvas(canvas, Vector2(0.0, 10.0)) - origin
	_ok(is_equal_approx(dx.x, dy.y), "x and y scale identically (no distortion)")
	# Round-trip: canvas_to_image is the exact inverse of image_to_canvas.
	var p := Vector2(640.0, 410.0)
	var back: Vector2 = MapProjection.canvas_to_image(canvas, MapProjection.image_to_canvas(canvas, p))
	_ok(back.is_equal_approx(p), "canvas_to_image(image_to_canvas(p)) == p")
	# Degenerate zero-size canvas (e.g. before first layout): the inverse must stay finite
	# (no inf/nan) so callers can't silently propagate garbage. scale<=0 -> pass the point through.
	_ok(MapProjection.canvas_to_image(Vector2.ZERO, Vector2(100.0, 100.0)).is_finite(),
		"canvas_to_image on a zero-size canvas returns a finite point")

func _test_map_projection_world_to_map() -> void:
	print("[map projection global transform]")
	# Constants match the canonical map-image space (map_v3.png is 1254x1254).
	_ok(MapProjection.MAP_SIZE == Vector2(1254.0, 1254.0), "MAP_SIZE is the map_v3.png pixel size")
	# UNIFIED (coordinate-unification pass): City.tscn's ground is ground_test.png (2508px, a 2x
	# render of the 1254 map) at scale 2.5 -> a 6270x6270 world, i.e. exactly 5.0 world units per
	# map pixel. One uniform transform now covers the live scene, the rite anchor, and the tracker.
	_ok(MapProjection.CITY_SCALE == 5.0, "CITY_SCALE is 5.0 (live City.tscn world / map_v3 px)")
	_ok(MapProjection.map_to_world(Vector2.ZERO).is_equal_approx(Vector2.ZERO),
		"map origin -> world origin")
	_ok(MapProjection.map_to_world(MapProjection.MAP_SIZE).is_equal_approx(Vector2(6270.0, 6270.0)),
		"map far corner -> world far corner (6270,6270) — the live ground size")
	# Round-trip identity: world_to_map is the exact inverse of map_to_world.
	var p := Vector2(1234.0, 567.0)
	_ok(MapProjection.map_to_world(MapProjection.world_to_map(p)).is_equal_approx(p),
		"map_to_world(world_to_map(p)) == p")
	# A sample map point scales by CITY_SCALE.
	_ok(MapProjection.map_to_world(Vector2(430.0, 300.0)).is_equal_approx(Vector2(2150.0, 1500.0)),
		"map (430,300) -> world (2150,1500)")
	# Landmarks across the WHOLE live city now project back inside the map image — the southern
	# city (e.g. the Chapel at world (2118,5015)) used to fall 179px off the 1254px map under 3.5.
	var map_rect := Rect2(Vector2.ZERO, MapProjection.MAP_SIZE)
	_ok(map_rect.has_point(MapProjection.world_to_map(Vector2(2118.0, 5015.0))),
		"the Chapel projects inside the map image (southern city no longer off-map)")
	_ok(map_rect.has_point(MapProjection.world_to_map(Vector2(5397.0, 1875.0))),
		"the Warehouse projects inside the map image")
	# The rite anchor now lives in the LIVE scene's space: its world position is the sabotage
	# cache at the real Warehouse building (City.tscn Warehouse/RiteCache), not the old-map point.
	var rite_world: Vector2 = MapProjection.map_to_world(MapProjection.WAREHOUSE_MAP)
	_ok(rite_world.distance_to(Vector2(5366.65, 2378.09)) < 1.0,
		"WAREHOUSE_MAP -> world ~(5366.65,2378.09) (the live Warehouse cache)")

## The map panel loads the real map texture and the five districts, and toggles like the other
## modals. Asserts only layout-independent invariants so it is robust under headless control sizing;
## the geometry it draws is covered by the MapProjection unit tests, not re-tested through the view.
func _test_district_map_panel() -> void:
	print("[district map panel]")
	var panel = load("res://ui/DistrictMap.tscn").instantiate()
	root.add_child(panel)
	await process_frame
	_ok(not panel.visible, "map panel hidden by default")
	_ok(panel.districts.size() == 5, "panel loaded the five districts")
	_ok(panel.has_map_texture(), "panel loaded the city map texture")
	panel.toggle()
	await process_frame
	_ok(panel.visible, "map panel toggles visible")
	panel.toggle()
	await process_frame
	_ok(not panel.visible, "map panel toggles back hidden")
	panel.queue_free()
	await process_frame

## Returns the argv prefix to run Python via `/usr/bin/env` (so PATH is searched), or []
## if no interpreter is available. Tries python3 then python.
func _python_argv_prefix() -> Array:
	if not FileAccess.file_exists("/usr/bin/env"):
		return []
	for candidate in ["python3", "python"]:
		var probe: Array = []
		if OS.execute("/usr/bin/env", [candidate, "--version"], probe, true) == 0:
			return [candidate]
	return []

## ---- Combat M5: player combat + HUD ----

## Instance the real Player scene (whose Combat child binds the SAME executor machinery to
## the player proxy) and move the proxy into an isolated test room, away from the live
## roster (rooms are separate coordinate spaces — nothing in "city" can be hit from here).
## No awaits: _ready runs synchronously inside add_child, and staying await-free keeps the
## manual step_combat calls the ONLY stepper of the player executor during a test.
func _stage_m5_player(room_id: String, pos: Vector2 = Vector2.ZERO) -> Node:
	var p = load("res://scenes/Player.tscn").instantiate()
	root.add_child(p)
	p.global_position = pos
	var pc: Node = p.get_node("Combat")
	pc.proxy.room = room_id
	pc.proxy.position = pos
	return p

## Fixed-dt deterministic stepping (60Hz) of the player executor + any staged NPC executors.
func _step_m5(pc: Node, seconds: float, extra: Array = []) -> void:
	var steps := int(round(seconds * 60.0))
	for i in steps:
		pc.executor.step_combat(1.0 / 60.0)
		for ex in extra:
			ex.step_combat(1.0 / 60.0)

## Free the player scene + staged executors immediately (PREDELETE unregisters the player
## executor from the routing table) and restore the real roster.
func _end_m5(player: Node, executors: Array = []) -> void:
	for ex in executors:
		ex.free()
	if player != null:
		player.free()
	root.get_node("/root/Agents").rebuild()
	root.get_node("/root/EventBus").clear()

func _test_combat_input_actions() -> void:
	print("[combat input actions (combat M5)]")
	for action in ["attack", "dash", "use_charm"]:
		_ok(InputMap.has_action(action), "action '%s' is registered" % action)
	var has_lmb := false
	var has_space := false
	for ev in InputMap.action_get_events("attack"):
		if ev is InputEventMouseButton and (ev as InputEventMouseButton).button_index == MOUSE_BUTTON_LEFT:
			has_lmb = true
		elif ev is InputEventKey and (ev as InputEventKey).physical_keycode == KEY_SPACE:
			has_space = true
	_ok(has_lmb, "attack binds mouse LMB")
	_ok(has_space, "attack binds physical Space")
	var dash_shift := false
	for ev in InputMap.action_get_events("dash"):
		if ev is InputEventKey and (ev as InputEventKey).physical_keycode == KEY_SHIFT:
			dash_shift = true
	_ok(dash_shift, "dash binds Shift")
	var charm_q := false
	for ev in InputMap.action_get_events("use_charm"):
		if ev is InputEventKey and (ev as InputEventKey).physical_keycode == KEY_Q:
			charm_q = true
	_ok(charm_q, "use_charm binds Q")

func _test_player_combat_casts() -> void:
	print("[player combat casts through the SAME executor (combat M5)]")
	var EB: Object = root.get_node("/root/EventBus")
	EB.clear()
	var p := _stage_m5_player("m5_arena")
	var pc: Node = p.get_node("Combat")
	_ok(pc.executor != null and pc.executor.agent == pc.proxy,
		"PlayerCombat binds a CombatExecutor to the player proxy agent")
	_ok(pc.proxy.id == "player", "…the registry's 'player' agent")
	_ok(pc.executor.cost_provider == pc, "the executor's cost seam is the PlayerCombat provider")
	_ok(pc.executor.tactics == null, "no tactical brain pilots the player (the player does)")
	var res: Dictionary = pc.on_attack_pressed(Vector2.RIGHT)
	_ok(bool(res.get("ok", false)), "attack casts revolver_shot")
	_ok(pc.proxy.item_count("revolver_round") == 11,
		"the shot consumes a carried round at accept (12 -> 11 in the proxy inventory)")
	var casts: Array = EB.events("ability_cast_started")
	_ok(casts.size() == 1
		and String((casts[0].get("data", {}) as Dictionary).get("caster", "")) == "player"
		and String((casts[0].get("data", {}) as Dictionary).get("ability", "")) == "revolver_shot",
		"the telegraph rides the SAME cast_started shape, caster 'player'")
	_ok(not bool(pc.on_attack_pressed(Vector2.RIGHT).get("ok", false)),
		"a second press mid-windup refuses (busy — same FSM as NPCs)")
	_step_m5(pc, 0.3)
	_ok(pc.executor.projectiles.size() == 1, "the windup resolved into a live projectile")
	_end_m5(p)

func _test_player_combat_ammo() -> void:
	print("[player ammo = carried rounds; no_ammo/no_weapon refusals (combat M5)]")
	var p := _stage_m5_player("m5_arena")
	var pc: Node = p.get_node("Combat")
	pc.proxy.inventory["revolver_round"] = 2
	_ok(bool(pc.on_attack_pressed(Vector2.RIGHT).get("ok", false)), "shot 1 casts")
	_step_m5(pc, 1.0)
	_ok(pc.proxy.item_count("revolver_round") == 1, "rounds 2 -> 1")
	_ok(bool(pc.on_attack_pressed(Vector2.RIGHT).get("ok", false)), "shot 2 casts (cooldown elapsed)")
	_step_m5(pc, 1.0)
	_ok(pc.proxy.item_count("revolver_round") == 0, "rounds 1 -> 0")
	var res: Dictionary = pc.on_attack_pressed(Vector2.RIGHT)
	_ok(not bool(res.get("ok", false)) and String(res.get("reason", "")) == "no_ammo",
		"the dry revolver refuses with 'no_ammo' (reload is a later pickup, not tonight)")
	_ok(pc.proxy.item_count("revolver_round") == 0,
		"the refusal never half-pays (rounds still 0, never negative)")
	_ok(CombatResolver.ledger_ready(pc.executor.ledger, "revolver_shot", pc.executor.now_ms()),
		"a cost refusal never burns the cooldown")
	# Cross-resource no-half-pay: the ammo IS affordable but the stamina leg refuses — try_pay
	# checks EVERY cost before deducting ANY, so the rounds must be untouched.
	pc.proxy.inventory["revolver_round"] = 3
	res = pc.try_pay({"id": "revolver_shot", "cost": {"ammo": 1, "stamina": 9999.0}})
	_ok(not bool(res.get("ok", false)) and String(res.get("reason", "")) == "no_stamina",
		"an unpayable stamina leg on an ammo-costing art refuses with 'no_stamina'")
	_ok(pc.proxy.item_count("revolver_round") == 3,
		"…and the refusal never half-pays the ammo leg (rounds untouched)")
	# No granting weapon carried at all: the ammo cost can't even resolve — a DISTINCT refusal
	# (the rounds in the pocket are useless without the revolver that fires them).
	pc.proxy.inventory["revolver_round"] = 5
	pc.proxy.remove_item("revolver", 1)
	res = pc.on_attack_pressed(Vector2.RIGHT)
	_ok(not bool(res.get("ok", false)) and String(res.get("reason", "")) == "no_weapon",
		"no carried granting weapon refuses with 'no_weapon'")
	_ok(pc.proxy.item_count("revolver_round") == 5, "…and spends nothing")
	# HUD read-out: a carried granting weapon that authors NO ammo_item ("") must resolve to
	# -1 (CombatHUD's "—"), never item_count("") == 0 masquerading as an empty magazine.
	var IDB: Object = root.get_node("/root/ItemDB")
	(IDB.get("_defs") as Dictionary)["t_free_gun"] = ItemDef.from_json({
		"id": "t_free_gun", "category": "weapon", "grants": ["revolver_shot"]})
	pc.proxy.add_item("t_free_gun", 1)
	_ok(pc.ammo_count() == -1,
		"ammo_count is -1 when the carried weapon authors no ammo_item (HUD shows '—', not 0)")
	(IDB.get("_defs") as Dictionary).erase("t_free_gun")
	_end_m5(p)

func _test_player_loadout() -> void:
	print("[player starting loadout: scenario.json items, granted once at proxy creation]")
	var AG: Object = root.get_node("/root/Agents")
	AG.rebuild()   # clears the ephemeral proxy -> the next ensure CREATES it fresh
	var p: Agent = AG.ensure_player_proxy(Vector2.ZERO, "city")
	_ok(p.item_count("revolver") == 1, "a fresh proxy carries the revolver (player_loadout)")
	_ok(p.item_count("revolver_round") == 12, "…and its 12 starting rounds")
	p.remove_item("revolver_round", 5)
	var again: Agent = AG.ensure_player_proxy(Vector2(1, 1), "city")
	_ok(again == p, "re-ensuring returns the SAME proxy")
	_ok(again.item_count("revolver_round") == 7,
		"…and does NOT re-grant the loadout (spent rounds stay spent across frames/rooms)")
	AG.rebuild()

func _test_player_combat_dash() -> void:
	print("[player dash: stamina cost + i-frames zero an NPC hit (combat M5)]")
	var EB: Object = root.get_node("/root/EventBus")
	EB.clear()
	var p := _stage_m5_player("m5_arena", Vector2(200, 0))
	var pc: Node = p.get_node("Combat")
	_ok(is_equal_approx(float(p.stamina), 100.0), "the player starts at full stamina")
	p.stamina = 10.0
	var res: Dictionary = pc.on_dash_pressed(Vector2.LEFT)
	_ok(not bool(res.get("ok", false)) and String(res.get("reason", "")) == "no_stamina",
		"dash refuses with 'no_stamina' when the pool can't pay")
	_ok(is_equal_approx(float(p.stamina), 10.0), "a refused dash spends nothing")
	_ok(CombatResolver.ledger_ready(pc.executor.ledger, "dash", pc.executor.now_ms()),
		"a refused cost never burns the dash cooldown")
	p.stamina = 100.0
	# An NPC shooter fires at the player; the dash INTO the round's path is saved only by
	# the i-frame window (geometry alone would connect) — resolver-side, via the proxy's
	# executor state.
	var shooter := _stage_m2("m5_shooter", "m5_arena", Vector2.ZERO)
	var sx := CombatExecutor.new()
	sx.bind(shooter)
	_ok(bool(sx.try_cast("revolver_shot", "player").get("ok", false)), "an NPC shot casts at the player")
	_step_m5(pc, 0.3, [sx])
	_ok(sx.projectiles.size() == 1, "the round is in flight")
	_ok(bool(pc.on_dash_pressed(Vector2.LEFT).get("ok", false)), "the player dashes into the path")
	_ok(is_equal_approx(float(p.stamina), 75.0), "the dash costs its authored 25 stamina")
	_step_m5(pc, 0.9, [sx])
	_ok(pc.proxy.hp == 100.0, "the i-frame window zeroes the NPC hit")
	_ok(EB.events("agent_attacked").is_empty(), "no agent_attacked was emitted")
	_end_m5(p, [sx])

func _test_player_combat_charm() -> void:
	print("[player charm zone slows + silences an NPC (combat M5)]")
	var p := _stage_m5_player("m5_arena")
	var pc: Node = p.get_node("Combat")
	var mark := _stage_m2("m5_cultist", "m5_arena", Vector2(260, 0))
	var mx := CombatExecutor.new()
	mx.bind(mark)
	var res: Dictionary = pc.on_charm_pressed(Vector2.RIGHT)
	_ok(bool(res.get("ok", false)), "use_charm casts paper_charm")
	_step_m5(pc, 0.7, [mx])
	_ok(pc.executor.zones.size() == 1, "the charm's zone entered the world (player executor steps it)")
	_ok(CombatResolver.has_status(mx.state, "slow", mx.now_ms()),
		"an NPC standing in the glyph is slowed")
	_ok(CombatResolver.has_status(mx.state, "silence", mx.now_ms()),
		"…and silenced (the charm's statuses ride the zone ticks)")
	var blocked: Dictionary = mx.try_cast("cleaver_swipe", "player")
	_ok(not bool(blocked.get("ok", false)) and String(blocked.get("reason", "")) == "silenced",
		"the silence blocks the cultist's windup")
	_end_m5(p, [mx])

func _test_combat_hud_binds() -> void:
	print("[combat HUD binds hp/ammo/stamina/pips (combat M5)]")
	var hud = load("res://ui/HUD.tscn").instantiate()
	root.add_child(hud)
	await process_frame
	var chud: Node = hud.get_node_or_null("CombatHUD")
	_ok(chud != null, "the persistent HUD carries the CombatHUD widgets")
	var p := _stage_m5_player("m5_arena")
	var pc: Node = p.get_node("Combat")
	pc.proxy.hp = 37.0
	p.stamina = 55.0
	pc.proxy.inventory["revolver_round"] = 7
	chud.refresh()
	_ok(float(chud.get_node("Vitals/Hp/Bar").value) == 37.0, "hp bar tracks the proxy's hp")
	_ok(String(chud.get_node("Vitals/Ammo/Value").text) == "7",
		"ammo counter tracks the carried rounds (resolved via the granting weapon's ammo_item)")
	pc.proxy.remove_item("revolver", 1)
	chud.refresh()
	_ok(String(chud.get_node("Vitals/Ammo/Value").text) == "—",
		"no carried granting weapon shows '—' (nothing to count rounds FOR)")
	pc.proxy.add_item("revolver", 1)
	chud.refresh()
	_ok(float(chud.get_node("Vitals/Stamina/Bar").value) == 55.0, "stamina bar tracks the player pool")
	_ok(float(chud.get_node("Vitals/Pips/DashBar").value) == 1.0, "dash pip full while ready")
	pc.on_dash_pressed(Vector2.RIGHT)
	chud.refresh()
	_ok(float(chud.get_node("Vitals/Pips/DashBar").value) < 1.0, "…and drains right after a dash")
	_step_m5(pc, 0.7)   # let the dash's FSM run back to idle before the next cast
	pc.on_charm_pressed(Vector2.RIGHT)
	chud.refresh()
	_ok(float(chud.get_node("Vitals/Pips/CharmBar").value) < 1.0, "charm pip drains on cast")
	# hp reacts to the agent_attacked event too (heals have no event; _process polls each frame).
	pc.proxy.hp = 90.0
	root.get_node("/root/EventBus").emit_event("agent_attacked",
		{"actor": "x", "target": "player", "damage": 10.0, "target_hp": 90.0, "downed": false})
	_ok(float(chud.get_node("Vitals/Hp/Bar").value) == 90.0,
		"agent_attacked refreshes the hp bar the moment the hit lands")
	hud.queue_free()
	_end_m5(p)
	await process_frame

func _test_hud_telegraph_vision_gate() -> void:
	print("[HUD enemy-telegraph indicator is vision-gated (combat M5)]")
	var AG: Object = root.get_node("/root/Agents")
	var hud = load("res://ui/HUD.tscn").instantiate()
	root.add_child(hud)
	await process_frame
	var tele: Label = hud.get_node("CombatHUD/Telegraph")
	AG.ensure_player_proxy(Vector2.ZERO, "m5_arena")
	var enemy := _stage_m2("m5_watcher", "m5_arena", Vector2(100, 0))
	_ok(not tele.visible, "no telegraph indicator at rest")
	# Out of the player's room: the cast must show NOTHING (the ONE shared perceiver gate,
	# from the PLAYER proxy's perspective).
	enemy.room = "m5_elsewhere"
	CombatEvents.cast_started("m5_watcher", "cleaver_swipe", "player", Vector2.LEFT, 0.45)
	_ok(not tele.visible, "an out-of-room enemy cast shows nothing")
	# Same room but beyond the proxy's vision_r: still nothing.
	enemy.room = "m5_arena"
	enemy.position = Vector2(500, 0)
	CombatEvents.cast_started("m5_watcher", "cleaver_swipe", "player", Vector2.LEFT, 0.45)
	_ok(not tele.visible, "a beyond-vision cast shows nothing")
	# In room + in vision: the wind-up reads (the GDD's readable-telegraph promise).
	enemy.position = Vector2(100, 0)
	CombatEvents.cast_started("m5_watcher", "cleaver_swipe", "player", Vector2.LEFT, 0.45)
	_ok(tele.visible and tele.text.contains("m5_watcher"),
		"a perceivable enemy wind-up shows the indicator")
	CombatEvents.cast_finished("m5_watcher", "cleaver_swipe")
	_ok(not tele.visible, "the indicator clears when the cast resolves")
	CombatEvents.cast_started("player", "revolver_shot", "", Vector2.RIGHT, 0.25)
	_ok(not tele.visible, "the player's own telegraph never alarms the HUD")
	hud.queue_free()
	AG.rebuild()
	root.get_node("/root/EventBus").clear()
	await process_frame

func _test_player_lethal_downs_endgame() -> void:
	print("[lethal NPC blow downs the proxy + EndGame latches (combat M5)]")
	var EB: Object = root.get_node("/root/EventBus")
	var EG: Object = root.get_node("/root/EndGame")
	EB.clear()
	EG._player_downed_shown = false
	var p := _stage_m5_player("m5_arena", Vector2(30, 0))
	var pc: Node = p.get_node("Combat")
	pc.proxy.hp = 20.0
	var brute := _stage_m2("m5_brute", "m5_arena", Vector2.ZERO)
	var bx := CombatExecutor.new()
	bx.bind(brute)
	var ended: Dictionary = {"n": 0, "outcome": ""}
	var cb := func(o, _r):
		ended["n"] += 1
		ended["outcome"] = o
	EG.ending_reached.connect(cb)
	_ok(bool(bx.try_cast("cleaver_swipe", "player").get("ok", false)), "the brute swings on the player")
	_step_m5(pc, 0.6, [bx])
	_ok(pc.proxy.downed, "the lethal hit downs the proxy (hp flows through the SAME pipes)")
	var downs: Array = EB.events("agent_downed")
	_ok(downs.size() == 1
		and String((downs[0].get("data", {}) as Dictionary).get("target", "")) == "player",
		"agent_downed {target: player} emitted exactly once")
	_ok(ended["n"] == 1 and String(ended["outcome"]) == "player_downed",
		"EndGame fires the terminal player_downed ending")
	EB.emit_event("agent_downed", {"actor": "x", "target": "player"})
	_ok(ended["n"] == 1, "…and it latches (a repeat down never re-fires)")
	EG.ending_reached.disconnect(cb)
	# Put the world back: unpause, re-arm the ending, drop the overlay.
	paused = false
	EG._player_downed_shown = false
	EG._hide_overlay()
	_end_m5(p, [bx])

## ---- Combat M6: the Kell slice (night deed, consequences, Critic amend, anim wiring) ----

## The data-authored night deed (data/deeds.json -> DeedRunner): Kell's own late-night schedule
## walks him to the canal waypoint; a minute tick there fires the deed ONCE per day — the
## authored fact_line fans through the standard vision-gated Stimulus channel, and the player
## proxy SEEING it earns the clue. Phase-, room-, and radius-gated; the latch round-trips.
func _test_deed_runner_night_deed() -> void:
	print("[night deed: schedule-walked witnessable fact + proxy clue (combat M6)]")
	var AG: Object = root.get_node("/root/Agents")
	var EB: Object = root.get_node("/root/EventBus")
	var DR: Object = root.get_node("/root/DeedRunner")
	var CD: Object = root.get_node("/root/ClueDB")
	var Clk: Object = root.get_node("/root/Clock")
	var ART: Object = root.get_node("/root/AgentRuntime")
	var clock_was: Dictionary = Clk.to_dict()
	var clues_was: Dictionary = CD.to_dict()
	var auto_was: bool = ART.auto_run
	ART.auto_run = false   # minute ticks below must not run deliberation beats
	AG.rebuild()
	DR.reset()
	CD.from_dict({})
	EB.clear()
	# The data rows: the deed def and both M6 clue defs exist.
	_ok(CD.library.has("bram_kell_suspicious") and CD.library.has("bram_kell_revealed"),
		"clues.json authors both M6 clue defs")
	var deed: Dictionary = {}
	for d_v in (DR.deeds as Array):
		if String((d_v as Dictionary).get("id", "")) == "kell_canal_disposal":
			deed = d_v
	_ok(not deed.is_empty(), "deeds.json authors the kell_canal_disposal deed")
	_ok(String(deed.get("agent", "")) == "bram_kell" and (deed.get("phases", []) as Array).has("late-night"),
		"the canal deed names bram_kell at late-night")
	_ok(String(deed.get("clue", "")) == "bram_kell_suspicious"
		and CD.library.has(String(deed.get("clue", ""))), "the deed's clue resolves in the library")
	# Kell's OWN schedule carries him there: his late-night waypoint IS the deed waypoint.
	var db: Object = root.get_node("/root/NpcDB")
	var wp_arr: Array = deed.get("waypoint", [])
	var wp := Vector2(float(wp_arr[0]), float(wp_arr[1]))
	_ok(db.waypoint_for("bram_kell", "late-night") == wp,
		"Kell's late-night schedule waypoint IS the deed waypoint (his own walk takes him there)")
	# §0 reachability of the rebound form: butcher_human's data rows carry the dodge reflex and
	# the hp_below(0.5) -> assume_form transform, and assume_form leads OUT of the worn form.
	var ADB: Object = root.get_node("/root/AbilityDB")
	var bform: Dictionary = ADB.form_def("butcher_human")
	var has_dodge := false
	var has_tf := false
	for r_v in (bform.get("reflexes", []) as Array):
		var r: Dictionary = r_v
		var when: Dictionary = r.get("when", {})
		var doo: Dictionary = r.get("do", {})
		if String(when.get("kind", "")) == "telegraph" and String(when.get("of", "")) == "projectile" \
				and bool(when.get("at_me", false)) and String(doo.get("kind", "")) == "dodge":
			has_dodge = true
		if String(when.get("kind", "")) == "hp_below" and float(when.get("value", 0.0)) == 0.5 \
				and String(doo.get("kind", "")) == "cast" and String(doo.get("ability", "")) == "assume_form":
			var delay := int(r.get("delay_ms", 0))
			has_tf = delay >= 150 and delay <= 800
	_ok(has_dodge, "butcher_human authors the projectile-telegraph dodge reflex (§0)")
	_ok(has_tf, "butcher_human authors hp_below(0.5) -> cast assume_form within the reflex delay clamp (§0)")
	_ok((ADB.kit_for("butcher_human") as Array).has("assume_form"),
		"assume_form is IN his kit — transformation is his own ability, never an engine rule")
	# Stage the night: 23:30, Kell standing on the spot; a keen witness, a dim witness, an
	# out-of-room agent, and the watching player proxy.
	Clk.set_time(3, 1410)
	var kell: Agent = AG.get_agent("bram_kell")
	kell.room = "city"
	kell.position = wp
	var keen: Agent = AG.get_agent("fishwife_dalia")
	keen.room = "city"; keen.position = wp + Vector2(100, 0); keen.vision_r = 160.0; keen.short_memory = []
	var dim: Agent = AG.get_agent("dockhand_pell")
	dim.room = "city"; dim.position = wp + Vector2(100, 0); dim.vision_r = 40.0; dim.short_memory = []
	var away: Agent = AG.get_agent("clerk_voss")
	away.room = "cathedral_crypt"; away.position = wp; away.short_memory = []
	AG.ensure_player_proxy(wp + Vector2(-90, 0), "city")
	# M12: the roster now authors a SECOND late-night deed (wren_blackthorn_stalk) whose agent rests
	# at her own waypoint on a late-night minute — count ONLY the kell_canal_disposal deed so this
	# test stays about Kell's canal round, not whatever else the living city walks into that minute.
	var kell_deeds := func() -> int:
		return EB.events("deed_performed").filter(func(e: Dictionary) -> bool:
			return String((e.get("data", {}) as Dictionary).get("deed", "")) == "kell_canal_disposal").size()
	Clk.advance_minutes(1)
	var line := String(deed.get("fact_line", ""))
	_ok(kell_deeds.call() == 1, "the deed fires on a late-night minute at the waypoint")
	_ok(_short_mem_has(keen, line), "a witness within its vision_r gets the authored fact line")
	_ok(not _short_mem_has(dim, line), "a dim witness (vision_r 40) at the same spot sees nothing")
	_ok(not _short_mem_has(away, line), "an out-of-room agent gets nothing")
	_ok(CD.is_collected("bram_kell_suspicious"), "the watching proxy earns the clue bram_kell_suspicious")
	# The digest narrates the deed with its own authored line (no engine wording).
	var dg: Dictionary = GMDigest.build_digest([{"seq": 1, "type": "deed_performed",
		"data": {"actor": "bram_kell", "deed": "kell_canal_disposal", "line": line}}])
	_ok((dg["lines"] as Array).size() == 1 and String((dg["lines"] as Array)[0]) == line,
		"the GM digest carries the deed's authored line verbatim")
	# Once per day; the latch survives a save round-trip; a new day re-arms.
	Clk.advance_minutes(5)
	_ok(kell_deeds.call() == 1, "the deed is latched for the rest of the day")
	DR.from_dict(DR.to_dict())
	Clk.advance_minutes(1)
	_ok(kell_deeds.call() == 1, "…and the latch survives a to_dict/from_dict round-trip")
	Clk.set_time(4, 1410)
	Clk.advance_minutes(1)
	_ok(kell_deeds.call() == 2, "a new day re-arms the deed")
	# Phase- and radius-gating: wrong phase or off the spot fires nothing.
	DR.reset()
	EB.clear()
	Clk.set_time(5, 600)   # 10:00 morning, still on the spot
	Clk.advance_minutes(1)
	_ok(kell_deeds.call() == 0, "a morning minute on the spot fires nothing (phase-gated)")
	Clk.set_time(5, 1410)
	kell.position = wp + Vector2(300, 0)
	Clk.advance_minutes(1)
	_ok(kell_deeds.call() == 0, "a late-night minute OFF the spot fires nothing (radius-gated)")
	DR.reset()
	CD.from_dict(clues_was)
	Clk.from_dict(clock_was)
	ART.auto_run = auto_was
	AG.rebuild()
	EB.clear()

## The M6 consequence rows (data/deeds.json -> DeedRunner): `transformed` for the authored
## agent+form adjusts attention +8 / panic +5 and grants the reveal clue ONLY if the player
## proxy could SEE him; a downing of the monster-form body adjusts attention +4 and confirms
## the clue sight-free; the still-human butcher downing reveals nothing (form-gated row).
## The Stimulus `transformed` fan gives witnesses a neutral fact that never names the form.
func _test_kell_consequences() -> void:
	print("[transform/downed consequences: pressures + sight-gated clue (combat M6)]")
	var AG: Object = root.get_node("/root/Agents")
	var EB: Object = root.get_node("/root/EventBus")
	var CD: Object = root.get_node("/root/ClueDB")
	var WS: Object = root.get_node("/root/WorldState")
	var clues_was: Dictionary = CD.to_dict()
	var attention_was: float = WS.attention
	var panic_was: float = WS.panic
	AG.rebuild()
	EB.clear()
	CD.from_dict({})
	WS.set_pressure(&"attention", 10.0)
	WS.set_pressure(&"panic", 10.0)
	var kell: Agent = AG.get_agent("bram_kell")
	kell.room = "m6_arena"
	kell.position = Vector2.ZERO
	# UNSEEN transform: the proxy is elsewhere — pressures move, the sight-gated clue does NOT.
	AG.ensure_player_proxy(Vector2.ZERO, "m6_elsewhere")
	EB.emit_event("transformed", {"agent": "bram_kell", "form": "bieber_monster"})
	_ok(WS.attention == 18.0 and WS.panic == 15.0, "transformed adjusts attention +8 and panic +5")
	_ok(not CD.is_collected("bram_kell_revealed"), "unseen, the reveal clue does NOT land (sight-gated)")
	# SEEN transform: proxy in room + within its own vision_r of Kell -> the clue lands. (Live,
	# transformed can only fire once per agent+form — the executor no-ops a same-form transform —
	# so this synthetic re-emit exists purely to pin the sight gate.)
	AG.ensure_player_proxy(Vector2(50, 0), "m6_arena")
	EB.emit_event("transformed", {"agent": "bram_kell", "form": "bieber_monster"})
	_ok(CD.is_collected("bram_kell_revealed"), "seen (proxy in room + within proxy vision), the clue lands")
	# Witnesses get the vision-gated Stimulus fact — worded neutrally, never naming the form id.
	var w: Agent = AG.get_agent("fishwife_dalia")
	w.room = "m6_arena"; w.position = Vector2(60, 0); w.vision_r = 160.0; w.short_memory = []
	EB.emit_event("transformed", {"agent": "bram_kell", "form": "bieber_monster"})
	_ok(_short_mem_has(w, "flesh splits"), "witnesses get the vision-gated transformed fact line")
	var leaked := false
	for m in w.short_memory:
		if String(m).contains("bieber"):
			leaked = true
	_ok(not leaked, "…which never leaks the data's form id")
	# An un-authored agent transforming matches no row: nothing adjusts.
	var att_now: float = WS.attention
	EB.emit_event("transformed", {"agent": "clerk_voss", "form": "bieber_monster"})
	_ok(WS.attention == att_now, "a transform by an un-authored agent adjusts nothing")
	# Downed while WEARING the monster: attention +4, clue confirmed WITHOUT a sight gate.
	CD.from_dict({})
	kell.combat_form = "bieber_monster"
	att_now = WS.attention
	EB.emit_event("agent_downed", {"actor": "player", "target": "bram_kell"})
	_ok(WS.attention == att_now + 4.0, "downing the monster-form Kell adjusts attention +4")
	_ok(CD.is_collected("bram_kell_revealed"), "…and CONFIRMS the reveal clue sight-free")
	# Downed while still human: the form-gated row does not match — no reveal from a shopkeeper brawl.
	CD.from_dict({})
	kell.combat_form = "butcher_human"
	att_now = WS.attention
	EB.emit_event("agent_downed", {"actor": "player", "target": "bram_kell"})
	_ok(WS.attention == att_now and not CD.is_collected("bram_kell_revealed"),
		"downing the still-human butcher reveals no monster (form-gated row)")
	CD.from_dict(clues_was)
	WS.set_pressure(&"attention", attention_was)
	WS.set_pressure(&"panic", panic_was)
	AG.rebuild()
	EB.clear()

## The M4 live-gate fix (combat plan §M6 item 5): while an agent is in_combat WITH a live
## executor, the Critic AMENDS a proposed legacy `attack` into `engage {target}` — the executor
## is the damage channel; a beat-level strike would double-dip. Out of combat (or in combat with
## no executor bound) the attack proposal stands unchanged.
func _test_critic_attack_amend() -> void:
	print("[Critic amends in-fight attack -> engage (combat M6)]")
	var AG: Object = root.get_node("/root/Agents")
	var EB: Object = root.get_node("/root/EventBus")
	var SB: Object = root.get_node("/root/SidecarBridge")
	var ART: Object = root.get_node("/root/AgentRuntime")
	var Clk: Object = root.get_node("/root/Clock")
	AG.rebuild()
	EB.clear()
	var brawler := _stage_m2("m6_brawler", "m6_amend", Vector2.ZERO, false)
	var mark := _stage_m2("m6_mark", "m6_amend", Vector2(40, 0), false)
	var attack := {"actor": "m6_brawler", "verb": "attack", "args": {"target": "m6_mark"}, "thought": "strike"}
	_ok(String(Critic.review(attack, brawler)["verdict"]) == "approve",
		"an out-of-combat attack proposal stands unchanged")
	brawler.in_combat = true
	_ok(String(Critic.review(attack, brawler)["verdict"]) == "approve",
		"in combat with NO live executor the attack still stands (it is the only damage channel)")
	var ex := CombatExecutor.new()
	ex.bind(brawler)
	brawler.combat_intent = {"mode": "engage", "target": "m6_mark", "style": "cautious", "set_at_beat": -5}
	var v: Dictionary = Critic.review(attack, brawler)
	_ok(String(v["verdict"]) == "amend", "with a live executor the attack is AMENDED")
	var act: Dictionary = v["action"]
	_ok(String(act.get("verb", "")) == "engage"
		and String((act.get("args", {}) as Dictionary).get("target", "")) == "m6_mark",
		"…into engage {target} at the proposed mark")
	_ok(String((act.get("args", {}) as Dictionary).get("style", "")) == "cautious",
		"…keeping the standing style")
	_ok(String(act.get("thought", "")) == "strike", "…with the proposal's thought riding along")
	# Committing the amendment PRESERVES/REFRESHES the stance and deals no beat-level damage.
	var hp_before: float = mark.hp
	ActionCommit.commit(act, brawler)
	_ok(String(brawler.combat_intent.get("mode", "")) == "engage"
		and String(brawler.combat_intent.get("target", "")) == "m6_mark"
		and String(brawler.combat_intent.get("style", "")) == "cautious",
		"committing the amendment preserves the combat intent")
	_ok(int(brawler.combat_intent.get("set_at_beat", -99)) == int(Clk.beat_index),
		"…re-stamped to THIS beat (refreshed)")
	_ok(mark.hp == hp_before, "…and applies no beat-level damage (the executor is the damage channel)")
	# No standing style: the amendment names none, so _engage falls to its default.
	brawler.combat_intent = {}
	var v2: Dictionary = Critic.review(attack, brawler)
	_ok(not ((v2["action"] as Dictionary).get("args", {}) as Dictionary).has("style"),
		"no standing style -> the amendment names none (engage defaults it)")
	# End-to-end through the runtime: the amended commit logs as agent_action_amended.
	brawler.combat_intent = {"mode": "engage", "target": "m6_mark", "style": "cautious", "set_at_beat": 0}
	var mock := MockSidecar.new()
	mock.set_action("m6_brawler", attack)
	SB.set_client(mock)
	ART.player_position = Vector2.ZERO
	ART.active_radius = 100.0
	EB.clear()
	ART.run_beat()
	var amended_events: Array = _events_by(EB, "agent_action_amended", "actor", "m6_brawler")
	_ok(amended_events.size() == 1
		and String((amended_events[0].get("data", {}) as Dictionary).get("verb", "")) == "engage",
		"the runtime commits the amendment and logs agent_action_amended {verb: engage}")
	ex.free()
	AG.rebuild()
	EB.clear()

## The M6 anim first pass: a Sprite2D body plays the worn form's authored 8-frame strips on the
## executor clock (attack on cast, hurt on a landed hit, death held on downing), the transform
## swaps the body sprite to the revealed form's authored art, and EVERY step is defensive —
## body-less executors and strip-less forms no-op silently (the headless sims stay byte-identical).
func _test_combat_anim_wiring() -> void:
	print("[executor anim wiring: strips, death hold, transform sprite (combat M6)]")
	var AG: Object = root.get_node("/root/Agents")
	var EB: Object = root.get_node("/root/EventBus")
	AG.rebuild()
	EB.clear()
	# Body-less: every cue no-ops (this is the sim harness path).
	var ghost := _stage_m2("m6_ghost", "m6_anim", Vector2.ZERO)
	ghost.combat_form = "bieber_monster"
	var gx := CombatExecutor.new()
	gx.bind(ghost)
	_ok(bool(gx.try_cast("cleaver_swipe", "").get("ok", false)), "a body-less cast still casts (anim no-ops)")
	_step_m2([gx], 1.0)
	# A Sprite2D body wearing bieber_monster: the attack strip swaps in, advances, and swaps back.
	var body := CharacterBody2D.new()
	var sprite := Sprite2D.new()
	sprite.name = "Sprite2D"
	var base_tex: Texture2D = load("res://icon.svg")
	sprite.texture = base_tex
	body.add_child(sprite)
	root.add_child(body)
	var monster := _stage_m2("m6_monster", "m6_anim", Vector2(300, 0))
	monster.combat_form = "bieber_monster"
	var mx := CombatExecutor.new()
	mx.bind(monster, body)
	_ok(bool(mx.try_cast("cleaver_swipe", "").get("ok", false)), "the monster swings")
	_ok(sprite.texture != base_tex
		and String(sprite.texture.resource_path).ends_with("bieber_monster_attack_side.png"),
		"the attack cue swaps in the form's authored strip")
	_ok(sprite.hframes == 8, "…as an 8-frame side strip")
	_step_m2([mx], 0.4)
	_ok(sprite.frame > 0, "the strip's frames advance on the executor clock")
	_step_m2([mx], 1.0)
	_ok(sprite.texture == base_tex and sprite.hframes == 1, "a finished strip restores the resting look")
	# hurt on a landed hit; death held on the felling blow.
	var shot: Dictionary = root.get_node("/root/AbilityDB").ability_for("revolver_shot")
	mx.receive_hit(ghost, shot, Vector2.RIGHT)
	_ok(String(sprite.texture.resource_path).ends_with("bieber_monster_hurt_down.png"),
		"a landed hit plays the hurt strip")
	_step_m2([mx], 1.0)
	_ok(sprite.texture == base_tex, "…and the flinch restores")
	monster.hp = 10.0
	mx.receive_hit(ghost, shot, Vector2.RIGHT)
	_ok(monster.downed, "the felling blow downs the body")
	_ok(String(sprite.texture.resource_path).ends_with("bieber_monster_death_down.png"),
		"…playing the death strip")
	_step_m2([mx], 2.0)
	_ok(String(sprite.texture.resource_path).ends_with("bieber_monster_death_down.png") and sprite.frame == 7,
		"…which HOLDS its final frame (the body stays down, never deleted)")
	# The human butcher: no authored strips -> cues no-op; the transform swaps the body sprite to
	# the revealed form's art and REBASES, so later strips restore to the monster, never the man.
	var body2 := CharacterBody2D.new()
	var sprite2 := Sprite2D.new()
	sprite2.name = "Sprite2D"
	sprite2.texture = base_tex
	body2.add_child(sprite2)
	root.add_child(body2)
	var kell := _stage_m2("m6_kell_anim", "m6_anim", Vector2(600, 0))
	kell.combat_form = "butcher_human"
	var kx := CombatExecutor.new()
	kx.bind(kell, body2)
	_ok(bool(kx.try_cast("cleaver_swipe", "").get("ok", false)), "the human butcher swings")
	_ok(sprite2.texture == base_tex, "…but butcher_human authors no strips, so the cue no-ops (defensive)")
	_step_m2([kx], 2.0)
	_ok(bool(kx.try_cast("assume_form", "").get("ok", false)), "the butcher casts assume_form")
	_step_m2([kx], 2.0)
	_ok(kell.combat_form == "bieber_monster", "the transform resolved")
	_ok(String(sprite2.texture.resource_path).ends_with("enemies/bieber_monster.png"),
		"…and the body's sprite became the revealed form's authored art")
	_ok(sprite2.hframes == 1, "…as a single-frame body sprite")
	kx.receive_hit(ghost, shot, Vector2.RIGHT)
	_ok(String(sprite2.texture.resource_path).ends_with("bieber_monster_hurt_down.png"),
		"post-transform hits play the MONSTER's strips")
	_step_m2([kx], 1.0)
	_ok(String(sprite2.texture.resource_path).ends_with("enemies/bieber_monster.png"),
		"…and restore to the monster base, never the shed skin")
	gx.free()
	mx.free()
	kx.free()
	body.free()
	body2.free()
	AG.rebuild()
	EB.clear()

## ---- Combat VFX (M1: make a fight legible) ----
## The FX layer is PURELY COSMETIC: scene visuals + a read-only EventBus listener that spawns
## transient nodes. It must never mutate combat/agent/world state or alter the sim transcript.

## (a) The projectile/zone scenes instantiate with a textured visual node.
func _test_combat_fx_scenes_have_visuals() -> void:
	print("[combat fx: projectile/zone scenes carry a textured visual (combat M1)]")
	var proj: CombatProjectile = load("res://scenes/CombatProjectile.tscn").instantiate()
	var pvis := _first_textured_visual(proj)
	_ok(pvis != null, "CombatProjectile.tscn carries a textured visual node")
	# The default fx resolves to the bullet tracer; setup orients it to travel direction.
	proj.setup(null, {"class": "projectile", "projectile": {"speed": 100.0}, "range": 300.0},
		Vector2.ZERO, Vector2.UP)
	var pvis2 := _first_textured_visual(proj)
	_ok(pvis2 != null and pvis2.texture != null, "the projectile visual has a texture after setup")
	_ok(absf(pvis2.rotation - Vector2.UP.angle()) < 0.001, "…oriented to the travel direction")
	proj.free()
	var zone: CombatZone = load("res://scenes/CombatZone.tscn").instantiate()
	var zvis := _first_textured_visual(zone)
	_ok(zvis != null, "CombatZone.tscn carries a textured visual node")
	zone.setup(null, {"kind": "zone", "radius": 120.0, "duration": 4.0, "tick": 0.5, "statuses": []},
		Vector2.ZERO)
	var zvis2 := _first_textured_visual(zone)
	_ok(zvis2 != null and zvis2.texture != null, "the zone visual has a texture after setup")
	# Sized to radius: on-screen half-extent (texture_h/2 * scale.y) tracks the 120px radius.
	var half := 0.5 * float(zvis2.texture.get_height()) * absf(zvis2.scale.y)
	_ok(absf(half - 120.0) < 2.0, "…scaled so the glyph spans the zone radius")
	zone.free()

## The first descendant Sprite2D under a node (the FX visual), null if none.
func _first_textured_visual(n: Node) -> Sprite2D:
	if n is Sprite2D:
		return n as Sprite2D
	for c in n.get_children():
		var found := _first_textured_visual(c)
		if found != null:
			return found
	return null

## (b) The CombatFx spawner creates a transient on an agent_attacked event and frees it after
## its lifetime — read-only, no combat-state feedback.
func _test_combat_fx_spawner_transient() -> void:
	print("[combat fx: spawner creates + frees a transient on a hit event (combat M1)]")
	var FX: Object = root.get_node_or_null("/root/CombatFx")
	_ok(FX != null, "CombatFx autoload is registered")
	if FX == null:
		return
	FX.clear_transients()
	var before := int(FX.transient_count())
	root.get_node("/root/EventBus").emit_event("agent_attacked",
		{"actor": "fx_a", "target": "fx_b", "damage": 10.0, "target_hp": 90.0, "downed": false})
	await process_frame
	_ok(int(FX.transient_count()) > before, "a hit event spawns at least one transient FX node")
	# The transients live in a dedicated layer, never under an executor or an Agent.
	_ok(FX.has_fx_layer(), "transients live in the cosmetic FX layer (never in combat nodes)")
	# Step past the longest transient lifetime; the pool frees them.
	var t := 0.0
	while t < 2.5 and int(FX.transient_count()) > before:
		FX.step_fx(1.0 / 60.0)
		await process_frame
		t += 1.0 / 60.0
	_ok(int(FX.transient_count()) == before, "the transient frees itself after its lifetime (no leak)")
	FX.clear_transients()

## (c) abilities.json carries the optional fx field; the resolver defaults cleanly for a missing one.
func _test_abilities_fx_field_and_resolver() -> void:
	print("[combat fx: abilities carry fx + resolver defaults (combat M1)]")
	var DB: Object = root.get_node("/root/AbilityDB")
	var shot: Dictionary = DB.ability_for("revolver_shot")
	_ok(String(shot.get("fx", "")) == "bullet_tracer", "revolver_shot authors fx=bullet_tracer")
	var charm: Dictionary = DB.ability_for("paper_charm")
	_ok(String(charm.get("fx", "")) == "charm_glyph", "paper_charm authors fx=charm_glyph")
	var dash: Dictionary = DB.ability_for("dash")
	_ok(String(dash.get("fx", "")) == "dash_afterimage_wisp", "dash authors fx=dash_afterimage_wisp")
	# The resolver maps an fx id to an existing texture, and DEFAULTS for a missing/unknown id.
	_ok(ResourceLoader.exists(CombatFxLib.texture_path("bullet_tracer")),
		"the fx resolver maps a known id to a real texture")
	_ok(ResourceLoader.exists(CombatFxLib.texture_path("")),
		"…and an ability with NO fx field resolves to a real default texture")
	_ok(ResourceLoader.exists(CombatFxLib.texture_path("does_not_exist_xyz")),
		"…and an unknown id degrades to the default, never a missing resource")
	# Regression (review finding #1): a NON-STRING fx field (int/array/dict/bool from malformed
	# data) must resolve to "" WITHOUT throwing a String() constructor error, then default cleanly.
	for bad_fx in [7, [1, 2], {"a": 1}, true, null]:
		_ok(CombatFxLib.fx_id_of({"fx": bad_fx}) == "",
			"a non-string fx (%s) resolves to empty, not a script error" % [typeof(bad_fx)])
	_ok(CombatFxLib.fx_id_of({"vfxId": 42}) == "", "a non-string vfxId also degrades to empty")
	_ok(ResourceLoader.exists(CombatFxLib.texture_path(CombatFxLib.fx_id_of({"fx": [1, 2]}))),
		"…and a malformed-fx ability still resolves to a real default texture")

## (d) Determinism guard: identical fights with FX enabled vs a no-FX control produce identical
## combat EVENT transcripts. FX changes nothing the sim can observe.
func _test_combat_fx_determinism_guard() -> void:
	print("[combat fx: identical event transcript with FX on vs off (combat M1)]")
	var with_fx := await _run_fx_fight(true)
	var no_fx := await _run_fx_fight(false)
	_ok(with_fx == no_fx and not with_fx.is_empty(),
		"the combat event transcript is byte-identical with FX enabled vs disabled")

## Stage a fixed revolver duel and return the combat event transcript (order + payload), FX on/off.
func _run_fx_fight(fx_enabled: bool) -> Array:
	var AG: Object = root.get_node("/root/Agents")
	var EB: Object = root.get_node("/root/EventBus")
	var FX: Object = root.get_node_or_null("/root/CombatFx")
	if FX != null:
		FX.set_enabled(fx_enabled)
		FX.clear_transients()
	AG.rebuild()
	EB.clear()
	var shooter := _stage_m2("fxd_shooter", "fxd_room", Vector2.ZERO)
	var mark := _stage_m2("fxd_mark", "fxd_room", Vector2(200, 0))
	var sx := CombatExecutor.new()
	sx.bind(shooter)
	var mx := CombatExecutor.new()
	mx.bind(mark)
	sx.try_cast("revolver_shot", "fxd_mark")
	_step_m2([sx, mx], 1.0)
	await process_frame   # let any FX listener drain
	var combat_types := ["ability_cast_started", "ability_cast_finished",
		"ability_cast_interrupted", "agent_attacked", "agent_downed", "transformed"]
	var transcript: Array = []
	for ev in EB.events():
		if combat_types.has(String(ev.get("type", ""))):
			transcript.append({"type": ev.get("type"), "data": ev.get("data")})
	sx.free()
	mx.free()
	if FX != null:
		FX.set_enabled(true)
		FX.clear_transients()
	AG.rebuild()
	EB.clear()
	return transcript

## M2 run shell: the RunManager autoload owns run lifecycle. Smoke-level asserts here (the
## full lifecycle + GAP-2.9 leak test live in tests/test_run_shell.gd); these keep the main
## suite honest that the autoload exists and start_run() resets a dirtied world to run-start.
func _test_run_manager_run_shell() -> void:
	print("[run shell: RunManager autoload owns the run lifecycle (M2)]")
	var RM: Object = root.get_node_or_null("/root/RunManager")
	_ok(RM != null, "RunManager autoload is registered")
	if RM == null:
		return
	var WS: Object = root.get_node("/root/WorldState")
	var CDB: Object = root.get_node("/root/ClueDB")
	var SP: Object = root.get_node("/root/SummoningPlan")
	# Dirty the run world, then a fresh run must scrub it back to run-start.
	WS.set_pressure(&"corruption", 91.0)
	CDB.collect("antigonus_notebook")
	SP.impede_score = 25.0
	RM.start_run()
	_ok(RM.current_day() == 1 and RM.current_phase() == "morning",
		"start_run() stamps day 1 / morning")
	_ok(is_equal_approx(WS.corruption, 5.0), "start_run() resets a dirtied pressure to run-start")
	_ok(CDB.collected_count() == 0, "start_run() clears collected clues (GAP-2.9)")
	_ok(is_equal_approx(SP.impede_score, 0.0), "start_run() resets the summoning plan")
	_ok(RM.total_days() >= 7, "the run calendar is ~7 in-game days")

## M4 four-meter system (direction v2 §4). Smoke-level asserts in the main suite; the full
## push-your-luck harness (drivers, vision-gated Heat, rampage, determinism guard, HUD) lives in
## tests/test_meters.gd. These keep the main suite honest that the meters clamp/reset, the Madness
## ladder telegraphs each rung once, panic is Doom-derived, and Doom rises on a rite step.
func _test_meters_clamp_reset_and_ladder() -> void:
	print("[meters: the four clamp 0..100, reset to RUN_START, Madness ladder fires once (M4)]")
	var M: Object = root.get_node_or_null("/root/Meters")
	_ok(M != null, "Meters autoload is registered")
	if M == null:
		return
	M.set_meter("doom", 250.0)
	_ok(M.get_meter("doom") == 100.0, "a meter clamps high to 100")
	M.set_meter("heat", -20.0)
	_ok(M.get_meter("heat") == 0.0, "a meter clamps low to 0")
	root.get_node("/root/RunManager").start_run()
	_ok(M.get_meter("madness") == M.run_start("madness")
		and M.get_meter("heat") == M.run_start("heat"),
		"start_run() scrubs the meters to RUN_START")
	var fired: Array = []
	var cb := func(level: int) -> void: fired.append(level)
	M.madness_threshold.connect(cb)
	M.set_meter("madness", 0.0)
	M.add_madness(50.0)
	M.add_madness(25.0)
	_ok(fired == [50, 75], "the Madness ladder fires 50 then 75 exactly once each")
	M.madness_threshold.disconnect(cb)
	M.set_meter("madness", 0.0)

func _test_meters_panic_derived_and_doom_driver() -> void:
	print("[meters: panic is a pure function of Doom; a rite step raises Doom (M4)]")
	var M: Object = root.get_node_or_null("/root/Meters")
	if M == null:
		return
	M.set_meter("doom", 0.0)
	var p0: float = M.panic()
	M.set_meter("doom", 100.0)
	_ok(M.panic() > p0, "panic rises with Doom")
	_ok(M.panic() == M.panic(), "panic is deterministic for a fixed Doom")
	M.set_meter("doom", 10.0)
	var before: float = M.get_meter("doom")
	root.get_node("/root/EventBus").emit_event("ritual_advanced",
		{"actor": "cultist", "step": 1, "closeness": 0.5})
	_ok(M.get_meter("doom") > before, "a rite-step event raises Doom (driver-wired)")

func _test_meters_rampage_ends_run() -> void:
	print("[meters: Madness 100 -> rampage transforms the player + ends the run 'lost_control' (M4)]")
	var M: Object = root.get_node_or_null("/root/Meters")
	if M == null:
		return
	var AG: Object = root.get_node("/root/Agents")
	var RM: Object = root.get_node("/root/RunManager")
	RM.start_run()
	AG.rebuild()
	var proxy: Agent = AG.ensure_player_proxy(Vector2.ZERO, "suite_rampage")
	proxy.combat_form = "player"
	M.rampage_duration_s = 0.5
	var ended := {"reason": ""}
	var cb := func(reason: String) -> void: ended["reason"] = reason
	RM.run_ended.connect(cb)
	M.set_meter("madness", 0.0)
	M.add_madness(100.0)
	_ok(M.in_rampage() and proxy.combat_form != "player",
		"Madness 100 transforms the player proxy into the rampage form")
	M.tick_rampage(0.6)
	_ok(ended["reason"] == "lost_control" and not M.in_rampage(),
		"at the window's expiry RunManager.end_run('lost_control') fires")
	RM.run_ended.disconnect(cb)
	RM.start_run()
	AG.rebuild()
	# Regression (review M4 #1): the Ritual-Night latch must NOT survive a checkpoint restore that
	# pulled Doom back below 100 (the M2-class leak). Checkpoint at Doom<100, top Doom out, then a
	# death restores the pre-100 snapshot -> the latch re-derives false.
	M.set_meter("doom", 40.0)
	RM.checkpoint_night()
	M.set_meter("doom", 100.0)
	_ok(RM.ritual_night_reached(), "Doom 100 latches Ritual Night")
	RM.end_run("death")
	_ok(M.get_meter("doom") < 100.0 and not RM.ritual_night_reached(),
		"the Ritual-Night latch clears on a checkpoint restore (no M2-class leak)")
	RM.start_run()
	AG.rebuild()

## M5 Sequence progression (direction v2 §6 — the RPG spine). Smoke-level asserts in the main
## suite; the full harness (snapshot/restore within a run, cross-run reset, live-proxy kit growth,
## determinism guard) lives in tests/test_progression.gd. These keep the main suite honest that
## progression starts Hunter · Seq 9, the digest->advance loop consumes the Characteristic + raises
## the rank + spikes Madness + grows the kit, a same-pathway kill drops the harvestable Characteristic
## while an off-pathway one does not, and the two new ability rows load with valid shapes + fx.
func _test_progression_advance_loop() -> void:
	print("[progression: Hunter Seq 9 -> the harvest/deed/advance loop raises the rank, spikes Madness, grows the kit (M5)]")
	var P: Object = root.get_node_or_null("/root/Progression")
	_ok(P != null, "Progression autoload is registered")
	if P == null:
		return
	var RM: Object = root.get_node("/root/RunManager")
	var AG: Object = root.get_node("/root/Agents")
	var M: Object = root.get_node("/root/Meters")
	var DB: Object = root.get_node("/root/AbilityDB")
	RM.start_run()
	AG.rebuild()
	_ok(P.pathway() == "hunter" and P.sequence() == 9, "a fresh run starts Hunter · Seq 9")
	# Refused with neither a same-pathway Characteristic nor the acting deed done.
	_ok(not bool(P.can_advance().get("ok", false)), "advance is refused with no characteristic and no deed")
	var proxy: Agent = AG.ensure_player_proxy(Vector2.ZERO, "suite_prog")
	proxy.add_item("hunter_characteristic", 1)
	P.mark_deed_done()   # the acting ritual performed for this advance
	M.set_meter("madness", 0.0)
	var res: Dictionary = P.advance()
	_ok(bool(res.get("ok", false)) and P.sequence() == 8, "a full advance raises the rank 9 -> 8")
	_ok(proxy.item_count("hunter_characteristic") == 0, "the advance consumes the same-pathway Characteristic")
	_ok(absf(M.get_meter("madness") - 35.0) < 0.01, "the advance spikes Madness by ~35 (digest)")
	_ok(P.granted_arts().has("mark_prey") and DB.kit_for("player").has("mark_prey"),
		"Seq 8 grows the Hunter kit with mark_prey (reaching the player's usable arts)")
	# 8 -> 7 grows incendiary_round; the slice caps at Seq 7.
	proxy.add_item("hunter_characteristic", 1)
	P.mark_deed_done()
	P.advance()
	_ok(P.sequence() == 7 and DB.kit_for("player").has("incendiary_round"),
		"Seq 7 grows the Hunter kit with incendiary_round")
	proxy.add_item("hunter_characteristic", 1)
	P.mark_deed_done()
	_ok(not bool(P.can_advance().get("ok", false)), "the slice ladder caps at Seq 7")
	# Cross-run reset: no stat inheritance (§8).
	RM.start_run()
	AG.rebuild()
	_ok(P.sequence() == 9 and P.granted_arts().is_empty(),
		"a new run resets the rank + wipes the granted arts (no cross-run inheritance)")

func _test_progression_characteristic_drop() -> void:
	print("[progression: a same-pathway kill drops a harvestable Characteristic; an off-pathway kill does not (M5)]")
	var P: Object = root.get_node_or_null("/root/Progression")
	if P == null:
		return
	var RM: Object = root.get_node("/root/RunManager")
	var AG: Object = root.get_node("/root/Agents")
	var EB: Object = root.get_node("/root/EventBus")
	var RI: Object = root.get_node("/root/RoomItems")
	RM.start_run()
	AG.rebuild()
	# A hunter-pathway foe (pathway is DATA on the agent) drops a hunter_characteristic where it fell.
	var foe := Agent.new("suite_hunter_foe")
	foe.room = "suite_drop"
	foe.position = Vector2(100, 50)
	foe.combat_form = "butcher_human"
	foe.pathway = "hunter"
	foe.downed = true
	AG._agents["suite_hunter_foe"] = foe
	RI.clear()
	EB.emit_event("agent_downed", {"actor": "player", "target": "suite_hunter_foe"})
	_ok(RI.count("suite_drop", "hunter_characteristic") >= 1,
		"downing a hunter-pathway foe drops a hunter_characteristic")
	# The off-pathway butcher (pathway "") drops a generic characteristic, NOT the hunter one (§3).
	var butcher := Agent.new("suite_butcher")
	butcher.room = "suite_butcher_room"
	butcher.position = Vector2(80, 20)
	butcher.combat_form = "butcher_human"
	butcher.pathway = ""
	butcher.downed = true
	AG._agents["suite_butcher"] = butcher
	RI.clear()
	EB.emit_event("agent_downed", {"actor": "player", "target": "suite_butcher"})
	_ok(RI.count("suite_butcher_room", "hunter_characteristic") == 0
		and RI.count("suite_butcher_room") >= 1,
		"the off-pathway butcher drops a generic characteristic, not a hunter one")
	RI.clear()
	AG.rebuild()

func _test_progression_new_abilities_shapes() -> void:
	print("[abilities: mark_prey + incendiary_round load with valid shapes + fx and pass validate_refs (M5)]")
	var DB: Object = root.get_node_or_null("/root/AbilityDB")
	if DB == null:
		return
	for aid in ["mark_prey", "incendiary_round"]:
		_ok(DB.has_ability(aid), "%s is loaded in AbilityDB" % aid)
		var a: Dictionary = DB.ability_for(aid)
		_ok(String(a.get("class", "")) != "" and String(a.get("fx", "")) != ""
			and a.get("effects", []) is Array and not (a.get("effects", []) as Array).is_empty(),
			"%s authors a class, an fx field, and a non-empty effects array" % aid)
	var problems: Array = DB.validate_refs(
		{"mark_prey": DB.ability_for("mark_prey"), "incendiary_round": DB.ability_for("incendiary_round")}, {})
	_ok(problems.is_empty(), "the two new rows pass AbilityDB.validate_refs")
	# Hardening (M5 review minor #1): a DIRECT kind:"status" effect that names a status the resolver
	# doesn't know (a typo'd "slwo") loaded silently and no-op'd every tick — validate_refs now catches
	# it against CombatResolver.STATUS_KINDS, the same way it already guards zone status names.
	_ok(not DB.validate_refs({"vx_bad_status": {"class": "effect",
		"effects": [{"kind": "status", "status": "slwo", "duration": 1.0}]}}, {}).is_empty(),
		"validate_refs flags a direct status effect with an unknown status name")
	# The real resolver kinds (incl. `dot`, which is NOT in the zone-only NAMED_STATUS_DEFAULTS) stay
	# clean — mark_prey's `slow` and incendiary_round's `dot` are legal, so the guard can't false-flag.
	_ok(DB.validate_refs({"vx_ok_status": {"class": "effect",
		"effects": [{"kind": "status", "status": "dot", "duration": 1.0}]}}, {}).is_empty(),
		"validate_refs accepts a direct status effect naming a real resolver status kind (dot)")

# --- M6: Rumors -> Leads (direction v2 §5) ----------------------------------------------------
func _test_leads_run_start_and_source_gate() -> void:
	print("[leads: run start slots the guaranteed butcher lead; leads surface source-gated (M6)]")
	var LS: Object = root.get_node_or_null("/root/LeadSystem")
	if LS == null:
		_ok(false, "LeadSystem autoload exists")
		return
	var RM: Object = root.get_node("/root/RunManager")
	RM.start_run()
	var butcher: Dictionary = LS.get_lead("butcher_iron_cross")
	_ok(not butcher.is_empty() and String(butcher.get("source", "")) == "constable_brom"
		and String(butcher.get("where_hint", "")) == "Iron Cross Street"
		and String(butcher.get("state", "")) == "open",
		"run start slots the guaranteed butcher lead from constable_brom, hot on Iron Cross Street, open")
	# Source-gated reveal: the source surfaces it; an NPC who wouldn't know does not.
	_ok(String(LS.surface_from("constable_brom").get("id", "")) == "butcher_iron_cross",
		"constable_brom (the source) surfaces the butcher lead")
	_ok(not LS.npc_knows("old_neil", butcher),
		"old_neil (no beat knowledge) would NOT surface the butcher lead")
	# STRONG gate proof (M6 review finding 4a): the knowledge branch must both ACCEPT a real
	# secondary knower and REJECT a real non-source/non-knower — against a lead that HAS a live
	# secondary knower in npcs.json, so the branch is genuinely exercised (not trivially empty).
	# maribel_hatch is NOT the butcher lead's source, but her knowledge names the strange butcher, so
	# the DATA-driven multi-source gate lets her surface it; old_neil (alchemist) knows neither.
	_ok(LS.npc_knows("maribel_hatch", butcher),
		"maribel_hatch (non-source) KNOWS the butcher lead via npcs.json knowledge (multi-source gate accepts)")
	_ok(String(LS.surface_from("maribel_hatch").get("id", "")) == "butcher_iron_cross",
		"a non-source knower actually surfaces the lead through the knowledge branch")
	_ok(not LS.npc_knows("old_neil", butcher),
		"old_neil (non-source, non-knower) is REJECTED against a lead with a live secondary knower (gate rejects)")
	# The courier lead is likewise reachable by a non-source knower (dockhand_pell), proving the
	# multi-source path is content-live for more than one lead.
	var courier: Dictionary = LS.get_lead("cult_courier")
	if not courier.is_empty():
		_ok(LS.npc_knows("dockhand_pell", courier) and String(courier.get("source", "")) != "dockhand_pell",
			"dockhand_pell (non-source) KNOWS the courier lead via knowledge (second live multi-source edge)")
	# The npc_said bus seam (the converse route fires it today; ambient beats ride the same seam)
	# surfaces the speaker's lead.
	var EB: Object = root.get_node("/root/EventBus")
	var seen := {"id": ""}
	var cb := func(_n: String, lead: Dictionary): seen["id"] = String(lead.get("id", ""))
	LS.lead_from_chatter.connect(cb)
	EB.emit_event("npc_said", {"agent": "constable_brom", "text": "blood under the door."})
	LS.lead_from_chatter.disconnect(cb)
	_ok(seen["id"] == "butcher_iron_cross",
		"a spoken line from the source surfaces the lead through the shared npc_said seam")

func _test_leads_perish_cold_respawn() -> void:
	print("[leads: an unfollowed lead goes cold past the threshold -> Doom+5 -> a new lead elsewhere (M6)]")
	var LS: Object = root.get_node_or_null("/root/LeadSystem")
	if LS == null:
		return
	var RM: Object = root.get_node("/root/RunManager")
	var Mt: Object = root.get_node("/root/Meters")
	RM.start_run()
	var before_doom: float = Mt.get_meter("doom")
	var before_count: int = LS.active_leads().size()
	var butcher: Dictionary = LS.get_lead("butcher_iron_cross")
	var old_where := String(butcher.get("where_hint", ""))
	LS.perish_tick(int(butcher.get("spawned_day", 1)) + LS.COLD_AFTER_DAYS + 1)
	_ok(LS.get_lead("butcher_iron_cross").is_empty(),
		"the cold lead leaves the board (the subject moved)")
	_ok(Mt.get_meter("doom") >= before_doom + 5.0,
		"a cold lead bumps Doom +5 through the Meters API")
	var respawn: Dictionary = LS.get_lead("butcher_iron_cross_2")
	_ok(not respawn.is_empty()
		and String(respawn.get("where_hint", "")) != old_where
		and String(respawn.get("where_hint", "")) != "",
		"a fresh lead re-emerges elsewhere with a new where_hint")
	_ok(LS.active_leads().size() == before_count,
		"the board count holds (one cold removed, one fresh spawned)")

func _test_leads_follow_resolve_and_snapshot() -> void:
	print("[leads: follow+resolve closes; reset per run; snapshot/restore within a run (M6)]")
	var LS: Object = root.get_node_or_null("/root/LeadSystem")
	if LS == null:
		return
	var RM: Object = root.get_node("/root/RunManager")
	RM.start_run()
	LS.follow("butcher_iron_cross")
	_ok(String(LS.get_lead("butcher_iron_cross").get("state", "")) == "followed",
		"following a lead marks it followed")
	var b: Dictionary = LS.get_lead("butcher_iron_cross")
	LS.perish_tick(int(b.get("spawned_day", 1)) + LS.COLD_AFTER_DAYS + 1)
	_ok(not LS.get_lead("butcher_iron_cross").is_empty(),
		"a followed lead survives the perish tick")
	# Snapshot the followed (unresolved) lead, mutate, restore -> it comes back.
	var snap: Dictionary = LS.to_dict()
	LS.resolve("butcher_iron_cross")
	_ok(LS.get_lead("butcher_iron_cross").is_empty(), "a resolved lead leaves the board")
	LS.from_dict(snap)
	_ok(String(LS.get_lead("butcher_iron_cross").get("state", "")) == "followed",
		"snapshot/restore brings the followed lead back within a run")
	# A fresh run re-slots to open (no cross-run carry).
	RM.start_run()
	_ok(String(LS.get_lead("butcher_iron_cross").get("state", "")) == "open",
		"a new run resets leads to open (no cross-run carry)")

func _test_leads_determinism_fixed_seed() -> void:
	print("[leads: slotting for a fixed run-seed is identical across runs (M6)]")
	var LS: Object = root.get_node_or_null("/root/LeadSystem")
	if LS == null:
		return
	LS.slot_run(4242)
	var a := _leads_where_sig(LS.active_leads())
	LS.slot_run(4242)
	var b := _leads_where_sig(LS.active_leads())
	_ok(a == b and not a.is_empty(),
		"the same run-seed slots identical leads (deterministic reshuffle)")
	LS.slot_run(9999)
	var c := _leads_where_sig(LS.active_leads())
	_ok(c.size() == a.size(),
		"a different seed still slots the same lead set (variety is in placement)")
	# STRONG variety proof (M6 review finding 4b): a different seed must actually MOVE at least one
	# lead's where_hint — otherwise "variety in placement" is unverified. (The guaranteed butcher lead
	# is fixed on Iron Cross Street by design; the weighted-candidate leads are what shift.)
	_ok(c != a,
		"a different seed produces a DIFFERENT placement signature (the reshuffle is real): 4242=%s 9999=%s" % [a, c])
	# Leave the world in a clean, re-slotted state for any later test.
	var RM: Object = root.get_node("/root/RunManager")
	RM.start_run()

func _leads_where_sig(rows: Array) -> Array:
	var out: Array = []
	for r in rows:
		out.append("%s@%s" % [r.get("id", ""), r.get("where_hint", "")])
	out.sort()
	return out

## M8 first-ten-minutes opening (direction v2 §3) — a smoke-level assertion in the main suite that the
## GM guarantees run-1's opening end to end: the hot butcher lead surfaces at run start + routes to a
## staged/reachable bram_kell; downing him yields the harvest fork + the same-pathway follow-up; a
## witnessed kill reveals Heat; >=2 follow-up leads (hunter + cult) are live; and it all resets per
## run. The full harness lives in tests/test_opening.gd.
func _test_opening_contract() -> void:
	print("[opening: the GM guarantees run-1 — hot lead -> staged butcher -> harvest fork -> Heat reveal -> 2 follow-ups, reset per run (M8)]")
	var GM: Object = root.get_node_or_null("/root/GMOpening")
	_ok(GM != null, "GMOpening autoload is registered")
	if GM == null:
		return
	var RM: Object = root.get_node("/root/RunManager")
	var LS: Object = root.get_node("/root/LeadSystem")
	var AG: Object = root.get_node("/root/Agents")
	var EB: Object = root.get_node("/root/EventBus")
	var Mt: Object = root.get_node("/root/Meters")
	var RI: Object = root.get_node("/root/RoomItems")

	# (a) the hot butcher lead is guaranteed + surfaces promptly at run start.
	var surfaced := {"id": ""}
	var cb := func(lead_id: String): surfaced["id"] = lead_id
	LS.lead_surfaced.connect(cb)
	RM.start_run()
	LS.lead_surfaced.disconnect(cb)
	var b: Dictionary = GM.butcher_lead()
	_ok(String(b.get("id", "")) == "butcher_iron_cross" and bool(b.get("hot", false))
			and String(b.get("source", "")) == "constable_brom",
		"the guaranteed butcher lead is hot + sourced to constable_brom")
	_ok(surfaced["id"] == "butcher_iron_cross", "…and it surfaces promptly during start_run")

	# (b) the butcher is staged + reachable at the lead's where_hint (his Iron Cross shop).
	var staged: Dictionary = GM.butcher_staged_at()
	var kell: Agent = AG.get_agent("bram_kell")
	_ok(String(staged.get("agent", "")) == "bram_kell" and kell != null
			and kell.room == String(staged.get("room", "")) and kell.combat_form == "butcher_human",
		"bram_kell is staged in human form at the reachable Iron Cross shop")

	# (d) Heat hidden at open; a witnessed public kill reveals it (progressive disclosure flips).
	_ok(not Mt.is_revealed("heat"), "Heat starts hidden (Doom-only HUD at the opening)")
	AG.ensure_player_proxy(staged.get("position", Vector2.ZERO), String(staged.get("room", "")))
	var wit: Agent = AG.get_agent("constable_brom")
	wit.room = String(staged.get("room", "")); wit.position = staged.get("position", Vector2.ZERO)
	wit.vision_r = 600.0; wit.downed = false
	kell.downed = true
	EB.emit_event("agent_downed", {"actor": "player", "target": "bram_kell"})

	# (c) the harvest: an off-pathway tainted Characteristic drops + the fork + the same-pathway hint.
	_ok(int(RI.count(kell.room, "tainted_characteristic")) > 0,
		"the downed butcher drops an off-pathway tainted Characteristic (the harvest)")
	var fork: Dictionary = GM.on_butcher_downed()
	var opts: Array = fork.get("options", [])
	_ok(opts.has("digest") and opts.has("sell") and opts.has("keep"), "the harvest fork offers digest/sell/keep")
	_ok(not GM.hunter_pathway_lead().is_empty()
			and String(GM.hunter_pathway_lead().get("pathway", "")) == "hunter",
		"…and the same-pathway (hunter) follow-up lead is live (the 'he wasn't the only one' hint)")
	_ok(Mt.is_revealed("heat"), "the witnessed kill revealed the Heat meter (disclosure flipped)")

	# (e) >=2 follow-up leads live (one hunter-pathway, one cult).
	var follow: Array = GM.follow_up_leads()
	var has_hunter := false
	var has_cult := false
	for l in follow:
		if String(l.get("pathway", "")) == "hunter" or String(l.get("subject_key", "")) == "hunter":
			has_hunter = true
		if String(l.get("subject_key", "")) == "courier":
			has_cult = true
	_ok(follow.size() >= 2 and has_hunter and has_cult,
		"by the end of the opening beat >=2 follow-ups are live: a hunter-pathway hunt + a cult courier")

	# (f) a fresh run guarantees the opening AGAIN with no carry.
	RM.start_run()
	_ok(not GM.harvest_presented() and not AG.get_agent("bram_kell").downed
			and String(GM.butcher_lead().get("state", "")) == "open",
		"a fresh run scrubs the opening + re-guarantees it (butcher up, fork not presented, lead open)")

## M12 — the SECOND adversary (the Hunter-pathway prey, the first real hunt; direction v2 §3/§6). A
## smoke-level assertion in the main suite that the quarry the opening promises actually EXISTS as
## pure DATA and works through the built machinery: the hidden Beyonder loads with pathway:hunter + a
## two-phase combat_form (human -> a monster via a transform), the hunter_prey lead is a REAL
## destination (a where_hint + pathway:hunter routing to them), downing them drops hunter_characteristic
## through the PATHWAY-driven drop (NOT special-cased) enabling an advance, and the signature deed
## grants its suspicion clue to a watching proxy. The full harness lives in tests/test_adversary2.gd
## and the two-phase determinism fight is combat_sim scenario E.
func _test_adversary2_hunter_prey() -> void:
	print("[adversary2: the Hunter-pathway prey EXISTS — pathway:hunter + two-phase form, a real lead, a pathway-driven drop that arms the advance, a deed clue (M12)]")
	var ND: Object = root.get_node_or_null("/root/NpcDB")
	var DB: Object = root.get_node_or_null("/root/AbilityDB")
	var P: Object = root.get_node_or_null("/root/Progression")
	var LS: Object = root.get_node_or_null("/root/LeadSystem")
	var DR: Object = root.get_node_or_null("/root/DeedRunner")
	if ND == null or DB == null or P == null or LS == null or DR == null:
		_ok(false, "the M12 autoloads are registered")
		return
	var RM: Object = root.get_node("/root/RunManager")
	var AG: Object = root.get_node("/root/Agents")
	var EB: Object = root.get_node("/root/EventBus")
	var RI: Object = root.get_node("/root/RoomItems")
	RM.start_run()
	AG.rebuild()

	# (a) the hidden Beyonder loads with pathway:hunter + a two-phase combat_form.
	var def: Dictionary = ND.get_def("sable_wren")
	_ok(not def.is_empty() and String(def.get("pathway", "")) == "hunter"
			and String(def.get("combat_form", "")) == "wren_human",
		"sable_wren loads pathway:hunter, opening in the human phase-1 form wren_human")
	var human_transforms := false
	for aid in DB.kit_for("wren_human"):
		var a: Dictionary = DB.ability_for(String(aid))
		if String(a.get("class", "")) == "transform":
			for eff in (a.get("effects", []) as Array):
				if String((eff as Dictionary).get("form", "")) == "wren_predator":
					human_transforms = true
	_ok(human_transforms and DB.is_monster_form("wren_predator"),
		"the human form transforms into the wren_predator MONSTER form (two-phase, the assume_form seam)")
	# The monster kit is DISTINCT from the butcher's cleaver melee (a ranged blood-hunter).
	_ok(not (DB.kit_for("wren_predator") as Array).has("cleaver_swipe"),
		"the monster kit is distinct from the butcher's cleaver (a ranged blood-hunter, not a brawler)")

	# (b) the hunter_prey lead is a REAL destination: a where_hint + pathway:hunter.
	var lead: Dictionary = LS.get_lead("hunter_prey_kell_kin")
	_ok(not lead.is_empty() and String(lead.get("pathway", "")) == "hunter"
			and String(lead.get("where_hint", "")) != "",
		"the hunter_prey lead routes to a real place (a where_hint) with pathway:hunter")

	# (c) downing them drops hunter_characteristic via the PATHWAY-driven drop (not special-cased).
	_ok(P.drop_for_pathway("hunter") == "hunter_characteristic",
		"the drop is pathway-driven: drop_for_pathway('hunter') -> hunter_characteristic (no id branch)")
	var foe: Agent = AG.get_agent("sable_wren")
	_ok(foe != null and String(foe.pathway) == "hunter",
		"the live agent carries pathway:hunter (hydrated from data, not code)")
	if foe != null:
		foe.room = "suite_adv2_drop"
		foe.position = Vector2(120, 60)
		foe.downed = true
		RI.clear()
		EB.emit_event("agent_downed", {"actor": "player", "target": "sable_wren"})
		_ok(RI.count("suite_adv2_drop", "hunter_characteristic") >= 1,
			"downing the adversary drops a hunter_characteristic (the harvest -> the advance's fuel)")
		var proxy: Agent = AG.ensure_player_proxy(Vector2.ZERO, "suite_adv2_drop")
		proxy.add_item("hunter_characteristic", 1)
		P.mark_deed_done()
		_ok(bool(P.can_advance().get("ok", false)),
			"the harvested Characteristic + acting ritual arms an advance (the first real hunt pays off)")
		RI.clear()

	# (d) the signature deed grants its suspicion clue to a watching proxy near the site.
	var CD: Object = root.get_node("/root/ClueDB")
	var Clk: Object = root.get_node("/root/Clock")
	var deed: Dictionary = {}
	for d in DR.deeds:
		if String((d as Dictionary).get("id", "")) == "wren_blackthorn_stalk":
			deed = d
	_ok(not deed.is_empty() and String(deed.get("agent", "")) == "sable_wren"
			and String(deed.get("clue", "")) == "sable_wren_suspicious",
		"the deed wren_blackthorn_stalk is authored to the adversary, granting sable_wren_suspicious")
	if not deed.is_empty():
		var wp_v: Array = deed.get("waypoint", [])
		var wp := Vector2(float(wp_v[0]), float(wp_v[1]))
		var room := String(deed.get("room", "city"))
		var wf: Agent = AG.get_agent("sable_wren")
		wf.room = room; wf.position = wp; wf.downed = false; wf.vision_r = 600.0
		var proxy2: Agent = AG.ensure_player_proxy(wp, room)
		proxy2.vision_r = 600.0
		CD.from_dict({}); DR.reset()
		Clk.set_time(2, 1200)   # 20:00 — the deed's night phase
		Clk.minute_ticked.emit(Clk.minute_of_day, Clk.day)
		_ok(CD.is_collected("sable_wren_suspicious"),
			"the watching proxy earned sable_wren_suspicious from the deed near the site")
		CD.from_dict({})
	RI.clear()
	AG.rebuild()

## M7 Ritual Night — a smoke-level assertion in the main suite that the climax is a real, winnable
## encounter with NO softlock: Doom 100 / force-assault starts it, the fuse loses, the interrupt
## (altar or celebrant kill) wins via a backlash wave, the avatar half-lands + can be slain, and
## every outcome calls end_run exactly once. The full harness lives in tests/test_ritual_night.gd.
func _test_ritual_night_climax() -> void:
	print("[ritual night: the climax is a winnable encounter — trigger, fuse=lose, interrupt=win, avatar=win, NO softlock (M7)]")
	var RN: Object = root.get_node_or_null("/root/RitualNight")
	_ok(RN != null, "RitualNight autoload is registered")
	if RN == null:
		return
	var RM: Object = root.get_node("/root/RunManager")
	var AG: Object = root.get_node("/root/Agents")
	var M: Object = root.get_node("/root/Meters")
	var DB: Object = root.get_node("/root/AbilityDB")

	# Trigger: Doom 100 starts it; force-assault starts it early.
	RM.start_run(); AG.rebuild(); RN.reset()
	M.set_meter("doom", 100.0)
	_ok(RN.active(), "Doom 100 starts Ritual Night")
	RM.start_run(); AG.rebuild(); RN.reset()
	RN.force_assault(true, 4242)
	_ok(RN.active(), "a force-assault starts Ritual Night")

	# Lose-by-fuse: an un-interrupted fuse reaches zero -> end_run('lose') once.
	RM.start_run(); AG.rebuild(); RN.reset()
	RN.force_assault(false, 4242)
	var lose := {"n": 0, "reason": ""}
	var lcb := func(reason: String) -> void:
		lose["n"] = int(lose["n"]) + 1
		lose["reason"] = reason
	RM.run_ended.connect(lcb)
	RN.tick_fuse(9999)
	RN.tick_fuse(9999)   # redundant late tick must not re-end
	RM.run_ended.disconnect(lcb)
	_ok(int(lose["n"]) == 1 and lose["reason"] == "lose", "the fuse runs out -> end_run('lose') exactly once (no softlock)")
	_ok(String(RN.result().get("outcome", "")) == "descent_complete", "a lose records descent_complete")

	# Win-by-interrupt: altar interactable -> backlash wave (celebrants assume_form) -> clear -> win.
	RM.start_run(); AG.rebuild(); RN.reset()
	RN.force_assault(false, 4242)
	var win := {"reason": ""}
	var wcb := func(reason: String) -> void: win["reason"] = reason
	RM.run_ended.connect(wcb)
	RN.use_interrupt_interactable()
	_ok(RN.interrupted() and RN.backlash_active(), "the altar interactable interrupts + spawns the backlash wave")
	var mons: Array = RN.backlash_monsters()
	var any_monster := false
	for id in mons:
		var a: Agent = AG.get_agent(id)
		if a != null and DB.is_monster_form(a.combat_form):
			any_monster = true
	_ok(mons.size() >= 1 and any_monster, "surviving celebrants LOSE CONTROL -> assume_form into monsters (canon §⑦)")
	RN.clear_backlash_wave()
	RM.run_ended.disconnect(wcb)
	_ok(win["reason"] == "win" and String(RN.result().get("outcome", "")) == "descent_stopped",
		"surviving the backlash -> end_run('win') + descent_stopped")

	# Win-by-avatar: the avatar half-lands past the low-fuse threshold; killing it wins.
	RM.start_run(); AG.rebuild(); RN.reset()
	RN.force_assault(false, 4242)
	RN.tick_fuse(RN.fuse_remaining() - RN.avatar_threshold() + 1)
	_ok(RN.avatar_present(), "crossing the low-fuse threshold half-lands the avatar")
	var av: Agent = AG.get_agent(RN.avatar_id())
	_ok(av != null and DB.is_monster_form(av.combat_form), "the avatar wears the descended_avatar monster form")
	var avwin := {"reason": ""}
	var acb := func(reason: String) -> void: avwin["reason"] = reason
	RM.run_ended.connect(acb)
	if av != null:
		av.take_damage(av.hp + 10.0)
		RN.notify_agent_downed(av.id)
	RM.run_ended.disconnect(acb)
	_ok(avwin["reason"] == "win" and String(RN.result().get("outcome", "")) == "avatar_slain",
		"killing the half-landed avatar -> end_run('win') + avatar_slain")

	# Determinism: a fixed seed yields the same which-door/relocation setup.
	RM.start_run(); AG.rebuild(); RN.reset(); RN.set_tipped(true); RN.force_assault(true, 4242)
	var sig_a := "%s|%d" % [RN.site_room(), RN.defender_count()]
	RM.start_run(); AG.rebuild(); RN.reset(); RN.set_tipped(true); RN.force_assault(true, 4242)
	var sig_b := "%s|%d" % [RN.site_room(), RN.defender_count()]
	_ok(sig_a == sig_b, "a fixed run-seed yields an identical climax setup (determinism)")

	# Leave the world clean for any later suite steps.
	RM.start_run(); AG.rebuild(); RN.reset()

## M27 meta payoff — a smoke-level assertion in the main suite that a run END now WRITES the persistent
## meta (the roguelite's reason to replay): the codex grows on a win, the first win unlocks the Fool
## pathway (a loss does not), the run-start pathway pick READS that unlock, and the two wins pay UNEQUAL
## meta-currency (avatar_slain > descent_stopped). The full harness lives in tests/test_meta_payoff.gd.
func _test_meta_payoff() -> void:
	print("[meta payoff: a run end writes codex + Fool-unlock + differential currency (M27)]")
	var RM: Object = root.get_node("/root/RunManager")
	var AG: Object = root.get_node("/root/Agents")
	var RN: Object = root.get_node_or_null("/root/RitualNight")
	var P: Object = root.get_node("/root/Progression")
	var EG: Object = root.get_node_or_null("/root/EndGame")
	if RN == null:
		_ok(false, "RitualNight autoload is registered (meta payoff needs the climax)")
		return

	# A LOSS writes the codex but unlocks nothing.
	RM.reset_meta()
	RM.start_run(); AG.rebuild(); RN.reset()
	if EG != null and EG.has_method("rearm"): EG.rearm()
	RN.force_assault(false, 4242)
	RN.tick_fuse(9999)   # descent_complete -> lose
	_ok(RM.meta_codex().size() > 0, "a run end WRITES codex entries (was: meta unchanged)")
	_ok(not RM.meta_unlocked_pathways().has("hermit"), "a LOSING run does not unlock Hermit")
	_ok(int(RM.meta_currency()) == 0, "a LOSE pays no meta-currency")

	# The pick reads the (still-locked) unlock: Hunter always, Hermit not yet (M28 retargeted the first-win
	# unlock from the Fool STUB to the real Hermit build).
	_ok(P.available_pathways().has("hunter") and not P.available_pathways().has("hermit"),
		"the pathway pick reads the meta: Hunter available, Hermit locked")

	# The first WIN (Quiet Win = descent_stopped) unlocks Hermit + pays currency.
	RM.start_run(); AG.rebuild(); RN.reset()
	if EG != null and EG.has_method("rearm"): EG.rearm()
	RN.force_assault(false, 4242)
	RN.use_interrupt_interactable()
	RN.clear_backlash_wave()   # descent_stopped -> win
	_ok(RM.meta_unlocked_pathways().has("hermit"), "the first WIN unlocks the Hermit pathway")
	var quiet := int(RM.meta_currency())
	_ok(quiet > 0, "the Quiet Win pays meta-currency (%d)" % quiet)
	# The pick now honors the unlock (and persists across a reload of the meta slot).
	RM.reload_meta()
	_ok(P.select_pathway("hermit") == "hermit", "the run-start pick now honors the Hermit unlock (persisted)")
	P.select_pathway("hunter")

	# The Deep Win (avatar_slain) pays MORE than the Quiet Win — the differential.
	RM.reset_meta()
	RM.start_run(); AG.rebuild(); RN.reset()
	if EG != null and EG.has_method("rearm"): EG.rearm()
	RN.force_assault(false, 4242)
	RN.tick_fuse(RN.fuse_remaining() - RN.avatar_threshold() + 1)
	var av: Agent = AG.get_agent(RN.avatar_id())
	if av != null:
		av.take_damage(av.hp + 10.0)
		RN.notify_agent_downed(av.id)   # avatar_slain -> win
	_ok(int(RM.meta_currency()) > quiet, "the Deep Win (avatar_slain) pays MORE than the Quiet Win (%d > %d)" % [int(RM.meta_currency()), quiet])

	# Restore a clean profile + world for later suite steps.
	RM.reset_meta()
	RM.start_run(); AG.rebuild(); RN.reset()

# --- B3 (retro): meta-profile isolation + the live meta SURFACE --------------------------------
## The suite runs entirely on the redirected test slot (see _init). This sentinel test stages a fake
## REAL profile, drives every meta-WRITING seam the tests use, and proves the real user://meta.json
## survives byte-identical (standalone twin: tests/test_meta_isolation.gd). RED before
## RunManager.meta_path existed — reset_meta()/end_run() used to wipe the player's actual profile.
func _test_meta_profile_isolation() -> void:
	print("[meta isolation: the suite never reads or wipes the REAL user profile (B3)]")
	var RM: Object = root.get_node("/root/RunManager")
	var AG: Object = root.get_node("/root/Agents")
	var RN: Object = root.get_node_or_null("/root/RitualNight")
	var real_path := String(RM.META_PATH)
	_ok(String(RM.meta_path) != real_path, "the suite runs on a redirected meta slot (never the real profile)")
	# Stage a sentinel AS the real profile (backing up any true bytes), drive the seams, compare.
	var had := FileAccess.file_exists(real_path)
	var backup := FileAccess.get_file_as_string(real_path) if had else ""
	var sentinel := "{\"version\": 1, \"runs_played\": 777, \"sentinel\": \"real-player-profile\"}"
	var fw := FileAccess.open(real_path, FileAccess.WRITE)
	fw.store_string(sentinel)
	fw.close()
	RM.reset_meta()                                        # the test-profile wipe
	RM.start_run()                                         # _bump_meta_runs -> _save_meta
	RM.end_run("lose", {"outcome": "descent_complete"})    # _flush_meta_on_run_end -> _save_meta
	RM.reload_meta()                                       # the re-READ seam
	var reads_ok := int(RM.meta_runs_played()) != 777
	var real_after := FileAccess.get_file_as_string(real_path) if FileAccess.file_exists(real_path) else ""
	# Restore the machine's true profile BEFORE asserting, then leave a clean world for later tests.
	if had:
		var fr := FileAccess.open(real_path, FileAccess.WRITE)
		fr.store_string(backup)
		fr.close()
	else:
		DirAccess.remove_absolute(ProjectSettings.globalize_path(real_path))
	_ok(reads_ok, "meta READS come from the test slot (not the sentinel's runs_played=777)")
	_ok(real_after == sentinel, "reset_meta/start_run/end_run leave the REAL profile byte-identical")
	RM.reset_meta()
	RM.start_run(); AG.rebuild()
	if RN != null:
		RN.reset()

## The end-of-suite guard (registered LAST): after EVERY test above ran, the REAL user profile is
## exactly as it was when the suite booted — identical bytes, or still absent. Any future test that
## forgets the redirect (or writes META_PATH directly) turns this RED.
func _test_real_meta_untouched() -> void:
	print("[meta isolation: end-of-suite — the real user profile is untouched (B3)]")
	var RM: Object = root.get_node("/root/RunManager")
	var real_path := String(RM.META_PATH)
	var exists := FileAccess.file_exists(real_path)
	var bytes_now := FileAccess.get_file_as_string(real_path) if exists else ""
	_ok(exists == _real_meta_existed, "the suite neither created nor deleted the real user://meta.json")
	_ok(bytes_now == _real_meta_before, "the real user://meta.json is byte-identical to its pre-suite bytes")

## B3: the meta-surface VIEW-MODEL builder (src/MetaSurface.gd) is pure + headless-testable — staged
## meta state in, display lines out. No autoload reads, no scene work. RED before the builder existed.
func _test_meta_surface_builder() -> void:
	print("[meta surface: pure view-model builder (B3)]")
	var MS = load("res://src/MetaSurface.gd")
	_ok(MS != null, "src/MetaSurface.gd exists (the view-model builder)")
	if MS == null:
		return
	# TITLE model: a staged profile -> header/summary/codex lines.
	var codex := [
		{"id": "ending:descent_stopped", "learned": "You broke a summoning rite at the altar."},
		{"id": "adversary:butcher_human", "learned": "You faced and put down a Beyonder in the Butcher shape."},
	]
	var vm: Dictionary = MS.title_model(7, 4, ["hermit"], codex)
	_ok(String(vm.get("summary", "")).find("7") >= 0, "the title summary carries the currency total")
	_ok(String(vm.get("summary", "")).find("4") >= 0, "the title summary carries the runs played")
	_ok(String(vm.get("summary", "")).find("Hermit") >= 0, "the title summary names the earned pathway")
	var lines: Array = vm.get("codex_lines", [])
	_ok(lines.size() == 2, "the codex block lists each learned entry")
	_ok(lines.size() > 0 and String(lines[0]).find("Butcher") >= 0,
		"codex lines surface the LEARNED copy, newest first")
	# Empty profile -> explicit empty state (the panel still renders honestly).
	var vm0: Dictionary = MS.title_model(0, 0, [], [])
	_ok((vm0.get("codex_lines", []) as Array).is_empty() and String(vm0.get("empty_line", "")) != "",
		"an empty profile yields no codex lines and an explicit empty-state line")
	# Cap: a long codex folds older entries so the title panel stays modest.
	var big: Array = []
	for i in range(9):
		big.append({"id": "adversary:form_%d" % i, "learned": "Learned line %d." % i})
	var vmb: Dictionary = MS.title_model(1, 1, [], big)
	_ok((vmb.get("codex_lines", []) as Array).size() == int(MS.MAX_TITLE_CODEX_LINES),
		"a long codex is capped to MAX_TITLE_CODEX_LINES on the title panel")
	_ok(String(vmb.get("codex_more", "")).find("3") >= 0, "the cap discloses how many older entries are folded")
	# PAYOFF model: the run's recorded meta delta -> the EndGame lines.
	var pay: Dictionary = MS.payoff_model({"outcome": "descent_stopped", "currency_delta": 1,
		"currency_total": 8, "new_unlocks": ["hermit"],
		"new_codex": [{"id": "ending:descent_stopped", "learned": "You broke a summoning rite at the altar."}]})
	var joined := "\n".join(PackedStringArray(pay.get("lines", [])))
	_ok(joined.find("+1") >= 0, "the payoff lines carry the currency DELTA (+1)")
	_ok(joined.find("8") >= 0, "the payoff lines carry the new currency total")
	_ok(joined.find("Hermit") >= 0, "the payoff lines announce the new pathway unlock")
	_ok(joined.find("altar") >= 0, "the payoff lines quote the new codex learning")
	_ok((MS.payoff_model({}) as Dictionary).is_empty(), "no payoff recorded -> an empty model (nothing renders)")
	# A zero-pay LOSE still yields an honest model (no fake '+' payout line).
	var lose: Dictionary = MS.payoff_model({"outcome": "descent_complete", "currency_delta": 0,
		"currency_total": 8, "new_unlocks": [], "new_codex": []})
	_ok(not lose.is_empty() and "\n".join(PackedStringArray(lose.get("lines", []))).find("+") < 0,
		"a zero-pay lose renders without a fake '+' payout line")

## B3 LIVE REACHABILITY: the TITLE screen mounts a ledger panel that reads the RunManager meta
## getters through the builder. Stages a profile in the redirected slot, mounts the REAL
## BootController (the title raiser), and asserts the panel + its lines. Fails if the wire is removed.
func _test_meta_surface_title_wire() -> void:
	print("[meta surface: the TITLE screen wires the ledger panel (B3)]")
	var RM: Object = root.get_node("/root/RunManager")
	var staged := {"version": 1, "runs_played": 4, "unlocked_pathways": ["hermit"],
		"codex": [{"id": "ending:descent_stopped", "learned": "You broke a summoning rite at the altar."}],
		"meta_currency": 7}
	var f := FileAccess.open(String(RM.meta_path), FileAccess.WRITE)
	f.store_string(JSON.stringify(staged))
	f.close()
	RM.reload_meta()
	var boot: Node = (load("res://src/BootController.gd") as GDScript).new()
	root.add_child(boot)
	await process_frame
	var panel: Node = boot.get_node_or_null("Title/MetaCodexPanel")
	_ok(panel != null, "the title mounts the MetaCodexPanel (fails if the wire is removed)")
	if panel != null:
		var summary: Label = panel.get_node_or_null("Ledger/Summary")
		_ok(summary != null and summary.text.find("7") >= 0,
			"the panel READS RunManager.meta_currency() (shows the staged 7)")
		_ok(summary != null and summary.text.find("Hermit") >= 0,
			"the panel shows the earned pathway from meta_unlocked_pathways()")
		var lines_box: Node = panel.get_node_or_null("Ledger/CodexLines")
		var has_line := false
		if lines_box != null:
			for c in lines_box.get_children():
				if c is Label and (c as Label).text.find("altar") >= 0:
					has_line = true
		_ok(has_line, "the panel lists the codex learned line from meta_codex()")
	boot.queue_free()
	await process_frame
	RM.reset_meta()

## B3 LIVE REACHABILITY: a real Ritual-Night WIN raises the EndGame screen WITH the run's meta
## payoff (currency delta + first-win unlock + new codex lines) once the meta flush lands, and the
## EndGame overlay draws ABOVE the just-raised title so the payoff is actually visible live.
func _test_meta_surface_endgame_payoff() -> void:
	print("[meta surface: the EndGame screen shows the run payoff (B3)]")
	var RM: Object = root.get_node("/root/RunManager")
	var AG: Object = root.get_node("/root/Agents")
	var RN: Object = root.get_node_or_null("/root/RitualNight")
	var EG: Object = root.get_node_or_null("/root/EndGame")
	if RN == null or EG == null:
		_ok(false, "RitualNight + EndGame autoloads are registered")
		return
	RM.reset_meta()
	RM.start_run(); AG.rebuild(); RN.reset()
	if EG.has_method("rearm"):
		EG.rearm()
	RN.force_assault(false, 4242)
	RN.use_interrupt_interactable()
	RN.clear_backlash_wave()   # descent_stopped -> WIN: overlay + meta flush + payoff section
	_ok(bool(EG.has_overlay()), "the win raises the EndGame overlay")
	_ok(int((EG as CanvasLayer).layer) > 10,
		"the EndGame overlay draws ABOVE the just-raised title layer (payoff visible live)")
	var payoff: Node = (EG as Node).find_child("RunPayoff", true, false)
	_ok(payoff != null, "the EndGame screen mounts the RunPayoff section (fails if the wire is removed)")
	if payoff != null:
		var text := ""
		for c in payoff.get_children():
			if c is Label:
				text += (c as Label).text + "\n"
		_ok(text.find("+1") >= 0, "the payoff shows the Quiet Win's +1 currency delta")
		_ok(text.find("Hermit") >= 0, "the payoff announces the first-win Hermit unlock")
		_ok(text.find("altar") >= 0, "the payoff quotes a new codex learned line (from data/scenario.json)")
	if EG.has_method("dismiss"):
		EG.dismiss()
	RM.reset_meta()
	RM.start_run(); AG.rebuild(); RN.reset()

# --- M10 polish: pause menu, settings, HUD legend, spark_burst VFX fix -------------------------
## (b) Every settings toggle PERSISTS (save->reload) and TAKES EFFECT (palette swap, text scale,
## audio bus). Cosmetic/accessibility only — never touches combat.
func _test_polish_settings() -> void:
	print("[polish: settings persist + take effect (M10)]")
	var S: Object = root.get_node_or_null("/root/Settings")
	_ok(S != null, "Settings autoload is registered")
	if S == null:
		return
	S.reset_defaults()
	_ok(S.get_bool("screen_shake") and S.get_bool("hit_flash"), "cosmetic feedback defaults ON")
	_ok(not S.get_bool("colorblind"), "colorblind defaults OFF")
	_ok(abs(S.get_number("text_scale") - 1.0) < 0.001, "text_scale defaults to 1.0")
	# TAKES EFFECT: text scale.
	var probe := Label.new()
	root.add_child(probe)
	S.set_value("text_scale", 1.5)
	S.apply_text_scale(probe, 20)
	_ok(probe.get_theme_font_size("font_size") == 30, "text_scale 1.5 scales a 20px probe to 30px")
	probe.queue_free()
	# TAKES EFFECT: colorblind swaps the palette constant.
	S.set_value("colorblind", false)
	var normal: Color = S.meter_color("doom")
	S.set_value("colorblind", true)
	var cb: Color = S.meter_color("doom")
	_ok(cb != normal, "colorblind ON swaps the doom meter color (safe palette)")
	# TAKES EFFECT: master volume drives the Master bus, mutes at 0.
	var bus := AudioServer.get_bus_index("Master")
	S.set_value("master_volume", 0.0)
	_ok(AudioServer.is_bus_mute(bus), "master_volume 0 mutes the Master bus")
	S.set_value("master_volume", 1.0)
	_ok(not AudioServer.is_bus_mute(bus), "master_volume 1 unmutes the Master bus")
	# PERSISTS: save -> reset -> reload.
	S.reset_defaults()
	S.set_value("screen_shake", false)
	S.set_value("colorblind", true)
	S.set_value("text_scale", 1.25)
	var tmp := "user://test_polish_settings.json"
	_ok(S.save_to(tmp), "settings save writes a file")
	S.reset_defaults()
	_ok(S.get_bool("screen_shake"), "reset restored the default before reload")
	_ok(S.load_from(tmp), "settings load reads the file")
	_ok(not S.get_bool("screen_shake"), "screen_shake persisted OFF across reload")
	_ok(S.get_bool("colorblind"), "colorblind persisted ON across reload")
	_ok(abs(S.get_number("text_scale") - 1.25) < 0.001, "text_scale persisted across reload")
	DirAccess.remove_absolute(ProjectSettings.globalize_path(tmp))
	S.reset_defaults()

## (b) The screen-shake / hit-flash toggles GATE the cosmetic helper — off = a verified no-op.
func _test_polish_combat_feedback_gates() -> void:
	print("[polish: shake/hit-flash toggles gate the cosmetic helper (M10)]")
	var S: Object = root.get_node_or_null("/root/Settings")
	var FB: Object = root.get_node_or_null("/root/CombatFeedback")
	_ok(FB != null, "CombatFeedback autoload is registered")
	if FB == null or S == null:
		return
	S.reset_defaults()
	S.set_value("screen_shake", true)
	FB.reset_probe(); FB.shake(8.0)
	_ok(FB.last_shake_amplitude() > 0.0, "shake ON -> the shake helper produces amplitude")
	S.set_value("screen_shake", false)
	FB.reset_probe(); FB.shake(8.0)
	_ok(FB.last_shake_amplitude() == 0.0, "shake OFF -> the shake helper is a NO-OP (not dead UI)")
	S.set_value("hit_flash", true)
	FB.reset_probe(); FB.flash()
	_ok(FB.last_flash_alpha() > 0.0, "hit_flash ON -> the flash helper produces a flash")
	S.set_value("hit_flash", false)
	FB.reset_probe(); FB.flash()
	_ok(FB.last_flash_alpha() == 0.0, "hit_flash OFF -> the flash helper is a NO-OP")
	S.reset_defaults()

## (a) The pause action pauses the tree + shows the menu; resume unpauses; quit-to-title ends the
## run + returns to title (no softlock, meta preserved); pause is INERT during an ending / at boot.
func _test_polish_pause_menu() -> void:
	print("[polish: pause menu pauses/resumes + quit-to-title + inert guards (M10)]")
	var RM: Object = root.get_node("/root/RunManager")
	var EG: Object = root.get_node("/root/EndGame")
	var PM: Object = root.get_node_or_null("/root/PauseMenu")
	_ok(PM != null, "PauseMenu autoload is registered")
	if PM == null:
		return
	# Clear any ending overlay a prior suite step (endgame tests) may have left mounted — else the
	# pause menu's INERT-during-ending guard would (correctly) refuse to open here.
	if EG.has_method("dismiss"):
		EG.dismiss()
	if EG.has_method("rearm"):
		EG.rearm()
	paused = false
	var boot: Node = (load("res://src/BootController.gd") as GDScript).new()
	root.add_child(boot)
	await process_frame
	boot.start_new_run()
	await process_frame
	_ok(RM.run_active(), "a run is active after start_new_run")
	_ok(not EG.has_overlay(), "no ending overlay is up (pause is eligible)")
	var runs_before := int(RM.meta_runs_played())
	# Pause / resume.
	paused = false
	PM.open()
	_ok(paused and PM.is_open(), "open() pauses the tree + shows the menu")
	PM.resume()
	_ok(not paused and not PM.is_open(), "resume() unpauses + hides the menu")
	# Quit to title.
	PM.open()
	PM.quit_to_title()
	_ok(not paused and not PM.is_open(), "quit_to_title lifts the pause + closes the menu (no softlock)")
	_ok(not RM.run_active(), "quit_to_title ends the active run")
	_ok(boot.has_method("is_at_title") and boot.is_at_title(), "quit_to_title returns to the title")
	_ok(int(RM.meta_runs_played()) >= runs_before, "meta (runs_played) preserved across quit-to-title")
	# Inert during an ending.
	boot.start_new_run()
	await process_frame
	EG.player_downed()
	_ok(paused, "an ending pauses the tree")
	PM.open()
	_ok(not PM.is_open(), "pause is INERT while an ending overlay is up")
	EG.dismiss()
	paused = false
	if EG.has_method("rearm"):
		EG.rearm()
	# Inert at the title (no active run).
	RM.end_run("win")
	await process_frame
	PM.open()
	_ok(not PM.is_open(), "pause is INERT at the title / boot (no run to pause)")

	# Review finding #1 (regression): Escape with a panel open must close the PANEL, not stack pause
	# on top. Correctness rests on _unhandled_input tree ordering + each panel's set_input_as_handled().
	# Inject a REAL Escape event with an open, active-run panel mounted and assert pause stays CLOSED.
	# (A future panel that forgets set_input_as_handled(), or a reparent moving PauseMenu deeper, would
	# fail this and let pause stack over the panel — the exact gap the review flagged as untested.)
	boot.start_new_run()
	await process_frame
	PM.resume()   # ensure a clean state (unpaused, closed) before the injection
	paused = false
	var panel := _PolishEscPanel.new()   # a real-pattern ui_cancel panel (consumes Escape when visible)
	root.add_child(panel)   # added after the PauseMenu autoload => deeper in _unhandled_input order
	panel.visible = true
	await process_frame
	var esc := InputEventKey.new()
	esc.keycode = KEY_ESCAPE
	esc.physical_keycode = KEY_ESCAPE
	esc.pressed = true
	Input.parse_input_event(esc)
	await process_frame
	await process_frame
	_ok(panel.consumed_escape, "the open panel actually saw + consumed the Escape event")
	_ok(not PM.is_open(), "Escape with a panel open closes the panel, NOT opens pause on top (no stacking)")
	_ok(not panel.visible, "the panel closed on Escape (ui_cancel path intact)")
	panel.free()
	RM.end_run("win")
	await process_frame

	boot.free()
	await process_frame

## (c) The HUD legend opens/closes and explains the four meters + the combat readout.
func _test_polish_hud_legend() -> void:
	print("[polish: HUD legend opens/closes + explains the meters/readout (M10)]")
	var HL: Object = (load("res://src/HudLegend.gd") as GDScript).new()
	root.add_child(HL)
	await process_frame
	_ok(not HL.is_open(), "the legend starts closed (unobtrusive)")
	HL.toggle()
	_ok(HL.is_open(), "toggle opens the legend")
	var body := String(HL.legend_text()).to_lower()
	for token in ["doom", "madness", "notice", "heat", "ammo", "cooldown", "telegraph"]:
		_ok(token in body, "the legend explains '%s'" % token)
	HL.toggle()
	_ok(not HL.is_open(), "toggle again closes the legend")
	HL.free()

## (d) The spark_burst FX now resolves to a non-boxy visual: an alpha-keyed cutout + the animated
## form (not the raw 1024^2 sheet drawn whole).
func _test_polish_spark_burst_fix() -> void:
	print("[polish: spark_burst FX is animated/keyed, not a boxy black panel (M10)]")
	var keyed := "res://assets/fx/flipbooks/spark_burst_keyed.png"
	_ok(ResourceLoader.exists(keyed), "an alpha-keyed spark_burst cutout exists on disk")
	if ResourceLoader.exists(keyed):
		var img := (load(keyed) as Texture2D).get_image()
		_ok(img.detect_alpha() != Image.ALPHA_NONE, "the keyed sheet has transparency (not an opaque box)")
		_ok(img.get_pixel(1, 1).a < 0.1, "the black background is keyed to transparent at the corner")
	var FX: Object = root.get_node_or_null("/root/CombatFx")
	_ok(FX != null and FX.has_method("spark_burst_is_animated"), "CombatFx exposes the spark_burst seam")
	if FX != null and FX.has_method("spark_burst_is_animated"):
		_ok(FX.spark_burst_is_animated(), "the transform burst uses the animated/keyed form (not the raw sheet)")
	# The SpriteFrames builder yields the flipbook frames (a real animation, not one whole-sheet frame).
	var frames := CombatFxLib.spark_burst_frames()
	_ok(frames != null and frames.get_frame_count("default") > 1,
		"the spark_burst SpriteFrames has multiple frames (per-frame burst, not a single boxy frame)")
	# Review finding #2: prove the SPAWNED node is genuinely an AnimatedSprite2D (is-using, not
	# would-use). Spawn a real transform burst and assert its concrete type + a multi-frame flipbook.
	if FX != null and FX.has_method("spawn_spark_burst_probe"):
		var burst_node: Node = FX.spawn_spark_burst_probe()
		_ok(burst_node is AnimatedSprite2D,
			"the SPAWNED transform burst is a real AnimatedSprite2D (not the raw sheet Sprite2D)")
		if burst_node is AnimatedSprite2D:
			var sf := (burst_node as AnimatedSprite2D).sprite_frames
			_ok(sf != null and sf.get_frame_count("default") > 1,
				"the spawned burst node carries the multi-frame flipbook (real per-frame animation)")
		if FX.has_method("clear_transients"):
			FX.clear_transients()

## (e) Determinism preserved: the M10 spark_burst change keeps the FX-on-vs-off transcript identical.
func _test_polish_combat_fx_determinism_still_holds() -> void:
	print("[polish: spark_burst change keeps the FX on/off transcript identical (M10)]")
	var with_fx := await _run_fx_fight(true)
	var no_fx := await _run_fx_fight(false)
	_ok(with_fx == no_fx and not with_fx.is_empty(),
		"the combat event transcript is byte-identical with FX on vs off (M10 change is cosmetic)")

## M11 the meters get TEETH — a smoke-level assertion in the main suite that high Notice spawns a
## beyond_hunter engaging the player, high Heat spawns a nighthawk_pursuer, the spawns are capped +
## clear on run reset, and an idle run's passive Doom fill reaches 100 by ~day 6-7. The full harness
## (respawn/decay lifecycle, live-combat engagement, determinism) lives in tests/test_meter_teeth.gd.
func _test_meter_teeth_spawns_and_doom_fill() -> void:
	print("[teeth: Notice->beyond_hunter, Heat->nighthawk (in combat vs player), capped, reset-clean; idle Doom fills to 100 (M11)]")
	var MT: Object = root.get_node_or_null("/root/MeterThreats")
	_ok(MT != null, "MeterThreats autoload is registered")
	if MT == null:
		return
	var M: Object = root.get_node("/root/Meters")
	var RM: Object = root.get_node("/root/RunManager")
	var AG: Object = root.get_node("/root/Agents")
	var CL: Object = root.get_node("/root/Clock")
	var DB: Object = root.get_node("/root/AbilityDB")
	# The two forms load with valid, monster-vs-official flags.
	_ok(DB.is_monster_form("beyond_hunter") and not DB.is_monster_form("nighthawk_pursuer"),
		"beyond_hunter is a monster form, nighthawk_pursuer is a human official")
	RM.start_run()
	AG.rebuild()
	AG.ensure_player_proxy(Vector2(300, 300), "suite_teeth")
	MT.spawn_room = "suite_teeth"
	MT.spawn_pos = Vector2(340, 300)
	# Notice crossing the high rung dispatches exactly one beyond_hunter, in combat, engaging player.
	M.set_meter("notice", 0.0)
	M.set_meter("notice", 90.0)
	var hunter: Agent = null
	for a in AG.all():
		if a != null and a.combat_form == "beyond_hunter" and not a.downed:
			hunter = a
	_ok(hunter != null and hunter.in_combat
		and String(hunter.combat_intent.get("target", "")) == "player",
		"high Notice spawns a beyond_hunter in combat engaging the player")
	# Heat crossing dispatches a nighthawk.
	M.set_meter("heat", 0.0)
	M.set_meter("heat", 90.0)
	var hawk_present := false
	for a in AG.all():
		if a != null and a.combat_form == "nighthawk_pursuer" and not a.downed:
			hawk_present = true
	_ok(hawk_present, "high Heat spawns a nighthawk_pursuer")
	# A fresh run scrubs both threats (no cross-run leak).
	RM.start_run()
	AG.rebuild()
	var leaked := false
	for a in AG.all():
		if a != null and (a.combat_form == "beyond_hunter" or a.combat_form == "nighthawk_pursuer"):
			leaked = true
	_ok(not leaked and not MT.has_active_threat("notice") and not MT.has_active_threat("heat"),
		"a fresh run has no leaked hunter/nighthawk (spawns clear on reset)")
	# An idle run's passive Doom fill reaches 100 within the 7-day run (time + phase pacing, §4).
	# M26 RETUNE #2 (known-gate fix): the roster's 3 hidden-Beyonder NPCs are LIVE from run start, but the
	# Doom monster driver counts a hidden Beyonder ONLY once its lead is KNOWN. To isolate the PURE PASSIVE
	# pacer on the REAL live roster (no downing fiction), stage an UN-SURFACED idle run via LeadSystem's
	# public debug seam (retro B4: no reaching into `_leads` internals) — the live Beyonders stay
	# uncounted because the gate holds them. (The known-gate itself is covered in test_balance.gd.)
	var _bls: Object = root.get_node_or_null("/root/LeadSystem")
	if _bls != null:
		_bls.debug_set_all_known(false)
	M.set_meter("doom", M.run_start("doom"))
	CL.set_time(1, 480)
	var reached := 0
	for _i in range(7 * 1440):
		CL.advance_minutes(1)
		if M.get_meter("doom") >= 100.0:
			reached = CL.day
			break
	_ok(reached >= 6 and reached <= 7, "an idle run's passive Doom fill reaches 100 on day %d (~6-7)" % reached)
	RM.start_run()
	AG.rebuild()

# ─────────────────────────────────────────────────────────────────────────────
# M14: 3rd adversary — the Seq-8 hunter's meal (inline smoke; full harness: tests/test_adversary3.gd)
# ─────────────────────────────────────────────────────────────────────────────

func _test_adversary3_mack_docks() -> void:
	print("[adversary3: the Seq-8 hunter's meal EXISTS — pathway:hunter + two-phase form, an after_advance lead, a pathway-driven drop + post-advance gate (M14)]")
	var ND: Object = root.get_node_or_null("/root/NpcDB")
	var DB: Object = root.get_node_or_null("/root/AbilityDB")
	var P: Object = root.get_node_or_null("/root/Progression")
	var LS: Object = root.get_node_or_null("/root/LeadSystem")
	var DR: Object = root.get_node_or_null("/root/DeedRunner")
	if ND == null or DB == null or P == null or LS == null or DR == null:
		_ok(false, "the M14 autoloads are registered")
		return
	var RM: Object = root.get_node("/root/RunManager")
	var AG: Object = root.get_node("/root/Agents")
	var EB: Object = root.get_node("/root/EventBus")
	var RI: Object = root.get_node("/root/RoomItems")
	RM.start_run()
	AG.rebuild()

	# (a) the harbour beast loads with pathway:hunter + a two-phase combat_form.
	var def: Dictionary = ND.get_def("leland_mack")
	_ok(not def.is_empty() and String(def.get("pathway", "")) == "hunter"
			and String(def.get("combat_form", "")) == "mack_harbor",
		"leland_mack loads pathway:hunter, opening in the human phase-1 form mack_harbor")
	var human_transforms := false
	for aid in DB.kit_for("mack_harbor"):
		var a: Dictionary = DB.ability_for(String(aid))
		if String(a.get("class", "")) == "transform":
			for eff in (a.get("effects", []) as Array):
				if String((eff as Dictionary).get("form", "")) == "mack_beast":
					human_transforms = true
	_ok(human_transforms and DB.is_monster_form("mack_beast"),
		"the human form transforms into the mack_beast MONSTER form (two-phase, the assume_form seam)")
	# The monster kit is DISTINCT from butcher (no cleaver_swipe) and Wren (no incendiary_round).
	var mon_kit: Array = DB.kit_for("mack_beast")
	_ok(not mon_kit.has("cleaver_swipe") and not mon_kit.has("incendiary_round"),
		"the monster kit is distinct from both the butcher (no cleaver_swipe) and Wren (no incendiary_round)")

	# (b) the Mack lead is tagged after_advance:true and is NOT the opener.
	var lead: Dictionary = LS.get_lead("hunter_prey_mack_docks")
	_ok(not lead.is_empty() and String(lead.get("pathway", "")) == "hunter"
			and String(lead.get("where_hint", "")) != ""
			and bool(lead.get("after_advance", false)),
		"the hunter_prey_mack_docks lead routes to a real place, pathway:hunter, after_advance:true")

	# (c) downing them drops hunter_characteristic via the PATHWAY-driven drop.
	_ok(P.drop_for_pathway("hunter") == "hunter_characteristic",
		"the drop is pathway-driven: drop_for_pathway('hunter') -> hunter_characteristic (no id branch)")
	var foe: Agent = AG.get_agent("leland_mack")
	_ok(foe != null and String(foe.pathway) == "hunter",
		"the live agent carries pathway:hunter (hydrated from data, not code)")
	if foe != null:
		foe.room = "suite_adv3_drop"
		foe.position = Vector2(120, 60)
		foe.downed = true
		RI.clear()
		EB.emit_event("agent_downed", {"actor": "player", "target": "leland_mack"})
		_ok(RI.count("suite_adv3_drop", "hunter_characteristic") >= 1,
			"downing leland_mack drops a hunter_characteristic (the second harvest -> Seq-7 advance)")
		RI.clear()

	# (d) the signature deed grants its suspicion clue to a watching proxy near the site.
	var deed: Dictionary = {}
	for d in DR.deeds:
		if String((d as Dictionary).get("id", "")) == "mack_breakwater_drag":
			deed = d
	_ok(not deed.is_empty() and String(deed.get("agent", "")) == "leland_mack"
			and String(deed.get("clue", "")) == "leland_mack_suspicious",
		"the deed mack_breakwater_drag is authored to the adversary, granting leland_mack_suspicious")

	# (e) the post-advance gate: after Progression.advanced fires, the lead is surfaced.
	var surfaced: Array = []
	var on_surf := func(id: String) -> void: surfaced.append(id)
	LS.lead_surfaced.connect(on_surf)
	P.advanced.emit("hunter", 8)
	LS.lead_surfaced.disconnect(on_surf)
	_ok(surfaced.has("hunter_prey_mack_docks"),
		"Progression.advanced fires -> LeadSystem surfaces the after_advance lead (post-advance gate)")

	# (f) engine neutrality: no NPC-id branches in src/ (grepped above by the BUILDER agent).
	# Two legitimate hunter meals: sable_wren (Seq-9 meal) + leland_mack (Seq-8 meal) = Seq 7 reachable
	# without touching constable_brom. B7 (M20): the quest-anchor constable_brom is now OFF-PATHWAY, so
	# downing the friendly lead-giver is no longer a farmable free advance (it would drop the generic
	# tainted_characteristic, not a usable hunter_characteristic).
	_ok(String(ND.get_def("constable_brom").get("pathway", "")) == ""
			and P.drop_for_pathway(String(ND.get_def("constable_brom").get("pathway", ""))) != "hunter_characteristic",
		"constable_brom is off-pathway (B7): downing him drops no free hunter_characteristic; Wren + Mack are the two meals")

	RI.clear()
	AG.rebuild()

## The REAL 9->7 advance loop (M14 review finding 6): two meals + two acting rituals driven through
## the LIVE Progression.advance() path — not a hand-emitted signal — proving the chain closes at
## Seq 7 on two legitimate harvests, and that the Mack lead unhides on the FIRST advance exactly.
func _test_adversary3_seq7_advance_loop() -> void:
	print("[adversary3: the REAL 9->7 advance loop — two meals, two rituals, the gated lead unhides on advance #1 (M14 #6)]")
	var P: Object = root.get_node("/root/Progression")
	var LS: Object = root.get_node("/root/LeadSystem")
	var RM: Object = root.get_node("/root/RunManager")
	var AG: Object = root.get_node("/root/Agents")
	var DB: Object = root.get_node("/root/AbilityDB")
	RM.start_run()
	var proxy: Agent = AG.ensure_player_proxy(Vector2.ZERO, "city")
	_ok(P.sequence() == 9, "a fresh run opens at Hunter Seq 9")
	# Pre-advance: the gated lead is HIDDEN — off the board, invisible to the player.
	_ok(String(LS.get_lead("hunter_prey_mack_docks").get("state", "")) == "hidden",
		"the Mack lead starts HIDDEN at run start")
	var on_board := false
	for l in LS.active_leads():
		if String((l as Dictionary).get("id", "")) == "hunter_prey_mack_docks":
			on_board = true
	_ok(not on_board, "…and does NOT show on the player's board pre-advance (no minute-0 spoiler)")
	# Advance #1 — the Wren meal + the acting ritual, through the LIVE gate.
	proxy.add_item("hunter_characteristic", 1)
	_ok(bool(P.perform_acting_deed().get("ok", false)), "acting ritual #1 performs through DeedRunner")
	_ok(bool(P.advance().get("ok", false)) and P.sequence() == 8,
		"advance #1: Seq 9 -> 8 on the first legitimate meal")
	_ok(String(LS.get_lead("hunter_prey_mack_docks").get("state", "")) == "open",
		"the FIRST advance unhides the Mack lead (hidden -> open, the Seq-8 hunt begins)")
	on_board = false
	for l in LS.active_leads():
		if String((l as Dictionary).get("id", "")) == "hunter_prey_mack_docks":
			on_board = true
	_ok(on_board, "…and it now renders on the board")
	# Advance #2 — the Mack meal + a FRESH ritual (each advance re-arms the deed), to the Seq-7 cap.
	proxy.add_item("hunter_characteristic", 1)
	_ok(not bool(P.can_advance().get("ok", false)),
		"a second advance is REFUSED before a fresh acting ritual (the deed re-arms per rung)")
	_ok(bool(P.perform_acting_deed().get("ok", false)), "acting ritual #2 performs")
	_ok(bool(P.advance().get("ok", false)) and P.sequence() == 7,
		"advance #2: Seq 8 -> 7 — the chain closes on TWO legitimate meals (no constable harmed)")
	_ok(DB.kit_for("player").has("mark_prey") and DB.kit_for("player").has("incendiary_round"),
		"…and both rung arts (mark_prey Seq8, incendiary_round Seq7) are in the usable kit")
	# Leave a fresh world for the tests downstream.
	RM.start_run()

# ─────────────────────────────────────────────────────────────────────────────
# M13: Reload / ammo pickups + empty-gun feedback (inline smoke; full harness: tests/test_reload.gd)
# ─────────────────────────────────────────────────────────────────────────────

func _test_reload_ammo_spawn_registered() -> void:
	print("[M13 reload: AmmoSpawn autoload + spawn table]")
	var AS: Object = root.get_node_or_null("/root/AmmoSpawn")
	_ok(AS != null, "AmmoSpawn autoload is registered")
	if AS == null:
		return
	_ok(AS.has_method("seed_run"), "AmmoSpawn.seed_run() method exists")
	_ok(AS.has_method("spawn_rooms"), "AmmoSpawn.spawn_rooms() method exists")
	_ok(AS.spawn_rooms().size() > 0, "spawn table has at least one room")

func _test_reload_pickup_seeds_deterministic() -> void:
	print("[M13 reload: pickup seeding is deterministic]")
	var RI: Object = root.get_node("/root/RoomItems")
	var AS: Object = root.get_node_or_null("/root/AmmoSpawn")
	if AS == null:
		_skip("AmmoSpawn not registered")
		return
	RI.clear()
	AS.seed_run(42)
	var total_a: int = 0
	for room_id in AS.spawn_rooms():
		total_a += RI.count(room_id, "revolver_round")
	_ok(total_a >= 1, "seed_run(42) places at least one revolver_round (%d placed)" % total_a)
	RI.clear()
	AS.seed_run(42)
	var total_b: int = 0
	for room_id in AS.spawn_rooms():
		total_b += RI.count(room_id, "revolver_round")
	_ok(total_b == total_a, "same seed -> same total pickups (deterministic: %d == %d)" % [total_b, total_a])
	RI.clear()

func _test_reload_empty_gun_event() -> void:
	print("[M13 reload: weapon_empty fires on no_ammo; pick-up closes dead-end]")
	var EB: Object = root.get_node("/root/EventBus")
	var RI: Object = root.get_node("/root/RoomItems")
	var p := _stage_player_m13("t_reload_smoke")
	var pc: Node = p.get_node("Combat")
	EB.clear()

	# Drain to 0 then trigger empty.
	pc.proxy.inventory["revolver_round"] = 1
	pc.on_attack_pressed(Vector2.RIGHT)
	_step_m13(pc, 1.0)
	pc.on_attack_pressed(Vector2.RIGHT)   # empty trigger
	_ok(EB.events("weapon_empty").size() >= 1,
		"weapon_empty event emitted on empty trigger")
	_ok(pc.ammo_count() == 0, "ammo_count() == 0 when dry")

	# Pick up a round and confirm the gun works again.
	var room_id: String = pc.proxy.room
	var pos: Vector2 = pc.proxy.position
	RI.clear()
	RI.place(room_id, "revolver_round", pos, 1)
	var taken: String = RI.take_near(room_id, "revolver_round", pos, 64.0)
	pc.proxy.add_item(taken, 1)
	_step_m13(pc, 0.5)
	var fired: Dictionary = pc.on_attack_pressed(Vector2.RIGHT)
	_ok(bool(fired.get("ok", false)),
		"after pick-up the gun fires again — ammo dead-end is closed")

	_end_player_m13(p)

func _test_reload_flash_toggle() -> void:
	print("[M13 reload: hit_flash toggle gates visual; event fires regardless]")
	var S: Object = root.get_node_or_null("/root/Settings")
	var FB: Object = root.get_node_or_null("/root/CombatFeedback")
	var EB: Object = root.get_node("/root/EventBus")
	if S == null or FB == null:
		_skip("Settings or CombatFeedback not available")
		return
	S.reset_defaults()
	EB.clear()
	var p := _stage_player_m13("t_flash_smoke")
	var pc: Node = p.get_node("Combat")
	pc.proxy.inventory["revolver_round"] = 1
	pc.on_attack_pressed(Vector2.RIGHT)
	_step_m13(pc, 1.0)
	# hit_flash ON.
	S.set_value("hit_flash", true)
	FB.reset_probe()
	pc.on_attack_pressed(Vector2.RIGHT)
	_ok(FB.last_flash_alpha() > 0.0, "hit_flash ON -> empty-gun flash fires (alpha=%.2f)" % FB.last_flash_alpha())
	_ok(EB.events("weapon_empty").size() >= 1, "hit_flash ON -> weapon_empty event fires")
	# hit_flash OFF.
	EB.clear()
	S.set_value("hit_flash", false)
	FB.reset_probe()
	pc.on_attack_pressed(Vector2.RIGHT)
	_ok(FB.last_flash_alpha() == 0.0, "hit_flash OFF -> empty-gun flash is a no-op")
	_ok(EB.events("weapon_empty").size() >= 1, "hit_flash OFF -> weapon_empty event STILL fires")
	S.reset_defaults()
	_end_player_m13(p)

func _test_reload_reset_per_run() -> void:
	print("[M13 reload: pickups reset per run (no carry/leak)]")
	var RI: Object = root.get_node("/root/RoomItems")
	var RM: Object = root.get_node("/root/RunManager")
	var AS: Object = root.get_node_or_null("/root/AmmoSpawn")
	if AS == null:
		_skip("AmmoSpawn not registered")
		return
	# Consume all pickups, then start_run to reset.
	RI.clear()
	AS.seed_run(7)
	for room_id in AS.spawn_rooms():
		for _i in RI.count(room_id, "revolver_round"):
			RI.take_near(room_id, "revolver_round", Vector2.ZERO, 99999.0)
	var after_consume: int = 0
	for room_id in AS.spawn_rooms():
		after_consume += RI.count(room_id, "revolver_round")
	_ok(after_consume == 0, "all pickups consumed")
	RM.start_run()
	var after_reset: int = 0
	for room_id in AS.spawn_rooms():
		after_reset += RI.count(room_id, "revolver_round")
	_ok(after_reset >= 1, "after start_run() pickups are re-placed (no leak, %d present)" % after_reset)
	# Second start_run must not accumulate extras.
	RM.start_run()
	var after_second: int = 0
	for room_id in AS.spawn_rooms():
		after_second += RI.count(room_id, "revolver_round")
	_ok(after_second == after_reset,
		"a second start_run() does not accumulate extra pickups (%d == %d)" % [after_second, after_reset])

func _test_reload_determinism_try_pay() -> void:
	print("[M13 reload: try_pay refusal order unchanged; weapon_empty cosmetic only]")
	var p := _stage_player_m13("t_det_smoke")
	var pc: Node = p.get_node("Combat")
	# no_weapon precedence.
	pc.proxy.remove_item("revolver", 1)
	pc.proxy.inventory["revolver_round"] = 5
	var r1: Dictionary = pc.on_attack_pressed(Vector2.RIGHT)
	_ok(not bool(r1.get("ok", false)) and String(r1.get("reason", "")) == "no_weapon",
		"no_weapon reason unchanged by M13")
	# no_ammo.
	pc.proxy.add_item("revolver", 1)
	pc.proxy.remove_item("revolver_round", 5)
	var r2: Dictionary = pc.on_attack_pressed(Vector2.RIGHT)
	_ok(not bool(r2.get("ok", false)) and String(r2.get("reason", "")) == "no_ammo",
		"no_ammo reason unchanged by M13")
	# weapon_empty NOT emitted for non-no_ammo refusals.
	var EB: Object = root.get_node("/root/EventBus")
	EB.clear()
	pc.proxy.remove_item("revolver", 1)
	pc.on_attack_pressed(Vector2.RIGHT)   # no_weapon, NOT no_ammo
	_ok(EB.events("weapon_empty").size() == 0,
		"weapon_empty NOT emitted for no_weapon (only for no_ammo)")
	_end_player_m13(p)

func _test_reload_city_bootstrap_preserves_ammo() -> void:
	## Regression for M13 review finding 1: CitySummoning._bootstrap used to call RoomItems.clear()
	## which wiped ALL rooms (including cathedral ammo). Fix: clear only city room, re-seed city ammo.
	## Proved headless: after CitySummoning._bootstrap runs, cathedral pickups must still exist.
	print("[M13 reload: CitySummoning bootstrap does NOT wipe non-city ammo pickups]")
	var RI: Object = root.get_node("/root/RoomItems")
	var AS: Object = root.get_node_or_null("/root/AmmoSpawn")
	if AS == null:
		_skip("AmmoSpawn not registered")
		return
	# Seed a full run (all rooms).
	RI.clear()
	AS.seed_run(42)
	var nave_before: int = RI.count("cathedral_nave", "revolver_round")
	var crypt_before: int = RI.count("cathedral_crypt", "revolver_round")
	_ok(nave_before >= 1, "cathedral_nave has ammo before bootstrap (%d rounds)" % nave_before)
	_ok(crypt_before >= 1, "cathedral_crypt has ammo before bootstrap (%d rounds)" % crypt_before)
	# Simulate CitySummoning._bootstrap (the non-underway path): call the static methods directly.
	# We do NOT instance City.tscn (that would trigger a 2-frame-deferred scene, slow + unstable).
	# Instead we call _clear_room("city") + seed_run_room("city") via the autoload seams, which is
	# exactly what the fixed _bootstrap does.
	var CS: GDScript = load("res://src/CitySummoning.gd") as GDScript
	var cs_inst: Node = CS.new()
	root.add_child(cs_inst)
	cs_inst._clear_room("city")
	AS.seed_run_room("city", 0)
	var nave_after: int = RI.count("cathedral_nave", "revolver_round")
	var crypt_after: int = RI.count("cathedral_crypt", "revolver_round")
	_ok(nave_after == nave_before,
		"cathedral_nave ammo PRESERVED after bootstrap (%d == %d)" % [nave_after, nave_before])
	_ok(crypt_after == crypt_before,
		"cathedral_crypt ammo PRESERVED after bootstrap (%d == %d)" % [crypt_after, crypt_before])
	var city_after: int = RI.count("city", "revolver_round")
	_ok(city_after >= 1, "city ammo re-seeded by bootstrap (%d rounds)" % city_after)
	cs_inst.free()
	RI.clear()

func _test_reload_player_proximity_pickup() -> void:
	## Regression for M13 review finding 2: the player must be able to auto-pick up ground ammo
	## via the proximity seam in PlayerCombat._try_pickup_nearby (the live production path, not the
	## test-calling-take_near directly as the old tests did).
	print("[M13 reload: player proximity auto-pickup (_try_pickup_nearby) closes dead-end]")
	var RI: Object = root.get_node("/root/RoomItems")
	var p := _stage_player_m13("t_proximity_pickup")
	var pc: Node = p.get_node("Combat")
	# Drain to 0.
	pc.proxy.inventory["revolver_round"] = 1
	pc.on_attack_pressed(Vector2.RIGHT)
	_step_m13(pc, 1.0)
	_ok(pc.proxy.item_count("revolver_round") == 0, "rounds drained to 0 for proximity test")
	# Place a round right where the player stands.
	var room_id: String = pc.proxy.room
	var pos: Vector2 = pc.proxy.position
	RI.clear()
	RI.place(room_id, "revolver_round", pos, 1)
	_ok(RI.count(room_id, "revolver_round") == 1, "round on ground at player position")
	# Call the production pickup path directly (same as the physics frame does).
	var taken: String = pc._try_pickup_nearby()
	_ok(taken == "revolver_round",
		"_try_pickup_nearby() picks up the round (production seam, not test-direct take_near)")
	_ok(pc.proxy.item_count("revolver_round") == 1,
		"inventory has 1 round after proximity pickup")
	_ok(RI.count(room_id, "revolver_round") == 0, "ground pile consumed")
	# The gun must fire again.
	_step_m13(pc, 0.5)
	var fired: Dictionary = pc.on_attack_pressed(Vector2.RIGHT)
	_ok(bool(fired.get("ok", false)),
		"gun fires after proximity pickup — dead-end closed via production path")
	_end_player_m13(p)
	RI.clear()

## M18: NPC combat costs are real — the generic AgentCostProvider pays an ammo-costed art from THE
## BOUND AGENT'S own inventory (a human gunman runs dry, then refuses), asked last so a refusal burns
## no cooldown; a free (monster) art is never refused. Mirrors PlayerCombat.try_pay for any agent.
func _test_npc_cost_provider() -> void:
	print("[NPC cost provider: ammo-costed arts pay from the agent's OWN inventory; free arts don't (combat M18)]")
	var gun := _stage_m2("m18_gun", "m18_arena", Vector2.ZERO)
	gun.add_item("revolver", 1)
	gun.add_item("revolver_round", 1)
	var ex := CombatExecutor.new()
	ex.bind(gun)
	ex.cost_provider = AgentCostProvider.new(gun)
	_ok(bool(ex.try_cast("revolver_shot", "").get("ok", false)),
		"a carried gun fires its ammo-costed art")
	_ok(gun.item_count("revolver_round") == 0,
		"the shot consumed a round from the agent's own inventory (not a built-in pool)")
	_step_m2([ex], 1.5)   # clear windup + the 0.9s cooldown
	var dry: Dictionary = ex.try_cast("revolver_shot", "")
	_ok(not bool(dry.get("ok", false)) and String(dry.get("reason", "")) == "no_ammo",
		"the dry gunman refuses the ammo-costed art with 'no_ammo'")
	_ok(ex.phase == "idle" and CombatResolver.ledger_ready(ex.ledger, "revolver_shot", ex.now_ms()),
		"…and a refused cost burns NO cooldown (asked last in the refusal chain)")
	# No granting weapon carried at all: a DISTINCT refusal (rounds are useless without the revolver).
	gun.remove_item("revolver", 1)
	gun.add_item("revolver_round", 3)
	var nw: Dictionary = ex.try_cast("revolver_shot", "")
	_ok(not bool(nw.get("ok", false)) and String(nw.get("reason", "")) == "no_weapon",
		"rounds without the granting weapon refuse with 'no_weapon'")
	_ok(gun.item_count("revolver_round") == 3, "…and the refusal spends nothing")
	# A monster free kit is UNAFFECTED — its {}-cost art always pays ok, with a provider bound.
	var mon := _stage_m2("m18_mon", "m18_arena", Vector2(40, 0))
	var mex := CombatExecutor.new()
	mex.bind(mon)
	mex.cost_provider = AgentCostProvider.new(mon)
	_ok(bool(mex.try_cast("cleaver_swipe", "").get("ok", false)),
		"a free (monster) art is never refused by the cost provider — monster forms fight unaffected")
	_end_m2([ex, mex])

## M18: NPC loadouts hydrate from DATA (npcs.json carried_items), a downed body's whole inventory is
## lootable exactly ONCE (latch), and both re-hydrate/reset per run with no cross-run leak.
func _test_npc_loadout_and_loot() -> void:
	print("[NPC loadout hydration + loot-a-downed-body-once + per-run reset (combat M18)]")
	var reg: Object = root.get_node("/root/Agents")
	reg.rebuild()
	var wren: Agent = reg.get_agent("sable_wren")
	_ok(wren != null and wren.item_count("revolver") == 1 and wren.item_count("revolver_round") == 6,
		"sable_wren hydrates her authored carried_items (revolver + 6 rounds)")
	_ok(wren != null and not wren.looted, "a freshly built body's loot latch is clear")
	# Loot transfer: a downed body yields its whole inventory once; a standing body yields nothing.
	var looter := Agent.new("m18_looter")
	var body := Agent.new("m18_body")
	body.add_item("revolver", 1)
	body.add_item("revolver_round", 2)
	body.add_item("shilling", 4)
	_ok(PlayerCombat.loot_downed_body(looter, body).is_empty() and looter.inventory_count() == 0,
		"a STANDING body cannot be looted")
	body.downed = true
	var moved: Dictionary = PlayerCombat.loot_downed_body(looter, body)
	_ok(int(moved.get("revolver", 0)) == 1 and looter.item_count("revolver_round") == 2
		and looter.item_count("shilling") == 4 and body.inventory_count() == 0 and body.looted,
		"looting a downed body moves its WHOLE inventory into the looter, once, and latches it")
	_ok(PlayerCombat.loot_downed_body(looter, body).is_empty() and looter.item_count("revolver") == 1,
		"a looted body yields nothing on a second loot (latch — no duplication)")
	# Per-run reset: mutate mid-run, then a fresh run re-hydrates + clears the latch + leaks nothing.
	wren.remove_item("revolver_round", 6)
	wren.looted = true
	wren.add_item("m18_junk", 3)
	reg.rebuild()
	var wren2: Agent = reg.get_agent("sable_wren")
	_ok(wren2.item_count("revolver") == 1 and wren2.item_count("revolver_round") == 6
		and not wren2.looted and wren2.item_count("m18_junk") == 0,
		"a fresh run re-hydrates the loadout, resets the loot latch, and leaks nothing")

func _stage_player_m13(room_id: String, pos: Vector2 = Vector2.ZERO) -> Node:
	var p = load("res://scenes/Player.tscn").instantiate()
	root.add_child(p)
	p.global_position = pos
	var pc: Node = p.get_node("Combat")
	pc.proxy.room = room_id
	pc.proxy.position = pos
	return p

func _step_m13(pc: Node, seconds: float) -> void:
	var steps := int(round(seconds * 60.0))
	for _i in steps:
		pc.executor.step_combat(1.0 / 60.0)

func _end_player_m13(player: Node) -> void:
	if player != null:
		player.free()
	root.get_node("/root/Agents").rebuild()
	root.get_node("/root/EventBus").clear()

# ─────────────────────────────────────────────────────────────────────────────
# M15: Franky's shop — buy ammo + sell harvest (inline smoke; full harness: tests/test_shop.gd)
# ─────────────────────────────────────────────────────────────────────────────

## A brand-new player proxy carrying the scenario loadout (rebuild clears the ephemeral proxy).
func _fresh_proxy_m15() -> Agent:
	var AG: Object = root.get_node("/root/Agents")
	AG.rebuild()
	return AG.ensure_player_proxy(Vector2.ZERO, "mr_frankys_inner")

func _end_shop_m15() -> void:
	root.get_node("/root/Agents").rebuild()
	root.get_node("/root/EventBus").clear()
	var S: Object = root.get_node_or_null("/root/Shop")
	if S != null:
		S.reset()

func _test_shop_buy_costed_and_latched() -> void:
	print("[M15 shop: buy is coin-costed + per-run stock-latched (no free infinite tap)]")
	var S: Object = root.get_node_or_null("/root/Shop")
	_ok(S != null, "Shop autoload is registered")
	if S == null:
		return
	S.reset()
	var p := _fresh_proxy_m15()
	_ok(p.item_count("shilling") == 5, "the loadout grants 5 starting shillings")
	var rounds_before := p.item_count("revolver_round")
	var r1: Dictionary = S.buy_ammo()
	_ok(bool(r1.get("ok", false)), "a funded buy succeeds")
	_ok(p.item_count("revolver_round") == rounds_before + 6, "rounds +6 (authored qty)")
	# M26 BALANCE RETUNE #4: buy price 4 -> 3, so 5 starting shillings -> 2 after one box.
	_ok(p.item_count("shilling") == 2, "coin -3 (authored price — COSTED, not free)")
	# No coin -> clean refusal, nothing moves.
	p.inventory["shilling"] = 0
	var r2: Dictionary = S.buy_ammo()
	_ok(not bool(r2.get("ok", false)) and String(r2.get("reason", "")) == "no_coin",
		"an unfunded buy refuses with no_coin")
	# Stock latch: 3 restocks per run, then out_of_stock.
	p.inventory["shilling"] = 100
	S.buy_ammo()
	S.buy_ammo()
	_ok(S.restocks_left() == 0, "stock exhausted after 3 restocks")
	var rounds_capped := p.item_count("revolver_round")
	var r3: Dictionary = S.buy_ammo()
	_ok(not bool(r3.get("ok", false)) and String(r3.get("reason", "")) == "out_of_stock",
		"buy 4 refuses with out_of_stock — the per-run cap holds")
	_ok(p.item_count("revolver_round") == rounds_capped, "…and the refused buy granted nothing")
	_end_shop_m15()

func _test_shop_sell_real_coin_and_fuel_forfeit() -> void:
	print("[M15 shop: sell pays authored coin; M26 pity margin keeps the climb reachable after selling fuel]")
	var S: Object = root.get_node_or_null("/root/Shop")
	var PR: Object = root.get_node("/root/Progression")
	if S == null:
		_skip("Shop autoload not registered")
		return
	S.reset()
	var p := _fresh_proxy_m15()
	p.inventory["shilling"] = 0
	PR.reset()
	p.add_item("tainted_characteristic", 2)
	p.add_item("hunter_characteristic", 1)
	PR.mark_deed_done()
	_ok(bool(PR.can_advance().get("ok", false)), "BEFORE the sell the advance is live")
	var s1: Dictionary = S.sell_harvest()
	_ok(bool(s1.get("ok", false)) and int(s1.get("coins", -1)) == 22,
		"sell pays the authored total: 2 tainted (6) + 1 hunter (10) == 22 shillings")
	_ok(p.item_count("shilling") == 22, "the coin landed in the inventory (sell is REAL)")
	# M26 BALANCE RETUNE #1: selling one fuel latches a pity margin, so the advance stays reachable —
	# the old sell-fork TRAP is gone (full margin proof lives in tests/test_balance.gd).
	var gate: Dictionary = PR.can_advance()
	_ok(bool(gate.get("ok", false)),
		"AFTER selling one fuel can_advance stays OK — the sell-fork trap is gone (pity margin)")
	var s2: Dictionary = S.sell_harvest()
	_ok(not bool(s2.get("ok", false)) and String(s2.get("reason", "")) == "nothing_to_sell",
		"an empty-handed sell refuses with nothing_to_sell")
	PR.reset()
	_end_shop_m15()

func _test_shop_reset_and_snapshot() -> void:
	print("[M15 shop: coin + stock reset per run; the stock latch rides the nightly checkpoint]")
	var S: Object = root.get_node_or_null("/root/Shop")
	var RM: Object = root.get_node("/root/RunManager")
	if S == null:
		_skip("Shop autoload not registered")
		return
	RM.start_run()
	var AG: Object = root.get_node("/root/Agents")
	var p: Agent = AG.ensure_player_proxy(Vector2.ZERO, "mr_frankys_inner")
	_ok(S.restocks_left() == 3, "a fresh run opens with the full shelf (3 restocks)")
	_ok(p.item_count("shilling") == 5, "a fresh run opens with the loadout coin (5)")
	S.buy_ammo()
	RM.checkpoint_night()
	p.inventory["shilling"] = 100
	S.buy_ammo()
	_ok(S.restocks_left() == 1, "two restocks used (one after the checkpoint)")
	RM.end_run("death")
	_ok(S.restocks_left() == 2,
		"a death restore returns the shelf to its CHECKPOINT state (2 left, not fresh/spent)")
	var p2: Agent = AG.ensure_player_proxy(Vector2.ZERO, "mr_frankys_inner")
	_ok(p2.item_count("shilling") == 5,
		"the restored proxy re-arms with the loadout coin (died-with-proxy semantics, as the 12 rounds)")
	RM.start_run()
	_ok(S.restocks_left() == 3, "start_run() restores the FULL shelf — no carry across runs")
	_end_shop_m15()

func _test_shop_fork_sell_and_counter_wired() -> void:
	print("[M15 shop: the opening fork's SELL is honest; the counter Interactable is wired]")
	var GMO: Object = root.get_node("/root/GMOpening")
	var opts: Array = GMO.harvest_fork().get("options", [])
	_ok(opts.has("sell"), "the authored fork offers sell")
	var r: Dictionary = GMO.choose_harvest("sell")
	_ok(bool(r.get("ok", false)) and String(r.get("hint", "")) != "",
		"choose_harvest('sell') surfaces the authored shop hint (the SELL word leads to real coin)")
	_ok(String(GMO.harvest_choice()) == "sell", "the fork choice is stored for the run")
	GMO.reset()
	_ok(String(GMO.harvest_choice()) == "", "GMOpening.reset() scrubs the stored fork choice")
	# The trade in Mr Franky's hall is TWO deliberate stops with the generic flags (review fix:
	# a single both-flag counter auto-sold the carried advance fuel on a plain rounds run).
	var room: Node = (load("res://scenes/MrFrankysInner.tscn") as PackedScene).instantiate()
	root.add_child(room)
	var sell_c: Node = room.get_node_or_null("SellCounter")
	var buy_c: Node = room.get_node_or_null("AmmoShelf")
	_ok(sell_c != null and "shop_sell_harvest" in sell_c
			and bool(sell_c.shop_sell_harvest) and not bool(sell_c.shop_buy_ammo),
		"MrFrankysInner has a SELL-only counter (selling the fuel is a deliberate act)")
	_ok(buy_c != null and "shop_buy_ammo" in buy_c
			and bool(buy_c.shop_buy_ammo) and not bool(buy_c.shop_sell_harvest),
		"MrFrankysInner has a BUY-only rounds shelf (a rounds run can never auto-sell the fuel)")
	room.free()
	# The old dead verb is honest now: franky_buy() without coin refuses (free tap CLOSED).
	var S: Object = root.get_node_or_null("/root/Shop")
	var AS: Object = root.get_node_or_null("/root/AmmoSpawn")
	if S == null or AS == null:
		_skip("Shop/AmmoSpawn not registered")
		return
	S.reset()
	var p := _fresh_proxy_m15()
	p.inventory["shilling"] = 0
	var rounds_before := p.item_count("revolver_round")
	var tap: Variant = AS.franky_buy()
	_ok(tap is Dictionary and not bool((tap as Dictionary).get("ok", false)),
		"AmmoSpawn.franky_buy() refuses without coin (the M13 free-tap warning is closed)")
	_ok(p.item_count("revolver_round") == rounds_before, "…and granted no rounds")
	_end_shop_m15()

## M15 review fix: the fork is PRESENTED live off the published agent_downed fact — a live player
## who downs the staged opening Beyonder sees digest/sell/keep + the sell_hint with no harness
## call. The full harness (narrated options, idempotent latch) lives in tests/test_shop.gd (g).
func _test_shop_live_fork_presented() -> void:
	print("[M15 shop: the harvest fork PRESENTS live off the agent_downed fact (no manual director call)]")
	var RM: Object = root.get_node("/root/RunManager")
	var GMO: Object = root.get_node("/root/GMOpening")
	var AG: Object = root.get_node("/root/Agents")
	var EB: Object = root.get_node("/root/EventBus")
	var WS: Object = root.get_node("/root/WorldState")
	RM.start_run()
	_ok(not GMO.harvest_presented(), "fresh run: the fork is not yet presented")
	var seen := {"forks": 0, "text": ""}
	var on_fork := func(_f: Dictionary) -> void: seen["forks"] = int(seen["forks"]) + 1
	var on_thought := func(t: String) -> void: seen["text"] = String(seen["text"]) + " " + t
	GMO.harvest_fork_presented.connect(on_fork)
	WS.thought_requested.connect(on_thought)
	AG.get_agent("bram_kell").downed = true
	EB.emit_event("agent_downed", {"actor": "player", "target": "bram_kell"})
	GMO.harvest_fork_presented.disconnect(on_fork)
	WS.thought_requested.disconnect(on_thought)
	_ok(GMO.harvest_presented() and int(seen["forks"]) == 1,
		"the downed FACT alone presented the fork exactly once (live path, not test-only)")
	var sell_hint := String(GMO.OPENING.get("sell_hint", ""))
	_ok(sell_hint != "" and String(seen["text"]).find(sell_hint) != -1,
		"the live presentation surfaces the authored sell_hint (the SELL word leads to real coin)")
	GMO.reset()
	_end_shop_m15()

## M20 live-loop bugs (docs/handoff/OVERNIGHT_BACKLOG.md B1/B2/B6/B7) — smoke-level asserts in the
## main suite; the full harness (live City.tscn pacing, the digest/acting Interactable flags, the
## Madness cap rollover, the constable_brom harvest drop) lives in tests/test_live_bugs.gd. These keep
## the main suite honest that the city no longer auto-loses, the core progression loop has a live
## caller, the opener objective points at the butcher, and constable_brom is off-pathway + talkable.
func _test_live_bugs_m20() -> void:
	print("[M20 live-loop bugs: B1 city auto-loss / B2 progression loop / B6 opener / B7 constable_brom]")
	var RM: Object = root.get_node("/root/RunManager")
	var RN: Object = root.get_node("/root/RitualNight")
	var AG: Object = root.get_node("/root/Agents")
	var P: Object = root.get_node("/root/Progression")
	var M: Object = root.get_node("/root/Meters")
	var WS: Object = root.get_node("/root/WorldState")
	var LS: Object = root.get_node("/root/LeadSystem")
	var DB: Object = root.get_node("/root/NpcDB")
	# B1: the City scene no longer embeds the legacy CitySummoning node.
	var city: Node = (load("res://scenes/City.tscn") as PackedScene).instantiate()
	_ok(city.get_node_or_null("CitySummoning") == null, "B1: City.tscn has no CitySummoning node")
	city.free()
	# B1: the legacy summoning_climax is inert unless a Ritual Night owns the climax.
	RN.reset()
	RM.start_run()
	var ended := {"reason": ""}
	var cb := func(reason: String) -> void: ended["reason"] = reason
	RM.run_ended.connect(cb)
	RM._on_summoning_climax(100.0)
	RM.run_ended.disconnect(cb)
	_ok(RM.run_active() and String(ended["reason"]) == "",
		"B1: _on_summoning_climax no-ops without an active Ritual Night (no self-loss)")
	# B2: the live digest/advance action raises the Sequence; checkpoint_night + acting deed move Madness.
	AG.rebuild()
	var proxy: Object = AG.ensure_player_proxy(Vector2.ZERO, "city")
	proxy.add_item(P.characteristic_item(), 1)
	P.mark_deed_done()
	var seq_before: int = P.sequence()
	var dnode: Node = (load("res://scenes/Interactable.tscn") as PackedScene).instantiate()
	dnode.digest_advance = true
	root.add_child(dnode)
	await process_frame
	dnode._use()
	dnode.free()
	_ok(P.sequence() == seq_before - 1, "B2: the digest/advance action raised the Sequence one rung")
	M.set_meter("doom", 30.0)
	M.set_meter("madness", 40.0)
	RM.checkpoint_night()
	_ok(is_equal_approx(M.get_meter("madness"), 30.0), "B2: checkpoint_night relieves Madness (nightly rest -10)")
	M.set_meter("madness", 50.0)
	root.get_node("/root/Clock").set_time(1, 480)
	M.try_relieve_madness_deed(); M.try_relieve_madness_deed(); M.try_relieve_madness_deed()
	var capped: Dictionary = M.try_relieve_madness_deed()
	# M26 RETUNE #5: deed relief -3 each (was -5); 3/day cap unchanged, so 50 -> 41 then refused.
	_ok(is_equal_approx(M.get_meter("madness"), 41.0) and not bool(capped.get("ok", true)),
		"B2: the acting-deed relief caps at 3/day (-9 then refused)")
	# B6: the run-start objective names the butcher opener.
	RM.start_run()
	var lead: Dictionary = LS.get_lead("butcher_iron_cross")
	_ok(not lead.is_empty() and String(WS.current_lead).to_lower().find("iron cross") != -1
			and String(WS.current_lead) != WS.RUN_START_LEAD,
		"B6: WorldState.current_lead points at the butcher opener (not the legacy string)")
	# B7: constable_brom is off-pathway (no free hunter_characteristic) and talkable.
	var def: Dictionary = DB.get_def("constable_brom")
	_ok(String(def.get("pathway", "")) == "" and String(def.get("combat_form", "")) != "butcher_human",
		"B7: constable_brom is off-pathway with no butcher combat_form")
	_ok(P.drop_for_pathway(String(def.get("pathway", ""))) != "hunter_characteristic",
		"B7: downing constable_brom would not drop a hunter_characteristic (no free advance)")
	var dlg: Variant = JSON.parse_string(FileAccess.get_file_as_string("res://data/dialogue.json"))
	_ok(dlg is Dictionary and (dlg as Dictionary).has("constable_brom")
			and String(def.get("dialogue_id", "")) == "constable_brom",
		"B7: constable_brom has a dialogue entry wired via dialogue_id")
	RM.start_run()
	AG.rebuild()
