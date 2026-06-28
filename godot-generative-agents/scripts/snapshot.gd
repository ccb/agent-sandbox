extends Node
## Dev utility: load a scene, let it draw a moment, save a screenshot of the
## viewport, and quit. Lets us verify the render without a person watching.
##
## Run (windowed — pixel capture needs a real renderer, so NOT --headless):
##   Godot --path <project> res://scenes/snapshot.tscn
##   Godot --path <project> res://scenes/snapshot.tscn -- <scene.tscn> <out.png>
## With no args it snapshots scenes/campus_urban.tscn to campus_snapshot.png.

const DEFAULT_SCENE := "res://scenes/campus_urban.tscn"
const DEFAULT_OUT := "res://campus_snapshot.png"


func _ready() -> void:
	var uargs := OS.get_cmdline_user_args()
	var scene_path := uargs[0] if uargs.size() >= 1 else DEFAULT_SCENE
	var out := uargs[1] if uargs.size() >= 2 else DEFAULT_OUT

	var scene: Node = load(scene_path).instantiate()
	add_child(scene)
	# Give the tilemap a few frames + a beat to paint and render.
	await get_tree().process_frame
	await get_tree().process_frame
	await get_tree().create_timer(1.0).timeout
	var img: Image = get_viewport().get_texture().get_image()
	var err := img.save_png(out)
	if err == OK:
		print("snapshot: saved ", ProjectSettings.globalize_path(out))
	else:
		push_error("snapshot: save failed (%d)" % err)
	get_tree().quit()
