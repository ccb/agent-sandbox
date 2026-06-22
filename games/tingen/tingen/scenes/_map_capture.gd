extends Node2D
## Throwaway test harness: render one frame of the scaled map + Klein, save a PNG,
## then quit its own window. Safe to delete with MapScaleTest.tscn.

const OUT := "/Users/markma/Desktop/Purm 2026/Tingen-Game/asset-gen/_maptest_capture.png"

func _ready() -> void:
	await get_tree().create_timer(1.0).timeout
	await RenderingServer.frame_post_draw
	var tex := get_viewport().get_texture()
	var img: Image = tex.get_image() if tex else null
	if img:
		img.save_png(OUT)
		print("CAPTURE_SAVED ", img.get_size())
	else:
		print("CAPTURE_FAILED null image")
	await get_tree().create_timer(0.3).timeout
	get_tree().quit()
