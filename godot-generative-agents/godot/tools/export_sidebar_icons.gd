extends SceneTree
## Export the sidebar's hand-drawn button glyphs as PNGs for the web companion's
## landing page, which shows them in a legend under the replay demo (issue #879).
## Run from anywhere:
##   godot --headless --path godot-generative-agents/godot \
##     --script res://tools/export_sidebar_icons.gd
## Exit 0 + the "ok: wrote N icons" line = all icons written. On a fresh checkout
## run `godot --headless --path godot-generative-agents/godot --import` first, so
## the glyph sheets agent_panel.gd preloads are in the .godot/ cache.
##
## The point of exporting rather than redrawing: these call agent_panel.gd's own
## static builders, so the legend on the page cannot drift from the buttons in the
## viewer. Only the five hand-drawn glyphs the legend uses are exported — add the
## sheet-cut ones (_pack_icon: home, zoom, reset, pause) here if it ever grows.

const AgentPanel := preload("res://scripts/agent_panel.gd")

const OUT_DIR := "res://../web/public/sidebar-icons"


func _initialize() -> void:
	# Output file stem -> that button's icon, straight from the panel's builder.
	var icons := {
		"heatmap": AgentPanel._flame_icon(),
		"social-graph": AgentPanel._graph_icon(),
		"day-plans": AgentPanel._calendar_icon(),
		"snapshot": AgentPanel._camera_icon(),
		"snapshots": AgentPanel._gallery_icon(),
	}

	var out := ProjectSettings.globalize_path(OUT_DIR)
	var err := DirAccess.make_dir_recursive_absolute(out)
	if err != OK:
		push_error("FAIL: cannot create %s (error %d)" % [out, err])
		quit(1)
		return

	for stem in icons:
		var image: Image = icons[stem].get_image()
		err = image.save_png("%s/%s.png" % [out, stem])
		if err != OK:
			push_error("FAIL: cannot write %s.png (error %d)" % [stem, err])
			quit(1)
			return
		print("  %s.png (%dx%d)" % [stem, image.get_width(), image.get_height()])

	print("ok: wrote %d icons to %s" % [icons.size(), out])
	quit(0)
