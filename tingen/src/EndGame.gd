extends CanvasLayer
## End-game shell (autoload `EndGame`). Listens for the one moment the doomsday clock runs out
## (`SummoningPlan.summoning_climax`), asks `EndGameResolver` which of the three endings the run
## reached, freezes the world, and raises a win/lose screen with Restart / Quit. It is a thin
## UI + pause shell: all the branching lives in the pure resolver, so this stays trivial to read.
##
## process_mode = ALWAYS (like DevConsole) so the overlay's buttons still respond once the tree
## is paused. Restart resets the handful of stateful singletons and reloads the world scene.

signal ending_reached(outcome: String, result: Dictionary)

var _overlay: Control = null
var _overlay_box: VBoxContainer = null   # B3: the overlay's content column (payoff section mounts here)
var _last_result: Dictionary = {}
# A player death is a TERMINAL ending: once shown, neither a second down nor a later climax may replace
# it. The reverse is intentionally NOT latched — the climax resolver is fired repeatedly by tests and a
# real run only fires it once (SummoningPlan.climax_fired), so the climax path stays un-latched.
var _player_downed_shown: bool = false

func _ready() -> void:
	process_mode = Node.PROCESS_MODE_ALWAYS
	# B3 (retro): draw ABOVE the boot title (10) and pathway picker (11). On a full run-end the boot
	# controller raises the title UNDER this ending screen (run_ended fires while the overlay is up);
	# at the CanvasLayer default (1) the title covered the ending — the run payoff was never visible.
	# PauseMenu (9) already documents this stack: "below the EndGame overlay". Dev/GM chrome stays
	# above (GMPanel 85, DevConsole 128, IntroCard 200).
	layer = 12
	# Idempotent connect guard: keep the headless suite (which can fire the climax many times)
	# and any re-add from a world swap from double-connecting.
	if not SummoningPlan.summoning_climax.is_connected(_on_climax):
		SummoningPlan.summoning_climax.connect(_on_climax)
	# Full combat: a downed player proxy (agent_downed, target=="player") is its own immediate bad ending,
	# distinct from the strength-gated climax endings the resolver produces.
	if not EventBus.event_logged.is_connected(_on_event):
		EventBus.event_logged.connect(_on_event)
	# B3 (retro): the run-PAYOFF wire. RitualNight resolves screen-first (show_ritual_result), THEN
	# RunManager.end_run flushes the meta — so the payoff section is appended when run_ended lands,
	# reading meta_last_payoff() (recorded at the flush seam). Deferred: RunManager is a LATER
	# autoload than EndGame, so it does not exist yet during this _ready.
	_connect_run_payoff.call_deferred()

## B3: connect the payoff appender to RunManager.run_ended (idempotent; deferred from _ready).
func _connect_run_payoff() -> void:
	var rm := get_node_or_null("/root/RunManager")
	if rm != null and rm.has_signal("run_ended") and not rm.run_ended.is_connected(_on_run_ended_payoff):
		rm.run_ended.connect(_on_run_ended_payoff)

## B3: a FULL run-end (win/lose) landed while an ending overlay is up — append what the run's meta
## flush actually paid (currency delta + new unlock + new codex lines) so the win FEELS like it paid
## out. death/lost_control are within-run setbacks (no flush, no payoff) and are skipped.
func _on_run_ended_payoff(reason: String) -> void:
	if reason != "win" and reason != "lose":
		return
	if not is_instance_valid(_overlay):
		return
	_append_run_payoff()

## B3: build the payoff section from RunManager.meta_last_payoff() via the pure MetaSurface builder
## and mount it into the overlay's box, above the buttons row. Idempotent (replaces a prior section).
func _append_run_payoff() -> void:
	var rm := get_node_or_null("/root/RunManager")
	if rm == null or not rm.has_method("meta_last_payoff"):
		return
	var ms: GDScript = load("res://src/MetaSurface.gd") as GDScript
	if ms == null:
		return
	var vm: Dictionary = ms.payoff_model(rm.meta_last_payoff())
	if vm.is_empty():
		return
	if _overlay_box == null or not is_instance_valid(_overlay_box):
		return
	var old := _overlay_box.get_node_or_null("RunPayoff")
	if old != null:
		old.name = "RunPayoffStale"
		old.queue_free()
	var section := VBoxContainer.new()
	section.name = "RunPayoff"
	section.add_theme_constant_override("separation", 4)
	var head := Label.new()
	head.name = "PayoffHeader"
	head.text = String(vm.get("header", ""))
	head.horizontal_alignment = HORIZONTAL_ALIGNMENT_CENTER
	head.add_theme_font_size_override("font_size", 20)
	head.add_theme_color_override("font_color", Color(0.82, 0.66, 0.35, 1.0))   # the theme's gilt accent
	section.add_child(head)
	for l in vm.get("lines", []):
		var lab := Label.new()
		lab.text = String(l)
		lab.horizontal_alignment = HORIZONTAL_ALIGNMENT_CENTER
		lab.autowrap_mode = TextServer.AUTOWRAP_WORD_SMART
		lab.custom_minimum_size = Vector2(760, 0)
		lab.add_theme_color_override("font_color", Color(0.85, 0.8, 0.68, 1.0))
		section.add_child(lab)
	_overlay_box.add_child(section)
	# Sit between the ending body copy and the Restart/Quit buttons row.
	_overlay_box.move_child(section, _overlay_box.get_child_count() - 2)

func _on_event(event: Dictionary) -> void:
	# Cheap guard first — event_logged fires on EVERY world event, but we care about exactly one type.
	if String(event.get("type", "")) != "agent_downed":
		return
	if String((event.get("data", {}) as Dictionary).get("target", "")) == "player":
		player_downed()

## The player was struck down in combat. N2 (A1): ONE death path — RunManager owns the run OUTCOME
## (restore-to-checkpoint or full loss); EndGame owns only the SCREEN. The playtest blocker this
## fixes: this used to latch a dead-end overlay whose Restart wiped the whole run, while
## RunManager's "death" branch (the nightly-checkpoint restore) sat dead with no live caller.
##   * checkpoint exists -> a within-run SETBACK: end_run("death") restores the last nightly
##     checkpoint (the boot controller wakes the player at the safe house on run_ended), then a
##     Continue-style "death_wake" screen mirrors the lost_control flow. Not terminal, no latch.
##   * no checkpoint (day-1 pre-checkpoint) -> TERMINAL: the run is LOST. The screen shows first
##     (so the run_ended("lose") payoff section mounts onto it), then end_run("death") flushes the
##     meta and hands the boot controller back to the title. Latched: once this ending shows, a
##     later climax must not replace it.
func player_downed() -> void:
	if _player_downed_shown:
		return
	var rm := get_node_or_null("/root/RunManager")
	var in_run: bool = rm != null and rm.has_method("run_active") and bool(rm.run_active())
	if in_run and rm.has_method("has_checkpoint") and bool(rm.has_checkpoint()):
		# Restore FIRST (unpaused — the boot controller swaps the wake scene on run_ended), then
		# raise the Continue-style wake screen, exactly like Meters._end_rampage -> lost_control().
		rm.end_run("death", {"outcome": "player_downed"})
		_last_result = {"outcome": "death_wake"}
		ending_reached.emit("death_wake", _last_result)
		EventBus.emit_event("endgame", _last_result)
		get_tree().paused = true
		_show_overlay(_last_result)
		return
	_player_downed_shown = true
	_last_result = {"outcome": "player_downed"}
	ending_reached.emit("player_downed", _last_result)
	EventBus.emit_event("endgame", _last_result)
	get_tree().paused = true
	_show_overlay(_last_result)
	if in_run and rm.has_method("end_run"):
		rm.end_run("death", {"outcome": "player_downed"})

## The single climax handler. Resolve the ending, announce it, log it, freeze the world, show it.
func _on_climax(strength: float) -> void:
	if _player_downed_shown:
		return   # the player already fell — don't overwrite that ending with the summoning's outcome
	_last_result = EndGameResolver.resolve(strength)
	ending_reached.emit(String(_last_result["outcome"]), _last_result)
	EventBus.emit_event("endgame", _last_result)
	get_tree().paused = true
	_show_overlay(_last_result)

## M7 Ritual Night: the climax controller (RitualNight) resolved the encounter — show ITS win/lose
## screen. Distinct from the legacy strength-gated `_on_climax` path (the doomsday-timer resolver):
## the encounter reaches a concrete outcome (descent_complete / descent_stopped / avatar_slain), and
## this raises the matching overlay. Latched behind the terminal player-death like every ending, and
## re-armed by rearm() so a fresh run can reach the climax screen again.
func show_ritual_result(result: Dictionary) -> void:
	if _player_downed_shown:
		return
	if not (result is Dictionary) or String(result.get("outcome", "")) == "":
		return
	_last_result = result.duplicate(true)
	ending_reached.emit(String(_last_result.get("outcome", "")), _last_result)
	EventBus.emit_event("endgame", _last_result)
	get_tree().paused = true
	_show_overlay(_last_result)

## M9 Gap 4: the 60s Madness rampage expired — the investigator LOST CONTROL. Unlike a combat death
## (a terminal ending) this is a within-run setback: the run CONTINUES (RunManager already restored to
## the checkpoint / day-1 by the time this shows). So this raises a distinct "you lost control" beat
## with a single CONTINUE button that just lifts the freeze — symmetric with player_downed()'s screen
## but NOT terminal (it does not latch _player_downed_shown, and Continue resumes rather than restarts).
func lost_control() -> void:
	if _player_downed_shown:
		return   # already fell in combat this frame — that terminal screen wins
	_last_result = {"outcome": "lost_control"}
	ending_reached.emit("lost_control", _last_result)
	EventBus.emit_event("endgame", _last_result)
	get_tree().paused = true
	_show_overlay(_last_result)

## Re-arm the terminal player-death ending for a new run. Called by RunManager on start_run() so
## the run lifecycle owner controls when a fresh run may reach an ending again (M2: RunManager owns
## the reset; EndGame owns only the screen + this latch).
func rearm() -> void:
	_player_downed_shown = false

## Reset the stateful singletons so a restart begins a clean run. Autoloads persist across a
## scene reload, so they must be reset explicitly (the reload alone won't clear them).
##
## M2: RunManager.start_run() is now the single, authoritative run-reset seam (it scrubs the full
## run-scoped manifest — see RunManager._reset_run_world). Delegate to it so there is ONE reset
## path and no drift, and re-arm the terminal-death latch here.
func _reset_world_state() -> void:
	_player_downed_shown = false   # re-arm the terminal player-death ending for the new run
	var rm := get_node_or_null("/root/RunManager")
	if rm != null and rm.has_method("start_run"):
		rm.start_run()
	else:
		# Fallback (RunManager somehow absent): the original in-line reset, so EndGame stays usable
		# on its own (e.g. a lone-scene F6 run of the climax).
		SummoningPlan.reset()
		Overseer.reset()
		OccultToolManager.rebuild()
		Agents.rebuild()
		AgentRuntime.always_active.clear()
		Clock.set_time(1, 480)
		EventBus.clear()

## M9 Gap 4: dismiss a NON-terminal overlay (the lost_control setback). Drop the overlay and lift the
## freeze so the restored run resumes — no reset, no world reload (RunManager already restored the run
## and the boot controller already woke the player in the safe house on run_ended).
func dismiss() -> void:
	_hide_overlay()
	get_tree().paused = false

## The ending screen's action button. N2 (B-F3/B-F4): it RETURNS TO THE TITLE through the boot
## flow — it must NOT start_run() here. The old direct start_run double-counted runs_played (the
## title's New Run counts the real one), scrubbed the run codex ledger, and silently rerouted an
## unlocked-pathway (Hermit) player onto the Hunter default. The boot controller already raised
## the title under this overlay on the win/lose run_ended; return_to_title() is idempotent and
## re-affirms it. The next run starts ONLY through the real New Run flow / pathway picker.
func restart() -> void:
	_hide_overlay()
	get_tree().paused = false
	var gcs := get_tree().get_nodes_in_group("game_controller")
	var gc: Node = gcs[0] if gcs.size() > 0 else null
	if gc != null and gc.has_method("return_to_title"):
		gc.return_to_title()
		return
	# Fallback (no boot controller mounted — a lone-scene F6 run of the climax): the legacy
	# in-place world reset + reload, guarded for the headless harness (no current scene).
	_reset_world_state()
	if get_tree().current_scene != null:
		get_tree().reload_current_scene()

# --- Overlay ----------------------------------------------------------------------------------
## M10: true while an ending/setback overlay is mounted. The pause menu reads this to stay INERT
## during an ending (EndGame owns that freeze) — pause must never open over an ending screen.
func has_overlay() -> bool:
	return is_instance_valid(_overlay)

func _hide_overlay() -> void:
	if is_instance_valid(_overlay):
		_overlay.queue_free()
	_overlay = null
	_overlay_box = null

func _show_overlay(result: Dictionary) -> void:
	_hide_overlay()
	var copy: Dictionary = _ending_copy(result)

	var overlay := Control.new()
	overlay.name = "EndOverlay"
	overlay.set_anchors_preset(Control.PRESET_FULL_RECT)
	overlay.mouse_filter = Control.MOUSE_FILTER_STOP

	var dim := ColorRect.new()
	dim.color = Color(0.02, 0.02, 0.04, 0.9)
	dim.set_anchors_preset(Control.PRESET_FULL_RECT)
	overlay.add_child(dim)

	var center := CenterContainer.new()
	center.set_anchors_preset(Control.PRESET_FULL_RECT)
	overlay.add_child(center)

	var box := VBoxContainer.new()
	box.alignment = BoxContainer.ALIGNMENT_CENTER
	box.add_theme_constant_override("separation", 18)
	center.add_child(box)
	_overlay_box = box   # B3: the payoff section mounts into this column on run_ended

	var title := Label.new()
	title.text = String(copy["title"])
	title.horizontal_alignment = HORIZONTAL_ALIGNMENT_CENTER
	title.add_theme_font_size_override("font_size", 48)
	box.add_child(title)

	var body := Label.new()
	body.text = String(copy["body"])
	body.horizontal_alignment = HORIZONTAL_ALIGNMENT_CENTER
	body.autowrap_mode = TextServer.AUTOWRAP_WORD_SMART
	body.custom_minimum_size = Vector2(760, 0)
	box.add_child(body)

	var buttons := HBoxContainer.new()
	buttons.alignment = BoxContainer.ALIGNMENT_CENTER
	buttons.add_theme_constant_override("separation", 24)
	box.add_child(buttons)

	# M9 Gap 4 + N2: lost_control AND death_wake are within-run setbacks (the run continues, the
	# checkpoint restore already happened) — offer CONTINUE, which just lifts the freeze. Every
	# other outcome is a full run-end — offer Return to Title / Quit (N2 B-F3: the button hands
	# back to the boot title; it never starts a run itself).
	if String(result.get("outcome", "")) in ["lost_control", "death_wake"]:
		var cont_btn := Button.new()
		cont_btn.text = "Continue"
		cont_btn.custom_minimum_size = Vector2(200, 44)
		cont_btn.pressed.connect(dismiss)
		buttons.add_child(cont_btn)
	else:
		var restart_btn := Button.new()
		restart_btn.text = "Return to Title"
		restart_btn.custom_minimum_size = Vector2(200, 44)
		restart_btn.pressed.connect(restart)
		buttons.add_child(restart_btn)

		var quit_btn := Button.new()
		quit_btn.text = "Quit"
		quit_btn.custom_minimum_size = Vector2(160, 44)
		quit_btn.pressed.connect(func() -> void: get_tree().quit())
		buttons.add_child(quit_btn)

	add_child(overlay)
	_overlay = overlay

## Per-ending title + body. Keeps the canon beats: a completed descent (降临) is total; a stopped
## descent either kills the player (near-good) or lets them walk away (all-good).
func _ending_copy(result: Dictionary) -> Dictionary:
	match String(result.get("outcome", "")):
		"player_downed":
			return {
				"title": "Cut Down in the Dark",
				"body": "The cell falls on you before you can break the circle. The last thing you see is the chalk lines guttering alight — the rite goes on without you.",
			}
		"lost_control":
			return {
				"title": "You Lost Control",
				"body": "The Madness took the reins. For a while there was only the beast — and when you come back to yourself the day is gone, the trail cold. You wake in your lodging, hands shaking, the night wasted. (The day is lost; your progress holds.)",
			}
		"death_wake":
			return {
				"title": "Cut Down in the Dark",
				"body": "The blows drive you into the black, and the cobbles come up to meet you... but Tingen is not done with you. Someone hauls you off the street before the cell can finish its work. You wake at your lodging, wounds bound, the lost day gone cold. (The day is lost; your progress holds.)",
			}
		"city_dies":
			return {
				"title": "Tingen Falls",
				"body": "The descent (降临) completes. A light that is not light blooms over Tingen, and the city is unmade. No one was left to stop it.",
			}
		"near_good":
			return {
				"title": "The Line Holds",
				"body": "You break the summoning — but the backlash takes you with it. Tingen wakes to a grey dawn; you do not see it.\n(%d rounds fought)" % int(result.get("rounds", 0)),
			}
		"all_good":
			return {
				"title": "Dawn Over Tingen",
				"body": "The rite shatters and the descending god (外神) is denied. You walk out of the warehouse alive, into a city that will never know how close it came.\n(%d HP remaining)" % int(result.get("player_hp_left", 0)),
			}
		# --- M7 Ritual Night encounter outcomes (win by interrupt/avatar, lose by fuse) ---
		"descent_complete":
			return {
				"title": "Tingen Falls",
				"body": "The fuse burns out. The final beat of the rite lands, and the descent (降临) completes — a light that is not light blooms over the crypt, and the city is unmade. You were too slow.",
			}
		"descent_stopped":
			return {
				"title": "The Circle Breaks",
				"body": "You shatter the rite before the last beat. The gathered faithful lose control and come apart into things that were never people (§⑦) — and you cut the last of them down. The descending god (外神) is denied. Tingen wakes to a grey, ordinary dawn.",
			}
		"avatar_slain":
			return {
				"title": "The Half-Made God Falls",
				"body": "The avatar half-lands — one foot in the world, one still beyond — and in that window you strike it down before it can finish descending (§9). The rite collapses with it. Tingen holds.",
			}
		_:
			return {"title": "The End", "body": ""}
