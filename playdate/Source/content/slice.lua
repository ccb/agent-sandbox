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
	local warriors = g:room("Hall of Warriors",
		"Four plexiglas burial cylinders stand on an uneven floor, each "
		.. "holding a guard-mummy armed as in life. One lies burst, its "
		.. "gel dried to amber lace. Something in the room is breathing.")
	warriors:set("dark", true)
	warriors:set("darkBlurb",
		"Dark as a pocket. Your footsteps come back off plexiglas somewhere "
		.. "close -- and low down, near the floor, something breathes "
		.. "wetly, in no hurry.")

	exterior:connect("north", youth, "south")
	exterior:connect("east", warriors, "west")
	exterior.blocks.up = "The climb waits for surer milestones."
	exterior:travelAlias("warrior door", "east"):travelAlias("enter warrior", "east")

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
		game:showFigure("glowstone")
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
	critch:alias("teamster", "hyena")
	critch:set("onTalk", function(game)
		if critch:get("spoken") then
			game:say("Critch is done talking. His feet say south.")
			return
		end
		critch:set("spoken", true)
		game:say('Critch does not stop working the straps. "Take what you '
			.. 'need from the merchant. He doesn\'t need it now. Tomb pays '
			.. 'better than the road, if the tomb lets you keep it. Mind the '
			.. 'boy\'s hall -- the ceiling has opinions about light." He '
			.. 'nods at the crates. "I walk south."')
	end)
	critch:set("onGift", function(game, item)
		if item.name == "dates" then
			game:say('Critch waves the crate off. "Keep them. Feed the '
				.. 'ceiling, not me -- nothing quiets a roost like a full '
				.. 'stomach."')
		else
			game:say('Critch shakes his head. "Carry your own weight, '
				.. 'scavenger. I have mine."')
		end
	end)
	wreck:addCharacter(critch)

	-- once spoken, the teamster decamps at the end of the NEXT turn
	g:addTrigger("critch_decamps", function(game)
		if not critch:get("spoken") or critch.location == nil then return false end
		local n = (critch:get("straps") or 0) + 1
		critch:set("straps", n)
		return n >= 2
	end, function(game)
		local room = critch.location
		for i = 1, #room.characters do
			if room.characters[i] == critch then
				table.remove(room.characters, i)
				break
			end
		end
		critch.location = nil
		if game.player.location == room then
			game:say("Critch shoulders his pack, tips the cracked mask, and "
				.. "walks south into the sand-haze. He does not look back.")
		end
	end, false)

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
		game:showFigure("bats-c") -- the residents, before the text
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

	-- --------------------------------------------------- hall of warriors
	local cylinders = Item("cylinders", "four plexiglas burial cylinders",
		"Guard-mummies stand sealed in gel, armed as in life. The burst one "
		.. "gapes; its guard has slumped, and his kit has scattered.")
	cylinders:alias("cylinder", "mummies", "guards")
	warriors:add(cylinders)

	local blade = Item("prismatic blade", "a guard's prismatic blade",
		"An Autarchy guard's blade, its edge fracturing the light into "
		.. "colours. It wants using.")
	blade:alias("blade", "sword")
	blade:set("gettable", true)
	blade:set("hidden", true)
	blade:set("weapon", true)
	cylinders:add(blade)

	local jar = Item("falcon jar", "a falcon-headed canopic jar",
		"A sealed jar with a falcon's head, wings swept back along the "
		.. "lid. Something coiled shifts inside.")
	jar:alias("jar")
	jar:set("gettable", true)

	local spawn = Engine.Character("spawn of guts",
		"a fungal spawn, eyeless under its falcon-headed jar, swaying "
		.. "toward every sound",
		"An octopus of orange fungus and grave-cured intestine, wearing "
		.. "the falcon canopic jar on top like a hat. It sways toward any "
		.. "sound. It has no eyes and does not want any.")
	spawn:alias("spawn", "fungus thing", "horror")
	spawn:set("hostile", true)
	spawn:set("vigor", 2)
	spawn:set("struckText", "The blade opens a rent in the orange mass; it "
		.. "seethes, and does not fall.")
	spawn:set("koText", "The last rent does not close. The spawn folds into "
		.. "its own skirt of tendrils, and the falcon jar topples, bounces "
		.. "once, and settles upright.")
	spawn:set("onDeath", function(game)
		warriors:add(jar)
		warriors.description = "Four plexiglas burial cylinders on an uneven "
			.. "floor, one burst. The spawn lies folded and still; the hall "
			.. "is only a room now."
		warriors:set("darkBlurb", "Dark as a pocket. Plexiglas gives back "
			.. "your footsteps. Nothing breathes but you.")
		game:award("spawn_quelled", 5, "[+5 -- the spawn of guts is quelled]")
	end)
	warriors:addCharacter(spawn)

	jar:set("onTaken", function(game)
		game:award("falcon_jar", 5, "[+5 -- the falcon jar, claimed]")
	end)

	-- the spawn hunts sound: your presence IS noise. One swing of warning,
	-- then acid on the odd rounds -- light or dark, it does not care.
	g:addTrigger("spawn_menace", function(game)
		return game.player.location == warriors and not spawn:get("dead")
	end, function(game)
		local n = (warriors:get("sway") or 0) + 1
		warriors:set("sway", n)
		spawn:set("aware", true)
		if n == 1 then
			game:showFigure("guts-a") -- the card plays first, then the text
			game:say("Something big swings toward your noise, arms rising "
				.. "from the floor like kelp in a current.")
		elseif n % 2 == 1 then
			game:wound("Acid-Lashed", "a wet arm finds you across the dark.")
		else
			game:say("The wet breathing tracks you. It is deciding.")
		end
	end, true)

	g:addTrigger("spawn_calm", function(game)
		return (warriors:get("sway") or 0) > 0
			and (game.player.location ~= warriors or spawn:get("dead"))
	end, function(_game)
		warriors:set("sway", 0)
		spawn:set("aware", nil)
	end, true)

	-- ----------------------------------------------------- hall of memory
	local memory = g:room("Hall of Memory",
		"Lattices of memory-crystal climb every wall, the Autarch's "
		.. "favoured recollections set in lazulite. The glimmering on them "
		.. "moves while you are still. A synth in yellow robes reads the "
		.. "walls with his fingertips.")
	memory:set("dark", true)
	memory:set("darkBlurb",
		"Gloom. Crystal facets give back your light's absence; somewhere "
		.. "in it, slow bright threads move where no light should be.")
	youth:connect("north", memory, "south")

	local lattice = Item("lattice", "lattices of memory-crystal",
		"The favoured recollections of Nassak An-Rah, set in lazulite. One "
		.. "bank is worn smooth at hand-height, as if often consulted.")
	lattice:alias("crystal", "crystals", "walls")
	memory:add(lattice)

	local silas = Engine.Character("silas",
		"Silas, a synthetic archivist in yellow monk's robes",
		"A gaunt synth in yellow robes, fingertips tipped with cranial "
		.. "bores, drawing memory from the lattice in slow bright threads. "
		.. "Patient, courteous, elsewhere.")
	silas:alias("synth", "archivist", "monk")
	silas:set("onTalk", function(game)
		game:award("archivist", 5, "[+5 -- the archivist's acquaintance]")
		game:say('Silas speaks without turning. "Scavenger. You walk in a '
			.. 'house of memory; mind what you wake. The lattice remembers '
			.. 'his embalming, for those who trouble to look. The dead here '
			.. 'listen. Step softly."')
	end)
	silas:set("onGift", function(game, item)
		if item.name == "dates" then
			game:say('Silas declines with a small bow. "I read the dead, '
				.. 'not the dinner."')
		else
			game:say('Silas considers it, and returns it. "Not what the '
				.. 'lattice wants. Not yet."')
		end
	end)
	memory:addCharacter(silas)

	-- ------------------------------------------------ canopic jars (slice)
	local canopic = g:room("Hall of the Canopic Jars",
		"Five plinths ring a central stair in a pentagon of dressed stone. "
		.. "Three jars stand answered -- baboon, human, mantis. The falcon "
		.. "plinth stands empty, lit crimson, its carved talons cupped "
		.. "around the shape of something lost.")
	memory:connect("east", canopic, "west")

	local seated = Item("jars", "three seated canopic jars",
		"Baboon, human, mantis: sealed, seated, satisfied. Their plinths "
		.. "glow a settled white.")
	seated:alias("three jars", "seated jars")
	canopic:add(seated)

	local plinth = Item("falcon plinth", "the empty falcon plinth",
		"Carved talons, cupped and waiting. The crimson light over it "
		.. "burns like an unanswered question.")
	plinth:alias("plinth")
	plinth:set("onReceive", function(game, item)
		if item.name ~= "falcon jar" then
			game:say("The talons refuse it. They were carved for one thing.")
			plinth:remove(item)
			game.player:add(item)
			return
		end
		game:say("The jar settles into the talons like a word into a "
			.. "sentence. The crimson steadies to white -- and somewhere "
			.. "above, stone parts from stone with a sigh.")
		game:award("seal", 10, "[+10 -- the seal answers the jars]")
		plinth.examineText = "The falcon jar sits answered in its talons, "
			.. "the light gone white. The carving reads as finished."
		canopic.description = "Five plinths, five jars, one pentagon of "
			.. "dressed stone -- all of it answered, all of it white. The "
			.. "stair above stands open on the dark."
		game.won = true
		game:say("*** The slice is won. The stair waits for the next "
			.. "milestone. ***")
	end)
	canopic:add(plinth)

	-- ------------------------------------------------------------- hints
	-- The booklet lists only puzzles the player has MET and not yet beaten.
	g:addHint({ key = "light", question = "How do I see anything down here?",
		levels = {
			"The caravan did not die carrying nothing.",
			"SEARCH the dead merchant; TAKE and LIGHT the glowstone.",
		},
		resolved = function(game) return game.scoredKeys["first_light"] end })
	g:addHint({ key = "bats", question = "What do I do about the bats?",
		levels = {
			"They hate your light. They love something else more.",
			"The wagon's crates hold dates. THROW DATES in the Hall of Youth.",
		},
		available = function(_) return youth.visited end,
		resolved = function(_) return youth:get("fed") end })
	g:addHint({ key = "spawn", question = "The thing in the dark keeps hitting me.",
		levels = {
			"It hunts sound, not light. Standing still is not quiet enough.",
			"The burst cylinder holds an edge. With light raised: SEARCH "
				.. "CYLINDERS, TAKE BLADE, ATTACK.",
		},
		available = function(_) return warriors.visited end,
		resolved = function(_) return spawn:get("dead") == true end })
	g:addHint({ key = "plinth", question = "What is the falcon jar for?",
		levels = {
			"The empty plinth's talons were carved for one thing.",
			"The spawn wears it as a hat. Quell it, TAKE FALCON JAR, and "
				.. "PUT FALCON JAR ON FALCON PLINTH.",
		},
		available = function(_) return canopic.visited end,
		resolved = function(game) return game.won == true end })

	-- ------------------------------------------------------------ start
	g.maxScore = 40
	g.player.location = wreck
	wreck.visited = true
	return g
end
