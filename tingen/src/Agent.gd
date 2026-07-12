class_name Agent
extends RefCounted
## Runtime representation of one inhabitant of the district.
##
## An Agent is the live, mutable counterpart to a static NpcDB definition: it holds the
## NPC's current position, intent, in-progress action, short-term memory and plan. In
## later plans an LLM decides each agent's actions per beat; until then `tick_fallback`
## gives cheap deterministic behaviour by walking the agent toward its scheduled
## waypoint. Agents round-trip through to_dict()/from_dict() so the AgentRegistry can
## persist the whole cast in a save file.

var id: String = ""
var display_name: String = ""
var role: String = ""
var intent: String = ""
## Goals the agent has TAKEN ON at runtime (e.g. after being persuaded in conversation) — the
## engine-side of goal-changing dialogue (adopt_goal/drop_goal, agent-sandbox precedent). Distinct from
## the intent-derived goals Perception synthesizes; these are mutable and per-agent. Each entry is a dict
## {"text": String, "kind": "defection"|"other"} — the kind is decided ONCE at adoption and persisted,
## so a "turned" waverer is recognised by its stored marker, never re-derived by scanning the goal text.
var adopted_goals: Array = []
## Persona prose for the LLM prompt (from the NpcDB def). `description` + `voice` give the model a voice;
## `knowledge` is the anti-hallucination floor of what this NPC may truthfully speak to; `secrets` are
## things it knows but conceals — gated like the secret goal, NEVER sent on a player-visible/hidden path.
var description: String = ""
var voice: String = ""
var knowledge: Array = []
var secrets: Array = []
## Secrets this agent has EARNED-revealed to the player (B11). A secret leaves the hidden set only when
## the player triggers the reveal in-fiction; the converse OUTBOUND redaction (ConverseRedaction) scans
## the NPC's reply against its UN-revealed secrets only, so a revealed secret stays legitimately
## discussable while an un-earned one is scrubbed engine-side. Data, not a per-NPC branch.
var revealed_secrets: Array = []
## Data-driven NPC record fields (design §2) — the engine reads these; an NPC is a bag of data with no
## faction. `goals` is a FLAT tiered list, each entry {"description": String, "tier": String} (goals are
## goals — no public/secret split). `secrets` are facts the character keeps hidden; it always KNOWS them
## and whether it reveals them is PURELY BEHAVIORAL (the LLM decides in character — no hard gate). `task`
## references the deliverable objective + its sites (e.g. {"ritual":…, "site":…, "cache":…}).
var goals: Array = []
var task: Dictionary = {}
## Cognition budget for this NPC (`"full"` | `"light"`). Background NPCs default to `"light"` — far less
## memory/persona/tokens; named principals are `"full"`. See the dialogue/events design doc §2.10.
var tier: String = "light"
## Whether the agent runtime deliberates (proposes actions) for this agent. The synthetic "player" proxy
## sets this false: it is a perceivable/attackable mirror of the real player, never a brain-driven actor.
var deliberates: bool = true
var position: Vector2 = Vector2.ZERO
## Which room/scene this agent is logically in (RoomGraph). `position` is its LOCAL position within
## that room. Crossing a portal sets room + repositions — a data move, no scene load.
var room: String = "city"
var current_action: Dictionary = {}
var short_memory: Array = []
## Monotonic count of every observation ever appended to short_memory, NEVER reset by the cap-slice.
## The brain uses (mem_total - short_memory.size()) as the absolute sequence id of the window's
## first surviving entry, so deltas stay correct even after old entries are evicted.
var mem_total: int = 0
var plan: Array = []
var thought: String = ""   # latest read-out: set by sidecar/critic, else synthesized
## Combat state. The cast is a fixed, saved roster, so a felled agent is incapacitated
## (downed), never deleted — unlike Yumina, which removes a dead entity from the world.
var hp: float = 100.0
var max_hp: float = 100.0
var downed: bool = false
## M18 loot latch: a downed body can be looted exactly ONCE. Ephemeral run scratch (like combat
## state) — never persisted; a fresh run rebuilds every Agent with the latch clear, so it can't leak
## across runs. Set by PlayerCombat.loot_downed_body when the player empties this body's inventory.
var looted: bool = false
## Combat mode (combat plan §M1). `in_combat` is the mask-flip flag: damage that lands on a
## standing agent raises it (take_damage -> CombatMode.enter_combat); the LLM's `disengage`
## intent lowers it. `combat_form` names this agent's combat kit in data/combat_forms.json
## (hydrated from an optional "combat_form" in npcs.json); "" = no combat form authored.
## `combat_intent` is the last committed intent-layer verb as a PUBLISHED FACT:
## {"mode": "engage"|"disengage"|"protect", "target"/"via"/"agent", "style", "set_at_beat"} —
## the M2/M3 tactical layer reads it; committing it applies no damage and moves nothing.
var in_combat: bool = false
var combat_form: String = ""
var combat_intent: Dictionary = {}
## Sequence PATHWAY this agent belongs to (direction v2 §6) — pure DATA, hydrated from an optional
## "pathway" in npcs.json. Names a Beyonder's ladder (e.g. "hunter"); "" = off-pathway / mundane.
## The engine reads this to decide the Characteristic a downed Beyonder drops (a SAME-pathway kill
## drops the player-usable characteristic; an off-pathway one drops a generic/sellable stand-in) —
## NEVER an NPC-identity branch. The butcher bram_kell stays "" (off-pathway per §3).
var pathway: String = ""
## A cast PARKED for this agent's executor (combat plan §M4): ActionCommit.cast_ability lands a
## beat-level cast here when no executor is live yet (the NPC seam spawns one a frame after
## combat_started) or the live one is busy; CombatExecutor.step_combat consumes it on its own
## clock. Cleared on downing and on leaving combat. EPHEMERAL combat scratch — deliberately NOT
## persisted (combat state never is; see CombatExecutor).
var pending_cast: String = ""
## Per-agent inventory (Yumina-faithful: a flat id->count store the agent carries). Distinct
## from the player Inventory autoload and from the cult's shared rite cache (SummoningPlan).
var inventory: Dictionary = {}  # item_id -> int
## Max total units this agent can carry at once (gather_item refuses beyond this).
var carry_capacity: int = 2
## How far (px) this agent can perceive — per-agent DATA (agent-sandbox precedent). Gates which
## same-room peers enter its `nearby` roster (Perception._nearby) and which room events Stimulus
## writes into its memory. Hydrated from an optional "vision_r" in npcs.json (AgentRegistry.rebuild).
## The literal mirrors Perception.DEFAULT_VISION_R — kept literal here because a cross-class_name
## const reference can fail to resolve under the headless -s test harness's parse ordering.
var vision_r: float = 160.0

func _init(agent_id: String = "") -> void:
	id = agent_id

func tick_fallback(phase: String, speed: float) -> void:
	# A downed agent is incapacitated: it holds its ground until helped up, so the cheap
	# scheduled walk skips it entirely. Mirrors the Critic veto that lets a felled agent only
	# idle — both keep a downed body from drifting around the district.
	if downed:
		return
	# Schedule waypoints (npcs.json) are CITY-space coordinates. An agent that has crossed into
	# another room (nave/crypt) must NOT walk toward one interpreted in its room's LOCAL space —
	# that darts it toward a wrong-space point. Hold position until a room-aware action moves it.
	if room != RoomGraph.DEFAULT_ROOM:
		return
	# Resolve the NpcDB autoload via the engine singleton table rather than the bare
	# global identifier: when this class_name script is compiled as a dependency of the
	# headless `-s` test runner, autoload globals aren't registered yet, so a bare
	# `NpcDB` reference fails to compile. The singleton lookup is ordering-independent.
	var npc_db: Object = (Engine.get_main_loop() as SceneTree).root.get_node("/root/NpcDB")
	var target: Vector2 = npc_db.waypoint_for(id, phase)
	if target == Vector2.ZERO and position == Vector2.ZERO:
		return
	var to_target: Vector2 = target - position
	var dist: float = to_target.length()
	if dist <= speed or dist == 0.0:
		position = target
	else:
		position += to_target / dist * speed

func distance_to(p: Vector2) -> float:
	return position.distance_to(p)

func remember(entry: String, cap: int = 20) -> void:
	short_memory.append(entry)
	mem_total += 1   # monotonic lifetime observation count; survives the cap-slice below
	if short_memory.size() > cap:
		short_memory = short_memory.slice(short_memory.size() - cap)

## Apply flat combat damage (ActionCommit.attack drives this). Clamps to [0, max_hp] and
## downs the agent at zero — mirroring Yumina's clamp-to-zero HP mutation, but incapacitating
## rather than deleting, since our cast is fixed and persisted.
## Damage that lands on a STANDING agent also flips it into combat mode (combat plan §0: damage
## flips the mask) — flag + combat_started event ONLY; no form/sprite swap ever rides this path
## (transformation is an ability). A downing blow downs without starting combat.
func take_damage(amount: float) -> void:
	if amount <= 0.0:
		return
	hp = clampf(hp - amount, 0.0, max_hp)
	if hp <= 0.0:
		downed = true
	# A downing blow ENDS the fight for this agent (review M1 #2): a felled body must not stay
	# latched in_combat — combat_ended must fire, saves must not persist a phantom fight, and
	# the Coordinator/executors must not misread the corpse as a combatant.
	if downed:
		if in_combat:
			var cm_exit := _combat_mode()
			if cm_exit != null:
				cm_exit.exit_combat(self)
			else:
				in_combat = false
		combat_intent = {}
		pending_cast = ""   # a downed body casts nothing — the parked art dies with the fight
		return
	if not in_combat:
		# Damage on a STANDING agent flips combat mode. The PLAYER PROXY is exempt (review M1 #4):
		# it has no brain to fight with — its combat mode belongs to the M5 player controller.
		if id == "player":
			return
		# Null-guarded /root lookup: headless unit contexts may construct an Agent with no
		# autoloads registered — the flag still flips, only the event is skipped there.
		var cm := _combat_mode()
		if cm != null:
			cm.enter_combat(self)
		else:
			in_combat = true

## Resolve the CombatMode autoload if one is registered (see take_damage). Agent is a class_name
## script, so a bare `CombatMode.` reference would fail to compile under the headless -s harness;
## the /root lookup is ordering-independent AND tolerates the autoload being absent entirely.
func _combat_mode() -> Node:
	var ml := Engine.get_main_loop()
	if ml == null or not (ml is SceneTree):
		return null
	return (ml as SceneTree).root.get_node_or_null("CombatMode")

## Add to this agent's own carried stock (ActionCommit.gather_item drives this).
func add_item(item_id: String, count: int = 1) -> void:
	if item_id == "" or count <= 0:
		return
	inventory[item_id] = int(inventory.get(item_id, 0)) + count

## How many of an item this agent is currently carrying.
func item_count(item_id: String) -> int:
	return int(inventory.get(item_id, 0))

## Total units carried across all item types.
func inventory_count() -> int:
	var n := 0
	for k in inventory:
		n += int(inventory[k])
	return n

## True when there is room for one more unit (gather is capacity-gated).
func can_carry() -> bool:
	return inventory_count() < carry_capacity

## Drop one unit of an item from the inventory; returns false if none carried.
func remove_item(item_id: String, count: int = 1) -> bool:
	if int(inventory.get(item_id, 0)) < count:
		return false
	inventory[item_id] = int(inventory[item_id]) - count
	if int(inventory[item_id]) <= 0:
		inventory.erase(item_id)
	return true

## The agent's moment-to-moment read-out for the character card. Returns an explicit
## thought when one was set (by a sidecar/critic), otherwise synthesizes one from the
## current action. Distinct from `intent`, which is the long-horizon goal. Always
## returns a non-empty string, so the card never shows a blank thought line.
func describe_thought() -> String:
	if thought != "":
		return thought
	var verb := String(current_action.get("verb", ""))
	var args: Dictionary = current_action.get("args", {})
	match verb:
		"move_to": return "Making my way to %s." % args.get("target", "somewhere")
		"talk_to": return "I should have words with %s." % args.get("agent", "them")
		"gather_item": return "I still need the %s." % args.get("item_id", "supplies")
		"perform_ritual_step": return "The rite must go on: %s." % args.get("step", "the next step")
		"recruit": return "Could %s be brought into the fold?" % args.get("agent", "them")
		"report": return "I must get word to %s." % args.get("to", "my contact")
		"hide": return "Best I am not seen just now."
		"flee": return "I have to get clear of %s." % args.get("from", "here")
		"attack": return "No choice left but to strike."
		_: return "Keeping to my own business... for now."

## True when the agent already holds an adopted goal with this exact text (kind-agnostic). Each
## adopted_goals entry is a dict {"text": String, "kind": "defection"|"other"} — the kind is decided
## ONCE at adoption and persisted, so "turned" state is read, never re-derived from words.
func has_adopted_goal(text: String) -> bool:
	for g in adopted_goals:
		if g is Dictionary and String(g.get("text", "")) == text:
			return true
	return false

## The plain text of every adopted goal, in order — what Perception folds into the brain's goal set.
func adopted_goal_texts() -> Array:
	var out: Array = []
	for g in adopted_goals:
		if g is Dictionary:
			out.append(String(g.get("text", "")))
	return out

## True when the agent has TURNED — holds at least one goal marked kind == "defection". This is the
## behavioral "turned" state (no separate flag): the goal-with-kind IS the state.
func has_defection_goal() -> bool:
	for g in adopted_goals:
		if g is Dictionary and String(g.get("kind", "")) == "defection":
			return true
	return false

## The secrets this agent has NOT yet earned-revealed to the player — what the converse redaction must
## keep from leaking (B11). Equality is by exact string against `revealed_secrets`.
func unrevealed_secrets() -> Array:
	var out: Array = []
	for s in secrets:
		if not revealed_secrets.has(s):
			out.append(s)
	return out

## Is this specific secret string already earned-revealed?
func is_secret_revealed(secret: String) -> bool:
	return revealed_secrets.has(secret)

## Mark one of this agent's own secrets earned-revealed (idempotent; only its OWN secrets qualify).
func reveal_secret(secret: String) -> void:
	if secrets.has(secret) and not revealed_secrets.has(secret):
		revealed_secrets.append(secret)

func to_dict() -> Dictionary:
	return {
		"id": id,
		"display_name": display_name,
		"role": role,
		"intent": intent,
		"adopted_goals": adopted_goals.duplicate(true),
		"description": description,
		"voice": voice,
		"knowledge": knowledge.duplicate(),
		"secrets": secrets.duplicate(),
		"revealed_secrets": revealed_secrets.duplicate(),
		"goals": goals.duplicate(true),
		"task": task.duplicate(true),
		"tier": tier,
		"deliberates": deliberates,
		"position": [position.x, position.y],
		"room": room,
		"current_action": current_action.duplicate(true),
		"short_memory": short_memory.duplicate(),
		"mem_total": mem_total,
		"plan": plan.duplicate(true),
		"thought": thought,
		"hp": hp,
		"max_hp": max_hp,
		"downed": downed,
		"in_combat": in_combat,
		"combat_form": combat_form,
		"combat_intent": combat_intent.duplicate(true),
		"pathway": pathway,
		"inventory": inventory.duplicate(true),
		"vision_r": vision_r,
	}

func from_dict(d: Dictionary) -> void:
	id = String(d.get("id", id))
	display_name = String(d.get("display_name", display_name))
	role = String(d.get("role", role))
	intent = String(d.get("intent", intent))
	adopted_goals = (d.get("adopted_goals", []) as Array).duplicate(true)
	description = String(d.get("description", description))
	voice = String(d.get("voice", voice))
	knowledge = (d.get("knowledge", []) as Array).duplicate()
	secrets = (d.get("secrets", []) as Array).duplicate()
	revealed_secrets = (d.get("revealed_secrets", []) as Array).duplicate()   # older saves lack it -> none revealed
	goals = (d.get("goals", []) as Array).duplicate(true)
	task = (d.get("task", {}) as Dictionary).duplicate(true)
	tier = String(d.get("tier", tier))
	deliberates = bool(d.get("deliberates", deliberates))
	var p: Variant = d.get("position", [0, 0])
	if typeof(p) == TYPE_ARRAY and (p as Array).size() >= 2:
		position = Vector2(float(p[0]), float(p[1]))
	room = String(d.get("room", room))
	current_action = (d.get("current_action", {}) as Dictionary).duplicate(true)
	short_memory = (d.get("short_memory", []) as Array).duplicate()
	mem_total = int(d.get("mem_total", short_memory.size()))
	plan = (d.get("plan", []) as Array).duplicate(true)
	thought = String(d.get("thought", thought))
	hp = float(d.get("hp", hp))
	max_hp = float(d.get("max_hp", max_hp))
	downed = bool(d.get("downed", downed))
	in_combat = bool(d.get("in_combat", in_combat))         # older saves lack these -> keep defaults
	combat_form = String(d.get("combat_form", combat_form))
	combat_intent = (d.get("combat_intent", {}) as Dictionary).duplicate(true)
	pathway = String(d.get("pathway", pathway))   # older saves lack it -> keep the default ("")
	inventory = (d.get("inventory", {}) as Dictionary).duplicate(true)
	vision_r = float(d.get("vision_r", vision_r))   # older saves lack it -> keep the default
