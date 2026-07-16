extends Node
## The single seam between the substrate and the LLM brain (autoload `SidecarBridge`).
## Holds one active SidecarClient, chosen at boot:
##   - TINGEN_SIDECAR_URL set -> HttpSidecar, the real LLM brain (Python agent-sidecar over HTTP),
##     with AmbientSidecar goal-seeking as its built-in fallback so nothing freezes if it is down;
##   - otherwise           -> AmbientSidecar, the offline brain that moves the district with no API.
## Tests pin a MockSidecar explicitly for deterministic scripted behavior. The agent runtime calls
## `propose(snapshots)` here and nowhere else.

const SIDECAR_URL_ENV: String = "TINGEN_SIDECAR_URL"

## B4 (M21) — session LLM budget guard. Nothing capped LLM spend anywhere: a live run POSTed to the
## brain every beat (and GMPanel every 30s) with no ceiling. This is the single seam every LLM call
## already flows through (propose/converse), so the cap lives HERE: once cumulative cost OR call count
## passes a configurable ceiling, the bridge DEGRADES to the offline ambient brain (zero further LLM
## calls) instead of billing forever. A ceiling of 0 disables that dimension.
const BUDGET_COST_ENV: String = "TINGEN_LLM_BUDGET"       # dollars (float); default below
const BUDGET_CALLS_ENV: String = "TINGEN_LLM_CALL_CAP"    # call count (int); default below
const DEFAULT_COST_CEILING: float = 5.0
const DEFAULT_CALL_CEILING: int = 4000

signal budget_exceeded_changed(exceeded: bool)

var client: SidecarClient = null

var budget_cost_ceiling: float = DEFAULT_COST_CEILING
var budget_call_ceiling: int = DEFAULT_CALL_CEILING
var _spend_cost: float = 0.0
var _spend_calls: int = 0
var _degraded: bool = false
var _ambient_fallback: SidecarClient = null

func _ready() -> void:
	if OS.has_environment(BUDGET_COST_ENV):
		budget_cost_ceiling = float(OS.get_environment(BUDGET_COST_ENV))
	if OS.has_environment(BUDGET_CALLS_ENV):
		budget_call_ceiling = int(OS.get_environment(BUDGET_CALLS_ENV))
	if client == null:
		var url := OS.get_environment(SIDECAR_URL_ENV) if OS.has_environment(SIDECAR_URL_ENV) else ""
		if url != "":
			client = HttpSidecar.new(url)
			print("[sidecar] live brain: HttpSidecar -> %s" % url)
		else:
			client = AmbientSidecar.new()

# --- Budget guard (B4) --------------------------------------------------------------------------
## Record one LLM call's realized cost (fed by HttpSidecar.apply_reply, the same place PlayLog totals
## usage). Crossing the ceiling flips the degrade latch once and surfaces it on the EventBus.
func note_llm_spend(cost: float) -> void:
	_spend_cost += maxf(0.0, cost)
	_spend_calls += 1
	if not _degraded and budget_exceeded():
		_degraded = true
		budget_exceeded_changed.emit(true)
		var eb := get_node_or_null("/root/EventBus")
		if eb != null and eb.has_method("emit_event"):
			eb.emit_event("llm_budget_exceeded", {"cost": _spend_cost, "calls": _spend_calls})
		print("[sidecar] LLM budget reached ($%.4f over %d calls) — degrading to the ambient brain" % [_spend_cost, _spend_calls])

## --- P3 (lab pull-in): per-NPC LLM cost attribution -------------------------------------------
## Every /decide launched for an agent lands HERE when its reply (or its timeout) comes back, so
## LLM spend is attributable to the CAUSING NPC — including calls that timed out (the money was
## spent whether or not the decision arrived in time). Fed by HttpSidecar.apply_reply; read by
## tooling/tests. Complements (never replaces) the session-total note_llm_spend guard above.
var _agent_llm: Dictionary = {}   # agent_id -> {"cost": float, "calls": int, "timeouts": int}

func note_agent_llm(agent_id: String, cost: float, timed_out: bool) -> void:
	if agent_id == "":
		return
	var e: Dictionary = _agent_llm.get(agent_id, {"cost": 0.0, "calls": 0, "timeouts": 0})
	e["cost"] = float(e["cost"]) + maxf(0.0, cost)
	e["calls"] = int(e["calls"]) + 1
	if timed_out:
		e["timeouts"] = int(e["timeouts"]) + 1
	_agent_llm[agent_id] = e

## One agent's attributed ledger ({} when it never caused a call).
func agent_llm(agent_id: String) -> Dictionary:
	return (_agent_llm.get(agent_id, {}) as Dictionary).duplicate(true)

func reset_agent_llm() -> void:
	_agent_llm.clear()

## True once cumulative spend has passed either configured ceiling (a 0 ceiling disables that check).
func budget_exceeded() -> bool:
	if budget_cost_ceiling > 0.0 and _spend_cost >= budget_cost_ceiling:
		return true
	if budget_call_ceiling > 0 and _spend_calls >= budget_call_ceiling:
		return true
	return false

func llm_spend() -> float:
	return _spend_cost

func llm_calls() -> int:
	return _spend_calls

## Re-arm the guard (a new session, or a test). Clears the running totals and the degrade latch.
func reset_budget() -> void:
	_spend_cost = 0.0
	_spend_calls = 0
	if _degraded:
		_degraded = false
		budget_exceeded_changed.emit(false)

## Configure the ceilings (tests / a settings screen). A 0 ceiling disables that dimension.
func set_budget(cost_ceiling: float, call_ceiling: int) -> void:
	budget_cost_ceiling = cost_ceiling
	budget_call_ceiling = call_ceiling

## The deterministic offline brain the guard falls back to (lazily built; shares prayer adjudication).
func _ambient() -> SidecarClient:
	if _ambient_fallback == null:
		_ambient_fallback = AmbientSidecar.new()
	return _ambient_fallback

## The active brain for THIS call — the ambient fallback once over budget, else the live client.
func _active_client() -> SidecarClient:
	return _ambient() if budget_exceeded() else client

func _exit_tree() -> void:
	if _cv_thread != null and _cv_thread.is_started():
		_cv_thread.wait_to_finish()
	_cv_thread = null
	_reap_orphans()
	if client != null and client.has_method("shutdown"):
		client.call("shutdown")

func set_client(c: SidecarClient) -> void:
	client = c

func is_ready() -> bool:
	return client != null and client.is_ready()

func propose(snapshots: Array) -> Array:
	# B4: once the session budget is spent, route to the ambient brain — zero further LLM calls,
	# the world keeps moving deterministically.
	var c := _active_client()
	if c == null:
		return []
	return c.propose(snapshots)

func adjudicate_prayer(request: Dictionary) -> Dictionary:
	if client == null:
		return {"god": String(request.get("god", "")), "outcome": "ignored", "outcome_zh": "无应", "severity": 0, "score": 0}
	return client.adjudicate_prayer(request)

## One player↔NPC conversation turn (design §2). Delegates to the active client; null/empty default so
## a missing client degrades to silence rather than crashing the dialogue UI. SYNCHRONOUS — kept for the
## deterministic offline/test path; the LIVE dialogue UI uses converse_async so the LLM round-trip never
## blocks the frame (GAP-2.3). The request must be fully STAMPED by the caller on the main thread first
## (ModelConfig etc.) — the worker thread must not touch the scene tree.
func converse(request: Dictionary) -> Dictionary:
	# B4: over budget -> the offline ambient conversation, no LLM call.
	var c := _active_client()
	if c == null:
		return {"say": "", "action": null, "replies": []}
	return c.converse(request)

# --- Async conversation transport (GAP-2.3 de-freeze) -----------------------------------------------
## The LLM converse round-trip blocks for SECONDS; running it on the main thread hard-freezes the
## window (audit GAP-2.3). So the transport runs on a background Thread — the SAME worker idiom as
## GMPanel.narrate and HttpSidecar's beat refresh: the main thread stamps the request, the worker does
## the pure blocking client.converse(), and the reply comes back through a mutex-guarded buffer + a
## thread-safe call_deferred that fires `converse_reply` on the main thread. One turn in flight at a
## time (a second send while thinking is ignored upstream). An instant client (Mock/Ambient) finishes
## on the worker immediately with no deadlock; a real thread that returns fast is fine too.
signal converse_reply(reply: Dictionary)

var _cv_thread: Thread = null
var _cv_mutex: Mutex = Mutex.new()
var _cv_busy: bool = false
var _cv_pending: Dictionary = {}
var _cv_has_pending: bool = false
# Generation token (GAP-2.3 finding #1): each kick stamps a generation onto its worker; the worker's
# reply is only delivered if its generation still matches the CURRENT one. cancel_converse() bumps the
# generation and clears _cv_busy WITHOUT joining, so a leave-and-reswitch during a slow live call frees
# the bridge immediately — the orphaned worker's late reply is dropped and its thread is reaped later.
var _cv_gen: int = 0
var _cv_worker_gen: int = -1            # generation of the thread currently in _cv_thread
var _cv_reaped: Array[Thread] = []      # detached workers awaiting a non-blocking join (reaped off-frame)

## Kick a conversation turn off the main thread. Returns immediately; the reply arrives later on
## `converse_reply` (main thread). `request` MUST be fully stamped by the caller first. Returns false
## if a turn is already in flight (the caller should have guarded, but we never pile up threads).
func converse_async(request: Dictionary) -> bool:
	_cv_mutex.lock()
	var busy := _cv_busy
	if not busy:
		_cv_busy = true
		_cv_gen += 1
	var gen := _cv_gen
	_cv_mutex.unlock()
	if busy:
		return false
	# Reap any previously detached workers opportunistically (they may already be done); this join is
	# on threads we no longer wait ON — in the common path they finished long ago, so it does not block.
	_reap_orphans()
	# The live thread slot should be free here (a running worker means _cv_busy was true → early return
	# above). If a *finished-but-unjoined* thread lingers, join it now (it is already done).
	if _cv_thread != null and _cv_thread.is_started():
		_cv_thread.wait_to_finish()
	# Bind the client on the MAIN thread (finding #2): the worker reads this captured snapshot, never the
	# live autoload field — so a set_client() mid-flight can't hand the worker a torn/swapped reference.
	# B4: over budget, bind the ambient fallback so a slow live dialogue can't run up more spend.
	var snapshot_client: SidecarClient = _active_client()
	_cv_thread = Thread.new()
	_cv_worker_gen = gen
	_cv_thread.start(_converse_worker.bind(snapshot_client, request.duplicate(true), gen))
	return true

## Worker thread: pure client.converse() (blocking HTTP for HttpSidecar, instant for Mock/Ambient) —
## touches no engine state, reads only the client snapshot BOUND on the main thread. The reply goes back
## through the mutex-guarded buffer, tagged with this worker's generation; call_deferred wakes the main
## thread to drain it (which drops the reply if its generation was cancelled meanwhile).
func _converse_worker(bound_client: SidecarClient, request: Dictionary, gen: int) -> void:
	var reply: Dictionary = {"say": "", "action": null, "replies": []}
	if bound_client != null:
		var r: Variant = bound_client.converse(request)
		if r is Dictionary:
			reply = r
	_cv_mutex.lock()
	# Only publish if this worker is still the current generation. A cancelled/superseded worker drops
	# its reply here and does NOT clear _cv_busy (a newer turn owns it).
	if gen == _cv_gen:
		_cv_pending = reply
		_cv_has_pending = true
		_cv_busy = false
	_cv_mutex.unlock()
	call_deferred("_drain_converse")

## Main thread: emit the landed reply. Absent pending (spurious deferred, or a cancelled worker that
## published nothing) is a harmless no-op.
func _drain_converse() -> void:
	_cv_mutex.lock()
	var has := _cv_has_pending
	var reply: Dictionary = _cv_pending.duplicate(true)
	_cv_has_pending = false
	_cv_pending = {}
	_cv_mutex.unlock()
	if has:
		converse_reply.emit(reply)

## Non-blocking cancel (GAP-2.3 finding #1): abandon the in-flight turn so the bridge is free for a NEW
## conversation IMMEDIATELY, without joining the (possibly slow, live-LLM) worker on the main thread.
## Bumping the generation guarantees the orphaned worker's late reply is dropped; its Thread is detached
## into _cv_reaped and joined off-frame (at the next kick, exit, or flush). Safe when nothing is running.
func cancel_converse() -> void:
	_cv_mutex.lock()
	_cv_gen += 1                # invalidate any in-flight worker's generation
	_cv_busy = false           # free the bridge for the next turn right away
	_cv_has_pending = false    # drop any reply already buffered for the abandoned turn
	_cv_pending = {}
	_cv_mutex.unlock()
	if _cv_thread != null:
		# Detach the running worker for a later, non-blocking reap rather than joining here.
		_cv_reaped.append(_cv_thread)
		_cv_thread = null
		_cv_worker_gen = -1
	_reap_orphans()

## Join any detached workers that have ALREADY finished, without blocking on ones still running. Godot's
## Thread has no non-blocking "is done" probe, so a still-running orphan stays in the list; it is reaped
## on a later pass (or force-joined at _exit_tree). In practice the offline/instant clients finish at
## once, and even a slow HTTP worker completes within the timeout, so orphans clear on the next kick.
func _reap_orphans() -> void:
	if _cv_reaped.is_empty():
		return
	var still: Array[Thread] = []
	for t in _cv_reaped:
		if t == null:
			continue
		if t.is_started() and not t.is_alive():
			t.wait_to_finish()   # finished — a real join, but it returns immediately
		elif t.is_alive():
			still.append(t)      # still running — leave it for a later pass, don't block the frame
		# (a never-started thread is simply dropped)
	_cv_reaped = still

## Join any in-flight converse worker and apply its reply NOW — makes the async seam deterministic for
## tests, and safe to call when nothing is in flight. Mirrors GMPanel.flush_narration. Also reaps any
## previously-detached (cancelled) workers so a cancel followed by a flush leaves no live thread behind.
func flush_converse() -> void:
	if _cv_thread != null and _cv_thread.is_started():
		_cv_thread.wait_to_finish()
	_cv_thread = null
	_cv_worker_gen = -1
	# Force-join any detached orphans here (flush is a deterministic barrier — tests rely on it).
	for t in _cv_reaped:
		if t != null and t.is_started():
			t.wait_to_finish()
	_cv_reaped.clear()
	_drain_converse()
