extends SceneTree
## M35 — AFFORDANCE & ONBOARDING POLISH. Two playtests found systems "reachable but undiscoverable":
## at a glance you can't tell what's interactive (only a floating "Examine" label), and onboarding is
## just progressive meters + the [H] legend. This harness pins the two systemic fixes, each driven
## through a REAL seam (not a private helper), all LOGIC (no pixels — the visuals are live-only):
##
##   (1) INTERACTABLE AFFORDANCE — an Interactable exposes a highlight STATE (is_highlighted()) that is
##       true while the player stands near it (the same _player_near seam that shows the Examine label)
##       and false when they leave. The live-only glow/bob rides that state; here we assert the STATE
##       transitions on enter/exit and that the existing Examine-label behaviour is preserved. A non-
##       player body never highlights.
##
##   (2) A REUSABLE ONCE-ONLY CONTEXTUAL-HINT FRAMEWORK (HintDirector) — given a hint KEY it surfaces the
##       diegetic copy (data/hints.json, or a caller-supplied line) EXACTLY ONCE and never again:
##         (2a) fire key A -> surfaces once; fire A again -> NO second surface; fire key B -> surfaces once.
##         (2b) a persisted (once-ever) key survives a fresh HintDirector instance (the "restart" proof).
##         (2c) REAL trigger: an ability_cast_started event (the live telegraph/cast seam) drives the
##              first-dash / first-fire / first-enemy-telegraph hints, each firing EXACTLY once across
##              repeated triggers — never on the 2nd+.  This is the no-spam core.
##         (2d) M32's counter-rite hint routes THROUGH the same framework (HintDirector.has_fired flips),
##              not a second parallel latch — and its once-per-run re-arm (CounterRite.reset) still works.
##
## Standalone: godot --headless --path tingen -s tests/test_onboarding.gd
## Folded into the suite via run_tests.gd `_test_onboarding` (SAME run_all() entry, shared pass/fail).

func _init() -> void:
	await process_frame
	await process_frame
	# B3 (retro): NEVER touch the player's REAL persistent profile (user://meta.json) — redirect
	# the meta slot to a test-scoped file before anything drives RunManager (tests/test_meta_isolation.gd).
	root.get_node("/root/RunManager").set("meta_path", "user://meta_test.json")
	root.get_node("/root/RunManager").reload_meta()
	var r: Dictionary = await run_all()
	print("\n=== test_onboarding: %d passed, %d failed ===" % [int(r["passed"]), int(r["failed"])])
	quit(1 if int(r["failed"]) > 0 else 0)

## The one entry point (returns {passed, failed}); folded into run_tests.gd.
static func run_all() -> Dictionary:
	var c := {"passed": 0, "failed": 0}
	var root: Node = (Engine.get_main_loop() as SceneTree).root
	await _1_interactable_highlight_state(c, root)
	_2a_hint_dedup_by_key(c, root)
	_2b_hint_persists_once_ever(c, root)
	_2c_hint_fires_on_real_cast_event(c, root)
	_2d_counter_rite_routes_through_framework(c, root)
	# Leave a clean world for whatever runs next in the shared suite.
	var HD: Object = root.get_node_or_null("/root/HintDirector")
	if HD != null and HD.has_method("clear_for_test"):
		HD.clear_for_test()
	root.get_node("/root/RunManager").start_run()
	root.get_node("/root/Agents").rebuild()
	return c

# --- helpers ------------------------------------------------------------------------------------
static func _check(c: Dictionary, cond: bool, label: String) -> void:
	if cond:
		c["passed"] = int(c["passed"]) + 1
		print("  PASS  %s" % label)
	else:
		c["failed"] = int(c["failed"]) + 1
		printerr("  FAIL  %s" % label)

# (1) Interactable highlight STATE follows _player_near; Examine label preserved -----------------
static func _1_interactable_highlight_state(c: Dictionary, root: Node) -> void:
	print("[M35 (1): an Interactable exposes a highlight STATE that follows the player-near seam — the affordance the live glow/bob rides; the Examine label is preserved]")
	var inter: Node = (load("res://scenes/Interactable.tscn") as PackedScene).instantiate()
	root.add_child(inter)
	await root.get_tree().process_frame
	# The affordance contract: a headless-observable highlight STATE (no pixel assertion).
	_check(c, inter.has_method("is_highlighted"),
		"the Interactable exposes is_highlighted() — a headless-observable affordance STATE")
	var prompt: Object = inter.get_node_or_null("Prompt")
	_check(c, prompt != null, "the Interactable still carries its Examine Prompt label")
	if not inter.has_method("is_highlighted") or prompt == null:
		inter.free()
		return

	# Baseline: nobody near -> not highlighted, Examine hidden.
	_check(c, not bool(inter.is_highlighted()), "with no one near, the interactable is NOT highlighted")
	_check(c, not bool(prompt.visible), "with no one near, the Examine label is hidden (preserved)")

	# The PLAYER enters the sensor (the real _player_near seam) -> highlighted + Examine shown.
	var player_body := Node2D.new()
	player_body.add_to_group("player")
	root.add_child(player_body)
	inter._on_body_entered(player_body)
	_check(c, bool(inter.is_highlighted()),
		"the interactable HIGHLIGHTS while the player is near (the glance-able affordance)")
	_check(c, bool(prompt.visible), "the Examine label STILL shows while near (existing behaviour preserved)")

	# The player leaves -> the highlight and the Examine label both clear.
	inter._on_body_exited(player_body)
	_check(c, not bool(inter.is_highlighted()), "the highlight clears when the player leaves")
	_check(c, not bool(prompt.visible), "the Examine label hides again when the player leaves")

	# A NON-player body must never trip the affordance (only the player's proximity counts).
	var stray := Node2D.new()
	stray.add_to_group("npc")
	root.add_child(stray)
	inter._on_body_entered(stray)
	_check(c, not bool(inter.is_highlighted()), "a non-player body entering does NOT highlight the interactable")

	inter._on_body_exited(stray)
	stray.free()
	player_body.free()
	inter.free()

# (2a) HintDirector — the once-only dedup core: fire once, never again; a different key still fires
static func _2a_hint_dedup_by_key(c: Dictionary, root: Node) -> void:
	print("[M35 (2a): HintDirector surfaces a hint by KEY EXACTLY once — a repeat of the SAME key never re-surfaces (no spam); a DIFFERENT key surfaces once]")
	var HD: Object = root.get_node_or_null("/root/HintDirector")
	var WS: Object = root.get_node_or_null("/root/WorldState")
	var EB: Object = root.get_node_or_null("/root/EventBus")
	_check(c, HD != null, "the HintDirector framework autoload exists (the reusable once-only hint system)")
	_check(c, WS != null and EB != null, "WorldState + EventBus autoloads are present")
	if HD == null or WS == null or EB == null:
		return
	_check(c, HD.has_method("fire") and HD.has_method("has_fired") and HD.has_method("clear_for_test"),
		"HintDirector exposes fire()/has_fired()/clear_for_test()")
	if not (HD.has_method("fire") and HD.has_method("has_fired") and HD.has_method("clear_for_test")):
		return

	HD.clear_for_test()
	# Count how often each authored line reaches the HUD's thought channel (the real surface seam).
	var seen := {"a": 0, "b": 0}
	var text_a := "M35-TEST-A the makings of a warding rite"
	var text_b := "M35-TEST-B a breath and I am elsewhere"
	var on_thought := func(t: String) -> void:
		if t == text_a:
			seen["a"] = int(seen["a"]) + 1
		elif t == text_b:
			seen["b"] = int(seen["b"]) + 1
	WS.thought_requested.connect(on_thought)

	# Fire key A the first time -> surfaces exactly once; the latch flips.
	var r1: bool = bool(HD.fire("m35_test_a", text_a, false))
	_check(c, r1, "firing a fresh hint key returns true (it surfaced)")
	_check(c, int(seen["a"]) == 1, "the hint surfaced EXACTLY once on the first fire")
	_check(c, bool(HD.has_fired("m35_test_a")), "the key is latched as fired")

	# Fire key A AGAIN -> NO second surface (dedup by key). THE most important behaviour.
	var r2: bool = bool(HD.fire("m35_test_a", text_a, false))
	_check(c, not r2, "re-firing the SAME key returns false (already shown)")
	_check(c, int(seen["a"]) == 1, "re-firing the SAME key does NOT surface a second time (no spam)")

	# A DIFFERENT key still surfaces once (the dedup is per-key, not global).
	var r3: bool = bool(HD.fire("m35_test_b", text_b, false))
	_check(c, r3 and int(seen["b"]) == 1, "a DIFFERENT hint key surfaces once (dedup is per-key)")

	# The surface also fans onto the EventBus exactly once per key (a hint_shown event, deduped).
	var shown_a: int = EB.events("hint_shown").filter(
		func(e: Dictionary) -> bool: return String((e.get("data", {}) as Dictionary).get("key", "")) == "m35_test_a").size()
	_check(c, shown_a == 1, "the EventBus carries a single hint_shown event for the deduped key")

	# A key with NO copy (no data entry, no override) does not surface and does not latch.
	var r4: bool = bool(HD.fire("m35_test_empty", "", false))
	_check(c, not r4 and not bool(HD.has_fired("m35_test_empty")),
		"a hint with no authored copy neither surfaces nor latches (nothing to say)")

	WS.thought_requested.disconnect(on_thought)
	HD.clear_for_test()

# (2b) A persisted (once-ever) key survives a fresh HintDirector instance — the "restart" proof ----
static func _2b_hint_persists_once_ever(c: Dictionary, root: Node) -> void:
	print("[M35 (2b): a persisted once-EVER hint key survives a fresh HintDirector instance (persisted flag, never repeats across runs)]")
	var HD: Object = root.get_node_or_null("/root/HintDirector")
	if HD == null or not HD.has_method("fire"):
		_check(c, false, "HintDirector present with a fire() verb")
		return
	HD.clear_for_test()
	# Fire a PERSISTED key (persist=true is the once-ever default).
	var did: bool = bool(HD.fire("m35_persist_key", "M35-TEST persisted line", true))
	_check(c, did and bool(HD.has_fired("m35_persist_key")), "a persisted hint fires and latches")

	# A brand-new HintDirector instance (a stand-in for a fresh game boot) must SEE it as already fired,
	# proving the flag is persisted to disk — not just held in memory for this session.
	var HDScript: Variant = load("res://src/HintDirector.gd")
	_check(c, HDScript != null, "the HintDirector script loads")
	if HDScript != null:
		var fresh: Object = HDScript.new()
		if fresh.has_method("reload"):
			fresh.reload()
		_check(c, bool(fresh.has_fired("m35_persist_key")),
			"a FRESH HintDirector instance sees the persisted key as already fired (survives a restart)")
		if fresh is Node:
			(fresh as Node).free()

	HD.clear_for_test()

# (2c) REAL trigger: an ability_cast_started event drives the dash/fire/telegraph hints, once each ---
## Drives the SAME event-dispatch handler live play uses (HintDirector._on_event over an
## ability_cast_started event — the cast/telegraph seam), directly, exactly as CombatFeedback's tests
## drive shake()/flash(). Asserts each hint fires EXACTLY once across repeated triggers (never 2nd+).
static func _2c_hint_fires_on_real_cast_event(c: Dictionary, root: Node) -> void:
	print("[M35 (2c): the REAL cast/telegraph seam (ability_cast_started) fires the first-dash / first-fire / first-enemy-telegraph hints EXACTLY once each — never on the 2nd+ (no spam)]")
	var HD: Object = root.get_node_or_null("/root/HintDirector")
	var WS: Object = root.get_node_or_null("/root/WorldState")
	_check(c, HD != null and WS != null, "HintDirector + WorldState present")
	if HD == null or WS == null:
		return
	_check(c, HD.has_method("_on_event") and HD.has_method("hint_text"),
		"HintDirector exposes the event seam (_on_event) + the data-copy accessor (hint_text)")
	if not (HD.has_method("_on_event") and HD.has_method("hint_text")):
		return

	# The onboarding copy is DATA (data/hints.json), not an engine literal.
	var dash_text := String(HD.hint_text("first_dash"))
	var fire_text := String(HD.hint_text("first_fire"))
	var tele_text := String(HD.hint_text("first_telegraph"))
	_check(c, dash_text != "" and fire_text != "" and tele_text != "",
		"the first_dash / first_fire / first_telegraph hints author diegetic copy in data/hints.json")

	HD.clear_for_test()
	var seen := {"dash": 0, "fire": 0, "tele": 0}
	var on_thought := func(t: String) -> void:
		if t == dash_text and dash_text != "":
			seen["dash"] = int(seen["dash"]) + 1
		elif t == fire_text and fire_text != "":
			seen["fire"] = int(seen["fire"]) + 1
		elif t == tele_text and tele_text != "":
			seen["tele"] = int(seen["tele"]) + 1
	WS.thought_requested.connect(on_thought)

	# The PLAYER dashes (ability_cast_started, caster player, ability dash) -> the first-dash hint once.
	HD._on_event({"type": "ability_cast_started", "data": {"caster": "player", "ability": "dash"}})
	_check(c, int(seen["dash"]) == 1, "the first player DASH surfaces the first-dash hint once")
	# Dash AGAIN and AGAIN -> never a second surface.
	HD._on_event({"type": "ability_cast_started", "data": {"caster": "player", "ability": "dash"}})
	HD._on_event({"type": "ability_cast_started", "data": {"caster": "player", "ability": "dash"}})
	_check(c, int(seen["dash"]) == 1, "repeated dashes NEVER re-surface the first-dash hint (fires once EVER)")

	# The PLAYER fires the primary (a non-dash player cast) -> the first-fire hint once, then never again.
	HD._on_event({"type": "ability_cast_started", "data": {"caster": "player", "ability": "revolver_shot"}})
	_check(c, int(seen["fire"]) == 1, "the first player primary FIRE surfaces the first-fire hint once")
	HD._on_event({"type": "ability_cast_started", "data": {"caster": "player", "ability": "star_brand"}})
	_check(c, int(seen["fire"]) == 1, "a later player cast never re-surfaces the first-fire hint")

	# An ENEMY telegraphs (ability_cast_started, caster NOT the player) -> the first-telegraph hint once.
	HD._on_event({"type": "ability_cast_started", "data": {"caster": "old_neil", "ability": "star_brand"}})
	_check(c, int(seen["tele"]) == 1, "the first ENEMY telegraph surfaces the first-telegraph hint once")
	HD._on_event({"type": "ability_cast_started", "data": {"caster": "butcher", "ability": "cleave"}})
	_check(c, int(seen["tele"]) == 1, "a later enemy telegraph never re-surfaces the first-telegraph hint")

	WS.thought_requested.disconnect(on_thought)
	HD.clear_for_test()

# (2d) M32's counter-rite hint routes THROUGH the framework (no parallel latch) --------------------
## The counter-rite discoverability hint must not be a second, parallel once-flag: it must go through
## HintDirector (has_fired flips), while keeping its once-per-RUN re-arm (CounterRite.reset).
static func _2d_counter_rite_routes_through_framework(c: Dictionary, root: Node) -> void:
	print("[M35 (2d): M32's counter-rite hint ROUTES THROUGH HintDirector (no duplicate system) — has_fired flips on first-hold-both, and reset() re-arms it for a fresh run]")
	var HD: Object = root.get_node_or_null("/root/HintDirector")
	var CR: Object = root.get_node_or_null("/root/CounterRite")
	var INV: Object = root.get_node_or_null("/root/Inventory")
	var WS: Object = root.get_node_or_null("/root/WorldState")
	_check(c, HD != null and CR != null and INV != null and WS != null,
		"HintDirector + CounterRite + Inventory + WorldState present")
	if HD == null or CR == null or INV == null or WS == null:
		return

	var hint_text := String(CR.rite_def().get("hint", ""))
	_check(c, hint_text != "", "the counter-rite still authors its diegetic hint in data/rituals.json")
	if HD.has_method("clear_for_test"):
		HD.clear_for_test()
	if CR.has_method("reset"):
		CR.reset()
	INV.clear()

	var seen := {"n": 0}
	var on_thought := func(t: String) -> void:
		if t == hint_text and hint_text != "":
			seen["n"] = int(seen["n"]) + 1
	WS.thought_requested.connect(on_thought)

	# First moment the player holds BOTH ingredients -> the hint surfaces once AND HintDirector latched it
	# under a stable key (proof it routed THROUGH the framework, not a private CounterRite flag).
	INV.add("candle", 1)
	_check(c, int(seen["n"]) == 0 and not bool(HD.has_fired("counter_rite")),
		"with only one ingredient the counter-rite hint has NOT fired (framework key not yet latched)")
	INV.add("consecrated_chalk", 1)
	_check(c, int(seen["n"]) == 1, "holding BOTH ingredients surfaced the counter-rite hint exactly once")
	_check(c, bool(HD.has_fired("counter_rite")),
		"the counter-rite hint routed THROUGH HintDirector (its framework key latched — one system, not two)")

	# A later inventory change does NOT re-fire (the framework's dedup owns it now).
	INV.add("candle", 1)
	_check(c, int(seen["n"]) == 1, "a later inventory change does NOT re-fire the counter-rite hint (framework dedup)")

	# Once-per-RUN: CounterRite.reset() re-arms the framework key so a fresh run hints again.
	if CR.has_method("reset"):
		CR.reset()
	_check(c, not bool(HD.has_fired("counter_rite")),
		"CounterRite.reset() re-arms the framework key (the once-per-run discovery beat, via the shared system)")
	INV.clear()
	var seen2 := {"n": 0}
	var on_thought2 := func(t: String) -> void:
		if t == hint_text and hint_text != "":
			seen2["n"] = int(seen2["n"]) + 1
	WS.thought_requested.connect(on_thought2)
	INV.add("candle", 1)
	INV.add("consecrated_chalk", 1)
	_check(c, int(seen2["n"]) == 1, "after reset() the counter-rite hint re-arms and fires once again (fresh run)")

	WS.thought_requested.disconnect(on_thought)
	WS.thought_requested.disconnect(on_thought2)
	INV.clear()
	if CR.has_method("reset"):
		CR.reset()
	if HD.has_method("clear_for_test"):
		HD.clear_for_test()
