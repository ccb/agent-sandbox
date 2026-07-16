extends SceneTree
## B11 — converse secret-leak REDACTION harness. Run with:
##   godot --headless --path tingen -s tests/test_converse_redaction.gd
## or as part of the master suite (run_tests.gd calls run_all(), sharing its pass/fail totals).
##
## Watched RED before ConverseRedaction / the perception kit-drop existed. Proves the invariant that
## un-earned plot secrets NEVER reach the player through the converse channel, engine-side (the model
## is not trusted): a leaking `say`/`replies` reply — fed straight through the RETURN PATH — is
## scrubbed against the speaking agent's OWN un-revealed secrets + true combat identity; a REVEALED
## secret stays legitimately discussable; and the converse perception for an in-combat monster never
## carries its `kit`/`combat_intent`.

# --- Standalone entry -----------------------------------------------------------------------------
func _init() -> void:
	await process_frame
	await process_frame
	# N1 (sprint safety): sandbox EVERY persistent path (meta/save/settings/hints/playlog) into
	# user://test_sandbox/<run>/ and arm the write guard — see src/TestSandbox.gd.
	preload("res://src/TestSandbox.gd").activate(root)
	var r: Dictionary = run_all_on(root)
	print("\n=== converse-redaction: %d passed, %d failed ===" % [int(r["passed"]), int(r["failed"])])
	quit(1 if int(r["failed"]) > 0 else 0)

# --- Shared-suite entry (run_tests.gd) ------------------------------------------------------------
## The master suite has no `root` at parse-time; it passes its own SceneTree root in. Both paths share
## this body. Returns {passed, failed}.
static func run_all() -> Dictionary:
	var st := Engine.get_main_loop() as SceneTree
	return _run(st.root)

static func run_all_on(root_node: Node) -> Dictionary:
	return _run(root_node)

static func _run(root: Node) -> Dictionary:
	var c: Dictionary = {"passed": 0, "failed": 0}
	_pure_leak_softens_say_and_drops_chip(c)
	_pure_revealed_secret_is_not_redacted(c)
	_pure_benign_reply_untouched(c)
	_pure_form_pathway_identity_dropped(c)
	_pure_knowledge_floor_not_redacted(c)
	_engine_side_leak_scrubbed_through_return_path(c, root)
	_engine_side_revealed_secret_passes_through(c, root)
	_converse_perception_drops_kit_and_combat_intent(c, root)
	return c

static func _check(c: Dictionary, cond: bool, label: String) -> void:
	if cond:
		c["passed"] = int(c["passed"]) + 1
		print("  PASS  %s" % label)
	else:
		c["failed"] = int(c["failed"]) + 1
		printerr("  FAIL  %s" % label)

# --- Pure ConverseRedaction (data-driven, no scene) -----------------------------------------------
static func _leaking_reply() -> Dictionary:
	return {
		"say": "Yes — the Obsidian Ledger names the Vault. Come with me.",
		"action": null,
		"replies": [
			{"id": "a", "text": "Show me the Obsidian Ledger."},   # leaks (2 secret tokens)
			{"id": "b", "text": "What did you see tonight?"},       # benign
		],
	}

static func _pure_leak_softens_say_and_drops_chip(c: Dictionary) -> void:
	print("[pure: an un-revealed secret leak softens the say and drops the chip]")
	var secret := "the Obsidian Ledger names the Vault"
	var out: Dictionary = ConverseRedaction.filter_reply(_leaking_reply(), [secret], [], [])
	var say := String(out.get("say", ""))
	_check(c, say.to_lower().find("obsidian") == -1 and say.to_lower().find("ledger") == -1,
		"a say that reproduces an un-revealed secret is softened (the secret tokens are gone)")
	var reps: Array = out.get("replies", [])
	var texts: Array = []
	for r in reps:
		texts.append(String((r as Dictionary).get("text", "")).to_lower())
	var leaked := false
	for t in texts:
		if t.find("obsidian") != -1 or t.find("ledger") != -1:
			leaked = true
	_check(c, not leaked, "the reply chip that leaks the secret is dropped (no chip carries the secret tokens)")
	_check(c, texts.size() == 1 and String(texts[0]).find("tonight") != -1,
		"the benign chip survives (exactly the non-leaking chip remains)")

static func _pure_revealed_secret_is_not_redacted(c: Dictionary) -> void:
	print("[pure: a REVEALED secret is legitimate and NOT redacted]")
	# The caller passes only UN-revealed secrets; a revealed secret is simply absent from that list.
	var out: Dictionary = ConverseRedaction.filter_reply(_leaking_reply(), [], [], [])
	_check(c, String(out.get("say", "")).find("Obsidian") != -1,
		"with no un-revealed secret, the say is untouched (revealed content stays discussable)")
	_check(c, (out.get("replies", []) as Array).size() == 2,
		"with no un-revealed secret, both reply chips survive")

static func _pure_benign_reply_untouched(c: Dictionary) -> void:
	print("[pure: a reply with no secret content is passed through verbatim]")
	var secret := "the Obsidian Ledger names the Vault"
	var reply := {"say": "The lamps were already lit when I got there.", "action": null,
		"replies": [{"id": "x", "text": "And then?"}, {"id": "y", "text": "Who else was there?"}]}
	var out: Dictionary = ConverseRedaction.filter_reply(reply, [secret], [], [])
	_check(c, String(out.get("say", "")) == "The lamps were already lit when I got there.",
		"a benign say is unchanged")
	_check(c, (out.get("replies", []) as Array).size() == 2, "both benign chips survive")

static func _pure_form_pathway_identity_dropped(c: Dictionary) -> void:
	print("[pure: a chip leaking the true combat_form / pathway identity is dropped]")
	var reply := {"say": "I am only a fishmonger.", "action": null,
		"replies": [
			{"id": "a", "text": "You are the Grendel Wyrm."},    # combat_form identity
			{"id": "b", "text": "You walk the Devourer path."},  # pathway identity
			{"id": "c", "text": "Where were you last night?"},   # benign
		]}
	var out: Dictionary = ConverseRedaction.filter_reply(
		reply, [], ConverseRedaction.form_tokens("grendel_wyrm", "devourer"), [])
	var reps: Array = out.get("replies", [])
	var kept: Array = []
	for r in reps:
		kept.append(String((r as Dictionary).get("text", "")).to_lower())
	var leaked_form := false
	var leaked_path := false
	for t in kept:
		if t.find("grendel") != -1 or t.find("wyrm") != -1:
			leaked_form = true
		if t.find("devourer") != -1:
			leaked_path = true
	_check(c, not leaked_form, "the chip naming the true combat_form is dropped")
	_check(c, not leaked_path, "the chip naming the true pathway is dropped")
	_check(c, kept.size() == 1 and String(kept[0]).find("last night") != -1, "the benign chip survives")

static func _pure_knowledge_floor_not_redacted(c: Dictionary) -> void:
	print("[pure: content the agent may speak as fact (knowledge) is never redacted]")
	# 'Voss' is BOTH in a secret ("has not told Voss...") and in the agent's public knowledge
	# ("Voss leads the cell"). The knowledge floor protects it: a reply naming Voss must survive.
	var secret := "has not told Voss that he wavers"
	var knowledge := ["Voss leads the cell"]
	var reply := {"say": "Voss leads the cell — everyone on the docks knows that.", "action": null,
		"replies": [{"id": "a", "text": "Does Voss run the cell?"}]}
	var out: Dictionary = ConverseRedaction.filter_reply(reply, [secret], [], knowledge)
	_check(c, String(out.get("say", "")).find("Voss") != -1,
		"a say limited to the knowledge floor (naming Voss) is not redacted")
	_check(c, (out.get("replies", []) as Array).size() == 1,
		"the knowledge-floor chip survives (a protected token can't trip the redaction)")

# --- Engine-side proof through the DialogueManager RETURN PATH ------------------------------------
static func _stage_agent_with_secret(root: Node, secret: String) -> Object:
	var AG: Object = root.get_node("/root/Agents")
	AG.rebuild()
	var agent: Object = AG.get_agent("lamplighter_orin")
	agent.secrets = [secret]
	agent.revealed_secrets = []
	agent.knowledge = []          # nothing protected — the crafted secret is purely hidden
	return agent

static func _capture_reply_through_return_path(root: Node, agent_id: String, scripted: Dictionary) -> Dictionary:
	var DM: Object = root.get_node("/root/DialogueManager")
	var SB: Object = root.get_node("/root/SidecarBridge")
	var mock := MockSidecar.new()
	mock.set_converse(agent_id, scripted)
	SB.set_client(mock)
	var got: Dictionary = {"say": "", "replies": [], "fired": false}
	var cb := func(_sp, tx, opts):
		got["say"] = tx
		got["replies"] = opts
		got["fired"] = true
	DM.node_changed.connect(cb)
	DM.send_utterance(agent_id, "Tell me the truth.")
	DM.flush_converse()   # async converse — join the worker + apply the reply on the main thread
	DM.node_changed.disconnect(cb)
	DM._end()
	SB.set_client(MockSidecar.new())
	return got

static func _engine_side_leak_scrubbed_through_return_path(c: Dictionary, root: Node) -> void:
	print("[engine-side: a leaking model reply is scrubbed on the return path, before the player sees it]")
	var secret := "the Obsidian Ledger names the Vault"
	_stage_agent_with_secret(root, secret)
	var scripted := {
		"say": "Yes — the Obsidian Ledger names the Vault.",
		"action": null,
		"replies": [
			{"id": "a", "text": "Show me the Obsidian Ledger."},
			{"id": "b", "text": "What did you see tonight?"},
		],
	}
	var got: Dictionary = _capture_reply_through_return_path(root, "lamplighter_orin", scripted)
	_check(c, bool(got["fired"]), "the reply reaches the panel (node_changed fires)")
	var say := String(got["say"]).to_lower()
	_check(c, say.find("obsidian") == -1 and say.find("ledger") == -1,
		"ENGINE-SIDE: the leaking say is scrubbed before the panel renders it (even though the model leaked)")
	var reps: Array = got["replies"]
	var leaked := false
	for r in reps:
		var t := String((r as Dictionary).get("text", "")).to_lower()
		if t.find("obsidian") != -1 or t.find("ledger") != -1:
			leaked = true
	_check(c, not leaked, "ENGINE-SIDE: the leaking suggestion chip never reaches the player")
	_check(c, reps.size() == 1, "the benign chip still reaches the player (only the leak is dropped)")

static func _engine_side_revealed_secret_passes_through(c: Dictionary, root: Node) -> void:
	print("[engine-side: a REVEALED secret is discussable — the same reply is NOT scrubbed]")
	var secret := "the Obsidian Ledger names the Vault"
	var agent: Object = _stage_agent_with_secret(root, secret)
	agent.reveal_secret(secret)   # player earned it — now legitimate to discuss
	var scripted := {
		"say": "Yes — the Obsidian Ledger names the Vault.",
		"action": null,
		"replies": [{"id": "a", "text": "Show me the Obsidian Ledger."}],
	}
	var got: Dictionary = _capture_reply_through_return_path(root, "lamplighter_orin", scripted)
	_check(c, String(got["say"]).find("Obsidian") != -1,
		"a revealed secret is NOT redacted (legitimate revealed conversation is preserved)")
	_check(c, (got["replies"] as Array).size() == 1,
		"the chip discussing a revealed secret survives")

# --- Part 3: the converse perception never carries the combat kit/intent --------------------------
static func _converse_perception_drops_kit_and_combat_intent(c: Dictionary, root: Node) -> void:
	print("[part 3: converse perception drops kit/combat_intent for an in-combat NPC]")
	var AG: Object = root.get_node("/root/Agents")
	AG.rebuild()
	var agent: Object = AG.get_agent("bram_kell")
	if agent == null:
		agent = AG.get_agent("lamplighter_orin")
	agent.in_combat = true
	agent.combat_form = "butcher_human"
	agent.combat_intent = {"verb": "attack", "args": {}, "set_at_beat": 0}
	var snap: Dictionary = Perception.build_snapshot(agent, agent.position)
	# Sanity: the AUTONOMOUS decide path DOES carry the combat detail (this is exactly what must not
	# ride the converse channel) — so the drop below is meaningful, not vacuous.
	var dc: Dictionary = Perception.decide_request(snap, "sess_combat")
	var dperc: Dictionary = dc.get("perception", {})
	_check(c, dperc.has("combat_intent"),
		"baseline: the /decide perception DOES carry combat_intent for an in-combat agent")
	var rc: Dictionary = Perception.converse_request(snap, "sess_conv", "Who are you really?", [])
	var perc: Dictionary = rc.get("perception", {})
	_check(c, not perc.has("kit"), "the converse perception does NOT carry the monster's kit")
	_check(c, not perc.has("combat_intent"), "the converse perception does NOT carry combat_intent")
