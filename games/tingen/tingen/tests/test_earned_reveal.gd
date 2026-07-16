extends SceneTree
## B2 retro-audit, finding 2 (M23 dead design channel): Agent.reveal_secret() had NO caller
## outside tests, so revealed_secrets was permanently empty and ConverseRedaction scrubbed even
## player-earned in-fiction confessions — while Perception.gd documents that "a player-prompted
## reveal/defection is player-earned, so the cult_secrecy veto must not block it". Run directly:
##   godot --headless --path tingen -s tests/test_earned_reveal.gd
## or as part of the master suite (run_tests.gd calls run_all_on(), sharing pass/fail totals).
##
## Watched RED before the wire existed: a scripted converse reply that carries the governed
## `reveal_secret` action + speaks the confession was still scrubbed to the neutral deflection
## (the action was schema-unknown and dropped; nothing ever marked the secret revealed).
##
## The wire under test rides the REAL converse seam end to end (send_utterance -> worker ->
## _on_converse_reply -> ActionSchema/Critic gate -> _apply_converse_action): a gate-approved
## `reveal_secret` action resolves its named secret against the agent's OWN unrevealed secrets
## (the redaction's own matcher — engine-neutral, no NPC-identity branch) and marks it revealed,
## so ConverseRedaction stops scrubbing THAT secret for THAT agent. Everything unearned stays
## default-deny: prose alone never reveals, and a mismatched action reveals nothing.

# --- Standalone entry -----------------------------------------------------------------------------
func _init() -> void:
	await process_frame
	await process_frame
	# N1 (sprint safety): sandbox EVERY persistent path (meta/save/settings/hints/playlog) into
	# user://test_sandbox/<run>/ and arm the write guard — see src/TestSandbox.gd.
	preload("res://src/TestSandbox.gd").activate(root)
	var r: Dictionary = run_all_on(root)
	print("\n=== earned reveal: %d passed, %d failed ===" % [int(r["passed"]), int(r["failed"])])
	quit(1 if int(r["failed"]) > 0 else 0)

# --- Shared-suite entry (run_tests.gd) ------------------------------------------------------------
static func run_all() -> Dictionary:
	var st := Engine.get_main_loop() as SceneTree
	return _run(st.root)

static func run_all_on(root_node: Node) -> Dictionary:
	return _run(root_node)

static func _run(root: Node) -> Dictionary:
	var c: Dictionary = {"passed": 0, "failed": 0}
	_unearned_secret_still_redacted(c, root)
	_earned_reveal_action_unlocks_the_secret(c, root)
	_revealed_secret_stays_discussable_next_turn(c, root)
	_mismatched_reveal_action_reveals_nothing(c, root)
	_paraphrased_confession_matches_the_stored_secret(c, root)
	return c

static func _check(c: Dictionary, cond: bool, label: String) -> void:
	if cond:
		c["passed"] = int(c["passed"]) + 1
		print("  PASS  %s" % label)
	else:
		c["failed"] = int(c["failed"]) + 1
		printerr("  FAIL  %s" % label)

# --- harness (test_converse_redaction conventions) -------------------------------------------------
const SECRET := "the Obsidian Ledger names the Vault"

static func _stage_agent(root: Node) -> Object:
	var AG: Object = root.get_node("/root/Agents")
	AG.rebuild()
	var agent: Object = AG.get_agent("lamplighter_orin")
	agent.secrets = [SECRET]
	agent.revealed_secrets = []
	agent.knowledge = []          # nothing protected — the crafted secret is purely hidden
	return agent

## One full converse turn through the REAL return path; returns what reached the panel.
static func _turn(root: Node, agent_id: String, scripted: Dictionary) -> Dictionary:
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
	DM.flush_converse()
	DM.node_changed.disconnect(cb)
	DM._end()
	SB.set_client(MockSidecar.new())
	return got

static func _confession(action: Variant) -> Dictionary:
	return {
		"say": "Yes — the Obsidian Ledger names the Vault. I've carried that too long.",
		"action": action,
		"replies": [],
	}

# --- (1) default-deny control: prose alone NEVER reveals — the unearned leak is still scrubbed -----
static func _unearned_secret_still_redacted(c: Dictionary, root: Node) -> void:
	print("[default-deny stands: a confession with NO governed reveal action is still scrubbed]")
	var agent: Object = _stage_agent(root)
	var got: Dictionary = _turn(root, "lamplighter_orin", _confession(null))
	var say := String(got["say"]).to_lower()
	_check(c, bool(got["fired"]), "the reply reaches the panel (node_changed fires)")
	_check(c, say.find("obsidian") == -1 and say.find("ledger") == -1,
		"an UN-earned secret in the say is still scrubbed (prose alone never reveals)")
	_check(c, (agent.revealed_secrets as Array).is_empty(),
		"…and nothing was marked revealed")

# --- (2) the earned reveal: the governed action marks the secret revealed, same-breath say passes --
static func _earned_reveal_action_unlocks_the_secret(c: Dictionary, root: Node) -> void:
	print("[a gate-approved converse reveal_secret action marks the secret revealed — the confession passes]")
	var agent: Object = _stage_agent(root)
	var got: Dictionary = _turn(root, "lamplighter_orin",
		_confession({"verb": "reveal_secret", "args": {"secret": SECRET}}))
	_check(c, (agent.revealed_secrets as Array).has(SECRET),
		"the converse action layer calls Agent.reveal_secret (the M23 channel is live)")
	_check(c, String(got["say"]).find("Obsidian") != -1,
		"the SAME turn's confession say passes redaction (the reveal lands before the scrub)")

# --- (3) once earned, the secret stays discussable on later turns ----------------------------------
static func _revealed_secret_stays_discussable_next_turn(c: Dictionary, root: Node) -> void:
	print("[an earned secret stays discussable on the NEXT turn (no reveal action needed again)]")
	var agent: Object = _stage_agent(root)
	_turn(root, "lamplighter_orin",
		_confession({"verb": "reveal_secret", "args": {"secret": SECRET}}))
	_check(c, (agent.revealed_secrets as Array).has(SECRET), "the reveal persisted on the agent")
	var got: Dictionary = _turn(root, "lamplighter_orin", {
		"say": "As I said: the Obsidian Ledger names the Vault. What will you do with it?",
		"action": null, "replies": [{"id": "a", "text": "Show me the Obsidian Ledger."}],
	})
	_check(c, String(got["say"]).find("Obsidian") != -1,
		"a later turn discussing the earned secret is NOT scrubbed")
	_check(c, (got["replies"] as Array).size() == 1,
		"…and the reply chip discussing it survives")

# --- (4) default-deny of the action channel: a mismatched reveal unlocks NOTHING -------------------
static func _mismatched_reveal_action_reveals_nothing(c: Dictionary, root: Node) -> void:
	print("[a reveal_secret action that matches NO owned secret reveals nothing (default-deny)]")
	var agent: Object = _stage_agent(root)
	var got: Dictionary = _turn(root, "lamplighter_orin",
		_confession({"verb": "reveal_secret", "args": {"secret": "the moon is made of tallow"}}))
	_check(c, (agent.revealed_secrets as Array).is_empty(),
		"a reveal action naming an un-owned secret marks nothing revealed")
	var say := String(got["say"]).to_lower()
	_check(c, say.find("obsidian") == -1 and say.find("ledger") == -1,
		"…and the real secret in the say is STILL scrubbed")

# --- (5) matcher symmetry: a paraphrase that the scrubber would catch maps to the stored secret ----
static func _paraphrased_confession_matches_the_stored_secret(c: Dictionary, root: Node) -> void:
	print("[a paraphrased reveal (same distinctive tokens) resolves to the stored secret string]")
	var agent: Object = _stage_agent(root)
	_turn(root, "lamplighter_orin",
		_confession({"verb": "reveal_secret",
			"args": {"secret": "that Obsidian Ledger I keep — it names the Vault"}}))
	_check(c, (agent.revealed_secrets as Array).has(SECRET),
		"the reveal resolves a paraphrase to the EXACT stored secret (the redaction's own matcher)")
