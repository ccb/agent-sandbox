extends Node
## Per-playthrough transcript (autoload `PlayLog`) — written to read cleanly as PLAIN TEXT (it is a
## .md file, but no tables/markup you need a previewer to make sense of).
##
## EventBus carries everything that happens. We render it top-to-bottom:
##   - beats are separated by a line of dashes; entries within a beat by a blank line;
##   - each AGENT action is a 3-line chunk: a one-sentence summary, its intent, its exact args;
##   - WORLD events (the descent, the ending, ...) are a single line.
## The full LLM prompt + raw reply for every decision is collected at the bottom. One file per play;
## the newest KEEP_PLAYS are kept in the project's playlogs/ dir.
##
## Inert in the headless unit-test harness (no main scene), so the suite writes nothing.

const KEEP_PLAYS: int = 5
const REL_DIR := "res://playlogs/"

## N1 (sprint safety): the ACTIVE flush dir — REDIRECTABLE (absolute path) so a test harness that
## mounts a real scene can never flush transcripts into (or rotate away) the repo's playlogs/.
## Live play never touches this default; src/TestSandbox.gd `activate()` points it at the sandbox.
var dir_override: String = ""
const SEP := "--------------------------------------------------------------------------------"

# Actions committed by the agent runtime — rendered as 3-line chunks.
const AGENT_EVENTS := ["agent_action", "agent_action_amended", "overseer_directive"]
# Redundant with the agent chunk (the raw proposal) or its effect, or too noisy — left out.
const SKIP_EVENTS := ["sidecar_proposed", "ritual_advanced"]

const SUMMARY_WIDTH := 110   # reserved width (bytes) of the top usage line we overwrite at the end

var _file: FileAccess = null
var _dir: String = ""
var _armed: bool = false
var _last_beat: int = -1
var _exchanges: Array = []          # {beat, actor, prompt, response} for the detail section
var _details_written: bool = false
# Running LLM usage totals, written into the reserved line at the top when the play ends.
var _tok_in: int = 0
var _tok_out: int = 0
var _cost: float = 0.0
var _calls: int = 0
var _model: String = ""
var _summary_offset: int = -1       # byte offset of the reserved usage line
var _world_prev: Dictionary = {}    # last beat's world-state snapshot, for end-of-beat deltas

func _ready() -> void:
	EventBus.event_logged.connect(_on_event)

func _on_event(ev: Dictionary) -> void:
	if not _armed:
		# Arm on the first event of a REAL play (a main scene is loaded). The -s test harness has no
		# current_scene, so it never arms — the suite writes nothing.
		if get_tree().current_scene == null:
			return
		_armed = true
		_start()
	if _file == null or _details_written:
		return
	var t := String(ev.get("type", ""))
	if t in SKIP_EVENTS:
		return
	var beat := int(ev.get("beat", 0))
	if beat != _last_beat:
		if _last_beat != -1:
			_write_world_line()                 # close the beat that just ended
		elif _world_prev.is_empty():
			_world_prev = _world_snapshot()      # baseline before the first beat
		_last_beat = beat
		_file.store_line("")
		_file.store_line(SEP)
		_file.store_line("beat %d" % beat)
	var data: Dictionary = ev.get("data", {})
	_file.store_line("")   # blank line separates entries within the same beat
	if t in AGENT_EVENTS:
		_file.store_line(_summary(t, data))                                   # what they did
		_file.store_line("intent:  %s" % String(data.get("intent", "")))      # their intent
		_file.store_line("args:    %s" % _args_str(data.get("args", {})))      # raw args
		_file.store_line("outcome: %s" % _args_str(data.get("outcome", {})))   # raw outcome
		_file.store_line("scene:   %s" % String(data.get("room", "?")))        # scene/room it happened in
	else:
		_file.store_line(_world_line(t, data))                           # one-line world event
	if t == "endgame":
		_write_details()
	else:
		_file.flush()

# --- rendering -----------------------------------------------------------------------------------
## One-sentence summary of an agent action, e.g. "Clerk Voss moves toward crypt_altar."
func _summary(event_type: String, data: Dictionary) -> String:
	var who := String(data.get("actor", "")).capitalize()   # clerk_voss -> "Clerk Voss"
	var phrase := _verb_phrase(String(data.get("verb", "")), data.get("args", {}))
	var note := ""
	if event_type == "agent_action_amended":
		note = " (the hard veto amended this)"
	elif event_type == "overseer_directive":
		note = " (on the overseer's directive)"
	return "%s %s.%s" % [who, phrase, note]

func _verb_phrase(verb: String, args: Dictionary) -> String:
	match verb:
		"move_to": return "moves toward %s" % String(args.get("target", "?"))
		"perform_ritual_step": return "works the rite (%s)" % String(args.get("step", ""))
		"talk_to": return "talks to %s about %s" % [String(args.get("agent", "?")), String(args.get("topic", "?"))]
		"gather_item": return "gathers %s" % String(args.get("item_id", "?"))
		"attack": return "attacks %s" % String(args.get("target", "?"))
		"flee": return "flees from %s" % String(args.get("from", "?"))
		"hide": return "goes to ground"
		"recruit": return "tries to recruit %s" % String(args.get("agent", "?"))
		"report": return "reports to %s" % String(args.get("to", "?"))
		"pray": return "prays to %s" % String(args.get("god", "?"))
		"idle": return "waits"
		_: return "does %s" % verb

## --- per-beat world state -----------------------------------------------------------------------
func _al(n: String) -> Node:
	var tree := get_tree()
	return tree.root.get_node_or_null("/root/" + n) if tree != null else null

## Snapshot the world-level variables we summarize at the end of each beat.
func _world_snapshot() -> Dictionary:
	var snap: Dictionary = {}
	var sp := _al("SummoningPlan")
	if sp != null:
		snap["descent_done"] = int(sp.START_COUNTDOWN) - int(sp.countdown_beats)
		snap["descent_total"] = int(sp.START_COUNTDOWN)
	var ws := _al("WorldState")
	if ws != null:
		snap["corruption"] = roundi(float(ws.corruption))
		snap["panic"] = roundi(float(ws.panic))
		snap["cult_readiness"] = roundi(float(ws.cult_readiness))
		snap["attention"] = roundi(float(ws.attention))
	var wm := _al("WorldManager")
	if wm != null and "current_stage_id" in wm:
		snap["stage"] = String(wm.current_stage_id)
	return snap

## End-of-beat line: how many descent steps are done, plus every world variable that changed
## (prev -> now) since the last beat.
func _write_world_line() -> void:
	if _file == null:
		return
	var cur := _world_snapshot()
	var parts: Array = []
	if cur.has("descent_done"):
		parts.append("descent %d/%d steps done" % [int(cur["descent_done"]), int(cur["descent_total"])])
	for k in ["corruption", "panic", "cult_readiness", "attention", "stage"]:
		if cur.has(k) and _world_prev.has(k) and str(_world_prev[k]) != str(cur[k]):
			parts.append("%s %s -> %s" % [k, str(_world_prev[k]), str(cur[k])])
	_file.store_line("")
	_file.store_line("[world] " + " | ".join(parts))
	_world_prev = cur

func _args_str(args: Dictionary) -> String:
	if args == null or args.is_empty():
		return "(none)"
	var parts: Array = []
	for k in args:
		var v: Variant = args[k]
		if typeof(v) == TYPE_DICTIONARY or typeof(v) == TYPE_ARRAY:
			v = JSON.stringify(v)
		parts.append("%s=%s" % [str(k), str(v)])
	return ", ".join(parts)

## A single line for a world/player event — the descent and the ending get a headline; NPC scene
## transitions, dialogue, inventory / HP / world-var changes each get a concise readable line that
## mirrors what the in-game debug overlay shows (the overlay HIDES the raw agent action; this .md keeps
## that full 3-line chunk AND these readable consequence lines, so the transcript loses nothing).
func _world_line(t: String, data: Dictionary) -> String:
	match t:
		"summoning_climax":
			return ">>> The True Creator Descends upon Tingen — the summoning succeeds (strength %d). <<<" % int(data.get("strength", 0))
		"endgame":
			var titles := {"city_dies": "Tingen Falls", "near_good": "The Line Holds", "all_good": "Dawn Over Tingen"}
			var outcome := String(data.get("outcome", ""))
			return ">>> %s  (ending: %s) <<<" % [String(titles.get(outcome, "The End")), outcome]
		"agent_moved_room":
			return "%s moved from the %s to the %s." % [
				_name(String(data.get("actor", ""))), _words(String(data.get("from", ""))), _words(String(data.get("to", "")))]
		"npc_said":
			return '%s: "%s"' % [_name(String(data.get("agent", ""))), String(data.get("text", ""))]
		"item_gathered":
			return "%s picked up %s" % [_name(String(data.get("actor", ""))), _words(String(data.get("item_id", "")))]
		"material_deposited":
			return "%s laid %s at the altar" % [_name(String(data.get("actor", ""))), _words(String(data.get("item_id", "")))]
		"agent_attacked":
			return "%s struck (hp %d)" % [_name(String(data.get("target", ""))), int(data.get("target_hp", 0))]
		"agent_downed":
			return "%s downed" % _name(String(data.get("target", "")))
		"world_var_changed":
			return "%s %s -> %s" % [_words(String(data.get("var", ""))), str(data.get("from", "")), str(data.get("to", ""))]
		"deciding":
			# P3: the decide lifecycle fact, rendered diegetically. begin = the LLM call is in
			# flight; end carries how it landed (ok / timeout / error / dropped) — a cut-short
			# deliberation means the offline brain carried that beat.
			var who := _name(String(data.get("agent", "")))
			if String(data.get("phase", "")) == "begin":
				return "%s pauses, weighing the next move (deciding)" % who
			var oc := String(data.get("outcome", "ok"))
			if oc == "ok":
				return "%s settles on a course (deciding done)" % who
			return "%s's deliberation is cut short (%s) — instinct carries the beat" % [who, oc]
		_:
			return "* %s: %s" % [t, _args_str(data)]

## An agent id -> a short readable name, matching the overlay: live display_name if any, else the
## titlecased last id segment ("fishwife_dalia" -> "Dalia", "clerk_voss" -> "Voss").
func _name(agent_id: String) -> String:
	if agent_id == "":
		return "Someone"
	var ag := _al("Agents")
	if ag != null and ag.has_method("get_agent"):
		var a: Object = ag.get_agent(agent_id)
		if a != null and String(a.display_name) != "":
			return String(a.display_name)
	var seg := agent_id.get_slice("_", agent_id.get_slice_count("_") - 1)
	return seg.capitalize() if seg != "" else agent_id.capitalize()

## "ritual_salt"/"cathedral_crypt" -> readable words.
func _words(id: String) -> String:
	return id.replace("_", " ") if id != "" else "?"

# --- LLM exchange detail (bottom of the file) ----------------------------------------------------
## Called by HttpSidecar (verbose dev logging only) with the exact prompt + raw reply for one decision.
func record_exchange(actor: String, prompt: String, response: String) -> void:
	if _file == null or _details_written:
		return
	_exchanges.append({"beat": Clock.beat_index, "actor": actor, "prompt": prompt, "response": response})

## Accumulate one LLM call's token usage + cost (verbose dev logging only).
func add_usage(tokens_in: int, tokens_out: int, cost: float, model: String) -> void:
	if _file == null:
		return
	_tok_in += tokens_in
	_tok_out += tokens_out
	_cost += cost
	_calls += 1
	if model != "":
		_model = model

## Overwrite the reserved top line with the final token + cost totals. Seeks back, writes a
## same-width ASCII line, then returns to the end so the detail section appends correctly.
func _finalize_summary() -> void:
	if _file == null or _summary_offset < 0:
		return
	var line: String
	if _calls == 0:
		line = "Total LLM cost: (no LLM calls captured - run the sidecar with TINGEN_DECIDE_LOG=1)"
	else:
		line = "Total LLM cost: $%.4f for %s input + %s output tokens over %d calls (%s)" % [
			_cost, _commas(_tok_in), _commas(_tok_out), _calls, (_model if _model != "" else "?")]
	var end_pos := _file.get_position()
	_file.seek(_summary_offset)
	_file.store_line(_pad(line))
	_file.seek(end_pos)

func _pad(s: String) -> String:
	if s.length() > SUMMARY_WIDTH:
		s = s.substr(0, SUMMARY_WIDTH)
	return s.rpad(SUMMARY_WIDTH)   # right-pad with spaces to the reserved width (ASCII -> bytes)

## Group digits with thousands commas: 48392 -> "48,392".
func _commas(n: int) -> String:
	var s := str(absi(n))
	var out := ""
	var c := 0
	for i in range(s.length() - 1, -1, -1):
		out = s[i] + out
		c += 1
		if c % 3 == 0 and i > 0:
			out = "," + out
	return ("-" + out) if n < 0 else out

func _write_details() -> void:
	if _file == null or _details_written:
		return
	_details_written = true
	_write_world_line()   # close the final beat's world state
	_finalize_summary()   # overwrite the reserved top line with the token + cost totals
	_file.store_line("")
	_file.store_line("")
	_file.store_line("================================================================================")
	_file.store_line("DETAILED LLM EXCHANGES")
	_file.store_line("the exact prompt sent to, and raw reply from, the LLM for each decision above")
	_file.store_line("(match by beat + actor)")
	_file.store_line("================================================================================")
	if _exchanges.is_empty():
		_file.store_line("")
		_file.store_line("(no prompts captured — run the sidecar with TINGEN_DECIDE_LOG=1 to record them.)")
		_file.flush()
		return
	for ex in _exchanges:
		_file.store_line("")
		_file.store_line("[beat %d · %s]" % [int(ex["beat"]), String(ex["actor"])])
		_file.store_line("--- prompt ---")
		_file.store_line(String(ex["prompt"]))
		_file.store_line("--- reply ---")
		_file.store_line(String(ex["response"]))
	_file.flush()

# --- file lifecycle ------------------------------------------------------------------------------
func _start() -> void:
	_dir = dir_override if dir_override != "" else ProjectSettings.globalize_path(REL_DIR)
	DirAccess.make_dir_recursive_absolute(_dir)
	_rotate()
	var stamp := Time.get_datetime_string_from_system().replace(":", "-").replace("T", "_")
	var path := _dir.path_join("play_%s.md" % stamp)
	# WRITE_READ (not WRITE) so we can seek back and overwrite the reserved usage line at the end.
	_file = FileAccess.open(path, FileAccess.WRITE_READ)
	if _file == null:
		push_warning("PlayLog: could not open %s" % path)
		return
	_file.store_line("Tingen playthrough - %s" % stamp)
	_file.store_line("")
	# Reserve a fixed-width line for the total token count + cost; overwritten in _finalize_summary().
	_summary_offset = _file.get_position()
	_file.store_line(_pad("Total LLM cost: (computed when the play ends)"))
	_file.store_line("")
	_file.store_line("Reads top to bottom. Beats are separated by a line of dashes; entries within a beat by a")
	_file.store_line("blank line. Each agent entry is three lines: what they did, their intent, the exact args.")
	_file.store_line("World events (the descent, the ending) are one line. The full LLM prompt + reply for every")
	_file.store_line("decision is in the DETAILED LLM EXCHANGES section at the bottom.")
	_file.flush()
	print("[PlayLog] this play -> %s" % path)

## Keep only the newest KEEP_PLAYS-1 existing logs, so this run's new file makes KEEP_PLAYS total.
func _rotate() -> void:
	var d := DirAccess.open(_dir)
	if d == null:
		return
	var files: Array = []
	for f in d.get_files():
		if f.begins_with("play_") and f.ends_with(".md"):
			files.append(f)
	files.sort()   # timestamped names sort chronologically; oldest first
	while files.size() > KEEP_PLAYS - 1:
		DirAccess.remove_absolute(_dir.path_join(String(files.pop_front())))

func _exit_tree() -> void:
	_write_details()   # fallback: a clean quit without an ending still gets the detail section
	if _file != null:
		_file.flush()
		_file = null
