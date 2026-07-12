extends Node
## Dialogue system (autoload singleton `DialogueManager`).
##
## Loads branching, topic/clue-aware dialogue trees from data/dialogue.json and drives
## the on-screen DialoguePanel (which registers itself at runtime). Options can be gated
## behind unlocked topics/clues (layered questioning), can carry effects, and can be
## flagged as `contradiction` to render a clue call-out differently.
##
## Tree shape (per npc id):
##   { "start": "<node id>", "nodes": {
##       "<id>": { "speaker": "...", "text": "...", "options": [
##           { "label": "...", "goto": "<id>|end",
##             "requires_topic": "...", "requires_clue": "...",
##             "contradiction": true,
##             "effects": [ {type:"pressure",target,delta} | {type:"lead",text}
##                          | {type:"collect",clue} ] } ] } } }

signal dialogue_started(npc_id: String)
signal node_changed(speaker: String, text: String, options: Array)
signal dialogue_ended
## Fired the instant a converse turn is kicked off (GAP-2.3): the panel flips to its "thinking…" state
## (disables send, shows an indicator) until the matching node_changed lands with the reply.
signal converse_pending(speaker: String)

const DIALOGUE_PATH: String = "res://data/dialogue.json"

var trees: Dictionary = {}
var _active_npc: String = ""
var _active_tree: Dictionary = {}
var active: bool = false

func _ready() -> void:
	_load()
	# The LLM converse round-trip runs on a worker thread (GAP-2.3 de-freeze); its reply lands here on
	# the main thread. Connecting once at boot keeps send_utterance a pure fire-and-forget kick.
	SidecarBridge.converse_reply.connect(_on_converse_reply)

func _load() -> void:
	if not FileAccess.file_exists(DIALOGUE_PATH):
		push_error("DialogueManager: missing %s" % DIALOGUE_PATH)
		return
	var parsed: Variant = JSON.parse_string(FileAccess.get_file_as_string(DIALOGUE_PATH))
	if typeof(parsed) != TYPE_DICTIONARY:
		push_error("DialogueManager: %s is not a JSON object" % DIALOGUE_PATH)
		return
	trees = parsed

func start(npc_id: String) -> void:
	# Loss-of-control lockout (§13 decision #5): the creature form doesn't parley — no dialogue can
	# open while a rampage is live (only the attack drives the beast; the timer runs to run-end).
	if Meters != null and Meters.in_rampage():
		return
	if not trees.has(npc_id):
		push_warning("DialogueManager: no dialogue for '%s'" % npc_id)
		return
	_active_npc = npc_id
	_active_tree = trees[npc_id]
	active = true
	dialogue_started.emit(npc_id)
	_goto(String(_active_tree.get("start", "root")))

## --- LLM conversation path (design §2) -------------------------------------------------------------
## The player says `text` to `npc_id`. Routes through the LLM brain (SidecarBridge.converse): the NPC's
## reply comes back as { say, action, replies }, the optional (already-governed) action is applied, and
## the spoken line + suggested replies are surfaced through the SAME node_changed contract the panel
## renders — so the scripted tree-walk and this path share one UI. Additive: the scripted start()/choose()
## stay as a fallback until the UI is rewired (Phase 3). World time stays paused via `active` while the
## player composes.
var _history: Array = []
const _HISTORY_CAP: int = 12            # last N lines sent with each turn (bounds prompt growth)
# GAP-2.3 de-freeze: a turn now runs on a WORKER THREAD. `_conversing` is the in-flight guard — true
# from the moment we kick the worker until its reply is applied on the main thread. While it is set the
# panel shows a "thinking…" state; a second send is ignored (one turn at a time). We stash the pending
# turn's npc/utterance so the reply handler (which the SidecarBridge signal delivers with no context)
# can gate the action and fold history for the RIGHT agent.
var _conversing: bool = false
var _pending_npc: String = ""
var _pending_text: String = ""

## An in-fiction fallback line for a timed-out/errored/empty round-trip — never a blank panel, never a
## hang. Engine-neutral (no NPC identity): a neutral beat that keeps the conversation alive.
const _FALLBACK_SAY: String = "They look away, as if weighing whether to answer. (No reply came through — try again.)"

## True while a converse turn is in flight (the worker is running or its reply is queued). The panel
## reads this to show/clear its "thinking…" indicator.
func is_converse_pending() -> bool:
	return _conversing

## Kick a conversation turn WITHOUT blocking the main thread. The request is fully stamped here (main
## thread), then handed to SidecarBridge.converse_async which runs the blocking client.converse on a
## worker; the reply lands later in _on_converse_reply (main thread). Returns immediately.
func send_utterance(npc_id: String, text: String) -> void:
	if _conversing:
		return   # a turn is already in flight on the worker; ignore re-entrant input
	var agent: Agent = Agents.get_agent(npc_id)
	if agent == null:
		push_warning("DialogueManager: no agent '%s' to converse with" % npc_id)
		return
	if not active or _active_npc != npc_id:
		_active_npc = npc_id
		_active_tree = {}
		_history = []
		active = true
		dialogue_started.emit(npc_id)
	# Build + stamp the request on the MAIN thread (Perception/ModelConfig touch the scene tree); the
	# secrecy payload is built exactly as before (Perception.converse_request) — only the threading
	# changes, so secrets still ride converse behind the revealed gate.
	var snap: Dictionary = Perception.build_snapshot(agent, AgentRuntime.player_position)
	var req: Dictionary = Perception.converse_request(snap, _session_id(), text, _history)
	_pending_npc = npc_id
	_pending_text = text
	_conversing = true            # enter 'thinking' — the panel shows its indicator and disables send
	# Emit a pending node_changed so the panel can flip to 'thinking' immediately (the reply replaces it).
	converse_pending.emit(agent.display_name)
	if not SidecarBridge.converse_async(req):
		# The bridge reports a turn already in flight. With DialogueManager's own _conversing guard this
		# should not happen, but a stale worker from a just-left conversation could still hold the bridge
		# busy (GAP-2.3 finding #1). Cancel that orphan (non-blocking) and retry once rather than silently
		# dropping this turn or hanging.
		SidecarBridge.cancel_converse()
		if not SidecarBridge.converse_async(req):
			# Still refused — abandon this turn cleanly and CLEAR the 'thinking' state (finding #4) so the
			# panel isn't left stuck spinning with no reply coming. Surface a fallback line via the reply
			# handler's contract so the panel re-renders interactively.
			_conversing = false
			_pending_npc = ""
			_pending_text = ""
			node_changed.emit(agent.display_name, _FALLBACK_SAY, [])

## The worker's reply, applied on the MAIN thread (SidecarBridge.converse_reply). Gates the optional
## action, folds history, logs npc_said, and surfaces the line through node_changed — the SAME contract
## the synchronous path used, just deferred one hop off the frame. A timed-out/errored/empty reply
## (say == "" and no replies) lands a graceful fallback line instead of a blank panel or a hang.
func _on_converse_reply(reply: Dictionary) -> void:
	if not _conversing:
		return   # a stray reply after the conversation ended (e.g. player left) — ignore
	var npc_id := _pending_npc
	var text := _pending_text
	_conversing = false
	_pending_npc = ""
	_pending_text = ""
	var agent: Agent = Agents.get_agent(npc_id)
	if agent == null:
		return   # the agent vanished mid-turn; nothing to render
	# The optional mechanical action is gated EXACTLY as the autonomous runtime gates a proposal —
	# ActionSchema legality + Critic coherence — because the brain's hard veto is narrative-only, not
	# the schema validator or the Critic. The spoken `say` is never gated; only the action is.
	# APPLIED BEFORE the outbound redaction (B2/M23): a gate-approved `reveal_secret` confession
	# must mark its secret revealed before the scrub computes the un-revealed set, so the same
	# breath that earns the reveal may also speak it. Un-earned prose still hits the scrub below.
	var action: Variant = reply.get("action")
	if action is Dictionary and String((action as Dictionary).get("verb", "")) != "":
		var act: Dictionary = (action as Dictionary).duplicate(true)
		act["actor"] = npc_id
		if not (act.get("args") is Dictionary):
			act["args"] = {}
		if ActionSchema.validate(act)["ok"]:
			var review: Dictionary = Critic.review(act, agent)
			match String(review["verdict"]):
				"approve":
					_apply_converse_action(act, agent)
				"amend":
					_apply_converse_action(review["action"], agent)
				# veto: the say still stands; no world effect
	# B11 — ENGINE-SIDE outbound redaction (defense in depth; the model is NOT trusted). Scrub any
	# un-earned secret leak from the spoken line + the suggested reply chips before they reach the
	# player, scanning ONLY against THIS agent's own UN-revealed secrets + true combat identity, and
	# never against what it may speak as fact (its `knowledge`). Data-driven — no NPC-identity branch.
	# A revealed secret is not in unrevealed_secrets(), so legitimate revealed talk is untouched.
	var clean: Dictionary = ConverseRedaction.filter_reply(
		reply,
		agent.unrevealed_secrets(),
		ConverseRedaction.form_tokens(agent.combat_form, agent.pathway),
		agent.knowledge)
	var say := String(clean.get("say", ""))
	var replies: Array = clean.get("replies", []) if clean.get("replies") is Array else []
	# Transport failure / empty reply → a graceful in-fiction fallback, never a blank panel or a freeze.
	if say == "" and replies.is_empty():
		say = _FALLBACK_SAY
	if text != "":
		_history.append("Player: %s" % text)
	if say != "":
		_history.append("%s: %s" % [agent.display_name, say])
	if _history.size() > _HISTORY_CAP:
		_history = _history.slice(_history.size() - _HISTORY_CAP)
	# Log hook: whenever the NPC actually speaks, announce it on the bus so observers (play-log,
	# transcript overlays) can record the line. Keyed by agent id, with the resolved say.
	if say != "":
		EventBus.emit_event("npc_said", {"agent": npc_id, "text": say})
	node_changed.emit(agent.display_name, say, replies)

## Deterministic seam for tests: join the in-flight converse worker and apply its reply NOW.
func flush_converse() -> void:
	SidecarBridge.flush_converse()

## Commit a gate-approved conversation action + apply its social consequence. A scout_waverer who
## adopts a DEFECTION goal is turned through the existing social_influence path (which records the turn as
## a defection goal + applies the rite impede); any other adopted goal merely records itself and steers
## later decisions via Perception goal-folding.
func _apply_converse_action(act: Dictionary, agent: Agent) -> void:
	ActionCommit.commit(act, agent)
	# B2/M23 — the EARNED-REVEAL wire (the previously dead Agent.reveal_secret channel). A converse
	# turn is player-prompted by construction (Perception.converse_request stamps player_triggered:
	# a player-prompted reveal is player-earned — the documented design intent), and this action has
	# already passed the schema + Critic gates. Resolve the named secret against the agent's OWN
	# un-revealed secrets with the redaction's own matcher (knowledge-protected, data-driven, no
	# NPC-identity branch) and mark it revealed, so ConverseRedaction stops scrubbing THAT secret
	# for THIS agent. Default-deny stands: prose alone never reveals (only this governed action
	# path does), this wire runs ONLY on the converse seam (an autonomous reveal_secret proposal
	# commits as a no-op), and a text matching no owned secret reveals nothing.
	if String(act.get("verb", "")) == "reveal_secret":
		var named := String((act.get("args", {}) as Dictionary).get("secret", ""))
		var matched := ConverseRedaction.matched_secret(named, agent.unrevealed_secrets(), agent.knowledge)
		if matched != "":
			agent.reveal_secret(matched)
			EventBus.emit_event("secret_revealed", {"agent": agent.id})
	# The turn fires on the goal's KIND, not its wording: ActionCommit.goal_kind reads the brain's explicit
	# `kind` if present, else classifies once. A defection goal phrased outside any keyword list still turns.
	if String(act.get("verb", "")) == "adopt_goal" and agent.role == "scout_waverer" \
			and ActionCommit.goal_kind(act.get("args", {}) as Dictionary) == "defection":
		PlayerActions.social_influence(agent.id)

## Open an LLM conversation with an agent (keyed by AGENT id, not a dialogue-tree id — any agent is
## conversable). Kicks off an opening turn so the NPC speaks first.
func open(npc_id: String) -> void:
	# Loss-of-control lockout (§13 decision #5): no conversation opens during a rampage.
	if Meters != null and Meters.in_rampage():
		return
	if Agents.get_agent(npc_id) == null:
		push_warning("DialogueManager: no agent '%s' to open a conversation with" % npc_id)
		return
	_active_npc = npc_id
	_active_tree = {}
	_history = []
	_conversing = false
	active = true
	dialogue_started.emit(npc_id)
	send_utterance(npc_id, "")   # opening turn: the NPC greets first (empty player line = approach)

## The agent id of the NPC the player is currently conversing with (for the panel's send routing).
func active_npc() -> String:
	return _active_npc

## Has this agent TURNED — i.e. adopted a goal stamped kind == "defection"? This is the behavioral
## "turned" state (no concealment flag): once true, the persuade option is spent. Reads the persisted
## marker (Agent.has_defection_goal), never re-scans the goal text.
func _has_defection_goal(agent: Object) -> bool:
	return agent != null and agent.has_defection_goal()

## Same memory-stream namespace the brain's /decide loop uses (HttpSidecar._session_id), so a
## conversation and the NPC's autonomous beats share one memory.
func _session_id() -> String:
	return "tingen_%d" % OS.get_process_id()

## Choose option `index` from the options last surfaced via node_changed.
func choose(node_id: String, option_index: int) -> void:
	var node: Dictionary = _active_tree.get("nodes", {}).get(node_id, {})
	var options := _visible_options(node)
	if option_index < 0 or option_index >= options.size():
		return
	var opt: Dictionary = options[option_index]
	for e in opt.get("effects", []):
		_apply_effect(e)
	var goto := String(opt.get("goto", "end"))
	if goto == "end" or goto == "":
		_end()
	else:
		_goto(goto)

func _goto(node_id: String) -> void:
	var nodes: Dictionary = _active_tree.get("nodes", {})
	if not nodes.has(node_id):
		_end()
		return
	var node: Dictionary = nodes[node_id]
	# Node-enter effects (optional).
	for e in node.get("effects", []):
		_apply_effect(e)
	_current_node_id = node_id
	node_changed.emit(String(node.get("speaker", "")), String(node.get("text", "")), _visible_options(node))

var _current_node_id: String = ""

func current_node_id() -> String:
	return _current_node_id

## Filter options by topic/clue gates so locked questions stay hidden.
func _visible_options(node: Dictionary) -> Array:
	var out: Array = []
	for opt in node.get("options", []):
		var req_topic := String(opt.get("requires_topic", ""))
		if req_topic != "" and not ClueDB.topic_unlocked(req_topic):
			continue
		var req_clue := String(opt.get("requires_clue", ""))
		if req_clue != "" and not ClueDB.is_collected(req_clue):
			continue
		# Gate on a live agent that has NOT yet TURNED, so options track the world's state, not just the
		# player's clue log. Orin's "persuade" line stays on offer while he is still with the cell and
		# vanishes the instant he is turned — you can't re-persuade someone already won over. "Turned" is
		# purely behavioral: the agent has adopted a defection goal (no concealment flag, no faction).
		var req_unturned := String(opt.get("requires_agent_unturned", ""))
		if req_unturned != "":
			var gated: Variant = Agents.get_agent(req_unturned)
			if gated == null or _has_defection_goal(gated):
				continue
		out.append(opt)
	return out

func _apply_effect(e: Dictionary) -> void:
	match String(e.get("type", "")):
		"pressure":
			WorldState.adjust(StringName(e.get("target", "")), float(e.get("delta", 0.0)))
		"lead":
			WorldState.set_lead(String(e.get("text", "")))
		"collect":
			ClueDB.collect(String(e.get("clue", "")))
		"thought":
			WorldState.thought_requested.emit(String(e.get("text", "")))
		"social_influence":
			# Persuasion in conversation routes through the same player verb the console/world
			# use, so a wavering NPC talked round actually turns (adopts a defection goal) and adds impede.
			PlayerActions.social_influence(String(e.get("agent", "")))
		"grant_item":
			# Hand the player a physical item through the dialogue seam — the Nighthawk Captain's
			# briefing issues the divination_kit + spirit_lens this way. Inventory.add enforces the
			# item's stacking cap, and the occult tools are non-stackable (cap 1), so a replayed
			# briefing can never dupe a tool: the second grant is a refused no-op.
			# TODO(occult-tools): dream_draught and gray_fog_focus are still UNGRANTED — when their
			# story beat lands (a later briefing / the HQ quartermaster), add
			# {"type": "grant_item", "item": "dream_draught"} / {"..." : "gray_fog_focus"} effects
			# to that dialogue node; no engine change needed beyond this handler.
			Inventory.add(String(e.get("item", "")), int(e.get("count", 1)))

func _end() -> void:
	active = false
	_active_npc = ""
	_active_tree = {}
	_current_node_id = ""
	# Drop any in-flight turn. A reply that lands after the player leaves is already ignored
	# (_on_converse_reply guards on _conversing), BUT we must also FREE THE BRIDGE (GAP-2.3 finding #1):
	# leaving without cancelling leaves SidecarBridge._cv_busy set on a slow live worker, so an immediate
	# re-open of a *new* conversation would have its turn silently dropped. cancel_converse is
	# non-blocking (it detaches the worker for an off-frame reap rather than joining), so leaving during a
	# slow live call stays instant.
	SidecarBridge.cancel_converse()
	_conversing = false
	_pending_npc = ""
	_pending_text = ""
	dialogue_ended.emit()
