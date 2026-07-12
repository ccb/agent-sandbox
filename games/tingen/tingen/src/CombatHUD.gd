extends Control
## Combat widgets on the persistent HUD (combat plan §M5): hp + stamina bars, the carried
## weapon's rounds counter (resolved through the ITEM system — no built-in ammo pool),
## dash/charm cooldown pips, and the enemy cast-telegraph indicator (the GDD's
## readable-telegraph promise). Pure read-out — nothing here mutates combat state.
##
## Bindings: hp reads the PLAYER PROXY agent (Agents "player" — the one hp authority);
## ammo + cooldown pips + the M31 spirituality (mana) bar read the live PlayerCombat node
## (group "player_combat"); stamina reads the Player body's existing pool (group "player").
## Values are polled in _process
## (heals have no event) AND refreshed immediately on an agent_attacked that names the
## player, so a landed hit reads the same frame.
##
## The telegraph indicator listens to ability_cast_started on the EventBus but shows a cast
## ONLY when the PLAYER'S PROXY could perceive the caster through the ONE shared gate
## (Perception.can_perceive — same room + within the proxy's vision_r): an out-of-room or
## beyond-vision wind-up shows NOTHING. It clears on cast_finished/interrupted (a wall-clock
## expiry is the UI-only safety net). The player's own casts never alarm the HUD.

@onready var _hp: ProgressBar = $Vitals/Hp/Bar
@onready var _stamina: ProgressBar = $Vitals/Stamina/Bar
@onready var _spirit: ProgressBar = $Vitals/Spirit/Bar
@onready var _ammo: Label = $Vitals/Ammo/Value
@onready var _dash: ProgressBar = $Vitals/Pips/DashBar
@onready var _charm: ProgressBar = $Vitals/Pips/CharmBar
@onready var _telegraph: Label = $Telegraph

## Live perceivable enemy wind-ups: caster id -> {text, until_ms (wall clock, UI net only)}.
var _telegraphs: Dictionary = {}
## M13: ammo-label empty pulse — seconds remaining for the red "empty" modulate on the ammo label.
var _ammo_empty_t: float = 0.0
const _AMMO_EMPTY_DURATION: float = 0.4
const _AMMO_EMPTY_COLOR: Color = Color(0.95, 0.25, 0.25)
## M34: Spirit-bar empty pulse — seconds remaining for the red "spent" modulate on the Spirit bar (the
## spirit counterpart to the ammo-label pulse). The Spirit bar is a ProgressBar with its own theme tint,
## so it pulses via `modulate` and RESTORES to that captured base tint (never clobbered to white).
var _spirit_empty_t: float = 0.0
var _spirit_base_modulate: Color = Color.WHITE
const _SPIRIT_EMPTY_DURATION: float = 0.4
const _SPIRIT_EMPTY_COLOR: Color = Color(0.95, 0.25, 0.25)

func _ready() -> void:
	_telegraph.visible = false
	# M34: remember the Spirit bar's normal theme tint so the empty-pulse restores it (not white).
	_spirit_base_modulate = _spirit.modulate
	var eb := get_node_or_null("/root/EventBus")
	if eb != null and not eb.event_logged.is_connected(_on_event):
		eb.event_logged.connect(_on_event)
	refresh()

func _process(delta: float) -> void:
	refresh()
	# M13: decay the ammo-label empty-pulse and restore normal color once it expires.
	if _ammo_empty_t > 0.0:
		_ammo_empty_t = maxf(0.0, _ammo_empty_t - delta)
		_ammo.add_theme_color_override("font_color", _AMMO_EMPTY_COLOR)
	else:
		_ammo.remove_theme_color_override("font_color")
	# M34: decay the Spirit-bar empty-pulse and restore the bar's normal tint once it expires (mirrors
	# the ammo-label pulse, on the Spirit ProgressBar via modulate).
	if _spirit_empty_t > 0.0:
		_spirit_empty_t = maxf(0.0, _spirit_empty_t - delta)
		_spirit.modulate = _SPIRIT_EMPTY_COLOR
	else:
		_spirit.modulate = _spirit_base_modulate

## Pull every widget's current value from its owner (idempotent; tests call it directly).
func refresh() -> void:
	var proxy := _proxy()
	if proxy != null:
		_hp.max_value = proxy.max_hp
		_hp.value = proxy.hp
	var pc: Node = get_tree().get_first_node_in_group("player_combat")
	# Rounds resolve through the ITEM system (PlayerCombat.ammo_count: the carried weapon
	# granting the kit's ammo-costing art -> its ammo_item's inventory count). -1 = nothing
	# resolves (e.g. no granting weapon carried) — there is nothing to count rounds FOR.
	var rounds: int = pc.ammo_count() if pc != null else -1
	_ammo.text = str(rounds) if rounds >= 0 else "—"
	_dash.value = (1.0 - pc.cooldown_frac("dash")) if pc != null else 0.0
	_charm.value = (1.0 - pc.cooldown_frac("paper_charm")) if pc != null else 0.0
	# M31: the spirituality pool (the Hermit's mana) — the PlayerCombat node owns it; read it exactly
	# like ammo/cooldowns (guarded on pc). A pure read-out; the HUD never mutates the pool.
	if pc != null:
		_spirit.max_value = pc.spirituality_max()
		_spirit.value = pc.spirituality_now()
	var pl: Node = get_tree().get_first_node_in_group("player")
	if pl != null and pl.get("stamina") != null:
		_stamina.max_value = float(pl.get("max_stamina"))
		_stamina.value = float(pl.get("stamina"))
	_prune_telegraphs(Time.get_ticks_msec())

func _on_event(ev: Dictionary) -> void:
	var d: Dictionary = ev.get("data", {}) if ev.get("data") is Dictionary else {}
	match String(ev.get("type", "")):
		"ability_cast_started":
			var caster_id := String(d.get("caster", ""))
			if caster_id == "" or caster_id == "player":
				return
			var reg := get_node_or_null("/root/Agents")
			var caster: Agent = reg.get_agent(caster_id) if reg != null else null
			var proxy := _proxy()
			if caster == null or proxy == null:
				return
			# The shared perceiver gate, from the PLAYER proxy's perspective.
			if not Perception.can_perceive(proxy, caster.room, caster.position):
				return
			var who := caster.display_name if caster.display_name != "" else caster_id
			var adb := get_node_or_null("/root/AbilityDB")
			var art := String(d.get("ability", ""))
			_telegraphs[caster_id] = {
				"text": "%s winds up %s!" % [who,
					adb.display_name(art) if adb != null else art.replace("_", " ")],
				"until_ms": Time.get_ticks_msec()
					+ int(round(float(d.get("cast_time", 0.0)) * 1000.0)) + 500,
			}
			_update_telegraph()
		"ability_cast_finished", "ability_cast_interrupted":
			if _telegraphs.erase(String(d.get("caster", ""))):
				_update_telegraph()
		"agent_attacked":
			if String(d.get("target", "")) == "player":
				refresh()
		"weapon_empty":
			# M13: the player fired dry — pulse the ammo label red so the player reads "out of ammo",
			# not "I took damage" (which is the full-screen hit-flash). Gated by hit_flash toggle via
			# the same Settings seam used by CombatFeedback (off -> no visual, but the event still fired).
			var s := get_node_or_null("/root/Settings")
			var flash_on: bool = s == null or bool(s.get_bool("hit_flash"))
			if flash_on:
				_ammo_empty_t = _AMMO_EMPTY_DURATION
		"spirit_empty":
			# M34: the player cast on an empty spirituality pool — pulse the Spirit bar red on its OWN
			# channel (distinct from the ammo pulse + the full-screen hit-flash), so a drained star-caster
			# reads "out of spirit". Gated by hit_flash via the same Settings seam (off -> no visual, but
			# the event still fired), exactly like the ammo pulse.
			var ss := get_node_or_null("/root/Settings")
			var spirit_flash_on: bool = ss == null or bool(ss.get_bool("hit_flash"))
			if spirit_flash_on:
				_spirit_empty_t = _SPIRIT_EMPTY_DURATION

func _update_telegraph() -> void:
	if _telegraphs.is_empty():
		_telegraph.visible = false
		_telegraph.text = ""
		return
	var last: Dictionary = _telegraphs[_telegraphs.keys().back()]
	_telegraph.text = String(last.get("text", ""))
	_telegraph.visible = true
	# M10: color the wind-up line from the active (colorblind-aware) palette.
	var s := get_node_or_null("/root/Settings")
	if s != null:
		_telegraph.add_theme_color_override("font_color", s.telegraph_color())

## UI safety net: a wind-up whose finish/interrupt event this HUD never saw still fades.
func _prune_telegraphs(now_ms: int) -> void:
	if _telegraphs.is_empty():
		return
	var changed := false
	for caster_id in _telegraphs.keys().duplicate():
		if now_ms >= int((_telegraphs[caster_id] as Dictionary).get("until_ms", 0)):
			_telegraphs.erase(caster_id)
			changed = true
	if changed:
		_update_telegraph()

func _proxy() -> Agent:
	var reg := get_node_or_null("/root/Agents")
	return reg.get_agent("player") if reg != null else null
