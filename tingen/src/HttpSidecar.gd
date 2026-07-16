class_name HttpSidecar
extends AmbientSidecar
## The real-LLM brain: talks to the Python agent-sidecar (agent-sidecar/sidecar.py) over HTTP.
## All API keys stay quarantined in that service — this client only ever sends perception
## snapshots and receives actions, never a key.
##
## The LLM call takes seconds; a 15s real-time beat cannot block on it. So the transport runs on
## a background Thread and proposals arrive with ONE beat of latency: `propose` returns instantly
## from a per-agent cache (ambient-filled for any agent not yet heard from) and kicks off a refresh
## whose reply is applied on the next beat. Because it extends AmbientSidecar, every fallback — cold
## cache, in-flight request, unreachable sidecar, malformed reply — is a live goal-seeking move, so
## the world never freezes. Prayer adjudication is inherited (the LLM brain still answers prayers
## deterministically until that path is wired too).
##
## All engine state (EventBus, the cache) is touched only on the main thread inside `propose`; the
## worker thread does pure HTTP + JSON and hands results back through a mutex-guarded buffer.

var base_url: String = ""        # e.g. "http://127.0.0.1:8777"; "" disables networking (pure ambient)
var timeout_sec: float = 20.0

# Brain mode (TINGEN_BRAIN): POST /decide with the stateful cognition layer (agent-sidecar SPEC §6 —
# per-agent memory stream + tiered goals + hard veto). This is the DEFAULT and only live path; the
# stateless /propose is retired to a thin emergency fallback (kill-switch only). The brain holds
# memory server-side; each beat we send the agent's full short_memory window with absolute seq ids
# and the brain dedups by seq, so a dropped/backpressured beat never loses an observation. One stable
# session id per run.
var _use_brain: bool = true
var _session_id: String = "tingen"

var _cache: Dictionary = {}      # agent_id -> most-recent LLM action
## P3 (lab pull-in): agents whose /decide is currently IN FLIGHT (agent_id -> begin beat). Each
## launch emits ONE typed `deciding {agent, phase: begin, beat}` EventBus fact; the reply (or its
## timeout) emits the matching `end` exactly once and attributes the call's cost to the causing
## NPC (SidecarBridge.note_agent_llm). Main-thread only (launch + drain both run in propose()).
var _inflight: Dictionary = {}
var _mutex: Mutex = Mutex.new()
var _thread: Thread = null
var _busy: bool = false
# Reply buffer filled by the worker, drained on the next main-thread propose().
var _pending_actions: Array = []
var _pending_error: String = ""
var _has_pending: bool = false

func _init(url: String = "") -> void:
	base_url = url
	# /decide (stateful cognition) is the default and only live path. Set TINGEN_BRAIN to 0/false/off to
	# fall back to the deprecated stateless /propose (kept only as a thin emergency fallback).
	_use_brain = not (OS.get_environment("TINGEN_BRAIN").to_lower() in ["0", "false", "off"])
	if _use_brain:
		_session_id = "tingen_%d" % OS.get_process_id()   # one stream namespace per game run
		print("[sidecar] brain mode ON: POST /decide (stateful cognition), session=%s" % _session_id)

func propose(snapshots: Array) -> Array:
	# Not configured -> behave exactly like the ambient brain, no network, no thread.
	if base_url == "":
		return super.propose(snapshots)
	_drain_pending()                       # apply the previous beat's reply (main thread)
	var out: Array = pick(snapshots)       # freshest cache over ambient fallback
	if _use_brain:
		_launch_brain_refresh(snapshots)   # stateful /decide (cognition + veto)
	else:
		_launch_refresh(snapshots)         # stateless /propose
	return out

## The LLM brain staggers deliberation (orchestrator/GM design §4.1): identical-context concurrent
## calls converge on the modal action, so only one cohort decides each beat while the others
## CONTINUE their committed action (AgentRuntime handles the continuation).
func stagger_k() -> int:
	return 2

## Build this beat's actions: the cached LLM action per agent, or the ambient goal-seek when we
## have not heard about that agent yet. Pure; safe to unit-test without any networking.
## CONSUME-ONCE: a cached action is erased as it is served. Without this, one slow LLM round-trip
## (the single in-flight slot skips busy beats) replayed each agent's last verb verbatim for beats
## on end — the "everyone repeats the same action" amplifier. Consumed + no fresh reply yet →
## ambient fallback keeps the agent moving instead of parroting a stale decision.
func pick(snapshots: Array) -> Array:
	var ambient: Array = super.propose(snapshots)
	var out: Array = []
	_mutex.lock()
	for i in snapshots.size():
		var aid := String((snapshots[i] as Dictionary).get("agent_id", ""))
		if _cache.has(aid):
			out.append(_cache[aid])
			_cache.erase(aid)
		else:
			out.append(ambient[i])
	_mutex.unlock()
	return out

## Apply one completed reply on the main thread: cache valid actions and log every outcome to the
## EventBus so the debug overlay shows the LLM's proposals and errors. Invalid actions are dropped
## (AgentRuntime would reject them anyway) and surfaced as sidecar_error.
func apply_reply(actions: Array, error: String) -> void:
	var eb := _al("EventBus")
	var beat := int(_al("Clock").beat_index)
	var sb := _al("SidecarBridge")
	if error != "":
		# P3: the bounded decide DIED (timeout / transport failure). The beat already completed on
		# the offline brain (pick's ambient fallback) — here we close each in-flight agent's
		# lifecycle fact exactly once and still attribute the spent call to the causing NPC.
		var outcome := "timeout" if error.contains("timeout") else "error"
		for aid in _inflight.keys():
			eb.emit_event("deciding", {"agent": aid, "phase": "end", "beat": beat, "outcome": outcome})
			if sb != null and sb.has_method("note_agent_llm"):
				sb.note_agent_llm(String(aid), 0.0, true)
		_inflight.clear()
		eb.emit_event("sidecar_error", {"reason": error})
		return
	for a in actions:
		if typeof(a) != TYPE_DICTIONARY:
			continue
		var act: Dictionary = a
		# P3: this agent's decide has LANDED — close its lifecycle fact (exactly once; a late
		# duplicate reply finds _inflight already empty) and attribute the realized cost.
		var landed_aid := String(act.get("actor", ""))
		if _inflight.has(landed_aid):
			_inflight.erase(landed_aid)
			eb.emit_event("deciding", {"agent": landed_aid, "phase": "end", "beat": beat, "outcome": "ok"})
			if sb != null and sb.has_method("note_agent_llm"):
				sb.note_agent_llm(landed_aid, float(act.get("_cost", 0.0)), false)
		# Hand the exact prompt + raw LLM reply + token usage (verbose dev logging only) to the
		# play-log, then strip them so they never reach the cache or the schema validator.
		if act.has("_prompt") or act.has("_tokens_in"):
			var pl := _playlog()
			if pl != null:
				pl.record_exchange(String(act.get("actor", "")),
					String(act.get("_prompt", "")), String(act.get("_llm_response", "")))
				pl.add_usage(int(act.get("_tokens_in", 0)), int(act.get("_tokens_out", 0)),
					float(act.get("_cost", 0.0)), String(act.get("_model", "")))
			# B4 (M21): feed the realized cost to the session budget guard so it can degrade to the
			# ambient brain once the ceiling is reached (the ONE place cumulative LLM spend is capped).
			if sb != null and sb.has_method("note_llm_spend"):
				sb.note_llm_spend(float(act.get("_cost", 0.0)))
			for k in ["_prompt", "_llm_response", "_tokens_in", "_tokens_out", "_cost", "_model", "_outcome"]:
				act.erase(k)
		# A per-agent brain failure (_error) or schema rejection (_invalid) the sidecar tagged: surface
		# it and DON'T cache, so the agent ambient-fills instead of silently replaying a masked idle.
		if act.has("_error") or act.has("_invalid"):
			_al("EventBus").emit_event("sidecar_error", {
				"actor": act.get("actor", ""), "reason": String(act.get("_error", act.get("_invalid", ""))),
			})
			continue
		var verdict: Dictionary = ActionSchema.validate(act)
		if verdict["ok"]:
			_cache[String(act.get("actor", ""))] = act
			_al("EventBus").emit_event("sidecar_proposed", {
				"actor": act.get("actor", ""), "verb": act.get("verb", ""), "args": act.get("args", {}),
			})
		else:
			_al("EventBus").emit_event("sidecar_error", {
				"actor": act.get("actor", ""), "reason": verdict["reason"],
			})
	# P3: an in-flight agent whose action never came back (a malformed reply) still gets its
	# lifecycle fact closed — begin/end pair EXACTLY once per decide, whatever happened.
	for aid in _inflight.keys():
		eb.emit_event("deciding", {"agent": aid, "phase": "end", "beat": beat, "outcome": "dropped"})
		if sb != null and sb.has_method("note_agent_llm"):
			sb.note_agent_llm(String(aid), 0.0, false)
	_inflight.clear()

## The PlayLog autoload if present (it is absent in some unit tests), else null.
func _playlog() -> Node:
	var tree := Engine.get_main_loop() as SceneTree
	return tree.root.get_node_or_null("/root/PlayLog") if tree != null else null

func _drain_pending() -> void:
	_mutex.lock()
	var has := _has_pending
	var actions: Array = _pending_actions.duplicate(true)
	var err := _pending_error
	_has_pending = false
	_pending_actions = []
	_pending_error = ""
	_mutex.unlock()
	if has:
		apply_reply(actions, err)

# --- Background transport ----------------------------------------------------------------
func _launch_refresh(snapshots: Array) -> void:
	if not _claim_worker():
		return
	# The legacy stateless path ships raw snapshots; strip the hidden contexts first — the /decide
	# path already withholds them (Perception.decide_request), and the kill-switch path must not be
	# the one place they leave the engine (build_prompt never renders them, but the wire should not
	# carry them at all). combat_form/combat_intent joined secrets in the combat arc: a form is a
	# secret in ability-shaped clothing, and intent is engine plumbing the LLM must not echo back
	# (final-review #5).
	var sanitized: Array = snapshots.duplicate(true)
	for s in sanitized:
		if s is Dictionary:
			for hidden in ["secrets", "combat_form", "combat_intent"]:
				(s as Dictionary).erase(hidden)
	_thread = Thread.new()
	_thread.start(_refresh_worker.bind(sanitized))

## Brain mode: build per-agent /decide requests on the MAIN thread, then hand them to the worker for
## pure HTTP. Each request carries the full short_memory window with absolute seq ids; the brain
## dedups by seq, so building+sending every beat is idempotent — a skipped (backpressured) beat loses
## nothing. No client-side high-water mark, so there is nothing to corrupt when a beat is dropped.
func _launch_brain_refresh(snapshots: Array) -> void:
	var requests: Array = []
	for snap in snapshots:
		var req: Dictionary = Perception.decide_request(snap as Dictionary, _session_id)
		# Stamp this agent's selected model (the temporary ModelConfig panel); empty/unset → the sidecar
		# uses its own default. This is how "run the cult on Sonnet" reaches the LLM call. Accessed via
		# _al (runtime lookup) — a class_name script can't reference an autoload by its global name.
		var mc := _al("ModelConfig")
		if mc != null:
			req["model"] = mc.model_for(String((snap as Dictionary).get("agent_id", "")))
		requests.append(req)
	if not _claim_worker():
		return
	# P3: announce each launched decide as ONE typed lifecycle fact — `deciding {agent, phase:
	# begin, beat}` — consumed by PlayLog and the thought panel's thinking tell, and closed
	# exactly once by apply_reply when the reply (or its timeout) lands. Emitted only after the
	# worker slot is claimed, so a skipped (busy) beat announces nothing.
	var eb := _al("EventBus")
	var beat := int(_al("Clock").beat_index)
	for req in requests:
		var aid := String((req as Dictionary).get("agent_id", ""))
		if aid != "":
			_inflight[aid] = beat
			eb.emit_event("deciding", {"agent": aid, "phase": "begin", "beat": beat})
	_thread = Thread.new()
	_thread.start(_brain_worker.bind(requests))

## Claim the single in-flight slot. Returns false if a request is already running (don't pile up).
func _claim_worker() -> bool:
	_mutex.lock()
	var busy := _busy
	if not busy:
		_busy = true
	_mutex.unlock()
	if busy:
		return false
	if _thread != null and _thread.is_started():
		_thread.wait_to_finish()
	return true

## Runs on the worker thread. Pure HTTP + JSON — touches no engine state; results go back through
## the mutex-guarded pending buffer for the main thread to apply.
func _refresh_worker(snaps: Array) -> void:
	_publish(_http_propose(snaps))

func _brain_worker(requests: Array) -> void:
	_publish(_http_decide(requests))

func _publish(result: Dictionary) -> void:
	_mutex.lock()
	_pending_actions = result.get("actions", [])
	_pending_error = String(result.get("error", ""))
	_has_pending = true
	_busy = false
	_mutex.unlock()

func _http_propose(snaps: Array) -> Dictionary:
	return _http_post("/propose", {"snapshots": snaps})

## Brain mode: one POST carrying every agent's decide request; the sidecar returns an `actions`
## array shaped exactly like /propose, so apply_reply/pick/cache are reused unchanged.
func _http_decide(requests: Array) -> Dictionary:
	return _http_post("/decide", {"requests": requests})

func _http_post(path: String, body_dict: Dictionary) -> Dictionary:
	var ex := _http_exchange(path, body_dict)
	if String(ex.get("error", "")) != "":
		return {"actions": [], "error": String(ex["error"])}
	return _parse_body(String(ex.get("text", "")))

## One player↔NPC conversation turn (design §2). SYNCHRONOUS: it blocks the calling thread for the
## round-trip, which is fine for a player-initiated dialogue (the UI shows a spinner) but would be wrong
## for the real-time beat (that path stays threaded + cached). Returns { say, action, replies };
## degrades to silence on any transport/parse error so the dialogue UI never crashes.
func converse(request: Dictionary) -> Dictionary:
	# Unconfigured (no URL) degrades to the AMBIENT offline conversation, exactly like propose():
	# the dialogue panel must never fall silent just because no sidecar is wired.
	if base_url == "":
		return super.converse(request)
	# This NPC's selected model (temporary ModelConfig panel); empty/unset → the sidecar's default.
	var mc := _al("ModelConfig")
	if mc != null:
		request["model"] = mc.model_for(String(request.get("agent_id", "")))
	var ex := _http_exchange("/converse", request)
	if String(ex.get("error", "")) != "":
		push_warning("[sidecar] converse: %s" % ex["error"])
		return {"say": "", "action": null, "replies": []}
	var parsed: Variant = JSON.parse_string(String(ex.get("text", "")))
	if typeof(parsed) != TYPE_DICTIONARY or not bool((parsed as Dictionary).get("ok", false)):
		return {"say": "", "action": null, "replies": []}
	var d: Dictionary = parsed
	var act: Variant = d.get("action")
	var reps: Variant = d.get("replies", [])
	return {
		"say": String(d.get("say", "")),
		"action": act if act is Dictionary else null,
		"replies": reps if reps is Array else [],
	}

## Narrate one GM digest (the GM panel's hybrid seam). SYNCHRONOUS blocking HTTP like converse();
## the GM panel calls it from its own worker thread, so the frame never blocks. Stamps the GM's
## selected model (ModelConfig "gm" = the default row) and POSTs {events, world, model} to /narrate.
## Returns {"summary": String}; degrades to {} on any transport/parse error, so the panel just keeps
## its deterministic digest — a missing narration is never an error the player sees.
func narrate(request: Dictionary) -> Dictionary:
	if base_url == "":
		return {}   # pure-ambient configuration: no network, no narration
	# The GM model arrives PRE-STAMPED by GMPanel on the main thread — this method runs on the
	# panel's worker thread, where a ModelConfig (/root) lookup would touch the scene tree
	# off-thread. No fallback lookup here on purpose; absent model → the sidecar's own default.
	var ex := _http_exchange("/narrate", request)
	if String(ex.get("error", "")) != "":
		push_warning("[sidecar] narrate: %s" % ex["error"])
		return {}
	var parsed: Variant = JSON.parse_string(String(ex.get("text", "")))
	if typeof(parsed) != TYPE_DICTIONARY or not bool((parsed as Dictionary).get("ok", false)):
		return {}
	# B4 finding #1: carry the realized cost back so the GM panel can feed it to the session budget
	# guard on the main thread (note_llm_spend). The "cost" key present == a real /narrate round-trip
	# happened; the offline/ambient/error paths return {} without it, so they are never billed.
	return {
		"summary": String((parsed as Dictionary).get("summary", "")),
		"cost": float((parsed as Dictionary).get("cost", 0.0)),
	}

## Shared blocking transport: POST body_dict to path; returns {text, error}. Pure HTTP, no JSON parse,
## so /propose, /decide, /converse, and /narrate can each parse the body their own way.
func _http_exchange(path: String, body_dict: Dictionary) -> Dictionary:
	var u: Dictionary = _split_url(base_url)
	var http := HTTPClient.new()
	var tls: TLSOptions = TLSOptions.client() if u["use_ssl"] else null
	if http.connect_to_host(String(u["host"]), int(u["port"]), tls) != OK:
		return {"text": "", "error": "connect failed"}
	var deadline := Time.get_ticks_msec() + int(timeout_sec * 1000.0)
	while http.get_status() in [HTTPClient.STATUS_CONNECTING, HTTPClient.STATUS_RESOLVING]:
		http.poll()
		if Time.get_ticks_msec() > deadline:
			return {"text": "", "error": "connect timeout"}
		OS.delay_msec(5)
	if http.get_status() != HTTPClient.STATUS_CONNECTED:
		return {"text": "", "error": "not connected"}
	var body := JSON.stringify(body_dict)
	if http.request(HTTPClient.METHOD_POST, path, ["Content-Type: application/json"], body) != OK:
		return {"text": "", "error": "request failed"}
	while http.get_status() == HTTPClient.STATUS_REQUESTING:
		http.poll()
		if Time.get_ticks_msec() > deadline:
			return {"text": "", "error": "request timeout"}
		OS.delay_msec(5)
	if http.get_response_code() != 200:
		return {"text": "", "error": "http %d" % http.get_response_code()}
	var buf := PackedByteArray()
	while http.get_status() == HTTPClient.STATUS_BODY:
		http.poll()
		var chunk := http.read_response_body_chunk()
		if chunk.size() > 0:
			buf.append_array(chunk)
		elif Time.get_ticks_msec() > deadline:
			return {"text": "", "error": "body timeout"}
		else:
			OS.delay_msec(2)
	return {"text": buf.get_string_from_utf8(), "error": ""}

## Pure: turn the sidecar's JSON envelope into {actions, error}. Separated out so it is testable
## without a socket.
func _parse_body(text: String) -> Dictionary:
	var parsed: Variant = JSON.parse_string(text)
	if typeof(parsed) != TYPE_DICTIONARY:
		return {"actions": [], "error": "bad json"}
	var d: Dictionary = parsed
	if not bool(d.get("ok", false)):
		return {"actions": [], "error": String(d.get("error", "sidecar not ok"))}
	var acts: Variant = d.get("actions", [])
	return {"actions": acts if acts is Array else [], "error": ""}

## Pure: split "http(s)://host:port[/...]" into {host, port, use_ssl}.
static func _split_url(url: String) -> Dictionary:
	var use_ssl := url.begins_with("https://")
	var rest := url
	if rest.begins_with("http://"):
		rest = rest.substr(7)
	elif rest.begins_with("https://"):
		rest = rest.substr(8)
	var slash := rest.find("/")
	if slash != -1:
		rest = rest.substr(0, slash)
	var host := rest
	var port := 443 if use_ssl else 80
	var colon := rest.rfind(":")
	if colon != -1:
		host = rest.substr(0, colon)
		port = int(rest.substr(colon + 1))
	return {"host": host, "port": port, "use_ssl": use_ssl}

## Join any in-flight worker before the game tears down. Safe to call when no thread is running.
func shutdown() -> void:
	if _thread != null and _thread.is_started():
		_thread.wait_to_finish()
	_thread = null
