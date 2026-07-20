extends TileMapLayer
## Generic renderer for a Tiled (.tmj) map whose tilesets are packed images (no
## spacing) — e.g. the OSM campus maps baked with Kenney's CC0 RPG Urban tiles
## (`osm_to_tiled.py --theme urban`), optionally alongside extra tilesets such as
## the generated lawn-edge strokes. Reads the JSON, loads every referenced sheet
## as its own atlas source, and paints each layer by GID. This is the no-plugin
## equivalent of importing the same .tmj via the YATI addon, and it works for any
## packed-image Tiled map, not just ours.

@export_file("*.tmj") var map_path: String = "res://maps/upenn_core_urban.tmj"

# One entry per .tmj tileset: where its GID range starts, its column count, and the
# atlas source id we registered it under. Used to map any GID back to its sheet.
var _sheets: Array = []


func _ready() -> void:
	# Nearest filtering (no smoothing) is what pixel art wants; combined with the
	# texture padding below and the project's pixel-snap, it keeps tile edges crisp
	# and seam-free even when the camera zooms to a fractional scale.
	texture_filter = CanvasItem.TEXTURE_FILTER_NEAREST

	var f := FileAccess.open(map_path, FileAccess.READ)
	if f == null:
		push_error("tiled_map: cannot open %s" % map_path)
		return
	var tmj: Variant = JSON.parse_string(f.get_as_text())
	if typeof(tmj) != TYPE_DICTIONARY:
		push_error("tiled_map: %s is not valid Tiled JSON" % map_path)
		return

	var tile_size := Vector2i(int(tmj["tilewidth"]), int(tmj["tileheight"]))
	tile_set = _build_tile_set(tmj, tile_size)
	if tile_set == null:
		return
	_paint(tmj)


func _build_tile_set(tmj: Dictionary, tile_size: Vector2i) -> TileSet:
	# Register every .tmj tileset as its own atlas source (source id = its index),
	# recording each one's GID range so _paint can resolve a GID to (source, cell).
	var t := TileSet.new()
	t.tile_size = tile_size
	for i in tmj["tilesets"].size():
		var ts: Dictionary = tmj["tilesets"][i]
		var tex := _load_texture(str(ts["image"]))
		if tex == null:
			push_error("tiled_map: cannot load tileset image %s" % ts["image"])
			return null
		var cols := int(ts["columns"])
		var count := int(ts["tilecount"])
		var src := TileSetAtlasSource.new()
		src.texture = tex
		src.texture_region_size = tile_size
		# Pad each tile by duplicating its edge pixels, so a neighbouring tile in the
		# packed sheet can never bleed in at the seams.
		src.use_texture_padding = true
		var rows := int(ceil(float(count) / cols))
		for r in rows:
			for c in cols:
				src.create_tile(Vector2i(c, r))
		t.add_source(src, i)
		_sheets.append({"first": int(ts["firstgid"]), "cols": cols, "source": i})
	# Highest firstgid first, so the lookup picks the tileset a GID actually lands in.
	_sheets.sort_custom(func(a, b): return a["first"] > b["first"])
	return t


func _load_texture(image_name: String) -> Texture2D:
	# The sheet sits next to the .tmj. Prefer the imported texture (export-safe);
	# fall back to reading the file directly if it isn't a project resource.
	var img_path := map_path.get_base_dir().path_join(image_name)
	var tex: Texture2D = load(img_path) if ResourceLoader.exists(img_path) else null
	if tex == null:
		var img := Image.load_from_file(img_path)
		if img != null:
			tex = ImageTexture.create_from_image(img)
	return tex


func _paint(tmj: Dictionary) -> void:
	# Paint each .tmj tile layer into its OWN stacked TileMapLayer rather than
	# flattening them all onto this one node. A TileMapLayer holds a single tile per
	# cell, so flattening let an upper layer overwrite the cell beneath it — and
	# because the tree (and lawn-edge) tiles are transparent around their art, a
	# flattened overlay erased what it stood on and showed the window's grey clear
	# colour instead. Stacked layers composite, so an overlay's transparent pixels
	# reveal the layer below.
	#
	# This node stays the bottom (ground) layer so camera_controls.gd — which finds
	# the map by the sibling that `is TileMapLayer` and reads its used_rect — keeps
	# working unchanged; every layer above ground becomes a child of this node.
	var w := int(tmj["width"])
	var root_used := false
	for layer in tmj.get("layers", []):
		if layer.get("type", "") != "tilelayer":
			continue
		var target: TileMapLayer = self
		if root_used:
			target = _add_layer(str(layer.get("name", "layer")))
		else:
			root_used = true
		var data: Array = layer.get("data", [])
		var painted := 0
		for i in data.size():
			var gid := int(data[i])
			if gid == 0:
				continue
			# Resolve the GID against whichever tileset's range it falls in.
			for sheet in _sheets:
				if gid >= int(sheet["first"]):
					var ti: int = gid - int(sheet["first"])
					var c: int = int(sheet["cols"])
					target.set_cell(
						Vector2i(i % w, i / w), int(sheet["source"]), Vector2i(ti % c, ti / c)
					)
					break
			painted += 1
		print("tiled_map: layer %-9s painted %d cells" % [layer.get("name", "?"), painted])


func _add_layer(layer_name: String) -> TileMapLayer:
	# A stacked child layer sharing this node's tileset and pixel-art settings.
	# Children inherit our transform (so they sit in the same world space) and draw
	# on top in creation order, which preserves the .tmj's bottom-to-top paint order.
	var child := TileMapLayer.new()
	child.name = layer_name
	child.tile_set = tile_set
	child.texture_filter = CanvasItem.TEXTURE_FILTER_NEAREST
	add_child(child)
	return child
