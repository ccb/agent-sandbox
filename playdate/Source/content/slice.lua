-- The vertical slice (M1): Wreck -> Wagon's Hold -> Tomb Exterior, ported
-- from the Python tomb WITH the terse-text pass (docs section 6: ~50 words,
-- nouns front-loaded -- the description is the noun lane's table of
-- contents). The Python adventure remains the source of truth.

function BuildTomb(seed)
	local g = Engine.Game(seed)
	local Item = Engine.Thing

	-- ------------------------------------------------------------ rooms
	local wreck = g:room("The Caravan Wreck",
		"The Tomblands road, the hour after the Cacklemaw. The wreck of a "
		.. "wind-wagon lies heeled over in blue sand; the dead zoxen and "
		.. "the merchant have been arranged by the wind into attitudes of "
		.. "sleep. Northward, three carved faces watch from azure stone.")
	local hold = g:room("The Wagon's Hold",
		"The hold survived the wagon: lashed crates of saffron and dates, "
		.. "and the merchant's ledger closed around its ribbon.")
	local exterior = g:room("Tomb Exterior",
		"A thirty-foot slab of azure stone, webbed with orange fungus. "
		.. "Three faces are carved in the tomb: a boy westward, a helmed "
		.. "warrior eastward, far up an old man weeping tendrils from his "
		.. "open mouth. Each mouth is a door.")

	wreck:connect("in", hold, "out")
	wreck:connect("north", exterior, "south")
	exterior.blocks.north = "The boy's door breathes cold air. (M2 opens it.)"
	exterior.blocks.east = "The warrior's door stands sealed. (M2 opens it.)"
	exterior.blocks.up = "The climb waits for surer milestones. (M2.)"

	-- the playtesters' phrasings (mirrors the Python direction aliases)
	wreck:travelAlias("enter wagon", "in"):travelAlias("wagon", "in")
		:travelAlias("tomb", "north"):travelAlias("approach tomb", "north")
	hold:travelAlias("leave", "out"):travelAlias("exit", "out")
	exterior:travelAlias("enter tomb", "north"):travelAlias("enter", "north")
		:travelAlias("climb", "up"):travelAlias("climb tomb", "up")
		:travelAlias("climb stone", "up")

	-- ------------------------------------------------------------ wreck
	local wagon = Item("wreck", "the heeled-over wind-wagon",
		"Pale wood ribs, cargo strewn and already sanding under. "
		.. "Road-worthy never again.")
	wagon:alias("wagon", "wind-wagon")
	wreck:add(wagon)

	local zoxen = Item("zoxen", "two dead zoxen, half-sanded",
		"Salt-heavy haulers, dead in harness. The sand is patient with them.")
	zoxen:alias("zox")
	wreck:add(zoxen)

	local merchant = Item("dead merchant", "the merchant, dead where the road put him",
		"He kept his ledger neat and his glowstone close. The road decided "
		.. "the rest.")
	merchant:alias("merchant", "body")
	wreck:add(merchant)

	local glowstone = Item("glowstone", "a dim glowstone",
		"A shard of cold lazulite, dark until woken. Light is dear; "
		.. "attention dearer.")
	glowstone:alias("stone")
	glowstone:set("gettable", true)
	glowstone:set("hidden", true)
	merchant:add(glowstone)

	local waterskin = Item("waterskin", "a waterskin with 3 rations",
		"Water is money here. This is a small inheritance.")
	waterskin:alias("skin", "water")
	waterskin:set("gettable", true)
	waterskin:set("hidden", true)
	merchant:add(waterskin)

	merchant:set("onSearched", function(game)
		game:award("inheritance", 5, "[+5 -- an inheritance of water]")
	end)

	local critch = Engine.Character("critch", "Critch, a golden new-hyena teamster",
		"Critch settles his pack straps like someone already decided to be "
		.. "elsewhere. His cracked mask hangs on its cord.")
	wreck:addCharacter(critch)

	-- ------------------------------------------------------------- hold
	local crates = Item("crates", "lashed crates, one split open",
		"Saffron and dates, lashed tight. One crate split in the wreck; "
		.. "dates within reach.")
	crates:alias("crate")
	hold:add(crates)

	local dates = Item("dates", "a crate of dates",
		"Proper trail food -- and anything in these halls with a nose will "
		.. "know you carry it.")
	dates:set("gettable", true)
	crates:add(dates)

	local ledger = Item("ledger", "the merchant's ledger",
		"Neat columns: water in, water out. The last line is the route "
		.. "north, underlined twice.")
	ledger:alias("book")
	hold:add(ledger)

	-- --------------------------------------------------------- exterior
	local tomb = Item("tomb", "the Tomb of Nassak An-Rah",
		"Azure stone, thirty feet of it. West, the Autarch young; east, a "
		.. "helmed warrior; at the summit an old man gazes skyward, orange "
		.. "tendrils weeping from his open mouth. Two doors, one chimney.")
	tomb:alias("faces", "stone slab")
	exterior:add(tomb)

	local fungus = Item("fungus", "creeping orange fungus",
		"It webs every seam of the stone, and it is not dead. Nothing "
		.. "here is entirely.")
	fungus:alias("growth", "tendrils")
	exterior:add(fungus)

	-- ------------------------------------------------------------ start
	g.maxScore = 5
	g.player.location = wreck
	wreck.visited = true
	return g
end
