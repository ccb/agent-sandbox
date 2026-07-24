extends Node
## The one place the landing menu and the viewer agree on "what did the user
## pick?" (issue #399). Registered as the `LaunchConfig` autoload (see
## project.godot), so it's a single persistent instance that survives the scene
## swap from scenes/main_menu.tscn to scenes/viewer.tscn — the menu writes
## the choice here, the viewer reads it in _ready(), and back-to-menu resets it.
##
## No `class_name`: the autoload name IS the global (LaunchConfig.mode, …), and a
## class_name of the same name would collide with it.
##
## When `mode == NONE` (a direct launch: run.sh, F6 on viewer.tscn, the
## smoke test), the viewer falls through to its original export/env-var behaviour —
## so every existing deep link into the scene keeps working untouched.

enum Mode { NONE, REPLAY, LIVE }

## What the user chose on the landing page. NONE = the scene was launched directly,
## not via the menu, so honour the exports / SIM_API_URL env var as before.
var mode := Mode.NONE

## REPLAY: absolute OS path or res:// path of the replay JSON to play.
var replay_path := ""

## REPLAY (from the Past-runs browser, #716): the replay JSON text fetched from
## GET /runs/{id}/replay, handed straight to the viewer. Set instead of
## replay_path so "open a stored run" works identically on desktop and web
## (the web loader ignores replay_path; both honour this).
var replay_text := ""

## LIVE: the backend base URL (already normalised — scheme, no trailing slash) and
## its optional Bearer token.
var live_url := ""
var live_token := ""

## The last live URL we connected to, kept across a back-to-menu so the menu can
## prefill it for a one-click reconnect. Unlike `live_url` it survives reset().
var last_live_url := ""

## RE-RUN (#734): a saved manifest's `config` block, stashed by the Past-runs
## browser's "Re-run with this setup" so the Simulation Setup scene pre-fills its
## cast + knobs from it. Read-once: the setup scene captures and clears it in
## _ready(), so a later fresh entry from the menu never inherits a stale seed.
var setup_seed := {}


# The two REPLAY sources are mutually exclusive: the viewer (_ready) prefers
# replay_text over replay_path, so each setter clears the other -- a value left
# over from a prior choice must never linger and hijack the next play.
func set_replay(path: String) -> void:
	mode = Mode.REPLAY
	replay_path = path
	replay_text = ""


func set_replay_text(text: String) -> void:
	mode = Mode.REPLAY
	replay_text = text
	replay_path = ""


func set_live(url: String, token: String) -> void:
	mode = Mode.LIVE
	live_url = url
	live_token = token
	last_live_url = url


func reset() -> void:
	# Back to a direct-launch state. We deliberately keep last_live_url and
	# live_token so returning to the menu can prefill the live form for a reconnect.
	mode = Mode.NONE
	replay_path = ""
	replay_text = ""
	live_url = ""
	setup_seed = {}
