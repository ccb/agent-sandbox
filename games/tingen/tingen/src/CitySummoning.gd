extends Node
## City.tscn summoning MVP bootstrap (issue #108).
##
## When the city runs as the main scene, this stages the LLM-driven cult around Saint Selena's
## Cathedral and kicks off the gather→deliver→rite loop: it stocks a supply cache of ritual offerings
## in the City, points the cult at it, keeps them ALWAYS deliberating so the summoning visibly races
## the player, and speeds the clock so a full descent plays out in a couple of minutes. Pure setup —
## it stages agent + world state once, then the agent runtime + sidecar + RoomView do the rest.
##
## Bodies are NOT spawned here anymore: RoomView (autoload) renders the cult in whatever room the
## player is standing in and follows them across the descent, so this only stages DATA. Likewise the
## demo state lives in autoloads (RoomItems cache, RoomView tracking, always_active, the sped clock),
## so it PERSISTS when City.tscn unloads as the player follows the cult into the cathedral.

## The rite is the REAL altar INSIDE CathedralCrypt.tscn. Targeting it makes the cult traverse the
## room graph City -> CathedralNave -> CathedralCrypt (tingen_scene_graph_design.md §4), crossing the
## same portals the player uses — instead of standing on a flat City-surface coordinate.
const RITE_SITE := "crypt_altar"
## WHO summons, WHERE they stand, WHAT the cache stocks, and the cult's marching orders are
## identity facts, so they live in data/scenario.json ("summoning" block) — engine code stays
## NPC-neutral (tingen_combat_implementation_plan.md §1) and stages whatever roster the
## scenario publishes. Hydrated once at script load (static init), so tests that read these
## straight off the loaded GDScript keep working.
const SCENARIO_PATH := "res://data/scenario.json"
static var _summoning: Dictionary = _load_summoning()
static var CULT: Array = _summoning.get("cult", [])
## Faster strides for the demo so the cult completes the multi-room journey well inside the doomsday
## countdown (default 48 px/beat would have them still walking when the clock runs out).
const DEMO_SPEED := 170.0

## The cult's supply cache: the offerings sit in the City, one at each cultist's feet so they grab it
## straight off the ground (the rendered pile visibly depletes as they pick it up). Carried down
## through the cathedral and laid at the crypt altar. Registered as a navigable (non-rite) location
## named 'ritual_cache' (its centroid) so a cultist can move_to it to fetch what's still missing.
const CACHE_NAME := "ritual_cache"
const CACHE_NAV_POS := Vector2(2110, 5455)   # centroid; the 'ritual_cache' move target

## Start spots on the plaza SOUTH of the Cathedral (Chapel @ ~(2118, 5015) — its nave collider
## reaches to y≈5414, so the plaza band starts below that) and north of the player start
## (~(1854, 5523)) — the cult is in frame from the off and converges up onto the chapel door.
## Legality (in-world + clear of every building collider) is asserted by
## _test_city_scene_placements_legal against the actual scene geometry.
static var SPOTS: Dictionary = _vec_map(_summoning.get("spots", {}))
## One offering at each cultist's feet (item id -> world pos) — so it's in gather reach from beat 1.
## The keys (each x1) define what the altar requires, so the cache exactly stocks the rite.
static var CACHE_ITEMS: Dictionary = _vec_map(_summoning.get("cache_items", {}))
## The cult's marching orders, verbatim from the scenario (two %s slots: cache name, rite site).
static var INTENT_TEMPLATE: String = String(_summoning.get("intent", ""))

static func _load_summoning() -> Dictionary:
	if not FileAccess.file_exists(SCENARIO_PATH):
		push_error("CitySummoning: missing %s" % SCENARIO_PATH)
		return {}
	var parsed: Variant = JSON.parse_string(FileAccess.get_file_as_string(SCENARIO_PATH))
	if typeof(parsed) != TYPE_DICTIONARY:
		push_error("CitySummoning: %s is not a JSON object" % SCENARIO_PATH)
		return {}
	return (parsed as Dictionary).get("summoning", {})

## JSON [x, y] pairs -> Vector2, keyed by id.
static func _vec_map(src: Dictionary) -> Dictionary:
	var out: Dictionary = {}
	for k in src:
		var arr: Array = src[k]
		out[String(k)] = Vector2(float(arr[0]), float(arr[1]))
	return out

func _ready() -> void:
	# AgentRegistry.rebuild() runs in its own _ready; wait a couple of frames so the cast exists.
	await get_tree().process_frame
	await get_tree().process_frame
	_bootstrap()

func _bootstrap() -> void:
	# Stage a fresh run ONLY when no summoning is already underway. If the player walks back into the
	# City mid-descent (re-instancing this scene), keep the run going — don't wipe the cache or reset
	# progress; just re-assert RoomView tracking. Keying on live SummoningPlan state (not a process-
	# static flag) means a genuine new game — which calls SummoningPlan.reset() — re-stocks correctly,
	# while a mid-run re-entry does not.
	var underway: bool = SummoningPlan.climax_fired \
		or SummoningPlan.countdown_beats < SummoningPlan.START_COUNTDOWN \
		or not SummoningPlan.deposited.is_empty()
	if underway:
		# RoomView tracks EVERYONE by default (empty tracked list = all non-player agents); re-assert
		# that default on re-entry in case something narrowed it, so cult AND civilians stay rendered.
		RoomView.set_tracked([])
		return
	# Watchable DEMO pacing: a deliberation beat every ~2.5s instead of every 15s, and longer strides
	# so the cross-room journey finishes inside the doomsday countdown. NOTE (P1): the run's Clock
	# pace (real_seconds_per_game_minute) is RunManager-owned — RUN_SECONDS_PER_GAME_MINUTE, applied
	# at run start — and must NEVER be set as a scene side-effect. This node's 0.5 override (dead/
	# unmounted since M20) was the only faster-pace setter, masking that live runs played at the slow
	# 1.0 default (~2.3x the ~60-min budget).
	Clock.minutes_per_beat = 5
	Agents.fallback_speed = DEMO_SPEED

	# The rite needs the offerings laid at the altar before it can advance — start from a clean ledger.
	# The requirement is exactly the cache contents (one of each offering).
	var requirement: Dictionary = {}
	for item_id in CACHE_ITEMS:
		requirement[item_id] = 1
	SummoningPlan.ritual_requirement = requirement
	SummoningPlan.deposited = {}

	# Drop each offering on the ground at its cultist's feet, and register the cache centroid as a
	# navigable location the cult can move_to to come back for anything still missing.
	# M13 FIX (review finding 1): The old RoomItems.clear() wiped ALL rooms — including the
	# cathedral_nave + cathedral_crypt ammo pickups seeded by RunManager._reset_run_world.
	# Clear ONLY the city room items, then re-place the cult cache AND city ammo pickups so
	# nothing is lost. Other rooms (cathedral_nave, cathedral_crypt) are untouched.
	_clear_room("city")
	var ammo_node: Node = _al("AmmoSpawn")
	if ammo_node != null and ammo_node.has_method("seed_run_room"):
		ammo_node.seed_run_room("city", 0)
	ActionCommit.set_nav_site(CACHE_NAME, CACHE_NAV_POS, "city")
	for item_id in CACHE_ITEMS:
		RoomItems.place("city", item_id, CACHE_ITEMS[item_id], 1)

	var staged := 0
	for id in CULT:
		var a = Agents.get_agent(id)
		if a == null:
			push_warning("CitySummoning: no agent '%s'" % id)
			continue
		var pos: Vector2 = SPOTS.get(id, Vector2(2118, 5440))
		a.position = pos
		a.room = "city"   # they start in the City and descend through the cathedral to the crypt
		a.carry_capacity = 2
		a.intent = INTENT_TEMPLATE % [CACHE_NAME, RITE_SITE]
		AgentRuntime.always_active[id] = true
		staged += 1

	# RoomView (autoload) owns rendering: it spawns/follows/despawns bodies in whatever room the
	# player is currently in — so following the cult into the crypt shows them — and renders the
	# ground offerings. It persists across scene swaps, so the descent stays visible. Its DEFAULT
	# (empty tracked list) tracks EVERY registered non-player agent, so the civilian roster renders
	# alongside the cult; re-assert that default here rather than narrowing to CULT.
	RoomView.set_tracked([])

	print("[CitySummoning] staged %d cult agents; cache '%s' @ %s (%d offerings); rite site '%s' @ %s"
		% [staged, CACHE_NAME, str(CACHE_NAV_POS), CACHE_ITEMS.size(), RITE_SITE, str(ActionCommit.SITES.get(RITE_SITE, Vector2.ZERO))])

	# Headless visibility into the descent: every rite step the cult lands moves the countdown, and
	# zero is the climax. Lets a no-window run prove the brain actually drove the rite home.
	SummoningPlan.countdown_changed.connect(func(n: int) -> void:
		print("[CitySummoning] rite advanced -> countdown %d" % n))
	SummoningPlan.summoning_climax.connect(func(strength: float) -> void:
		print("[CitySummoning] *** DESCENT COMPLETE — summoning_climax strength=%.2f ***" % strength))

## The demo deliberately does NOT tear down on City unload: the cult, the sped clock, the cache, and
## RoomView tracking all live in autoloads so the summoning keeps racing — and stays rendered — as the
## player follows the cult down into the cathedral. (A fresh run resets it by relaunching the scene.)
func _exit_tree() -> void:
	pass

## Clear all ground items in ONE room only. Used by _bootstrap to wipe the city before re-seeding,
## without touching cathedral_nave / cathedral_crypt (where the M13 ammo pickups live).
func _clear_room(room_id: String) -> void:
	var ri: Node = _al("RoomItems")
	if ri == null:
		return
	var items: Array = (ri.items_in(room_id) as Array).duplicate()
	for e in items:
		var qty: int = int((e as Dictionary).get("qty", 0))
		var pos: Vector2 = (e as Dictionary).get("pos", Vector2.ZERO)
		var iid: String = String((e as Dictionary).get("item_id", ""))
		for _i in qty:
			ri.take_near(room_id, iid, pos, 4.0)

func _al(autoload_name: String) -> Node:
	var ml := Engine.get_main_loop()
	if ml == null or not (ml is SceneTree):
		return null
	return (ml as SceneTree).root.get_node_or_null(autoload_name)
