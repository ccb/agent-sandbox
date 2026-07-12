-- Tomb of Nassak An-Rah -- Playdate (M1+: the continuous Composer)
-- docs/design/playdate.md. ONE wheel: the crank runs through EXITS, VERBS,
-- and NOUNS as a single strip with inline section tags; left/right jumps a
-- section; A speaks; B unsays. Saves are (seed, journal) in the datastore.

import "CoreLibs/graphics"
import "CoreLibs/crank"
import "CoreLibs/keyboard"
import "engine/core"
import "content/slice"

local gfx = playdate.graphics

-- ------------------------------------------------------------- transcript
local SCREEN_W, TRANS_H = 400, 198
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
	say("Crank or left/right turns the word wheel; A speaks; B unsays.")
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
		say("The expedition continues. (Menu: new game to begin anew.)")
		game:describe()
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
	game:doCommand(line)
	autosave()
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
	local arity = Engine.verbArity(command[1])
	if #command >= arity + 1 then
		runCommand(table.concat(command, " "))
		command = {}
		jumpTo(VERBS_LANE) -- the loop restarts at the verbs
	elseif it.lane == VERBS_LANE then
		jumpTo(NOUNS_LANE) -- a verb that wants a noun advances you
	end
end

local function pressB()
	if #command > 0 then
		command[#command] = nil
		if #command == 0 then jumpTo(VERBS_LANE) end
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
	if on then playdate.keyboard.show("") end
end)

function playdate.keyboard.keyboardWillHideCallback(okPressed)
	if okPressed and playdate.keyboard.text ~= "" then
		runCommand(playdate.keyboard.text)
	end
end

-- ------------------------------------------------------------ input + draw
function playdate.update()
	local ticks = playdate.getCrankTicks(6)
	if ticks ~= 0 then pos = pos + ticks end

	if playdate.buttonJustPressed(playdate.kButtonLeft) then
		pos = pos - 1 -- the d-pad steps the wheel, same as the crank
	elseif playdate.buttonJustPressed(playdate.kButtonRight) then
		pos = pos + 1
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

	-- the transcript, bottom-anchored, clipped
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
				gfx.setColor(gfx.kColorWhite)
				gfx.drawRect(x - 2, stripY - 1, tw + 6, th + 2)
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
