extends Node
## The Ritual Night climax controller (autoload `RitualNight`) — M7, direction v2 §9 / §13.
##
## The climax is the ASSEMBLY of systems M2–M6 already built, not a new engine. This node is the
## thin conductor that:
##   * STARTS the encounter when Doom hits 100 (Meters.ritual_night) OR the player force-assaults
##     the ritual site early (§13 #7). On an early assault while the cult was TIPPED (a scouting
##     flag), the site RELOCATES ONCE as counterplay (a seeded swap to another room).
##   * stages the crypt encounter DATA (a celebrant agent, N defenders per door, an altar interrupt
##     flag) from scenario.json — engine code stays NPC-neutral.
##   * runs the FUSE: a descent countdown in beats. Reaching 0 un-interrupted -> the descent
##     completes -> LOSE (RunManager.end_run('lose') + a lose ending).
##   * on INTERRUPT (the altar interactable flips a SummoningPlan flag, OR the celebrant is downed):
##     the surviving celebrants LOSE CONTROL and assume_form into monsters (canon §⑦) — the BACKLASH
##     wave. Surviving/clearing it -> WIN.
##   * if the fuse crosses a LOW threshold before interrupt, the avatar HALF-LANDS as a boss
##     combat_form (descended_avatar, a two-stage assume_form descent). Killing it in its window ->
##     WIN (the canon 'kill the avatar before full descent').
##   * every outcome resolves EXACTLY ONCE to RunManager.end_run('win'/'lose') and a result screen
##     via EndGame — NO softlock (fixes GAP-2.11).
##
## Determinism: which door is guarded / where the site relocates is driven by the run seed passed in
## (never RNG-in-combat). The combat transcript itself is untouched — this only stages agents and
## reads their downed state; combat_sim / run_combat_vectors stay byte-identical.
##
## Headless: everything here is data + agent staging + explicit stepping (tick_fuse, notify_agent_
## downed, clear_backlash_wave), so tests stage the crypt state and step it with no display.

signal ritual_night_started(site_room: String, early: bool)
signal fuse_changed(beats_left: int)
signal backlash_fuse_changed(beats_left: int)
signal rite_interrupted(via: String)
signal avatar_half_landed(avatar_id: String)
signal backlash_spawned(monster_ids: Array)
signal climax_resolved(outcome: String)

const SCENARIO_PATH := "res://data/scenario.json"

# --- authored config (scenario.json "ritual_night") -------------------------------------------
var _site_room: String = "cathedral_crypt"
## N2 (A4): the AUTHORED site room, remembered at config load — a tipped-relocation mutates
## _site_room in place, so reset() must restore THIS (it used to leak the relocated crypt into
## every later run: the site never came home).
var _site_room_default: String = "cathedral_crypt"
var _celebrant_tpl: String = "clerk_voss"
var _fuse_beats_start: int = 12
var _avatar_threshold: int = 3
var _door_defenders: Dictionary = {"front": 3, "side": 1}
var _relocate_rooms: Array = []
var _avatar_form: String = "descended_avatar"
var _backlash_form: String = "cult_thrall"
# N6 (B2+B3): the door defenders' human-phase form — DATA (scenario.json ritual_night.
# defender_form); the fallback matches the shipped scenario row so a config-less test
# still stages the diegetic roster.
var _defender_form: String = "cult_guard"
var _backlash_extra: int = 2
# M22 B9: the backlash wave's own BACKSTOP countdown (beats). The main fuse FREEZES on interrupt
# (an interrupted rite can never fire its climax), so before this a player who interrupts but cannot
# clear the wave (e.g. a 0-ammo player with no damage art) had NO clock forcing any ending -> a hard
# softlock. This backstop guarantees the interrupted climax ALWAYS resolves: if the wave is not
# cleared within this many beats of the interrupt, the rite's stored power completes -> LOSE. TUNING
# placeholder — 10 beats (generous enough for a competent clear, bounded so an abandon still ends).
var _backlash_beats: int = 10

# --- live encounter state ---------------------------------------------------------------------
var _active: bool = false
var _resolved: bool = false
var _tipped: bool = false
var _relocated: bool = false
var _door: String = "front"
var _seed: int = 0

var _fuse: int = 0
var _backlash_fuse: int = 0
var _interrupted: bool = false
var _backlash_active: bool = false
var _avatar_present: bool = false

var _celebrant_id: String = ""
var _avatar_id: String = ""
var _defender_ids: Array = []
var _backlash_ids: Array = []

var _result: Dictionary = {}

func _ready() -> void:
	_load_config()
	# Doom topping out is the canonical trigger (§9). Meters fires `ritual_night` once at Doom 100.
	if Meters != null and not Meters.ritual_night.is_connected(_on_doom_ritual_night):
		Meters.ritual_night.connect(_on_doom_ritual_night)
	# A celebrant/avatar felled in real combat routes an agent_downed event — the interrupt/avatar
	# WIN hooks read it, so a live fight resolves the climax the same way the headless notify does.
	if EventBus != null and not EventBus.event_logged.is_connected(_on_world_event):
		EventBus.event_logged.connect(_on_world_event)
	# The LIVE fuse: once the climax is active, each Clock beat burns one beat of the descent timer
	# (the fuse). Headless tests drive tick_fuse directly instead; this only fires while _active, so
	# it's inert outside the climax and byte-identical for the sims (which never start a climax).
	if Clock != null and not Clock.beat_ticked.is_connected(_on_beat):
		Clock.beat_ticked.connect(_on_beat)

## The live fuse driver: one Clock beat burns one beat of the descent timer while the climax is
## live. Inert outside the climax (and so for the headless sims, which never start one).
func _on_beat(_beat_index: int, _day: int) -> void:
	if not _active or _resolved:
		return
	if not _interrupted:
		tick_fuse(1)
	elif _backlash_active:
		# M22 B9: once interrupted the descent fuse freezes, so the BACKLASH backstop takes over —
		# each beat burns one beat of the wave's window; abandoning it (never clearing) still ends.
		tick_backlash(1)

func _load_config() -> void:
	if not FileAccess.file_exists(SCENARIO_PATH):
		return
	var parsed: Variant = JSON.parse_string(FileAccess.get_file_as_string(SCENARIO_PATH))
	if not (parsed is Dictionary):
		return
	var rn: Dictionary = (parsed as Dictionary).get("ritual_night", {})
	if rn.is_empty():
		return
	_site_room = String(rn.get("site_room", _site_room))
	_site_room_default = _site_room   # N2 (A4): the authored home reset() restores
	_celebrant_tpl = String(rn.get("celebrant", _celebrant_tpl))
	_fuse_beats_start = int(rn.get("fuse_beats", _fuse_beats_start))
	_avatar_threshold = int(rn.get("avatar_threshold", _avatar_threshold))
	var doors: Dictionary = rn.get("doors", {})
	for d in doors:
		_door_defenders[String(d)] = int((doors[d] as Dictionary).get("defenders", 1))
	_relocate_rooms = (rn.get("relocate_rooms", []) as Array).duplicate()
	_avatar_form = String(rn.get("avatar_form", _avatar_form))
	_backlash_form = String(rn.get("backlash_form", _backlash_form))
	_defender_form = String(rn.get("defender_form", _defender_form))
	_backlash_extra = int(rn.get("backlash_extra", _backlash_extra))
	_backlash_beats = int(rn.get("backlash_beats", _backlash_beats))   # M22 B9 backstop window

# --- lifecycle / reset ------------------------------------------------------------------------
## Scrub the climax back to run-start. Called by RunManager._reset_run_world (a fresh run must not
## inherit a prior Ritual Night) and by the harness between cases.
func reset() -> void:
	_active = false
	_resolved = false
	_tipped = false
	_relocated = false
	# N2 (A4): a tipped-relocation moved the site in place — bring it home to the AUTHORED room,
	# else the relocated crypt leaks into every later run (reset cleared _relocated but not the room).
	_site_room = _site_room_default
	_door = "front"
	_seed = 0
	_fuse = 0
	_backlash_fuse = 0
	_interrupted = false
	_backlash_active = false
	_avatar_present = false
	_celebrant_id = ""
	_avatar_id = ""
	_defender_ids = []
	_backlash_ids = []
	_result = {}

# --- triggers ---------------------------------------------------------------------------------
## The Doom-100 trigger (§9). Meters latches Ritual Night; here we START the encounter proper.
## Doom 100 is the "full timer ran out" case — never an early assault, never tipped-relocation.
func _on_doom_ritual_night() -> void:
	if _active or _resolved:
		return
	var rm := _rm()
	if rm != null and not rm.run_active():
		return
	_begin(false, "front", int(_run_seed()))

## The player force-assaults the ritual site early (§13 #7 — ALLOWED). `early` marks it as an
## early assault (vs the Doom-100 fill); `door` picks the entry portal (front = guarded, side =
## quiet). A tipped early assault relocates the site once before staging.
func force_assault(early: bool, seed_val: int, door: String = "front") -> void:
	if _active or _resolved:
		return
	_begin(early, door, seed_val)

## The trigger latch is set (by Meters) but the player hasn't reached the site — used by the HUD/
## gating to know the fuse is lit. True once the encounter is staged.
func active() -> bool:
	return _active

func resolved() -> bool:
	return _resolved

func set_tipped(v: bool) -> void:
	_tipped = v

func tipped() -> bool:
	return _tipped

func relocated() -> bool:
	return _relocated

func _begin(early: bool, door: String, seed_val: int) -> void:
	_active = true
	_resolved = false
	_seed = seed_val
	_door = door if _door_defenders.has(door) else "front"
	_interrupted = false
	_backlash_active = false
	_avatar_present = false
	_fuse = _fuse_beats_start
	_backlash_fuse = 0
	# Counterplay (§1): an EARLY assault while the cult was TIPPED relocates the site ONCE. The swap
	# is seed-driven (deterministic), never RNG.
	if early and _tipped and not _relocated and not _relocate_rooms.is_empty():
		var idx := int(abs(seed_val)) % _relocate_rooms.size()
		_site_room = String(_relocate_rooms[idx])
		_relocated = true
	_stage_encounter()
	ritual_night_started.emit(_site_room, early)

# --- crypt encounter staging (data-driven; agents only) ---------------------------------------
## Stage the celebrant + the door's defenders as agents in the site room. Pure DATA staging — no
## scene work (RoomView renders whatever room the player is in). The altar interrupt interactable
## and the two portals live in the scene (CathedralCrypt.tscn); this owns the agent roster.
func _stage_encounter() -> void:
	var reg := _al("Agents")
	if reg == null:
		return
	# The celebrant: reuse the scenario's celebrant NPC if it's on the roster, else spawn a proxy.
	var celebrant: Agent = reg.get_agent(_celebrant_tpl)
	if celebrant == null:
		celebrant = _spawn_agent("ritual_celebrant", "butcher_human")
	_celebrant_id = celebrant.id
	celebrant.room = _site_room
	celebrant.hp = celebrant.max_hp
	celebrant.downed = false
	# The door's defenders (front guarded vs side quiet — different counts, §2).
	var n := int(_door_defenders.get(_door, 1))
	_defender_ids = []
	for i in range(n):
		var d := _spawn_agent("ritual_defender_%d" % i, _defender_form)
		d.room = _site_room
		_defender_ids.append(d.id)

func _spawn_agent(id: String, form: String) -> Agent:
	var reg := _al("Agents")
	var a: Agent = reg.get_agent(id)
	if a == null:
		a = Agent.new(id)
		# N6 (B2): a runtime spawn with no npcs.json name reads DIEGETIC off its form's
		# data display_name ("Cult defender"), the raw id only as the last fallback.
		var adb := _al("AbilityDB")
		var dn: String = String(adb.form_display_name(form)) if adb != null else ""
		a.display_name = dn if dn != "" else id
		reg.register_agent(a)
	a.combat_form = form
	a.hp = a.max_hp
	a.downed = false
	a.room = _site_room
	return a

# --- entry doors (§2) -------------------------------------------------------------------------
func site_room() -> String:
	return _site_room

## How many cult defenders the CHOSEN entry door fields (front > side). The scene reuses the two
## crypt portals; the player's door pick lands here.
func defender_count() -> int:
	return _defender_ids.size()

func door() -> String:
	return _door

# --- the fuse (§3) ----------------------------------------------------------------------------
func fuse_remaining() -> int:
	return _fuse

func avatar_threshold() -> int:
	return _avatar_threshold

## Advance the descent fuse by `beats`. Clamps at zero. Crossing the low threshold half-lands the
## avatar; reaching zero un-interrupted completes the descent -> LOSE. Idempotent once resolved.
## The live tree drives this off Clock beats; the harness calls it directly.
func tick_fuse(beats: int = 1) -> void:
	if not _active or _resolved or _interrupted:
		return
	if beats <= 0:
		return
	_fuse = maxi(0, _fuse - beats)
	fuse_changed.emit(_fuse)
	# The avatar half-lands the moment the fuse drops to/below the low threshold (but not at zero,
	# which is the full descent -> lose).
	if _fuse <= _avatar_threshold and _fuse > 0 and not _avatar_present:
		_half_land_avatar()
	if _fuse <= 0:
		_lose("descent_complete")

## The avatar HALF-LANDS (§5): a descended_avatar boss enters the site as an agent. Killing it in
## this window wins; letting the fuse hit zero still loses.
func _half_land_avatar() -> void:
	if _avatar_present:
		return
	_avatar_present = true
	var a := _spawn_agent("descended_avatar", _avatar_form)
	_avatar_id = a.id
	avatar_half_landed.emit(_avatar_id)

func avatar_present() -> bool:
	return _avatar_present

func avatar_id() -> String:
	return _avatar_id

# --- interrupt = WIN path (§4) ----------------------------------------------------------------
## The altar interrupt interactable (break the altar / destroy the vessel): flips the SummoningPlan
## interrupt flag and triggers the backlash. One of the two authored WIN inputs.
func use_interrupt_interactable() -> void:
	_interrupt("altar")

## Reaching the celebrant and downing them (combat) also interrupts the rite (§4).
func celebrant_id() -> String:
	return _celebrant_id

## Route an agent_downed into the climax hooks: the celebrant downed -> interrupt; the avatar
## downed in its window -> avatar_slain WIN. The live path calls this via the EventBus listener;
## the harness calls it directly after take_damage.
func notify_agent_downed(id: String) -> void:
	if not _active or _resolved:
		return
	if id == _avatar_id and _avatar_present:
		_win("avatar_slain")
		return
	if id == _celebrant_id and not _interrupted:
		_interrupt("celebrant_downed")

func _interrupt(via: String) -> void:
	if not _active or _resolved or _interrupted:
		return
	_interrupted = true
	# Flip the cult's own rite flag so the summoning engine agrees the rite is broken — an
	# interrupted rite can never fire its climax (SummoningPlan.climax_fired latch stays honest).
	if SummoningPlan != null:
		SummoningPlan.climax_fired = true
	rite_interrupted.emit(via)
	_spawn_backlash_wave()

# --- backlash wave (§6) -----------------------------------------------------------------------
## On interrupt the surviving celebrants LOSE CONTROL (canon §⑦) -> assume_form into monsters. The
## final wave the player must SURVIVE. Every still-standing cult body (celebrant + defenders) sheds
## into the backlash form via the transform seam, plus a couple of extra thralls the rite tears
## loose. Downing/surviving them all completes the WIN.
func _spawn_backlash_wave() -> void:
	if _backlash_active:
		return
	_backlash_active = true
	# M22 B9: arm the backstop the moment the wave spawns — an interrupted climax now always has a
	# clock running toward an ending even if the player can never down a single backlash monster.
	_backlash_fuse = _backlash_beats
	backlash_fuse_changed.emit(_backlash_fuse)
	_backlash_ids = []
	var reg := _al("Agents")
	if reg == null:
		return
	var survivors: Array = []
	survivors.append_array(_defender_ids)
	survivors.append(_celebrant_id)
	for id in survivors:
		var a: Agent = reg.get_agent(id)
		if a == null or a.downed:
			continue
		# LOSE CONTROL: assume_form into the monster (canon §⑦). The transform is the ONLY
		# transformation seam (constraint): swap combat_form to the backlash monster form + flag
		# combat, and announce it exactly like the executor's assume_form block does.
		a.combat_form = _backlash_form
		a.in_combat = true
		if EventBus != null:
			EventBus.emit_event("transformed", {"agent": a.id, "form": _backlash_form})
		_backlash_ids.append(a.id)
	# A couple of extra thralls the backlash tears loose (the rite's stored power lashing out).
	for i in range(_backlash_extra):
		var t := _spawn_agent("backlash_thrall_%d" % i, _backlash_form)
		t.in_combat = true
		if EventBus != null:
			EventBus.emit_event("transformed", {"agent": t.id, "form": _backlash_form})
		_backlash_ids.append(t.id)
	backlash_spawned.emit(_backlash_ids)

func backlash_active() -> bool:
	return _backlash_active

## M22 B9: beats remaining on the backlash backstop (0 outside an interrupted wave). HUD/gating read.
func backlash_fuse_remaining() -> int:
	return _backlash_fuse

## M22 B9: advance the backlash BACKSTOP by `beats`. Only runs during an un-resolved interrupted
## wave. If the wave is ALREADY cleared, this is inert (the WIN path owns that outcome — the backstop
## never overrides a survived wave). Reaching zero un-cleared completes the rite's stored power ->
## LOSE, so an interrupted-then-abandoned climax ALWAYS resolves to an ending (no softlock). The live
## tree drives this off Clock beats after the interrupt; the harness calls it directly. Idempotent
## once resolved.
func tick_backlash(beats: int = 1) -> void:
	if not _active or _resolved or not _interrupted or not _backlash_active:
		return
	if beats <= 0:
		return
	# A wave already cleared resolves as a WIN elsewhere — never let the backstop steal that ending.
	if backlash_cleared():
		return
	_backlash_fuse = maxi(0, _backlash_fuse - beats)
	backlash_fuse_changed.emit(_backlash_fuse)
	if _backlash_fuse <= 0:
		_lose("backlash_overrun")

func interrupted() -> bool:
	return _interrupted

## The agent ids of the backlash monsters (celebrants that lost control + torn-loose thralls).
func backlash_monsters() -> Array:
	return _backlash_ids.duplicate()

## True once every backlash monster is downed (the wave is cleared). The live combat path downs
## them one by one (agent_downed events); this is the survive-check.
func backlash_cleared() -> bool:
	if not _backlash_active:
		return false
	var reg := _al("Agents")
	if reg == null:
		return true
	for id in _backlash_ids:
		var a: Agent = reg.get_agent(id)
		if a != null and not a.downed:
			return false
	return true

## Down every remaining backlash monster and resolve the WIN. The live encounter reaches this by
## the player clearing the wave in combat (each kill routes agent_downed -> _on_world_event, which
## calls _win once the last falls); the harness calls this to close the wave deterministically.
func clear_backlash_wave() -> void:
	if not _active or _resolved:
		return
	if not _backlash_active:
		# An interrupt must precede the wave; guard against a bare clear call.
		return
	var reg := _al("Agents")
	if reg != null:
		for id in _backlash_ids:
			var a: Agent = reg.get_agent(id)
			if a != null and not a.downed:
				a.downed = true
	_win("descent_stopped")

# --- resolution (§7 — every outcome reaches an ending, NO softlock) ---------------------------
func _win(outcome: String) -> void:
	if _resolved:
		return
	_resolve("win", outcome)

func _lose(outcome: String) -> void:
	if _resolved:
		return
	_resolve("lose", outcome)

## The single resolution seam. Latches resolved (so no second ending fires — no double-end, no
## softlock), records the result, raises the EndGame screen with the climax copy, and ends the run.
func _resolve(reason: String, outcome: String) -> void:
	_resolved = true
	_active = false
	_result = {"outcome": outcome, "reason": reason, "site_room": _site_room, "door": _door}
	climax_resolved.emit(outcome)
	# The climax SCREEN (EndGame owns it): show the win/lose result. EndGame freezes + overlays.
	var eg := _al("EndGame")
	if eg != null and eg.has_method("show_ritual_result"):
		eg.show_ritual_result(_result)
	# The run OUTCOME (RunManager owns it): end the run win/lose -> meta -> title. Exactly once. M27:
	# pass the concrete climax OUTCOME (avatar_slain / descent_stopped / descent_complete) so the meta
	# payoff (codex / Fool unlock / differential currency) can key off which grade of win/lose this was.
	var rm := _rm()
	if rm != null:
		rm.end_run(reason, {"outcome": outcome})

func result() -> Dictionary:
	return _result.duplicate(true)

# --- live combat routing ----------------------------------------------------------------------
## The live agent_downed ear: a felled celebrant/avatar/backlash-monster resolves the climax the
## same way the headless notify_agent_downed does, so a real fight reaches an ending.
func _on_world_event(ev: Dictionary) -> void:
	if not _active or _resolved:
		return
	if String(ev.get("type", "")) != "agent_downed":
		return
	var d: Dictionary = ev.get("data", {}) if ev.get("data") is Dictionary else {}
	var target := String(d.get("target", ""))
	if target == "":
		return
	notify_agent_downed(target)
	# A backlash monster falling: when it was the LAST standing, the wave is cleared -> WIN.
	if _backlash_active and _backlash_ids.has(target) and backlash_cleared():
		_win("descent_stopped")

# --- helpers ----------------------------------------------------------------------------------
func _rm() -> Node:
	return _al("RunManager")

## The deterministic per-run seed the strategic slots use (WorldManager.seed_value), so a live
## Doom-100 trigger's which-door/relocation is reproducible per run.
func _run_seed() -> int:
	var wm := _al("WorldManager")
	if wm != null and "seed_value" in wm:
		return int(wm.seed_value)
	return 0

func _al(autoload_name: String) -> Node:
	var ml := Engine.get_main_loop()
	if ml == null or not (ml is SceneTree):
		return null
	return (ml as SceneTree).root.get_node_or_null(autoload_name)
