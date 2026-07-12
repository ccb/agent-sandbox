-- Tomb of Nassak An-Rah -- Playdate (M1+: the continuous Composer)
-- docs/design/playdate.md. ONE wheel: the crank runs through EXITS, VERBS,
-- and NOUNS as a single strip with inline section tags; left/right jumps a
-- section; A speaks; B unsays. Saves are (seed, journal) in the datastore.

import "CoreLibs/graphics"
import "CoreLibs/crank"
import "CoreLibs/keyboard"
import "engine/core"
import "content/slice"
import "content/captions"

local gfx = playdate.graphics

-- ------------------------------------------------------------- transcript
local SCREEN_W, TRANS_H = 400, 198
local MARGIN = 6
local PANE = TRANS_H - MARGIN * 2
local transcript = {}
local viewY = 0 -- pixels of transcript scrolled past the pane's top
local anchorTop = true -- reading mode: top of turn by default (CCB)

local function say(text)
	local _, h = gfx.getTextSizeForMaxWidth(text, SCREEN_W - MARGIN * 2)
	transcript[#transcript + 1] = { text = text, h = h + 4 }
end

local function totalHeight()
	local total = 0
	for i = 1, #transcript do total = total + transcript[i].h end
	return total
end

local function clampView()
	viewY = math.max(0, math.min(viewY, math.max(0, totalHeight() - PANE)))
end

-- After a turn's output: LATEST snaps to the end; TOP pins the turn's
-- first line to the pane top so the player reads down at their own pace
-- (the web terminal's behavior, CCB).
local function settleView(turnStartHeight)
	if anchorTop then
		viewY = turnStartHeight
	else
		viewY = totalHeight() - PANE
	end
	clampView()
end

-- ---------------------------------------------------------- card captions
-- Words on the cards render on DEVICE (content/captions.lua): pixel-true
-- Playdate fonts over text-free imagetable geometry.
local function drawCaptions(key, frame)
	local list = Captions and Captions[key]
	if not list then return end
	gfx.setImageDrawMode(gfx.kDrawModeFillWhite)
	for j = 1, #list do
		local c = list[j]
		if frame >= (c.from or 0) and (not c.to or frame < c.to) then
			if c.text2 then
				-- a LEDGER line: label, then the dot leader typed one dot
				-- at a time to the tab stop, then the value -- proportional
				-- type, aligned column
				local labelW = gfx.getTextSize(c.text)
				local dotW = gfx.getTextSize(".")
				local dotsX = c.x + labelW + 4
				local nDots = math.max(0, math.floor((c.x2 - 6 - dotsX) / dotW))
				local total = #c.text + nDots + #c.text2
				local k = total
				if c.type then
					k = math.min(total,
						math.floor((frame - (c.from or 0)) * (c.cps or 2)))
				end
				local label = string.sub(c.text, 1, math.min(k, #c.text))
				local dots = string.rep(".", math.max(0,
					math.min(k - #c.text, nDots)))
				local value = string.sub(c.text2, 1,
					math.max(0, k - #c.text - nDots))
				local cursor = (k < #c.text and 1)
					or (k < #c.text + nDots and 2)
					or (k < total and 3) or 0
				-- the REWRITE beat: backspace the value, hold, retype the
				-- fate (the dots stay down)
				local rw = c.rewrite
				local boldLine = c.bold
				if rw and frame >= rw.at then
					local rk = math.floor((frame - rw.at) * (rw.cps or 2))
					if rk < #c.text2 then
						value = string.sub(c.text2, 1, #c.text2 - rk)
						cursor = 3
					elseif rw.retypeAt and frame < rw.retypeAt then
						value = ""
						cursor = 0
					else
						local t0 = rw.retypeAt or rw.at
						local typed = math.floor((frame - t0) * (rw.cps or 2))
						value = string.sub(rw.text2, 1,
							math.min(typed, #rw.text2))
						cursor = typed < #rw.text2 and 3 or 0
					end
					if rw.bold then boldLine = true end
				end
				if cursor == 1 then label = label .. "_"
				elseif cursor == 2 then dots = dots .. "_"
				elseif cursor == 3 then value = value .. "_" end
				if boldLine then
					label = "*" .. label .. "*"
					if #dots > 0 then dots = "*" .. dots .. "*" end
					if #value > 0 then value = "*" .. value .. "*" end
				end
				gfx.drawText(label, c.x, c.y)
				if #dots > 0 then gfx.drawText(dots, dotsX, c.y) end
				if #value > 0 then gfx.drawText(value, c.x2, c.y) end
			else
				local shown = #c.text
				if c.type then
					shown = math.min(#c.text,
						math.floor((frame - (c.from or 0)) * (c.cps or 2)))
				end
				local txt = string.sub(c.text, 1, shown)
				if shown < #c.text then txt = txt .. "_" end
				if c.bold then txt = "*" .. txt .. "*" end
				if c.align == "center" then
					gfx.drawTextAligned(txt, c.x, c.y, kTextAlignment.center)
				elseif c.align == "right" then
					gfx.drawTextAligned(txt, c.x, c.y, kTextAlignment.right)
				else
					gfx.drawText(txt, c.x, c.y)
				end
			end
		end
	end
end

-- ---------------------------------------------------------------- figures
-- Litho cards as 1-bit imagetables (tools/export_figures.py). A cue plays
-- the card full-screen at the reel's 12 fps; any button returns to the
-- text. Missing tables are silently skipped -- text is the complete game.
local figTables = {}
local overlay = nil

local function showFigure(key)
	if figTables[key] == nil then
		figTables[key] = gfx.imagetable.new("images/figures/" .. key) or false
	end
	if figTables[key] then
		overlay = { t = figTables[key], i = 1, acc = 0, key = key }
	end
end

-- ------------------------------------------------------------------ game
local game

local function newGame(seed)
	game = BuildTomb(seed)
	game.out = say
	transcript = {}
	say("VAULTS OF VAARN: TOMB OF NASSAK AN-RAH")
	game:describe()
	settleView(0)
	game.onFigure = showFigure
	showFigure("road") -- the Trail opens every fresh expedition
end

local function autosave()
	playdate.datastore.write(game:snapshot(), "auto")
end

local function boot()
	local snap = playdate.datastore.read("auto")
	if snap and snap.journal and #snap.journal > 0 then
		game = Engine.restore(function(seed)
			local g = BuildTomb(seed)
			g.out = function() end
			return g
		end, snap)
		game.out = say
		transcript = {}
		say("The expedition continues. (Menu: new game to begin anew.)")
		game:describe()
		settleView(0)
		game.onFigure = showFigure -- attached AFTER replay: no stale pops
	else
		newGame(playdate.getSecondsSinceEpoch() % 1000000)
	end
end

-- ------------------------------------------------------------ the Composer
local LANES = { "EXITS", "VERBS", "NOUNS" }
local EXITS_LANE, VERBS_LANE, NOUNS_LANE = 1, 2, 3
local pos = 1
local lastWord = { nil, nil, nil } -- per-pool recency (Thy Dungeonman)
local command = {}

-- the whole wheel: every lane's words, in lane order, as one strip
local function wheel()
	local sug = game:suggestions()
	local pools = { sug.exits, sug.verbs, sug.nouns }
	local items, starts = {}, {}
	for l = 1, 3 do
		starts[l] = #items + 1
		for i = 1, #pools[l] do
			items[#items + 1] = { word = pools[l][i], lane = l }
		end
	end
	return items, starts
end

local function jumpTo(laneIdx)
	local items, starts = wheel()
	pos = starts[laneIdx] or 1
	if lastWord[laneIdx] then
		for i = starts[laneIdx], #items do
			if items[i].lane ~= laneIdx then break end
			if items[i].word == lastWord[laneIdx] then
				pos = i
				break
			end
		end
	end
end

local function runCommand(line)
	local startH = totalHeight()
	local n0 = #transcript
	game:doCommand(line)
	autosave()
	-- In top mode, pin the view just PAST the echoed command: you know what
	-- you said; the pane opens on the world's answer. The echo stays in the
	-- transcript for scrollback (CCB).
	local echoH = 0
	if #transcript > n0 + 1 then echoH = transcript[n0 + 1].h end
	settleView(startH + echoH)
end

local function pressA()
	local items = wheel()
	if #items == 0 then return end
	pos = ((pos - 1) % #items) + 1
	local it = items[pos]
	if it.lane == EXITS_LANE then
		if #command == 0 then
			lastWord[EXITS_LANE] = it.word
			runCommand("go " .. it.word)
		end
		return -- an exit is never a noun; mid-command it stays quiet
	end
	lastWord[it.lane] = it.word
	command[#command + 1] = it.word
	-- walk the verb's slot template: connectors ("to") append themselves
	local slots = Engine.verbSlots(command[1])
	local filled = #command - 1
	while filled < #slots and slots[filled + 1] ~= "noun" do
		command[#command + 1] = slots[filled + 1]
		filled = filled + 1
	end
	if filled >= #slots then
		runCommand(table.concat(command, " "))
		command = {}
		jumpTo(VERBS_LANE) -- the loop restarts at the verbs
	elseif it.lane == VERBS_LANE then
		jumpTo(NOUNS_LANE) -- a verb that wants nouns advances you
	end
end

local function pressB()
	if #command > 0 then
		command[#command] = nil
		-- a bare connector never stands at the end of the line
		while #command > 1 and Engine.verbSlots(command[1])[#command - 1] ~= "noun" do
			command[#command] = nil
		end
		if #command == 0 then jumpTo(VERBS_LANE) end
	else
		viewY = totalHeight() - PANE -- bare B: snap to the latest
		clampView()
	end
end

-- ------------------------------------------------------- system menu items
local menu = playdate.getSystemMenu()
menu:addMenuItem("new game", function()
	playdate.datastore.delete("auto")
	newGame(playdate.getSecondsSinceEpoch() % 1000000)
end)
menu:addCheckmarkMenuItem("free input", false, function(on)
	if on then playdate.keyboard.show("") end
end)
menu:addOptionsMenuItem("reading", { "top", "latest" }, (function()
	local prefs = playdate.datastore.read("prefs")
	if prefs ~= nil then anchorTop = (prefs.anchorTop == true) end
	return anchorTop and "top" or "latest"
end)(), function(value)
	anchorTop = (value == "top")
	playdate.datastore.write({ anchorTop = anchorTop }, "prefs")
end)

function playdate.keyboard.keyboardWillHideCallback(okPressed)
	if okPressed and playdate.keyboard.text ~= "" then
		runCommand(playdate.keyboard.text)
	end
end

-- ------------------------------------------------------------ input + draw
function playdate.update()
	-- a card on screen owns the screen: advance at the reel's 12 fps,
	-- hold the last frame, and leave on any button
	if overlay then
		if playdate.buttonJustPressed(playdate.kButtonA)
			or playdate.buttonJustPressed(playdate.kButtonB) then
			overlay = nil
			return
		end
		gfx.clear(gfx.kColorBlack)
		-- copy mode: the lingering fill-white text mode would paint the
		-- whole card as a blank block
		gfx.setImageDrawMode(gfx.kDrawModeCopy)
		local n = overlay.t:getLength()
		local img = overlay.t:getImage(math.min(overlay.i, n))
		if img then img:draw(8, 0) end
		drawCaptions(overlay.key, overlay.i - 1)
		overlay.acc = overlay.acc + 12 / 30
		if overlay.acc >= 1 then
			overlay.i = math.min(overlay.i + math.floor(overlay.acc), n)
			overlay.acc = overlay.acc % 1
		end
		return
	end

	local ticks = playdate.getCrankTicks(6)
	if ticks ~= 0 then pos = pos + ticks end

	if playdate.buttonJustPressed(playdate.kButtonLeft) then
		pos = pos - 1 -- the d-pad steps the wheel, same as the crank
	elseif playdate.buttonJustPressed(playdate.kButtonRight) then
		pos = pos + 1
	elseif playdate.buttonJustPressed(playdate.kButtonUp) then
		viewY = viewY - 40
		clampView()
	elseif playdate.buttonJustPressed(playdate.kButtonDown) then
		viewY = viewY + 40
		clampView()
	elseif playdate.buttonJustPressed(playdate.kButtonA) then
		pressA()
	elseif playdate.buttonJustPressed(playdate.kButtonB) then
		pressB()
	end

	gfx.clear(gfx.kColorBlack)
	gfx.setImageDrawMode(gfx.kDrawModeFillWhite)

	-- the transcript, bottom-anchored, clipped
	gfx.setClipRect(0, 0, SCREEN_W, TRANS_H)
	local y = MARGIN - viewY
	for i = 1, #transcript do
		local e = transcript[i]
		if y + e.h > 0 and y < TRANS_H then
			gfx.drawTextInRect(e.text, MARGIN, y, SCREEN_W - MARGIN * 2, e.h)
		end
		y = y + e.h
	end
	gfx.clearClipRect()

	-- the command line, and the score at its right
	gfx.drawLine(0, TRANS_H + 2, SCREEN_W, TRANS_H + 2)
	gfx.drawText("> " .. table.concat(command, " ") .. "_", MARGIN, TRANS_H + 6)
	gfx.drawText("*" .. game.score .. "/" .. game.maxScore .. "  T:" .. game.turn .. "*",
		SCREEN_W - 96, TRANS_H + 6)

	-- ONE strip: [TAG] word word [TAG] word ... selected word inverted,
	-- section tags appearing inline as the wheel crosses them
	local stripY = TRANS_H + 24
	local items = wheel()
	if #items > 0 then
		pos = ((pos - 1) % #items) + 1
		local x = MARGIN
		local i = pos
		local prevLane = nil
		local shown = 0
		local _, th = gfx.getTextSize("A")
		while x < SCREEN_W - 8 and shown < #items do
			local it = items[i]
			if it.lane ~= prevLane then
				local tag = LANES[it.lane]
				local tw = gfx.getTextSize(tag)
				gfx.drawText(tag, x + 1, stripY)
				x = x + tw + 14
				prevLane = it.lane
			end
			local ww = gfx.getTextSize(it.word)
			if x < SCREEN_W - 8 then
				if shown == 0 then
					gfx.setColor(gfx.kColorWhite)
					gfx.fillRect(x - 3, stripY - 1, ww + 6, th + 2)
					gfx.setImageDrawMode(gfx.kDrawModeFillBlack)
					gfx.drawText(it.word, x, stripY)
					gfx.setImageDrawMode(gfx.kDrawModeFillWhite)
				else
					gfx.drawText(it.word, x, stripY)
				end
			end
			x = x + ww + 14
			i = (i % #items) + 1
			shown = shown + 1
		end
	end
end

boot()
