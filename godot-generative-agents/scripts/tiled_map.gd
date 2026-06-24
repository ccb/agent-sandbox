extends TileMapLayer
## Generic renderer for a Tiled (.tmj) map whose tileset is a single packed
## image (no spacing) — e.g. the OSM campus maps baked with Kenney's CC0 RPG
## Urban tiles (`osm_to_tiled.py --theme urban`). Reads the JSON, loads the
## referenced sheet, registers every tile, and paints each layer by GID. This is
## the no-plugin equivalent of importing the same .tmj via the YATI addon, and it
## works for any single-image-tileset Tiled map, not just ours.

@export_file("*.tmj") var map_path: String = "res://maps/upenn_core_urban.tmj"

const SOURCE_ID := 0


func _ready() -> void:
	# Nearest filtering (no smoothing) is what pixel art wants; combined with the
	# texture padding below and the project's pixel-snap, it keeps tile edges
	# crisp and seam-free even when the camera zooms to a fractional scale.
	texture_filter = CanvasItem.TEXTURE_FILTER_NEAREST

	var f := FileAccess.open(map_path, FileAccess.READ)
	if f == null:
		push_error("tiled_map: cannot open %s" % map_path)
		return
	var tmj: Variant = JSON.parse_string(f.get_as_text())
	if typeof(tmj) != TYPE_DICTIONARY:
		push_error("tiled_map: %s is not valid Tiled JSON" % map_path)
		return

	var ts: Dictionary = tmj["tilesets"][0]
	var cols := int(ts["columns"])
	var first := int(ts["firstgid"])
	var tile_size := Vector2i(int(tmj["tilewidth"]), int(tmj["tileheight"]))

	# The tileset image sits next to the .tmj. Prefer the imported texture
	# (export-safe); fall back to reading the file directly if it isn't a project
	# resource.
	var img_path := map_path.get_base_dir().path_join(str(ts["image"]))
	var tex: Texture2D = load(img_path) if ResourceLoader.exists(img_path) else null
	if tex == null:
		var img := Image.load_from_file(img_path)
		if img != null:
			tex = ImageTexture.create_from_image(img)
	if tex == null:
		push_error("tiled_map: cannot load tileset image %s" % img_path)
		return

	tile_set = _build_tile_set(tex, tile_size, cols, int(ts["tilecount"]))
	_paint(tmj, cols, first)


func _build_tile_set(tex: Texture2D, tile_size: Vector2i, cols: int, count: int) -> TileSet:
	var t := TileSet.new()
	t.tile_size = tile_size
	var src := TileSetAtlasSource.new()
	src.texture = tex
	src.texture_region_size = tile_size
	# Pad each tile in the internal atlas by duplicating its edge pixels, so a
	# neighbouring tile in the packed sheet can never bleed in at the seams.
	src.use_texture_padding = true
	# Register every tile in the sheet so any GID in the map resolves.
	var rows := int(ceil(float(count) / cols))
	for r in rows:
		for c in cols:
			src.create_tile(Vector2i(c, r))
	t.add_source(src, SOURCE_ID)
	return t


func _paint(tmj: Dictionary, cols: int, first: int) -> void:
	var w := int(tmj["width"])
	for layer in tmj.get("layers", []):
		if layer.get("type", "") != "tilelayer":
			continue
		var data: Array = layer.get("data", [])
		var painted := 0
		for i in data.size():
			var gid := int(data[i])
			if gid == 0:
				continue
			var ti := gid - first  # tile index within the sheet
			set_cell(Vector2i(i % w, i / w), SOURCE_ID, Vector2i(ti % cols, ti / cols))
			painted += 1
		print("tiled_map: layer %-9s painted %d cells" % [layer.get("name", "?"), painted])
