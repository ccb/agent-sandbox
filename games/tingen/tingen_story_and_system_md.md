# Tingen Arc Story + System-Driven Game Design (Detailed)

---

# Part 1: Original Story (Detailed)

## Core Premise
A cursed artifact (Antigonus Notebook) spreads mental corruption, triggering deaths, failed rituals, and eventually a large-scale attempt to summon a higher entity.

---

## Full Story Breakdown

### 1. Inciting Incident – Suicide
- Protagonist awakens in a body that has just shot itself
- Scene includes:
  - revolver
  - blood
  - strange notebook
- Root cause: exposure to Antigonus Notebook
- Early themes:
  - identity confusion
  - memory fragmentation
  - immediate mystery

---

### 2. Initial Contamination Chain
- Welch and companions studied the notebook
- Results:
  - mental instability
  - suicide or death
- Notebook moves between individuals
- Pattern emerges:
  - knowledge → corruption → collapse

---

### 3. Entry into Official Investigation
- Protagonist joins Nighthawks
- Learns:
  - supernatural system (sequence pathway)
  - investigation protocols
- Begins structured case work

---

### 4. Bieber Incident (Localized Ritual Failure)
- Ray Bieber obtains notebook
- Attempts ritual / power digestion
- Outcome:
  - loses control
  - becomes monster
  - partial ritual success

Meaning:
- first proof of ritual mechanics
- escalation beyond simple madness

---

### 5. Discovery of Hidden Network
- Investigation reveals:
  - multiple connected incidents
  - organized cult structure
  - use of intermediaries
- Clues begin forming a network:
  - logistics
  - meetings
  - ritual preparation

---

### 6. City-Wide Escalation
- Multiple anomalies occur simultaneously
- Increased:
  - disappearances
  - abnormal behavior
  - ritual signs
- Indicates:
  - coordinated large-scale operation

---

### 7. Final Crisis – Descent Attempt
- Cult prepares large ritual
- Objective:
  - summon higher entity (offspring of True Creator)
- Organization intervenes

Outcome:
- heavy casualties
- leader death
- partial success (ritual prevented, cost high)

---

## Key Narrative Patterns

- Corruption spreads through contact and knowledge
- Small events escalate into systemic crisis
- Truth is incomplete and delayed
- Time pressure is implicit (world progresses)
- Combat is secondary to prevention

---

# Part 2: Opening Gameplay Flow (Engine-Friendly)

## Goal
Fast, low-cost, high-impact intro using:
- video generation
- 2D pixel scene
- minimal scripting

---

## Opening Sequence

### Step 1: Video Animation (15–25s)
- pixel-style or generated video
- desk + revolver + notebook
- subtle motion (hand tremble, flicker)
- audio: heartbeat + whisper

→ gun fires → cut to black

---

### Step 2: Black Screen Transition
- audio: ringing + faint voices
- text:
  “我是谁？”

---

### Step 3: Wake Up (2D Scene)
- top-down pixel room
- player on ground
- blood visible
- interactable objects:
  - notebook
  - gun
  - mirror

player gains control immediately

---

### Step 4: Minimal Interaction

Notebook:
→ “这东西不对劲”

Gun:
→ “是我开的枪？”

Mirror:
→ “这不是我”

---

### Step 5: Soft Guidance (No Popup)

Internal thoughts appear:

- “需要搞清楚发生了什么……”
- “也许应该找官方的人……”

---

### Step 6: Door Event
- knock sound or visual cue
- player interacts with door

---

### Step 7: Transition to City
- immediate scene change
- world simulation begins

---

### Step 8: First Lead

UI text:

“线索：寻找值夜者”

---

## Opening Flow Summary

```text
Animation → Black screen → Wake up → Inspect → Thought hints → Door → City → Lead
```

---

# Part 3: System-Driven Game Logic

## Core Principle

The game does NOT contain a fixed story.
It contains systems that generate outcomes.

---

## 1. World State Variables

- corruption
- panic
- cult_progress
- player_trust
- cult_affinity
- stability

These define all progression.

---

## 2. Rules (Behavior Logic)

Examples:

- IF corruption high → anomalies increase
- IF cult_affinity high → cult contact possible
- IF trust low → allies withdraw
- IF stability low → perception unreliable

---

## 3. Event Resolution

Events triggered by conditions:

Example:

- high cult_progress
- correct location
- player present

→ ritual event occurs

---

## 4. Core Gameplay Loop

```text
Investigate → Hypothesis → Decide → Night Events → World Changes → Repeat
```

---

## 5. World Progression Model

Not chapters, but pressure levels:

- low: isolated anomalies
- medium: connected events
- high: multiple incidents
- critical: descent window

---

## 6. NPC System

NPCs:
- follow schedules
- have goals
- react to events

Player:

```text
observe → detect anomaly → infer
```

---

## 7. Player Agency

Player does not choose story.
Player changes state.
System produces outcome.

---

## 8. Corruption / Alignment System

No explicit “join cult” option.

Instead:

```text
actions → state changes → new interactions → role shift
```

Possible outcome:
- player becomes part of cult system

---

## 9. Event Selection Model

```text
for each event:
    score = weight × state_match

select highest scoring
execute
```

---

## 10. Combat Role

```text
Investigation → Locate → Intervene → Result
```

Combat validates decisions.

---

# Final Summary

This design combines:

1. Original narrative structure (corruption → escalation → ritual)
2. Engine-first gameplay flow (fast, minimal intro → simulation)
3. System-based progression (state + rules → emergent events)

Result:

A simulation where the player interacts with a living system, and the story emerges dynamically rather than being pre-written.

