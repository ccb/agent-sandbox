-- The vertical slice (M1): Wreck -> Wagon's Hold -> Tomb Exterior, ported
-- from the Python tomb WITH the terse-text pass (docs section 6: ~50 words,
-- nouns front-loaded -- the description is the noun lane's table of
-- contents). The Python adventure remains the source of truth.

function BuildTomb(seed)
	local g = Engine.Game(seed)
	local Item = Engine.Thing

	-- ------------------------------------------------------------ rooms
	local wreck = g:room("The Caravan Wreck",
		"The Tomblands road, the hour after the Cacklemaw attack. The wreck of a "
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

	local hounds = g:room("Hall of Hounds",
		"A long gallery dominated by a gel tank, its glass sweating. "
		.. "Inside floats a cyborg hound, perfectly preserved. Something "
		.. "small and two-legged twitches in the far dark, listening.")
	hounds:set("dark", true)
	hounds:set("darkBlurb",
		"Dark, and close. Glass somewhere, sweating. And a small dry "
		.. "twitching, like a metronome deciding.")

	local summit = g:room("The Summit",
		"The tomb's crown, open to the horizon's molten line. An ossified "
		.. "mystic sits here in the lotus posture, fungus weeping from his "
		.. "eyes and mouth, down into a chimney bored through the crown.")

	local chimney = g:room("The Fungal Chimney",
		"A throat of stone furred floor-to-crown with orange growth. It "
		.. "breathes. Somewhere in the fur, something long and patient "
		.. "does not move.")
	chimney:set("dark", true)
	chimney:set("darkBlurb",
		"A throat of stone, utterly dark, furred with something soft that "
		.. "your fingers regret. The air moves like slow breath.")

	exterior:connect("north", youth, "south")
	exterior:connect("east", warriors, "west")
	warriors:connect("east", hounds, "west")
	exterior:connect("up", summit, "down")
	summit:connect("in", chimney, "out")
	exterior:travelAlias("warrior door", "east"):travelAlias("enter warrior", "east")
	summit:travelAlias("chimney", "in"):travelAlias("enter chimney", "in")
		:travelAlias("descend", "in")

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

	Engine.selves = {
		"a cacogen salvager, chrome-gilled, owing three water-debts",
		"a true-kin exile with a forged pilgrim's brand",
		"a mycomorph courier whose spores hum when it rains",
		"a synth deserter running on prayer and one good servo",
		"a newbeast tinker, hyena-line, mask cracked down the smile",
		"a vat-born duelist who lost the duel and kept the walk",
		"a faa nomad's seventh child, sold a map that was a poem",
		"an archive-thief with lazulite dust under every nail",
		"a gene-witch's apprentice, fired for excessive mercy",
		"a former Autarchy re-enactor who got too good at it",
		"a water-diviner whose rod points only at debts",
		"an ex-cultist of the Sky Sires, deprogrammed, mostly",
	}

	local zoxen = Item("zoxen", "two dead zoxen, half-sanded",
		"Salt-heavy haulers, dead in harness. The sand is patient with them.")
	zoxen:alias("zox")
	zoxen:set("taste", "of salt and brine. Zoxen are half salt by weight.")
	wreck:add(zoxen)

	-- butchery: the first cut takes the haunch AND the blood; meat draws
	-- the pack (they keep a ledger, and you just opened an account)
	local haunch = Item("zox haunch", "a briny haunch of zox meat",
		"Dense and briny, dark as jerky already. It will keep. In these "
		.. "halls, meat has listeners.")
	haunch:alias("haunch", "meat")
	haunch:set("gettable", true)
	haunch:set("edible", true)
	haunch:set("taste", "of iron and brine -- food, honestly, and better "
		.. "bait: you are not the hungriest thing out here.")

	local blood = Item("zox blood", "zox blood, caught warm (2 doses)",
		"Half water by weight, like everything about a zox. Two honest "
		.. "doses; each drinks like a meal and a rest.")
	blood:alias("blood")
	blood:set("gettable", true)
	blood:set("portions", 2)
	blood:set("onDrunk", function(game, thing)
		local n = thing:get("portions") or 0
		if n <= 0 then
			game:say("Only the stain remains.")
			return
		end
		thing:set("portions", n - 1)
		if game:heal() then
			game:say("The blood goes down like a meal and a drink at once. "
				.. "A wound closes.")
		else
			game:say("The blood goes down warm. Nothing in you needed "
				.. "mending; it settles for the mood.")
		end
		thing.description = (n - 1 > 0)
			and ("zox blood, caught warm (" .. (n - 1) .. " dose)")
			or "a smear of zox blood, spent"
	end)

	zoxen:set("onButchered", function(game, thing)
		local cut = (thing:get("cut") or 0) + 1
		thing:set("cut", cut)
		if cut == 1 then
			wreck:add(haunch)
			wreck:add(blood)
			game:say("You open the nearer zox along the clean flank and "
				.. "carve loose a haunch; the blood you catch before the "
				.. "sand can. Road-butchery: quick, ungentle, honest. And "
				.. "somewhere south, noses lift.")
		else
			game:say("Nothing left on them worth the knife; the sand has "
				.. "the rest.")
		end
	end)

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
	glowstone:set("taste", "like a nine-volt battery: a flat electric fizz "
		.. "that finds every filling you own. Not food. Possibly not polite.")
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
	waterskin:set("portions", 3)
	waterskin:set("onDrunk", function(game, thing)
		local n = thing:get("portions") or 0
		if n <= 0 then
			game:say("The skin gives a dry apology.")
			return
		end
		thing:set("portions", n - 1)
		if game:heal() then
			game:say("The water does what water does in Vaarn. A wound "
				.. "troubles you less.")
		else
			game:say("You drink. Money never tasted so plain.")
		end
		thing.description = (n - 1 > 0)
			and ("a waterskin with " .. (n - 1) .. " ration"
				.. ((n - 1) ~= 1 and "s" or ""))
			or "an empty waterskin"
	end)
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
	dates:set("taste", "of honey and sun under the road-dust. Anything "
		.. "down here with a nose will know you carry them.")
	dates:set("onEaten", function(game)
		game:say("You could. But something in the boy's hall wants them "
			.. "more than you do, and it outvotes you by thousands.")
	end)
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

	-- the four cylinders, individually: nouns on the wheel, each with its
	-- own temperament under a crowbar opinion
	local cerulean = Item("cerulean cylinder", "the cerulean cylinder, burst",
		"The burst one: gel dried to amber lace, its guard slumped where "
		.. "duty left him. His kit scattered when it went -- worth a "
		.. "SEARCH of the cylinders.")
	cerulean:alias("cerulean")
	cerulean:set("onBreak", function(game)
		game:say("It is already burst. You kick a shard, for punctuation.")
	end)
	warriors:add(cerulean)

	local amber = Item("amber cylinder", "the amber cylinder, sealed",
		"A guard-mummy stands sealed in amber gel, armed as in life, "
		.. "provisioned as for a march.")
	amber:alias("amber")
	amber:set("onBreak", function(game, thing)
		if thing:get("broken") then
			game:say("Its pieces are done breaking.")
			return
		end
		thing:set("broken", true)
		thing.description = "the amber cylinder, broken"
		thing.examineText = "Crazed plexiglas and drying gel. The guard "
			.. "slumps; his marching kit does not march."
		local rations = Item("preserved rations", "a guard's preserved rations",
			"Autarchy field rations, gel-sealed four thousand years. "
			.. "Technically food. Philosophically a dare.")
		rations:alias("rations")
		rations:set("gettable", true)
		rations:set("taste", "of history, wax, and a soldier's patience.")
		rations:set("onEaten", function(game, thing)
			if thing.holder then thing.holder:remove(thing) end
			if game:heal() then
				game:say("You honor the dare. Four thousand years and the "
					.. "Autarchy's quartermaster still delivers: a wound "
					.. "troubles you less.")
			else
				game:say("You honor the dare. Dense, waxy, adequate. The "
					.. "quartermaster would accept that review.")
			end
		end)
		warriors:add(rations)
		game:say("The amber cylinder gives on the second blow -- gel "
			.. "sheets down, the guard slumps, and his marching kit "
			.. "spills at your feet. The crash rolls down the halls.")
	end)
	warriors:add(amber)

	local viridian = Item("viridian cylinder", "the viridian cylinder, sealed",
		"A guard-mummy in viridian gel, spear still shouldered, four "
		.. "thousand years into the watch.")
	viridian:alias("viridian")
	viridian:set("onBreak", function(game, thing)
		if thing:get("broken") then
			game:say("Its pieces are done breaking.")
			return
		end
		thing:set("broken", true)
		thing.description = "the viridian cylinder, broken"
		thing.examineText = "The guard finished slumping; the gel is "
			.. "finishing drying. The watch is over."
		game:say("The viridian cylinder shatters; gel gouts across the "
			.. "floor and the guard folds out of his watch at last. The "
			.. "crash rolls down the halls.")
	end)
	warriors:add(viridian)

	local orange = Item("orange cylinder", "the orange cylinder, sealed -- and wrong",
		"The gel in this one has gone ORANGE, and it is not entirely "
		.. "still. Whatever the guard is keeping now, it is not the watch.")
	orange:alias("orange")
	orange:set("onBreak", function(game, thing)
		if thing:get("broken") then
			game:say("Nothing left in it but the smell of bad decisions.")
			return
		end
		thing:set("broken", true)
		thing.description = "the orange cylinder, broken -- a mistake"
		thing.examineText = "Burst plexiglas rimed with orange dust. The "
			.. "guard inside is mostly fungus now, and glad of the air."
		game:say("The orange cylinder cracks -- and EXHALES. A gout of "
			.. "spores takes you full in the face.")
		game:wound("Spore-Bitten", "the orange dust finds your lungs and "
			.. "files a claim.")
	end)
	warriors:add(orange)

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
			and not game.sneaked
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
		if item.name == "ego-core" then
			game.player:remove(item)
			silas:add(item)
			game:award("archivist_whole", 10,
				"[+10 -- the archivist, made whole]")
			game:say('Silas holds the core to his brow. His eyes flicker '
				.. 'through four thousand years in a breath, and when he '
				.. 'speaks, it is with two voices in perfect agreement. '
				.. '"The lattice is complete. The dead may rest. And you, '
				.. 'scavenger -- you are WRITTEN IN."')
			return
		end
		if item.name == "friend's fungus" then
			game.player:remove(item)
			silas:add(item)
			game:award("archivist_dosed", 5,
				"[+5 -- the archivist, agreeable]")
			game:say('Silas takes the pouch with both hands, and for the '
				.. 'first time turns from the wall. "The mystic\'s own. '
				.. 'You climbed for this." He doses the wafer-port under '
				.. 'his jaw, and his shoulders settle an inch. "Ask me '
				.. 'anything. Better: ask the lattice."')
			local lantern = Item("ulfire lantern", "the ulfire lantern",
				"A lantern that burns the ninth colour. Things lit by it "
				.. "show what they are, not what they seem.")
			lantern:alias("lantern")
			lantern:set("gettable", true)
			lantern:set("lightable", true)
			lantern:set("onLit", function(game2)
				local box = game2.player:carrying("manifold box")
				if box and not box:get("opened") then
					box:set("opened", true)
					for i = 1, #box.contents do
						box.contents[i]:set("hidden", nil)
					end
					game2:say("Under the ninth colour the box shows what "
						.. "it is: a fold of space wearing a box costume. "
						.. "A compartment that was always there opens "
						.. "outward from somewhere else, and inside -- "
						.. "the EGO-CORE, humming its owner's name.")
				end
			end)
			game.player:add(lantern)
			game:say('He presses something into your hands: a lantern '
				.. 'that burns a colour you have no name for. "Ulfire. '
				.. 'For seeing what things are. You will know when."')
		elseif item.name == "dates" then
			game:say('Silas declines with a small bow. "I read the dead, '
				.. 'not the dinner."')
		else
			game:say('Silas considers it, and returns it. "Not what the '
				.. 'lattice wants. Not yet."')
		end
	end)
	memory:addCharacter(silas)

	-- --------------------------------------------------- the jackal pack
	-- Staged offstage; butchered meat opens an account. Outdoors only.
	local pack = Engine.Character("jackal pack", "a pack of pthalo-jackals",
		"Pthalo-jackals: cautious, clever, cerulean-coated. Their eyes do "
		.. "sums -- you, minus what you carry, minus what you bleed. It is "
		.. "not you they want.")
	pack:alias("jackals", "jackal", "pack")
	pack:set("hostile", true)
	pack:set("vigor", 3)
	pack:set("struckText", "The blow lands; the pack gives ground "
		.. "snarling, thinner by one.")
	pack:set("koText", "The last jackal breaks and runs south, ledger "
		.. "unbalanced. The road is yours.")
	pack:set("onDeath", function(game)
		game:award("jackals_settled", 5, "[+5 -- the pack is settled]")
	end)
	pack:set("onGift", function(game, item)
		if item.name == "zox haunch" then
			game.player:remove(item)
			game:say("The pack closes over the haunch with terrible "
				.. "courtesy and is gone south before the sand settles. "
				.. "The ledger reads: paid.")
			pack:set("dead", true)
			pack:set("hostile", nil)
			local room = pack.location
			if room then
				for i = 1, #room.characters do
					if room.characters[i] == pack then
						table.remove(room.characters, i)
						break
					end
				end
				pack.location = nil
			end
			game:award("jackals_settled", 5, "[+5 -- the pack is settled]")
		else
			game:say("The pack noses it and lets it fall. It is not you "
				.. "they want; it is not this either.")
		end
	end)

	g:addTrigger("pack_arrives", function(game)
		if pack.location ~= nil or pack:get("dead") then return false end
		local room = game.player.location
		if room ~= wreck and room ~= exterior then return false end
		if game.player:carrying("zox haunch") then return true end
		for i = 1, #room.contents do
			if room.contents[i].name == "zox haunch" then return true end
		end
		return false
	end, function(game)
		game.player.location:addCharacter(pack)
		game:say("They come in low and unhurried, cerulean-coated, "
			.. "filling the road. The nearest growls -- a sound with "
			.. "arithmetic in it -- and the pack looks from you to your "
			.. "bag, and back.")
	end, false)

	g:addTrigger("pack_presses", function(game)
		return pack.location ~= nil
			and game.player.location == pack.location
			and not pack:get("dead")
			and not game.sneaked
	end, function(game)
		local n = (pack:get("owed") or 0) + 1
		pack:set("owed", n)
		pack:set("aware", true)
		if n == 1 then
			game:say("The pack spreads, unhurried, sure of you.")
		elseif n % 2 == 1 then
			game:wound("Pack-Torn", "a jackal takes its installment out "
				.. "of your calf.")
		else
			game:say("Yellow eyes do the arithmetic again.")
		end
	end, true)

	-- ------------------------------------------------------ hall of hounds
	local tank = Item("gel tank", "the sweating gel tank",
		"Preservative gel, faintly luminous. The hound inside is sleek as "
		.. "a racing dog and half chrome. It is not coming out; it is not "
		.. "trying to.")
	tank:alias("tank", "glass")
	hounds:add(tank)

	local hound = Item("cyborg hound", "a cyborg hound, gel-slick, preserved",
		"One of An-Rah's coursers: servo hocks, chrome ribs, glass lenses, "
		.. "the rest of it dog. Heavy as a rolled carpet.")
	hound:alias("hound", "dog")
	tank:add(hound)

	local servo = Item("sparking servo", "a sparking servo",
		"A fist-sized actuator out of the hound's chest, still holding "
		.. "charge. Strike its leads and it spits fat blue sparks.")
	servo:alias("servo")
	servo:set("gettable", true)
	servo:set("hidden", true)
	hound:add(servo)

	local jackalJar = Item("jackal jar", "a jackal-headed canopic jar",
		"A sealed jar with a jackal's head, ears swept back along the "
		.. "lid. Something folded shifts inside.")
	jackalJar:set("gettable", true)

	local brain = Engine.Character("spawn of brain",
		"a fungal brain on two small legs, jackal jar for a head, listening",
		"A fungal brain that walks on two small legs, the jackal canopic "
		.. "jar worn as a hat. No eyes, and it does not appear to want "
		.. "any; it twitches toward every noise, precise as a metronome.")
	brain:alias("spawn", "brain")
	brain:set("hostile", true)
	brain:set("vigor", 2)
	brain:set("struckText", "The blade parts a lobe; the brain staggers, "
		.. "reorients by ear, and keeps coming.")
	brain:set("koText", "The last cut is the last. The brain folds, and "
		.. "the jackal jar rolls to your feet and settles upright.")
	brain:set("onDeath", function(game)
		hounds:add(jackalJar)
		hounds.description = "A long gallery, a sweating gel tank, a "
			.. "preserved hound. The listener lies folded; the hall keeps "
			.. "only the tank's slow drip now."
		hounds:set("darkBlurb", "Dark, and close. Glass somewhere, "
			.. "sweating. Nothing listens but you.")
		game:award("brain_quelled", 5, "[+5 -- the spawn of brain is quelled]")
	end)
	hounds:addCharacter(brain)

	jackalJar:set("onTaken", function(game)
		game:award("jackal_jar", 5, "[+5 -- the jackal jar, claimed]")
	end)

	g:addTrigger("brain_menace", function(game)
		return game.player.location == hounds and not brain:get("dead")
			and not game.sneaked
	end, function(game)
		local n = (hounds:get("tick") or 0) + 1
		hounds:set("tick", n)
		brain:set("aware", true)
		if n == 1 then
			game:say("The twitching stops. Then it starts toward you, "
				.. "precise as a metronome.")
		elseif n % 2 == 1 then
			game:wound("Head-Butted", "the jar-helmed thing rams you at "
				.. "knee height, harder than it has any right to.")
		else
			game:say("Small feet, counting your position.")
		end
	end, true)

	g:addTrigger("brain_calm", function(game)
		return (hounds:get("tick") or 0) > 0
			and (game.player.location ~= hounds or brain:get("dead"))
	end, function(_game)
		hounds:set("tick", 0)
		brain:set("aware", nil)
	end, true)

	-- ------------------------------------------------------------ summit
	local mystic = Item("ossified corpse", "an ossified mystic",
		"A corpse turned to stone mid-meditation, orange fungus weeping "
		.. "from its eyes and mouth -- the wellspring, it seems, of all "
		.. "the rot below. Its clasped hands hold their shape around "
		.. "something.")
	mystic:alias("mystic", "corpse", "statue")
	summit:add(mystic)

	local fungus = Item("friend's fungus", "a pouch of pink fungus",
		"A pouch of pink fungus, soft and faintly warm. The Autarchy fed "
		.. "it to guests of state: whoever ingests it becomes extremely "
		.. "agreeable, and stays that way for hours.")
	fungus:alias("fungus", "pouch")
	fungus:set("gettable", true)
	fungus:set("hidden", true)
	fungus:set("taste", "of a microdose of agreement. For one long minute "
		.. "the sand seems reasonable, the tomb well-run.")
	fungus:set("onEaten", function(game)
		game:say("You eat the whole pouch. The next hour is spent agreeing "
			.. "warmly with the wind, the stone, and a rock that reminds "
			.. "you of your mother. When it passes, the pouch is gone and "
			.. "the archivist below will never know what he missed.")
		game.player:remove(game.player:carrying("friend's fungus"))
	end)
	mystic:add(fungus)

	-- ----------------------------------------------------------- chimney
	local growth = Item("orange growth", "orange growth, floor to crown",
		"The fur of the chimney: soft, warm, and wrong. It flinches from "
		.. "your light by a finger's width.")
	growth:alias("growth", "fur")
	chimney:add(growth)

	local centipede = Engine.Character("glass centipede",
		"a glass centipede, four feet of translucent patience",
		"Four feet of centipede in a carapace like poured glass -- you "
		.. "see it mostly by what bends behind it. It does not move while "
		.. "you watch.")
	centipede:alias("centipede", "glass")
	centipede:set("hostile", true)
	centipede:set("vigor", 1)
	centipede:set("koText", "The blade finds it mid-flow: the centipede "
		.. "shatters along its length like a dropped icicle.")
	centipede:set("onDeath", function(game)
		chimney.description = "A throat of stone furred with orange "
			.. "growth. Glass litter glitters in the fur where the "
			.. "centipede came apart."
		game:award("centipede_quelled", 5, "[+5 -- the centipede, answered]")
	end)
	chimney:addCharacter(centipede)

	g:addTrigger("centipede_springs", function(game)
		return game.player.location == chimney
			and not centipede:get("sprung")
			and not centipede:get("dead")
			and not game.sneaked
	end, function(game)
		centipede:set("sprung", true)
		centipede:set("aware", true)
		game:say("The growth beside you bends wrong -- and four feet of "
			.. "glass uncoils out of it, faster than the eye wants to "
			.. "allow.")
		game:wound("Centipede Venom", "twin punctures in the calf; the "
			.. "venom goes in cold.")
	end, false)

	g:addTrigger("centipede_presses", function(game)
		return game.player.location == chimney
			and centipede:get("sprung") == true
			and not centipede:get("dead")
	end, function(game)
		local n = (chimney:get("coil") or 0) + 1
		chimney:set("coil", n)
		if n % 2 == 0 then
			game:wound("Centipede Venom", "it strikes again from the fur, "
				.. "cold and exact.")
		else
			game:say("A ripple crosses the growth: it is repositioning.")
		end
	end, true)

	-- ------------------------------------------------ canopic jars (slice)
	local sphere -- built after the hall; the plinth hook closes over it
	local canopic = g:room("Hall of the Canopic Jars",
		"Five plinths ring a central stair in a pentagon of dressed stone. "
		.. "Three jars stand answered -- baboon, human, mantis. The falcon "
		.. "and jackal plinths stand empty, lit crimson: cupped talons and "
		.. "parted jaws, each around the shape of something lost.")
	memory:connect("east", canopic, "west")

	local seated = Item("jars", "three seated canopic jars",
		"Baboon, human, mantis: sealed, seated, satisfied. Their plinths "
		.. "glow a settled white.")
	seated:alias("three jars", "seated jars")
	canopic:add(seated)

	local function sealCheck(game)
		local falconHome, jackalHome = false, false
		for _, it in ipairs(canopic.contents) do
			if it.name == "falcon plinth" then
				for _, c in ipairs(it.contents) do
					if c.name == "falcon jar" then falconHome = true end
				end
			elseif it.name == "jackal plinth" then
				for _, c in ipairs(it.contents) do
					if c.name == "jackal jar" then jackalHome = true end
				end
			end
		end
		if falconHome and jackalHome then
			game:say("The last jar settles -- and every plinth answers at "
				.. "once, crimson steadying to white around the ring. Above "
				.. "the stair, stone parts from stone with a sigh. The way "
				.. "UP stands open.")
			game:award("seal", 10, "[+10 -- the seal answers the jars]")
			canopic.description = "Five plinths, five jars, one pentagon "
				.. "of dressed stone -- all of it answered, all of it "
				.. "white. The stair above stands open on the dark."
			canopic:connect("up", sphere, "down")
		end
	end

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
			.. "sentence. The plinth's crimson steadies to white.")
		plinth.examineText = "The falcon jar sits answered in its talons, "
			.. "the light gone white. The carving reads as finished."
		sealCheck(game)
	end)
	canopic:add(plinth)

	local jplinth = Item("jackal plinth", "the empty jackal plinth",
		"Carved stone jaws, parted around an absence, lit crimson.")
	jplinth:alias("jackal stand")
	jplinth:set("onReceive", function(game, item)
		if item.name ~= "jackal jar" then
			game:say("The stone jaws refuse it. They were parted for one "
				.. "thing.")
			jplinth:remove(item)
			game.player:add(item)
			return
		end
		game:say("The jar settles between the jaws, and they read as "
			.. "closed at last. The plinth's crimson steadies to white.")
		jplinth.examineText = "The jackal jar sits answered in the stone "
			.. "jaws, the light gone white."
		sealCheck(game)
	end)
	canopic:add(jplinth)

	-- --------------------------------------------------- the burial sphere
	sphere = g:room("Burial Sphere of Nassak An-Rah",
		"A spherical chamber carved over every inch with funeral prayers, "
		.. "and nothing in it obeys the ground. At the dead centre hangs "
		.. "the Autarch's coffin: clouded glass, its field failing, its "
		.. "interior a slow orange churn.")
	sphere:set("dark", true)
	sphere:set("darkBlurb",
		"Gloom, and no floor your feet believe in. Somewhere at the centre "
		.. "something turns over, slowly, like a sleeper.")

	local coffin = Item("coffin", "the Autarch's anti-entropy coffin",
		"A clouded glass sphere. Past the cloud, shapes drift and turn "
		.. "like fish under ice: bone, and things buried to be kept. A "
		.. "seam at its equator, fine as a hair -- it could be PRIED, "
		.. "with an edge.")
	coffin:alias("glass sphere", "casket")
	coffin:set("closed", true) -- the pry is the only way in
	sphere:add(coffin)

	local box = Item("manifold box", "An-Rah's manifold box",
		"A small gilded box that doesn't quite fit the space it sits in "
		.. "-- hypergeometric, and heavier inside than out.")
	box:alias("box")
	box:set("gettable", true)
	box:set("hidden", true)
	coffin:add(box)

	local core = Item("ego-core", "the Autarch's ego-core",
		"A spindle of memory-lazulite, warm as a kept promise. It hums "
		.. "a name: its own.")
	core:alias("core")
	core:set("gettable", true)
	core:set("hidden", true)
	box:add(core)

	local prayers = Item("prayers", "funeral prayers, carved everywhere",
		"Carved to be read from every direction at once. READ them to "
		.. "study the lines.")
	prayers:alias("prayer", "carvings", "walls")
	sphere:add(prayers)

	local wrath = Item("prayer of wrath", "the Prayer of Wrath",
		"A word with edges. The chamber's law, waiting to be invoked.")
	wrath:alias("wrath")
	wrath:set("hidden", true)
	sphere:add(wrath)

	local balm = Item("prayer of balm", "the Prayer of Balm",
		"A word like water finding a crack. Said aloud, it mends the sayer.")
	balm:alias("balm")
	balm:set("hidden", true)
	sphere:add(balm)

	local mending = Item("prayer of mending", "the Prayer of Mending",
		"A word that remembers how things were made. Said aloud over the "
		.. "broken, it argues them whole.")
	mending:alias("mending")
	mending:set("hidden", true)
	sphere:add(mending)

	prayers:set("readText",
		"Most of it is names and grief. But three lines are RUNG, cut "
		.. "deeper than the rest, meant to be SAID aloud: the PRAYER OF "
		.. "BALM, the PRAYER OF WRATH -- and beneath them, oldest and "
		.. "deepest, the PRAYER OF MENDING.")
	prayers:set("onRead", function(_game)
		wrath:set("hidden", nil)
		balm:set("hidden", nil)
		mending:set("hidden", nil)
	end)

	mending:set("onSaid", function(game)
		if not coffin:get("pried") then
			game:say("The word finds nothing broken here worth its breath.")
			return
		end
		if game.player:carrying("manifold box") == nil
			and not game.scoredKeys["laid_to_rest"]
			and sphere.characters[1] ~= nil then
			game:say("The chamber will not mend around its tenant. The "
				.. "Horror first.")
			return
		end
		if game.scoredKeys["laid_to_rest"] then
			game:say("The coffin is whole. The word rests too.")
			return
		end
		coffin:set("pried", nil)
		coffin:set("closed", true)
		coffin.examineText = "The glass sphere hangs whole at the "
			.. "chamber's heart, its equator seamless -- you know where "
			.. "the cracks were, and cannot find them. Past the clearing "
			.. "cloud, Nassak An-Rah lies re-housed among his wrappings, "
			.. "composed, the gold wire at his joints at rest."
		sphere.description = "A spherical chamber carved with funeral "
			.. "prayers, quiet in the way of a made bed. The coffin hangs "
			.. "whole at the dead centre, seam sealed, the Autarch "
			.. "re-housed within; the ash of the Horror turns in its slow "
			.. "orbit, out of respect."
		game:say("You say the PRAYER OF MENDING, and the chamber leans on "
			.. "the cracks until they remember being whole. Seams close "
			.. "like water under silk. Past the clearing cloud the "
			.. "Autarch settles among his wrappings -- composed, kept, "
			.. "DREAMING SOMETHING KIND.")
		game:award("laid_to_rest", 10, "[+10 -- the Autarch, laid to rest]")
	end)

	local horror = Engine.Character("fungal horror",
		"the Fungal Horror, coiled around the Autarch's bones",
		"A single muscle of orange fungus the size of a river-snake, "
		.. "moving the Autarch's dead limbs like its own. Where you cut "
		.. "it, it remembers.")
	horror:alias("horror", "coil")
	horror:set("mends", true)
	horror:set("mendsText", "The blade opens a rent in the orange mass -- "
		.. "and the rent closes as you watch. Steel is a treadmill here. "
		.. "The walls were carved for this.")

	coffin:set("onPried", function(game)
		if coffin:get("pried") then
			game:say("The coffin already stands open, and regrets it.")
			return
		end
		local edged = false
		for i = 1, #game.player.contents do
			if game.player.contents[i]:get("weapon") then edged = true end
		end
		if not edged then
			game:say("The seam wants a lever with an edge. Your fingers "
				.. "are not that.")
			return
		end
		coffin:set("pried", true)
		coffin:set("closed", nil) -- what it kept is reachable now
		coffin.examineText = "The coffin stands open, its cloud let out. "
			.. "What it kept is out with it."
		horror:set("hostile", true)
		horror:set("aware", true)
		sphere:addCharacter(horror)
		game:say("The seam gives. The cloud sighs out -- and the coffin's "
			.. "tenant UNCOILS, taking the Autarch's bones with it like a "
			.. "puppet recalled to the stage.")
	end)

	g:addTrigger("horror_menace", function(game)
		return game.player.location == sphere
			and horror.location == sphere
			and not horror:get("dead")
	end, function(game)
		local n = (sphere:get("press") or 0) + 1
		sphere:set("press", n)
		if n == 1 then
			game:say("The coil turns its borrowed skull toward you and "
				.. "considers.")
		elseif n % 2 == 1 then
			game:wound("Coil-Struck",
				"a limb of fungus finds you across the weightless dark.")
		else
			game:say("It drifts nearer, unhurried. It has time.")
		end
	end, true)

	balm:set("onSaid", function(game)
		if balm:get("spent") then
			game:say("The balm has given what it had.")
			return
		end
		balm:set("spent", true)
		if game:heal() then
			game:say("The word goes through you like water finding a "
				.. "crack. A wound closes, politely.")
		else
			game:say("The word finds nothing in you to mend, and settles "
				.. "for the mood.")
		end
	end)

	wrath:set("onSaid", function(game)
		if horror.location ~= sphere or horror:get("dead") then
			game:say("The word waits. It knows what it is for, and this "
				.. "is not it.")
			return
		end
		horror:set("dead", true)
		horror:set("hostile", nil)
		for i = 1, #sphere.characters do
			if sphere.characters[i] == horror then
				table.remove(sphere.characters, i)
				break
			end
		end
		horror.location = nil
		local ash = Item("drift of ash", "the ash of the Fungal Horror",
			"Fine grey ash shot through with dull orange, hanging "
			.. "weightless where the Horror burned. Nothing in it mends.")
		ash:alias("ash")
		sphere:add(ash)
		sphere.description = "A spherical chamber carved with funeral "
			.. "prayers, quiet in the way of a made bed. The coffin hangs "
			.. "open at the centre; the ash of the Horror turns in a slow "
			.. "orbit, out of respect."
		game:say("You say the PRAYER OF WRATH, and the chamber says it "
			.. "with you. Every carved line ignites at once -- the Horror "
			.. "is unwritten limb by limb, ash before it can remember how "
			.. "to mend.")
		game:award("wrath", 10, "[+10 -- the chamber's law, invoked]")
		game.won = true
		game:say("*** The tomb is quiet. The expedition stands. "
			.. game.score .. "/" .. game.maxScore .. " ***")
	end)

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
	g:addHint({ key = "plinth", question = "What are the jars for?",
		levels = {
			"Two plinths burn crimson: cupped talons, parted jaws. Each "
				.. "was carved for one thing.",
			"The spawns wear them as hats. Quell both, TAKE the jars, and "
				.. "PUT each ON its matching plinth.",
		},
		available = function(_) return canopic.visited end,
		resolved = function(game) return game.won == true end })

	g:addHint({ key = "listener", question = "Something small counts my steps.",
		levels = {
			"It hunts like its sibling in the warriors' hall.",
			"Light up, and the blade you already carry answers it. It "
				.. "wears what the jackal plinth wants.",
		},
		available = function(_) return hounds.visited end,
		resolved = function(_) return brain:get("dead") == true end })
	g:addHint({ key = "chimney", question = "The chimney bit me.",
		levels = {
			"It is faster than you, once. Then it is glass.",
			"With light raised, one clean blow: ATTACK CENTIPEDE.",
		},
		available = function(_) return chimney.visited end,
		resolved = function(_) return centipede:get("dead") == true end })
	g:addHint({ key = "mystic", question = "The stone man on the summit holds something.",
		levels = {
			"His hands kept their shape around it for a reason.",
			"SEARCH the ossified corpse. The archivist below would thank "
				.. "you for what it holds.",
		},
		available = function(_) return summit.visited end,
		resolved = function(game) return game.scoredKeys["archivist_dosed"] end })

	g:addHint({ key = "jackals", question = "A pack is doing arithmetic at me.",
		levels = {
			"They keep a ledger, and your knife opened an account.",
			"GIVE ZOX HAUNCH TO JACKAL PACK -- or the blade balances it "
				.. "the other way.",
		},
		available = function(_) return pack.location ~= nil
			or pack:get("dead") == true end,
		resolved = function(_) return pack:get("dead") == true end })
	g:addHint({ key = "box", question = "The gilded box won't open.",
		levels = {
			"It isn't closed. It's folded. You need a light that shows "
				.. "what things ARE.",
			"The dosed archivist gave you it: carry the box, LIGHT ULFIRE "
				.. "LANTERN.",
		},
		available = function(game) return game.player:carrying("manifold box") ~= nil end,
		resolved = function(game) return game.scoredKeys["archivist_whole"] end })
	g:addHint({ key = "rest", question = "The coffin stands open and wrong.",
		levels = {
			"The walls hold three prayers, not two. Read them again.",
			"With the Horror gone: SAY PRAYER OF MENDING.",
		},
		available = function(_) return coffin:get("pried") == true
			and sphere.characters[1] == nil end,
		resolved = function(game) return game.scoredKeys["laid_to_rest"] end })

	g:addHint({
		key = "horror",
		question = "The coffin's tenant will not stay cut.",
		levels = {
			"Steel is a treadmill. The room itself disagrees with it.",
			"READ PRAYERS, then SAY PRAYER OF WRATH.",
		},
		available = function(_) return sphere.visited end,
		resolved = function(game) return game.won == true end,
	})

	-- ------------------------------------------------------------ start
	g.maxScore = 95
	g.player.location = wreck
	wreck.visited = true
	return g
end
