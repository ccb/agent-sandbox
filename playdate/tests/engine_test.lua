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
g.player.location.blocks.west = "A test wall refuses you, in-fiction."
g:doCommand("west")
ok(saw(lines, "test wall refuses"), "blocks still refuse in-fiction")
g.player.location.blocks.west = nil
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
sug = g:suggestions()
ok(has(sug.nouns, "glowstone"), "revealed glowstone joins the lane")
g:doCommand("take waterskin")
ok(saw(lines, "inheritance of water"), "the take pays its award (web parity)")
ok(g.score == 5, "score banks")
g:doCommand("drop waterskin")
g:doCommand("take waterskin")
ok(g.score == 5, "award is idempotent")
g:doCommand("drop waterskin")

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
ok(g.score == 20, "this run banks 20 of 25 (the colony went unfed)")
g:doCommand("look")
g:doCommand("look")
ok(g.wounds <= 1, "a dead spawn lashes no one")

-- bare hands are refused; the pool hides attack when nothing is hostile
g, lines = game()
sug = g:suggestions()
ok(not has(sug.verbs, "attack"), "no fight, no fight verbs")

print("warriors slice: all green")

-- --------------------------------------------- the canopic ending + cues
g, lines = game()
g:doCommand("search merchant")
g:doCommand("take glowstone")
g:doCommand("light glowstone")
g:doCommand("in")
g:doCommand("take dates")
g:doCommand("out")
g:doCommand("go north")
g:doCommand("go east")
g:doCommand("search cylinders")
g:doCommand("take prismatic blade")
g:doCommand("attack spawn of guts")
g:doCommand("attack spawn of guts")
g:doCommand("take falcon jar")
g:doCommand("go west")
g:doCommand("go north")
g:doCommand("throw dates")
ok(g.figuresShown and g.figuresShown["bats-c"], "the feast cues its card")
g:doCommand("go north")
g:doCommand("go east")
g:doCommand("put falcon jar on falcon plinth")
ok(saw(lines, "crimson steadies to white"), "the falcon plinth answers its jar")
ok(not saw(lines, "seal answers the jars"), "one jar does not pay the seal")
ok(not g.won, "one jar wins nothing")
ok(g.player.location.connections["up"] == nil, "the stair keeps waiting")

-- the wrong offering is returned
g, lines = game()
g:doCommand("in")
g:doCommand("take dates")
g:doCommand("out")
g:doCommand("go north")
-- (dark halls: travel through unlit is allowed; the canopic path needs light
-- only for aiming, not walking)
g:doCommand("go north")
g:doCommand("go north")
g:doCommand("go east")
g:doCommand("put dates on falcon plinth")
ok(saw(lines, "talons refuse it"), "the plinth wants one thing")
ok(g.player:carrying("dates") ~= nil, "refused offerings come back")

-- death cues the epitaph with the honest ledger
g, lines = game()
g:doCommand("search merchant")
g:doCommand("take glowstone")
g:doCommand("go north")
g:doCommand("go east")
for _ = 1, 7 do g:doCommand("look") end
ok(g.over, "the spawn finishes the careless")
ok(g.figuresShown and g.figuresShown["epitaph"], "death cues the stone")

print("canopic + cues: all green")

-- ------------------------------------------------------- the hint booklet
g, lines = game()
g:doCommand("hint")
ok(saw(lines, "see anything down here"), "the light question is always met")
ok(not saw(lines, "falcon jar for"), "unmet puzzles stay off the menu")
sug = g:suggestions()
ok(has(sug.verbs, "light") and has(sug.verbs, "resume"),
	"hint mode fills the wheel with topics")
local t0 = g.turn
g:doCommand("light")
ok(saw(lines, "did not die carrying nothing"), "one ask, one level")
ok(not saw(lines, "SEARCH the dead merchant"), "level two stays unbought")
g:doCommand("light")
ok(saw(lines, "SEARCH the dead merchant"), "the second ask buys it")
ok(g.turn == t0, "the booklet is free: no turns passed")
ok(g.hintsTaken == 2, "the game owns up to the hints")
g:doCommand("resume")
ok(not g.hintMode, "resume closes the booklet")

-- solved topics leave; replay restores the reveals
g:doCommand("search merchant")
g:doCommand("take glowstone")
g:doCommand("light glowstone")
g:doCommand("hint")
local lightOpen = false
for _, h in ipairs(g:openHints()) do
	if h.key == "light" then lightOpen = true end
end
ok(not lightOpen, "solved topics leave the menu")
g:doCommand("resume")
local snap3 = g:snapshot()
local g4 = Engine.restore(function(seed)
	local gg = BuildTomb(seed)
	gg.out = function() end
	return gg
end, snap3)
ok(g4.hintProgress["light"] == 2, "replay restores the reveals")
ok(g4.hintsTaken == 2, "replay restores the honesty counter")
ok(not g4.hintMode, "replay closes the booklet it opened")

print("hints: all green")

-- ---------------------------------------------- the march: the full tomb
g, lines = game()
g:doCommand("search merchant")
g:doCommand("take glowstone")
g:doCommand("light glowstone")
g:doCommand("go north")
g:doCommand("go east")
g:doCommand("search cylinders")
g:doCommand("take prismatic blade")
g:doCommand("attack spawn of guts")
g:doCommand("attack spawn of guts")
g:doCommand("take falcon jar")
-- the guards' kit: the mask spares the chimney, the boots anchor the pry
g:doCommand("break amber cylinder")
g:doCommand("take respirator")
g:doCommand("wear respirator")
g:doCommand("break viridian cylinder")
g:doCommand("take magnetic boots")
g:doCommand("wear magnetic boots")
-- the hall of hounds: the listener, and the second jar
g:doCommand("go east")
ok(saw(lines, "precise as a metronome"), "the brain marks you")
g:doCommand("attack spawn of brain")
g:doCommand("attack spawn of brain")
ok(saw(lines, "jackal jar rolls"), "the brain gives up its hat")
g:doCommand("take jackal jar")
ok(saw(lines, "jackal jar, claimed"), "the jar pays")
g:doCommand("search cyborg hound")
ok(saw(lines, "sparking servo"), "the hound keeps a servo")
-- the summit and the chimney
g:doCommand("go west")
g:doCommand("go west")
g:doCommand("go up")
g:doCommand("search ossified corpse")
g:doCommand("take friend's fungus")
ok(g.player:carrying("friend's fungus") ~= nil, "the mystic held the pouch")
local w0 = g.wounds
g:doCommand("in")
ok(g.wounds == w0 + 1, "the chimney bites once, cold")
g:doCommand("attack glass centipede")
ok(saw(lines, "dropped icicle"), "one clean blow answers it")
-- the seal wants BOTH jars
g:doCommand("out")
g:doCommand("go down")
g:doCommand("go north")
g:doCommand("go north")
g:doCommand("go east")
g:doCommand("put falcon jar on falcon plinth")
ok(g.player.location.connections["up"] == nil, "one jar is not enough")
g:doCommand("put jackal jar on jackal plinth")
ok(saw(lines, "every plinth answers at once"), "both jars open the seal")
ok(g.player.location.connections["up"] ~= nil, "the stair stands open")
-- the balm heals the venom before the coil can press
g:doCommand("go up")
g:doCommand("pry coffin")
g:doCommand("read prayers")
g:doCommand("say prayer of balm")
ok(saw(lines, "A wound closes, politely"), "the balm closes a wound"
	.. " (the coil may press the same round -- net is the fiction's problem)")
g:doCommand("say prayer of wrath")
ok(g.scoredKeys["horror"] == true, "the chamber's law ends the Horror")
ok(not g.won, "the win waits at the door (web parity: OUT, alive, carrying)")
g:doCommand("take dagger")
g:doCommand("take manifold box")
g:doCommand("go down")
g:doCommand("go west")
g:doCommand("go south")
g:doCommand("go south")
ok(g.won, "out alive with the Exotica: the tomb is quiet")
print("full tomb: all green")

-- ------------------------------------------------------------- sneaking
g, lines = game()
g:doCommand("search merchant")
g:doCommand("take glowstone")
g:doCommand("light glowstone")
g:doCommand("go north")
g:doCommand("sneak east")
ok(g.player.location.name == "hall of warriors", "sneak moves")
ok(not saw(lines, "swings toward your noise"), "quiet feet wake nothing")
g:doCommand("sneak west")
ok(g.wounds == 0, "in and out, unheard, unhurt")
g:doCommand("go east")
ok(saw(lines, "swings toward your noise"), "loud feet still pay the toll")
-- the chimney's ambush also respects quiet -- for one round
g, lines = game()
g:doCommand("go north")
g:doCommand("go up")
g:doCommand("sneak in")
ok(g.wounds == 1, "quiet slips the glass but not the spores (web parity: "
	.. "unmasked lungs pay at the door)")
g:doCommand("look")
ok(g.wounds == 2, "the next loud act springs the centipede")
print("sneak: all green")

-- ---------------------------------------------------------------- break
g, lines = game()
g:doCommand("search merchant")
g:doCommand("take glowstone")
g:doCommand("light glowstone")
g:doCommand("go north")
g:doCommand("go east")
sug = g:suggestions()
for _, cyl in ipairs({ "cylinders", "cerulean cylinder", "amber cylinder",
	"viridian cylinder", "orange cylinder" }) do
	ok(has(sug.nouns, cyl), "on the wheel: " .. cyl)
end
ok(has(sug.verbs, "break"), "break is on the combat wheel too")
g:doCommand("break amber cylinder")
ok(saw(lines, "marching kit spills"), "the amber cylinder gives up its kit")
g:doCommand("take preserved rations")
ok(g.player:carrying("preserved rations") ~= nil, "the rations are real")
local wB = g.wounds
g:doCommand("break orange cylinder")
ok(g.wounds == wB + 1, "the orange cylinder files a claim")
g:doCommand("break cylinders")
ok(saw(lines, "sturdier than your opinion"), "unbreakables refuse politely")
print("break: all green")

-- ------------------------------------------- the rest of the game
g, lines = game()
g:doCommand("examine self")
ok(saw(lines, "You are a"), "the chargen's afterlife answers")
g:doCommand("search merchant")
g:doCommand("take glowstone")
g:doCommand("take waterskin")
g:doCommand("taste glowstone")
ok(saw(lines, "nine-volt battery"), "the glowstone tastes as it should")
g:doCommand("in")
g:doCommand("take dates")
g:doCommand("eat dates")
ok(g.player:carrying("dates") ~= nil, "the ceiling outvotes your appetite")
g:doCommand("out")
-- butchery opens the ledger; tribute closes it
g:doCommand("light glowstone")
g:doCommand("go north")
g:doCommand("go east")
g:doCommand("search cylinders")
g:doCommand("take prismatic blade")
g:doCommand("attack spawn of guts")
g:doCommand("attack spawn of guts")
g:doCommand("go west")
g:doCommand("go south")
g:doCommand("butcher zoxen")
ok(saw(lines, "noses lift"), "meat has listeners")
g:doCommand("take zox haunch")
ok(saw(lines, "arithmetic in it"), "the pack arrives with its ledger")
ok(g:mode() == "combat", "a pack doing sums is combat")
g:doCommand("give zox haunch to jackal pack")
ok(saw(lines, "ledger reads: paid"), "the tribute settles it")
ok(g.score >= 20, "the settlement paid")
-- a wound, and three ways to drink it away
g.wounds = 1
g:doCommand("drink waterskin")
ok(g.wounds == 0, "water does what water does")
print("rest-of-game systems: all green")
