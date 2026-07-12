-- The coverage audit (M2.5): every command in the WIN walkthrough must be
-- COMPOSABLE -- producible by the wheel from that turn's suggestions --
-- before it executes. A verb or noun the composer cannot offer fails here,
-- in CI, not on a player's device. Run: lua playdate/tests/audit_test.lua

dofile("playdate/Source/engine/core.lua")
dofile("playdate/Source/content/slice.lua")

local function has(list, word)
	for i = 1, #list do if list[i] == word then return true end end
	return false
end

local function composable(g, line)
	local sug = g:suggestions()
	local dir = line:match("^go%s+(.+)$") or line
	if has(sug.exits, dir) then return true end
	if g.player.location.directionAliases[line] then return true end
	-- longest verb name/phrase that prefixes the line
	local verb, rest = nil, nil
	for i = 1, #sug.verbs do
		local v = sug.verbs[i]
		if line == v or line:sub(1, #v + 1) == v .. " " then
			if not verb or #v > #verb then
				verb = v
				rest = line:sub(#v + 2)
			end
		end
	end
	if not verb then return false, "verb not on the wheel" end
	local slots = Engine.verbSlots(verb)
	if #slots == 0 then return rest == nil or rest == "" end
	if #slots == 1 then
		return has(sug.nouns, rest), "noun not on the wheel: " .. tostring(rest)
	end
	local connector = slots[2]
	local a, b = rest:match("^(.-)%s+" .. connector .. "%s+(.+)$")
	if not a then return false, "template did not split" end
	if not has(sug.nouns, a) then return false, "noun not on the wheel: " .. a end
	if not has(sug.nouns, b) then return false, "noun not on the wheel: " .. b end
	return true
end

local WIN = {
	"talk to critch",
	"search dead merchant",
	"take glowstone",
	"take waterskin",
	"light glowstone",
	"in",
	"take dates",
	"out",
	"go north",
	"go east",
	"search cylinders",
	"take prismatic blade",
	"attack spawn of guts",
	"attack spawn of guts",
	"take falcon jar",
	"break amber cylinder",
	"take respirator",
	"wear respirator",
	"break viridian cylinder",
	"take magnetic boots",
	"wear magnetic boots",
	"go east",
	"attack spawn of brain",
	"attack spawn of brain",
	"take jackal jar",
	"go west",
	"go west",
	"go up",
	"search ossified corpse",
	"take friend's fungus",
	"in",
	"attack glass centipede",
	"out",
	"drink waterskin",
	"go down",
	"go south",
	"butcher zoxen",
	"take zox haunch",
	"give zox haunch to jackal pack",
	"take zox blood",
	"go north",
	"go north",
	"throw dates",
	"go north",
	"talk to silas",
	"give friend's fungus to silas",
	"remember",
	"remember",
	"remember",
	"remember",
	"go east",
	"put falcon jar on falcon plinth",
	"put jackal jar on jackal plinth",
	"go up",
	"pry coffin",
	"read prayers",
	"say prayer of balm",
	"say prayer of wrath",
	"search coffin",
	"take manifold box",
	"take synth-hunting dagger",
	"light ulfire lantern",
	"take ego-core",
	"go down",
	"go west",
	"give ego-core to silas",
	"go east",
	"go up",
	"say prayer of mending",
	"go down",
	"go west",
	"go south",
	"go south",
}

local g = BuildTomb(3)
g.out = function() end
for i = 1, #WIN do
	local okc, why = composable(g, WIN[i])
	if not okc then
		error("NOT COMPOSABLE at step " .. i .. " ('" .. WIN[i] .. "'): "
			.. tostring(why))
	end
	g:doCommand(WIN[i])
end
assert(g.score == g.maxScore,
	"walkthrough banks " .. g.score .. " of " .. g.maxScore)
assert(not g.over, "the winner lives")
assert(g.won, "the winner won")
print("audit: every step composable; " .. g.score .. "/" .. g.maxScore
	.. " in " .. g.turn .. " turns; wounds " .. g.wounds)
