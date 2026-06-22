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

var _cache: Dictionary = {}      # agent_id -> most-recent LLM action
var _mutex: Mutex = Mutex.new()
var _thread: Thread = null
var _busy: bool = false
# Reply buffer filled by the worker, drained on the next main-thread propose().
var _pending_actions: Array = []
var _pending_error: String = ""
var _has_pending: bool = false

func _init(url: String = "") -> void:
	base_url = url

func propose(snapshots: Array) -> Array:
	# Not configured -> behave exactly like the ambient brain, no network, no thread.
	if base_url == "":
		return super.propose(snapshots)
	_drain_pending()                       # apply the previous beat's reply (main thread)
	var out: Array = pick(snapshots)       # freshest cache over ambient fallback
	_launch_refresh(snapshots)             # request next beat's proposals
	return out

## Build this beat's actions: the cached LLM action per agent, or the ambient goal-seek when we
## have not heard about that agent yet. Pure; safe to unit-test without any networking.
func pick(snapshots: Array) -> Array:
	var ambient: Array = super.propose(snapshots)
	var out: Array = []
	_mutex.lock()
	for i in snapshots.size():
		var aid := String((snapshots[i] as Dictionary).get("agent_id", ""))
		out.append(_cache.get(aid, ambient[i]))
	_mutex.unlock()
	return out

## Apply one completed reply on the main thread: cache valid actions and log every outcome to the
## EventBus so the debug overlay shows the LLM's proposals and errors. Invalid actions are dropped
## (AgentRuntime would reject them anyway) and surfaced as sidecar_error.
func apply_reply(actions: Array, error: String) -> void:
	if error != "":
		_al("EventBus").emit_event("sidecar_error", {"reason": error})
		return
	for a in actions:
		if typeof(a) != TYPE_DICTIONARY:
			continue
		var act: Dictionary = a
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
	_mutex.lock()
	var busy := _busy
	if not busy:
		_busy = true
	_mutex.unlock()
	if busy:
		return   # a request is already in flight; don't pile up
	if _thread != null and _thread.is_started():
		_thread.wait_to_finish()
	_thread = Thread.new()
	_thread.start(_refresh_worker.bind(snapshots.duplicate(true)))

## Runs on the worker thread. Pure HTTP + JSON — touches no engine state; results go back through
## the mutex-guarded pending buffer for the main thread to apply.
func _refresh_worker(snaps: Array) -> void:
	var result: Dictionary = _http_propose(snaps)
	_mutex.lock()
	_pending_actions = result.get("actions", [])
	_pending_error = String(result.get("error", ""))
	_has_pending = true
	_busy = false
	_mutex.unlock()

func _http_propose(snaps: Array) -> Dictionary:
	var u: Dictionary = _split_url(base_url)
	var http := HTTPClient.new()
	var tls: TLSOptions = TLSOptions.client() if u["use_ssl"] else null
	if http.connect_to_host(String(u["host"]), int(u["port"]), tls) != OK:
		return {"actions": [], "error": "connect failed"}
	var deadline := Time.get_ticks_msec() + int(timeout_sec * 1000.0)
	while http.get_status() in [HTTPClient.STATUS_CONNECTING, HTTPClient.STATUS_RESOLVING]:
		http.poll()
		if Time.get_ticks_msec() > deadline:
			return {"actions": [], "error": "connect timeout"}
		OS.delay_msec(5)
	if http.get_status() != HTTPClient.STATUS_CONNECTED:
		return {"actions": [], "error": "not connected"}
	var body := JSON.stringify({"snapshots": snaps})
	if http.request(HTTPClient.METHOD_POST, "/propose", ["Content-Type: application/json"], body) != OK:
		return {"actions": [], "error": "request failed"}
	while http.get_status() == HTTPClient.STATUS_REQUESTING:
		http.poll()
		if Time.get_ticks_msec() > deadline:
			return {"actions": [], "error": "request timeout"}
		OS.delay_msec(5)
	if http.get_response_code() != 200:
		return {"actions": [], "error": "http %d" % http.get_response_code()}
	var buf := PackedByteArray()
	while http.get_status() == HTTPClient.STATUS_BODY:
		http.poll()
		var chunk := http.read_response_body_chunk()
		if chunk.size() > 0:
			buf.append_array(chunk)
		elif Time.get_ticks_msec() > deadline:
			return {"actions": [], "error": "body timeout"}
		else:
			OS.delay_msec(2)
	return _parse_body(buf.get_string_from_utf8())

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
