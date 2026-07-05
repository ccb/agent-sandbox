extends "res://scripts/hud_source.gd"
## Live usage feed: polls a running backend for the run-monitor HUD (issue #264).
##
## Talks to the unified backend (backend/api.py, issue #179) over plain HTTP:
##
## * `GET /usage`  (issue #262) -- the engine `UsageLedger.summary()` as JSON:
##   tokens + running cost. Passed through to the HUD verbatim, which is why the
##   HUD renders live and simulated data identically.
## * `GET /health` -- `{"ok": true, "turn": N}`; a slow transport-independent
##   liveness check. Two missed checks in a row = the backend is unreachable.
## * `POST /pause` (issue #262) -- the Emergency Stop. Deliberately plain HTTP,
##   not a WebSocket message: the stop must work precisely when the socket is
##   wedged (that IS the emergency). `POST /resume` lifts it.
##
## When the live viewer client (issue #263) lands, its WebSocket becomes the
## PRIMARY liveness signal -- it should call note_socket_state()/
## note_socket_event() here, and the health poll stays on as the backstop
## (socket open + events flowing = OK; open but silent = degraded; closed =
## fall back to what the poll says).
##
## Auth matches the backend's security model (issue #186): pass the SIM_API_TOKEN
## value and every request carries `Authorization: Bearer <token>`.

# Slow polls on purpose (the issue asks for exactly this): the meter doesn't
# need to be frame-accurate, and a busy backend shouldn't feel HUD traffic.
const USAGE_POLL_SEC := 2.0
const HEALTH_POLL_SEC := 3.0
# With a socket attached (#263): no event for this long while open = degraded.
const SOCKET_SILENT_MS := 8000

var _base_url := ""
var _token := ""
# One HTTPRequest per concern -- a Godot HTTPRequest runs one request at a
# time, and the Emergency Stop must never queue behind an in-flight poll.
var _usage_http: HTTPRequest
var _health_http: HTTPRequest
var _control_http: HTTPRequest
var _control_op := ""  # "pause" or "resume": which request _control_http carries
# Liveness bookkeeping: consecutive failed health checks, the last turn the
# backend reported, and the (optional, #263) socket's state.
var _misses := 0
var _last_turn := -1
var _socket_attached := false
var _socket_open := false
var _socket_last_event_ms := 0
var _halted := false


func configure(base_url: String, token: String) -> void:
	## Point the source at a backend (e.g. "http://127.0.0.1:8000") and start
	## polling. Called once by penn_replay.gd; must run after add_child().
	_base_url = base_url.rstrip("/")
	_token = token

	_usage_http = HTTPRequest.new()
	_usage_http.request_completed.connect(_on_usage_completed)
	add_child(_usage_http)

	_health_http = HTTPRequest.new()
	_health_http.request_completed.connect(_on_health_completed)
	add_child(_health_http)

	_control_http = HTTPRequest.new()
	_control_http.request_completed.connect(_on_control_completed)
	add_child(_control_http)

	var usage_timer := Timer.new()
	usage_timer.wait_time = USAGE_POLL_SEC
	usage_timer.timeout.connect(_poll_usage)
	add_child(usage_timer)
	usage_timer.start()

	var health_timer := Timer.new()
	health_timer.wait_time = HEALTH_POLL_SEC
	health_timer.timeout.connect(_poll_health)
	add_child(health_timer)
	health_timer.start()

	# Don't leave the HUD blank for a poll interval: check in immediately.
	health_changed.emit(Health.DEGRADED, "connecting to %s…" % _base_url)
	_poll_usage()
	_poll_health()


func note_socket_state(open: bool) -> void:
	## Seam for the live client (#263): tell the HUD source whether the event
	## WebSocket is open. Once called, the socket becomes the primary liveness
	## signal and the health poll is just the backstop.
	_socket_attached = true
	_socket_open = open
	if open:
		_socket_last_event_ms = Time.get_ticks_msec()
	_resolve_health()


func note_socket_event() -> void:
	## Seam for the live client (#263): an event just arrived on the socket.
	_socket_last_event_ms = Time.get_ticks_msec()
	_resolve_health()


func request_stop() -> void:
	# Emergency Stop: pause the backend's stepping loop over plain HTTP. This
	# also stops spend at the source (no loop, no LLM calls). When #262 exposes
	# the ledger's #183 kill-switch alongside /pause, trip it here too so a
	# resume can't silently resume spending past the ceiling.
	_send_control("pause")


func request_resume() -> void:
	_send_control("resume")


func _send_control(op: String) -> void:
	# ERR_BUSY = a previous control request is still in flight; the button can
	# simply be pressed again (nothing to queue -- the newest intent wins).
	_control_op = op
	var err := _control_http.request(
		"%s/%s" % [_base_url, op], _headers(), HTTPClient.METHOD_POST, "{}"
	)
	if err != OK and err != ERR_BUSY:
		health_changed.emit(Health.DOWN, "%s request failed to start" % op)


func _on_control_completed(
	result: int, code: int, _headers: PackedStringArray, _body: PackedByteArray
) -> void:
	var ok := result == HTTPRequest.RESULT_SUCCESS and code >= 200 and code < 300
	if ok:
		_halted = _control_op == "pause"
		halted_changed.emit(_halted)
	else:
		# Surface the failure where the operator is already looking. Keep the
		# current health state; this is a one-off command failing, not (yet)
		# evidence the backend is gone -- the health poll decides that.
		health_changed.emit(
			_poll_state(), "%s failed (HTTP %d) — try again" % [_control_op, code]
		)


func _headers() -> PackedStringArray:
	var headers := PackedStringArray(["Content-Type: application/json"])
	if _token != "":
		headers.append("Authorization: Bearer %s" % _token)
	return headers


func _poll_usage() -> void:
	# ERR_BUSY (the previous poll hasn't finished) just means we skip a beat.
	_usage_http.request("%s/usage" % _base_url, _headers())


func _on_usage_completed(
	result: int, code: int, _headers: PackedStringArray, body: PackedByteArray
) -> void:
	if result != HTTPRequest.RESULT_SUCCESS or code != 200:
		return  # liveness is the health poll's job; a missed meter beat is fine
	var parsed: Variant = JSON.parse_string(body.get_string_from_utf8())
	if typeof(parsed) == TYPE_DICTIONARY:
		# Straight through to the HUD: this is UsageLedger.summary() as JSON,
		# the same shape the simulated source synthesizes.
		usage_updated.emit(parsed)


func _poll_health() -> void:
	_health_http.request("%s/health" % _base_url, _headers())


func _on_health_completed(
	result: int, code: int, _headers: PackedStringArray, body: PackedByteArray
) -> void:
	var healthy := false
	if result == HTTPRequest.RESULT_SUCCESS and code == 200:
		var parsed: Variant = JSON.parse_string(body.get_string_from_utf8())
		if typeof(parsed) == TYPE_DICTIONARY and bool(parsed.get("ok", false)):
			healthy = true
			_last_turn = int(parsed.get("turn", -1))
	if healthy:
		_misses = 0
	else:
		_misses += 1
	_resolve_health()


func _poll_state() -> int:
	# The liveness ladder as seen by the HTTP poll alone: healthy / one missed
	# check (a blip or a stalled provider call) / two or more (unreachable).
	if _misses == 0:
		return Health.OK
	return Health.DEGRADED if _misses == 1 else Health.DOWN


func _resolve_health() -> void:
	# Combine the two signals. Socket first (when #263 has attached one): open
	# and flowing is the strongest OK there is; open-but-silent is degraded even
	# if HTTP still answers (events are the product); closed defers to the poll,
	# which can at most say "degraded" -- a dead socket is never fully OK.
	var state: int
	var detail: String
	if _socket_attached:
		var silent: bool = (
			Time.get_ticks_msec() - _socket_last_event_ms > SOCKET_SILENT_MS
		)
		if _socket_open and not silent:
			state = Health.OK
			detail = "socket live · turn %d" % _last_turn
		elif _socket_open:
			state = Health.DEGRADED
			detail = "socket open, no events"
		else:
			# Defer to the poll, but never read fully OK with a dead socket.
			state = maxi(_poll_state(), Health.DEGRADED)
			detail = "socket closed" + (" · HTTP ok" if _misses == 0 else "")
	else:
		state = _poll_state()
		match state:
			Health.OK:
				detail = "turn %d" % _last_turn if _last_turn >= 0 else "connected"
			Health.DEGRADED:
				detail = "missed a health check"
			_:
				detail = "backend unreachable"
	health_changed.emit(state, detail)
