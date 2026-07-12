class_name AmbientSidecar
extends MockSidecar
## Offline "living world" brain — the live default until HttpSidecar (the real LLM) is wired.
## MockSidecar idles every unscripted actor, so active agents near the player freeze while only
## far ones (schedule fallback) move; the district looks dead. AmbientSidecar instead gives every
## agent a task-appropriate goal each beat: a task-bearer converges on its rite site, and
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
	"Set and light the candle at the circle's point.",
	"Lay the salt wards and speak the descending name.",
	"Offer the marked sacrifice to open the gate.",
]

func propose(snapshots: Array) -> Array:
	var out: Array = []
	for s in snapshots:
		out.append(_decide(s as Dictionary))
	return out

## Offline conversation: a no-LLM stand-in that ACKNOWLEDGES the player's line and VARIES by turn, so
## talking to an NPC in the no-API build visibly progresses instead of repeating one canned greeting (the
## rich, in-character path is HttpSidecar.converse, where wariness/secrecy emerge from persona). It reads
## the request the same fields the live brain gets — the player's `utterance` and the dialogue `history`
## (whose length is the turn counter) — and is a pure function of them, so it stays deterministic and
## unit-testable, never empty (no dead panel), with no group/faction branching.
func converse(request: Dictionary) -> Dictionary:
	var p: Dictionary = request.get("perception", {})
	var who := String(p.get("display_name", "They"))
	var utter := String(request.get("utterance", "")).strip_edges()
	# Turn counter: each completed turn appends to history, so its size advances the beat past the opener.
	var turn := int((request.get("history", []) as Array).size())
	# The opening approach (empty player line) gets a greeting; thereafter the NPC answers the LINE the
	# player just typed, echoing a fragment of it so the player sees their utterance landed and the panel
	# moves. The closing line cycles by turn so successive sends never read identical.
	var say: String
	if utter == "":
		say = "%s gives you a guarded nod. \"Cold night for questions, isn't it?\"" % who
	else:
		say = "%s weighs your words — \"%s\" — then %s" % [who, _echo(utter), _follow(turn)]
	return {
		"say": say,
		"action": null,
		"replies": _replies_for(turn),
	}

## Echo a short, safe fragment of the player's line back so the offline reply demonstrably depends on it.
func _echo(utterance: String) -> String:
	var t := utterance.strip_edges()
	return t if t.length() <= 48 else t.substr(0, 45) + "..."

## A varying tail keyed on the turn so the offline NPC's line changes every send (it must not read frozen).
func _follow(turn: int) -> String:
	var tails: Array = [
		"answers carefully. \"Maybe. Maybe not. Hard to say in this district.\"",
		"glances down the street before replying. \"You keep asking. I keep wondering why.\"",
		"lowers their voice. \"Some things are better left where they lie.\"",
		"shrugs. \"I've told you what I can. The rest you'll have to find yourself.\"",
	]
	return String(tails[posmod(turn, tails.size())])

## Reply chips that also rotate by turn, so the offered follow-ups move with the conversation.
func _replies_for(turn: int) -> Array:
	var banks: Array = [
		[{"id": "ask", "text": "Have you seen anything strange in the district lately?"},
			{"id": "pass", "text": "Just passing through."}],
		[{"id": "press", "text": "Strange how? Tell me what you saw."},
			{"id": "trust", "text": "You can talk to me. I'm trying to help."}],
		[{"id": "where", "text": "Where were you last night?"},
			{"id": "leave", "text": "I'll let you be — for now."}],
	]
	return (banks[posmod(turn, banks.size())] as Array).duplicate(true)

func _decide(snap: Dictionary) -> Dictionary:
	var actor := String(snap.get("agent_id", ""))
	var beat := int(snap.get("beat", 0))
	# COMBAT (combat plan §M4): an agent whose mask is flipped decides about the FIGHT, not the
	# errand — the offline brain must fight plausibly with zero LLM. Task-bearers (their work is
	# threatened) and anyone whose form carries arts ENGAGE the most concrete threat the snapshot
	# names, aggressively; a true civilian (no task, no arts) breaks off. These are the normal
	# intent VERBS riding the normal propose→commit pipeline — the executor does the actual
	# fighting at frame rate. A pure function of the snapshot, like every other branch here.
	if bool(snap.get("in_combat", false)):
		return _combat_intent_for(actor, snap)
	# A task-bearer runs the gather→deliver→rite LADDER (all from its own snapshot DATA, never a
	# faction). Before the ladder existed the offline cult beelined to the altar EMPTY-HANDED and
	# mimed the rite forever with nothing to deposit (live_sim regression).
	if _has_task(snap):
		var outstanding: Dictionary = (snap.get("rite_materials", {}) as Dictionary).get("outstanding", {})
		var ready := bool((snap.get("rite_materials", {}) as Dictionary).get("ready", false))
		var carrying := _carrying_needed(snap, outstanding)
		# At the site with something to lay — or everything laid / no ledger info — work the rite
		# (perform_ritual_step deposits carried offerings, then advances once the altar is stocked).
		if _at_rite(snap) and (not carrying.is_empty() or ready or outstanding.is_empty()):
			return {
				"actor": actor,
				"verb": "perform_ritual_step",
				"args": {"step": _rite_step(beat)},
				"thought": "The descent draws nearer by my hand.",
			}
		# The site still lacks materials: pick up a needed item lying within reach.
		if not outstanding.is_empty() and bool(snap.get("can_carry_more", true)):
			var reachable := _needed_in_reach(snap, outstanding)
			if reachable != "":
				return {"actor": actor, "verb": "gather_item", "args": {"item_id": reachable},
					"thought": "The work needs this."}
		# Carrying what the site needs: deliver it to the task's named site.
		if not carrying.is_empty():
			var deliver_site := _task_site_name(snap)
			if deliver_site != "":
				return {"actor": actor, "verb": "move_to", "args": {"target": deliver_site}, "thought": _thought_for(snap)}
		# Empty-handed with materials still outstanding: fetch from the task's cache.
		if not outstanding.is_empty() and carrying.is_empty():
			var cache := String((snap.get("task", {}) as Dictionary).get("cache", ""))
			if cache != "":
				return {"actor": actor, "verb": "move_to", "args": {"target": cache}, "thought": _thought_for(snap)}
		# No ledger to satisfy (or nothing actionable): walk toward the named site as before.
		var site := _task_site_name(snap)
		if site != "":
			return {"actor": actor, "verb": "move_to", "args": {"target": site}, "thought": _thought_for(snap)}
	var goal: Vector2 = _goal_for(actor, snap) + _scatter(actor, beat)
	# Encode the goal as an "x,y" target so ActionCommit resolves it without a named site.
	return {
		"actor": actor,
		"verb": "move_to",
		"args": {"target": "%.1f,%.1f" % [goal.x, goal.y]},
		"thought": _thought_for(snap),
	}

## The offline combat decision (combat plan §M4): engage for anyone with a stake in the fight
## (a task to defend, or arts to fight with), disengage for the unarmed bystander — and for a
## fighter the snapshot names no threat for (nothing to engage means the fight, for this agent,
## is over). Emits only schema verbs; damage/movement stay the executor's.
func _combat_intent_for(actor: String, snap: Dictionary) -> Dictionary:
	var kit: Array = snap.get("kit", []) if snap.get("kit") is Array else []
	if _has_task(snap) or not kit.is_empty():
		var target := _threat_for(actor, snap)
		if target != "":
			return {"actor": actor, "verb": "engage",
				"args": {"target": target, "style": "aggressive"},
				"thought": "I will not be stopped."}
	return {"actor": actor, "verb": "disengage", "args": {},
		"thought": "This is not a fight I can win."}

## The most concrete threat this snapshot names: the last agent to strike this body (the
## forwarded executor-ledger fact), else the nearest visibly fighting neighbor, else the nearest
## standing neighbor at all ("" when truly alone). Downed bodies are never threats. Deterministic:
## nearest-first over the snapshot's own roster.
func _threat_for(actor: String, snap: Dictionary) -> String:
	# The remembered attacker counts only while still VISIBLE (present in this snapshot's own
	# nearby roster). Without the presence check, a hit-and-run (strike once, leave the room)
	# froze the offline fighter at the fight spot forever: it kept engaging a target its
	# tactical layer could never reach, schedule suspended, no exit path (final-review #1).
	# An absent attacker falls through — and with nobody else around, the disengage arm fires.
	var last_attacker := String(snap.get("last_attacker", ""))
	if last_attacker != "" and last_attacker != actor:
		for n_v in (snap.get("nearby", []) as Array):
			if n_v is Dictionary and String((n_v as Dictionary).get("id", "")) == last_attacker:
				return last_attacker
	var fighter := ""
	var fighter_d := INF
	var anyone := ""
	var anyone_d := INF
	for n_v in (snap.get("nearby", []) as Array):
		var n: Dictionary = n_v if n_v is Dictionary else {}
		var nid := String(n.get("id", ""))
		if nid == "" or nid == actor or String(n.get("hp_band", "")) == "downed":
			continue
		var d := float(n.get("distance", INF))
		if bool(n.get("in_combat", false)) and d < fighter_d:
			fighter = nid
			fighter_d = d
		if d < anyone_d:
			anyone = nid
			anyone_d = d
	return fighter if fighter != "" else anyone

## True when the agent already stands within rite range of the warehouse — the same threshold the
## commit step enforces (ActionCommit.RITE_RADIUS), so the brain never proposes a rite that wouldn't
## actually bite the clock.
func _at_rite(snap: Dictionary) -> bool:
	# Room-aware, sharing ActionCommit's commit-time gate: at the rite only when standing on a site in
	# the agent's own room (so a city cultist mid-journey is NOT "at" the crypt altar).
	return ActionCommit._near_any_rite_site(
		String(snap.get("room", RoomGraph.DEFAULT_ROOM)), _vec(snap.get("position", [0, 0])))

## Item ids the agent carries that the task site still needs — the "deliver" trigger of the ladder.
func _carrying_needed(snap: Dictionary, outstanding: Dictionary) -> Array:
	var inv: Dictionary = snap.get("inventory", {}) if snap.get("inventory") is Dictionary else {}
	var out: Array = []
	for item_id in inv:
		if int(inv[item_id]) > 0 and int(outstanding.get(item_id, 0)) > 0:
			out.append(String(item_id))
	return out

## The first outstanding material lying within reach (ground_items is nearest-first from Perception,
## so the pick is deterministic), or "" when nothing needed is graspable here.
func _needed_in_reach(snap: Dictionary, outstanding: Dictionary) -> String:
	for g in (snap.get("ground_items", []) as Array):
		var gd: Dictionary = g if g is Dictionary else {}
		var iid := String(gd.get("item_id", ""))
		if iid != "" and bool(gd.get("in_reach", false)) and int(outstanding.get(iid, 0)) > 0:
			return iid
	return ""

## The task's named destination: its own `site` field first (data), else a site named in the intent.
func _task_site_name(snap: Dictionary) -> String:
	var site := String((snap.get("task", {}) as Dictionary).get("site", ""))
	if site != "":
		return site
	return _rite_site_name(snap)

## The named rite site this cultist is bound for (from its intent), or "" if none is named. Moving by
## NAME lets ActionCommit's room-aware move traverse City -> Nave -> Crypt on fallback beats too.
func _rite_site_name(snap: Dictionary) -> String:
	var intent := String(snap.get("intent", "")).to_lower()
	for site_name in ActionCommit.SITES.keys():
		if intent.contains(String(site_name).to_lower()):
			return String(site_name)
	return ""

## The rite site this cultist is bound for. Prefer a site named in the agent's intent
## (CitySummoning writes "...the site named 'cathedral_crypt'..."), else the nearest known site to
## where the agent stands, else the warehouse. So the warehouse (CityBlocks) AND the cathedral
## (City.tscn) both route the OFFLINE / latency-fallback cult to the right altar — not only the
## live LLM. Without this, an unkeyed or in-flight beat walks the cult to the warehouse instead.
func _rite_site_for(snap: Dictionary) -> Vector2:
	# Only consider sites in the agent's OWN room — positions in other rooms are a different local
	# space, so the nearest-by-distance pick must not stray across rooms (e.g. a city cultist must not
	# be drawn toward the crypt altar's local coordinate).
	var room := String(snap.get("room", RoomGraph.DEFAULT_ROOM))
	var intent := String(snap.get("intent", "")).to_lower()
	for site_name in ActionCommit.SITES.keys():
		if ActionCommit._site_room(site_name) == room and intent.contains(String(site_name).to_lower()):
			return ActionCommit.SITES[site_name]
	var pos: Vector2 = _vec(snap.get("position", [0, 0]))
	var best: Vector2 = WAREHOUSE
	var best_d: float = INF
	for site_name in ActionCommit.SITES.keys():
		if ActionCommit._site_room(site_name) != room:
			continue
		var d: float = pos.distance_to(ActionCommit.SITES[site_name])
		if d < best_d:
			best_d = d
			best = ActionCommit.SITES[site_name]
	return best

## Pick the descent step for this beat — cycles the litany so the rite reads as progressing, and is
## a pure function of beat so the same beat replays identically.
func _rite_step(beat: int) -> String:
	return String(RITE_STEPS[posmod(beat, RITE_STEPS.size())])

func _goal_for(actor: String, snap: Dictionary) -> Vector2:
	if _has_task(snap):
		return _rite_site_for(snap)
	return _schedule_goal(actor, snap)

## True when the agent carries a deliverable task in its data — the generic signal that it converges on
## a site and works it, replacing the old faction check. No group/faction.
func _has_task(snap: Dictionary) -> bool:
	return not (snap.get("task", {}) as Dictionary).is_empty()

## Where a non-cult agent is headed: its scheduled waypoint for the current phase. Falls back to
## holding position (+scatter) when the agent has no schedule entry, so it still reads as alive.
func _schedule_goal(actor: String, snap: Dictionary) -> Vector2:
	var wp: Vector2 = _al("NpcDB").waypoint_for(actor, String(snap.get("phase", "")))
	if wp == Vector2.ZERO:
		return _vec(snap.get("position", [0, 0]))
	return wp

## Deterministic per-agent, per-beat offset in roughly [-WANDER, WANDER] on each axis. A pure hash
## of (actor, beat) so the same beat replays identically while the crowd still spreads out.
## md5, NOT String.hash(): djb2 (h = h*33 + c) makes consecutive beats differ by exactly 1, so the
## "re-scatter" moved a fixed 0.028px/beat — invisibly (the same weakness ActionCommit's
## _formation_offset documents). md5 mixes honestly, so each beat lands a genuinely new offset.
func _scatter(actor: String, beat: int) -> Vector2:
	var hx := ("0x" + ("%s|x|%d" % [actor, beat]).md5_text().substr(0, 8)).hex_to_int()
	var hy := ("0x" + ("%s|y|%d" % [actor, beat]).md5_text().substr(0, 8)).hex_to_int()
	var fx := float(hx % 2001) / 1000.0 - 1.0
	var fy := float(hy % 2001) / 1000.0 - 1.0
	return Vector2(fx, fy) * WANDER

func _thought_for(snap: Dictionary) -> String:
	return "The work calls me on." if _has_task(snap) else "Going about my day."

func _vec(v: Variant) -> Vector2:
	if typeof(v) == TYPE_ARRAY and (v as Array).size() >= 2:
		return Vector2(float(v[0]), float(v[1]))
	return Vector2.ZERO

## Resolve an autoload by name — direct `NpcDB.` references fail to compile in a class_name script
## under the headless -s harness (autoloads register after class_name scripts parse).
func _al(autoload_name: String) -> Node:
	return (Engine.get_main_loop() as SceneTree).root.get_node("/root/" + autoload_name)
