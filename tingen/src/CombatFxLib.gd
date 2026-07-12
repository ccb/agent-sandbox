class_name CombatFxLib
extends RefCounted
## Cosmetic FX resolver (combat plan §M1 — make a fight legible). The ONE place an ability's
## optional `fx`/`vfxId` id (or an event kind) maps to an orphaned art asset under assets/fx.
## PURELY COSMETIC: nothing here reads or writes combat/agent/world state — it only names files.
##
## Ability defs may carry an OPTIONAL `fx` (alias `vfxId`) string. An ability with no field, or
## one naming an asset that doesn't exist on disk, degrades to a real DEFAULT texture so every
## cast still shows SOMETHING (never a missing resource, never a hard error mid-fight).

const FX_DIR: String = "res://assets/fx/"
const FLIPBOOK_DIR: String = "res://assets/fx/flipbooks/"

## The fallbacks every unfielded/unknown lookup lands on — all guaranteed present on disk.
const DEFAULT_PROJECTILE: String = "bullet_tracer"
const DEFAULT_ZONE: String = "charm_glyph"
const DEFAULT_HIT: String = "hit_spark_1"
const DEFAULT_SPLATTER: String = "ichor_splatter_1"
const DEFAULT_DASH: String = "dash_afterimage_wisp"
const DEFAULT_TRANSFORM: String = "spark_burst"

## Read an ability def's optional cosmetic fx id (accepts either `fx` or `vfxId`), "" when unset.
## Type-guarded: a non-string `fx`/`vfxId` (int/array/dict/bool from malformed data) degrades to
## "" rather than throwing a `String` constructor error mid-resolve — the caller then defaults.
static func fx_id_of(ability: Dictionary) -> String:
	var v := _as_string(ability.get("fx", ""))
	if v == "":
		v = _as_string(ability.get("vfxId", ""))
	return v

## Coerce ONLY a real String; any other Variant (never a valid fx id) yields "". Guards against
## the `String(non_string)` constructor error the plain `String(...)` cast would raise.
static func _as_string(raw: Variant) -> String:
	return raw if raw is String else ""

## Map an fx id (a bare asset name, no dir/extension) to a texture path that EXISTS on disk.
## An empty or unknown id degrades to DEFAULT_PROJECTILE — always a real resource.
static func texture_path(fx_id: String, fallback: String = DEFAULT_PROJECTILE) -> String:
	for candidate in [fx_id, fallback, DEFAULT_PROJECTILE]:
		if String(candidate) == "":
			continue
		var p := _resolve(String(candidate))
		if p != "":
			return p
	return FX_DIR + DEFAULT_PROJECTILE + ".png"

## Try the flat fx dir first, then flipbooks; "" when the asset is absent.
static func _resolve(name: String) -> String:
	var flat := FX_DIR + name + ".png"
	if ResourceLoader.exists(flat):
		return flat
	var flip := FLIPBOOK_DIR + name + ".png"
	if ResourceLoader.exists(flip):
		return flip
	return ""

## Load a texture for an fx id (default-guarded), null only if even the default is missing.
static func texture_for(fx_id: String, fallback: String = DEFAULT_PROJECTILE) -> Texture2D:
	var path := texture_path(fx_id, fallback)
	return load(path) as Texture2D if ResourceLoader.exists(path) else null

# --- Flipbook animation (M10: the spark_burst boxy-panel fix) ---------------------------------
## The spark_burst source is a 1024^2 SHEET; drawn WHOLE it renders as an opaque boxy black panel.
## The fix keys the black background out (the *_keyed.png cutout) AND animates it per-frame so it
## reads as a burst, not a box. These constants describe that sheet's grid.
const SPARK_BURST_KEYED: String = "res://assets/fx/flipbooks/spark_burst_keyed.png"
const SPARK_BURST_GRID_COLS: int = 4
const SPARK_BURST_GRID_ROWS: int = 4
const SPARK_BURST_FPS: float = 24.0

## True when the alpha-keyed spark_burst cutout is present on disk (so the animated form is usable);
## false degrades the caller back to the flat still (never a hard error mid-fight).
static func has_keyed_spark_burst() -> bool:
	return ResourceLoader.exists(SPARK_BURST_KEYED)

## Build a SpriteFrames animation from the keyed spark_burst sheet — each grid cell becomes one
## AtlasTexture frame, so an AnimatedSprite2D plays the burst rather than drawing the whole sheet.
## Returns null when the keyed sheet is absent (caller falls back to the flat still).
static func spark_burst_frames() -> SpriteFrames:
	if not has_keyed_spark_burst():
		return null
	var sheet := load(SPARK_BURST_KEYED) as Texture2D
	if sheet == null:
		return null
	var cw := sheet.get_width() / SPARK_BURST_GRID_COLS
	var ch := sheet.get_height() / SPARK_BURST_GRID_ROWS
	var frames := SpriteFrames.new()
	frames.set_animation_speed("default", SPARK_BURST_FPS)
	frames.set_animation_loop("default", false)
	for gy in SPARK_BURST_GRID_ROWS:
		for gx in SPARK_BURST_GRID_COLS:
			var at := AtlasTexture.new()
			at.atlas = sheet
			at.region = Rect2(gx * cw, gy * ch, cw, ch)
			frames.add_frame("default", at)
	return frames
