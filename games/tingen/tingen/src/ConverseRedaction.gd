class_name ConverseRedaction
extends RefCounted
## Engine-side OUTBOUND redaction for the /converse return path (B11 — the secret-leak backstop).
##
## The converse channel forwards an NPC's OWN `secrets` into the prompt so a revealed cultist can
## discuss them; the model is asked to keep un-earned secrets hidden, but that is BEHAVIORAL. A
## swapped/weaker per-NPC model — or just a slip in the suggested `replies` chips (the observed
## break) — can push plot content the player has not earned into the reply. This module is the
## ENGINE backstop that does not trust the model: it scans the returned `say` + each `replies` chip
## against the speaking agent's OWN un-revealed secret DATA (and its true combat_form / pathway
## identity) and softens the line / drops the chip when it reproduces an un-earned secret.
##
## Engine-neutral + data-driven (CLAUDE.md): every decision reads the agent's own secrets/knowledge
## /form DATA passed in by the caller — there is NO NPC-identity branch, no hardcoded secret string.
## A REVEALED secret is never in the un-revealed set the caller passes, so legitimate revealed
## conversation is untouched (the caller computes `agent.unrevealed_secrets()`).
##
## Matching rule (low false-positive, data-neutral): each secret / identity string becomes a MODEL —
## a set of DISTINCTIVE tokens (proper nouns len>=3, or content words len>=5) minus common stopwords
## minus anything the agent may speak as fact (its `knowledge`) and its own name. A line LEAKS a
## model when it reproduces >= min_hits DISTINCT tokens of that model, where min_hits is 2 for a
## multi-token model (so a lone shared word — a character name, a common noun — never trips it) and 1
## for a single distinctive token (a rare identifier IS the leak on its own).

## The in-fiction deflection a leaking `say` is replaced with (never a blank line). Neutral + agent-
## agnostic — the character simply declines to say the thing.
const NEUTRAL_SAY: String = "They hold your gaze and say nothing of the sort."

## Common words that carry no secret signal (kept small + language-neutral to the setting). A token in
## this set never becomes a model token, whatever its case.
const STOPWORDS: PackedStringArray = [
	"the", "and", "for", "with", "that", "this", "into", "from", "you", "your", "are", "was", "were",
	"has", "have", "had", "not", "but", "his", "her", "him", "she", "they", "them", "who", "what",
	"why", "how", "when", "where", "will", "would", "could", "should", "there", "here", "then",
	"than", "over", "under", "about", "onto", "off",
]

## Build the per-conversation redaction from the speaking agent's own DATA. Public entry.
##   reply     : the model's {say, action, replies} return (unchanged; a cleaned COPY comes back)
##   secrets   : the agent's UN-revealed secret strings (caller: agent.unrevealed_secrets())
##   form_groups: token GROUPS for the true combat identity (caller: form_tokens(combat_form, pathway))
##   protected : things the agent MAY speak as fact — its `knowledge` (+ its own name); never redacted
static func filter_reply(reply: Dictionary, secrets: Array, form_groups: Array = [],
		protected: Array = []) -> Dictionary:
	var models: Array = _build_models(secrets, form_groups, protected)
	var out: Dictionary = reply.duplicate(true)
	if _leaks(String(out.get("say", "")), models):
		out["say"] = NEUTRAL_SAY
	var reps_in: Array = out.get("replies", []) if out.get("replies") is Array else []
	var kept: Array = []
	for r in reps_in:
		if not _leaks(_reply_text(r), models):
			kept.append(r)
	out["replies"] = kept
	return out

## The stored secret string that `text` reproduces — by exact match first, else by the SAME
## token rule the scrubber uses (>= min_hits distinctive tokens, knowledge-protected tokens
## excluded) — or "" when it matches none. The earned-reveal wire (B2/M23) resolves a confessed
## or paraphrased secret back to the exact stored string Agent.reveal_secret ledgers, symmetric
## by construction: a text this module WOULD scrub maps to the secret it would scrub, so
## revealing it unlocks exactly that line of talk and nothing else. Data-driven, agent-agnostic.
static func matched_secret(text: String, secrets: Array, protected: Array = []) -> String:
	for s in secrets:
		if String(s) == text:
			return String(s)
	for s in secrets:
		if _leaks(text, _build_models([String(s)], [], protected)):
			return String(s)
	return ""

## Token GROUPS for the agent's true combat identity — the combat_form id and the pathway id, each
## split into its distinctive parts. A group is a single model (so a 2-part form id needs both parts,
## a lone pathway word is its own single-token model). Empty ids contribute nothing.
static func form_tokens(combat_form: String, pathway: String) -> Array:
	var groups: Array = []
	for ident in [combat_form, pathway]:
		var toks: PackedStringArray = _distinctive_tokens(String(ident).replace("_", " ").replace("-", " "))
		if not toks.is_empty():
			groups.append(toks)
	return groups

# --- internals ------------------------------------------------------------------------------------

## A model = { "tokens": PackedStringArray(lowercased, distinct), "min_hits": int }.
static func _build_models(secrets: Array, form_groups: Array, protected: Array) -> Array:
	var protected_set: Dictionary = {}
	for p in protected:
		for t in _distinctive_tokens(String(p)):
			protected_set[t] = true
	var models: Array = []
	for s in secrets:
		var toks: PackedStringArray = _drop_protected(_distinctive_tokens(String(s)), protected_set)
		if not toks.is_empty():
			models.append({"tokens": toks, "min_hits": 2 if toks.size() >= 2 else 1})
	for g in form_groups:
		var gt: PackedStringArray = _drop_protected(_to_lower_set(g), protected_set)
		if not gt.is_empty():
			models.append({"tokens": gt, "min_hits": 2 if gt.size() >= 2 else 1})
	return models

## Distinctive, lowercased, DISTINCT tokens of a phrase: proper nouns (initial-uppercase, len>=3) or
## content words (len>=5), never a stopword. This is the signal a leak must reproduce.
static func _distinctive_tokens(phrase: String) -> PackedStringArray:
	var out: PackedStringArray = []
	for raw in _words(phrase):
		var alpha := _alpha_only(raw)
		if alpha.length() < 3:
			continue
		var lower := alpha.to_lower()
		if STOPWORDS.has(lower):
			continue
		var is_proper := alpha[0] == alpha[0].to_upper() and alpha[0] != alpha[0].to_lower()
		if (is_proper and alpha.length() >= 3) or alpha.length() >= 5:
			if not out.has(lower):
				out.append(lower)
	return out

## Lowercased distinct token set of an already-tokenized group (form parts), dropping stopwords/shorts.
static func _to_lower_set(group) -> PackedStringArray:
	var out: PackedStringArray = []
	for raw in (group as Array if group is Array else Array(group as PackedStringArray)):
		var alpha := _alpha_only(String(raw)).to_lower()
		if alpha.length() >= 3 and not STOPWORDS.has(alpha) and not out.has(alpha):
			out.append(alpha)
	return out

static func _drop_protected(toks: PackedStringArray, protected_set: Dictionary) -> PackedStringArray:
	var out: PackedStringArray = []
	for t in toks:
		if not protected_set.has(t):
			out.append(t)
	return out

## Does `text` reproduce >= min_hits distinct tokens of ANY model?
static func _leaks(text: String, models: Array) -> bool:
	if text.strip_edges() == "" or models.is_empty():
		return false
	var present: Dictionary = {}
	for raw in _words(text):
		var t := _alpha_only(raw).to_lower()
		if t != "":
			present[t] = true
	for m in models:
		var hits := 0
		for tok in (m["tokens"] as PackedStringArray):
			if present.has(tok):
				hits += 1
		if hits >= int(m["min_hits"]):
			return true
	return false

## Split on any non-letter run so "Iron Cross," and "grendel_wyrm" tokenize cleanly.
static func _words(text: String) -> PackedStringArray:
	var spaced := ""
	for i in text.length():
		var ch := text[i]
		spaced += ch if (ch >= "a" and ch <= "z") or (ch >= "A" and ch <= "Z") else " "
	return spaced.split(" ", false)

static func _alpha_only(w: String) -> String:
	var out := ""
	for i in w.length():
		var ch := w[i]
		if (ch >= "a" and ch <= "z") or (ch >= "A" and ch <= "Z"):
			out += ch
	return out

## The rendered text of a reply chip — chips are either a plain String or {id, text}.
static func _reply_text(r) -> String:
	if r is Dictionary:
		return String((r as Dictionary).get("text", ""))
	return String(r)
