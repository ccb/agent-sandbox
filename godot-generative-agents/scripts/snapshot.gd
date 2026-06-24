extends Node
## Dev utility: load the main scene, let it draw a moment, save a screenshot of
## the viewport, and quit. Lets us verify the render without a person watching.
##
## Run (windowed — pixel capture needs a real renderer, so NOT --headless):
##   Godot --path <project> res://scenes/snapshot.tscn
## The PNG lands in the project root as campus_snapshot.png.

const OUT := "res://campus_snapshot.png"


func _ready() -> void:
	var main: Node = load("res://scenes/main.tscn").instantiate()
	add_child(main)
	# Give the tilemap a few frames + a beat to paint and render.
	await get_tree().process_frame
	await get_tree().process_frame
	await get_tree().create_timer(1.0).timeout
	var img: Image = get_viewport().get_texture().get_image()
	var err := img.save_png(OUT)
	if err == OK:
		print("snapshot: saved ", ProjectSettings.globalize_path(OUT))
	else:
		push_error("snapshot: save failed (%d)" % err)
	get_tree().quit()
