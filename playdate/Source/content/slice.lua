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

	local youth = g:room("Hall of Youth",
		"Your light wakes blue statues of the boy-Autarch, swaddled and "
		.. "adored, rendered with unsettling tenderness. Overhead the vault "
		.. "seethes: thousands of bats, wheeling lower with every pass.")
	youth:set("dark", true)
	youth:set("darkBlurb",
		"Dark as a pocket. The air moves overhead in slow leathery waves, "
		.. "and the floor grits underfoot. Your light would wake this room "
		.. "-- and everything roosting in it.")

	wreck:connect("in", hold, "out")
	wreck:connect("north", exterior, "south")
	exterior:connect("north", youth, "south")
	exterior.blocks.east = "The warrior's door stands sealed. (Next milestone.)"
	exterior.blocks.up = "The climb waits for surer milestones."

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
	glowstone:set("lightable", true)
	glowstone:set("onLit", function(game)
		game:award("first_light", 5, "[+5 -- light, learned]")
	end)
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

	-- ------------------------------------------------------ hall of youth
	local statues = Item("statues", "blue statues of the boy-Autarch",
		"Nassak An-Rah as an infant, a child, a youth -- each rendered with "
		.. "unsettling tenderness in cold blue stone.")
	statues:alias("statue", "boy")
	youth:add(statues)

	local ceiling = Item("ceiling", "the seething ceiling",
		"Thousands of bats packed wing to wing, folded and dreaming -- and "
		.. "the nearest have already let go of the stone. They hate your "
		.. "light. They love something else more.")
	ceiling:alias("bats", "colony", "vault")
	youth:add(ceiling)

	-- the dates puzzle: land them in the hall and the colony forgets you
	dates:set("onLanded", function(game, item)
		if game.player.location ~= youth or youth:get("fed") then return end
		youth:set("fed", true)
		youth:set("mob", 0)
		youth:remove(item)
		game:say("The ceiling DETACHES. The whole colony falls on the dates "
			.. "and cares about nothing else; then, gorged, they climb the "
			.. "walls and fold themselves to sleep.")
		youth.description = "Blue statues of the boy-Autarch, swaddled and "
			.. "adored. The ceiling seethes gently now: the colony, fed and "
			.. "folded, has no further opinions about your light."
		ceiling.examineText = "The colony, packed wing to wing and fast "
			.. "asleep. They have no further opinions about your light."
		game:award("colony_fed", 5, "[+5 -- the colony, fed]")
	end)

	-- the bats hate your light: one warning, then the swarm
	g:addTrigger("bat_menace", function(game)
		return game.player.location == youth
			and game:hasLight()
			and not youth:get("fed")
	end, function(game)
		local n = (youth:get("mob") or 0) + 1
		youth:set("mob", n)
		if n == 1 then
			game:say("The rustle overhead deepens. Grit sifts down through "
				.. "your light; the whole vault has begun, gently, to move.")
		else
			game:wound("Raked",
				"leather and small teeth descend on your light.")
		end
	end, true)

	g:addTrigger("bat_calm", function(game)
		return (youth:get("mob") or 0) > 0
			and not (game.player.location == youth and game:hasLight())
	end, function(_game)
		youth:set("mob", 0)
	end, true)

	-- ------------------------------------------------------------ start
	g.maxScore = 15
	g.player.location = wreck
	wreck.visited = true
	return g
end
