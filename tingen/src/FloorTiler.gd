extends TileMapLayer
## Fills a rectangular floor region with one tile at runtime, so we get a real TileMapLayer
## floor without hand-painting tile data in the editor. The slice uses a single seamless wood
## tile; later hubs extend this to multiple sources / per-cell variety.

@export var cols: int = 9
@export var rows: int = 6
@export var source_id: int = 0
@export var atlas_coords: Vector2i = Vector2i.ZERO

func _ready() -> void:
	if tile_set == null:
		push_warning("FloorTiler on '%s' has no tile_set; floor will be empty." % name)
		return
	for y in rows:
		for x in cols:
			set_cell(Vector2i(x, y), source_id, atlas_coords)
