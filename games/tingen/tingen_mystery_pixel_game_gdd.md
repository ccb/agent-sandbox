# Tingen Mystery Pixel Game - Detailed Design Document

## 0. Important Note

This document contains **design suggestions, not instructions**. It is intended as a feature-testing and vertical-slice planning document for Yumina's future direction. The goal is to explore whether a **2D pixel-art mystery game with living NPC intelligence, world-managed plot progression, enterable buildings, and investigation-combat integration** can serve as a strong new feature testbed.

This document is inspired by the atmosphere and structural strengths of the Tingen arc from *Lord of the Mysteries*, but it is written as a **game systems design document**, not a strict one-to-one adaptation plan.

---

## 0.1 Design Direction Update (2026-06-08) — supersedes the detective framing

The project has **pivoted from a "solve-a-fixed-mystery" detective game to an open-world,
real-time immersive simulation with an AI-managed story.** Where this section conflicts with
the original text below, **this section wins.** Full detail lives in
`docs/superpowers/specs/2026-06-08-tingen-agent-sim-vertical-slice-design.md`.

What changes:

- **NPC intelligence = LLM agents.** The original "60-second strategic intelligence refresh"
  becomes **per-NPC autonomous LLM agents** with their own intent, memory, and plans, that
  perceive and interact with each other. Each agent has a cheap **fallback behavior**
  (its schedule) that runs while it deliberates, so real-time play never stalls.
- **World Manager → World-AI overseer + critic.** The director now receives the full event
  stream and can **re-task an agent, cancel a plan, or coordinate a group beat** to keep the
  emergent story interesting — and enforces invariants like *"the cult is never exposed/caught
  by chance; exposure is gated on the player's involvement."* It also **catches and kills**
  boring or incoherent emergent threads (a coherence/quality critic).
- **No set mystery lines.** The cult faction **genuinely intends** to summon a descending evil
  god and will **actually complete** it if unopposed. The story is *steered*, not scripted.
- **Combat is first-class** and the climax of confrontation, within a **multi-path** immersive
  sim (investigate → sabotage / socially turn / fight). Accumulated **impede** scales the
  climax difficulty.
- **Occult tools + inventory survive, demoted** to player *perception* (divination/spirit-
  vision/dream → directional leads) and *action* (ingredients are a real economy; sabotage
  removes them). **The Gray-Fog Hypothesis Board (detective deduction) is cut.**
- **Architecture:** a **deterministic Godot sim substrate** + an **external Python sidecar**
  that runs the LLM agents/overseer (API keys + nondeterminism quarantined there; saves store
  outcomes not prompts; tests mock the sidecar). Real engine: **Godot 4.6** (not the Yumina
  web engine the original doc targeted).
- **Build approach:** a **vertical slice first** — ~3–5 agents in Iron Cross Street, one cult
  summoning thread, end to end — before scaling to the full city.

The original pillars below (living traversable city, world-managed progression, enterable
interiors, investigation-combat integration, dynamic slotting) **remain valid**; only the
*mechanism* of NPC intelligence and the *detective-deduction* framing are revised.

---

# 1. Executive Summary

## 1.1 Project Vision

Build a **2D top-down pixel-art mystery-action simulation** set in a compact, fully traversable city inspired by Tingen. The player explores a living city with enterable buildings, investigates a spreading occult conspiracy, and tries to prevent a large-scale ritual catastrophe.

The game's distinctive pillar is that the city is not static. A **World Manager** advances the hidden plot, while each character is powered by **60-second strategic intelligence refreshes plus event-driven reactions**. This makes the city feel like a moving machine of secrets, rumors, schedules, panic, mistakes, and hidden agendas.

The intended result is not just an RPG or visual novel, but a **mystery simulation** in which:

- the city changes without the player,
- clues are physical, social, and supernatural,
- combat is dangerous and information-dependent,
- plot progression is structured but partially variable,
- replayability comes from dynamic slotting of events, suspects, locations, and timing.

## 1.2 Primary Product Goal

Create a **vertical slice** that proves Yumina can support:

1. A living 2D city with enterable interiors
2. World-managed narrative progression
3. NPC strategic behavior at scale
4. Investigation systems based on partial information
5. Event-driven mystery escalation
6. Tactical, high-tension combat tied to prior investigation

## 1.3 Core Fantasy

The player fantasy is:

> "I am walking through a city that is hiding something terrible. Every person may know something, every building may contain evidence, and every delay may allow the ritual to get closer to completion."

## 1.4 Why This Is a Strong Yumina Feature Test

This concept stress-tests exactly the kinds of systems Yumina appears to want to explore:

- persistent world simulation
- AI characters with memory and goals
- narrative orchestration
- agent scheduling and event responses
- hybrid authored + emergent storytelling
- highly contextual interactions in a 2D RPG environment

This makes it an unusually good testbed because the genre itself *benefits* from dynamic AI.

---

# 2. Design Pillars

## 2.1 Pillar A: The City Feels Alive

The player should feel that the city continues moving whether or not they are present.

Signs this is working:

- NPCs move with purpose, not random wandering
- rumors spread through districts
- suspicious characters change routes when heat increases
- ordinary citizens react to danger, curfews, and public panic
- different neighborhoods feel socially different

## 2.2 Pillar B: Mystery Is Built from Systems, Not Only Script

The player should not merely consume dialogue; they should infer truth from evidence.

Signs this is working:

- clues come from places, schedules, contradictions, dreams, occult residue, and observed behavior
- players can reach correct conclusions through multiple paths
- misreading evidence produces consequences, not only a hard fail
- key revelations feel earned

## 2.3 Pillar C: Investigation and Combat Are Interlocked

Combat should not feel like a separate mode. Investigation should prepare it, and combat outcomes should reshape future investigation.

Signs this is working:

- scouting a ritual site reveals routes, chokepoints, and ritual anchors
- finding a suspect early weakens later encounters
- losing a witness changes available evidence
- using force too early increases panic or scatters enemies

## 2.4 Pillar D: Horror Comes from Pressure and Uncertainty

The game should not rely mainly on jump scares. Tension should come from incomplete knowledge, looming catastrophe, strange behavior, and difficult tradeoffs.

Signs this is working:

- the player is never fully sure where the next incident will occur
- supernatural events distort normal city routines
- time pressure exists, but not so harshly that exploration becomes impossible
- atmosphere intensifies as the city slips toward catastrophe

## 2.5 Pillar E: Dynamic but Readable Narrative

The game should feel alive and variable without becoming incoherent.

Signs this is working:

- the world manager preserves a recognizable arc
- each run varies in details but retains dramatic logic
- NPC decisions remain explainable in hindsight
- players can form mental models of the city

---

# 3. High-Level Genre Positioning

## 3.1 Genre Blend

The project sits at the intersection of:

- 2D pixel RPG
- mystery/investigation game
- immersive sim lite
- social simulation
- tactical occult combat
- narrative simulation

## 3.2 Notable Reference DNA

This concept can borrow lessons from several design families:

- **Stardew Valley / classic top-down RPG readability** for approachable 2D world navigation
- **Disco Elysium** for investigation, interpretation, layered clue handling, and identity through internal logic
- **Pathologic** for dread, pressure, and city-scale crisis
- **Persona-style scheduling pressure** for day/night structure
- **Project Zomboid / simulation-lite** for living populations and observable routines
- **Into the Breach / tactical clarity** for readable high-stakes encounters
- **Shadows of Doubt** for systemic mystery inspiration, though at a smaller, more curated scale

The project should **not** aim for maximal sandbox complexity initially. It should aim for a strong authored-simulation hybrid.

---

# 4. Target Experience

## 4.1 Emotional Arc

The desired emotional progression:

1. Curiosity
2. Unease
3. Pattern recognition
4. Growing pressure
5. Moral and tactical stress
6. Catastrophic confrontation
7. Aftermath and reflection

## 4.2 What the Player Should Be Doing Minute to Minute

The player should frequently alternate between:

- walking through districts
- entering buildings
- talking to NPCs
- inspecting evidence
- watching routines
- following leads
- consulting an investigation board
- performing occult tools or divination
- deciding where to deploy allies
- responding to sudden incidents
- surviving short, sharp combat encounters

## 4.3 What Makes the Game Memorable

The memorable stories should sound like:

- "I ignored a small warehouse clue and that district became the ritual hub that night."
- "A suspect lied poorly, but I only realized it after seeing them leave through the back alley at dusk."
- "My strongest ally got injured in an early mistake, so I entered the final ritual undermanned."
- "A child witness survived because I evacuated the street early, and that clue saved the run."
- "I thought the church district was safe, but panic drove people into the streets and let the cult hide in the crowd."

---

# 5. Scope Recommendation

## 5.1 Recommended First Deliverable

A **vertical slice**, not a full-length game.

## 5.2 Recommended Vertical Slice Scope

- 1 city map with 8 districts
- 12 to 20 enterable buildings
- 25 to 40 active NPCs
- 6 major named core characters
- 1 main occult plotline
- 2 to 3 dynamic side incidents
- 1 local ritual disruption mission
- 1 final catastrophe sequence
- full day/night loop
- world manager with stage progression
- 60-second AI refresh + event interrupts
- investigation board system
- rumor system
- one combat kit with a few occult tools and firearms

## 5.3 Why Scope Discipline Matters

If the team attempts a full city-scale social sim with dozens of deep behaviors immediately, the project will likely become unwieldy. The purpose of the first version is to validate whether the **systems produce believable mystery and tension**, not to maximize content.

---

# 6. Setting and World Structure

## 6.1 City Design Philosophy

The city should be compact, dense, and memorable rather than large and sparse.

The ideal city:

- can be mentally mapped by the player
- has visually distinct districts
- supports routine observation
- has enough traversal friction to make decisions matter
- contains layered public/private spaces

## 6.2 District Breakdown

### 6.2.1 Investigator Headquarters / Security Company
Purpose:
- mission intake
- report submission
- ally deployment
- evidence storage
- occult tool preparation
- save/rest point

Design notes:
- should feel safe but increasingly strained over time
- visual tone shifts from organized to exhausted as the crisis worsens

### 6.2.2 Residential Street
Purpose:
- ordinary life anchor
- witness interviews
- routine observation
- emotional grounding

Design notes:
- emphasize small domestic spaces
- gossip density should be high
- an ideal place for rumors and visible social change

### 6.2.3 University / Archive / Library District
Purpose:
- research
- original incident root
- language, history, and occult context

Design notes:
- slower tempo
- strong clue density
- likely early-game narrative importance

### 6.2.4 Commercial Street / Market / Tavern Zone
Purpose:
- public conversation hub
- merchants, informants, rumors, purchases
- high variability in crowds and overheard information

Design notes:
- social puzzle center
- ideal for schedule-based observation and tailing suspects

### 6.2.5 Dock / Transit / Freight Zone
Purpose:
- shipments
- illicit deliveries
- suspicious movement
- outsider access point

Design notes:
- stronger night activity
- weather and visibility can matter here
- ideal for clandestine exchanges

### 6.2.6 Industrial / Warehouse District
Purpose:
- hidden gatherings
- material storage
- ritual sites
- combat arenas

Design notes:
- high physical tension
- lots of line-of-sight gameplay potential
- one of the most likely escalation zones

### 6.2.7 Church / Cathedral / Sacred District
Purpose:
- cleansing
- backup resources
- ideological contrast
- NPC refuge during panic

Design notes:
- can function as a stabilizing force in the city simulation
- later may become overcrowded, politically tense, or spiritually compromised

### 6.2.8 Poorer Outskirts / Narrow Alleys / Abandoned Housing
Purpose:
- missing persons cases
- desperation-driven recruitment
- social fragility
- hidden dens and occult fallout

Design notes:
- high vulnerability to rumor, fear, and coercion
- should feel physically constricted and emotionally dangerous

## 6.3 Enterable Building Philosophy

Buildings must matter. Entry should not be decorative. Each interior should support one or more of:

- clue discovery
- NPC behavior observation
- social interaction
- environmental storytelling
- stealth or combat
- ritual evidence
- class contrast or political mood

A building is successful if the player can say why it exists in the simulation.

---

# 7. Narrative Structure

## 7.1 Overall Arc

The game should follow a fixed dramatic spine but allow dynamic details.

### Stage 1: Disturbance
- recent deaths or madness
- first evidence of occult contamination
- strange inconsistencies in witness reports

### Stage 2: Localized Case
- a visible suspect or victim chain emerges
- one district begins showing recurring anomalies
- the player starts linking people, places, and times

### Stage 3: Hidden Network
- the player realizes multiple incidents connect
- deliveries, meetings, or symbols reveal a broader conspiracy
- some allies begin to fear a bigger threat than expected

### Stage 4: Escalation
- panic rises
- multiple incidents occur close together
- city pressure variables begin to compound
- safe routines become less reliable

### Stage 5: Premonition of Catastrophe
- supernatural events become undeniable
- night activity spikes
- key NPCs are threatened or compromised
- the player must prioritize what can still be saved

### Stage 6: Ritual Night / Final Prevention Attempt
- simultaneous crises across the city
- one main confrontation at the true ritual site
- outcomes depend on prior investigation, ally health, city pressure, and resource management

## 7.2 Authored vs Dynamic Content

### Authored
- main dramatic beats
- tone-defining scenes
- major core character arcs
- city escalation thresholds
- final catastrophe framework

### Dynamic
- specific ritual site
- clue order
- who gets corrupted first
- which buildings are used as fronts
- which witness is silenced
- which side incident flares up
- whether an ally survives or becomes unavailable

## 7.3 Why This Hybrid Is Important

Pure scripting reduces replay value and weakens AI testing.
Pure simulation risks incoherence.
This hybrid maintains dramatic quality while still stress-testing Yumina's systemic capabilities.

---

# 8. World Manager Architecture

## 8.1 Role of the World Manager

The World Manager is the hidden director of city-scale progression. It does not micromanage every step; instead, it orchestrates:

- plot stage progression
- global pressure values
- event eligibility
- district state changes
- NPC role reassignment under crisis
- ritual preparation progression
- side-incident spawning

## 8.2 Core Responsibilities

1. Maintain current narrative stage
2. Track citywide pressure metrics
3. Unlock or suppress events based on conditions
4. Assign dynamic slots for key story functions
5. Resolve offscreen progression
6. Signal urgency to AI systems
7. Feed player-visible consequences back into the environment

## 8.3 Global Pressure Variables

Recommended global variables:

### Corruption Level
Represents occult contamination in the city.
Affects:
- anomaly frequency
- dream intensity
- probability of NPC instability
- strength of ritual sites

### Public Panic
Represents how much citizens believe something is wrong.
Affects:
- crowd density
- shop closures
- witness reliability
- rumor spread speed
- civilian movement patterns

### Investigator Fatigue
Represents ally exhaustion, overwork, and morale degradation.
Affects:
- deployment effectiveness
- recovery times
- reaction delays
- likelihood of mistakes in the field

### Cult Readiness
Represents how close the antagonist network is to completing its plan.
Affects:
- ritual timing
- coordination of suspicious actions
- fallback site activation
- enemy preparedness in encounters

### Attention of the Beyond
Represents how strongly the hidden cosmic/supernatural force is focused on the city.
Affects:
- dream invasions
- visual distortions
- boss behavior
- endgame severity

## 8.4 Example Stage Transition Logic

A stage may progress when a combination of conditions is met, such as:

- enough time has passed,
- certain clues were or were not found,
- a district corruption threshold was reached,
- a ritual courier successfully completed delivery,
- a local incident concluded in failure,
- the player openly cracked down and pushed the cult underground.

This allows both authored inevitability and player impact.

## 8.5 Dynamic Slotting System

At the start of each run or chapter, the World Manager assigns dynamic roles to content slots.

Example slots:
- primary ritual site
- secondary fallback site
- first corrupted civilian
- misleading witness
- key courier
- hidden ledger location
- ally who will be most at risk

This creates variety while preserving recognizable structure.

## 8.6 Offscreen Resolution

The World Manager should resolve actions the player does not witness.

Examples:
- if a cult courier is not intercepted, a warehouse gains ritual materials
- if panic rises in a district, civilians stop going out after dark
- if the church becomes overloaded, healing and cleansing services slow down
- if an ally is sent to observe alone too often, fatigue increases faster

This is critical for making the city feel alive.

---

# 9. NPC Intelligence System

## 9.1 Design Goal

NPCs should feel purposeful, interpretable, and responsive without requiring fully expensive continuous cognition.

The recommended model is:

- **high-level strategic refresh every 60 seconds**, plus
- **event-driven interrupts and state changes** in between

## 9.2 Why 60 Seconds Works

Refreshing every second is wasteful and noisy.
Refreshing every 60 seconds allows:

- visible routine chunks
- understandable movement patterns
- enough stability for player observation
- scalable AI processing
- coherent schedule-based behavior

Event interrupts then handle urgency.

## 9.3 NPC Data Model

Each NPC should carry at least:

- identity
- district/home/work locations
- social relationships
- role/archetype
- daily schedule template
- current task
- goal stack
- knowledge state
- suspicion map
- stress level
- corruption level
- fear/faith profile
- combat readiness
- faction alignment
- secrets
- memory of recent events

## 9.4 Suggested NPC Archetypes

### Ordinary Civilian
- follows work/home/social loop
- spreads rumors
- can witness events
- reacts to danger and district conditions

### Merchant / Service Provider
- more static location
- high gossip utility
- can hide transactional clues
- schedule changes when panic rises

### Investigator Ally
- patrols, rests, reports, follows orders
- can tail, guard, raid, escort, study evidence
- performance affected by fatigue and morale

### Corrupted Victim
- outwardly normal at first
- increasing irregularity over time
- strange route deviations, compulsions, isolation, sleep loss
- may become encounter trigger or tragic witness

### Cult Affiliate
- manages covert schedules
- avoids high-risk routes when pressure rises
- performs deliveries, meetings, or recruitment
- can lie, flee, hide evidence, or redirect suspicion

### Core Named Character
- more authored personality and scenes
- stronger memory and response complexity
- may anchor key emotional beats

## 9.5 60-Second Decision Refresh

At each high-level refresh, an NPC should evaluate:

1. Current world stage
2. Personal role
3. Needs and schedule
4. Threat level in nearby districts
5. Known information
6. Social obligations
7. Panic/corruption context
8. Current interrupts

And produce a chosen next objective such as:

- go to work
- visit market
- meet contact
- buy materials
- hide item
- return home early
- patrol sector
- deliver report
- avoid district
- seek help at church
- perform ritual preparation
- stalk target
- flee from suspicion

## 9.6 Event-Driven Interrupts

Interrupts should immediately override ordinary schedules when necessary.

Examples:
- gunshot heard
- body discovered nearby
- direct questioning by player
- observed by investigators too long
- district curfew begins
- occult signal detected
- ally requests backup
- ritual timer crosses threshold
- family member goes missing
- public rumor reaches dangerous intensity

## 9.7 Memory Model

NPCs should not only react to the present. They should store recent salient events.

Useful short-term memory entries:
- was questioned by player
- saw someone run into warehouse
- heard church bell emergency signal
- witnessed violence in district
- noticed patrol density increase
- saw cult symbol
- was turned away from a building

These memories can influence future dialogue, movement, and suspicion.

## 9.8 Visibility and Legibility

NPC simulation must be readable enough for the player to form theories.

This means:
- suspicious behavior should be noticeable in hindsight
- movement changes should correlate with known world events
- anomalies should create patterns, not total chaos
- the player should be able to learn how the city behaves

---

# 10. Major Characters and Role Design

## 10.1 Core Cast Structure

The vertical slice should include a small named cast with strong contrast in worldview, utility, and risk.

Recommended role categories:

- Player character / junior investigator
- Veteran leader / strategist
- composed occult expert
- physically capable field ally
- anxious but smart archivist or assistant
- civilian witness with personal stakes
- primary suspect / corrupted intermediary
- hidden cult organizer

## 10.2 Major Character Functions

Each named character should serve multiple functions:

- gameplay utility
- emotional tone
- information source
- moral framing
- failure consequence

## 10.3 Example Character Function Matrix

### Player Character
Function:
- exploration
- evidence gathering
- field decisions
- tactical combat
- occult perception tools

### Veteran Team Lead
Function:
- mission authority
- risk framing
- deployment decisions
- emotional anchor of responsibility

### Research-Oriented Ally
Function:
- interprets clues
- unlocks occult understanding
- helps reconcile contradictions in evidence

### Combat Ally
Function:
- strong in raids
- weaker in abstract reasoning
- useful but can become overextended

### Civilian Anchor Character
Function:
- gives the city emotional reality
- demonstrates consequences of panic or corruption
- may become endangered or manipulated

### Main Corrupted Intermediary
Function:
- bridges early mystery to the wider plot
- visibly deteriorates across the game
- can be confronted, watched, or tragically lost

### Hidden Cult Organizer
Function:
- orchestrates deliveries and rituals
- rarely seen directly early on
- revealed through network evidence

## 10.4 Character-Driven Replay Variation

Named characters should remain themselves, but their trajectories can vary:

- who is injured first
- who mistrusts the player after a poor decision
- who becomes isolated
- who becomes available for endgame help
- who can still testify or interpret a clue

---

# 11. Investigation System

## 11.1 Design Goal

Investigation should feel like assembling truth from partial, messy, and layered evidence.

The player should not merely exhaust dialogue trees. They should:

- compare testimonies
- observe routines
- inspect environments
- use occult methods
- form and revise hypotheses

## 11.2 Three Evidence Layers

### Physical Evidence
Examples:
- blood traces
- unusual books or symbols
- letters
- receipts
- ledger pages
- ritual residue
- missing-person items
- altered door locks
- drug vials or powders

### Behavioral Evidence
Examples:
- someone leaves home at unusual hours
- two NPCs meet in a location with no public reason
- a merchant lies about having never seen a suspect
- a witness remembers the wrong weather or wrong day
- a suspect changes districts after patrol pressure rises

### Occult Evidence
Examples:
- dream fragments
- divination outcomes
- psychic residue
- ritual echoes
- symbolic pattern recognition
- gray-fog reconstruction or strategic inference mechanic

## 11.3 Investigation Board

The player should maintain a visible case board or notebook.

Features:
- collected clue cards
- suspect profiles
- location nodes
- time-of-day associations
- player-created links
- hypothesis slots
- flagged uncertainties

### Why It Matters
This makes the player actively reason rather than passively consume exposition.

## 11.4 Hypothesis Mechanics

The player should be able to propose actionable hypotheses such as:

- "the next meeting will happen at warehouse B"
- "merchant X is acting as courier"
- "the church district is a decoy target"
- "victim Y was selected through the boarding-house network"

These should not require perfect certainty. Instead, each hypothesis can have a confidence value based on clue support.

## 11.5 Consequences of Wrong Inference

Wrong conclusions should create setbacks, not always immediate failure.

Examples:
- wasted patrol deployment
- suspect slips away
- ally injured in wrong raid
- panic rises due to public disruption
- time lost, letting cult readiness increase

This keeps mystery tense and forgiving enough to experiment.

## 11.6 Interview System

Conversations should support:

- direct questions
- soft probing
- contradiction confrontation
- intimidation or pressure options
- occult-assisted insight if available

Witnesses should differ in:
- honesty
- memory quality
- fear level
- susceptibility to rumor
- relationship to the person being discussed

## 11.7 Observation Gameplay

Players should be rewarded for simply watching.

Observation mechanics may include:
- tailing suspects
- note-taking on routes
- stakeouts
- comparing district population at different times
- detecting repeated symbols or visitors

This is especially important because NPC scheduling is one of the concept's central features.

---

# 12. Occult Systems and Supernatural Investigation

## 12.1 Design Goal

The supernatural layer should deepen mystery and risk rather than trivialize investigation.

Occult tools should reveal patterns, hints, and dangerous truths, but not provide effortless answers.

## 12.2 Suggested Supernatural Tools

### Divination
Use cases:
- determine whether a lead is promising
- gain symbolic hints about a suspect or location
- estimate danger level

Tradeoff:
- ambiguous results
- mental strain
- possible contamination if overused

### Residue Sight / Spirit Vision
Use cases:
- inspect scenes for unnatural traces
- identify prior ritual use
- detect violent emotional imprints

Tradeoff:
- temporary sensory distortion
- may increase fear or corruption

### Dream Fragments
Use cases:
- symbolic foreshadowing
- hidden connections between seemingly unrelated clues
- soft direction toward important districts or objects

Tradeoff:
- interpretation challenge
- misleading imagery possible under high corruption

### Gray-Fog Reconstruction / Abstract Inference Space
Use cases:
- review clue structures
- project likely ritual patterns
- reconstruct a missing link from partial evidence

Tradeoff:
- limited uses
- depends on how much raw evidence the player found

## 12.3 Supernatural Clarity Rules

Important principle: occult systems should make players ask better questions, not skip the game.

Good:
- "something happened here at midnight"
- "this ledger page matters"
- "the witness is hiding fear, not necessarily lying"

Too strong too early:
- "the ritual is in warehouse 4 at 11:20 PM and merchant Allen is the courier"

---

# 13. Rumor System

## 13.1 Why Rumors Matter

Rumor is one of the most important bridges between social simulation and mystery.

Rumors help make the city feel alive and give NPC intelligence something to react to besides direct scripting.

## 13.2 Rumor Attributes

Each rumor can have:
- topic
- district of origin
- truthfulness level
- spread strength
- emotional valence (fear, anger, fascination, distrust)
- attached entities (person, district, event)

## 13.3 Example Rumors

- strange lights near the warehouses
- someone from the boarding house disappeared
- investigators are arresting innocent people
- the church bells rang without cause
- a certain merchant is cursed
- there are monsters by the docks
- don't go out after dusk in the east district

## 13.4 Effects of Rumor

Rumors can alter:
- civilian movement
- willingness to talk
- false leads
- crowd concentration
- market closures
- cult route adaptation
- witness emotional states

## 13.5 Gameplay Value

Rumors serve both as:
- partial clues
- noise that the player must filter

This is excellent for a mystery game because truth is social, distorted, and distributed.

---

# 14. Time Structure and Daily Loop

## 14.1 Recommended Time Model

Divide the day into major segments:

- Morning
- Afternoon
- Dusk
- Night
- Late Night

This can coexist with real-time minutes for local simulation, but major event scheduling should respect broad phases.

## 14.2 Daily Rhythm

### Morning
- reporting
- reviewing clues
- questioning witnesses in routine settings
- planning deployments

### Afternoon
- active investigation
- research
- suspect observation
- district traversal

### Dusk
- transition period
- tension rises
- suspicious actors begin repositioning
- player must choose where to be

### Night
- most anomalies, clandestine meetings, and ritual preparation occur
- combat incidents more likely
- supernatural pressure increases

### Late Night
- peak danger and highest chance of irreversible developments
- best time for raids, but worst time for unpreparedness

## 14.3 Why This Structure Works

It gives the city rhythm, makes schedules legible, and lets tension crescendo naturally every cycle.

---

# 15. Missions, Side Incidents, and Dynamic Content

## 15.1 Main Missions

Main missions should drive the occult plot and advance the narrative spine.

Examples:
- investigate the first contaminated residence
- identify the source of a ritual component supply chain
- tail a suspected courier at dusk
- search a warehouse after contradictory testimony
- defend or evacuate a witness
- disrupt the final ritual

## 15.2 Side Incidents

Side incidents create texture and pressure.

Examples:
- panic in a boarding house
- missing child report
- merchant claims harassment by investigators
- strange sounds at chapel annex
- body found near alley but unrelated to main plot
- false monster sighting caused by rumor

## 15.3 Why Side Incidents Matter

Without them, the city feels obviously gamey and plot-centered.
With them, the player must prioritize and live with incomplete coverage.

## 15.4 Dynamic Incident Rules

Incidents should consider:
- current world stage
- district conditions
- corruption level
- rumor density
- which actors are currently free
- recent player behavior

This keeps the world reactive and context-sensitive.

---

# 16. Combat Design

## 16.1 Combat Philosophy

Combat should be:

- short
- lethal or threatening
- tactical
- information-sensitive
- atmosphere-preserving
- not the dominant mode of play

This is not a pure hack-and-slash game.

## 16.2 Recommended Combat Format

Best fit options:

### Option A: Real-Time with Pause
Pros:
- supports tension and tactical control
- works well with small squads or ally coordination
- allows readable occult interactions

### Option B: Tight Tactical Real-Time
Pros:
- more immediate
- easier to blend with exploration
- strong for short encounters

For the first slice, a **tight tactical real-time system with optional pause** is likely ideal.

## 16.3 Player Combat Tools

The player's toolkit should reflect investigation-first, occult-lite style play.

Possible tools:
- revolver or firearm with limited ammo
- short-range occult barrier
- paper charm / sigil trap
- decoy or lure tool
- predictive dodge cue from divination
- temporary spirit sight to reveal hidden anchors
- emergency retreat ability

## 16.4 Ally Roles in Combat

Allies should have tactical specialties:
- frontliner / suppressor
- support / cleansing
- investigator who exposes weak points
- lock or door control specialist

## 16.5 Enemy Categories

### Corrupted Human
- unstable movement
- sudden bursts
- tragic visual language

### Cult Operative
- tactical, cowardly, coordinated
- may flee or stall rather than fight fairly

### Ritual Spawn / Distorted Entity
- unnatural attacks
- zone control
- strong atmosphere function

### Partial Descent / Endgame Horror
- not fully a boss in a conventional sense
- may require multiple objectives rather than simple DPS race

## 16.6 Combat Objectives Beyond Killing

Many combat encounters should prioritize:
- interrupting a ritual
- rescuing a hostage
- surviving long enough for backup
- cleansing anchors
- preventing escape
- holding a chokepoint
- destroying evidence before enemies do

This preserves narrative flavor and differentiates the game.

## 16.7 How Investigation Should Affect Combat

Investigation can improve combat by:
- revealing enemy positions
- identifying weak ritual nodes
- reducing enemy numbers
- allowing ambush setup
- predicting when the site is least defended
- warning which enemy type will appear

This interlock is one of the most important design goals.

---

# 17. Failure, Injury, and Consequence Design

## 17.1 Design Philosophy

Failure should not usually be binary. It should reshape the city and the ending trajectory.

## 17.2 Types of Consequences

- witness death or disappearance
- district panic spike
- ally injury or fatigue
- suspect relocation
- fallback ritual activation
- public distrust of investigators
- stronger final descent event

## 17.3 Why Partial Failure Is Valuable

Partial failure creates stories and makes dynamic systems meaningful.
If every mistake leads only to immediate game over, the mystery becomes brittle and less interesting.

## 17.4 End Conditions

Possible endings include:
- strong prevention with manageable losses
- success at great personal cost
- catastrophic success with massive city damage
- failed prevention / partial descent
- pyrrhic containment with political fallout

---

# 18. Progression and Replayability

## 18.1 In-Run Progression

During a single run, progression can include:
- broader access to districts or rooms
- improved occult interpretation
- stronger alliance trust
- more deployment options
- expanded case-board tools

## 18.2 Meta Replayability

Replays should differ through:
- variable clue order
- different ritual site assignment
- different corrupted intermediaries
- altered rumor chains
- shifting side incidents
- ally survival variation
- different district pressure patterns

## 18.3 Replay Philosophy

The goal is not infinite randomness. It is **structured variability**. Players should learn the logic of the city while still encountering meaningful differences.

---

# 19. UX and UI Design

## 19.1 General UI Philosophy

The UI should be readable, atmospheric, and restrained.

Avoid overloading the player with screens. Key information should be legible but not clinical.

## 19.2 Core UI Surfaces

### Main Exploration HUD
Should include:
- health/stability/resource indicators
- current time phase
- current objective or active lead
- quick-access tools
- district status icons when relevant

### Dialogue Interface
Should support:
- layered questioning
- topic references from known clues
- contradiction call-outs
- emotional tone cues when appropriate

### Investigation Board
Should allow:
- dragging connections
- reviewing evidence
- pinning likely conclusions
- marking uncertainty
- seeing timeline associations

### Map Interface
Should show:
- district names
- known points of interest
- ally deployment locations
- recent incident markers
- risk overlays once unlocked

### Team Management / Deployment Screen
Should support:
- assigning allies to districts or tasks
- seeing fatigue and readiness
- planning night coverage

## 19.3 Suggested Player-Facing Presentation Style

The UI should feel like a blend of:
- detective notebook
- occult field kit
- minimally intrusive retro adventure HUD

## 19.4 Event Pop-Ups

When urgent events occur, use strong but simple notifications, such as:
- bell sound + short panel
- map highlight
- named district alert

This is essential for coordinating a living city.

---

# 20. Art Direction

## 20.1 Visual Goal

A moody, readable, top-down or slightly angled 2D pixel-art world with Victorian/industrial urban atmosphere.

## 20.2 Style Characteristics

- restrained color palette with district-specific tone shifts
- warm interior lighting vs cold exterior nights
- readable silhouettes for NPC types
- strong use of fog, lamp glow, and window light
- subtle supernatural distortion effects

## 20.3 District Visual Differentiation

Each district should be identifiable by:
- paving style
- architecture density
- signage language
- lighting color temperature
- crowd behavior
- ambient sound profile

## 20.4 Supernatural Visual Language

Occult phenomena should use a distinct but consistent visual grammar:
- fine distortions
- unusual shadow behavior
- symbolic flashes
- unstable environmental tiles
- sound or sprite desynchronization

Important: the world should not look overtly magical all the time. Supernatural elements should feel invasive.

---

# 21. Audio Direction

## 21.1 Music Strategy

Music should support:
- quiet routine
- creeping unease
- escalating dread
- tactical focus during combat
- sorrowful aftermath

## 21.2 Ambient Sound

Critical for city life and horror:
- footsteps by district material
- church bells
- market chatter
- dock chains and water
- distant carriage sounds
- whisper-like supernatural tails
- muffled indoor voices from buildings

## 21.3 Audio as Gameplay Signal

Sound can support investigation by indicating:
- unusual gathering in a building
- someone running nearby
- occult resonance
- panic crowd movement
- ritual buildup intensity

---

# 22. Technical Architecture Suggestions

## 22.1 Core Systems Needed

1. City navigation and enterable interiors
2. Time-of-day simulation
3. NPC schedule and goal system
4. Event bus / event interrupt architecture
5. World manager and pressure model
6. dialogue and knowledge system
7. evidence/investigation board system
8. combat encounter layer
9. save/load state for dynamic world

## 22.2 Event Bus Importance

A robust event system is central.
Examples of events:
- body_found
- witness_questioned
- district_panic_rise
- rumor_spawned
- patrol_assigned
- suspect_observed
- ritual_material_delivered
- ally_injured
- occult_trace_detected
- stage_advanced

NPCs, the world manager, UI, audio, and mission systems should all be able to subscribe to relevant events.

## 22.3 Suggested AI Layering

### Layer 1: Schedule Base
Default routine by day phase

### Layer 2: Goal Selector
Every 60 seconds, choose next main action

### Layer 3: Event Interrupts
Override schedule based on urgent stimuli

### Layer 4: Immediate Path/Animation Controller
Handle local navigation and execution

This layered model is more manageable than trying to make every NPC fully deliberative all the time.

## 22.4 Save State Requirements

The save system must preserve:
- stage and time phase
- district variables
- rumor states
- NPC locations and key memories
- clue inventory
- board links / hypotheses
- ally injuries and fatigue
- event completion flags
- dynamic slot assignments

This is necessary for a world that changes persistently.

---

# 23. Data Structure Suggestions

## 23.1 NPC Schema Example

Suggested fields:

- id
- name
- archetype
- faction
- home_location
- work_location
- schedule_template
- relationship_ids
- secrets
- stress
- corruption
- fear
- faith
- suspicion_map
- known_facts
- current_goal
- active_interrupts
- recent_memories
- combat_profile

## 23.2 Building Schema Example

- id
- district
- type
- public_or_private
- occupants
- open_hours
- clue_slots
- occult_affinity
- line_of_sight_tags
- entry_conditions

## 23.3 World State Schema Example

- current_stage
- time_phase
- corruption_level
- public_panic
- investigator_fatigue
- cult_readiness
- beyond_attention
- ritual_site_primary
- ritual_site_secondary
- active_rumors
- active_incidents
- district_states

---

# 24. Content Pipeline Suggestions

## 24.1 Build Order

Recommended order:

1. one district with two buildings and a few NPC routines
2. event system + 60-second refresh
3. one investigation chain with clue collection
4. one suspicion/tailing interaction
5. one small combat encounter
6. world manager stage transitions
7. rumor propagation
8. ally deployment
9. final ritual sequence

## 24.2 Why This Order

It validates the hardest systemic interactions first instead of sinking time into content before the foundation is proven.

## 24.3 Authoring Tools Needed

Internal authoring tools would ideally support:
- NPC schedule editing
- incident creation
- clue linking
- district variable tuning
- stage transition conditions
- encounter placement
- dialogue condition testing

These tools will drastically reduce iteration pain.

---

# 25. Vertical Slice Plan

## 25.1 Slice Objective

Demonstrate that a small city can support:
- mystery-solving via behavior and clues
- dynamic plot escalation
- investigation-combat interplay
- living NPC routines with strategic refresh

## 25.2 Slice Content Proposal

### Playtime Target
45 to 90 minutes

### Included Features
- 3 districts
- 8 enterable buildings
- 15 to 20 NPCs
- 1 major suspect chain
- 1 rumor system implementation
- 1 small deployment choice
- 1 warehouse combat mission
- 1 limited end-night escalation sequence

## 25.3 Success Criteria

The slice succeeds if playtesters say things like:
- "I could tell people were acting differently because of what happened."
- "I had to think, not just click through dialogue."
- "I felt pressure deciding where to go at night."
- "The fight felt better because I had figured out the location first."
- "I want to replay to see how it changes."

---

# 26. Testing Questions for Yumina

This project should answer the following product questions.

## 26.1 AI and Simulation Questions

- Does 60-second strategic refresh feel alive enough?
- How many NPCs can meaningfully run in parallel?
- Do event-driven interrupts create believable reactivity?
- Can players actually notice and use schedule-based anomalies?

## 26.2 Narrative Questions

- Can a world-managed plot feel coherent while varying details?
- Do dynamic slots create replayability without confusion?
- Can authored scenes coexist with simulation cleanly?

## 26.3 Gameplay Questions

- Is investigation engaging when built from clues and behavior?
- Does combat feel justified and consequential?
- Can players hold the needed mental model of the city?

## 26.4 UX Questions

- Is the investigation board understandable?
- Can players read urgency from the UI without clutter?
- Are district changes and rumor effects perceptible?

---

# 27. Risks and Mitigations

## 27.1 Risk: Simulation Feels Random
Mitigation:
- strengthen schedule logic
- keep strong authored spine
- improve clue legibility
- tune event thresholds to preserve causality

## 27.2 Risk: Mystery Becomes Opaque
Mitigation:
- ensure multiple clue paths to the same conclusion
- let occult tools give directional hints
- improve investigation board support
- use strong environmental storytelling

## 27.3 Risk: Combat Feels Detached
Mitigation:
- tie enemy setups to prior evidence
- vary combat objectives beyond killing
- ensure pre-combat investigation materially changes outcomes

## 27.4 Risk: Scope Explosion
Mitigation:
- start with one plotline
- keep districts compact
- prioritize systemic depth over sheer content count
- build vertical slice first

## 27.5 Risk: NPC Intelligence Is Expensive but Invisible
Mitigation:
- make schedule shifts visible
- support stakeout gameplay
- let rumors and witness reports reference actual NPC movement
- ensure AI creates player-noticeable patterns

---

# 28. Recommended Next Steps

## 28.1 Immediate Design Next Step

Write a more granular **system specification package** for:

1. World Manager state machine
2. NPC intelligence schema and refresh logic
3. investigation board interactions
4. rumor propagation rules
5. combat encounter rules

## 28.2 Immediate Prototype Next Step

Prototype one tiny scenario:

- one suspect
- one rumor chain
- one warehouse
- one clue trail
- one late-night confrontation
- 8 to 10 NPCs

If that is fun, expand outward.

## 28.3 Strategic Recommendation

Treat this concept as a **platform proof-of-capability**, not only a content experiment. If it works, Yumina will have demonstrated a reusable architecture for:

- social sim RPGs
- detective games
- narrative town simulators
- living companion-based worlds
- story-rich combat adventures

---

# 29. Final Product Framing

The strongest framing for this concept is:

> A 2D pixel-art occult mystery simulation in which a living city hides a growing conspiracy, a world manager pushes a catastrophe toward reality, and every character acts on schedules, pressure, memory, and fear.

This is promising because it makes Yumina's intelligence systems visible, playable, and emotionally meaningful.

Its best version is not simply a lore adaptation. It is a **systemic mystery game** where story emerges from the interaction of authored structure, dynamic AI, social rumor, occult pressure, and player inference.

That combination is unusual, testable, and potentially very strong.

---

# 30. Optional Follow-On Documents

Natural follow-up documents that would be valuable:

1. Full Game Design Document v2 with concrete mechanics and numbers
2. World Manager technical spec
3. NPC AI decision architecture spec
4. UI wireframe document
5. vertical slice milestone plan
6. event taxonomy and data schema
7. sample chapter script and example runthrough

If expanded, this document can serve as the foundation for all of them.


---

# 31. Engine-First Requirement (Critical)

This project is **not just a game prototype**. It is a **Yumina engine capability showcase and developer platform test**.

The core requirement:

> A developer should be able to use Yumina to build a polished, content-rich 2D pixel game (like this one) **without fighting the engine**.

This implies two simultaneous goals:

1. The vertical slice is fun and coherent
2. The **tooling and pipeline are smooth, powerful, and expressive**

Everything below should be evaluated through this lens.

---

# 32. Developer Experience (DX) Goals

## 32.1 Core DX Principles

- **Low friction**: common tasks (add NPC, add building, add event) should take minutes
- **High ceiling**: complex behaviors (multi-step events, AI reactions, UI logic) must be supported
- **Live iteration**: designers should tweak and immediately see results
- **Data-driven**: minimal hardcoding
- **Composable systems**: behaviors should stack cleanly

## 32.2 Developer Persona

The target developer is:

- indie dev / student / prototyper
- familiar with basic scripting or config
- not necessarily building an engine from scratch

They should be able to:

- import sprites
- define NPC behavior
- create missions
- design UI
- configure audio
- iterate quickly

---

# 33. Asset Pipeline Requirements

## 33.1 Sprite System

Must support:

- sprite sheets
- directional animations (up/down/left/right)
- idle, walk, run, interact, combat states
- layering (body, clothing, accessories)
- palette swaps (for variation)

## 33.2 Animation System

Must support:

- frame-based animation
- state machines (idle → walk → interact → combat)
- animation blending (optional but ideal)
- event hooks (on animation frame X → trigger event)

Example use:
- trigger gunshot sound on frame 6
- trigger door open on animation complete

## 33.3 Opening / Cutscene System

Must support:

- scripted sequences (camera pans, fades, dialogue)
- timeline-based animation
- event triggers inside cutscenes
- skipping and replay

## 33.4 Audio System

Must support:

- background music by district and time
- dynamic transitions (day → night → combat)
- layered ambient sound
- positional audio (important for investigation)
- sound event triggers

Example:
- faint chanting increases near ritual site

## 33.5 UI Asset System

Must support:

- custom UI skins/themes
- pixel-perfect scaling
- font customization
- icon atlases

---

# 34. UI/UX Creation System (Engine Feature)

## 34.1 UI Builder Requirements

Developers must be able to visually or declaratively create:

- HUD
- dialogue panels
- investigation board
- map overlay
- inventory/tool UI
- notifications

## 34.2 UI Behavior Layer

UI should support:

- binding to game state
- conditional rendering
- event-driven updates
- drag-and-drop (for investigation board)

## 34.3 Example UI Components

- Node-link board (drag lines between clues)
- Dialogue choice tree
- Map with overlays
- Status bars (panic, corruption)

---

# 35. World Manager Technical Spec (Expanded)

## 35.1 State Machine

World Manager operates as:

- finite state machine (stages)
- plus continuous variables (pressure)

## 35.2 Update Loop

Every tick (or interval):

1. update global variables
2. evaluate triggers
3. spawn or resolve events
4. notify systems via event bus

## 35.3 Event Generation

Event =
- trigger condition
- affected entities
- resolution logic

Example:

trigger: corruption > threshold in district
→ event: "strange sightings"
→ effect: rumor spawn + NPC fear increase

## 35.4 Developer Control

Devs must be able to:

- define stages
- define triggers declaratively
- inject custom logic
- simulate stage progression manually

---

# 36. NPC AI System Spec (Expanded)

## 36.1 Decision Model

Each NPC runs:

- 60s strategic planner
- event interrupt handler
- action executor

## 36.2 Goal Stack

Goals are prioritized list:

- survive
- complete role tasks
- respond to events
- pursue hidden agenda

## 36.3 Behavior Authoring

Developers define:

- schedule templates
- goal weights
- reaction rules

Example:

IF panic high → reduce travel radius
IF followed → change route
IF corrupted → seek ritual site

## 36.4 Debug Tools (Critical)

Engine MUST include:

- NPC state inspector
- current goal display
- path visualization
- memory log viewer

Without this, AI is unusable for devs.

---

# 37. UI Wireframe Spec (High-Level)

## 37.1 Exploration Screen

- center: player + world
- bottom: quick tools
- top: time + objective

## 37.2 Investigation Board

- canvas with draggable nodes
- left panel: clues
- right panel: suspects

## 37.3 Map Screen

- district overlay
- event markers
- deployment controls

## 37.4 Dialogue Screen

- text box
- selectable topics
- clue references

---

# 38. Milestone Plan

## Milestone 1: Core Engine Loop

- movement + map
- sprite + animation
- basic NPC schedules

## Milestone 2: Event + AI

- event bus
- 60s decision system
- simple reactions

## Milestone 3: Investigation

- clue system
- board UI
- dialogue

## Milestone 4: World Manager

- stage progression
- pressure variables

## Milestone 5: Combat

- encounter system
- basic tools

## Milestone 6: Polish + Assets

- UI skin
- music
- lighting
- effects

## Milestone 7: Vertical Slice Complete

- full loop playable

---

# 39. Engine Validation Checklist

The engine succeeds if developers can:

- import sprites and animate in minutes
- create a new NPC with behavior easily
- define an event without code complexity
- build UI without hacks
- debug AI clearly
- iterate quickly

And the resulting experience feels:

- alive
- coherent
- reactive

---

# 40. Final Positioning

This is not just a game concept.

It is a **reference implementation for a narrative simulation engine**.

If successful, Yumina enables:

- mystery games
- social sims
- narrative RPGs
- agent-driven worlds

This Tingen project is simply the most demanding and revealing test case.

---

