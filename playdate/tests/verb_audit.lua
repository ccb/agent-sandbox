-- The VERB audit: every verb in the registry must (a) appear on a wheel the
-- player can actually reach (default lane, a modal pool, or the booklet),
-- and (b) execute successfully in at least one scripted real context.
-- A verb that exists but never surfaces is dead weight; a verb that
-- surfaces but has no working use is a lie. Run: lua playdate/tests/verb_audit.lua

dofile("playdate/Source/engine/core.lua")
dofile("playdate/Source/content/slice.lua")

local function has(list, w)
	for i = 1, #list do if list[i] == w then return true end end
	return false
end

-- (a) LANE PRESENCE ---------------------------------------------------------
local g = BuildTomb(5)
g.out = function() end

local registry = {}
for i = 1, #Engine.verbs do registry[#registry + 1] = Engine.verbs[i] end

local defaultLane = g:suggestions().verbs
-- reach combat: walk at the spawn loudly
g:doCommand("search merchant"); g:doCommand("take glowstone")
g:doCommand("light glowstone"); g:doCommand("go north"); g:doCommand("go east")
assert(g:mode() == "combat", "audit setup: combat should be live")
local combatLane = g:suggestions().verbs

local unreachable = {}
for i = 1, #registry do
	local v = registry[i]
	if not has(defaultLane, v.name) and not has(combatLane, v.name) then
		unreachable[#unreachable + 1] = v.name
	end
end
assert(#unreachable == 0,
	"verbs on NO reachable wheel: " .. table.concat(unreachable, ", "))
print("lane presence: " .. #registry .. " verbs, all reachable "
	.. "(" .. #defaultLane .. " default, " .. #combatLane .. " combat)")

-- (b) ONE WORKING USE EACH --------------------------------------------------
local uses = {
	{ "look", nil },
	{ "examine", "examine wreck" },
	{ "search", "search dead merchant" },
	{ "take", "take glowstone" },
	{ "drop", "drop glowstone" },
	{ "light", "light glowstone" },
	{ "douse", "douse glowstone" },
	{ "inventory", "inventory" },
	{ "taste", "taste glowstone" },
	{ "talk to", "talk to critch" },
	{ "sneak", "sneak in" },
	{ "read", nil }, -- exercised below, in the sphere
	{ "eat", nil }, -- rations, below
	{ "drink", "drink waterskin" },
	{ "butcher", nil }, -- below, with the blade
	{ "break", nil }, -- below, in the hall
	{ "throw", nil }, -- dates, below
	{ "give", nil }, -- tribute, below
	{ "put", nil }, -- the plinths, below
	{ "attack", nil }, -- the spawn, below
	{ "pry", nil }, -- the coffin, below
	{ "say", nil }, -- the prayers, below
	{ "hint", "hint" },
}
local g2 = BuildTomb(5)
local out = {}
g2.out = function(t) out[#out + 1] = t end
local exercised = {}
local function run(verbName, cmd)
	assert(g2:doCommand(cmd),
		"verb '" .. verbName .. "' failed its context: " .. cmd)
	exercised[verbName] = true
end
run("look", "look")
run("wait", "wait")
run("help", "help")
run("feel", "feel")
run("listen", "listen")
run("smell", "smell")
run("hint", "hint")
run("hint-resume", "resume")
run("examine", "examine wreck")
run("search", "search dead merchant")
run("take", "take glowstone")
run("taste", "taste glowstone")
run("drop", "drop glowstone")
run("take", "take glowstone")
run("take", "take waterskin")
run("drink", "drink waterskin")
run("light", "light glowstone")
run("douse", "douse glowstone")
run("light", "light glowstone")
run("inventory", "inventory")
run("talk to", "talk to critch")
run("go", "in")
run("take", "take dates")
run("open", "open crates")
run("take", "take bolt of spider-silk")
run("go", "out")
run("go", "go north")
run("sneak", "sneak east")
run("search", "search cylinders")
run("take", "take prismatic blade")
run("attack", "attack spawn of guts")
run("attack", "attack spawn of guts")
run("open", "open falcon jar")
run("break", "break amber cylinder")
run("take", "take respirator")
run("wear", "wear respirator")
run("break", "break orange cylinder")
run("take", "take plasma-igniter")
run("eat-rations", "take preserved rations")
run("eat", "eat preserved rations")
run("close", "close falcon jar")
run("wield", "wield prismatic blade")
run("take", "take falcon jar")
run("go", "go west")
run("go", "go south")
run("butcher", "butcher zoxen")
run("take", "take zox haunch")
run("give", "give zox haunch to jackal pack")
run("go", "go north")
run("go", "go north")
run("throw", "throw dates")
run("go", "go north")
run("remember", "remember") -- the lattice answers in the hall of memory
run("go", "go east")
run("put", "put falcon jar on falcon plinth")
-- the burn path: gel from the hounds, spark from the guards, fire at the crown
local function roomNamed(name)
	for i = 1, #g2.rooms do
		if g2.rooms[i].name == name then return g2.rooms[i] end
	end
end
g2.player.location = roomNamed("hall of hounds")
run("take", "take flask of gel")
g2.player.location = roomNamed("the summit")
run("burn", "burn ossified corpse")
-- the sphere set (jackal jar skipped: this run tests verbs, not the win)
g2.player.location = g2.rooms[#g2.rooms] -- the sphere is built last
run("open-redirect", "open coffin")
run("tie", "tie coffin") -- the silk from the hold answers zero gravity
run("pry", "pry coffin")
run("read", "read prayers")
run("say", "say prayer of balm")
run("say", "say prayer of wrath")
run("say", "say prayer of mending")

local unexercised = {}
for i = 1, #registry do
	if not exercised[registry[i].name] then
		unexercised[#unexercised + 1] = registry[i].name
	end
end
assert(#unexercised == 0,
	"verbs with no working use: " .. table.concat(unexercised, ", "))
print("working use: every verb exercised in a real context")
print("verb audit: ALL GREEN")
