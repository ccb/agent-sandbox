-- Tomb of Nassak An-Rah -- M0 spike (docs/design/playdate.md)
-- Proves the loop: a transcript pane + the three-lane crank Composer over a
-- two-room stub world. Exit criterion: composing GO NORTH moves you.

import "CoreLibs/graphics"
import "CoreLibs/crank"

local gfx = playdate.graphics

-- ------------------------------------------------------------- stub world
local rooms = {
	wreck = {
		name = "THE CARAVAN WRECK",
		text = "A trade caravan lies heeled over in the blue sand, the dead "
			.. "arranged by the wind into attitudes of sleep. Northward, three "
			.. "carved faces watch from a slab of azure stone.",
		exits = { north = "exterior" },
		nouns = { "wreck", "zoxen", "merchant", "critch" },
	},
	exterior = {
		name = "TOMB EXTERIOR",
		text = "A thirty-foot slab of azure stone rises from the phthalo "
			.. "sands, webbed with creeping orange fungus. Three faces are "
			.. "carved in it. Each mouth is a door.",
		exits = { south = "wreck" },
		nouns = { "tomb", "faces", "fungus" },
	},
}
local here = "wreck"

-- ------------------------------------------------------------- transcript
local SCREEN_W, TRANS_H = 400, 144
local MARGIN = 6
local transcript = {} -- { {text=..., h=...}, ... }
local scrollUp = 0 -- lines of history the player has cranked/paged back

local function say(text)
	local _, h = gfx.getTextSizeForMaxWidth(text, SCREEN_W - MARGIN * 2)
	transcript[#transcript + 1] = { text = text, h = h + 4 }
	scrollUp = 0 -- new text snaps the view to the bottom
end

local function describe()
	local room = rooms[here]
	local exits = {}
	for dir in pairs(room.exits) do exits[#exits + 1] = dir end
	say("*" .. room.name .. "*")
	say(room.text)
	say("Exits: " .. table.concat(exits, ", "))
end

-- ------------------------------------------------------------- the world answers
local function doCommand(words)
	local line = table.concat(words, " ")
	say("> " .. line)
	local verb, noun = words[1], words[2]
	if verb == "go" and rooms[here].exits[noun] then
		here = rooms[here].exits[noun]
		say("You moved to " .. rooms[here].name .. ".")
		describe()
	elseif verb == "look" then
		describe()
	elseif verb == "inventory" then
		say("You carry the M0 spike, and high hopes.")
	elseif verb == "examine" and noun then
		say("You look closely at the " .. noun
			.. ". The full tomb knows more; the spike only nods.")
	elseif verb == "take" and noun then
		say("The " .. noun .. " stays where it is -- taking arrives in M1.")
	elseif verb == "search" and noun then
		say("You search the " .. noun .. ". M1 will hide things worth finding.")
	else
		say("The spike does not know that one yet.")
	end
end

-- ------------------------------------------------------------- the Composer
local LANES = { "EXITS", "VERBS", "NOUNS" }
local VERBS = { "look", "examine", "take", "search", "inventory" }
local lane = 1
local sel = { 1, 1, 1 }
local command = {}

local function laneWords()
	if lane == 1 then
		local out = {}
		for dir in pairs(rooms[here].exits) do out[#out + 1] = dir end
		table.sort(out)
		return out
	elseif lane == 2 then
		return VERBS
	end
	return rooms[here].nouns
end

local function submitReady()
	if #command == 0 then return false end
	local v = command[1]
	if v == "look" or v == "inventory" or v == "go" and command[2] then
		return true
	end
	return #command >= 2
end

local function pressA()
	local words = laneWords()
	if #words == 0 then return end
	local word = words[((sel[lane] - 1) % #words) + 1]
	if lane == 1 and #command == 0 then
		doCommand({ "go", word }) -- an exit alone IS the command
		return
	end
	command[#command + 1] = word
	if submitReady() then
		doCommand(command)
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

-- ------------------------------------------------------------- input + draw
local function update()
	-- crank scrolls the active lane; six detents per revolution feels
	-- like a ratchet (Designing for Playdate: give the crank teeth)
	local ticks = playdate.getCrankTicks(6)
	if ticks ~= 0 then sel[lane] += ticks end

	if playdate.buttonJustPressed(playdate.kButtonLeft) then
		lane = ((lane - 2) % #LANES) + 1
	elseif playdate.buttonJustPressed(playdate.kButtonRight) then
		lane = (lane % #LANES) + 1
	elseif playdate.buttonJustPressed(playdate.kButtonUp) then
		scrollUp += 40
	elseif playdate.buttonJustPressed(playdate.kButtonDown) then
		scrollUp = math.max(0, scrollUp - 40)
	elseif playdate.buttonJustPressed(playdate.kButtonA) then
		pressA()
	elseif playdate.buttonJustPressed(playdate.kButtonB) then
		pressB()
	end

	gfx.clear(gfx.kColorBlack)
	gfx.setImageDrawMode(gfx.kDrawModeFillWhite)

	-- the transcript, bottom-anchored, clipped to its pane
	gfx.setClipRect(0, 0, SCREEN_W, TRANS_H)
	local total = 0
	for i = 1, #transcript do total += transcript[i].h end
	local y = TRANS_H - MARGIN - total + scrollUp
	if total < TRANS_H - MARGIN * 2 then y = MARGIN end
	for i = 1, #transcript do
		local e = transcript[i]
		if y + e.h > 0 and y < TRANS_H then
			gfx.drawTextInRect(e.text, MARGIN, y, SCREEN_W - MARGIN * 2, e.h)
		end
		y += e.h
	end
	gfx.clearClipRect()

	-- the rule, and the command line being composed
	gfx.drawLine(0, TRANS_H + 2, SCREEN_W, TRANS_H + 2)
	local composed = "> " .. table.concat(command, " ") .. "_"
	gfx.drawText(composed, MARGIN, TRANS_H + 8)

	-- lane tabs: the active lane reads inverted
	local tabX = MARGIN
	for i = 1, #LANES do
		local label = LANES[i]
		local w, h = gfx.getTextSize(label)
		if i == lane then
			gfx.fillRect(tabX - 2, TRANS_H + 28, w + 6, h + 2)
			gfx.setImageDrawMode(gfx.kDrawModeFillBlack)
			gfx.drawText(label, tabX + 1, TRANS_H + 29)
			gfx.setImageDrawMode(gfx.kDrawModeFillWhite)
		else
			gfx.drawText(label, tabX + 1, TRANS_H + 29)
		end
		tabX += w + 18
	end

	-- the word wheel: three visible, selected centered and marked
	local words = laneWords()
	local wheelY = TRANS_H + 50
	for row = -1, 1 do
		if #words > 0 then
			local idx = ((sel[lane] - 1 + row) % #words) + 1
			local marker = row == 0 and "> " or "  "
			gfx.drawText(marker .. words[idx], MARGIN + 8, wheelY + (row + 1) * 15)
		end
	end

	playdate.drawFPS(378, 224)
end

function playdate.update()
	update()
end

say("TOMB OF NASSAK AN-RAH -- a Vaults of Vaarn expedition (M0 spike)")
say("Crank scrolls the word lane. Left/right picks a lane. A speaks. B unsays.")
describe()
