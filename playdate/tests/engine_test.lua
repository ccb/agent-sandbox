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
g:doCommand("up")
ok(saw(lines, "climb waits"), "blocks still refuse in-fiction")
g:doCommand("enter tomb")
ok(g.player.location.name == "hall of youth", "travel alias walks the boy's door")
ok(saw(lines, "Dark as a pocket"), "the hall opens dark")
g:doCommand("south")
g:doCommand("south")
ok(g.player.location.name == "the caravan wreck", "bare exit words walk home")
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

-- ---------------------------------------------------- the Hall of Youth
-- darkness is honest: no nouns, no room text, the blurb instead
g, lines = game()
g:doCommand("go north")
g:doCommand("go north")
ok(g.player.location.name == "hall of youth", "the boy's door opens")
ok(saw(lines, "Dark as a pocket"), "dark rooms give the blurb")
sug = g:suggestions()
ok(not has(sug.nouns, "statues"), "darkness keeps nouns off the lane")

-- light earns the look, the award -- and the colony's attention
g, lines = game()
g:doCommand("search merchant")
g:doCommand("take glowstone")
g:doCommand("go north")
g:doCommand("go north")
g:doCommand("light glowstone")
ok(saw(lines, "light, learned"), "first light pays")
ok(saw(lines, "statues of the boy-Autarch"), "light earns the room's look")
ok(saw(lines, "rustle overhead deepens"), "the colony gives one warning")
g:doCommand("look")
ok(g.wounds == 1, "the second lit round wounds")
g:doCommand("douse glowstone")
ok(saw(lines, "Dark as a pocket"), "dousing narrates the dark")
g:doCommand("look")
ok(g.wounds == 1, "dark means unseen: no wound")

-- the dates puzzle settles the colony for good
g, lines = game()
g:doCommand("search merchant")
g:doCommand("take glowstone")
g:doCommand("in")
g:doCommand("take dates")
g:doCommand("out")
g:doCommand("go north")
g:doCommand("go north")
g:doCommand("light glowstone")
g:doCommand("throw dates")
ok(saw(lines, "ceiling DETACHES"), "the colony takes the dates")
ok(saw(lines, "colony, fed"), "the feast pays")
ok(g.score == 15, "full slice score")
g:doCommand("look")
g:doCommand("look")
ok(g.wounds == 0, "a fed colony has no opinions about light")

-- death, and the gate on the dead
g, lines = game()
g:doCommand("search merchant")
g:doCommand("take glowstone")
g:doCommand("go north")
g:doCommand("go north")
g:doCommand("light glowstone")
g:doCommand("look")
g:doCommand("look")
g:doCommand("look")
ok(g.wounds >= 3 and g.over, "three rakings end the expedition")
local before = g.turn
g:doCommand("look")
ok(g.turn == before, "the dead take no turns")

-- replay carries the whole slice state: wounds, fed colony, score
g, lines = game()
g:doCommand("search merchant")
g:doCommand("take glowstone")
g:doCommand("in")
g:doCommand("take dates")
g:doCommand("out")
g:doCommand("go north")
g:doCommand("go north")
g:doCommand("light glowstone")
g:doCommand("throw dates")
local snap2 = g:snapshot()
local g3 = Engine.restore(function(seed)
	local gg = BuildTomb(seed)
	gg.out = function() end
	return gg
end, snap2)
ok(g3.score == 15, "replay: feast score")
ok(g3.player.location.name == "hall of youth", "replay: location")
ok(g3.wounds == g.wounds, "replay: wounds")

print("youth slice: all green")

-- ------------------------------------------------- M2: templates and talk
g, lines = game()
g:doCommand("talk to critch")
ok(saw(lines, "ceiling has opinions about light"), "Critch talks, and hints")
g:doCommand("look")
g:doCommand("look")
local gone = true
for i = 1, #g.player.location.characters do
	if g.player.location.characters[i].name == "critch" then gone = false end
end
ok(gone, "the teamster decamps after speaking")
ok(saw(lines, "does not look back"), "the departure narrates")

g, lines = game()
g:doCommand("in")
g:doCommand("take dates")
g:doCommand("out")
g:doCommand("give dates to critch")
ok(saw(lines, "Feed the ceiling"), "GIVE _ TO _ parses and Critch declines with the hint")
ok(g.player:carrying("dates") ~= nil, "declined gifts stay carried")
g:doCommand("give dates to zoxen")
ok(saw(lines, "wants nothing of yours"), "giving to the unreceptive defaults politely")

-- the composer's slot walk exposes the template
local slots = Engine.verbSlots("give")
ok(#slots == 3 and slots[2] == "to", "give walks noun-to-noun")
ok(#Engine.verbSlots("look") == 0, "look walks nothing")

print("M2 templates: all green")

-- --------------------------------------------- the Hall of Warriors
-- the spawn hunts sound: dark or lit, presence is noise
g, lines = game()
g:doCommand("search merchant")
g:doCommand("take glowstone")
g:doCommand("go north")
g:doCommand("go east")
ok(saw(lines, "swings toward your noise"), "one warning, even in the dark")
ok(g:mode() == "combat", "an aware hunter means combat mode")
sug = g:suggestions()
ok(sug.verbs[1] == "attack", "combat pool leads with attack")
ok(not has(sug.nouns, "spawn of guts"), "but the dark still hides your target")
g:doCommand("look")
ok(saw(lines, "It is deciding"), "the even rounds menace without landing")
g:doCommand("look")
ok(g.wounds == 1, "the odd rounds lash")

-- lit, armed, and answered
g, lines = game()
g:doCommand("search merchant")
g:doCommand("take glowstone")
g:doCommand("light glowstone")
g:doCommand("go north")
g:doCommand("go east")
g:doCommand("search cylinders")
ok(saw(lines, "prismatic blade"), "the burst cylinder gives up the blade")
g:doCommand("take blade")
g:doCommand("attack spawn")
ok(saw(lines, "does not fall"), "the first cut is answered")
g:doCommand("attack spawn")
ok(saw(lines, "falcon jar topples"), "the second cut fells it")
ok(saw(lines, "spawn of guts is quelled"), "the quelling pays")
ok(g:mode() == "default", "the fight over, the fight verbs go home")
g:doCommand("take jar")
ok(saw(lines, "falcon jar, claimed"), "the jar pays")
ok(g.score == 25, "the full slice banks 25")
g:doCommand("look")
g:doCommand("look")
ok(g.wounds <= 1, "a dead spawn lashes no one")

-- bare hands are refused; the pool hides attack when nothing is hostile
g, lines = game()
sug = g:suggestions()
ok(not has(sug.verbs, "attack"), "no fight, no fight verbs")

print("warriors slice: all green")
