extends Area2D
## A world object the player can examine, a person they can talk to, or a door that
## loads another scene.
##
## Shows a floating prompt while the player is nearby. On `interact`:
##   - if `dialogue_id` is set  -> opens that dialogue tree
##   - else if `target_scene`   -> requests a scene transition
##   - else                     -> surfaces an internal-thought line
## In the examine case, if `clue_id` is set the clue is collected (once).

@export_multiline var thought: String = ""
@export var prompt_text: String = "Examine"
@export var tint: Color = Color.WHITE
## Optional real art; when set it replaces the placeholder tint-square and is feet-anchored.
@export var icon: Texture2D
## Target on-screen height in pixels for the icon art.
@export var icon_px: float = 56.0
@export_file("*.tscn") var target_scene: String = ""
@export var lead_on_use: String = ""
## When true, interacting strips one gathered ingredient from the cult's rite cache instead of
## examining/talking/transitioning — the warehouse "spoil the cache" point the player walks up to.
@export var sabotage_cache: bool = false
## Clue collected on first examine (must match an id in data/clues.json).
@export var clue_id: String = ""
## NPC dialogue tree to open (must match a key in data/dialogue.json).
@export var dialogue_id: String = ""
## When set, LEFT-CLICKING this object opens the matching Agent's inspect card
## (WorldState.inspect_requested -> CharacterCard) — surfaces the agent's goal + live thought.
@export var agent_id: String = ""
## When true, interacting (E) toggles the host room's RoomState (normal <-> 失控), via the
## node in group "room_state". Used by the in-room ritual trigger in Old Neil's home.
@export var room_state_toggle: bool = false
## M7 Ritual Night: when true, interacting is the ALTAR INTERRUPT (break the altar / destroy the
## vessel) — it flips RitualNight's interrupt flag, triggering the backlash wave -> the WIN path.
## Inert (a bare examine) when no Ritual Night is active.
@export var ritual_interrupt: bool = false
## M15 Franky's shop: when true, interacting SELLS every carried item in the authored sell table
## (Shop.sell_harvest — characteristics out, coin in). Generic flag, same pattern as
## ritual_interrupt: prices and the coin item are data (scenario.json `shop`), no NPC-id branch.
@export var shop_sell_harvest: bool = false
## M15: when true, interacting BUYS one box of rounds at the authored price (Shop.buy_ammo) —
## coin-costed and stock-latched per run (never a free infinite tap). With BOTH shop flags set the
## use is sell-then-buy in one stop, so a fresh harvest can fund the round box on the spot.
@export var shop_buy_ammo: bool = false
## M32: when true, interacting BUYS one COUNTER-RITE ingredient (Shop.buy_ingredient) — coin from the
## player proxy purse, the ingredient delivered into the ritual Inventory the counter-rite reads. This
## is the LIVE source that makes the anti-Doom rite reachable at Franky's (no longer locked behind the
## cult supply cache alone). Generic flag, same pattern as shop_buy_ammo; the item id it stocks is DATA
## (`shop_ingredient_item`, matched against the authored ingredient_prices table), no NPC-id branch.
@export var shop_buy_ingredient: bool = false
## M32: the counter-rite ingredient this shelf stocks (an item id in the shop's authored ingredient
## table — Shop.ingredient_prices). Carried on the flag because Shop.buy_ingredient needs one; a bare
## examine when empty. Content is data (set per-node in the scene), no id literal in engine logic.
@export var shop_ingredient_item: String = ""
## B2 (M20): when true, interacting is the DIGEST/ADVANCE ritual — the live caller for the core
## RPG loop (§6). It performs the acting ritual (arming the digest) if the player hasn't yet, then
## calls Progression.advance(): consume a same-pathway Characteristic, raise the Sequence rank, spike
## Madness (+35), grow the kit. Generic flag, same pattern as ritual_interrupt/shop_* — no NPC-id
## branch; the pathway/characteristic economy is all data. Inert (a bare thought) when the player
## can't advance (no Characteristic carried, or already at the slice cap).
@export var digest_advance: bool = false
## B2 (M20): when true, interacting performs a daily ACTING DEED — the live caller for the Madness
## REST-of-the-cycle deed sink (§4, -5, capped 3/day via Meters.try_relieve_madness_deed). Playing
## your Sequence's role in the world quiets the whispers. Generic flag; no NPC-id branch.
@export var acting_deed: bool = false

@onready var _prompt: Label = $Prompt
@onready var _sprite: Sprite2D = $Sprite2D

var _player_near: bool = false

## M35 AFFORDANCE: highlight STATE — true while the player stands near (the same _player_near seam that
## shows the Examine label). A headless-observable flag (is_highlighted()); the live-only glow/bob below
## rides it so an interactable is distinguishable at a glance, not just by the floating "Examine" text.
var _highlighted: bool = false
## The sprite's resting look, captured after _ready sets it — the base the live bob/glow lerps from and
## restores to on exit (so the affordance never leaves a permanently shifted/brightened sprite).
var _base_modulate: Color = Color.WHITE
var _base_sprite_pos: Vector2 = Vector2.ZERO
var _bob_t: float = 0.0
const _BOB_SPEED: float = 5.0     # rad/s — a gentle hover
const _BOB_AMP: float = 4.0       # px of lift at the top of the bob
const _GLOW_LIFT: float = 0.35    # peak brightness added on the pulse (cosmetic)

func _ready() -> void:
	if icon:
		_sprite.texture = icon
		_sprite.texture_filter = CanvasItem.TEXTURE_FILTER_NEAREST
		_sprite.modulate = Color.WHITE
		var h := float(icon.get_height())
		var s: float = icon_px / h if h > 0.0 else 1.0
		_sprite.scale = Vector2(s, s)
		_sprite.offset = Vector2(0, -h * 0.5)   # feet-anchor for Y-sort
	else:
		_sprite.modulate = tint
	_prompt.text = prompt_text
	_prompt.visible = false
	_base_modulate = _sprite.modulate
	_base_sprite_pos = _sprite.position
	# The glow/bob is purely cosmetic and LIVE-ONLY: under --headless there is no per-frame visual work
	# at all (the highlight STATE still flips for logic/tests). Keeps every deterministic harness clean.
	set_process(_is_live())
	body_entered.connect(_on_body_entered)
	body_exited.connect(_on_body_exited)
	if agent_id != "":
		input_pickable = true
		input_event.connect(_on_input_event)

## The affordance STATE: true while the player is near (drives the live glow/bob). Headless-observable.
func is_highlighted() -> bool:
	return _highlighted

func _on_body_entered(body: Node) -> void:
	if body.is_in_group("player"):
		_player_near = true
		_prompt.visible = true
		_highlighted = true

func _on_body_exited(body: Node) -> void:
	if body.is_in_group("player"):
		_player_near = false
		_prompt.visible = false
		_highlighted = false
		_clear_highlight_visual()

## LIVE-ONLY subtle affordance: while highlighted, a gentle upward bob + a brightness pulse so the object
## reads as interactive at a glance. State-gated (an idle interactable does nothing), never runs headless
## (set_process(false) there). Pure cosmetic — mutates only this node's own sprite transform/modulate.
func _process(delta: float) -> void:
	if not _highlighted:
		return
	_bob_t += delta
	var wave := 0.5 + 0.5 * sin(_bob_t * _BOB_SPEED)   # 0..1
	_sprite.position = _base_sprite_pos + Vector2(0.0, -_BOB_AMP * wave)
	var g := 1.0 + _GLOW_LIFT * wave
	_sprite.modulate = Color(_base_modulate.r * g, _base_modulate.g * g, _base_modulate.b * g, _base_modulate.a)

## Restore the sprite's resting look when the player leaves (idempotent; safe headless).
func _clear_highlight_visual() -> void:
	_bob_t = 0.0
	if _sprite != null:
		_sprite.position = _base_sprite_pos
		_sprite.modulate = _base_modulate

## True only with a real display (live play); false under --headless (the CombatFeedback._is_live pattern).
func _is_live() -> bool:
	return DisplayServer.get_name() != "headless"

## Left-click while `agent_id` is set: open that agent's inspect card (its goal + thought).
func _on_input_event(_viewport: Node, event: InputEvent, _shape_idx: int) -> void:
	if event is InputEventMouseButton and event.button_index == MOUSE_BUTTON_LEFT and event.pressed:
		WorldState.inspect_requested.emit(agent_id)

func _unhandled_input(event: InputEvent) -> void:
	if not _player_near:
		return
	if event.is_action_pressed("interact"):
		_use()
		get_viewport().set_input_as_handled()

func _use() -> void:
	if room_state_toggle:
		var rs: Node = get_tree().get_first_node_in_group("room_state")
		if rs and rs.has_method("toggle"):
			rs.toggle()
		return
	if ritual_interrupt:
		_interrupt_ritual()
		return
	if sabotage_cache:
		_sabotage_rite_cache()
		return
	if shop_sell_harvest or shop_buy_ammo:
		_use_shop_counter()
		return
	if shop_buy_ingredient:
		_use_ingredient_counter()
		return
	if digest_advance:
		_digest_advance()
		return
	if acting_deed:
		_perform_acting_deed()
		return
	if dialogue_id != "":
		DialogueManager.start(dialogue_id)
		return
	if target_scene != "":
		SceneFade.go(target_scene, lead_on_use)
		return
	if clue_id != "":
		ClueDB.collect(clue_id)
	if thought != "":
		WorldState.thought_requested.emit(thought)
	if lead_on_use != "":
		WorldState.set_lead(lead_on_use)

## M7 Ritual Night: break the altar / destroy the vessel.
##   * If a Ritual Night is already LIVE (Doom-100 fill or an early assault already begun) this is the
##     interrupt WIN input — flip RitualNight's interrupt flag (triggering the backlash wave).
##   * If NO climax is live yet (M9 Gap 1), reaching the crypt altar early is the player's "storm the
##     rite" verb (§13 #7): force-assault the site NOW rather than waiting ~7 days for Doom to fill.
##     Gated on a LIVE run and an unresolved climax so a post-win examine stays a bare look.
func _interrupt_ritual() -> void:
	var rn: Node = get_tree().root.get_node_or_null("RitualNight")
	if rn == null:
		WorldState.thought_requested.emit("The altar sits cold. Nothing is happening here yet.")
		return
	# Climax already underway -> the interrupt WIN input (down the rite).
	if rn.has_method("active") and rn.active() and rn.has_method("use_interrupt_interactable"):
		rn.use_interrupt_interactable()
		WorldState.thought_requested.emit("I smash the vessel — the circle's light gutters and the faithful start to come apart.")
		return
	# No climax yet -> STORM THE RITE early (the promised player verb into the climax, M9 Gap 1).
	var already_resolved: bool = rn.has_method("resolved") and bool(rn.resolved())
	var run_live: bool = RunManager != null and bool(RunManager.run_active())
	if run_live and not already_resolved and rn.has_method("force_assault"):
		var seed_val := 0
		var wm: Node = get_tree().root.get_node_or_null("WorldManager")
		if wm != null and "seed_value" in wm:
			seed_val = int(wm.seed_value)
		rn.force_assault(true, seed_val, "front")
		WorldState.thought_requested.emit("No more waiting. I storm the crypt — the faithful turn from the altar, and the descent's fuse is lit.")
		return
	WorldState.thought_requested.emit("The altar sits cold. Nothing is happening here yet.")

## M15 Franky's counter: auto-transact through the Shop autoload's data verbs — SELL the whole
## carried harvest first (so a fresh characteristic can fund the round box on the spot), then BUY
## one box of rounds if that flag is set too. No menu (the slice keeps interaction simple); every
## price is authored data, and the narration stays generic (no NPC-id/content literal here).
func _use_shop_counter() -> void:
	var shop: Node = get_tree().root.get_node_or_null("Shop")
	if shop == null:
		WorldState.thought_requested.emit("The counter is unattended.")
		return
	var lines: Array = []
	if shop_sell_harvest:
		var s: Dictionary = shop.sell_harvest()
		if bool(s.get("ok", false)):
			lines.append("Sold what I was carrying for %d coin." % int(s.get("coins", 0)))
	if shop_buy_ammo:
		var b: Dictionary = shop.buy_ammo()
		if bool(b.get("ok", false)):
			lines.append("Bought %d rounds for %d coin." % [int(b.get("qty", 0)), int(b.get("cost", 0))])
		elif String(b.get("reason", "")) == "no_coin":
			lines.append("Not enough coin left for a box of rounds.")
		elif String(b.get("reason", "")) == "out_of_stock":
			lines.append("The round shelf is bare — nothing more to buy this run.")
	if lines.is_empty():
		lines.append("Nothing on me worth selling, and no trade to make.")
	WorldState.thought_requested.emit(" ".join(lines))

## M32 Franky's ingredient shelf: BUY one counter-rite ingredient through the Shop autoload's data verb
## (Shop.buy_ingredient) — coin debited from the player proxy, the ingredient delivered into the ritual
## Inventory the counter-rite reads. The item id is authored on this node (shop_ingredient_item), same
## generic pattern as shop_buy_ammo; the price is data (scenario.json shop.buy_ingredients), no NPC-id
## branch. Narration stays generic. This is the LIVE seam that makes the anti-Doom rite reachable in play.
func _use_ingredient_counter() -> void:
	var shop: Node = get_tree().root.get_node_or_null("Shop")
	if shop == null or not shop.has_method("buy_ingredient"):
		WorldState.thought_requested.emit("The counter is unattended.")
		return
	var r: Dictionary = shop.buy_ingredient(shop_ingredient_item)
	if bool(r.get("ok", false)):
		WorldState.thought_requested.emit(
			"Bought %s for %d coin — the makings of a warding rite." % [String(r.get("item", "")).replace("_", " "), int(r.get("cost", 0))])
		return
	match String(r.get("reason", "")):
		"no_coin":
			WorldState.thought_requested.emit("Not enough coin for that.")
		"inventory_full":
			WorldState.thought_requested.emit("No room to carry more of that.")
		"unknown_item":
			WorldState.thought_requested.emit("They don't stock that here.")
		_:
			WorldState.thought_requested.emit("No trade to make here.")

## B2 (M20): the DIGEST/ADVANCE ritual — the live caller for the §6 advance loop. Performs the
## acting ritual (arming this digest) if it isn't yet armed, then calls Progression.advance(): the
## same-pathway Characteristic is consumed, the Sequence rank rises, Madness spikes (+35), and the
## kit grows. Narrates the outcome as an internal thought (the built M3 seam). Engine-neutral — the
## whole pathway/characteristic economy is data in Progression; nothing here names a pathway or id.
func _digest_advance() -> void:
	var prog: Node = get_tree().root.get_node_or_null("Progression")
	if prog == null:
		WorldState.thought_requested.emit("Nothing to digest here.")
		return
	# Arm the acting ritual for this digest if the player hasn't already performed it (the digestion's
	# "acting" step, §6). perform_acting_deed() runs the authored player deed and latches it.
	if not prog.deed_done():
		prog.perform_acting_deed()
	var res: Dictionary = prog.advance()
	if bool(res.get("ok", false)):
		WorldState.thought_requested.emit(
			"I take the Characteristic into myself. It burns — and I rise. (%s)" % String(prog.label()))
		return
	match String(res.get("reason", "")):
		"no_characteristic":
			WorldState.thought_requested.emit("I have nothing of my own pathway to digest yet. Hunt first.")
		"at_cap":
			WorldState.thought_requested.emit("I've climbed as far as this act of the story allows.")
		_:
			WorldState.thought_requested.emit("The digestion won't take — not yet.")

## B2 (M20): a daily ACTING DEED — the live Madness rest-of-cycle sink (§4, -5, 3/day). Routes
## through Meters.try_relieve_madness_deed() which owns the per-day cap. Narrates the result.
func _perform_acting_deed() -> void:
	var m: Node = get_tree().root.get_node_or_null("Meters")
	if m == null:
		return
	var res: Dictionary = m.try_relieve_madness_deed()
	if bool(res.get("ok", false)):
		var left: int = m.deed_relief_remaining_today() if m.has_method("deed_relief_remaining_today") else 0
		WorldState.thought_requested.emit(
			"I play my part on the beat — a Hunter's role, acted true. The whispers ebb. (%d more today)" % left)
	else:
		WorldState.thought_requested.emit("I've acted my part enough today; the whispers won't quiet further.")

## Strip one gathered ingredient from the cult's rite cache (PlayerActions.sabotage_any) and
## narrate the result, so the player feels the rite set back. When the cache is already bare the
## prompt still works but reports there is nothing left to spoil.
func _sabotage_rite_cache() -> void:
	var stripped := PlayerActions.sabotage_any()
	if stripped != "":
		WorldState.thought_requested.emit(
			"I scattered their %s. The rite will have to gather it again." % stripped.replace("_", " "))
	else:
		WorldState.thought_requested.emit("Nothing left here worth spoiling — the cache is bare.")
