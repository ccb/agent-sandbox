extends TileMapLayer
## Builds the tiled ground from the Cute Fantasy tile sheet: grass everywhere,
## two crossing dirt paths, and a small pond with a proper shoreline.
##
## The TileSet is assembled in code, so there is no binary tile data to hand-edit
## — we just loop over set_cell(). Grass and path are single 16x16 fill tiles; the
## pond uses the 3x3 "water-in-grass" nine-slice (corners, edges, centre) from the
## top-left of the Water_Tile sheet, so its edges blend into the surrounding grass.

@export var grass_tile: Texture2D   # Tiles/Grass_Middle.png (16x16 fill)
@export var path_tile: Texture2D    # Tiles/Path_Middle.png  (16x16 fill)
@export var pond_sheet: Texture2D   # Tiles/Water_Tile.png   (nine-slice in top-left)

const TILE_PX := 16   # each source tile is 16x16 pixels
const COLS := 24      # at scale 3 (48px/tile) this fills the 1152-wide window...
const ROWS := 14      # ...and the 648-tall window (with a little to spare)

# Atlas-source ids for the tile kinds in the TileSet we build below.
const GRASS := 0
const PATH := 1
const POND := 2


func _ready() -> void:
	tile_set = _build_tile_set()

	# 1) Carpet the whole grid with grass.
	for y in ROWS:
		for x in COLS:
			set_cell(Vector2i(x, y), GRASS, Vector2i.ZERO)

	# 2) Two dirt paths that cross in the middle.
	var road_row := ROWS / 2
	var road_col := COLS / 2
	for x in COLS:
		set_cell(Vector2i(x, road_row), PATH, Vector2i.ZERO)
	for y in ROWS:
		set_cell(Vector2i(road_col, y), PATH, Vector2i.ZERO)

	# 3) A small pond in the top-left grass.
	_draw_pond(2, 2, 5, 4)


func _build_tile_set() -> TileSet:
	var ts := TileSet.new()
	ts.tile_size = Vector2i(TILE_PX, TILE_PX)
	_add_fill_source(ts, GRASS, grass_tile)
	_add_fill_source(ts, PATH, path_tile)
	_add_pond_source(ts, POND, pond_sheet)
	return ts


# A single-tile source: one 16x16 tile at atlas coord (0, 0).
func _add_fill_source(ts: TileSet, id: int, tex: Texture2D) -> void:
	var src := TileSetAtlasSource.new()
	src.texture = tex
	src.texture_region_size = Vector2i(TILE_PX, TILE_PX)
	src.create_tile(Vector2i.ZERO)
	ts.add_source(src, id)


# The pond source holds the 3x3 nine-slice in the top-left of the Water_Tile sheet.
func _add_pond_source(ts: TileSet, id: int, tex: Texture2D) -> void:
	var src := TileSetAtlasSource.new()
	src.texture = tex
	src.texture_region_size = Vector2i(TILE_PX, TILE_PX)
	for ty in 3:
		for tx in 3:
			src.create_tile(Vector2i(tx, ty))
	ts.add_source(src, id)


# Paint a w x h pond at tile (x0, y0). Border cells pick the matching nine-slice
# corner/edge; interior cells are open water. Looks best with w >= 3 and h >= 3.
func _draw_pond(x0: int, y0: int, w: int, h: int) -> void:
	for dy in h:
		for dx in w:
			# Atlas column: 0 = left edge, 2 = right edge, 1 = middle.
			var ax := 1
			if dx == 0:
				ax = 0
			elif dx == w - 1:
				ax = 2
			# Atlas row: 0 = top edge, 2 = bottom edge, 1 = middle.
			var ay := 1
			if dy == 0:
				ay = 0
			elif dy == h - 1:
				ay = 2
			set_cell(Vector2i(x0 + dx, y0 + dy), POND, Vector2i(ax, ay))
