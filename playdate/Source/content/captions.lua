-- Card captions, rendered ON DEVICE in real Playdate fonts (the native-text
-- layer, docs section 5): the imagetables carry pure geometry; the words
-- live here, in device space (400x240) and card frames (12 fps, 0-based).
-- Entry: { from=, to=, x=, y=, text=, type=, cps=, bold=, align= }
--   from/to .. frame window (to nil = forever)
--   type .... typewriter from 'from' (cps chars/frame, default 2)
--   align ... "center" | "right" (x is the anchor)

Captions = {
	road = {
		{ from = 0, x = 8, y = 2, text = "ROAD TO GNOMON", bold = true,
			type = true, cps = 2 },
		-- the party ledger, typed -- then moonset rewrites every line
		{ from = 4, to = 116, x = 14, y = 30, type = true, cps = 3,
			text = "MERCHANT ...... WITH THE WAGON" },
		{ from = 10, to = 116, x = 14, y = 48, type = true, cps = 3,
			text = "ZOXEN x2 ...... PULLING" },
		{ from = 16, to = 116, x = 14, y = 66, type = true, cps = 3,
			text = "TEAMSTER ...... DRIVING" },
		{ from = 22, to = 116, x = 14, y = 84, type = true, cps = 3,
			text = "YOU ........... NOT YET HERE" },
		{ from = 116, x = 14, y = 30, text = "MERCHANT ...... LOST (MOONSET)" },
		{ from = 116, x = 14, y = 48, text = "ZOXEN x2 ...... LOST" },
		{ from = 116, x = 14, y = 66, text = "TEAMSTER ...... FLED SOUTH" },
		{ from = 116, x = 14, y = 84, text = "YOU ........... INCOMING",
			bold = true },
		{ from = 150, x = 200, y = 196, align = "center", type = true, cps = 3,
			text = "THE ROAD TO GNOMON IS WALKED" },
		{ from = 160, x = 200, y = 216, align = "center", type = true, cps = 3,
			text = "ONLY BY THE DESPERATE. PROVEN AGAIN." },
	},
	["guts-a"] = {
		{ from = 0, x = 8, y = 2, text = "SPAWN OF GUTS", bold = true,
			type = true, cps = 2 },
		{ from = 10, x = 392, y = 30, align = "right", type = true, cps = 3,
			text = "HELM: THE FALCON JAR." },
		{ from = 22, x = 392, y = 48, align = "right", type = true, cps = 3,
			text = "THE PLINTH WANTS IT BACK." },
		{ from = 40, x = 200, y = 216, align = "center", type = true, cps = 3,
			text = "IT SWAYS TOWARD WHATEVER YOU JUST DID." },
	},
	glowstone = {
		{ from = 0, x = 8, y = 2, text = "GLOWSTONE", bold = true,
			type = true, cps = 2 },
		{ from = 14, x = 200, y = 218, align = "center", type = true, cps = 3,
			text = "DARK UNTIL WOKEN. LIGHT IS DEAR." },
	},
}
