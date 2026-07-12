-- The parity harness (M1): plain-lua tests over the playdate-free engine.
-- Run: lua playdate/tests/engine_test.lua
-- The same files compile under pdc; anything asserted here holds on device.

dofile("playdate/Source/engine/core.lua")
dofile("playdate/Source/content/slice.lua")

local passed = 0
local function ok(cond, label)
	if not cond then error("FAIL: " .. label, 2) end
	passed = passed + 1
end

local function game()
	local g = BuildTomb(7)
	local lines = {}
	g.out = function(text) lines[#lines + 1] = text end
	return g, lines
end

local function saw(lines, frag)
	for i = 1, #lines do
		if string.find(lines[i], frag, 1, true) then return true end
	end
	return false
end

-- movement, aliases, blocks
local g, lines = game()
g:doCommand("go north")
ok(g.player.location.name == "tomb exterior", "go north moves")
g:doCommand("enter tomb")
ok(saw(lines, "boy's door"), "travel alias hits the block line")
g:doCommand("south")
ok(g.player.location.name == "the caravan wreck", "bare exit word moves")
g:doCommand("wagon")
ok(g.player.location.name == "the wagon's hold", "playtester alias enters the hold")
g:doCommand("leave")
ok(g.player.location.name == "the caravan wreck", "leave exits the hold")

-- search reveals; hidden stays honest before that
g, lines = game()
local sug = g:suggestions()
local function has(list, word)
	for i = 1, #list do if list[i] == word then return true end end
	return false
end
ok(not has(sug.nouns, "glowstone"), "hidden glowstone stays off the lane")
g:doCommand("search merchant")
ok(saw(lines, "inheritance of water"), "the search pays its award")
ok(g.score == 5, "score banks")
g:doCommand("search merchant")
ok(g.score == 5, "award is idempotent")
sug = g:suggestions()
ok(has(sug.nouns, "glowstone"), "revealed glowstone joins the lane")

-- take/drop/inventory, container reach
g:doCommand("take glowstone")
ok(g.player:carrying("glowstone") ~= nil, "take moves it to the pack")
g:doCommand("inventory")
ok(saw(lines, "dim glowstone"), "inventory lists it")
g:doCommand("drop glowstone")
ok(g.player:carrying("glowstone") == nil, "drop lets it go")
g:doCommand("in")
g:doCommand("take dates")
ok(g.player:carrying("dates") ~= nil, "an open crate's dates are reachable")

-- examine + aliases
g, lines = game()
g:doCommand("x merchant")
ok(saw(lines, "ledger neat"), "x examines")
g:doCommand("examine zox")
ok(saw(lines, "Salt-heavy"), "noun alias answers")

-- the whole save contract: replay rebuilds identical state
g, lines = game()
g:doCommand("search merchant")
g:doCommand("take glowstone")
g:doCommand("go north")
local snap = g:snapshot()
local g2 = Engine.restore(function(seed)
	local gg = BuildTomb(seed)
	gg.out = function() end
	return gg
end, snap)
ok(g2.player.location.name == g.player.location.name, "replay: location")
ok(g2.score == g.score, "replay: score")
ok(g2.turn == g.turn, "replay: turn")
ok(g2.player:carrying("glowstone") ~= nil, "replay: inventory")

-- suggestions stay honest about arity + verbs
ok(Engine.verbArity("look") == 0, "look submits alone")
ok(Engine.verbArity("take") == 1, "take waits for a noun")

print("engine_test: " .. passed .. " assertions passed")
