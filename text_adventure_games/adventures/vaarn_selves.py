"""One hundred selves (CCB's easter egg): EXAMINE SELF, once per expedition,
discovers who the scavenger has been all along. Each is a Vaults of Vaarn
character sketch -- ancestries, gifts, mutations, and bad decisions from the
zine's tables, described in the tomb's own voice. The draw happens at action
time (journaled), so a save restores the same self.

Second person, present tense, 25-50 words. The joke is that the player never
asked until now."""

SELVES = (
    "You are true-kin, or so your mother swore: unmutated stock of the old "
    "blood, sun-cracked and thin. The only heirloom of that pedigree is a "
    "jaw that aches before sandstorms. It aches now.",
    "You are a new-hyena, golden-coated, and you have been laughing at the "
    "wrong moments your whole life. The drover's coat you wear belonged to "
    "someone who found that charming. Briefly.",
    "You are a synth in a scavenger's body, and you have known it exactly "
    "since this morning: the wound on your forearm shows braided silver "
    "beneath, and no blood at all worth mentioning.",
    "You are a mycomorph -- a colony wearing the consensus of a person. "
    "Under stress the consensus loosens; your left hand is currently "
    "voting to be a fan of pale gills. You outvote it.",
    "You are cacogen: born under a bad star and visibly so. Your shadow "
    "falls a half-second after you move, and it has never once been late "
    "to anything important. You check it often.",
    "You are a new-coyote in an indigo coat of your own fur, and you "
    "believe, privately, calmly, and against all evidence, that you are "
    "human. The mask you carry is blank. It is a spare face.",
    "You are true-kin gone feral: court manners, gutter grammar, a "
    "duelling scar you tell three different stories about. All three are "
    "lies. The truth involves a door.",
    "You are a new-ibis, white as paper, and you cannot stop writing: "
    "margins, walls, your own forearm, which currently reads TRUST THE "
    "WATER in your own cramped hand. You do not remember writing it.",
    "You are a planeyperson, or partly one: viewed straight-on you pass "
    "for anyone, but in profile you thin alarmingly, and you have learned "
    "to take corners with ceremony. Doors love you. Cracks adore you.",
    "You are a mystic irradiated at birth, and small dead things know it: "
    "moths, sand-fleas, one memorable kestrel. They gather at your camps "
    "in respectful circles, waiting for instructions you refuse to give.",
    "You are a new-tortoise, slow by policy rather than nature, with a "
    "shell you have papered inside with receipts for everything the "
    "desert ever took from you. The list is itemized. It is long.",
    "You are a vat-grown laborer with a serial number where a family name "
    "should be, and a family name anyway -- you stole a good one off a "
    "grave-marker and have worn it honestly ever since.",
    "You are a new-moth, dust-winged and lamp-hearted. You have flown at "
    "exactly one open flame in your life and you married them. That was "
    "long ago. You still cannot pass a lit window with dignity.",
    "You are true-kin with the Vice: you grip your own wrist to steady "
    "your hands, the way the old kings did, though you learned it from a "
    "puppet show. Your hands shake anyway. The grip is the point.",
    "You are a synth built for gardening, repurposed for grave-robbing, "
    "and you resent none of it: tombs, you have found, are just gardens "
    "run in reverse. Something is always coming up.",
    "You are a new-vulture, and you are tired of the jokes. You have "
    "never once eaten a colleague. The bald head is dignified. The "
    "hunched patience is professionalism. The circling was one time.",
    "You are a mutant whose gift is small and constant: you always know "
    "which way the nearest water lies. It is a cruel talent for Vaarn to "
    "issue. The answer is almost always 'far.'",
    "You are a new-cat of no particular breed, which among new-cats is "
    "the only insult that draws blood. You carry a brass mirror you "
    "never look in. It is for signaling. It is definitely for signaling.",
    "You are cacogen, and your eyes are holes of modest depth -- an inch, "
    "maybe two. People who look too long report a faint draft. You wear "
    "smoked lenses at funerals, out of courtesy.",
    "You are a faa nomad three oaths from home: one to a well, one to a "
    "dead riding-bird, one to a person whose face you now assemble from "
    "other people's features. The oaths hold. The face doesn't.",
    "You are a new-pangolin, armored in your own diminishing currency -- "
    "you have been prying off scales to pay tolls since the border, and "
    "you are worth less and lighter with every road.",
    "You are a mystic whose power source is a cursed ring you cannot "
    "remove and whose gift is that you always know the time. Not the "
    "hour. The time: LATE. It is always LATE. The ring is very smug.",
    "You are true-kin royalty by the math of it -- everyone is, twenty "
    "generations deep -- but you alone brought the paperwork: a genealogy "
    "scroll, self-annotated, that no one has ever asked to see.",
    "You are a new-octopus in a man-shaped harness of straps and salve, "
    "miserably far from any sea, curious beyond all sense. Three of your "
    "arms are asleep. One is going through your own pockets again.",
    "You are a child of the Hegemony's leftovers: your blood carries "
    "nanomachines that mend you slightly too well. Your scars vanish "
    "overnight, and with them the proof. You keep a written list of "
    "wounds, so that something remembers.",
    "You are a new-ram with one horn sawn short -- a sentence served, in "
    "some town whose name you keep like a stone in your boot. The horn is "
    "growing back. Towns do not.",
    "You are a lichen-priest's apprentice who never finished: half your "
    "scalp is a tonsure of pale green symbiote that photosynthesizes "
    "opinions. In strong sun you feel briefly, dangerously optimistic.",
    "You are a new-hound who has never once been lost, which is not the "
    "gift it sounds: you always know exactly how far you are from home, "
    "to the pace. The number is obscene. It ticks up nightly.",
    "You are a duneborn foundling raised by a well-cult, taught to "
    "genuflect at pumps and weep at rain. You have seen rain twice. Both "
    "times you conducted yourself disgracefully, and do not regret it.",
    "You are a synth who dreams, which the manuals say is impossible, "
    "and dreams exclusively of filing. Endless drawers, perfect order, a "
    "label for everything. You wake rested. You tell no one.",
    "You are a new-serpent in a padded coat, legless below the waist and "
    "tired of stairs, balanced on a coiled tail that children ask to "
    "touch and adults pretend not to stare at. You let the children.",
    "You are a mutant with a functioning compass rose birthmarked across "
    "your back, accurate to true north, useless to you personally -- you "
    "cannot see your own back. Strangers navigate by you in bars.",
    "You are true-kin of the archivist caste, excommunicated for a "
    "marginal note. You still write in the approved hand. The note said "
    "'citation needed,' and you stand by it.",
    "You are a new-mule, and everything they say is true: you can carry "
    "double, go days dry, and hold a grudge across a decade with the "
    "patience of geology. Three are active. One matures this year.",
    "You are a gene-tinker's apology: made too pretty for labor and too "
    "strong for court, with teeth like a commemorative dinner service. "
    "You bite through wire for money and hearts for free.",
    "You are a new-owl who cannot turn her head all the way around and "
    "has spent a lifetime being asked to. Your neck aches from "
    "demonstrations. Your patience died young. Your aim is improving.",
    "You are a mystic of the eyeless persuasion -- sighted, but sworn to "
    "act otherwise on holy days. You have lost track of the calendar. To "
    "be safe, you squint always, and bump into things devoutly.",
    "You are a saltflat pearl-diver a thousand miles from the memory of "
    "water, chest like a barrel, able to hold your breath through most "
    "arguments and one whole marriage.",
    "You are a new-boar with tusks capped in trade-silver, each cap "
    "engraved with the name of someone who insisted you were harmless. "
    "There is room on the left tusk for two more names.",
    "You are cacogen with a quantum stutter: sometimes, briefly, there "
    "are two of you a hand's width apart, agreeing. Witnesses dislike "
    "it. You have learned to stand near curtains.",
    "You are an ex-legionary of a Hegemony that no longer exists, still "
    "in half the uniform, still polishing the buttons. The empire owes "
    "you eleven years' pay. You have kept the receipts and the bayonet.",
    "You are a new-heron, stilt-legged and ceremonious, incapable of "
    "hurry. You have outwaited floods, sieges, and one glacier. The "
    "tomb's patience does not impress you. You have stood in colder.",
    "You are a fungus-eater's child, weaned on Friend's Fungus and weird "
    "honey, and consequently you like everyone. It has nearly killed you "
    "nine times. You like the nine people responsible.",
    "You are a new-badger, low-slung and legally dead in two provinces, "
    "a professional under-digger of walls whose proudest work collapsed "
    "a courthouse. Allegedly. The tunnel was never found. You were.",
    "You are a mutant whose skin maps the sky: freckles migrate nightly "
    "into yesterday's constellations. Astronomers have proposed marriage "
    "for access. You value being loved for yourself, and said no. Twice.",
    "You are true-kin gone to seed in the archive-slums, spectacles "
    "ground from bottle glass, able to read four dead languages and "
    "haggle in none of the living ones.",
    "You are a new-jackal -- pthalo-coated, personally embarrassed by "
    "your cousins' behavior in tombs -- and you tip generously wherever "
    "the dead are concerned. Professional courtesy runs both ways.",
    "You are a synth missing your warranty plate and your first three "
    "years. Sometimes your hands perform a task you never learned -- "
    "rigging, embalming, a cradle-knot -- and you watch them, a stranger "
    "at your own wrists.",
    "You are a new-hare, ears scarred to lace, faster than everything "
    "except your own decisions. You have escaped four dooms and RSVP'd "
    "to a fifth. It is this tomb. You are early.",
    "You are a woman of the glass tribes who walks barefoot on shard-sand "
    "as a discipline, soles like bookbinding leather, gait like a "
    "metronome. You have not made a sound in years you didn't choose.",
    "You are a new-mantis, and you have given up religion twice: once "
    "for love, once because the congregation kept checking where your "
    "hands were. They fold naturally. It means nothing.",
    "You are a tomb-brat, born inside a mausoleum during a sandstorm and "
    "never fully persuaded to leave the type. The dead don't frighten "
    "you; they read as landlords, and you have never paid rent.",
    "You are a mutant with a second pulse in your palm that beats to "
    "someone else's heart. You have never found whose. You shake hands "
    "carefully, listening, like a safecracker.",
    "You are a new-elephant in miniature -- knee-high tusks on a "
    "wrestler's frame -- who forgets nothing and forgives most things, "
    "which is a harder combination than the poets allow.",
    "You are a rust-monk of the Ferrous Word, sworn to oil what squeaks "
    "and free what seizes. Your kit weighs more than your food. You have "
    "anointed doorhinges in this tomb already, without noticing.",
    "You are a new-gazelle wearing lead anklets by choice, because "
    "without them you bolt at surprises, and Vaarn is made of surprises. "
    "The anklets are engraved: STAY. ASK QUESTIONS.",
    "You are cacogen, and mirrors decline you: your reflection is always "
    "a beat behind and slightly better dressed. You have stopped "
    "checking. It waves you on, generously, like a doorman.",
    "You are the last speaker of a language with fourteen words for "
    "erosion and none for goodbye. You inventory the world in it "
    "silently. This tomb, in that tongue, is one long verb.",
    "You are a new-toad, wide as a door and calm as one, with a poison "
    "sweat you can summon by thinking about your father. You wear long "
    "sleeves and think about him rarely, on purpose.",
    "You are an escaped oracle -- the temple bred you to answer, and you "
    "ran before your first question. The gift ripens anyway: lately, "
    "when strangers speak, you know their next word. It is usually "
    "'water.'",
    "You are a new-macaw in molting season, shedding embarrassments of "
    "scarlet everywhere you go, trackable across a province. As stealth "
    "goes you are a parade. You have made loudness a doctrine.",
    "You are a gravedigger's gravedigger: you bury the ones who buried "
    "others, a guild-secret trade with its own knots and courtesies. "
    "Work has been good. Work is always good.",
    "You are a mutant who casts two shadows, and they disagree: one "
    "points with the sun, one with something else's light. Surveyors "
    "have offered money. The second shadow points, just now, DOWN.",
    "You are a new-camel and you have heard every joke, including the "
    "one you are currently thinking of, which a stranger told you in a "
    "caravanserai eleven years ago, better.",
    "You are a bone-setter struck off the rolls for setting a bone that "
    "wasn't broken yet. It broke on schedule, exactly as you'd set it. "
    "The guild called it witchcraft. The patient called it Tuesday.",
    "You are a new-rat of the granary aristocracy, whiskered, waist-"
    "coated, heir to nothing but a good name among thieves -- which in "
    "Vaarn appraises higher than most land.",
    "You are a weather-cousin: barometric, prophetic to a horizon of "
    "four hours, joints that forecast in a dead scale. Right now every "
    "knuckle you own is reading STILLNESS, which is never the good one.",
    "You are a synth whose empathy dial was installed backward: you feel "
    "calmest at funerals and weep at auctions. Estate sales wreck you. "
    "This entire tomb is, technically, an estate.",
    "You are a new-crocodile who took holy orders, smiling by "
    "construction, penitent by choice, dangerous by heritage. Your order "
    "permits one bite a year. You are saving this year's.",
    "You are a courier who swallowed the message: state secret, wax-"
    "sealed, riding in you somewhere these nine years. The war it "
    "concerned is over. Nobody told the seal. It ticks on cold nights.",
    "You are a new-bee, one of a hive-clan's thousand daughters, the "
    "only one born without the choir in her head. The silence is vast "
    "and yours. You dance sometimes, alone, in the old directions.",
    "You are a glass-blower's accident: lungs like bellows, a whistle in "
    "your breath at altitude, and one arm glossy to the elbow where the "
    "melt kissed you. In firelight the arm remembers, and shines.",
    "You are a new-sloth, and the tomb's hazards have not yet noticed "
    "you move. Neither, wholly, have you. Your patience is not a virtue; "
    "it is a metabolism. You started this expedition in spring.",
    "You are a debt-monk: you took on strangers' debts as sins and wear "
    "the ledger as a habit, hemmed in figures. Yours is nearly paid. One "
    "creditor remains. He is dead, and buried deep, and downstairs.",
    "You are a new-falcon, hooded by choice in bright company, because "
    "your eyes read too much: pulse, sweat, the lie forming before the "
    "lips move. The hood is manners. It is off now.",
    "You are a mutant whose bones sing in wind -- flute-holed, the "
    "surgeons said, a fashion of some ancestor's court. In the desert "
    "gale you are a small ominous orchestra. Indoors you are quiet.",
    "You are the widow of a cartographer, still finishing his last map "
    "from memory and spite. There is one blank region left. You are "
    "standing in it.",
    "You are a new-lemur, saucer-eyed, built for a gentler planet, "
    "trafficked here as a curiosity and self-employed since the escape. "
    "Night is your shift. Your eyes make the dark negotiable.",
    "You are an ash-drinker: survivor of a burned city who kept the "
    "habit of tasting ruin -- a fingertip of soot, read like tea leaves. "
    "This tomb's ash, tried at the door, tasted of unfinished business.",
    "You are a new-goat who has eaten three sacred texts and digested "
    "their arguments. You quote scripture no living scholar can source. "
    "Two seminaries want you burned. One wants you tenured.",
    "You are somebody's clone, decanted late and told nothing, "
    "recognized twice in market towns by strangers who fled. You keep a "
    "sketch of your own face, annotated with questions.",
    "You are a new-wolf raised by librarians -- the reverse of the usual "
    "arrangement -- leash-trained on silence and citation. You still "
    "point at footnotes. You still howl, but only at misprints.",
    "You are a stylite come down from the pillar after nineteen years, "
    "legs like rope, soul like a scoured pot, hunting the one prayer the "
    "wind took from you up there. You will know it when you hear it.",
    "You are a new-ox, freed with papers you cannot read and would not "
    "sell, laminated in horn and worn over your heart. The yoke-scar "
    "across your shoulders is fading. You check it every morning.",
    "You are a mutant whose tears crystallize -- little lenses of grief, "
    "faintly magnifying. You have wept perhaps forty times and carry the "
    "evidence in a pouch, through which small things look enormous.",
    "You are a new-chameleon of fixed opinions and unfixed color, "
    "currently the exact blue of Vaarn's sand out of what you insist is "
    "coincidence. Your handshake takes strangers a moment to find.",
    "You are the product of a wager between two gene-barons, and the "
    "terms are sealed until your fortieth year. You are thirty-nine. "
    "Lately you sleep badly, and your teeth feel provisional.",
    "You are a new-swine of impeccable manners, tusked and pomaded, "
    "banned from four banquets for correcting a duke's fork-work. Truffle-"
    "sense runs in the blood: you can smell buried things. You are, at "
    "this moment, nearly deafened.",
    "You are a lightning-struck shepherd with a fern of scar across your "
    "back and a standing offer from three storm-cults. Sheep still obey "
    "you absolutely. It no longer feels like a skill.",
    "You are a new-mole in smoked goggles, star-nosed, reading the world "
    "through your fingertips like fine print. Above ground you are "
    "polite and lost. Below it you are a cathedral's own architect.",
    "You are a failed immortal: the procedure took, then lapsed, leaving "
    "you ageless from the years 20 to 24 and mortal ever after. You "
    "spent the ageless years, by your own account, 'napping.'",
    "You are a new-crow who has sworn off shiny things, a recovering "
    "collector, sponsor-bird to three others in the program. The "
    "glowstone in this tomb has tested you sorely. One day at a time.",
    "You are a leech-barber of the old school, offering haircuts and "
    "humors in one sitting. Business fell off when the leeches "
    "unionized. You respect them for it. You kept their tank.",
    "You are a new-horse who broke her own bridle-oath and lives with "
    "it: never carry, never be carried. You have walked every mile of "
    "your life since. Your spine is a debt no one may ride.",
    "You are cacogen with a door in your forehead -- small, yellow, "
    "locked, a knocker the size of a grape-pip. Nothing has ever "
    "knocked. You keep the knocker polished anyway. Hospitality.",
    "You are a salt-sworn judge of a circuit that no longer exists, "
    "still empowered, by your reading, to try crimes committed on "
    "extinct roads. This tomb predates every road you know. "
    "Jurisdiction, at last.",
    "You are a new-otter, wringing pleasure from a dry world -- you body-"
    "surf dune-faces, hold pebble-juggling tournaments against "
    "yourself, and grieve, briefly and completely, every empty well.",
    "You are a bell-founder's daughter with perfect pitch for alarm: you "
    "can hear a crack in bronze, a lie in a voice, a wrongness in a "
    "room. This room, for the record, has been ringing since you came in.",
    "You are a new-mouse the size of a ten-year-old, an epic poet of "
    "the crumb-saga tradition, forty thousand verses deep into a work "
    "about your grandmother. The tomb will get a canto. Everything does.",
    "You are yourself, only yourself, and exactly yourself: no ancestry "
    "tables, no gift, no mutation -- the single least remarkable person "
    "in Vaarn, statistically miraculous, utterly unprecedented. The "
    "lattice downstairs would kill for a day of your life.",
)
