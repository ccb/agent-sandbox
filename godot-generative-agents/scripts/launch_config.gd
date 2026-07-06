extends Node
## The one place the landing menu and the viewer agree on "what did the user
## pick?" (issue #399). Registered as the `LaunchConfig` autoload (see
## project.godot), so it's a single persistent instance that survives the scene
## swap from scenes/main_menu.tscn to scenes/penn_replay.tscn — the menu writes
## the choice here, the viewer reads it in _ready(), and back-to-menu resets it.
##
## No `class_name`: the autoload name IS the global (LaunchConfig.mode, …), and a
## class_name of the same name would collide with it.
##
## When `mode == NONE` (a direct launch: run_replay.sh, F6 on penn_replay.tscn, the
## smoke test), the viewer falls through to its original export/env-var behaviour —
## so every existing deep link into the scene keeps working untouched.

enum Mode { NONE, REPLAY, LIVE }

## What the user chose on the landing page. NONE = the scene was launched directly,
## not via the menu, so honour the exports / SIM_API_URL env var as before.
var mode := Mode.NONE

## REPLAY: absolute OS path or res:// path of the replay JSON to play.
var replay_path := ""

## LIVE: the backend base URL (already normalised — scheme, no trailing slash) and
## its optional Bearer token.
var live_url := ""
var live_token := ""

## The last live URL we connected to, kept across a back-to-menu so the menu can
## prefill it for a one-click reconnect. Unlike `live_url` it survives reset().
var last_live_url := ""


func set_replay(path: String) -> void:
	mode = Mode.REPLAY
	replay_path = path


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
	live_url = ""
