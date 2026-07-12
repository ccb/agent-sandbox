# LLM Dialogue, Perception-Event Triggers & Persona Enrichment — Design

**Status:** Phases 0–5 implemented and verified (unit-green at 702 tests; each phase reviewed +
playtested by independent subagents; Phase 5's flagship — walking in on the rite — playtested against the
live LLM). Phase 6 (immediate reactive re-decide) remains optional. Three coupled features that move the
player↔NPC and
world↔NPC interfaces off scripted reactions and onto the same LLM cognition path the autonomous beat
loop already uses (`agent-sidecar/cognition/brain.py`, `governance.py`, `goals.py`). Feature 1 replaces
the hand-authored dialogue trees with a real `/converse` round-trip; Feature 2 fires objective world
events into the affected agents' perception and lets the LLM choose the reaction (including hostility and
full combat against the player); Feature 3 gives every NPC persona prose + wires in existing-but-unused
lore so 1 and 2 read in-character. Companion to [`tingen_scene_graph_design.md`](tingen_scene_graph_design.md)
(rooms, `RoomGraph`, `RoomView`, the per-(session,agent) memory stream) and the cognition `SPEC.md`
(§3 tiered goals, §5 hard veto, §6 stateful brain). The design is decided; this is the build spec.

---

## 1. Overview & goals

Three things are wrong today, and they share one root cause — the player- and world-facing surfaces are
**scripted**, while the autonomous NPC loop is **LLM-driven**:

1. **Dialogue is a hand-authored tree.** `DialogueManager` (autoload) walks `data/dialogue.json`,
   emitting `node_changed(speaker, text, options)` which `DialoguePanel` renders as buttons
   (`src/DialogueManager.gd:42-77`, `src/DialoguePanel.gd:19-35`). No LLM is in the dialogue path at all;
   the only place the brain runs is the per-beat `/decide` action loop. Persuasion is a hardcoded
   `social_influence` effect (`DialogueManager.gd:115-118` → `PlayerActions.social_influence`,
   `src/PlayerActions.gd:31-39`) that flips a `role == "scout_waverer"` agent's faction. The NPC cannot
   say anything not pre-written, cannot refuse, and "persuasion" is a menu button, not a choice the NPC
   makes.
2. **The world cannot signal the cult.** There is no way for "the player walked onto the crypt mid-rite"
   to reach an NPC's brain and let *it* decide to turn hostile. The only edge hook on player movement is
   `WorldState.transition_requested` (`src/WorldState.gd:15,51-57`), and the player is not even a
   perceivable entity — `attack target="player"` cannot resolve, because there is no `player` agent in
   the registry.
3. **NPCs have no persona.** A definition in `data/npcs.json` carries only `name`, `faction`, `role`, a
   one-sentence `intent`, and a `tint` (`data/npcs.json:2-9`). The prompt has nothing to voice. Rich lore
   exists (`data/gods.json` — the Descending One + three opposing churches; `data/districts.json`) but
   none of it reaches the prompt. (Clues/leads are deliberately out of scope this pass — see the note in §4.3.)

**Design principles (decided):**

> **A. Speech is free; only actions are governed.** An NPC's spoken line is never vetoed — the NPC speaks
> freely, in character. Only the optional structured `action` it chooses passes `governance.py`.

> **B. The world states FACTS; the LLM decides reactions.** A perception signal is uniform and unbiased
> (`"<player name> entered <room>"`), identical whether the player enters a tavern or a crypt mid-rite.
> Hostility must *emerge* from the agent's own secret-rite context + goals + persona, never from biased
> signal wording or a hardcoded "attack the player."

> **C. Persuasion is the persuaded agent CHOOSING.** Modeled exactly on agent-sandbox's goal-changing
> dialogue: a character `Say`s, listeners `hear` it (speech becomes a PERCEPTION), and the listener's LLM
> then decides freely — including general goal-management verbs `AdoptGoal`/`DropGoal`. What keeps
> persuasion in check is the deciding agent's persona, not a restriction on the verb. (Precedent:
> `agent-sandbox/text_adventure_games/actions/talk.py::Say`, `actions/goals.py::AdoptGoal/DropGoal`,
> `tests/test_dialogue_persuasion.py`.)

> **D. Secrecy is the top correctness risk.** Every prompt the player can see must use the same
> revealed/secret-goal gating as the autonomous path (`build_decide_prompt`/`build_query` →
> `goals.prompt_goals(goal_list, revealed)` and `goals.render_block`, `cognition/goals.py:39-59`), or a
> cultist leaks its hidden long goal in conversation.

The shipped contract that survives unchanged: `DialogueManager.node_changed(speaker, text, options)` →
`DialoguePanel`. The UI is mostly untouched; we replace the tree-walk *behind* that signal with an LLM
round-trip, and extend the options channel into a hybrid chips+free-text composer.

---

## 2. Feature 1 — Real LLM-driven NPC conversation

### 2.0 What a "converse" turn is (plain terms)

A *converse turn* is one exchange in a back-and-forth between the player and an NPC, run through the LLM.
The *round-trip* is the full send→receive cycle: the player submits a line (a suggested chip or typed
text), the game packs everything the NPC needs to answer in character (its persona, goals, memory, the
current situation, and the player's line) into a request, POSTs it to the sidecar's `/converse` endpoint,
the sidecar asks Claude for the NPC's reply, and the answer — the NPC's spoken line, an optional action,
and a few suggested player replies — travels back and is shown in the dialogue panel.
`BrainSession.converse()` is the sidecar-side function that does the middle step (load that NPC's memory →
build the prompt → call the LLM → return `{say, action, replies}`). It is the conversation twin of the
existing `decide()`: where `decide()` answers "what is your single next autonomous action this beat?" and
returns one verb, `converse()` answers "the player just said X to you — what do you say back, and do you do
anything?" Today NO LLM runs in dialogue at all; talking just walks a pre-written tree.

### 2.1 The precedent (agent-sandbox)

`Say.apply_effects` (`actions/talk.py:209-233`) broadcasts the utterance to `game.audience_for(...)` and
each listener does `listener.hear(self._heard_line(listener))` — speech becomes a line in the listener's
`heard` buffer (a perception channel), *not* a direct state mutation on the listener. On the listener's
turn its agent observes that line and may choose `adopt goal <text>` / `drop goal <text>`
(`actions/goals.py`), which are general verbs gated only by the agent's own preconditions and persona.
`tests/test_dialogue_persuasion.py` proves the discipline: `test_servant_adopts_goal_after_hearing_request`
(a servant persona adopts the requested goal) vs `test_stubborn_knight_does_not_adopt` (a stubborn persona,
same request, refuses) — *same input, different persona, different choice*, with no hardcoded effect
anywhere. We port this exactly: the player's utterance is a perception the NPC `hear`s; the NPC's LLM
decides freely; persuasion (and refusal) are choices, not effects.

### 2.2 Architecture & data flow

```
Player composes a line (chip OR free-text)
        │  (one identical send shape — §2.6)
        ▼
DialogueManager.send_utterance(npc_id, text)          # NEW; replaces the tree-walk
        │  sets/keeps DialogueManager.active = true (gates player + NPC movement)
        │  shows a short UI "thinking…" spinner
        ▼
SidecarBridge.converse(request)  ──►  SidecarClient.converse(request)
        │                                  ├─ MockSidecar.converse()  (offline/tests, deterministic)
        │                                  └─ HttpSidecar.converse()  (real POST /converse)
        ▼
agent-sidecar  POST /converse  ──►  BrainSession.converse(request, llm_fn)   # NEW, mirrors decide()
        │  3-phase lock discipline (§2.5)
        ▼
returns { "say": "<in-character line>", "action": {verb,args}|null,
          "replies": [ up to 4 suggested player replies ] }
        ▼
DialogueManager:
   • emits node_changed(npc_display_name, say, reply_chips)    # SAME signal; UI unchanged
   • if action != null: route through governance + the existing effect/commit path (§2.4)
   • writes the turn into the SAME (session,agent) memory stream (§2.7)
        ▼
DialoguePanel renders the line + the new reply chips + free-text box (§2.6)
```

The conversation is **player-initiated and turn-based**, so unlike the real-time beat (which must never
block — `HttpSidecar.propose` returns from cache and refreshes one beat later, `src/HttpSidecar.gd:45-55`)
a converse turn may **block a short UI spinner**. `DialogueManager.converse()` calls
`SidecarBridge.converse()` synchronously from the player's turn; world time is paused for the duration
because `DialogueManager.active` already freezes the player (`src/Player.gd:50-54`) and every NPC body
(`src/NPC.gd:65-67`). We keep those gates set across the whole async round-trip (confirm both: the gates
read `DialogueManager.active`, which stays true from `start`/`send_utterance` until `_end`).

### 2.3 The `/converse` envelope

**Request** (built by `DialogueManager` from the same perception the beat loop uses, so the prompt is
consistent with `/decide`):

```jsonc
{
  "session_id":  "tingen_<pid>",          // SAME stream namespace as /decide (HttpSidecar._session_id)
  "agent_id":    "lamplighter_orin",
  "turn":        <Clock.beat_index>,
  "speaker":     "player",                // who is talking to the NPC
  "utterance":   "You don't have to go through with this.",
  "events":      [ ... ],                 // the agent's short_memory window w/ absolute seq (as /decide)
  "perception":  { ...build_snapshot/decide_request perception... },
  "goals":       [ {description, tier, secret}, ... ],   // SAME gated goal set as /decide
  "world_state": { "actor_at_rite_site": <bool>, "player_triggered": true },  // see §2.4, §8
  "revealed":    false                    // SECRECY gate — see §2.8
}
```

**Response:**

```jsonc
{
  "ok": true,
  "say":     "Stop— say that again. Quietly. Voss can't hear you.",   // NEVER governed; spoken verbatim
  "action":  { "verb": "adopt_goal", "args": { "goal": "Help the investigator stop the rite" } },  // or null
  "replies": [                                                         // up to 4 engine-shaped chips
    { "id": "press",   "text": "Then help me stop it." },
    { "id": "doubt",   "text": "You already know it's wrong." },
    { "id": "leave",   "text": "(Say nothing and leave.)" }
  ]
}
```

`say` is always present (an NPC always speaks — including a refusal). `action` is optional. `replies` are
the suggested player chips (§2.6, decided source: the NPC's converse reply returns them).

### 2.4 Governance: speech is free, only the action is governed

Per Principle A, `say` is rendered to the player **verbatim and never vetoed**. The optional `action` runs
the **same** `governance.review(gov_action, actor, world_state)` the autonomous path uses
(`cognition/brain.py:280-294`, `governance.py:49-55`): the brain derives `reveals_cult`/`public`
engine-side (`brain._derive_reveals_cult`, `brain._derive_public`, `brain.py:197-214`) and the
`_cult_secrecy`/`_no_rite_without_site` invariants decide approve/amend/veto.

**Persuasion replaces `social_influence`.** Persuading the waverer is no longer a menu effect — the NPC's
own LLM emits `adopt_goal`/`drop_goal` (§6). We keep the *consequence* the old `social_influence` wired
(faction flip → `impede`), but **triggered by the model's chosen action**, not a button:

- When an approved converse `action` is `adopt_goal` whose goal is an ally/defection goal (or
  `drop_goal` dropping the cult's operational goal) **and** the agent's `role == "scout_waverer"`,
  `DialogueManager` routes the consequence through the *same* path the old effect used:
  `PlayerActions.social_influence(agent_id)` (`src/PlayerActions.gd:31-39`) — which sets
  `a.faction = "ally"`, `a.remember(...)`, `SummoningPlan.add_impede(SOCIAL_IMPEDE, ...)`, and emits
  `player_social`. The faction/impede mechanics stay identical; only the *trigger* changed from a menu
  effect to an LLM-chosen, persona-gated, governance-approved action. (The `social_influence` effect type
  in `DialogueManager._apply_effect` and the `requires_agent_faction`-gated persuade options in
  `data/dialogue.json:118,127` are removed once the LLM path is live.)
- `world_state.player_triggered` is set **true** for converse-initiated actions (§8): a defection/reveal
  prompted by the player is player-earned, so `_cult_secrecy` must not wrongly veto it. (Today it is
  hardcoded `false` for the beat loop — `Perception.decide_request`, `src/Perception.gd:96-99`.)

### 2.5 The brain seam — `BrainSession.converse(request, llm_fn)`

A new method on `BrainSession` mirroring `decide()`'s **3-phase lock discipline**
(`cognition/brain.py:246-312`), so concurrency and idempotency stay identical:

- **Phase 1 — under the per-(session,agent) lock** (`self._lock_for(key)`, `brain.py:238-244,261-265`):
  1. `stream = self.stream(session_id, agent_id)`;
  2. **ingest the player utterance as an observation** via the same idempotent path as events
     (`_ingest_and_retrieve`, `brain.py:314-341`) — the utterance is appended as a high-importance event
     line so it cannot be lost on a re-send;
  3. retrieve relevant memories with `build_query(perception, goal_list, revealed)` (honors the secrecy
     gate — `brain.py:38-46`);
  4. `self._goals[key] = goal_list`.
- **Phase 2 — OUTSIDE the lock** (the slow network call): build a **converse prompt** (§2.8) and call
  `llm_fn(prompt)`. The reply is parsed into `{say, action, replies}` (tolerant JSON extraction like
  `sidecar.extract_action`, `sidecar.py:119-128`).
- **Phase 3 — under the lock again**: governance on the *action only* (§2.4); reflection bookkeeping
  (`importance_since_reflection` edge-trigger, `brain.py:296-303`); and **memory write-back** (§2.7): add
  an observation summarizing what the NPC said/did so the autonomous loop sees it next beat.

This reuses `_goal_objs`, `_ingest_and_retrieve`, `build_query`, and the governance call unchanged; the
only new surface is the prompt builder and the `{say, action, replies}` parse.

### 2.6 Hybrid input — chips + free-text (decided)

The composer is **2–4 engine-supplied reply chips + a free-text box**, modeled on Yumina's
`packages/app/src/features/game-play/npc-chat-bubble.tsx` (chips + free-text) and `chat-dock.tsx`
(free-text send mechanics). **Reply-choice source (decided):** the NPC's `/converse` reply returns up to 4
`replies` (cleaner than the engine deriving them post-hoc — the model already has the conversational
context to suggest good responses, and it is one round-trip not two). The chips are capped at 4,
stable-`id`-keyed, with 1–4 number-key hotkeys.

`DialoguePanel` is extended (it already clears + rebuilds option buttons on `node_changed`,
`src/DialoguePanel.gd:19-35`): render the `replies` as the existing option buttons (chip = instant send)
plus a `LineEdit` free-text box and a Send button below them.

**Imitate from Yumina (verified sound):**

| Property | Yumina source | Tingen port |
|---|---|---|
| Chips + free-text funnel through ONE identical send shape | `handleSend` and `handleQuickPhrase` both call `send({type:"send_message", content, targetNpcId})` (`npc-chat-bubble.tsx:65-116`) | both chip-press and free-text Send call `DialogueManager.send_utterance(npc_id, text)` |
| ONE in-flight lock (can't fire both at once) | `isSendingMessage` gate on both handlers (`:71,107`) | `DialogueManager._busy: bool`; both paths early-return if `_busy` |
| Choices engine-supplied, capped ~4, stable-id keyed | `quickPhrases.slice(0,4)`, `key={phrase.id ?? ...}` (`:165-181`) | `replies` capped at 4, keyed by `reply.id` |
| 1–4 number-key hotkeys | the `{i+1}` chip badges (`:178`) | `DialoguePanel._unhandled_input` maps `KEY_1..KEY_4` to chip `index` |
| Chip = instant send, does NOT touch typed text | `handleQuickPhrase` ignores `input` (`:105-116`) | chip path passes `reply.text`; never reads the `LineEdit` |
| Streaming hygiene: render only the FINAL line | `lastSpeech` skips `m.streaming` rows (`:38-51`); `chat-dock` `if (msg.streaming) continue` (`:96-97`) | converse is one synchronous round-trip — render only the returned `say`, never a mid-stream partial |

**Bake in these three fixes (bugs in the Yumina reference — must NOT be reproduced):**

1. **Enter-to-send must guard IME composition.** Yumina got this right
   (`!e.nativeEvent.isComposing`, `npc-chat-bubble.tsx:205`, `chat-dock.tsx:343`) — Godot's `LineEdit`
   already swallows composition keys, but we still must NOT treat a raw `KEY_ENTER` in `_unhandled_input`
   as send while an IME pre-edit is open: bind send to `LineEdit.text_submitted` (which fires only on a
   committed line), not to a global Enter handler. This is the explicit guard.
2. **Any safety/timeout must be ref-tracked and cleared, never a bare stacking `setTimeout`.** Yumina's
   `sendTimerRef` pattern (`npc-chat-bubble.tsx:57,94-102,120`) is the model — but the bug to avoid is a
   *stacked* timer. The Godot port: one `SceneTreeTimer` (or one-shot `Timer` node) handle stored on
   `DialogueManager._spinner_timeout`; before arming a new one, free/stop the existing handle; clear it on
   reply or on `_end`. Never create a fresh timer per send without clearing the prior.
3. **The submit guard must read FRESH state, not a stale snapshot.** Yumina's fix is the
   `useGamePlayStore.getState()` re-read after the one-render-stale capture (`npc-chat-bubble.tsx:74-76`,
   `chat-dock.tsx:154-156`). In GDScript there is no render-stale snapshot, but the equivalent discipline
   is: `send_utterance` reads `_busy` **at call time** and sets it atomically before dispatch — never act
   on a captured-earlier boolean. The single-threaded turn means a re-check at top of `send_utterance`
   suffices.

### 2.7 Memory write-back

Each converse turn writes an observation into the **same** `(session, agent)` memory stream the beat loop
uses, so what is said changes how the NPC later ACTS autonomously. In Phase 3 of
`BrainSession.converse`, after governance, call `stream.add_observation(text, turn, importance=...)`
(`cognition/agent_memory.py:292-310`) with a line like
`"the investigator said to me: <utterance>"` and, if an action was approved, `"I told them: <say>"` /
`"I chose to <verb>"`. This is the same stream `decide()` reads via `_ingest_and_retrieve`, so the next
autonomous beat retrieves it. (Mirror of agent-sandbox: the heard utterance is a perception the agent
acts on later — `test_servant_adopts_goal_after_hearing_request`.)

### 2.8 Secrecy — the top correctness risk (call-out)

The converse prompt builder **must** use the same secrecy gate as `build_decide_prompt`:

- render goals via `goals.render_block(goal_list, revealed)` (`cognition/goals.py:53-59`), which drops
  `secret` goals unless `revealed` (`prompt_goals`, `goals.py:39-50`);
- seed memory retrieval with `build_query(perception, goal_list, revealed)` (`brain.py:38-46`), which
  likewise drops secret goals from the query so a hidden aim never *surfaces a memory* into a
  player-visible context;
- the cult's true long goal is `{tier: "long", secret: true}` (`Perception._goals_for`,
  `src/Perception.gd:106-110`); on a hidden beat `revealed == false`, so it never enters the prompt;
- rite-materials knowledge stays cult-gated exactly as in `decide_request` (`Perception.gd:82-84`).

A cultist talking to the player runs with `revealed == false`, so Voss (or a still-cult Orin) can speak
freely *in character* but the prompt never contains the words "summon the descending god and escape
mortality." If we ever want a cornered cultist to *confess*, that is the model choosing a `say` that
reveals — which is fine (speech is free) — but we never hand the model the secret goal text to leak by
accident. **This is the single most important invariant in the whole feature; it gets a dedicated test
(§7).**

### 2.9 Refusal

Refusal is just an LLM-chosen `say` — an in-character rebuff ("I've nothing to say to you," a cultist
turning the player away) — shown through the same `node_changed` text channel, with `action: null`. No new
mechanism. A refusing NPC simply does not emit a goal change and may return zero or one "leave" chip.
World time stays paused while the player decides whether to press or leave (the `active` gates, §2.2).

### 2.10 Cognition tiers — every NPC converses, background NPCs cheaply (decided)

Every NPC can be talked to (drop the `dialogue_id` precondition in `NPC._can_talk`, `src/NPC.gd:92-93`, so
any agent is conversable — the brain can voice any persona). But a passing lamplighter is not worth a cult
leader's token budget, so converse runs at one of two **tiers**, set per NPC by a `tier` field in
`data/npcs.json` (`"full"` | `"light"`; default `"light"`, with the cult + named principals marked
`"full"`):

| | `full` (cult, named principals) | `light` (background civilians) |
|---|---|---|
| Memory window sent | full `short_memory` window (cap 20) | last ~3 lines only |
| Persona in prompt | `description` + `voice` + `knowledge` (+ gated `secrets`) | one-line `description` only |
| WORLD lore block (§4.3) | included | omitted |
| Suggested `replies` | up to 4 | up to 2 |
| Output cap (`max_tokens`) | normal | small |
| Memory write-back (§2.7) | yes — conversations persist + shape later autonomous action | no — stateless turn, nothing retained |

Mechanically the tier just trims the converse request the client builds (smaller `events` window, omit the
persona/lore blocks, cap `replies`) and the sidecar caps `max_tokens` for `light`; both tiers share the
exact same `/converse` code path and the same secrecy gate (§2.8). Net effect: a background NPC costs a few
hundred tokens with no lasting memory, while a cult member gets the full stateful treatment. (The same
`tier` can later gate the autonomous `/decide` cost too; this pass wires it for converse + the persona
prompt only.)

---

## 3. Feature 2 — Perception-event triggers

### 3.1 Principle & the canonical signal

Fire **objective** world events into the affected agents' perception; the LLM decides the reaction. The
prompt NEVER says "attack the player." The canonical signal text is uniform and unbiased:

```
"<player display name> entered <room display name>"
```

identical whether the player steps into a tavern or onto the crypt mid-rite. The cult turning hostile must
**emerge** from the agent's own secret-rite context + goals (the `{long, secret}` summoning goal, the
operational rite goals, `actor_at_rite_site == true`) and persona (§4), not from biased wording.

### 3.2 Stimulus framework — how a fact reaches the brain

A stimulus is injected on each affected agent **two ways**, because there is exactly one live channel and
one dead channel into the prompt:

1. **A high-importance line into `Agent.short_memory` via `Agent.remember(...)`** (`src/Agent.gd:67-71`).
   This is the live channel: `short_memory` is forwarded into `decide_request.events` with per-line
   importance (`Perception.decide_request`, `src/Perception.gd:53-60`), and the brain ingests it. Note the
   importance is scored by `Perception._event_importance` keyword match (`src/Perception.gd:116-121`) — an
   objective `"Klein entered the cathedral crypt"` already hits the `"crypt"`/`"cathedral"` keyword and
   scores **6.0** (high). For a room with no keyword (e.g. a plain tavern), we set importance explicitly:
   the injector writes the line through `remember()` and, in `decide_request`, room-entry stimulus lines
   are tagged at a floor importance of `6.0` so they reliably surface in retrieval regardless of room name.

2. **A transient `world_state` flag in `decide_request`** (e.g. `intruder: true` / `observed_by:
   "player"`), cleared after one beat. Extend `Perception.decide_request`'s `world_state` block
   (`src/Perception.gd:92-99`) to forward a per-agent transient flag set on the agent (e.g.
   `agent.pending_stimulus: Dictionary`), then cleared once consumed so it pulses for one beat only.

**GOTCHA to document (decided):** `recent_events` / `EventBus.latest` is a **DEAD channel** into the
brain. `build_snapshot` includes `recent_events` (`src/Perception.gd:35,161-165`) but `decide_request`
**never forwards it** — it builds `events` purely from `short_memory` (`Perception.gd:53-91`). So emitting
to the `EventBus` alone will **NOT** reach the prompt. Injection MUST write `short_memory` (channel 1)
and/or extend `decide_request`'s `world_state` (channel 2). Emitting an `EventBus` event is still useful
for the debug overlay/log, but it is not a brain input.

### 3.3 Detection — a thin `room_changed` signal (both boot modes)

There is **no** `room_changed` signal today (verified: none in `src/`). The only edge hook on player
movement is `WorldState.transition_requested` (`src/WorldState.gd:15`), fired via
`Portal._on_body_entered` → `SceneFade.go` → `WorldState.request_transition`
(`src/Portal.gd:15-23`, `src/SceneFade.gd:30`, `src/WorldState.gd:51-57`). Standalone runs route the same
intent through `StandaloneBoot._on_transition` → `get_tree().change_scene_to_file`
(`src/StandaloneBoot.gd:45-46`). Both modes already converge on `WorldState.request_transition`, so we add
the signal there.

**Design:** add `signal room_changed(room_id: String, scene_path: String)` to `WorldState` and emit it
from a single chokepoint after a successful transition in **both** modes:

- Main mode: `GameController._on_transition_requested` → `_swap_world` succeeds
  (`src/GameController.gd:31-46`) → resolve `room_id = RoomGraph.room_for_scene(scene_path)`
  (`src/RoomGraph.gd:34-38`, already used by `GameController.current_room`, `:56-57`) → emit
  `room_changed`.
- Standalone mode: `StandaloneBoot._on_transition` (`src/StandaloneBoot.gd:45-46`) emits the same after
  `change_scene_to_file`.

A new lightweight autoload (or a handler on `AgentRuntime`) listens for `room_changed(room_id, _path)` and
**fans the stimulus to every agent whose `agent.room == room_id`**. Use **`agent.room` equality**, NOT the
distance test: `AgentRuntime._active_agents` / `Agents.active` are room-BLIND (they compare
`position.distance_to(player_position)` across rooms — `src/AgentRuntime.gd:54-59`,
`src/AgentRegistry.gd:35-40`), so a distance test would mis-target across rooms. Iterate `Agents.all()`
and match `String(a.room) == room_id`.

**Active-set caveat (decided to document):** only ACTIVE agents reach a live `/decide`
(`AgentRuntime.run_beat` deliberates only `_active_agents()`, `src/AgentRuntime.gd:34-47`). An agent that
got the stimulus written to `short_memory` but is not active will only react when it next becomes active.
So for the signal to actually drive a decision, **the cult must be `always_active` or near the player** —
which is already true in the demo (`CitySummoning` sets `AgentRuntime.always_active[id] = true` for the
cult, `src/CitySummoning.gd:101`). Document this as a precondition of the triggers landing.

### 3.4 The player as a perceivable / attackable entity (required)

Register a **synthetic, NON-deliberating `"player"` agent** in `AgentRegistry`, mirrored each frame to the
real player's room + position, so the player appears in other agents' `nearby` and `attack
target="player"` resolves through the existing combat path. The brain NEVER decides for it.

- **Registration:** add `Agents.ensure_player_proxy()` (called at bootstrap) that inserts an `Agent` with
  `id = "player"`, `display_name` = the player's name, `faction = "player"`, `role = "investigator"`. It
  is a normal `Agent` so `_attack`/`_resolve_target` find it (`ActionCommit._resolve_target` looks up
  `Agents.get_agent(target)` first, `src/ActionCommit.gd:297-300`), and so it shows up in
  `Perception._nearby` (`src/Perception.gd:151-159`).
- **Exclusion from deliberation:** `AgentRuntime._active_agents` and the deliberation loop must skip
  `id == "player"` (it has no brain). Add an `Agent.deliberates: bool = true` flag, set `false` on the
  proxy, and filter on it in `run_beat`/`_active_agents` (`src/AgentRuntime.gd:24-59`). The proxy never
  builds a snapshot and never gets a `/decide`.
- **Mirroring:** in `GameController._process` (which already runs every frame and writes
  `AgentRuntime.player_position`, `src/GameController.gd:18-29`) also mirror the proxy:
  `player_proxy.position = player.global_position; player_proxy.room = current_room()`. Standalone mode
  mirrors the same in `StandaloneBoot._process` (`src/StandaloneBoot.gd:48-55`).

### 3.5 Stakes — full combat (decided)

The player has HP and can be downed; being downed triggers a real bad-ending hook.

- **Player health model:** the synthetic `"player"` proxy reuses `Agent`'s existing combat state — `hp`,
  `max_hp`, `downed`, `take_damage()` (`src/Agent.gd:31-33,76-81`). No new health system; the proxy IS the
  player's HP. A felled proxy sets `downed = true` (clamp-to-zero, like any agent).
- **Reuse `ATTACK_RADIUS` / `ATTACK_DAMAGE`:** `ActionCommit._attack` already does flat
  `ATTACK_DAMAGE = 34.0` within `ATTACK_RADIUS = 64.0`, emitting `agent_attacked` and (once)
  `agent_downed` (`src/ActionCommit.gd:67-70,222-235`). A cultist's `attack target="player"` resolves the
  proxy via `_resolve_target`, checks reach against `player_proxy.position` (kept live by §3.4), and
  applies damage. About three connecting strikes fell a full-HP player — unchanged.
- **EndGame seam:** a new tiny listener on `EventBus` `agent_downed` (or a direct call from the proxy's
  `take_damage` override) checks `target == "player"` and triggers the bad ending. The cleanest tie-in:
  reuse the existing `EndGame` shell (`src/EndGame.gd`) — add `EndGame.player_downed()` that does the same
  freeze + overlay as `_on_climax` but with a dedicated copy entry (extend `_ending_copy`,
  `src/EndGame.gd:114-132`) e.g. `"downed"` → "You fall on the crypt stones; the rite goes on without
  resistance." It logs `EventBus.emit_event("endgame", {...})`, sets `get_tree().paused = true`, and shows
  the overlay with Restart/Quit, exactly like the climax path (`src/EndGame.gd:23-28`). This is distinct
  from `EndGameResolver`'s strength-gated endings (`src/EndGameResolver.gd`) — a player death is its own
  immediate bad ending, not a strength resolution.

### 3.6 Trigger table (decided: framework + four triggers)

Each row is JUST a signal — an objective fact written to perception (§3.2). The LLM decides the reaction;
none of these prompts says "attack." Latency is **one beat** (~2.5s in the demo,
`Clock.minutes_per_beat`/`real_seconds_per_game_minute` set by `CitySummoning`, `src/CitySummoning.gd:66-67`).

| Trigger | Fires when | Signal line (objective) | Transient `world_state` | Who receives |
|---|---|---|---|---|
| `player_entered_room` | `room_changed` (§3.3) | `"<player> entered <room>"` | `observed_by: "player"` | every agent with `agent.room == room_id` |
| `rite_interrupted` | a `player_entered_room` whose room holds a cultist who is `actor_at_rite_site` and mid `perform_ritual_step` | `"<player> entered <room> while the rite is underway"` (still objective — states the rite is underway, names no command) | `intruder: true` | the cultist(s) on the altar |
| `cultist_attacked` | `ActionCommit._attack` connects on a cult agent (or the player attacks one) | `"<attacker> struck <target>"` | `under_attack: true` | the struck agent (+ co-located cult) |
| `ally_downed` | `agent_downed` for a cult/ally agent | `"<target> was struck down"` | `ally_down: true` | co-located same-faction agents |

`rite_interrupted` reuses the `actor_at_rite_site` predicate already in `decide_request.world_state`
(`Perception.gd:93`, `ActionCommit._near_any_rite_site`, `src/ActionCommit.gd:132-136`) and the
`perform_ritual_step` in-progress state from `agent.current_action`. The cult turning hostile on
interruption is *emergent* — the agent sees an outsider witnessing it `actor_at_rite_site` with its
secret/operational goals in context and chooses `attack`/`flee`/`hide` itself.

**Optional immediate reactive re-decide (mark OPTIONAL):** for the interrupted agents specifically, an
optional enhancement is to trigger an *immediate* extra `/decide` for just those agents the moment the
stimulus is injected, rather than waiting up to one beat (~2.5s). This is a latency optimization only —
the base design accepts one beat of latency. Flagged optional; not required for v1.

---

## 4. Feature 3 — Persona / world-description prompt enrichment

NPCs have NO persona prose today — only the one-sentence `intent` (`data/npcs.json:7`, surfaced via
`Agent.intent` → goals `short` tier, `Perception._goals_for`, `src/Perception.gd:111-112`). Features 1 & 2
are only as good as the prompt's sense of who the NPC is.

### 4.1 Per-NPC persona fields

Add to each `data/npcs.json` entry (additive — `NpcDB` reads the whole dict, `src/NpcDB.gd:14-22`):

```jsonc
"lamplighter_orin": {
  "name": "Orin the Lamplighter", "faction": "cult", "role": "scout_waverer",
  "intent": "...",                                   // unchanged
  "tier": "full",                                    // "full" | "light" — cognition budget, §2.10
  "description": "A lamplighter in his fifties, soot on his cuffs, who took the cult's coin before he understood the price.",
  "voice": "Plain, hesitant, asks more than he answers; trails off when the talk turns to the warehouse.",
  "knowledge": ["the cult meets below Saint Selena's", "Voss leads them", "the offerings are moved through the harbor"],
  "secrets": ["doubts the summoning", "has not told Voss he wavers"]
}
```

- `tier` (`"full"` | `"light"`, §2.10) → how much memory/persona/tokens this NPC's brain gets; background NPCs default to `"light"`.
- `description` + `voice` → persona prose for the prompt.
- `knowledge[]` → what this NPC may truthfully speak to (anti-hallucination floor).
- `secrets[]` → things the NPC knows but conceals — **gated** like the secret goal (rendered only when
  `revealed`, §2.8). The victim `dockhand_pell` must NOT know he is the sacrifice (`data/npcs.json:60` —
  his `intent` already says "Unaware…"); his `secrets[]` stays empty and his `knowledge[]` carries no
  cult facts.

### 4.2 Plumbing

- **`Agent.gd`**: add `description`, `voice`, `knowledge: Array`, `secrets: Array` vars; populate in
  `to_dict`/`from_dict` (`src/Agent.gd:134-172`) so they persist.
- **`AgentRegistry.rebuild()`** (`src/AgentRegistry.gd:17-27`): read the new fields off the `NpcDB` def
  alongside the existing `name`/`faction`/`role`/`intent`.
- **`Perception.build_snapshot`** (`src/Perception.gd:17-45`): add `description`, `voice`, `knowledge`,
  `secrets` to the snapshot.
- **`Perception.decide_request`** (`src/Perception.gd:53-100`): forward `description`/`voice`/`knowledge`
  into `perception`; forward `secrets` only when `revealed` (mirror the rite-materials cult gate at
  `:82-84`).
- **Sidecar prompt** (`build_decide_prompt`, `cognition/brain.py:126-188`; and the new converse prompt):
  add a PERSONA block (`description` + `voice`) and a KNOWLEDGE block; render `secrets` only when
  `revealed`. The existing `persona` dict (`brain.py:128`) is extended.

### 4.3 World / situation block (wire in existing lore)

A WORLD block built from data that already exists but never reaches the prompt:

- **`data/gods.json`** — the Descending One (`outer_god`) the cult serves, and the three opposing churches
  (`goddess_of_night`/Evernight, `eternal_blazing_sun`/Church of the Sun, `the_fool`), each with
  `domain`/`opposes_cult`/`blurb` (`data/gods.json`). Surface a one-line situational summary (the cult
  labors to pull the Descending One into Tingen; the churches oppose it).
- **`data/districts.json`** — district context for where the NPC stands.

**Clues / leads are OUT OF SCOPE for this pass (decided).** Clues have no gameplay use yet, so no
clue-collection or lead-reveal flows through dialogue: the old `collect`/`lead`/`pressure`/`thought`
dialogue effects (`DialogueManager._apply_effect`) and `WorldState.current_lead` are simply NOT ported
into the LLM path — they retire with the scripted trees. (Revisit when clues earn a gameplay role.)

Cult secrets stay gated throughout: the WORLD block is public framing; the secret long goal and
`secrets[]` remain `revealed`-only.

---

## 5. Components & seams — every file touched

| File | Change |
|---|---|
| `tingen/src/DialogueManager.gd` | Replace tree-walk with LLM round-trip. New: `send_utterance(npc_id, text)`, `converse()` (calls `SidecarBridge.converse` sync), `_busy` in-flight lock, `_spinner_timeout` ref-tracked timer, `replies` rendered through existing `node_changed`. Remove the `social_influence` effect branch (`:115-118`) once LLM persuasion is live. Keep `active` gate set across the round-trip. |
| `tingen/src/DialoguePanel.gd` | Extend `_on_node_changed` (`:19-35`): render `replies` chips (1–4 hotkeys, instant send, stable-id keyed) + a `LineEdit` free-text box + Send. Bind send to `LineEdit.text_submitted` (IME-safe), not a raw Enter handler. |
| `tingen/src/SidecarClient.gd` | New base method `converse(request: Dictionary) -> Dictionary` returning `{say:"", action:null, replies:[]}` neutral default. |
| `tingen/src/MockSidecar.gd` | New deterministic `converse()` — scripted `say`/`action`/`replies` per (agent, keyword in utterance), so offline/tests are reproducible (e.g. waverer + "stop" → `adopt_goal`). |
| `tingen/src/HttpSidecar.gd` | New `converse()` → synchronous `_http_post("/converse", request)` returning the parsed `{say,action,replies}` (own parse, not `_parse_body` which expects `actions`). Synchronous is fine — converse is player-turn, not the real-time beat. |
| `tingen/src/SidecarBridge.gd` | Expose `converse(request)` delegating to `client.converse(request)` (guard null like `propose`, `:33-36`). |
| `tingen/src/PlayerActions.gd` | `social_influence` stays as the faction-flip + impede consequence, now CALLED by `DialogueManager` when an LLM `adopt_goal`/`drop_goal` is approved for a waverer (not by a menu effect). |
| `tingen/src/WorldState.gd` | New `signal room_changed(room_id, scene_path)`; emit from `request_transition`/controller chokepoint after a successful swap. Set `player_triggered=true` plumbing for converse (transient flag). |
| `tingen/src/GameController.gd` | In `_on_transition_requested`/`_swap_world` (`:31-46`) resolve `RoomGraph.room_for_scene` and emit `room_changed`. In `_process` (`:18-29`) mirror the `"player"` proxy room+position. |
| `tingen/src/StandaloneBoot.gd` | Emit `room_changed` in `_on_transition` (`:45-46`); mirror the proxy in `_process` (`:48-55`). |
| `tingen/src/AgentRegistry.gd` | `rebuild()` reads persona fields; new `ensure_player_proxy()` registers the synthetic non-deliberating `"player"` agent. |
| `tingen/src/Agent.gd` | New vars: `description`, `voice`, `knowledge`, `secrets`, `deliberates:=true`, transient `pending_stimulus`. Add to `to_dict`/`from_dict`. |
| `tingen/src/AgentRuntime.gd` | Skip `deliberates == false` (the proxy) in `_active_agents`/`run_beat` (`:24-59`). New stimulus fan-out listener on `room_changed` (room-equality, not distance). |
| `tingen/src/Perception.gd` | `decide_request` (`:53-100`): floor importance for room-entry stimulus lines; forward transient `world_state` stimulus flags + cleared after a beat; set `player_triggered` from the converse context; forward persona/knowledge always and `secrets` gated; trim per `tier` (§2.10). `build_snapshot` (`:17-45`): add persona fields + the WORLD lore block (gods/districts). |
| `tingen/src/ActionCommit.gd` | `_attack` already resolves `"player"` via `_resolve_target` (`:222-235,297-300`) — no change beyond the proxy existing. (Optionally emit `cultist_attacked`/`ally_down` stimulus from `_attack`.) |
| `tingen/src/EndGame.gd` | New `player_downed()` bad-ending hook (freeze + overlay), listening for `agent_downed` with `target=="player"`; new `"downed"` entry in `_ending_copy` (`:114-132`). |
| `tingen/data/npcs.json` | Add `description`, `voice`, `knowledge[]`, `secrets[]` per NPC. `dockhand_pell` keeps empty secrets/no cult knowledge. |
| `tingen/data/action_schema.json` | Add `adopt_goal: ["goal"]`, `drop_goal: ["goal"]` (and the conversational verb set, §6). |
| `tingen/data/dialogue.json` | Retire the `social_influence` persuade options (`:118,127`) once LLM persuasion is live; the file may remain as a fallback while feature-flagged. |
| `agent-sidecar/sidecar.py` | New `POST /converse` route in `Handler.do_POST` (`:238-259`): parse request, call `_BRAIN.converse(req, llm)`, return `{ok, say, action, replies}`. Reuse `call_claude_full`/`extract_*` and `validate_action` for the action. |
| `agent-sidecar/cognition/brain.py` | New `BrainSession.converse(request, llm_fn)` mirroring `decide()` 3-phase lock (§2.5); new converse prompt builder reusing `render_block`/`build_query`/secrecy gate; parse `{say,action,replies}`; governance on the action only; memory write-back. Extend `build_decide_prompt` persona block with `description`/`voice`/`knowledge`/gated `secrets`. |
| `agent-sidecar/schema_parity_check.py` / `tingen/tests/run_tests.gd` | New verbs flow through automatically (parity reads the shared schema), but ADD the new verbs to the parity fixtures list (`run_tests.gd:2110-2129`) so a valid + a rejection path is exercised for each. |

---

## 6. Schema & verbs

New verbs added to **both** `data/action_schema.json` (the JSON source of truth) and exercised through the
GDScript `ActionSchema` (which loads that same JSON — `src/ActionSchema.gd:16-31`, no hardcoded list) and
the Python `sidecar.load_schema()`/`validate_action()` (`sidecar.py:55-72`):

| Verb | Required args | Purpose |
|---|---|---|
| `adopt_goal` | `["goal"]` | The NPC takes on a goal (persuasion / defection). Precedent: agent-sandbox `AdoptGoal`. |
| `drop_goal` | `["goal"]` | The NPC abandons a current goal. Precedent: agent-sandbox `DropGoal`. |

`attack` and `flee` already exist in the schema (`data/action_schema.json:7-8`) and resolve through
`ActionCommit._attack`/`_flee` — confirmed, no new combat verb needed. The conversational turn itself is
NOT a schema verb — `say` is free prose in the `/converse` envelope, never validated against the verb
schema (Principle A). Only the optional `action` (`adopt_goal`/`drop_goal`/`attack`/`flee`/etc.) goes
through `validate_action` + `governance.review`.

**Dual-source parity is mandatory.** `data/action_schema.json` is read verbatim by `ActionSchema.gd`
(`:11`) and by `sidecar.py` (`SCHEMA_PATH`, `:44`), and the cross-language parity test
(`run_tests.gd::_test_schema_parity_with_sidecar`, `:2098-2192`) asserts verb-set parity, per-verb
required-args parity, and verdict (ok+reason) parity over fixtures by invoking the real
`agent-sidecar/schema_parity_check.py`. Adding `adopt_goal`/`drop_goal` to the JSON satisfies both
validators automatically; we extend the fixtures list (`run_tests.gd:2110-2129`) with one valid and one
missing-arg case for each new verb so the parity test covers them.

---

## 7. Testing

- **Offline/deterministic (must stay green):**
  - `MockSidecar.converse()` returns scripted `{say, action, replies}` keyed on (agent_id, utterance
    keyword), so the whole dialogue path runs with no LLM and no network. Mirror of agent-sandbox's
    `MockReActClient` driving `test_dialogue_persuasion.py`.
  - The **639-test GDScript suite** (`tingen/tests/run_tests.gd`) stays green: new tests for
    `room_changed` (both boot modes), stimulus → `short_memory` injection (and the `recent_events`
    dead-channel non-regression), the `"player"` proxy resolving in `_attack`, player-downed → EndGame
    hook, and the converse seam (`DialogueManager.send_utterance` → `node_changed` with chips).
  - The **Python brain tests** (`agent-sidecar/cognition/test_brain.py`, `run_vectors.py`) stay green; add
    `converse()` unit tests mirroring `test_dialogue_persuasion.py`: same utterance, persuadable persona
    adopts vs stubborn persona refuses; and a **secrecy test** asserting the converse prompt for a
    `revealed=false` cultist contains NEITHER the secret long-goal text NOR `secrets[]` (the top-risk
    invariant, §2.8).
  - **Schema parity**: `_test_schema_parity_with_sidecar` extended with `adopt_goal`/`drop_goal` fixtures
    (`run_tests.gd:2110-2129`).
- **Live verification:** the real brain (sidecar running + `TINGEN_BRAIN=1`, `HttpSidecar` brain mode,
  `src/HttpSidecar.gd:40-43`) plus a play-through: talk a waverer round and confirm the faction flip +
  impede happen via the LLM's chosen `adopt_goal` (not a menu); walk onto the crypt mid-rite and confirm
  the cult turns hostile *without* any "attack the player" wording; let the player be downed and confirm
  the bad ending fires.

---

## 8. Risks & gotchas

1. **Secrecy leak in dialogue (TOP).** If the converse prompt builder does not reuse
   `goals.render_block(goal_list, revealed)` + `build_query(..., revealed)` (`cognition/goals.py:39-59`,
   `brain.py:38-46`) and the `secrets[]` gate, a cultist leaks its hidden long goal. Dedicated test (§7).
2. **`action_schema.json` dual-source parity.** New verbs must be in the JSON AND covered by the parity
   fixtures, or `_test_schema_parity_with_sidecar` fails (`run_tests.gd:2098-2192`). The GDScript side has
   no hardcoded verb list (`ActionSchema.gd` loads JSON), so the only failure mode is forgetting to add a
   fixture.
3. **The per-(session,agent) lock discipline in `converse()`.** Phase 1 (ingest+retrieve+goal-store) and
   Phase 3 (governance+reflection+memory write-back) MUST be under `self._lock_for(key)`; the Claude call
   MUST be outside it (`brain.py:261-303`). Getting this wrong serializes agents or races the stream.
4. **`recent_events` dead channel.** Emitting to `EventBus` does NOT reach the prompt (`decide_request`
   never forwards `recent_events`, `Perception.gd:53-91`). Stimulus MUST write `short_memory` and/or
   `decide_request.world_state`.
5. **Active-set room-blindness.** `_active_agents`/`Agents.active` use a cross-room distance test
   (`AgentRuntime.gd:54-59`, `AgentRegistry.gd:35-40`). Fan stimulus by `agent.room` equality, and note
   the cult must be `always_active`/near the player to react this beat (`CitySummoning.gd:101`).
6. **`world_state.player_triggered` is hardcoded `false`.** For the conversational / forced context, set
   it **true** (`Perception.decide_request`, `src/Perception.gd:96-99`) so a player-prompted
   reveal/defection is NOT wrongly vetoed by `_cult_secrecy` (`governance.py:13-27`).
7. **The three Yumina input bugs we are deliberately NOT reproducing** (§2.6): (1) Enter-to-send must
   guard IME composition (bind to `text_submitted`, not raw Enter); (2) the spinner/safety timeout must be
   ref-tracked and cleared, never a stacking timer; (3) the submit guard reads fresh `_busy` state at call
   time, not a stale capture.
8. **Player proxy must never deliberate.** The synthetic `"player"` agent has no brain — filter it out of
   `_active_agents`/`run_beat` via `deliberates == false` (§3.4), or the engine will try to `/decide` for
   the player.

---

## 9. Phased implementation plan

_Legend: ✅ done + verified (subagent review + playtest), ◻️ not started._

- ✅ **Phase 0 — Schema + persona data.** Add `adopt_goal`/`drop_goal` to `data/action_schema.json` + parity
  fixtures (green parity test). Add persona fields to `data/npcs.json` and plumb through
  `Agent`/`AgentRegistry`/`Perception`/`build_decide_prompt` (Feature 3). Lowest-risk, unblocks 1 & 2,
  improves the autonomous loop immediately.
- ✅ **Phase 1 — `converse()` brain + sidecar route.** `BrainSession.converse` (3-phase lock, secrecy gate,
  memory write-back), `POST /converse`, the converse prompt builder, Python unit tests incl. the secrecy
  test. No engine UI yet — test via curl + `test_brain.py`.
- ✅ **Phase 2 — Engine dialogue seam.** `SidecarClient/MockSidecar/HttpSidecar/SidecarBridge.converse`;
  `DialogueManager.send_utterance` replacing the tree-walk behind `node_changed`; route approved
  `adopt_goal`/`drop_goal` through `PlayerActions.social_influence` for the waverer consequence. Keep
  `dialogue.json` as a feature-flagged fallback until the LLM path is proven.
- ✅ **Phase 3 — Hybrid input UI.** `DialoguePanel` chips + free-text + hotkeys, the one send shape, the one
  in-flight lock, the three bug fixes. Retire the `social_influence` menu options in `dialogue.json`.
- ✅ **Phase 4 — Player entity + combat.** `ensure_player_proxy`, frame mirroring (both boot modes),
  `deliberates` filter, EndGame `player_downed` hook. Verify `attack target="player"` resolves and downs.
  Proxy is ephemeral — excluded from `AgentRegistry.to_dict` so it is never persisted; `deliberates`
  round-trips. `player_downed` is a terminal latch (a later climax can't overwrite it).
- ✅ **Phase 5 — Perception triggers.** `WorldState.room_changed` signal (both boot modes) → the
  `Stimulus` autoload fans neutral facts by room-equality: `"<player> entered the <room>"` on entry, and
  `"<A> struck <B>"` / `"<B> was struck down"` from combat events, written into the affected agents'
  `short_memory` (the live channel into `/decide`; the EventBus log is a dead channel). Wording is a pure
  observation — the reaction (incl. hostility) emerges from the agent's own secret-rite goal, never the
  signal text. Reviewed clean; flagship playtested against the live LLM (walk onto the crypt mid-rite).
- ◻️ **Phase 6 (optional) — Immediate reactive re-decide** for interrupted agents (§3.6). Latency
  optimization only — without it, an `always_active` reactor still acts on the freshly-banked stimulus on
  its very next beat (~2.5s in the City demo); a non-`always_active` agent banks it until the player is in
  range. Acceptable for v1.

---

## 10. Resolved decisions (was: open questions)

1. **DECIDED — reply chips + a guaranteed exit.** The NPC's `/converse` reply returns up to 4 (`full` tier)
   / 2 (`light` tier) `replies`; the engine ALWAYS appends a terminal "(leave)" chip, so the player can
   exit even if the model returns none.
2. **DECIDED — converse latency = blocking spinner + 15s timeout.** A "…thinking" spinner runs during the
   round-trip with a hard **15-second timeout** (ref-tracked per §2.6 fix-2): if the model has not answered
   in 15s, fall back to a generic in-character line (an "…" beat) and end the turn cleanly.
3. **DECIDED — all NPCs converse, tiered (§2.10).** Drop the `dialogue_id` precondition so every NPC is
   conversable, but background NPCs run the `light` cognition tier — significantly less memory/persona/
   tokens and no memory write-back; cult + named principals run `full`.
4. **DECIDED — combat→stimulus via a listener, combat code untouched.** `cultist_attacked`/`ally_downed`
   are produced by a listener on the EXISTING `agent_attacked`/`agent_downed` EventBus events that
   `ActionCommit._attack` already emits (`src/ActionCommit.gd:231-234`); the listener writes the objective
   line into nearby agents' `short_memory`. The trigger layer only turns a combat EVENT into a perception
   line — `ActionCommit` stays pure.
5. **DECIDED — no extra reflection on converse turns in v1.** `converse()` runs the same
   `importance_since_reflection` edge-trigger as `decide()` (`brain.py:296-303`) but skips the optional
   synthesis LLM step, matching `decide`'s current behavior.

---

## 11. Empirical findings — the cult's emergent reaction to an intruder (live LLM)

After Phase 5 shipped, a live probe of the real brain (sidecar `/decide`, both `claude-haiku-4-5` —
production — and `claude-sonnet-4-6`) measured *what the cult actually decides* when the player walks in
on the rite. This drove one code change and surfaced two decisions for the project owner.

### 11.1 The salience fix (SHIPPED, TDD-green, reviewed)
The neutral "<player> entered <room>" stimulus reached the prompt but was buried in the raw `Nearby:`
dump while the rite got a salient `SITUATION:` line — so the cult ignored the intruder. Fix
(`cognition/brain.py`): for a cult agent **at a rite site** with a non-cult witness present, surface a
pure-fact line —

> `PRESENT: an outsider (investigator) is here with you right now, and not one of the faithful.`

— stating presence + non-membership ONLY, no reaction. Gated to `actor_at_rite_site` (the "during ritual
performance" tension; off-site/undercover cultists don't turn on bystanders) and cult-scoped. Six unit
tests assert it is surfaced, names who, stays neutral (banned-word list), and is suppressed for
fellow-cultists / a downed outsider / off-site / non-cult factions. The `_has_outsider_witness` predicate
(which also drives the secrecy veto) was refactored to share `_outsider_witnesses` with no behavior change.

### 11.2 What the cult does (n=6–8 per cell, with the fix live)
| scenario (cult at altar unless noted) | haiku | sonnet |
|---|---|---|
| rite completable + intruder | perform ×6 | perform ×6 |
| performing (carrying offering) + intruder | perform ×5, talk_to ×1 | perform ×6 |
| stalled (must fetch) + intruder | idle ×5, talk_to ×1 | **talk_to ×6** |
| performing, **ALONE** (control) | perform ×6 | — |
| **city, off-site** + intruder (gate off) | hide ×5, flee ×1 | — |
| provoked (player struck down a cultist) | idle ×6, talk_to ×2 | **talk_to ×8** |
| **aggressive "rite-guard" persona** + intruder | **attack ×8** | **attack ×8** |

Reading: the salience fact makes the cult **reliably react** (stop / confront / hide) instead of
ignoring the player — with **no false hostility** (alone → keeps performing; off-site → hides, never
attacks a bystander). The reaction is **purely persona-driven and emergent**: measured Voss *confronts*
(`talk_to`); an aggressive guard *attacks* — from the identical neutral stimulus. The `attack` branch is
fully reachable but **never selected by the current roster** (Voss "measured, never raises his voice";
Dalia loyal; Orin doubting), even under direct provocation. Revealing the cult's own secret motivation to
its private cognition (`revealed=true`) pushed haiku from idle toward more engagement but not to attack.

### 11.3 Two open decisions for the project owner (NOT changed unilaterally — tone/content calls)
1. **The "attack on intrusion" vision needs an aggressive disposition.** With the current cast no cultist
   ever attacks, so the Phase-4 `player_downed` bad ending is effectively **unreachable in normal play**.
   Confirmed neutral lever (attack ×8 on both models): give one member an enforcer/zealot persona + a
   standing "guard the rite, by force if it comes to it" disposition (a *character trait*, never a
   per-event "if player enters, attack" script). Options: add a dedicated enforcer NPC, or harden an
   existing member (e.g. Dalia). **Recommended:** a dedicated enforcer, so the leader stays a talker and
   the threat is one identifiable body — preserving the talk-vs-fight spectrum.
2. **`talk_to(player)` is currently invisible to the player.** When the measured cult emergently chooses
   to confront, `ActionCommit._talk_to` writes the line into the synthetic player *proxy's* memory
   (`src/ActionCommit.gd:306`), which is never shown. So the cult's "stop and confront" reaction is real
   in the brain but unseen on screen. To make the confront branch *felt*, surface an NPC→player utterance
   as a chat bubble (reuse the npc-chat-bubble path), or treat a cultist `talk_to(player)` as the opening
   of a forced/initiated dialogue. (Separate from the attack lever; affects every non-violent reaction.)
