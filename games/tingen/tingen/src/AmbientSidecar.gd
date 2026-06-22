class_name AmbientSidecar
extends MockSidecar
## Offline "living world" brain — the live default until HttpSidecar (the real LLM) is wired.
## MockSidecar idles every unscripted actor, so active agents near the player freeze while only
## far ones (schedule fallback) move; the district looks dead. AmbientSidecar instead gives every
## agent a faction-appropriate goal each beat: cultists (cult 教徒) converge on the rite site, and
## everyone else drifts along their daily schedule. A small deterministic per-agent/per-beat
## scatter keeps the crowd from stacking on a single pixel and reads as milling/loitering.
##
## It extends MockSidecar (not SidecarClient) to inherit the deterministic prayer adjudication, so
## the player's prayers still resolve correctly under the live brain. Only `propose` is replaced;
## `scripted` is ignored. Every output is a pure function of (snapshot, beat) — same inputs give
## the same proposal — so the world is reproducible and the behavior is unit-testable.

## Mirrors ActionCommit.SITES.iron_cross_warehouse — the descending god's rite pulls the faithful in.
## static var (not const) so it can be computed from MapProjection's transform.
static var WAREHOUSE: Vector2 = MapProjection.map_to_world(MapProjection.WAREHOUSE_MAP)
const WANDER: float = 28.0   # px of deterministic per-beat scatter around a goal

## The four-step descent litany, mirroring data/rituals.json summoning_descent. Cycled by beat so
## the rite visibly progresses while staying deterministic; the line is flavor, the clock effect
## (one beat off the countdown, applied in ActionCommit) is independent of which step shows.
const RITE_STEPS: Array = [
	"Inscribe the consecrated circle in chalk.",
	"Set and light the three candles at its points.",
	"Lay the salt wards and speak the descending name.",
	"Offer the marked sacrifice to open the gate.",
]

func propose(snapshots: Array) -> Array:
	var out: Array = []
	for s in snapshots:
		out.append(_decide(s as Dictionary))
	return out

func _decide(snap: Dictionary) -> Dictionary:
	var actor := String(snap.get("agent_id", ""))
	var faction := String(snap.get("faction", ""))
	var beat := int(snap.get("beat", 0))
	# A cultist who has reached the rite site works the ritual instead of milling about — and that
	# drives the summoning clock (ActionCommit.perform_ritual_step). Until they arrive they keep
	# converging on the warehouse, so you watch them gather, then watch the descent quicken.
	if _is_cult(faction) and _at_rite(snap):
		return {
			"actor": actor,
			"verb": "perform_ritual_step",
			"args": {"step": _rite_step(beat)},
			"thought": "The descent draws nearer by my hand.",
		}
	var goal: Vector2 = _goal_for(actor, faction, snap) + _scatter(actor, beat)
	# Encode the goal as an "x,y" target so ActionCommit resolves it without a named site.
	return {
		"actor": actor,
		"verb": "move_to",
		"args": {"target": "%.1f,%.1f" % [goal.x, goal.y]},
		"thought": _thought_for(faction),
	}

## True when the agent already stands within rite range of the warehouse — the same threshold the
## commit step enforces (ActionCommit.RITE_RADIUS), so the brain never proposes a rite that wouldn't
## actually bite the clock.
func _at_rite(snap: Dictionary) -> bool:
	return _vec(snap.get("position", [0, 0])).distance_to(WAREHOUSE) <= ActionCommit.RITE_RADIUS

## Pick the descent step for this beat — cycles the litany so the rite reads as progressing, and is
## a pure function of beat so the same beat replays identically.
func _rite_step(beat: int) -> String:
	return String(RITE_STEPS[posmod(beat, RITE_STEPS.size())])

func _goal_for(actor: String, faction: String, snap: Dictionary) -> Vector2:
	if _is_cult(faction):
		return WAREHOUSE
	return _schedule_goal(actor, snap)

func _is_cult(faction: String) -> bool:
	return faction.to_lower().contains("cult")

## Where a non-cult agent is headed: its scheduled waypoint for the current phase. Falls back to
## holding position (+scatter) when the agent has no schedule entry, so it still reads as alive.
func _schedule_goal(actor: String, snap: Dictionary) -> Vector2:
	var wp: Vector2 = _al("NpcDB").waypoint_for(actor, String(snap.get("phase", "")))
	if wp == Vector2.ZERO:
		return _vec(snap.get("position", [0, 0]))
	return wp

## Deterministic per-agent, per-beat offset in roughly [-WANDER, WANDER] on each axis. A pure hash
## of (actor, beat) so the same beat replays identically while the crowd still spreads out.
func _scatter(actor: String, beat: int) -> Vector2:
	var fx := float(absi(hash(actor + "|x|" + str(beat)) % 2001)) / 1000.0 - 1.0
	var fy := float(absi(hash(actor + "|y|" + str(beat)) % 2001)) / 1000.0 - 1.0
	return Vector2(fx, fy) * WANDER

func _thought_for(faction: String) -> String:
	return "The rite needs me at the warehouse." if _is_cult(faction) else "Going about my day."

func _vec(v: Variant) -> Vector2:
	if typeof(v) == TYPE_ARRAY and (v as Array).size() >= 2:
		return Vector2(float(v[0]), float(v[1]))
	return Vector2.ZERO

## Resolve an autoload by name — direct `NpcDB.` references fail to compile in a class_name script
## under the headless -s harness (autoloads register after class_name scripts parse).
func _al(autoload_name: String) -> Node:
	return (Engine.get_main_loop() as SceneTree).root.get_node("/root/" + autoload_name)
