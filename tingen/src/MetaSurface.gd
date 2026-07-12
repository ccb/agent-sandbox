extends Object
## B3 (retro) — the meta-progression VIEW-MODEL builder: the ONE place the persistent meta
## (codex / earned pathway unlocks / meta-currency) becomes display lines for the two live surfaces
## the M27 payoff was missing — the TITLE screen's ledger panel (BootController._build_meta_panel)
## and the EndGame screen's run-payoff section (EndGame._append_run_payoff).
##
## PURE + headless-testable: staged data in -> strings out. No autoload reads, no scene work, no
## NPC-identity branches (engine neutrality §8): pathway names render from their ids exactly like
## the M30 pathway picker, and every codex line shown here was already authored in
## data/scenario.json's `codex` block (RunManager._codex_line wrote it into the meta at run end).
##
## Currency display name: the meta-currency is bookkeeping toward future meta unlocks, never run
## power (§8). "Sigils" is its dossier name on these panels; one const so it stays retunable.

const CURRENCY_NAME := "Sigils"
const MAX_TITLE_CODEX_LINES := 6    # the title ledger stays modest: newest N entries + a fold line
const MAX_PAYOFF_CODEX_LINES := 4   # the EndGame payoff quotes at most N new learnings

## The TITLE ledger model. Inputs mirror the RunManager meta getters (meta_currency /
## meta_runs_played / meta_unlocked_pathways / meta_codex); output is ready-to-render copy.
static func title_model(currency: int, runs_played: int, unlocked: Array, codex: Array) -> Dictionary:
	var pathways := "none yet"
	if not unlocked.is_empty():
		var names: Array = []
		for p in unlocked:
			names.append(String(p).capitalize())
		pathways = ", ".join(PackedStringArray(names))
	# Newest learnings first (the codex appends chronologically on disk), capped for the panel.
	var lines: Array = []
	for i in range(codex.size() - 1, -1, -1):
		if lines.size() >= MAX_TITLE_CODEX_LINES:
			break
		var e = codex[i]
		if e is Dictionary and String((e as Dictionary).get("learned", "")) != "":
			lines.append(String((e as Dictionary).get("learned", "")))
	var more := codex.size() - lines.size()
	return {
		"header": "THE INVESTIGATOR'S LEDGER",
		"summary": "%s: %d    Runs: %d    Pathways earned: %s" % [CURRENCY_NAME, currency, runs_played, pathways],
		"codex_header": "Codex — what the city has taught you:",
		"codex_lines": lines,
		"codex_more": ("…and %d older entries." % more) if more > 0 else "",
		"empty_line": "" if not lines.is_empty() else "The codex is empty. Tingen keeps its secrets — for now.",
	}

## The EndGame RUN-PAYOFF model. Input is RunManager.meta_last_payoff() — the delta the run-end
## flush actually wrote (currency_delta/currency_total/new_unlocks/new_codex). An empty/outcome-less
## payoff yields {} so nothing renders (death/lost_control setbacks are not run ends and pay nothing).
static func payoff_model(payoff: Dictionary) -> Dictionary:
	if payoff.is_empty() or String(payoff.get("outcome", "")) == "":
		return {}
	var lines: Array = []
	var delta := int(payoff.get("currency_delta", 0))
	var total := int(payoff.get("currency_total", 0))
	if delta > 0:
		lines.append("+%d %s earned — %d in the ledger now." % [delta, CURRENCY_NAME, total])
	else:
		lines.append("No %s earned. The ledger holds at %d." % [CURRENCY_NAME, total])
	var unlocks: Array = payoff.get("new_unlocks", []) if payoff.get("new_unlocks") is Array else []
	for u in unlocks:
		lines.append("New pathway unlocked: %s." % String(u).capitalize())
	var new_codex: Array = payoff.get("new_codex", []) if payoff.get("new_codex") is Array else []
	if not new_codex.is_empty():
		lines.append("The codex grows:")
		var shown := 0
		for e in new_codex:
			if shown >= MAX_PAYOFF_CODEX_LINES:
				break
			if e is Dictionary and String((e as Dictionary).get("learned", "")) != "":
				lines.append("• %s" % String((e as Dictionary).get("learned", "")))
				shown += 1
		if new_codex.size() > shown:
			lines.append("…and %d more." % (new_codex.size() - shown))
	return {"header": "THE LEDGER RECORDS", "lines": lines}
