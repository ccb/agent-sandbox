extends "res://scripts/hud_source.gd"
## Simulated usage feed for baked-replay mode (issue #264).
##
## A baked replay has no backend and spent no real money, but the run-monitor
## HUD should still be exercisable today -- so this source plays the part of a
## live backend's ledger: while the replay is playing it accrues a plausible
## LLM spend (one decision call per persona every TICK_SEC of wall-clock time,
## priced like a real cheap model), reports it in the exact
## `UsageLedger.summary()` shape the real `GET /usage` returns, and lets the
## Emergency Stop trip a mock budget gate. Swap in hud_source_live.gd and the
## HUD shows real numbers instead -- nothing else changes.
##
## The numbers are cumulative and monotone, like a real ledger: seeking the
## replay backwards does NOT rewind the meter (money, once spent, stays spent).
## They accrue in wall-clock time while playback runs, because that is what the
## live HUD will show -- a run burning tokens as you watch -- rather than being
## a function of the playhead. Everything is deterministic (a hash of persona
## name + tick index provides the jitter), so two runs of the same length read
## the same.

# How often (real seconds) the fake backend "completes a round of decisions":
# one LLM call per persona per tick. ~1.5s per round reads like a brisk live
# run without the meter blurring.
const TICK_SEC := 1.5
# Per-call token shape: a ReAct decision prompt is ~1k tokens in, a short
# labeled Reasoning:/Action: reply out. Jitter (below) varies each call a bit.
const BASE_INPUT_TOKENS := 900
const INPUT_JITTER := 300
const BASE_OUTPUT_TOKENS := 70
const OUTPUT_JITTER := 80
# After the first round, most of the prompt (system text, world description)
# would be served from the provider's prompt cache; this fraction of the input
# is billed as a cache read instead of full-price input.
const CACHE_READ_FRACTION := 0.65
# Priced like claude-haiku-4-5 (see PRICES in text_adventure_games/usage.py):
# $/1M tokens for input/output; cache writes cost 1.25x input, reads 0.10x.
const PRICE_IN_PER_M := 1.00
const PRICE_OUT_PER_M := 5.00
const MODEL_LABEL := "mock (haiku-priced)"
# The mock budget ceiling (the ledger's max_cost_usd, issue #183). Generous on
# purpose: it trips via the Emergency Stop, not by natural accrual mid-demo.
const SIM_BUDGET_USD := 5.00

var _names: Array = []
var _running := false
var _halted := false
var _tripped := false  # the mock #183 kill-switch: set by Stop, cleared by resume
var _tick := 0         # rounds completed so far; also the jitter seed
# Cumulative totals, mirroring UsageLedger's counters.
var _calls := 0
var _input_tokens := 0
var _output_tokens := 0
var _cache_creation_tokens := 0
var _cache_read_tokens := 0
var _cost_usd := 0.0
var _by_actor := {}  # name -> cumulative cost (the summary's by_actor rollup)


func _ready() -> void:
	# The fake backend's clock. It always ticks; _on_tick just does nothing
	# while playback is paused/halted or the replay hasn't loaded yet.
	var timer := Timer.new()
	timer.wait_time = TICK_SEC
	timer.timeout.connect(_on_tick)
	add_child(timer)
	timer.start()
	# Tell the HUD what it's looking at, and seed the meter with zeros so it
	# doesn't sit blank until the first tick.
	health_changed.emit(Health.SIMULATED, "baked replay — no backend")
	usage_updated.emit(_summary())


func set_cast(names: Array) -> void:
	_names = names.duplicate()


func set_running(running: bool) -> void:
	_running = running


func request_stop() -> void:
	# The mock emergency stop: mark the run halted AND trip the budget gate,
	# mirroring what the live stop will do (POST /pause + the #183 kill-switch).
	_halted = true
	_tripped = true
	usage_updated.emit(_summary())  # so the Budget row shows TRIPPED at once
	halted_changed.emit(true)


func request_resume() -> void:
	_halted = false
	_tripped = false
	usage_updated.emit(_summary())
	halted_changed.emit(false)


func _on_tick() -> void:
	# One round of decisions: every persona makes one LLM call. Skipped while
	# the viewer says the run isn't advancing (paused, halted, replay ended).
	if not _running or _halted or _names.is_empty():
		return
	_tick += 1
	for name in _names:
		_accrue_call(String(name))
	usage_updated.emit(_summary())


func _accrue_call(name: String) -> void:
	# Deterministic per-call jitter: hash the persona + tick so the numbers
	# wobble like real traffic but replay identically run to run.
	var h: int = absi(hash("%s:%d" % [name, _tick]))
	var prompt: int = BASE_INPUT_TOKENS + h % (INPUT_JITTER + 1)
	var output: int = BASE_OUTPUT_TOKENS + (h / 1000) % (OUTPUT_JITTER + 1)

	# First round writes the prompt cache; later rounds mostly read from it.
	var cached := int(prompt * CACHE_READ_FRACTION)
	var uncached := prompt - cached
	var cache_write := 0
	var cache_read := 0
	if _tick <= 1:
		cache_write = cached
	else:
		cache_read = cached

	# Same pricing rule as usage.price(): writes 1.25x input, reads 0.10x.
	var cost := (
		uncached / 1e6 * PRICE_IN_PER_M
		+ cache_write / 1e6 * PRICE_IN_PER_M * 1.25
		+ cache_read / 1e6 * PRICE_IN_PER_M * 0.10
		+ output / 1e6 * PRICE_OUT_PER_M
	)

	_calls += 1
	_input_tokens += uncached
	_output_tokens += output
	_cache_creation_tokens += cache_write
	_cache_read_tokens += cache_read
	_cost_usd += cost
	_by_actor[name] = float(_by_actor.get(name, 0.0)) + cost

	# One llm_call record per fake call, in the exact shape the live feed
	# carries (see hud_source.gd) -- so the HUD's request log demos offline
	# the same way the rest of the meter does.
	llm_call.emit({
		"kind": "llm_call",
		"call_no": _calls,
		"time": Time.get_time_string_from_system(),
		"role": "decide",
		"actor": name,
		"turn": _tick,
		"model": MODEL_LABEL,
		"input_tokens": uncached,
		"output_tokens": output,
		"cache_creation_input_tokens": cache_write,
		"cache_read_input_tokens": cache_read,
		"cost_usd": cost,
		"cum_cost_usd": _cost_usd,
		"latency_ms": null,
	})


func _summary() -> Dictionary:
	# The exact UsageLedger.summary() shape (plus the ledger's optional budget
	# fields), so the HUD renders this and the real GET /usage identically.
	return {
		"kind": "summary",
		"model": MODEL_LABEL,
		"calls": _calls,
		"total_cost_usd": _cost_usd,
		"by_actor": _by_actor.duplicate(),
		"input_tokens": _input_tokens,
		"output_tokens": _output_tokens,
		"cache_creation_input_tokens": _cache_creation_tokens,
		"cache_read_input_tokens": _cache_read_tokens,
		"max_cost_usd": SIM_BUDGET_USD,
		"over_budget": _tripped or _cost_usd >= SIM_BUDGET_USD,
	}
