extends Node
## The Sequence-progression authority (autoload singleton `Progression`) — direction v2 §6.
##
## Progression IS the LotM Sequence system: a run picks a PATHWAY (named by its Seq 0 — the slice
## ships the **Hunter** build) and starts at that pathway's **Sequence 9** rank, then climbs the
## 9 → 8 → 7 ladder. Each promotion is the canonical advance LOOP, not a bought skill node:
##
##     hunt a same-pathway Beyonder  ->  harvest the Characteristic that drops from the kill
##       ->  DIGEST it via the "acting" ritual (a DeedRunner deed the player performs)
##       ->  advance() : consume the Characteristic, raise the rank, SPIKE Madness (+35),
##           and GROW the Hunter kit (a new data ability row unlocks on the player's form).
##
## This node owns three run-scoped facts and nothing else: the current `_pathway`, the current
## `_seq` rank, and the per-run set of `_granted_arts` (the abilities the ladder has unlocked so
## far this run). It is PURE where it can be — can_advance() reads state and mutates nothing; the
## drop listener and advance() are the only writers.
##
## Engine-neutral (the §6 constraint): a Beyonder's pathway is DATA on the Agent (`agent.pathway`,
## hydrated from npcs.json), never an NPC-identity branch. The Characteristic economy keys entirely
## off that field — a downed agent drops `<pathway>_characteristic` when it carries a pathway, else
## the generic/sellable `tainted_characteristic` (the off-pathway butcher's drop, §3). advance()
## then requires a characteristic that matches the PLAYER's pathway, so "which monster do I hunt"
## is a build decision.
##
## Run lifecycle (§8 — NO cross-run stat inheritance): reset() is the run-start seam RunManager
## calls; to_dict()/from_dict() snapshot the rank + granted arts so progress CARRIES within a run
## (across a nightly checkpoint restore) but a fresh run is byte-identical to Seq 9. Determinism:
## progression never touches an in-flight fight — the kit grows BETWEEN fights (advance is out of
## combat), so a duel's transcript is identical regardless of the player's rank (the §f guard).

signal advanced(pathway: String, sequence: int)

## The slice's default pathway (direction v2 §6: Hunter is the vertical-slice build).
const DEFAULT_PATHWAY: String = "hunter"
## The ladder bookends for the slice. A pathway starts at Seq 9 (the low rank) and the demo climbs
## to Seq 7 (Pyromaniac). Lower numbers are higher rank; 9 -> 8 -> 7. TUNING — the slice cap.
const START_SEQUENCE: int = 9
const MIN_SEQUENCE: int = 7   # the slice ladder caps here (post-slice ladders go lower)

## The item id an acting-ritual deed row lives under (data/deeds.json). Progression asks DeedRunner
## to fire this on demand as the digestion's "acting" step.
const ACTING_DEED_ID: String = "hunter_act_predator"

## The Madness spike on a digest/advance (direction v2 §4/§6 — ingesting a Characteristic +35).
## The canonical value lives in Meters (MADNESS_DIGEST); mirrored here only as the fallback when the
## Meters autoload is somehow absent. TUNING — placeholder.
const DIGEST_MADNESS_SPIKE: float = 35.0

## The pathway kit-growth table (direction v2 §6 "kit honesty"): reaching a Sequence rank UNLOCKS
## the named ability on that pathway's kit. Data-authored as a per-pathway {rank -> ability id}
## map — the engine reads it, no ability-name branch. The slice authors only the Hunter 8/7 rows
## (mark_prey / incendiary_round); Fool/Hermit ladders slot in here post-slice with no code change.
const LADDER_UNLOCKS: Dictionary = {
	"hunter": {
		8: "mark_prey",         # Seq 8 Provoker: a tracking/first-strike mark (effect class)
		7: "incendiary_round",  # Seq 7 Pyromaniac: a stronger revolver variant with a burn
	},
	# M28 — the HERMIT ladder (direction v2 §6: astrology/ritual/knowledge), mirroring the Hunter's shape.
	"hermit": {
		8: "astral_chains",     # Seq 8: the binding-stun control art (mirrors the Hunter's mark_prey)
		7: "collapsing_star",   # Seq 7: the star/ritual AoE payoff (mirrors incendiary_round)
	},
}

## M28 — the acting-ritual deed id PER PATHWAY (direction v2 §6): each pathway digests its Characteristic
## by ACTING its role (the Hunter stalks as a predator; the Hermit works the star-rite). Data keyed by
## pathway string (engine-neutral, no NPC/id branch); ACTING_DEED_ID is the Hunter default/fallback for
## a pathway with no authored acting deed. perform_acting_deed()/acting_deed_id() route through this.
const ACTING_DEEDS: Dictionary = {
	"hunter": "hunter_act_predator",
	"hermit": "hermit_act_rite",
}

## M26 BALANCE RETUNE #1 — the sell-fork PITY MARGIN, authored in data/scenario.json's `progression`
## block (engine-neutral, no NPC-id branch). The slice stages exactly (START_SEQUENCE - MIN_SEQUENCE)
## same-pathway meals for that many advances, so selling a hunter_characteristic USED to be a hard trap
## (sell one -> can never reach the cap). The pity latches a small, per-run-capped make-up supply of
## advance fuel WHEN THE PLAYER SELLS fuel — so "sell one and still advance" has margin — without ever
## letting the pity be re-sold (it is consumed only inside advance()). Loaded once, static (identity
## data), same pattern as Shop/AmmoSpawn.
const SCENARIO_PATH := "res://data/scenario.json"
static var PROGRESSION_CFG: Dictionary = _load_progression_cfg()

static func _load_progression_cfg() -> Dictionary:
	if not FileAccess.file_exists(SCENARIO_PATH):
		return {}
	var parsed: Variant = JSON.parse_string(FileAccess.get_file_as_string(SCENARIO_PATH))
	if not (parsed is Dictionary):
		return {}
	var block: Variant = (parsed as Dictionary).get("progression", {})
	return block if block is Dictionary else {}

## Is the sell-fork pity margin enabled (data flag; default OFF -> the raw trap)?
func pity_on_sell() -> bool:
	return bool(PROGRESSION_CFG.get("pity_fuel_on_sell", false))

## The per-run cap on pity fuel granted (the margin size; default 1 = "you may sell ONE and still climb").
func pity_cap() -> int:
	return int(PROGRESSION_CFG.get("pity_fuel_cap", 1))

var _pathway: String = DEFAULT_PATHWAY
var _sequence: int = START_SEQUENCE
## M26 RETUNE #1: pity advance-fuel currently available (grown by selling fuel, consumed by advance()),
## and the running total granted this run (clamped to pity_cap so selling BOTH meals still forfeits).
var _pity_fuel: int = 0
var _pity_granted: int = 0
## The abilities unlocked so far THIS run (a flat list, in unlock order) — grown by advance(),
## wiped by reset(). AbilityDB.kit_for("player") appends these to the base player kit, so the
## growth reaches every consumer (PlayerCombat's primary-attack pick, the ammo/cooldown HUD).
var _granted_arts: Array = []
## Whether the acting ritual has been performed for the CURRENT pending advance. Set by
## perform_acting_deed()/mark_deed_done(); cleared on a successful advance (each advance needs its
## own acting) and on reset(). Round-trips through the snapshot so a reload mid-digestion-night
## doesn't silently drop the ritual the player already did.
var _deed_done: bool = false

# --- read (pure) ------------------------------------------------------------------------------
func pathway() -> String:
	return _pathway

func sequence() -> int:
	return _sequence

## The abilities the ladder has unlocked this run (a copy — read-only view).
func granted_arts() -> Array:
	return _granted_arts.duplicate()

## A legible label for the HUD, e.g. "Hunter · Seq 9". Display-only.
func label() -> String:
	return "%s · Seq %d" % [_pathway.capitalize(), _sequence]

# --- run-start pathway pick (M27 — reads the persistent meta unlocks) --------------------------
## Hunter is ALWAYS available (the slice baseline build), regardless of meta state.
const BASE_PATHWAYS: Array = ["hunter"]

## The pathways the player may PICK at run start: the base set + whatever the persistent meta has
## unlocked (read from RunManager._meta.unlocked_pathways — e.g. "fool" after the first win, M27).
## Engine-neutral: the unlock is a DATA flag in the meta slot, never an NPC/id branch. Hunter is
## always here; Fool appears only once a win has written it into the meta unlocks.
func available_pathways() -> Array:
	var out: Array = BASE_PATHWAYS.duplicate()
	var rm := _al("RunManager")
	if rm != null and rm.has_method("meta_unlocked_pathways"):
		for p in rm.meta_unlocked_pathways():
			var ps := String(p)
			if not out.has(ps):
				out.append(ps)
	return out

func pathway_available(id: String) -> bool:
	return available_pathways().has(id)

## Choose the run's pathway at run start, HONORING the meta unlock: an unlocked pathway id is
## accepted; a locked/unknown id falls back to the slice default (Hunter). Returns the pathway set.
## This is the META READ side of M27 — the unlock a win wrote becomes selectable the NEXT run.
##
## M27 SCOPE NOTE: unlocking Fool is a no-op-safe FLAG here — the Fool KIT (its ability rows / prey /
## acting deed) is a LATER milestone. Selecting it sets the pathway field so the pick honors the
## unlock, but grows no Fool-specific kit: LADDER_UNLOCKS has no "fool" table, so advance() simply
## unlocks no art on the Fool ladder (a clean stub) until that content lands.
func select_pathway(id: String) -> String:
	_pathway = id if pathway_available(id) else DEFAULT_PATHWAY
	return _pathway

## The ability id the NEXT rank would unlock for the current pathway ("" when the ladder authors
## none / the slice cap is reached). Pure — lets the HUD preview the next unlock.
func next_unlock() -> String:
	var target := _sequence - 1
	var table: Dictionary = LADDER_UNLOCKS.get(_pathway, {})
	return String(table.get(target, ""))

## Is this Characteristic item id usable for THIS pathway's advance? A same-pathway characteristic
## is `<pathway>_characteristic` (data convention). Pure.
func characteristic_item() -> String:
	return "%s_characteristic" % _pathway

# --- the acting ritual ------------------------------------------------------------------------
## Perform the "acting" deed (direction v2 §6): run the authored player deed through DeedRunner
## (the digestion's role-play step) and latch it as done for the pending advance. Returns the
## DeedRunner verdict. The generic acting-deed Madness RELIEF (-5, §4) is intentionally NOT applied
## here — this ritual is the toll-paying digestion step whose net effect on Madness is the +35
## spike advance() lands; the -5 relief is for ordinary daily acting, a separate call site.
func perform_acting_deed() -> Dictionary:
	var dr := _al("DeedRunner")
	var res: Dictionary = dr.perform_deed(acting_deed_id()) if dr != null else {"ok": true, "reason": ""}
	if bool(res.get("ok", false)):
		_deed_done = true
	return res

## The acting-ritual deed id for the CURRENT pathway (M28 — data-driven, ACTING_DEEDS; the Hunter's
## ACTING_DEED_ID is the fallback for a pathway with no authored acting deed). Pure.
func acting_deed_id() -> String:
	return String(ACTING_DEEDS.get(_pathway, ACTING_DEED_ID))

## Test/dev seam: mark the acting ritual as performed without walking DeedRunner (the harness uses
## this to arm an advance). The live path is perform_acting_deed().
func mark_deed_done() -> void:
	_deed_done = true

func deed_done() -> bool:
	return _deed_done

# --- advance gating (pure) --------------------------------------------------------------------
## Can the player advance right now? Returns {ok, reason}. Requires ALL of:
##   * not already at the slice cap (MIN_SEQUENCE);
##   * a SAME-pathway Characteristic carried in the player proxy's inventory;
##   * the acting ritual performed for this advance.
## Pure — reads inventory + latches, mutates nothing.
func can_advance() -> Dictionary:
	if _sequence <= MIN_SEQUENCE:
		return {"ok": false, "reason": "at_cap"}
	# M26 RETUNE #1: a carried Characteristic OR banked pity fuel (from a prior fuel sale) satisfies
	# the fuel requirement — this is what removes the sell-fork trap.
	if _player_characteristic_count() + _pity_fuel <= 0:
		return {"ok": false, "reason": "no_characteristic"}
	if not _deed_done:
		return {"ok": false, "reason": "no_acting_deed"}
	return {"ok": true, "reason": ""}

## Perform the digest -> advance (direction v2 §6). On success: consume ONE same-pathway
## Characteristic, raise the rank one rung (9 -> 8 -> 7), spike Madness (+35 via Meters), grow the
## kit (unlock the rank's authored art), clear the acting latch, and emit `advanced`. Refuses (no
## state change) when can_advance() is false. OUT OF COMBAT only — the caller gates on that; this
## never touches an in-flight fight (the kit grows between fights).
func advance() -> Dictionary:
	var gate := can_advance()
	if not bool(gate.get("ok", false)):
		return gate
	# (a) consume the fuel: a carried same-pathway Characteristic first, else a banked pity unit
	# (M26 RETUNE #1 — the pity is spent HERE, inside advance(), so it never lands in inventory to be
	# re-sold; that is what keeps the sell margin from becoming a coin farm).
	var proxy := _player_proxy()
	if proxy != null and proxy.item_count(characteristic_item()) > 0:
		proxy.remove_item(characteristic_item(), 1)
	elif _pity_fuel > 0:
		_pity_fuel -= 1
	# (b) raise the rank one rung.
	_sequence -= 1
	# (c) spike Madness — ingesting a Characteristic is the toll (§4/§6).
	var M := _al("Meters")
	if M != null:
		M.add_madness(M.MADNESS_DIGEST if "MADNESS_DIGEST" in M else DIGEST_MADNESS_SPIKE, "digest_advance")
	# (d) grow the kit: unlock the rank's authored art (if any), additive + de-duplicated.
	var table: Dictionary = LADDER_UNLOCKS.get(_pathway, {})
	var art := String(table.get(_sequence, ""))
	if art != "" and not _granted_arts.has(art):
		_granted_arts.append(art)
	# (e) each advance needs its own acting ritual.
	_deed_done = false
	advanced.emit(_pathway, _sequence)
	return {"ok": true, "reason": "", "sequence": _sequence, "unlocked": art}

## The abilities to APPEND to a form's base kit (AbilityDB.kit_for consults this). The Hunter growth
## rides the PLAYER form only (the player's own arts expand as they climb); no NPC form grows. This
## keeps the kit-growth seam engine-neutral and data-driven: AbilityDB owns the base kit, Progression
## owns the run's earned additions, and every kit consumer sees the union with no special-casing.
func kit_additions(form: String) -> Array:
	if form == "player":
		return _granted_arts.duplicate()
	return []

# --- Characteristic economy: the drop on a downed Beyonder ------------------------------------
func _ready() -> void:
	# A published `agent_downed` fact is the harvest trigger (direction v2 §6): a downed Beyonder
	# drops its Characteristic on the ground where it fell. Idempotent connect across world swaps.
	var eb := _al("EventBus")
	if eb != null and not eb.event_logged.is_connected(_on_event):
		eb.event_logged.connect(_on_event)

## Drop the Characteristic of a downed agent onto the ground (RoomItems), keyed purely off the
## agent's `pathway` DATA: a pathway-tagged Beyonder drops `<pathway>_characteristic`; an untagged
## (off-pathway/mundane) agent drops the generic `tainted_characteristic`. No id branch — the same
## rule handles the Hunter foe and the off-pathway butcher. Deterministic; the player HARVESTS by
## picking it up (RoomItems.take_near / the standard gather), reusing the existing pickup path.
func _on_event(ev: Dictionary) -> void:
	var etype := String(ev.get("type", ""))
	if etype == "harvest_sold":
		_on_harvest_sold(ev.get("data", {}) if ev.get("data") is Dictionary else {})
		return
	if etype != "agent_downed":
		return
	var data: Dictionary = ev.get("data", {}) if ev.get("data") is Dictionary else {}
	var target_id := String(data.get("target", ""))
	if target_id == "" or target_id == "player":
		return   # the player proxy going down is a run event, not a harvestable Beyonder
	var reg := _al("Agents")
	var agent: Agent = reg.get_agent(target_id) if reg != null else null
	if agent == null:
		return
	var drop := drop_for_pathway(String(agent.pathway))
	var ri := _al("RoomItems")
	if ri != null and drop != "":
		ri.place(agent.room, drop, agent.position, 1, true)

## M26 RETUNE #1: the pity-margin trigger. When the shop reports a harvest sale that INCLUDES this
## pathway's advance fuel (a hunter_characteristic sold at Franky's), latch up to the per-run cap of
## make-up "pity" fuel — so selling one fuel for coin no longer forfeits the climb. Engine-neutral:
## keyed purely off the fuel item id + the authored data flag, never who sold it. Selling BEYOND the
## cap grants nothing more, so cashing in BOTH meals' fuel still forfeits (the choice keeps its teeth).
func _on_harvest_sold(data: Dictionary) -> void:
	if not pity_on_sell():
		return
	var sold: Dictionary = data.get("sold", {}) if data.get("sold") is Dictionary else {}
	var fuel := characteristic_item()
	if not sold.has(fuel):
		return
	var qty_sold := int((sold[fuel] as Dictionary).get("qty", 0)) if sold[fuel] is Dictionary else 0
	if qty_sold <= 0:
		return
	var grant: int = mini(qty_sold, maxi(0, pity_cap() - _pity_granted))
	if grant > 0:
		_pity_fuel += grant
		_pity_granted += grant

## The Characteristic item id a downed agent of `foe_pathway` drops (pure): a tagged pathway drops
## `<pathway>_characteristic`; an empty/off-pathway tag drops the generic sellable one. Data
## convention, no id branch — a Fool/Death foe drops fool_/death_characteristic with zero code change.
func drop_for_pathway(foe_pathway: String) -> String:
	if foe_pathway == "":
		return "tainted_characteristic"
	return "%s_characteristic" % foe_pathway

# --- run lifecycle (§8) -----------------------------------------------------------------------
## Scrub to run-start — the seam RunManager.reset()/start_run() calls so a fresh run is byte-
## identical to the very first (Hunter · Seq 9, no granted arts, no pending deed). NO cross-run
## inheritance: the granted arts and rank do NOT survive a new run.
func reset() -> void:
	_pathway = DEFAULT_PATHWAY
	_sequence = START_SEQUENCE
	_granted_arts.clear()
	_deed_done = false
	# M26 RETUNE #1: a fresh run's pity margin is clean (no cross-run carry of a spent/earned pity).
	_pity_fuel = 0
	_pity_granted = 0

func to_dict() -> Dictionary:
	return {
		"pathway": _pathway,
		"sequence": _sequence,
		"granted_arts": _granted_arts.duplicate(),
		"deed_done": _deed_done,
		# M26 RETUNE #1: the pity margin rides the nightly checkpoint (a mid-run reload keeps whatever
		# margin the player earned by selling, and its per-run cap accounting).
		"pity_fuel": _pity_fuel,
		"pity_granted": _pity_granted,
	}

func from_dict(d: Dictionary) -> void:
	_pathway = String(d.get("pathway", _pathway))
	_sequence = int(d.get("sequence", _sequence))
	_granted_arts = (d.get("granted_arts", []) as Array).duplicate()
	_deed_done = bool(d.get("deed_done", _deed_done))
	_pity_fuel = int(d.get("pity_fuel", _pity_fuel))
	_pity_granted = int(d.get("pity_granted", _pity_granted))

# --- internals --------------------------------------------------------------------------------
func _player_proxy() -> Agent:
	var reg := _al("Agents")
	return reg.get_agent(reg.PLAYER_ID) if reg != null else null

func _player_characteristic_count() -> int:
	var proxy := _player_proxy()
	return proxy.item_count(characteristic_item()) if proxy != null else 0

## Autoload lookup via /root (class_name-safe under the headless -s harness), tolerant of absence.
func _al(autoload_name: String) -> Node:
	var ml := Engine.get_main_loop()
	if ml == null or not (ml is SceneTree):
		return null
	return (ml as SceneTree).root.get_node_or_null(autoload_name)
