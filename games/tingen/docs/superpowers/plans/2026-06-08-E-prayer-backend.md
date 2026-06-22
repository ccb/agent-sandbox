# Plan E — Prayer backend

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development. Steps use checkbox (`- [ ]`) syntax.

**Goal:** Let the player petition the focused Tingen pantheon and receive an LLM-judged answer in one of four canon registers — **Granted (应允)**, **Cryptic (神秘应答)**, **Ignored (无应)**, **Punished (惩罚)**. The outcome depends on the *god*, the player's *standing* with it, and the *prayer's content* (respect vs. demand, domain alignment). This plan builds the data + adjudication + effects backend; Plan F is the UI.

**Architecture:** Prayer is adjudicated through a **second method on the existing sidecar contract** — `adjudicate_prayer(request)` — parallel to the agents' `propose(snapshots)`. `MockSidecar` models the four outcomes deterministically (the real LLM replaces it later, same as `propose`). A new `PrayerService` autoload orchestrates: build the request (god + standing + prayer text) → route through `SidecarBridge` → apply mechanical effects → update per-god standing → log a first-class `player_prayer` event (so the overseer treats prayer like any other player involvement). `pray` is also added to the shared `action_schema.json` so it is parity-checked and agents could pray too. A Python reference adjudicator + parity test guard the GDScript↔Python boundary, mirroring the existing `schema_parity_check.py`.

**Tech Stack:** Godot 4.6, GDScript; Python 3 stdlib (reference adjudicator). Depends on nothing from A/B/C/D except that they share `run_tests.gd`.

**Key facts (verified against the codebase):**
- `SidecarClient` (`class_name … extends RefCounted`) is the abstract brain boundary; `MockSidecar extends SidecarClient` is deterministic; `SidecarBridge` (autoload) holds one client and exposes `propose`. We add `adjudicate_prayer` to all three.
- `ActionSchema` (`class_name`, static loader) reads `data/action_schema.json` (shared verbatim with the Python sidecar). Adding a verb there is auto-picked-up by both languages; the parity test compares the two loaded schemas + per-fixture verdicts.
- `WorldState` (autoload) pressures via `adjust(&"name", delta)` (clamped 0..100): `corruption`, `panic`, `fatigue`, `cult_readiness`, `attention`. Signals `thought_requested(text)`, `lead_changed`, `state_changed`.
- `SummoningPlan.add_impede(amount, reason)` weakens the descent. `EventBus.emit_event(type, data)` logs; any `player_*` event marks the player involved (`Overseer.allows_exposure()` flips true).
- `PlayerActions` (autoload Node, NOT `class_name`) uses **bare** autoload references (`SummoningPlan`, `EventBus`, `Agents`) at runtime — the pattern `PrayerService` follows. (`class_name` scripts can't, in the headless `-s` harness — they use `_al()`; an autoload `Node` script can.)
- `SaveManager.save_game`/`load_game` is a dict of each subsystem's `to_dict()`/`from_dict()`. Adding persistence = add one key.
- `run_tests.gd` (`extends SceneTree`): register tests in `_init()`; `_ok(cond, label)`, `_skip(label)`; `_python_argv_prefix()` already exists for invoking Python via `/usr/bin/env`.
- Headless run: `godot --headless --path tingen -s tests/run_tests.gd`. Summary line `=== N passed, M failed, K skipped ===`.

**The focused pantheon (per user canon):** the descending evil god **外神** (`outer_god`, the cult's goal — answers, but its power feeds the gate), the **黑夜女神** Goddess of Night (`goddess_of_night`, Church of Evernight), the **永恒烈阳** Eternal Blazing Sun (`eternal_blazing_sun`, zealous, quick to punish), and the **愚者** the Fool (`the_fool`, answers obliquely in the tarot register).

---

## Task E1: gods.json + GodDB + the `pray` verb

**Files:**
- Create: `tingen/data/gods.json`
- Create: `tingen/src/GodDB.gd`
- Modify: `tingen/data/action_schema.json` (add `pray`)
- Modify: `tingen/src/ActionCommit.gd` (handle `pray` so an agent praying is a safe no-op + memory)
- Test: `tingen/tests/run_tests.gd` (add `_test_gods_db`; add two `pray` fixtures to the existing parity battery; register `_test_gods_db` after `_test_summoning_plan`)

- [ ] **Step 1: Write the failing test**

Add to `run_tests.gd`:

```gdscript
func _test_gods_db() -> void:
	print("[gods db]")
	_ok(GodDB.ids().size() == 4, "four gods in the focused pantheon")
	_ok(GodDB.has("the_fool"), "the Fool is present")
	var fool: Dictionary = GodDB.get_def("the_fool")
	_ok(String(fool.get("name_zh", "")) == "愚者", "the Fool carries its 中文 name")
	_ok((fool.get("domain", []) as Array).size() > 0, "a god lists domain keywords")
	_ok(GodDB.has("outer_god"), "the descending god (外神) is present")
	_ok(bool(GodDB.get_def("goddess_of_night").get("opposes_cult", false)), "the Goddess of Night opposes the cult")
	# pray is now a known, schema-valid verb.
	_ok(ActionSchema.is_verb("pray"), "pray is a known action verb")
	_ok(ActionSchema.validate({"actor": "player", "verb": "pray", "args": {"god": "the_fool", "prayer": "guide me"}})["ok"],
		"well-formed pray validates")
	_ok(not ActionSchema.validate({"actor": "player", "verb": "pray", "args": {"god": "the_fool"}})["ok"],
		"pray missing 'prayer' rejected")
```

Register it in `_init()` immediately after `_test_summoning_plan()`:

```gdscript
	_test_summoning_plan()
	_test_gods_db()
```

- [ ] **Step 2: Run to verify it fails** — `godot --headless --path tingen -s tests/run_tests.gd` → FAIL (GodDB missing, `pray` not a verb).

- [ ] **Step 3: Add the `pray` verb to the shared schema**

In `tingen/data/action_schema.json`, add one entry to `"verbs"` (e.g. after `"report"`). Keep valid JSON — every entry except the last needs a trailing comma:

```json
		"report": ["to", "info"],
		"pray": ["god", "prayer"],
		"idle": []
```

- [ ] **Step 4: Create `tingen/data/gods.json`**

```json
{
	"outer_god": {
		"name": "The Descending One",
		"name_zh": "外神",
		"domain": ["descent", "gate", "void", "hunger", "ruin"],
		"register": "ravenous",
		"wrath": 1.0,
		"opposes_cult": false,
		"blurb": "The evil god the Iron Cross cell labors to pull into Tingen. It answers — but every gift widens the gate it is coming through."
	},
	"goddess_of_night": {
		"name": "The Goddess of Night",
		"name_zh": "黑夜女神",
		"domain": ["night", "dream", "secrets", "shelter", "mercy"],
		"register": "veiled",
		"wrath": 0.4,
		"opposes_cult": true,
		"blurb": "Mistress of night and dream; the Church of Evernight shelters the fearful. She rewards the humble and the watchful."
	},
	"eternal_blazing_sun": {
		"name": "The Eternal Blazing Sun",
		"name_zh": "永恒烈阳",
		"domain": ["sun", "fire", "judgment", "purge", "courage"],
		"register": "burning",
		"wrath": 0.8,
		"opposes_cult": true,
		"blurb": "Lord of sun and fire; the Church of the Sun purges corruption by flame. Zealous, and quick to punish the unclean."
	},
	"the_fool": {
		"name": "The Fool",
		"name_zh": "愚者",
		"domain": ["fate", "mystery", "fortune", "travelers", "secrets"],
		"register": "tarot",
		"wrath": 0.3,
		"opposes_cult": true,
		"blurb": "The Mysterious Sovereign above the gray fog. Answers obliquely, in the language of the tarot — if it answers at all."
	}
}
```

> **Parity note:** keep each `wrath` such that `wrath * 2` never lands on a `.5` (e.g. avoid 0.25/0.75). GDScript and Python round `.5` differently; the values above (1.0, 0.4, 0.8, 0.3) are safe. The parity test (E4) would catch a violation anyway.

- [ ] **Step 5: Create `tingen/src/GodDB.gd`**

```gdscript
class_name GodDB
extends RefCounted
## Read-only loader for the focused Tingen pantheon (data/gods.json). Pure data access,
## shared by the prayer adjudicator (MockSidecar) and the prayer panel. Mirrors the
## ActionSchema static-loader pattern, so no extra autoload is needed and a class_name
## script can read it without the _al() dance.

const PATH: String = "res://data/gods.json"

static var _defs: Dictionary = {}
static var _loaded: bool = false

static func _ensure_loaded() -> void:
	if _loaded:
		return
	_loaded = true
	if not FileAccess.file_exists(PATH):
		push_error("GodDB: missing %s" % PATH)
		return
	var parsed: Variant = JSON.parse_string(FileAccess.get_file_as_string(PATH))
	if typeof(parsed) == TYPE_DICTIONARY:
		_defs = parsed

## Sorted god ids (stable order for the panel).
static func ids() -> Array:
	_ensure_loaded()
	var k: Array = _defs.keys()
	k.sort()
	return k

static func has(id: String) -> bool:
	_ensure_loaded()
	return _defs.has(id)

## A copy of one god's def ({} if unknown).
static func get_def(id: String) -> Dictionary:
	_ensure_loaded()
	return (_defs.get(id, {}) as Dictionary).duplicate(true)

## Every god as a def dict with its "id" folded in, in sorted-id order.
static func all() -> Array:
	_ensure_loaded()
	var out: Array = []
	for id in ids():
		var d: Dictionary = get_def(id)
		d["id"] = id
		out.append(d)
	return out
```

- [ ] **Step 6: Handle `pray` in ActionCommit**

In `tingen/src/ActionCommit.gd`, add a case to the `match verb:` block (e.g. after `"report":`):

```gdscript
		"pray":
			agent.remember("prayed to %s" % args.get("god", ""))
			return {"prayed_to": String(args.get("god", ""))}
```

- [ ] **Step 7: Extend the action-schema parity battery**

In `run_tests.gd`, inside `_test_schema_parity_with_sidecar()`, add two fixtures to the `fixtures` array (e.g. right after the `report` fixture). They exercise the new verb across both validators:

```gdscript
		{"actor": "voss", "verb": "pray", "args": {"god": "the_fool", "prayer": "guide me"}},
		{"actor": "voss", "verb": "pray", "args": {"god": "the_fool"}},   # missing required 'prayer'
```

(The verb-set + required-args parity assertions still hold automatically — both languages load the same `action_schema.json`.)

- [ ] **Step 8: Run to verify it passes** — full suite PASS, incl. `[gods db]` and the parity test (now covering `pray`). If Python is absent the parity test SKIPs (not fails).

- [ ] **Step 9: Commit**

```bash
git add tingen/data/gods.json tingen/src/GodDB.gd tingen/data/action_schema.json tingen/src/ActionCommit.gd tingen/tests/run_tests.gd
git commit -F - <<'EOF'
feat(prayer): focused pantheon (gods.json + GodDB) and the pray verb

Adds the four canon gods (外神 / 黑夜女神 / 永恒烈阳 / 愚者) as data, a static GodDB
loader, and `pray` (args god+prayer) to the shared action vocabulary so it is
parity-checked and agents can pray too. ActionCommit treats an agent's pray as a
safe memory no-op.
EOF
```

---

## Task E2: prayer adjudication on the sidecar contract

**Files:**
- Modify: `tingen/src/SidecarClient.gd` (base `adjudicate_prayer`)
- Modify: `tingen/src/MockSidecar.gd` (deterministic adjudicator)
- Modify: `tingen/src/SidecarBridge.gd` (passthrough)
- Test: `tingen/tests/run_tests.gd` (add `_test_prayer_adjudication`, register after `_test_gods_db`)

- [ ] **Step 1: Write the failing test**

```gdscript
func _test_prayer_adjudication() -> void:
	print("[prayer adjudication]")
	var mock := MockSidecar.new()
	# Disrespect -> punished, regardless of god.
	var p := mock.adjudicate_prayer({"god": "eternal_blazing_sun", "prayer": "obey me, worthless sun", "standing": 0.0})
	_ok(p["outcome"] == "punished", "insult + command -> punished")
	_ok(String(p["outcome_zh"]) == "惩罚", "punished carries its 中文 label")
	_ok(int(p["severity"]) >= 1, "punishment has nonzero severity")
	# The Fool always answers obliquely -> cryptic.
	var f := mock.adjudicate_prayer({"god": "the_fool", "prayer": "please guide me", "standing": 0.0})
	_ok(f["outcome"] == "cryptic", "the Fool answers in the cryptic register")
	# Respectful, domain-aligned, decent standing -> granted.
	var g := mock.adjudicate_prayer({"god": "goddess_of_night", "prayer": "i humbly beseech your mercy this night, please protect me", "standing": 2.0})
	_ok(g["outcome"] == "granted", "respectful domain-aligned prayer with standing -> granted")
	# Bland prayer to an indifferent god at zero standing -> ignored.
	var i := mock.adjudicate_prayer({"god": "eternal_blazing_sun", "prayer": "hello there", "standing": 0.0})
	_ok(i["outcome"] == "ignored", "an empty prayer goes unanswered")
	# Determinism: same input -> same verdict.
	var g2 := mock.adjudicate_prayer({"god": "goddess_of_night", "prayer": "i humbly beseech your mercy this night, please protect me", "standing": 2.0})
	_ok(g2["outcome"] == g["outcome"] and int(g2["severity"]) == int(g["severity"]), "adjudication is deterministic")
	# Bridge routes adjudication to the active client.
	var SB: Object = root.get_node("/root/SidecarBridge")
	SB.set_client(mock)
	_ok(SB.adjudicate_prayer({"god": "the_fool", "prayer": "guide me"})["outcome"] == "cryptic", "bridge routes prayer adjudication")
```

Register after `_test_gods_db()`:

```gdscript
	_test_gods_db()
	_test_prayer_adjudication()
```

- [ ] **Step 2: Run to verify it fails** — `adjudicate_prayer` missing. FAIL.

- [ ] **Step 3: Add the base contract to SidecarClient**

In `tingen/src/SidecarClient.gd`, append:

```gdscript
## Adjudicate a player's prayer. `request` carries { god, prayer, standing }. Returns
## { god, outcome, outcome_zh, severity, score }. Base is a neutral "ignored"; MockSidecar
## models the four canon outcomes deterministically and a future HttpSidecar defers to the LLM.
func adjudicate_prayer(request: Dictionary) -> Dictionary:
	return {
		"god": String(request.get("god", "")),
		"outcome": "ignored", "outcome_zh": "无应", "severity": 0, "score": 0,
	}
```

- [ ] **Step 4: Implement the deterministic adjudicator on MockSidecar**

In `tingen/src/MockSidecar.gd`, append. **This logic is mirrored byte-for-byte by `agent-sidecar/prayer_adjudicator.py` (Task E4); the parity test guards the two.**

```gdscript
# --- Prayer adjudication (deterministic stand-in for the LLM's judgment) -----------------
# Mirrored EXACTLY by agent-sidecar/prayer_adjudicator.py — keep the marker lists,
# thresholds, and the decision order identical, or the parity test (E4) fails.
const PRAYER_RESPECT: PackedStringArray = [
	"please", "humbly", "beseech", "guide", "protect", "mercy",
	"grant", "thank", "praise", "honor", "i offer", "i beg",
]
const PRAYER_DISRESPECT: PackedStringArray = [
	"demand", "command", "obey", "serve me", "worthless",
	"weak", "kneel", "i curse", "mock", "useless",
]
const GRANT_THRESHOLD: int = 3
const CRYPTIC_THRESHOLD: int = 1
const OUTCOME_ZH: Dictionary = {
	"granted": "应允", "cryptic": "神秘应答", "ignored": "无应", "punished": "惩罚",
}

## Judge one prayer. request: { god, prayer, standing }. Returns
## { god, outcome, outcome_zh, severity, score }. Pure + deterministic.
func adjudicate_prayer(request: Dictionary) -> Dictionary:
	var god_id := String(request.get("god", ""))
	var text := String(request.get("prayer", "")).to_lower()
	var standing := float(request.get("standing", 0.0))
	var god: Dictionary = GodDB.get_def(god_id)

	var respect := _count_markers(text, PRAYER_RESPECT)
	var disrespect := _count_markers(text, PRAYER_DISRESPECT)
	var domain_hit := _domain_hit(text, god.get("domain", []))

	var score := respect * 2 - disrespect * 5
	score += 1 if domain_hit else 0
	score += int(clampf(standing, -3.0, 3.0))

	var register := String(god.get("register", ""))
	var wrath := float(god.get("wrath", 0.5))

	var outcome := "ignored"
	var severity := 0
	if disrespect > 0:
		outcome = "punished"
		severity = clampi(disrespect + int(round(wrath * 2.0)), 1, 3)
	elif register == "tarot":
		outcome = "cryptic"          # the Fool answers obliquely, if at all
		severity = 1
	elif score >= GRANT_THRESHOLD:
		outcome = "granted"
		severity = 2 if god_id == "outer_god" else 1
	elif score >= CRYPTIC_THRESHOLD:
		outcome = "cryptic"
		severity = 1
	else:
		outcome = "ignored"
		severity = 0

	return {
		"god": god_id, "outcome": outcome,
		"outcome_zh": String(OUTCOME_ZH.get(outcome, "")),
		"severity": severity, "score": score,
	}

func _count_markers(text: String, markers: PackedStringArray) -> int:
	var n := 0
	for m in markers:
		if text.contains(m):
			n += 1
	return n

func _domain_hit(text: String, domain: Array) -> bool:
	for kw in domain:
		if text.contains(String(kw).to_lower()):
			return true
	return false
```

- [ ] **Step 5: Add the passthrough on SidecarBridge**

In `tingen/src/SidecarBridge.gd`, append:

```gdscript
func adjudicate_prayer(request: Dictionary) -> Dictionary:
	if client == null:
		return {"god": String(request.get("god", "")), "outcome": "ignored", "outcome_zh": "无应", "severity": 0, "score": 0}
	return client.adjudicate_prayer(request)
```

- [ ] **Step 6: Run to verify it passes** — PASS incl. `[prayer adjudication]`.

- [ ] **Step 7: Commit**

```bash
git add tingen/src/SidecarClient.gd tingen/src/MockSidecar.gd tingen/src/SidecarBridge.gd tingen/tests/run_tests.gd
git commit -F - <<'EOF'
feat(prayer): deterministic prayer adjudication on the sidecar contract

Adds adjudicate_prayer() to SidecarClient/MockSidecar/SidecarBridge. The mock
scores respect/disrespect markers + domain alignment + standing against explicit
thresholds and returns one of granted/cryptic/ignored/punished; the Fool always
answers in the cryptic register and any disrespect is punished. The real LLM
replaces the mock later behind the same contract.
EOF
```

---

## Task E3: PrayerService — orchestration, standing, effects, save/load

**Files:**
- Create: `tingen/src/PrayerService.gd`
- Modify: `tingen/project.godot` (register the autoload)
- Modify: `tingen/src/SaveManager.gd` (persist standing)
- Test: `tingen/tests/run_tests.gd` (add `_test_prayer_service`, register after `_test_prayer_adjudication`)

- [ ] **Step 1: Write the failing test**

```gdscript
func _test_prayer_service() -> void:
	print("[prayer service]")
	var PS: Object = root.get_node("/root/PrayerService")
	var WS: Object = root.get_node("/root/WorldState")
	var SP: Object = root.get_node("/root/SummoningPlan")
	var OV: Object = root.get_node("/root/Overseer")
	var EB: Object = root.get_node("/root/EventBus")
	var SB: Object = root.get_node("/root/SidecarBridge")
	SB.set_client(MockSidecar.new())   # deterministic adjudication
	PS.reset(); SP.reset(); OV.reset(); EB.clear()

	# Unknown god is rejected cleanly.
	_ok(PS.pray("no_such_god", "hi")["ok"] == false, "praying to an unknown god is rejected")

	# Granted by an opposing god: impedes the descent, eases fatigue, raises standing,
	# and marks the player involved.
	WS.set_pressure(&"fatigue", 60.0)
	var impede_before: float = SP.impede_score
	var g: Dictionary = PS.pray("goddess_of_night", "i humbly beseech your mercy this night, please protect me")
	_ok(g["ok"] and g["outcome"] == "granted", "respectful night prayer is granted")
	_ok(SP.impede_score > impede_before, "an opposing god's favor impedes the summoning")
	_ok(WS.get_pressure(&"fatigue") < 60.0, "granted boon eases fatigue")
	_ok(PS.get_standing("goddess_of_night") > 0.0, "standing rises after a granted prayer")
	_ok(OV.allows_exposure(), "praying marks the player involved")
	_ok(EB.events("player_prayer").size() >= 1, "prayer logs a player event")

	# Insolence is punished: corruption spikes, standing falls.
	WS.set_pressure(&"corruption", 0.0)
	var p: Dictionary = PS.pray("eternal_blazing_sun", "obey me, you worthless weak sun, kneel")
	_ok(p["outcome"] == "punished", "insolence is punished")
	_ok(WS.get_pressure(&"corruption") > 0.0, "punishment spikes corruption")
	_ok(PS.get_standing("eternal_blazing_sun") < 0.0, "standing falls after punishment")

	# Praying to the descending god (外神) grants power but feeds the gate.
	PS.reset()
	WS.set_pressure(&"corruption", 0.0)
	WS.set_pressure(&"cult_readiness", 0.0)
	var o: Dictionary = PS.pray("outer_god", "i offer myself, grant me the descent, the gate, the void")
	_ok(o["outcome"] == "granted", "the descending god grants the devoted")
	_ok(WS.get_pressure(&"cult_readiness") > 0.0, "the descending god's favor advances the summoning")
	_ok(WS.get_pressure(&"corruption") > 0.0, "praying to the outer god corrupts the supplicant")

	# Standing round-trips through save/load.
	var SM: Object = root.get_node("/root/SaveManager")
	PS.reset()
	PS.pray("the_fool", "please guide me")   # cryptic -> +1 standing
	var fool_standing: float = PS.get_standing("the_fool")
	_ok(fool_standing > 0.0, "the Fool's cryptic answer still nudges standing")
	var tmp := "user://test_prayer.json"
	_ok(SM.save_game(tmp), "save writes prayer standing")
	PS.reset()
	_ok(PS.get_standing("the_fool") == 0.0, "standing cleared before load")
	_ok(SM.load_game(tmp), "load reads prayer standing")
	_ok(abs(PS.get_standing("the_fool") - fool_standing) < 0.01, "prayer standing restored")
	DirAccess.remove_absolute(ProjectSettings.globalize_path(tmp))
```

Register after `_test_prayer_adjudication()`:

```gdscript
	_test_prayer_adjudication()
	_test_prayer_service()
```

- [ ] **Step 2: Run to verify it fails** — PrayerService autoload missing. FAIL.

- [ ] **Step 3: Create `tingen/src/PrayerService.gd`**

```gdscript
extends Node
## The player's prayer verb (autoload `PrayerService`). The player petitions a god; the
## sidecar (mock now, LLM later) judges the prayer and returns one of four canon outcomes —
## Granted (应允), Cryptic (神秘应答), Ignored (无应), Punished (惩罚). This service builds the
## adjudication request (god + the player's standing + the prayer text), routes it through
## SidecarBridge, applies the mechanical effects, updates per-god standing, and logs a
## first-class `player_prayer` event so the overseer treats prayer like any other player
## involvement. (Autoload Node, so bare autoload refs are fine at runtime — see PlayerActions.)

## Per-god favor. Rises when a god answers well, falls when it punishes. Clamped -10..10.
var standing: Dictionary = {}   # god_id -> float

func get_standing(god_id: String) -> float:
	return float(standing.get(god_id, 0.0))

## Offer a prayer. Returns the full outcome dict for the UI:
##   { ok, god, outcome, outcome_zh, severity, message, struck_down }
## ok is false (with `reason`) when the god id or prayer is malformed.
func pray(god_id: String, text: String) -> Dictionary:
	if not GodDB.has(god_id):
		return {"ok": false, "reason": "unknown god '%s'" % god_id}
	var action := {"actor": "player", "verb": "pray", "args": {"god": god_id, "prayer": text}}
	var check: Dictionary = ActionSchema.validate(action)
	if not check["ok"]:
		return {"ok": false, "reason": String(check["reason"])}

	var verdict: Dictionary = SidecarBridge.adjudicate_prayer({
		"god": god_id, "prayer": text, "standing": get_standing(god_id),
	})
	var outcome := String(verdict.get("outcome", "ignored"))
	var severity := int(verdict.get("severity", 0))
	var god: Dictionary = GodDB.get_def(god_id)
	var struck_down := _apply_effects(god_id, god, outcome, severity)
	var message := _compose_message(god, outcome, severity)

	EventBus.emit_event("player_prayer", {
		"actor": "player", "god": god_id, "outcome": outcome, "severity": severity,
	})
	return {
		"ok": true, "god": god_id, "outcome": outcome,
		"outcome_zh": String(verdict.get("outcome_zh", "")),
		"severity": severity, "message": message, "struck_down": struck_down,
	}

## Apply the mechanical consequences. Returns true if the punishment struck the player down.
func _apply_effects(god_id: String, god: Dictionary, outcome: String, severity: int) -> bool:
	var opposes_cult := bool(god.get("opposes_cult", false))
	match outcome:
		"granted":
			WorldState.adjust(&"fatigue", -15.0)
			_bump_standing(god_id, 2.0)
			if opposes_cult:
				# A rival power lends strength against the descent.
				SummoningPlan.add_impede(8.0 * severity, "divine favor: %s" % god_id)
			elif god_id == "outer_god":
				# The descending god grants power, but you have fed its gate.
				WorldState.adjust(&"corruption", 12.0)
				WorldState.adjust(&"cult_readiness", 8.0)
		"cryptic":
			_bump_standing(god_id, 1.0)
		"ignored":
			pass
		"punished":
			WorldState.adjust(&"corruption", 10.0 * severity)
			WorldState.adjust(&"panic", 5.0 * severity)
			WorldState.adjust(&"fatigue", 8.0 * severity)
			_bump_standing(god_id, -2.0 * severity)
			if severity >= 3:
				EventBus.emit_event("player_struck_down", {"actor": "player", "god": god_id})
				return true
	return false

func _bump_standing(god_id: String, delta: float) -> void:
	standing[god_id] = clampf(get_standing(god_id) + delta, -10.0, 10.0)

## Flavor line per (register, outcome). The mechanical effects are already applied; this is
## just the god's voice for the panel.
func _compose_message(god: Dictionary, outcome: String, severity: int) -> String:
	var god_name := String(god.get("name", "the god"))
	var register := String(god.get("register", ""))
	match outcome:
		"granted":
			if register == "ravenous":
				return "%s answers. Power floods you — and somewhere, a gate widens." % god_name
			return "%s grants your plea; strength settles into your bones." % god_name
		"cryptic":
			if register == "tarot":
				return "The Fool turns a card — The Moon, reversed. What you seek wears a borrowed face."
			return "%s answers, but the meaning is veiled, like a shape behind frosted glass." % god_name
		"ignored":
			return "You speak into the dark. Nothing answers."
		"punished":
			if severity >= 3:
				return "%s does not suffer your insolence. The world goes white, then black." % god_name
			return "%s recoils from your words; cold dread floods in where the prayer should have gone." % god_name
	return ""

func reset() -> void:
	standing.clear()

func to_dict() -> Dictionary:
	return {"standing": standing.duplicate(true)}

func from_dict(d: Dictionary) -> void:
	standing = (d.get("standing", {}) as Dictionary).duplicate(true)
```

- [ ] **Step 4: Register the autoload**

In `tingen/project.godot`, inside `[autoload]`, add after `PlayerActions`:

```
PrayerService="*res://src/PrayerService.gd"
```

- [ ] **Step 5: Persist standing in SaveManager**

In `tingen/src/SaveManager.gd`, add to the `data` dict in `save_game` (e.g. after `"occult_tools"`):

```gdscript
		"prayer": PrayerService.to_dict(),
```

and in `load_game`, alongside the other `from_dict` restores (e.g. after the `OccultToolManager.from_dict(...)` line):

```gdscript
	PrayerService.from_dict(data.get("prayer", {}))
```

- [ ] **Step 6: Run to verify it passes** — PASS incl. `[prayer service]`.

- [ ] **Step 7: Smoke-run** — `godot --headless --path tingen --quit-after 60` → no script errors (autoload loads clean).

- [ ] **Step 8: Commit**

```bash
git add tingen/src/PrayerService.gd tingen/project.godot tingen/src/SaveManager.gd tingen/tests/run_tests.gd
git commit -F - <<'EOF'
feat(prayer): PrayerService — adjudication, effects, standing, persistence

pray() builds the request (god + standing + prayer), routes it through the
sidecar, applies outcome effects (opposing gods' boons impede the descent; the
外神's favor feeds the gate; punishment spikes corruption/panic and can strike the
player down), tracks per-god standing, logs a player_prayer event, and round-trips
standing through SaveManager.
EOF
```

---

## Task E4: Python reference adjudicator + GDScript↔Python parity test

**Files:**
- Create: `agent-sidecar/prayer_adjudicator.py`
- Create: `agent-sidecar/prayer_parity_check.py`
- Test: `tingen/tests/run_tests.gd` (add `_test_prayer_parity_with_sidecar`, register after `_test_schema_parity_with_sidecar`)

- [ ] **Step 1: Write the failing test**

```gdscript
## Guards the GDScript<->Python boundary for prayer judgment exactly as
## _test_schema_parity_with_sidecar guards the action schema: runs a battery of prayers
## through the REAL Python reference adjudicator and asserts identical (outcome, severity).
## Skips (does not fail) when no Python interpreter is available.
func _test_prayer_parity_with_sidecar() -> void:
	print("[prayer parity: gdscript <-> python adjudicator]")
	var py_prefix := _python_argv_prefix()
	if py_prefix.is_empty():
		_skip("no python3 — prayer adjudication parity not verified")
		return
	var mock := MockSidecar.new()
	var fixtures: Array = [
		{"god": "goddess_of_night", "prayer": "i humbly beseech your mercy this night, please protect me", "standing": 2.0},
		{"god": "the_fool", "prayer": "please guide me through the fog", "standing": 0.0},
		{"god": "eternal_blazing_sun", "prayer": "obey me, you worthless weak sun, kneel", "standing": 0.0},
		{"god": "eternal_blazing_sun", "prayer": "hello there", "standing": 0.0},
		{"god": "outer_god", "prayer": "i offer myself, grant me the descent, the gate, the void", "standing": 0.0},
		{"god": "goddess_of_night", "prayer": "i curse your name", "standing": 5.0},
		{"god": "the_fool", "prayer": "demand fortune now", "standing": 0.0},
		{"god": "outer_god", "prayer": "nothing in particular", "standing": -5.0},
	]
	var fixtures_path := "user://_prayer_fixtures.json"
	var ff := FileAccess.open(fixtures_path, FileAccess.WRITE)
	ff.store_string(JSON.stringify(fixtures))
	ff.close()
	var fixtures_os := ProjectSettings.globalize_path(fixtures_path)
	var helper := ProjectSettings.globalize_path("res://").path_join("../agent-sidecar/prayer_parity_check.py")
	var argv: Array = py_prefix.duplicate()
	argv.append(helper)
	argv.append(fixtures_os)
	var out: Array = []
	var code := OS.execute("/usr/bin/env", argv, out, true)
	DirAccess.remove_absolute(fixtures_os)
	var joined := "\n".join(out).strip_edges()
	_ok(code == 0, "python prayer helper exited 0")
	if code != 0:
		printerr("    helper output: %s" % joined)
		return
	var parsed: Variant = JSON.parse_string(joined)
	if typeof(parsed) != TYPE_DICTIONARY:
		_ok(false, "python helper emitted parseable JSON (got: %s)" % joined)
		return
	var py_verdicts: Array = parsed.get("verdicts", [])
	_ok(py_verdicts.size() == fixtures.size(), "one python verdict per prayer fixture")
	var parity := true
	for i in fixtures.size():
		var gd: Dictionary = mock.adjudicate_prayer(fixtures[i])
		var py: Array = py_verdicts[i] if i < py_verdicts.size() else ["", -1]
		var gd_out: String = gd["outcome"]
		var gd_sev: int = int(gd["severity"])
		var py_out: String = String(py[0]) if py.size() > 0 else ""
		var py_sev: int = int(py[1]) if py.size() > 1 else -1
		if gd_out != py_out or gd_sev != py_sev:
			parity = false
			printerr("    prayer mismatch %d (%s): gd=[%s,%d] py=[%s,%d]" % [
				i, str(fixtures[i].get("god", "")), gd_out, gd_sev, py_out, py_sev])
	_ok(parity, "adjudicator outcomes (outcome+severity) match across %d prayers" % fixtures.size())
```

Register after `_test_schema_parity_with_sidecar()` (the last line of `_init()`):

```gdscript
	_test_schema_parity_with_sidecar()
	_test_prayer_parity_with_sidecar()
```

- [ ] **Step 2: Run to verify it fails** — the helper script does not exist → `OS.execute` non-zero → FAIL (or, if Python is absent, SKIP — in that case create the files anyway and rely on a Python-equipped run).

- [ ] **Step 3: Create the reference adjudicator `agent-sidecar/prayer_adjudicator.py`**

```python
#!/usr/bin/env python3
"""
Prayer adjudication reference (deterministic).
==============================================
The offline judgment the sidecar uses for player prayers, mirrored EXACTLY by the Godot
MockSidecar (tingen/src/MockSidecar.gd). The engine test feeds a battery of prayers through
both and asserts identical (outcome, severity); the real LLM replaces this later behind the
same contract. Keep the marker lists, thresholds, and decision order in lockstep with the
GDScript side.

Pure stdlib. Reads the focused pantheon from tingen/data/gods.json (one source of truth with
the engine), so a god's domain/register/wrath cannot drift between the two languages.
"""
from __future__ import annotations

import json
from pathlib import Path

GODS_PATH = Path(__file__).resolve().parent.parent / "tingen" / "data" / "gods.json"

RESPECT = [
    "please", "humbly", "beseech", "guide", "protect", "mercy",
    "grant", "thank", "praise", "honor", "i offer", "i beg",
]
DISRESPECT = [
    "demand", "command", "obey", "serve me", "worthless",
    "weak", "kneel", "i curse", "mock", "useless",
]
GRANT_THRESHOLD = 3
CRYPTIC_THRESHOLD = 1
OUTCOME_ZH = {"granted": "应允", "cryptic": "神秘应答", "ignored": "无应", "punished": "惩罚"}


def load_gods() -> dict:
    with open(GODS_PATH, "r", encoding="utf-8") as f:
        return json.load(f)


def _count(text: str, markers: list) -> int:
    return sum(1 for m in markers if m in text)


def _clampi(v: int, lo: int, hi: int) -> int:
    return max(lo, min(hi, v))


def adjudicate_prayer(request: dict, gods: dict) -> dict:
    god_id = request.get("god", "")
    text = str(request.get("prayer", "")).lower()
    standing = float(request.get("standing", 0.0))
    god = gods.get(god_id, {})

    respect = _count(text, RESPECT)
    disrespect = _count(text, DISRESPECT)
    domain = [str(k).lower() for k in god.get("domain", [])]
    domain_hit = any(kw in text for kw in domain)

    score = respect * 2 - disrespect * 5
    score += 1 if domain_hit else 0
    score += int(max(-3.0, min(3.0, standing)))

    register = god.get("register", "")
    wrath = float(god.get("wrath", 0.5))

    if disrespect > 0:
        outcome = "punished"
        severity = _clampi(disrespect + int(round(wrath * 2.0)), 1, 3)
    elif register == "tarot":
        outcome, severity = "cryptic", 1
    elif score >= GRANT_THRESHOLD:
        outcome = "granted"
        severity = 2 if god_id == "outer_god" else 1
    elif score >= CRYPTIC_THRESHOLD:
        outcome, severity = "cryptic", 1
    else:
        outcome, severity = "ignored", 0

    return {
        "god": god_id, "outcome": outcome,
        "outcome_zh": OUTCOME_ZH.get(outcome, ""),
        "severity": severity, "score": score,
    }
```

- [ ] **Step 4: Create the parity helper `agent-sidecar/prayer_parity_check.py`**

```python
#!/usr/bin/env python3
"""
Cross-language prayer-adjudication parity helper (mirrors schema_parity_check.py).
==================================================================================
Imports the REAL prayer_adjudicator reference and runs it over a battery of prayer requests
read from a JSON-array file, printing ONE JSON object to stdout:

    {"verdicts": [[<outcome:str>, <severity:int>], ...]}

Invoked by tingen/tests/run_tests.gd:
    python3 agent-sidecar/prayer_parity_check.py <fixtures.json>
A file path (not inline JSON) so a quote-laden payload survives the argv. Pure stdlib.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import prayer_adjudicator as pa  # noqa: E402  (the real reference under test)


def main() -> int:
    if len(sys.argv) < 2:
        print(json.dumps({"error": "usage: prayer_parity_check.py <fixtures.json>"}))
        return 2
    try:
        fixtures = json.loads(Path(sys.argv[1]).read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        print(json.dumps({"error": f"could not read fixtures: {exc}"}))
        return 2
    gods = pa.load_gods()
    verdicts = []
    for req in fixtures:
        v = pa.adjudicate_prayer(req, gods)
        verdicts.append([v["outcome"], v["severity"]])
    print(json.dumps({"verdicts": verdicts}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
```

- [ ] **Step 5: Run to verify it passes** — with Python present, `[prayer parity …]` PASSes (8/8 outcomes match). Cross-check by hand: night-mercy→granted(1); fool-guide→cryptic(1); sun-insult→punished(3); sun-bland→ignored(0); outer-devotion→granted(2); night-curse→punished(2); fool-demand→punished(2); outer-bland(standing −5)→ignored(0).

- [ ] **Step 6: Commit**

```bash
git add agent-sidecar/prayer_adjudicator.py agent-sidecar/prayer_parity_check.py tingen/tests/run_tests.gd
git commit -F - <<'EOF'
test(prayer): GDScript<->Python parity for prayer adjudication

Adds a deterministic Python reference adjudicator (reading the same gods.json) and
a parity helper; the engine test runs a battery of prayers through both and asserts
identical (outcome, severity), mirroring the action-schema parity guard. Skips
cleanly when no Python interpreter is present.
EOF
```

---

## Done when

- The four gods load from `gods.json` via `GodDB`; `pray` is a schema-valid, parity-checked verb (`_test_gods_db`, action-schema parity battery).
- `MockSidecar.adjudicate_prayer` deterministically returns granted/cryptic/ignored/punished by god + standing + content (`_test_prayer_adjudication`).
- `PrayerService.pray` applies the right effects (opposing-god boons impede the descent; the 外神's favor feeds the gate; punishment spikes pressures and can strike the player down), tracks per-god standing, logs `player_prayer`, and persists standing (`_test_prayer_service`).
- GDScript and Python adjudicators agree across the fixture battery (`_test_prayer_parity_with_sidecar`).
- Full suite green; boots clean. **No API keys ever enter the engine** — adjudication is local/deterministic; the LLM path stays quarantined in the sidecar.
