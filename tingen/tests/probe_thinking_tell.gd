extends SceneTree
## PROBE (tool, windowed) — captures the P3 "thinking" tell on the inspect card, driven through
## the REAL seams: a live HttpSidecar launch against a hung (never-answering) responder emits the
## typed `deciding begin` fact; the CharacterCard shows "( thinking… )" until the bounded decide
## times out and the `end` fact restores the live thought. Two shots:
##   thinking_01_in_flight.png — the card mid-decide, thinking tell up
##   thinking_02_restored.png  — after the timeout lands, the live thought line back
## Run WINDOWED:  $GODOT --path tingen -s tests/probe_thinking_tell.gd [-- outdir=/abs/path]
## No LLM cost (nothing ever answers); TestSandbox keeps the real profile untouched.

func _init() -> void:
	await process_frame
	await process_frame
	preload("res://src/TestSandbox.gd").activate(root)
	var outdir := "user://probe_shots"
	for arg in OS.get_cmdline_user_args():
		if String(arg).begins_with("outdir="):
			outdir = String(arg).substr(7)
	DirAccess.make_dir_recursive_absolute(ProjectSettings.globalize_path(outdir))

	var AG: Object = root.get_node("/root/Agents")
	AG.rebuild()
	var a: Agent = AG.get_agent("clerk_voss")

	# A plain backdrop so the card reads in the shot.
	var bg := ColorRect.new()
	bg.color = Color(0.09, 0.09, 0.12)
	bg.set_anchors_preset(Control.PRESET_FULL_RECT)
	root.add_child(bg)
	var card: Node = load("res://ui/CharacterCard.tscn").instantiate()
	root.add_child(card)
	await process_frame
	root.get_node("/root/WorldState").inspect_requested.emit(a.id)
	await process_frame

	# The REAL seam: a bounded /decide against a responder that never answers.
	var srv := TCPServer.new()
	srv.listen(58741, "127.0.0.1")
	var hs := HttpSidecar.new("http://127.0.0.1:58741")
	hs.timeout_sec = 1.5
	hs.propose([Perception.build_snapshot(a, Vector2.ZERO)])   # -> `deciding begin` fact
	await process_frame
	await process_frame
	var tell: String = card.get_node("Margin/Body/Thought").text
	print("[probe][assert] in-flight thought line: %s" % tell)
	print("[probe][assert] thinking tell visible: %s" % str(tell.to_lower().contains("thinking")))
	await _shot(outdir.path_join("thinking_01_in_flight.png"))

	# Let the bounded decide time out; drain -> `deciding end` -> the live thought returns.
	var t0 := Time.get_ticks_msec()
	while Time.get_ticks_msec() - t0 < 2500:
		await process_frame
	hs._drain_pending()
	await process_frame
	await process_frame
	var restored: String = card.get_node("Margin/Body/Thought").text
	print("[probe][assert] restored thought line: %s" % restored)
	print("[probe][assert] tell cleared: %s" % str(not restored.to_lower().contains("thinking")))
	await _shot(outdir.path_join("thinking_02_restored.png"))
	hs.shutdown()
	srv.stop()
	quit(0)

func _shot(path: String) -> void:
	await process_frame
	var img: Image = root.get_viewport().get_texture().get_image()
	img.save_png(ProjectSettings.globalize_path(path))
	print("[probe] wrote %s" % ProjectSettings.globalize_path(path))
