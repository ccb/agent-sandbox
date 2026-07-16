extends SceneTree
## M_cast (user request) — THE CAST: the title-screen NPC dossier roulette panel.
##
## v2 (user correction): "the point of the roulette is for me to see the character information,
## ALL of it. for now, write everything on there, including their goals, personality, their
## powers, abilities, etc." — the panel is (for now) a FULL DESIGN-REFERENCE DOSSIER:
##   * SHOW_ALL defaults TRUE: every Beyonder card ships REVEALED (pathway/sequence, the form
##     family, the beneath-the-mask monster flip, BOTH forms' full kits with REAL numbers) with
##     no codex gating. The codex-gate machinery is KEPT behind the one flag (build_cards'
##     show_all arg; CastCodex.SHOW_ALL is the shipped default) so a player-facing gated mode
##     can return later.
##   * every AUTHORED npcs.json field rides the card: persona (description + voice, untruncated),
##     GOALS (intent + the goals list), SECRETS (the actual strings), KNOWLEDGE, the full phase
##     SCHEDULE as readable district lines, and a generic RECORDS catch-all (tier / vision_r /
##     max_hp / task / carried_items / tint / dialogue_id — any non-underscore field a section
##     did not consume, so a NEW authored field can never silently vanish). Underscore-prefixed
##     keys (_pathway_note …) are authoring comments (JSON's comment convention), not character
##     data — excluded by convention, never by id.
##
## This harness pins the HEADLESS layer (rendered pixels are proven by tests/screenshot_probe.gd):
##   (a) the PURE view-model builder (src/CastCodex.gd) builds a card for EVERY roster NPC in
##       deterministic deck order, purely from data args (npcs/forms/abilities/districts/codex);
##   (b) every card's dossier face is always present: name, role, haunts, persona description,
##       voice, goals, secrets key, knowledge, readable schedule lines, records, and a portrait
##       path that resolves to a real file;
##   (c) the SHOW_ALL default: an EMPTY codex still reveals EVERY Beyonder (the design-reference
##       default) — and the gate flag still WORKS when false (the old redaction behavior, kept);
##   (d) the codex->NPC mapping machinery (gated mode, show_all=false) still walks the DATA:
##       `adversary:<form>` ids map through npcs.json combat_form + the transform-effect chain;
##       either phase's record reveals; pathway-only entries reveal nobody;
##   (i) FULL-DOSSIER content, pinned on known roster cards: maribel_hatch (mundane civilian
##       dossier: goals/knowledge/voice/schedule), old_neil + sister_auber (Beyonder dossier:
##       the actual secret strings, goals, and BOTH forms' kits with abilities.json numbers —
##       damage/cooldown/cost/range);
##   (e) mundane NPCs (no combat_form/pathway) are never redacted OR revealed — the "No touch of
##       the Beyond" line — while still carrying the full civilian dossier;
##   (f) the mapping is ENGINE-NEUTRAL: a fully synthetic roster (fake npc/forms/abilities) walks
##       the same chain and carries the same numbers — no real-roster or NPC-id dependence;
##   (g) the PANEL (src/CastPanel.gd) drives headless: open/close, wrap-around next/prev,
##       deterministic spin_to, spin() landing inside the deck (UI-layer RNG only), the
##       beneath-the-mask flip (now offered on EVERY monster-art Beyonder — SHOW_ALL), and the
##       card's DossierScroll (the overflow scroll seam, reset per card);
##   (h) LIVE REACHABILITY: the mounted TITLE screen (BootController) wires a "The Cast" button
##       that opens the panel, and the panel READS the real RunManager.meta_codex() ledger —
##       proven by the staged learned line QUOTED on the card (state alone no longer proves the
##       read: SHOW_ALL reveals everything).
##
## Standalone: godot --headless --path tingen -s tests/test_cast_roulette.gd
## Also folded into the main suite (run_tests.gd `_test_cast_roulette`) via the SAME run_all().

func _init() -> void:
	await process_frame
	await process_frame
	# N1 (sprint safety): sandbox EVERY persistent path (meta/save/settings/hints/playlog) into
	# user://test_sandbox/<run>/ and arm the write guard — see src/TestSandbox.gd.
	preload("res://src/TestSandbox.gd").activate(root)
	var r: Dictionary = await run_all()
	print("\n=== test_cast_roulette: %d passed, %d failed ===" % [int(r["passed"]), int(r["failed"])])
	quit(1 if int(r["failed"]) > 0 else 0)

## The one entry point (returns {passed, failed}); folded into run_tests.gd.
static func run_all() -> Dictionary:
	var c := {"passed": 0, "failed": 0}
	var root: Node = (Engine.get_main_loop() as SceneTree).root
	_a_builder_all_roster(c, root)
	_b_public_fields_always(c, root)
	_c_show_all_default_and_gate_flag(c, root)
	_d_gated_mapping_machinery(c, root)
	_i_full_dossier_content(c, root)
	_e_mundane_handling(c, root)
	_f_synthetic_data_engine_neutral(c, root)
	await _g_panel_headless(c, root)
	await _h_title_reachability(c, root)
	return c

static func _check(c: Dictionary, cond: bool, label: String) -> void:
	if cond:
		c["passed"] = int(c["passed"]) + 1
		print("  PASS  %s" % label)
	else:
		c["failed"] = int(c["failed"]) + 1
		printerr("  FAIL  %s" % label)

static func _n(root: Node, autoload_name: String) -> Node:
	return root.get_node_or_null("/root/" + autoload_name)

## The builder script (null before implementation — every section then fails RED, not crashes).
static func _cc() -> GDScript:
	return load("res://src/CastCodex.gd") as GDScript

## Gather the REAL data exactly as the panel does: NpcDB defs, AbilityDB forms + abilities,
## the districts array. Defensive so a pre-implementation run degrades to FAILs, never a crash.
static func _data(root: Node) -> Dictionary:
	var npcs: Dictionary = {}
	var db := _n(root, "NpcDB")
	if db != null:
		npcs = db.defs
	var forms: Dictionary = {}
	var abilities: Dictionary = {}
	var adb := _n(root, "AbilityDB")
	if adb != null and adb.has_method("all_form_ids"):
		for f in adb.all_form_ids():
			forms[String(f)] = adb.form_def(String(f))
	if adb != null:
		for aid in adb.all_ability_ids():
			abilities[String(aid)] = adb.ability_for(String(aid))
	var districts: Variant = JSON.parse_string(FileAccess.get_file_as_string("res://data/districts.json"))
	return {"npcs": npcs, "forms": forms, "abilities": abilities,
		"districts": districts if districts is Array else []}

## Build cards. show_all == null exercises the SHIPPED DEFAULT (the 5-arg call — SHOW_ALL);
## a bool exercises the gate flag explicitly. Pre-implementation guard: an old builder without
## the SHOW_ALL const cannot take the 6th arg — return [] so asserts FAIL red, never crash.
static func _cards(root: Node, codex: Array, show_all: Variant = null) -> Array:
	var CC := _cc()
	if CC == null:
		return []
	var d := _data(root)
	if show_all == null:
		return CC.build_cards(d["npcs"], d["forms"], d["abilities"], d["districts"], codex)
	if not (CC.get_script_constant_map() as Dictionary).has("SHOW_ALL"):
		return []
	return CC.build_cards(d["npcs"], d["forms"], d["abilities"], d["districts"], codex, bool(show_all))

static func _card_by_id(cards: Array, id: String) -> Dictionary:
	for card in cards:
		if card is Dictionary and String((card as Dictionary).get("id", "")) == id:
			return card
	return {}

static func _joined(card: Dictionary, key: String) -> String:
	var v: Variant = card.get(key, [])
	if not v is Array:
		return ""
	var parts := PackedStringArray()
	for e in (v as Array):
		parts.append(String(e))
	return "\n".join(parts)

# (a) --------------------------------------------------------------------------------------------
static func _a_builder_all_roster(c: Dictionary, root: Node) -> void:
	print("[cast (a): the pure builder deals a card for EVERY roster NPC, deck order deterministic]")
	_check(c, _cc() != null, "src/CastCodex.gd exists (the pure view-model builder)")
	var d := _data(root)
	var npcs: Dictionary = d["npcs"]
	_check(c, npcs.size() >= 21, "the roster data is loaded (%d NPCs)" % npcs.size())
	var cards := _cards(root, [])
	_check(c, cards.size() == npcs.size(),
		"one card per roster NPC (%d cards for %d NPCs) — the panel grows with the data" % [cards.size(), npcs.size()])
	var ids_in_order := true
	var keys: Array = npcs.keys()
	for i in mini(cards.size(), keys.size()):
		if String((cards[i] as Dictionary).get("id", "")) != String(keys[i]):
			ids_in_order = false
	_check(c, cards.size() == keys.size() and ids_in_order,
		"deck order is the roster's authored order (deterministic — the dot strip is stable)")
	# Purity: two builds from the same inputs are identical (no hidden state, no RNG).
	var again := _cards(root, [])
	_check(c, str(cards) == str(again), "the builder is PURE (same inputs -> identical cards)")

# (b) --------------------------------------------------------------------------------------------
static func _b_public_fields_always(c: Dictionary, root: Node) -> void:
	print("[cast (b): every card's dossier face — name/role/haunts/persona/voice/goals/knowledge/schedule/records/portrait]")
	var cards := _cards(root, [])
	if cards.is_empty():
		_check(c, false, "cards built (builder missing)")
		return
	var bad_name := 0
	var bad_role := 0
	var bad_desc := 0
	var bad_haunt := 0
	var bad_art := 0
	var bad_voice := 0
	var bad_goals := 0
	var bad_secrets_key := 0
	var bad_knowledge := 0
	var bad_sched := 0
	var bad_records := 0
	for card in cards:
		var cd: Dictionary = card
		if String(cd.get("name", "")) == "":
			bad_name += 1
		if String(cd.get("role", "")) == "":
			bad_role += 1
		if String(cd.get("description", "")) == "":
			bad_desc += 1
		if String(cd.get("haunts", "")) == "":
			bad_haunt += 1
		var art := String(cd.get("portrait", ""))
		if art == "" or not ResourceLoader.exists(art):
			bad_art += 1
		# v2 (user correction): the WHOLE authored dossier rides every card.
		if String(cd.get("voice", "")) == "":
			bad_voice += 1
		if not (cd.get("goals") is Array) or (cd.get("goals") as Array).is_empty():
			bad_goals += 1   # every roster NPC authors an `intent` — it folds into GOALS
		if not (cd.get("secrets") is Array):
			bad_secrets_key += 1   # the KEY is always present (mundane folk author [])
		if not (cd.get("knowledge") is Array) or (cd.get("knowledge") as Array).is_empty():
			bad_knowledge += 1
		if not (cd.get("schedule_lines") is Array) or (cd.get("schedule_lines") as Array).is_empty():
			bad_sched += 1
		if not (cd.get("records") is Array) or (cd.get("records") as Array).is_empty():
			bad_records += 1   # every roster NPC authors at least `tier` — the catch-all carries it
	_check(c, bad_name == 0, "every card carries a display NAME (%d missing)" % bad_name)
	_check(c, bad_role == 0, "every card carries a ROLE line (%d missing)" % bad_role)
	_check(c, bad_desc == 0, "every card carries the authored persona DESCRIPTION (%d missing)" % bad_desc)
	_check(c, bad_haunt == 0, "every card carries a HAUNTS line (districts from schedule, %d missing)" % bad_haunt)
	_check(c, bad_art == 0, "every card's PORTRAIT path resolves to a real file (%d broken)" % bad_art)
	_check(c, bad_voice == 0, "every card carries the authored VOICE line (%d missing)" % bad_voice)
	_check(c, bad_goals == 0, "every card carries GOALS lines (intent + goals fields, %d missing)" % bad_goals)
	_check(c, bad_secrets_key == 0, "every card carries a SECRETS array (%d missing the key)" % bad_secrets_key)
	_check(c, bad_knowledge == 0, "every card carries its KNOWLEDGE lines (%d missing)" % bad_knowledge)
	_check(c, bad_sched == 0, "every card carries readable SCHEDULE lines (%d missing)" % bad_sched)
	_check(c, bad_records == 0, "every card carries the RECORDS catch-all (tier/vision/… %d empty)" % bad_records)

# (c) --------------------------------------------------------------------------------------------
## v2 INVERSION (user correction, replacing the old empty-meta-redacts-everything default): the
## shipped panel is a design-reference dossier — an EMPTY codex reveals EVERY Beyonder. The old
## redaction asserts are NOT deleted: they now pin the GATED mode behind show_all=false, so the
## machinery a player-facing mode needs later is proven alive.
static func _c_show_all_default_and_gate_flag(c: Dictionary, root: Node) -> void:
	print("[cast (c): SHOW_ALL default — a fresh install reveals EVERYTHING; the gate flag still works off]")
	var CC := _cc()
	if CC == null:
		_check(c, false, "builder missing")
		return
	_check(c, (CC.get_script_constant_map() as Dictionary).has("SHOW_ALL")
			and bool(CC.SHOW_ALL) == true,
		"CastCodex.SHOW_ALL exists and ships TRUE (the one gate flag — user: 'write everything on there')")
	# DEFAULT build (no flag arg) on an EMPTY codex: every Beyonder stands revealed.
	var cards := _cards(root, [])
	if cards.is_empty():
		_check(c, false, "cards built (builder missing)")
		return
	var beyonders := 0
	var revealed := 0
	var secret_full := 0
	var any_learned := false
	for card in cards:
		var cd: Dictionary = card
		if bool(cd.get("learned", false)):
			any_learned = true
		if bool(cd.get("is_beyonder", false)):
			beyonders += 1
			if String(cd.get("state", "")) == "revealed":
				revealed += 1
			if not (cd.get("secret", {}) as Dictionary).is_empty():
				secret_full += 1
	_check(c, beyonders >= 7, "the roster hides Beyonders among the people (%d)" % beyonders)
	_check(c, revealed == beyonders,
		"SHOW_ALL default: EVERY Beyonder card is revealed on an empty codex (%d/%d)" % [revealed, beyonders])
	_check(c, secret_full == beyonders,
		"SHOW_ALL default: every Beyonder card carries the full secret layer (%d/%d)" % [secret_full, beyonders])
	_check(c, not any_learned,
		"the `learned` flag stays TRUTHFUL under SHOW_ALL (empty codex has learned nobody)")
	# The GATE still works when false: the old redaction default, preserved behind the flag.
	var gated := _cards(root, [], false)
	if gated.is_empty():
		_check(c, false, "gated build (show_all=false) produced cards")
		return
	var g_revealed := 0
	var g_leak := 0
	var g_beyonders := 0
	var g_redacted_ok := 0
	for card in gated:
		var cd: Dictionary = card
		if String(cd.get("state", "")) == "revealed":
			g_revealed += 1
		if not (cd.get("secret", {}) as Dictionary).is_empty():
			g_leak += 1
		if bool(cd.get("is_beyonder", false)):
			g_beyonders += 1
			if String(cd.get("state", "")) == "redacted" \
					and String(cd.get("secret_line", "")) == String(CC.REDACTED_LINE):
				g_redacted_ok += 1
	_check(c, g_revealed == 0, "gated (show_all=false) + empty codex: no card is revealed")
	_check(c, g_leak == 0, "gated: the secret dict NEVER leaks on an empty codex (%d leaked)" % g_leak)
	_check(c, g_redacted_ok == g_beyonders,
		"gated: every Beyonder card carries the dossier redaction line (%d/%d)" % [g_redacted_ok, g_beyonders])

# (d) --------------------------------------------------------------------------------------------
## The codex->NPC mapping MACHINERY, pinned in the GATED mode (show_all=false — under the shipped
## SHOW_ALL default everything is revealed, so only the gated build can prove the mapping).
static func _d_gated_mapping_machinery(c: Dictionary, root: Node) -> void:
	print("[cast (d): the gated codex mapping machinery still walks the data (show_all=false)]")
	var cards := _cards(root, [], false)
	if cards.is_empty():
		_check(c, false, "cards built (builder missing)")
		return
	# The MONSTER-phase record (downed after the descend) maps BACK through the transform chain.
	var neil_line := "The Sage's pollution wore what was left of the alchemist."
	var staged: Array = [{"id": "adversary:neil_monster", "learned": neil_line}]
	var revealed := _cards(root, staged, false)
	var neil := _card_by_id(revealed, "old_neil")
	_check(c, bool(neil.get("learned", false)) and String(neil.get("state", "")) == "revealed",
		"adversary:neil_monster (the MONSTER phase) reveals old_neil — form->npc via the transform chain")
	var secret: Dictionary = neil.get("secret", {}) if neil.get("secret") is Dictionary else {}
	_check(c, String(secret.get("pathway", "")) == "hermit", "the reveal names his PATHWAY (hermit)")
	_check(c, String(secret.get("monster_form", "")) == "neil_monster",
		"the reveal names the MONSTER form (neil_monster)")
	var art := String(secret.get("monster_art", ""))
	_check(c, art != "" and ResourceLoader.exists(art),
		"the beneath-the-mask MONSTER art path resolves to a real file (%s)" % art)
	var kit: Array = secret.get("abilities", []) if secret.get("abilities") is Array else []
	_check(c, kit.size() >= 3, "the reveal lists his ability kit (%d arts)" % kit.size())
	var kit_named := not kit.is_empty()
	var kit_ids: Array = []
	for a in kit:
		kit_ids.append(String((a as Dictionary).get("id", "")))
		if String((a as Dictionary).get("name", "")) == "" or String((a as Dictionary).get("description", "")) == "":
			kit_named = false
	_check(c, kit_named, "every kit entry carries a display NAME and a one-line DESCRIPTION (AbilityDB data)")
	_check(c, kit_ids.has("star_brand") and kit_ids.has("collapsing_star"),
		"the kit spans BOTH phases of the chain (human star_brand + monster collapsing_star)")
	var lines: Array = neil.get("codex_lines", []) if neil.get("codex_lines") is Array else []
	_check(c, lines.size() == 1 and String(lines[0]) == neil_line,
		"the card quotes THIS NPC's learned ledger line at the bottom")
	# Nobody else is revealed by Neil's record.
	var wren := _card_by_id(revealed, "sable_wren")
	var finch := _card_by_id(revealed, "ledger_finch")
	_check(c, String(wren.get("state", "")) == "redacted" and String(finch.get("state", "")) == "redacted",
		"the record reveals ONLY its own NPC (wren/finch stay redacted)")
	# The HUMAN-phase record (downed before the transform) reveals too.
	var kell := _card_by_id(_cards(root, [{"id": "adversary:butcher_human", "learned": "x"}], false), "bram_kell")
	_check(c, String(kell.get("state", "")) == "revealed",
		"adversary:butcher_human (the HUMAN phase) reveals bram_kell — either phase's record counts")
	# A pathway-only codex reveals NOBODY (knowing the pathway is not knowing the person).
	var pw_only := _cards(root, [{"id": "pathway:hermit", "learned": "x"}, {"id": "ending:descent_stopped", "learned": "y"}], false)
	var pw_revealed := 0
	for card in pw_only:
		if String((card as Dictionary).get("state", "")) == "revealed":
			pw_revealed += 1
	_check(c, pw_revealed == 0, "pathway:/ending: entries reveal NO card (adversary records only)")
	# Under the SHIPPED default, a learned line is still QUOTED on the (already revealed) card.
	var neil_default := _card_by_id(_cards(root, staged), "old_neil")
	var dlines: Array = neil_default.get("codex_lines", []) if neil_default.get("codex_lines") is Array else []
	_check(c, dlines.size() == 1 and String(dlines[0]) == neil_line and bool(neil_default.get("learned", false)),
		"SHOW_ALL default + a staged codex: the learned ledger line is still quoted (the ledger read survives)")

# (i) --------------------------------------------------------------------------------------------
## v2 (user correction) — FULL-DOSSIER CONTENT pinned on known roster cards: the exact authored
## strings and the exact abilities.json numbers must ride the card models.
static func _i_full_dossier_content(c: Dictionary, root: Node) -> void:
	print("[cast (i): FULL dossier content — goals/secrets/knowledge/schedule strings + kit numbers]")
	var cards := _cards(root, [])   # the SHIPPED default: empty codex, everything shown
	if cards.is_empty():
		_check(c, false, "cards built (builder missing)")
		return
	# --- maribel_hatch: a MUNDANE civilian's complete dossier -------------------------------------
	var mh := _card_by_id(cards, "maribel_hatch")
	_check(c, _joined(mh, "goals").contains("loan shark"),
		"maribel's GOALS carry her authored intent (the loan shark)")
	_check(c, _joined(mh, "knowledge").contains("who owes money to whom"),
		"maribel's KNOWLEDGE lists the authored lines verbatim")
	_check(c, String(mh.get("voice", "")).contains("gossip"),
		"maribel's VOICE line is the authored persona text")
	var mh_sched: Array = mh.get("schedule_lines", []) if mh.get("schedule_lines") is Array else []
	_check(c, mh_sched.size() == 5,
		"maribel's SCHEDULE renders every authored phase (5 lines, got %d)" % mh_sched.size())
	_check(c, mh_sched.size() > 0 and String(mh_sched[0]).begins_with("Morning"),
		"schedule lines read as 'Phase — place' in authored order (first: %s)" % (String(mh_sched[0]) if mh_sched.size() > 0 else "<none>"))
	_check(c, (mh.get("secrets") is Array) and (mh.get("secrets") as Array).is_empty(),
		"maribel authors NO secrets — the card carries the empty array, not an invention")
	# --- old_neil: a Beyonder's complete dossier — secrets, goals, and NUMBERS ---------------------
	var neil := _card_by_id(cards, "old_neil")
	_check(c, String(neil.get("state", "")) == "revealed",
		"old_neil ships revealed (SHOW_ALL default, empty codex)")
	_check(c, _joined(neil, "secrets").contains("is trying to resurrect Celeste"),
		"neil's SECRETS carry the actual authored secret strings")
	_check(c, _joined(neil, "goals").contains("Celeste"),
		"neil's GOALS carry his authored intent (Celeste)")
	_check(c, _joined(neil, "records").contains("vision_r") and _joined(neil, "records").contains("600"),
		"neil's RECORDS catch-all carries the authored vision_r stat (600)")
	var ns: Dictionary = neil.get("secret", {}) if neil.get("secret") is Dictionary else {}
	var fks: Array = ns.get("form_kits", []) if ns.get("form_kits") is Array else []
	_check(c, fks.size() == 2, "neil's secret carries BOTH forms' kits (form_kits, got %d)" % fks.size())
	var human_kit: Dictionary = {}
	var monster_kit: Dictionary = {}
	for fk in fks:
		if String((fk as Dictionary).get("form", "")) == "neil_human":
			human_kit = fk
		elif String((fk as Dictionary).get("form", "")) == "neil_monster":
			monster_kit = fk
	_check(c, not human_kit.is_empty() and not bool(human_kit.get("monster", true)),
		"form_kits names the HUMAN phase (neil_human, monster=false)")
	_check(c, not monster_kit.is_empty() and bool(monster_kit.get("monster", false)),
		"form_kits names the MONSTER phase (neil_monster, monster=true)")
	var sb := _kit_entry(human_kit, "star_brand")
	_check(c, not sb.is_empty(), "the human kit lists star_brand")
	_check(c, is_equal_approx(float(sb.get("damage", 0.0)), 30.0),
		"star_brand carries its REAL damage number (30, got %s)" % str(sb.get("damage")))
	_check(c, is_equal_approx(float(sb.get("cooldown", 0.0)), 1.0)
			and is_equal_approx(float(sb.get("range", 0.0)), 500.0),
		"star_brand carries cooldown 1.0 + range 500 from abilities.json")
	var sb_cost: Dictionary = sb.get("cost", {}) if sb.get("cost") is Dictionary else {}
	_check(c, int(sb_cost.get("spirituality", 0)) == 10,
		"star_brand carries its cost (10 spirituality)")
	_check(c, String(sb.get("stats", "")).contains("30") and String(sb.get("stats", "")).contains("500"),
		"star_brand renders a readable stats line with the real numbers (%s)" % String(sb.get("stats", "")))
	var cs := _kit_entry(monster_kit, "collapsing_star")
	_check(c, not cs.is_empty() and is_equal_approx(float(cs.get("damage", 0.0)), 46.0)
			and is_equal_approx(float(cs.get("cooldown", 0.0)), 3.0),
		"the monster kit lists collapsing_star with ITS numbers (dmg 46, cd 3.0)")
	# --- sister_auber: the second Beyonder spot-check ----------------------------------------------
	var auber := _card_by_id(cards, "sister_auber")
	var aus: Dictionary = auber.get("secret", {}) if auber.get("secret") is Dictionary else {}
	_check(c, String(auber.get("state", "")) == "revealed" and String(aus.get("pathway", "")) == "death",
		"sister_auber ships revealed with her pathway (death)")
	_check(c, _joined(auber, "secrets").contains("grave-power"),
		"auber's SECRETS carry the authored grave-power string")

static func _kit_entry(form_kit: Dictionary, aid: String) -> Dictionary:
	var abl: Array = form_kit.get("abilities", []) if form_kit.get("abilities") is Array else []
	for a in abl:
		if a is Dictionary and String((a as Dictionary).get("id", "")) == aid:
			return a
	return {}

# (e) --------------------------------------------------------------------------------------------
static func _e_mundane_handling(c: Dictionary, root: Node) -> void:
	print("[cast (e): mundane NPCs — no touch of the Beyond, never redacted, never revealed]")
	var CC := _cc()
	# Even under SHOW_ALL + a fully learned codex the mundane stay mundane (no Beyond layer to show).
	var staged: Array = [{"id": "adversary:neil_monster", "learned": "x"},
		{"id": "adversary:butcher_human", "learned": "y"}, {"id": "pathway:hermit", "learned": "z"}]
	var cards := _cards(root, staged)
	if CC == null or cards.is_empty():
		_check(c, false, "cards built (builder missing)")
		return
	var pip := _card_by_id(cards, "pip")
	_check(c, not bool(pip.get("is_beyonder", true)), "pip (the urchin) is MUNDANE (no combat_form/pathway data)")
	_check(c, String(pip.get("state", "")) == "mundane" \
			and String(pip.get("secret_line", "")) == String(CC.MUNDANE_LINE),
		"the mundane card carries the 'No touch of the Beyond' line — not the redaction block")
	# v2: the mundane card still carries the FULL civilian dossier.
	_check(c, (pip.get("knowledge") is Array) and not (pip.get("knowledge") as Array).is_empty() \
			and (pip.get("schedule_lines") is Array) and not (pip.get("schedule_lines") as Array).is_empty() \
			and _joined(pip, "goals").contains("Eat today"),
		"pip's civilian dossier is complete (knowledge + schedule + his authored intent)")
	var mundane_total := 0
	var mundane_ok := 0
	for card in cards:
		var cd: Dictionary = card
		if not bool(cd.get("is_beyonder", false)):
			mundane_total += 1
			if String(cd.get("state", "")) == "mundane" and not bool(cd.get("learned", true)) \
					and (cd.get("secret", {}) as Dictionary).is_empty():
				mundane_ok += 1
	_check(c, mundane_total >= 10 and mundane_ok == mundane_total,
		"EVERY mundane NPC reads mundane even under SHOW_ALL + a learned codex (%d/%d)" % [mundane_ok, mundane_total])

# (f) --------------------------------------------------------------------------------------------
static func _f_synthetic_data_engine_neutral(c: Dictionary, root: Node) -> void:
	print("[cast (f): a fully SYNTHETIC roster walks the same mapping + numbers — engine-neutral]")
	var CC := _cc()
	if CC == null:
		_check(c, false, "builder missing")
		return
	var s_npcs := {"test_ghoul": {"name": "Test Ghoul", "role": "night_porter",
		"description": "A test spectre.", "voice": "flat", "intent": "haunt the tests",
		"knowledge": ["the harness"], "secrets": ["is synthetic"],
		"combat_form": "tg_human", "pathway": "fool", "sequence": 9, "tier": "full", "schedule": {}}}
	var s_abilities := {
		"tg_claw": {"id": "tg_claw", "name": "test claw", "description": "a test claw",
			"cooldown": 1.5, "range": 60, "effects": [{"kind": "damage", "amount": 12}]},
		"tg_shift": {"id": "tg_shift", "name": "shift", "description": "become the test thing",
			"class": "transform", "effects": [{"kind": "transform", "form": "tg_monster"}]},
	}
	var s_forms := {"tg_human": {"kit": ["tg_claw", "tg_shift"], "hidden_beyonder": true},
		"tg_monster": {"kit": ["tg_claw"], "monster": true}}
	# The SHIPPED default: an EMPTY codex reveals the synthetic Beyonder outright.
	var cards: Array = CC.build_cards(s_npcs, s_forms, s_abilities, [], [])
	_check(c, cards.size() == 1, "the synthetic roster builds (1 card)")
	if cards.is_empty():
		return
	var g: Dictionary = cards[0]
	_check(c, String(g.get("state", "")) == "revealed",
		"SHOW_ALL default: the synthetic Beyonder ships revealed on an empty codex")
	var gs: Dictionary = g.get("secret", {}) if g.get("secret") is Dictionary else {}
	_check(c, String(gs.get("monster_form", "")) == "tg_monster" and String(gs.get("pathway", "")) == "fool",
		"the synthetic secret carries monster form + pathway from the DATA")
	_check(c, int(gs.get("sequence", 0)) == 9, "an authored `sequence` field surfaces in the reveal (data-driven)")
	_check(c, String(g.get("portrait", "")) == "",
		"a portrait-less synthetic id degrades to no art (never a broken path)")
	var g_fks: Array = gs.get("form_kits", []) if gs.get("form_kits") is Array else []
	var g_claw := _kit_entry(g_fks[0] if g_fks.size() > 0 else {}, "tg_claw")
	_check(c, g_fks.size() == 2 and is_equal_approx(float(g_claw.get("damage", 0.0)), 12.0)
			and is_equal_approx(float(g_claw.get("cooldown", 0.0)), 1.5),
		"synthetic form_kits carry the synthetic NUMBERS (dmg 12, cd 1.5) — the same generic walk")
	_check(c, _joined(g, "records").contains("tier: full"),
		"the RECORDS catch-all is generic (synthetic `tier` surfaces without an id branch)")
	# The GATED mapping (show_all=false): only the codex record reveals, through the chain walk.
	if not (CC.get_script_constant_map() as Dictionary).has("SHOW_ALL"):
		_check(c, false, "gated synthetic build (SHOW_ALL seam missing)")
		return
	var gated: Array = CC.build_cards(s_npcs, s_forms, s_abilities, [], [], false)
	var gated_empty: Array = CC.build_cards(s_npcs, s_forms, s_abilities, [], [{"id": "adversary:tg_monster", "learned": "seen"}], false)
	_check(c, cards.size() == 1 and String((gated[0] as Dictionary).get("state", "")) == "redacted",
		"gated + empty codex: the synthetic Beyonder is redacted (the machinery lives)")
	_check(c, String((gated_empty[0] as Dictionary).get("state", "")) == "revealed",
		"gated + the monster record: revealed through the SAME chain walk (pure data)")
	# N6 (B1): the card art must ride the ONE N4 form->art resolver, not a raw filename
	# convention — an ALIAS-ONLY monster form (no enemies/<form>.png of its own, only a DATA
	# `sprite` row) rendered ARTLESS in the Cast panel under the old raw ENEMY_ART_DIR build.
	var alias_path := "res://assets/enemies/cult_thrall.png"
	var s_forms_aliased := {"tg_human": {"kit": ["tg_claw", "tg_shift"], "hidden_beyonder": true},
		"tg_monster": {"kit": ["tg_claw"], "monster": true, "sprite": alias_path}}
	var aliased: Array = CC.build_cards(s_npcs, s_forms_aliased, s_abilities, [], [])
	var asec: Dictionary = (aliased[0] as Dictionary).get("secret", {}) \
		if (aliased[0] as Dictionary).get("secret") is Dictionary else {}
	_check(c, String(asec.get("monster_art", "")) == alias_path,
		"an alias-only monster form wears its DATA `sprite` painting on the card (N4 resolver)")

# (g) --------------------------------------------------------------------------------------------
static func _g_panel_headless(c: Dictionary, root: Node) -> void:
	print("[cast (g): the panel drives headless — open/wrap/spin_to/spin/flip/scroll, deterministic]")
	var PS := load("res://src/CastPanel.gd") as GDScript
	_check(c, PS != null, "src/CastPanel.gd exists (the panel)")
	if PS == null:
		return
	var tree := Engine.get_main_loop() as SceneTree
	var panel: Control = PS.new()
	root.add_child(panel)
	await tree.process_frame
	panel.open([])   # EMPTY codex override — the builder takes the meta as an ARG
	_check(c, bool(panel.is_open()), "open([]) opens the panel headless")
	var n := int(panel.card_count())
	var db := _n(root, "NpcDB")
	_check(c, db != null and n == (db.defs as Dictionary).size(), "the deck holds the full roster (%d)" % n)
	_check(c, int(panel.current_index()) == 0, "the deck opens on card 0")
	panel.show_card(3)
	_check(c, int(panel.current_index()) == 3, "show_card jumps the deck directly (the test/probe seam)")
	panel.next()
	_check(c, int(panel.current_index()) == 4, "next() advances one card")
	panel.show_card(0)
	panel.prev()
	_check(c, int(panel.current_index()) == n - 1, "prev() from card 0 WRAPS to the deck's end")
	panel.next()
	_check(c, int(panel.current_index()) == 0, "next() from the end WRAPS back to card 0")
	panel.spin_to(5)
	_check(c, int(panel.current_index()) == 5 and not bool(panel.is_spinning()),
		"headless spin_to lands INSTANTLY (animations are live-only)")
	var landed := int(panel.spin())
	_check(c, landed >= 0 and landed < n and int(panel.current_index()) == landed,
		"spin() picks a deck index with the UI-layer RNG and lands on it (headless instant)")
	# v2 INVERSION (user correction): SHOW_ALL ships true, so an EMPTY codex now offers the
	# beneath-the-mask flip on EVERY monster-art Beyonder (the old assert pinned flippable==0).
	var expected_flippable := 0
	var flippable := 0
	var first_flip := -1
	for i in n:
		panel.show_card(i)
		var cd: Dictionary = panel.current_card()
		var sec: Dictionary = cd.get("secret", {}) if cd.get("secret") is Dictionary else {}
		if String(cd.get("state", "")) == "revealed" and String(sec.get("monster_art", "")) != "":
			expected_flippable += 1
		if bool(panel.can_flip()):
			flippable += 1
			if first_flip < 0:
				first_flip = i
	_check(c, expected_flippable >= 1 and flippable == expected_flippable,
		"SHOW_ALL: every monster-art Beyonder offers the flip on an EMPTY codex (%d cards)" % flippable)
	panel.show_card(first_flip if first_flip >= 0 else 0)
	panel.flip()
	_check(c, first_flip >= 0 and bool(panel.is_flipped()),
		"flip() turns a revealed card to its monster face (no codex needed)")
	panel.next()
	_check(c, not bool(panel.is_flipped()), "leaving the card turns it back (flip state resets per card)")
	# v2: the dossier overflows the fixed card — the card content is SCROLLABLE.
	var scrolls := panel.find_children("DossierScroll", "", true, false)
	_check(c, scrolls.size() == 1 and scrolls[0] is ScrollContainer,
		"the card mounts the DossierScroll container (the overflow scroll seam)")
	if panel.has_method("scroll_dossier"):   # pre-implementation guard: FAIL red, never crash
		panel.scroll_dossier(40)
		panel.next()
		_check(c, int(panel.dossier_scroll_value()) == 0,
			"changing cards RESETS the dossier scroll to the top")
	else:
		_check(c, false, "the panel exposes the scroll_dossier seam")
	panel.close()
	_check(c, not bool(panel.is_open()), "close() closes the panel")
	panel.queue_free()
	await tree.process_frame

# (h) --------------------------------------------------------------------------------------------
static func _h_title_reachability(c: Dictionary, root: Node) -> void:
	print("[cast (h): LIVE REACHABILITY — the TITLE wires The Cast button; the panel reads the REAL ledger]")
	var tree := Engine.get_main_loop() as SceneTree
	var RM := _n(root, "RunManager")
	var db := _n(root, "NpcDB")
	if RM == null or db == null:
		_check(c, false, "RunManager + NpcDB autoloads are registered")
		return
	# Stage a learned form in the SANDBOXED meta slot (data-driven pick: the first Beyonder's
	# start form), so the button-opened panel proves it reads RunManager.meta_codex().
	var staged_npc := ""
	var staged_form := ""
	for id in (db.defs as Dictionary).keys():
		var f := String(((db.defs as Dictionary)[id] as Dictionary).get("combat_form", ""))
		if f != "":
			staged_npc = String(id)
			staged_form = f
			break
	_check(c, staged_form != "", "a Beyonder stands in the roster data to stage (%s)" % staged_npc)
	var staged_line := "Seen beneath the mask."
	var staged := {"version": 1, "runs_played": 1, "unlocked_pathways": [],
		"codex": [{"id": "adversary:%s" % staged_form, "learned": staged_line}],
		"meta_currency": 0}
	var f := FileAccess.open(String(RM.meta_path), FileAccess.WRITE)
	f.store_string(JSON.stringify(staged))
	f.close()
	RM.reload_meta()
	# Mount the REAL title raiser.
	var boot: Node = (load("res://src/BootController.gd") as GDScript).new()
	root.add_child(boot)
	await tree.process_frame
	var btns := boot.find_children("CastButton", "", true, false)
	_check(c, btns.size() == 1, "the TITLE mounts The Cast button (fails if the button is removed)")
	if btns.size() == 1:
		_check(c, String((btns[0] as Button).text).to_lower().contains("cast"),
			"the button reads as The Cast")
		(btns[0] as Button).pressed.emit()
	await tree.process_frame
	var panel: Node = boot.cast_panel() if boot.has_method("cast_panel") else null
	_check(c, panel != null and bool(panel.is_open()),
		"pressing the button OPENS the Cast panel (fails if the wire is removed)")
	if panel != null:
		_check(c, int(panel.card_count()) == (db.defs as Dictionary).size(),
			"the button-opened deck holds the full roster")
		var idx := int(panel.index_of(staged_npc))
		panel.show_card(idx)
		var cur: Dictionary = panel.current_card()
		_check(c, String(cur.get("state", "")) == "revealed",
			"the staged NPC stands revealed (trivially true under SHOW_ALL — kept as a floor)")
		# v2: SHOW_ALL reveals everyone, so `state` no longer proves the meta read. The QUOTED
		# learned line does — it exists ONLY in the staged RunManager.meta_codex() ledger.
		var lines: Array = cur.get("codex_lines", []) if cur.get("codex_lines") is Array else []
		_check(c, lines.size() == 1 and String(lines[0]) == staged_line,
			"the panel READ the REAL RunManager.meta_codex(): the staged ledger line is quoted on the card")
		panel.close()
		_check(c, not bool(panel.is_open()), "the panel closes back to the title")
	boot.queue_free()
	await tree.process_frame
	RM.reset_meta()
