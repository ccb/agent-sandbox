-- The mini-engine (M1): rooms, things, verbs, journal -- the playdate-free
-- core of the Tomb port (docs/design/playdate.md section 4). Pure Lua 5.4:
-- no playdate APIs, no `+=`, so the same file runs under pdc on device and
-- under plain lua in the parity harness (tests/engine_test.lua).
--
-- The Python engine remains the source of truth; this mirrors its shapes
-- (properties, scope, journal replay, idempotent awards) small enough for a
-- 168 MHz handheld. One global namespace: Engine.

Engine = {}

local function class(parent)
	local c = {}
	c.__index = c
	setmetatable(c, {
		__index = parent,
		__call = function(cls, ...)
			local o = setmetatable({}, cls)
			o:init(...)
			return o
		end,
	})
	return c
end
Engine.class = class

-- ------------------------------------------------------------------ things
local Thing = class()
Engine.Thing = Thing

function Thing:init(name, description, examine)
	self.name = string.lower(name)
	self.description = description
	self.examineText = examine or description
	self.properties = {}
	self.aliases = {}
	self.contents = {} -- ordered: description order IS lane order
end

function Thing:set(k, v) self.properties[k] = v end
function Thing:get(k) return self.properties[k] end

function Thing:alias(...)
	local names = { ... }
	for i = 1, #names do
		self.aliases[#self.aliases + 1] = string.lower(names[i])
	end
	return self
end

function Thing:answersTo(word)
	word = string.lower(word)
	if self.name == word then return true end
	for i = 1, #self.aliases do
		if self.aliases[i] == word then return true end
	end
	return false
end

function Thing:add(item)
	self.contents[#self.contents + 1] = item
	item.holder = self
	return self
end

function Thing:remove(item)
	for i = 1, #self.contents do
		if self.contents[i] == item then
			table.remove(self.contents, i)
			item.holder = nil
			return true
		end
	end
	return false
end

-- What a look can reach inside this thing: nothing while closed, and
-- hidden things stay hidden until SEARCH lifts them.
function Thing:accessible()
	local out = {}
	if self:get("closed") then return out end
	for i = 1, #self.contents do
		if not self.contents[i]:get("hidden") then
			out[#out + 1] = self.contents[i]
		end
	end
	return out
end

-- --------------------------------------------------------------- character
local Character = class(Thing)
Engine.Character = Character

function Character:init(name, description, examine)
	Thing.init(self, name, description, examine)
	self.location = nil
end

function Character:carrying(word)
	for i = 1, #self.contents do
		if self.contents[i]:answersTo(word) then return self.contents[i] end
	end
	return nil
end

-- ---------------------------------------------------------------- location
local Location = class(Thing)
Engine.Location = Location

function Location:init(name, description)
	Thing.init(self, name, description)
	self.connections = {} -- dir -> Location
	self.directionAliases = {} -- exact phrase -> dir
	self.blocks = {} -- dir -> refusal line
	self.characters = {}
	self.visited = false
end

function Location:connect(dir, dest, backDir)
	self.connections[dir] = dest
	if backDir then dest.connections[backDir] = self end
	return self
end

function Location:travelAlias(phrase, dir)
	self.directionAliases[string.lower(phrase)] = dir
	return self
end

function Location:addCharacter(c)
	self.characters[#self.characters + 1] = c
	c.location = self
end

function Location:exitNames()
	local out = {}
	for dir in pairs(self.connections) do out[#out + 1] = dir end
	table.sort(out)
	return out
end

-- -------------------------------------------------------------------- game
local Game = class()
Engine.Game = Game

function Game:init(seed)
	self.seed = seed or 0
	self.rooms = {}
	self.turn = 0
	self.score = 0
	self.maxScore = 0
	self.scoredKeys = {}
	self.journal = {}
	self.quiet = false
	self.over = false
	self.wounds = 0
	self.triggers = {}
	-- InvisiClues, in-engine (ported from the Python hints.py): topics the
	-- player has MET and not yet beaten; each ask reveals one more level.
	self.hints = {}
	self.hintProgress = {}
	self.hintsTaken = 0
	self.hintMode = false
	self.out = function(_text) end -- the surface's renderer hooks this
	self.player = Character("you", "you, a scavenger of the Tomblands")
end

-- React phase: fired after every executed command (also during replay --
-- determinism is the save system). Same shape as the Python engine.
function Game:addTrigger(name, pred, effect, repeatable)
	self.triggers[#self.triggers + 1] =
		{ name = name, pred = pred, effect = effect, repeatable = repeatable, done = false }
end

function Game:runTriggers()
	for i = 1, #self.triggers do
		local t = self.triggers[i]
		if (t.repeatable or not t.done) and t.pred(self) then
			t.done = true
			t.effect(self)
			if self.over then return end
		end
	end
end

function Game:addHint(h)
	self.hints[#self.hints + 1] = h
end

function Game:openHints()
	local out = {}
	for i = 1, #self.hints do
		local h = self.hints[i]
		local met = (h.available == nil) or h.available(self)
		local beaten = h.resolved ~= nil and h.resolved(self)
		if met and not beaten then out[#out + 1] = h end
	end
	return out
end

-- Illustration cues (the FIGURE channel, mirrored from the Python
-- engine): once per key per game; the surface hooks onFigure to draw.
-- Purely cosmetic -- a surface without cards ignores it, and replay
-- rebuilds the shown-set without popping overlays (the surface attaches
-- onFigure only after restore).
function Game:showFigure(key, data)
	self.figuresShown = self.figuresShown or {}
	if self.figuresShown[key] then return end
	self.figuresShown[key] = true
	if self.onFigure then self.onFigure(key, data) end
end

-- Wounds, slice-simple (the full d20 table is M5): three and the tomb
-- keeps you.
function Game:heal()
	if self.wounds > 0 then
		self.wounds = self.wounds - 1
		return true
	end
	return false
end

function Game:wound(name, line)
	self.wounds = self.wounds + 1
	self:say("* " .. name .. " -- " .. line)
	if self.wounds >= 3 then
		self.over = true
		self:showFigure("epitaph", {
			cause = string.upper(name),
			score = self.score .. " OF " .. self.maxScore,
		})
		self:say("Your body has no room left to be hurt in. The tomb keeps you.")
		self:say("(Menu: new game.)")
	end
end

function Game:room(name, description)
	local r = Location(name, description)
	self.rooms[#self.rooms + 1] = r
	return r
end

function Game:say(text)
	if not self.quiet then self.out(text) end
end

function Game:award(key, points, msg)
	if self.scoredKeys[key] then return end
	self.scoredKeys[key] = true
	self.score = self.score + points
	if msg then self:say(msg) end
end

function Game:hasLight()
	for i = 1, #self.player.contents do
		if self.player.contents[i]:get("lit") then return true end
	end
	return false
end

function Game:canSee()
	return not self.player.location:get("dark") or self:hasLight()
end

function Game:describe()
	local room = self.player.location
	self:say("*" .. string.upper(room.name) .. "*")
	if not self:canSee() then
		self:say(room:get("darkBlurb") or "It is pitch dark.")
		return
	end
	self:say(room.description)
	local seen = {}
	for i = 1, #room.contents do
		local it = room.contents[i]
		if not it:get("hidden") then seen[#seen + 1] = it.description end
	end
	for i = 1, #room.characters do
		seen[#seen + 1] = room.characters[i].description
	end
	if #seen > 0 then self:say("You see: " .. table.concat(seen, "; ") .. ".") end
	self:say("Exits: " .. table.concat(room:exitNames(), ", ") .. ".")
end

-- Scope: what a word can mean HERE -- room things (not hidden), what shows
-- inside them, folk present, and everything carried. Order is lane order.
function Game:scope()
	local out = {}
	local function put(thing)
		out[#out + 1] = thing
		local inner = thing:accessible()
		for i = 1, #inner do put(inner[i]) end
	end
	local room = self.player.location
	if self:canSee() then
		for i = 1, #room.contents do
			if not room.contents[i]:get("hidden") then put(room.contents[i]) end
		end
		for i = 1, #room.characters do out[#out + 1] = room.characters[i] end
	end
	for i = 1, #self.player.contents do put(self.player.contents[i]) end
	return out
end

function Game:find(word)
	local things = self:scope()
	for i = 1, #things do
		if things[i]:answersTo(word) then return things[i] end
	end
	return nil
end

-- ------------------------------------------------------------------- verbs
-- Ordered: this IS the composer's verb lane. arity 0 verbs submit alone;
-- arity 1 wait for a noun.
Engine.verbs = {}
local function verb(name, arity, run, ...)
	local v = { name = name, arity = arity, run = run, aliases = { ... } }
	Engine.verbs[#Engine.verbs + 1] = v
	return v
end

-- A multi-slot verb: template is the slot walk, e.g. {"noun","to","noun"}
-- (bare strings are connectors the composer inserts by itself).
local function templateVerb(name, template, run, ...)
	local v = verb(name, #template, run, ...)
	v.template = template
	return v
end

local function findVerb(word)
	for i = 1, #Engine.verbs do
		local v = Engine.verbs[i]
		if v.name == word then return v end
		for j = 1, #v.aliases do
			if v.aliases[j] == word then return v end
		end
	end
	return nil
end

function Game:go(dir)
	local room = self.player.location
	if room.blocks[dir] then
		self:say(room.blocks[dir])
		return true
	end
	local dest = room.connections[dir]
	if not dest then
		self:say("You can't go that way.")
		return true
	end
	self.player.location = dest
	dest.visited = true
	self:say("You moved to " .. dest.name .. ".")
	self:describe()
	return true
end

verb("look", 0, function(g)
	g:describe()
end, "l", "look around")

verb("examine", 1, function(g, thing)
	g:say(thing.examineText)
	local inner = thing:accessible()
	if #inner > 0 then
		local names = {}
		for i = 1, #inner do names[#names + 1] = inner[i].description end
		g:say("Within reach: " .. table.concat(names, "; ") .. ".")
	end
end, "x", "look at")

verb("search", 1, function(g, thing)
	local found = {}
	for i = 1, #thing.contents do
		if thing.contents[i]:get("hidden") then
			thing.contents[i]:set("hidden", nil)
			found[#found + 1] = thing.contents[i].description
		end
	end
	if #found > 0 then
		g:say("You search the " .. thing.name .. " and find "
			.. table.concat(found, ", ") .. ".")
		local hook = thing:get("onSearched")
		if hook then hook(g, thing) end
	else
		g:say("You find nothing more in the " .. thing.name .. ".")
	end
end)

verb("take", 1, function(g, thing)
	if not thing:get("gettable") then
		g:say("The " .. thing.name .. " stays where it is.")
		return
	end
	if thing.holder then thing.holder:remove(thing) end
	g.player:add(thing)
	g:say("You got the " .. thing.name .. ".")
	local hook = thing:get("onTaken")
	if hook then hook(g, thing) end
end, "get")

verb("drop", 1, function(g, thing)
	if not g.player:carrying(thing.name) then
		g:say("You aren't carrying that.")
		return
	end
	g.player:remove(thing)
	g.player.location:add(thing)
	g:say("You dropped the " .. thing.name .. ".")
	local hook = thing:get("onLanded")
	if hook then hook(g, thing) end
end)

verb("throw", 1, function(g, thing)
	if not g.player:carrying(thing.name) then
		g:say("You aren't carrying that.")
		return
	end
	g.player:remove(thing)
	g.player.location:add(thing)
	g:say("You throw the " .. thing.name .. ".")
	local hook = thing:get("onLanded")
	if hook then hook(g, thing) end
end, "toss")

verb("light", 1, function(g, thing)
	if not thing:get("lightable") then
		g:say("That's not something that can be lit.")
		return
	end
	if thing:get("lit") then
		g:say("It is already lit.")
		return
	end
	local dark = not g:canSee()
	thing:set("lit", true)
	g:say("The " .. thing.name .. " flares alight and glows.")
	local hook = thing:get("onLit")
	if hook then hook(g, thing) end
	if dark and g:canSee() then g:describe() end -- the light earns the look
end, "turn on")

verb("douse", 1, function(g, thing)
	if not thing:get("lit") then
		g:say("It isn't lit.")
		return
	end
	thing:set("lit", nil)
	g:say("You douse the " .. thing.name .. ".")
	if not g:canSee() then
		g:say((g.player.location:get("darkBlurb")) or "The dark closes in.")
	end
end, "turn off", "extinguish")

local attackVerb = verb("attack", 1, function(g, thing)
	if thing:get("mends") then
		thing:set("aware", true)
		g:say(thing:get("mendsText")
			or ("The blade opens a rent in the " .. thing.name
				.. "; it closes as you watch."))
		return
	end
	if not thing:get("vigor") then
		g:say("The " .. thing.name .. " takes no notice of violence.")
		return
	end
	local weapon = nil
	for i = 1, #g.player.contents do
		if g.player.contents[i]:get("weapon") then
			weapon = g.player.contents[i]
			break
		end
	end
	if not weapon then
		g:say("Your hands alone won't part it. Something edged might.")
		return
	end
	thing:set("aware", true)
	local v = thing:get("vigor") - 1
	thing:set("vigor", v)
	if v > 0 then
		g:say(thing:get("struckText")
			or ("The " .. weapon.name .. " bites; the " .. thing.name .. " does not fall."))
	else
		thing:set("dead", true)
		thing:set("hostile", nil)
		g:say(thing:get("koText") or ("The " .. thing.name .. " falls, and stays down."))
		local hook = thing:get("onDeath")
		if hook then hook(g, thing) end
	end
end, "hit", "strike", "kill")
attackVerb.combatOnly = true

verb("talk to", 1, function(g, thing)
	local hook = thing:get("onTalk")
	if hook then
		hook(g, thing)
	else
		g:say("The " .. thing.name .. " has nothing to say to you.")
	end
end, "talk", "talk with")

templateVerb("put", { "noun", "on", "noun" }, function(g, item, target)
	if not g.player:carrying(item.name) then
		g:say("You aren't carrying that.")
		return
	end
	local hook = target:get("onReceive")
	if hook then
		g.player:remove(item)
		target:add(item)
		hook(g, item, target)
	else
		g:say("The " .. target.name .. " offers it no purchase.")
	end
end, "place", "set")

templateVerb("give", { "noun", "to", "noun" }, function(g, item, target)
	if not g.player:carrying(item.name) then
		g:say("You aren't carrying that.")
		return
	end
	local hook = target:get("onGift")
	if hook then
		hook(g, item, target)
	else
		g:say("The " .. target.name .. " wants nothing of yours.")
	end
end, "offer")

local sneakVerb = verb("sneak", 1, function(g)
	g:say("Sneak which way?")
end, "creep")
sneakVerb.template = { "direction" }

verb("break", 1, function(g, thing)
	local hook = thing:get("onBreak")
	if not hook then
		g:say("The " .. thing.name .. " is sturdier than your opinion of it.")
		return
	end
	hook(g, thing)
end, "smash", "shatter")

verb("pry", 1, function(g, thing)
	local hook = thing:get("onPried")
	if not hook then
		g:say("The " .. thing.name .. " offers nothing to lever against.")
		return
	end
	hook(g, thing)
end, "pry open", "open")

verb("read", 1, function(g, thing)
	local txt = thing:get("readText")
	if not txt then
		g:say("The " .. thing.name .. " has nothing written on it.")
		return
	end
	if type(txt) == "function" then txt = txt(g, thing) end
	g:say(txt)
	local hook = thing:get("onRead")
	if hook then hook(g, thing) end
end)

verb("say", 1, function(g, thing)
	local hook = thing:get("onSaid")
	if not hook then
		g:say("You say it. The tomb does not answer.")
		return
	end
	hook(g, thing)
end, "speak", "recite")

local hintVerb = verb("hint", 0, function(g)
	local open = g:openHints()
	if #open == 0 then
		g:say("Nothing you have met wants a hint right now.")
		return
	end
	g:say("The questions worth asking, so far:")
	for i = 1, #open do
		local h = open[i]
		local done = g.hintProgress[h.key] or 0
		local gauge = done > 0 and ("  (" .. done .. "/" .. #h.levels .. ")") or ""
		g:say("  " .. string.upper(h.key) .. " -- " .. h.question .. gauge)
	end
	g:say("(Pick a question from the wheel; RESUME returns to the tomb.)")
	g.hintMode = true
end, "hints")
hintVerb.free = true -- consulting the booklet costs no turn

verb("inventory", 0, function(g)
	if #g.player.contents == 0 then
		g:say("You carry nothing but your reputation.")
		return
	end
	local names = {}
	for i = 1, #g.player.contents do
		names[#names + 1] = g.player.contents[i].description
	end
	g:say("You carry: " .. table.concat(names, "; ") .. ".")
end, "i")

-- --------------------------------------------------------------- the turn
function Game:doCommand(line)
	line = string.lower(line):gsub("^%s+", ""):gsub("%s+$", "")
	if line == "" then return end
	self:say("> " .. line)
	if self.over then
		self:say("The expedition is over. (Menu: new game.)")
		return false
	end
	-- the hint booklet: journaled (replay restores the reveals) but FREE --
	-- no turn passes, nothing in the tomb gets to move
	if self.hintMode then
		self.journal[#self.journal + 1] = line
		if line == "resume" or line == "done" or line == "back" then
			self.hintMode = false
			self:say("You close the booklet. The tomb resumes.")
			return true
		end
		local open = self:openHints()
		for i = 1, #open do
			local h = open[i]
			if h.key == line then
				local done = self.hintProgress[h.key] or 0
				if done < #h.levels then
					done = done + 1
					self.hintProgress[h.key] = done
					self.hintsTaken = self.hintsTaken + 1
				end
				self:say(string.upper(h.key) .. " -- " .. h.question)
				for l = 1, done do
					self:say("  " .. l .. ". " .. h.levels[l])
				end
				if done >= #h.levels then
					self:say("(That is the whole of it.)")
				else
					self:say("(Ask again for a stronger nudge.)")
				end
				return true
			end
		end
		self:say("No open question matches that. (RESUME to return.)")
		return false
	end
	local room = self.player.location

	self.sneaked = false
	-- SNEAK <exit>: quiet travel -- the sound-hunters' triggers skip the
	-- round (their preds consult game.sneaked). Handled before the verb
	-- table: its argument is a direction, not a noun.
	local sneakArg = line:match("^sneak%s*(.*)$") or line:match("^creep%s*(.*)$")
	if sneakArg then
		if sneakArg == "" then
			self:say("Sneak which way?")
			return false
		end
		local d = room.directionAliases[sneakArg]
		if not d and (room.connections[sneakArg] or room.blocks[sneakArg]) then
			d = sneakArg
		end
		if not d then
			self:say("You can't creep that way.")
			return false
		end
		self.journal[#self.journal + 1] = line
		self.turn = self.turn + 1
		self.sneaked = true
		self:say("You go low and quiet, weight on the outside of your feet.")
		self:go(d)
		self:runTriggers()
		return true
	end

	-- travel: exact per-room phrase, a bare exit name, or GO <exit>
	local dir = room.directionAliases[line]
	if not dir and (room.connections[line] or room.blocks[line]) then dir = line end
	if not dir then
		local goDir = line:match("^go%s+(.+)$")
		if goDir and (room.connections[goDir] or room.blocks[goDir]) then
			dir = goDir
		end
	end
	if dir then
		self.journal[#self.journal + 1] = line
		self.turn = self.turn + 1
		self:go(dir)
		self:runTriggers()
		return true
	end

	local verbWord, rest = line:match("^(%S+)%s*(.*)$")
	-- longest verb phrase wins: try "talk to"/"look at" BEFORE bare "talk"
	-- (whose alias would otherwise strand the connector in the noun)
	local v = nil
	if rest ~= "" then
		local two = verbWord .. " " .. rest:match("^(%S+)")
		v = findVerb(two)
		if v then rest = rest:gsub("^%S+%s*", "") end
	end
	if not v then v = findVerb(verbWord) end
	if not v then
		self:say("The tomb does not know that word yet.")
		return false
	end
	local args = {}
	if v.template then
		-- walk the template: nouns split on the connector words
		local pieces, connector = {}, nil
		for i = 1, #v.template do
			if v.template[i] ~= "noun" then connector = v.template[i] end
		end
		local a, b = rest:match("^(.-)%s+" .. connector .. "%s+(.+)$")
		if not a then
			self:say(string.upper(v.name) .. " what " .. connector .. " whom?")
			return false
		end
		pieces[1], pieces[2] = a, b
		for i = 1, 2 do
			args[i] = self:find(pieces[i])
			if not args[i] then
				self:say("You don't see any " .. pieces[i] .. " here.")
				return false
			end
		end
	elseif v.arity == 1 then
		if rest == "" then
			self:say(string.upper(v.name) .. " what?")
			return false
		end
		args[1] = self:find(rest)
		if not args[1] then
			self:say("You don't see any " .. rest .. " here.")
			return false
		end
	end
	self.journal[#self.journal + 1] = line
	if v.free then
		v.run(self, args[1], args[2])
		return true
	end
	self.turn = self.turn + 1
	v.run(self, args[1], args[2])
	self:runTriggers()
	return true
end

-- ------------------------------------------------------------- suggestions
-- Modal word pools (the Thy Dungeonman lesson): the verb lane swaps by
-- game state. In combat the fight verbs lead; at rest the fight verbs
-- stay off the wheel entirely.
Engine.pools = {
	-- arming yourself mid-fight is THE move in the warriors hall: take and
	-- search stay on the wheel (the audit caught their absence)
	combat = { "attack", "sneak", "say", "read", "pry", "break", "take",
		"search", "throw", "examine", "look", "douse", "inventory", "hint" },
}

-- Combat: something hostile shares the room and is either visible to you
-- or already aware of you (a sound-hunter needs no light to fight).
function Game:mode()
	local room = self.player.location
	for i = 1, #room.characters do
		local c = room.characters[i]
		if c:get("hostile") and not c:get("dead") then
			if self:canSee() or c:get("aware") then return "combat" end
		end
	end
	return "default"
end

-- The composer's lanes, honesty guaranteed: only words the engine will
-- accept. Verb order is fixed (ranking doc section 8); noun order is scope
-- order (the fiction's own salience).
function Game:suggestions()
	if self.hintMode then
		local verbs = {}
		local open = self:openHints()
		for i = 1, #open do verbs[#verbs + 1] = open[i].key end
		verbs[#verbs + 1] = "resume"
		return { exits = {}, verbs = verbs, nouns = {} }
	end
	local nouns, seen = {}, {}
	local things = self:scope()
	for i = 1, #things do
		local n = things[i].name
		if not seen[n] then
			seen[n] = true
			nouns[#nouns + 1] = n
		end
	end
	local verbs = {}
	local pool = Engine.pools[self:mode()]
	if pool then
		for i = 1, #pool do verbs[#verbs + 1] = pool[i] end
	else
		for i = 1, #Engine.verbs do
			local v = Engine.verbs[i]
			if not v.combatOnly then verbs[#verbs + 1] = v.name end
		end
	end
	return {
		exits = self.player.location:exitNames(),
		verbs = verbs,
		nouns = nouns,
	}
end

function Engine.verbArity(name)
	local v = findVerb(name)
	return v and v.arity or 1
end

-- The composer's slot walk for a verb: {"noun"}, {}, or the template
-- ({"noun","to","noun"} -- connectors are strings the composer inserts).
function Engine.verbSlots(name)
	local v = findVerb(name)
	if not v then return { "noun" } end
	if v.template then return v.template end
	local slots = {}
	for _ = 1, v.arity do slots[#slots + 1] = "noun" end
	return slots
end

-- ------------------------------------------------------------ saves/replay
-- A save is (seed, journal); restoring is replaying quietly. Determinism
-- is the whole save system, same contract as the Python engine.
function Game:snapshot()
	return { seed = self.seed, journal = self.journal }
end

function Engine.restore(build, snap)
	local g = build(snap.seed)
	g.quiet = true
	for i = 1, #snap.journal do g:doCommand(snap.journal[i]) end
	g.quiet = false
	return g
end
