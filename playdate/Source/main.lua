-- Tomb of Nassak An-Rah -- Playdate (M1: the mini-engine drives the UI)
-- docs/design/playdate.md. The Composer: crank scrolls the active lane,
-- d-pad switches EXITS/VERBS/NOUNS, A speaks, B unsays. Saves are
-- (seed, journal) in the datastore, replayed quietly on boot.

import "CoreLibs/graphics"
import "CoreLibs/crank"
import "CoreLibs/keyboard"
import "engine/core"
import "content/slice"

local gfx = playdate.graphics

-- ------------------------------------------------------------- transcript
local SCREEN_W, TRANS_H = 400, 198 -- the composer is two lines, not a panel
local MARGIN = 6
local transcript = {}
local scrollUp = 0

local function say(text)
	local _, h = gfx.getTextSizeForMaxWidth(text, SCREEN_W - MARGIN * 2)
	transcript[#transcript + 1] = { text = text, h = h + 4 }
	scrollUp = 0
end

-- ------------------------------------------------------------------ game
local game

local function newGame(seed)
	game = BuildTomb(seed)
	game.out = say
	transcript = {}
	say("TOMB OF NASSAK AN-RAH -- a Vaults of Vaarn expedition")
	say("Crank turns the word lane; left/right picks a lane; A speaks; B unsays.")
	game:describe()
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
		say("The expedition continues. (Menu: New Game to begin anew.)")
		game:describe()
	else
		newGame(playdate.getSecondsSinceEpoch() % 1000000)
	end
end

-- ------------------------------------------------------------ the Composer
local LANES = { "EXITS", "VERBS", "NOUNS" }
local lane = 1
local sel = { 1, 1, 1 }
local lastWord = { nil, nil, nil } -- per-pool recency (Thy Dungeonman's trick)
local command = {}

local function laneWords()
	local sug = game:suggestions()
	if lane == 1 then return sug.exits end
	if lane == 2 then return sug.verbs end
	return sug.nouns
end

local function recall()
	-- the lane opens on the word you used last, when it still exists
	local words = laneWords()
	if lastWord[lane] then
		for i = 1, #words do
			if words[i] == lastWord[lane] then
				sel[lane] = i
				return
			end
		end
	end
end

local function runCommand(line)
	game:doCommand(line)
	autosave()
end

local function pressA()
	local words = laneWords()
	if #words == 0 then return end
	local word = words[((sel[lane] - 1) % #words) + 1]
	lastWord[lane] = word
	if lane == 1 and #command == 0 then
		runCommand("go " .. word)
		return
	end
	command[#command + 1] = word
	local arity = Engine.verbArity(command[1])
	if #command >= arity + 1 then
		runCommand(table.concat(command, " "))
		command = {}
	end
end

local function pressB()
	if #command > 0 then
		command[#command] = nil
	else
		scrollUp = 0
	end
end

-- ------------------------------------------------------- system menu items
local menu = playdate.getSystemMenu()
menu:addMenuItem("new game", function()
	playdate.datastore.delete("auto")
	newGame(playdate.getSecondsSinceEpoch() % 1000000)
end)
menu:addCheckmarkMenuItem("free input", false, function(on)
	if on then
		playdate.keyboard.show("")
	end
end)

function playdate.keyboard.keyboardWillHideCallback(okPressed)
	if okPressed and playdate.keyboard.text ~= "" then
		runCommand(playdate.keyboard.text)
	end
end

-- ------------------------------------------------------------ input + draw
function playdate.update()
	local ticks = playdate.getCrankTicks(6)
	if ticks ~= 0 then sel[lane] = sel[lane] + ticks end

	if playdate.buttonJustPressed(playdate.kButtonLeft) then
		lane = ((lane - 2) % #LANES) + 1
		recall()
	elseif playdate.buttonJustPressed(playdate.kButtonRight) then
		lane = (lane % #LANES) + 1
		recall()
	elseif playdate.buttonJustPressed(playdate.kButtonUp) then
		scrollUp = scrollUp + 40
	elseif playdate.buttonJustPressed(playdate.kButtonDown) then
		scrollUp = math.max(0, scrollUp - 40)
	elseif playdate.buttonJustPressed(playdate.kButtonA) then
		pressA()
	elseif playdate.buttonJustPressed(playdate.kButtonB) then
		pressB()
	end

	gfx.clear(gfx.kColorBlack)
	gfx.setImageDrawMode(gfx.kDrawModeFillWhite)

	gfx.setClipRect(0, 0, SCREEN_W, TRANS_H)
	local total = 0
	for i = 1, #transcript do total = total + transcript[i].h end
	local y = TRANS_H - MARGIN - total + scrollUp
	if total < TRANS_H - MARGIN * 2 then y = MARGIN end
	for i = 1, #transcript do
		local e = transcript[i]
		if y + e.h > 0 and y < TRANS_H then
			gfx.drawTextInRect(e.text, MARGIN, y, SCREEN_W - MARGIN * 2, e.h)
		end
		y = y + e.h
	end
	gfx.clearClipRect()

	gfx.drawLine(0, TRANS_H + 2, SCREEN_W, TRANS_H + 2)
	gfx.drawText("> " .. table.concat(command, " ") .. "_", MARGIN, TRANS_H + 6)
	gfx.drawText("*" .. game.score .. "/" .. game.maxScore .. "  T:" .. game.turn .. "*",
		SCREEN_W - 96, TRANS_H + 6)

	-- one strip: [LANE TAG] word word word -- the selected word inverted,
	-- crank slides the strip, left/right swaps the tag (and its pool)
	local stripY = TRANS_H + 24
	local tag = LANES[lane]
	local tw, th = gfx.getTextSize(tag)
	gfx.setColor(gfx.kColorWhite)
	gfx.fillRect(MARGIN - 2, stripY - 1, tw + 8, th + 2)
	gfx.setImageDrawMode(gfx.kDrawModeFillBlack)
	gfx.drawText(tag, MARGIN + 2, stripY)
	gfx.setImageDrawMode(gfx.kDrawModeFillWhite)

	local words = laneWords()
	local x = MARGIN + tw + 16
	if #words > 0 then
		local n = #words
		local i = ((sel[lane] - 1) % n)
		local shown = 0
		while x < SCREEN_W - 8 and shown < n do
			local word = words[(i % n) + 1]
			local ww = gfx.getTextSize(word)
			if shown == 0 then
				gfx.setColor(gfx.kColorWhite)
				gfx.fillRect(x - 3, stripY - 1, ww + 6, th + 2)
				gfx.setImageDrawMode(gfx.kDrawModeFillBlack)
				gfx.drawText(word, x, stripY)
				gfx.setImageDrawMode(gfx.kDrawModeFillWhite)
			else
				gfx.drawText(word, x, stripY)
			end
			x = x + ww + 14
			i = i + 1
			shown = shown + 1
		end
	end
end

boot()
