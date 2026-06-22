# Yumina Plugin Architecture — Raising the Authoring Ceiling

**Context:** The Tingen GDD needs systems that are "specific to this game" — a clue/evidence model, a ritual stage machine, gray-fog reconstruction, etc. Baking those into the engine core is wrong: the engine should stay general-purpose, and game-specific systems should be built ON TOP by developers.

The existing chat mode already demonstrates the right pattern: the Kochuu game is a single `customUI` TSX file (~60KB) that builds an entire horror-mystery game UI — character creation, inventory, map, roster, kill log, audio orchestration, session management — by calling `useYumina()`. The engine provides primitives (variables, reactions, audio, messages); the dev assembles them.

This document maps how to extend that authoring model from "UI + passive variables" to **"UI + systems + state shapes + simulation ticks + prompt injection + editor panels."** The comparison point is Unity, where a dev gets GameObjects + MonoBehaviours + ScriptableObjects + editor extensibility and then builds their genre-specific game on top.

---

## 1. The Two Authoring Models We Already Support

### Model A — Data-driven (forms-based)
Entries, rules, reactions, variables, scenes, entities, quests. All data, edited via editor sections, validated via Zod, persisted via DB. **Good for: non-coders. Limits: only the shapes we define.**

### Model B — Code-driven (TSX upload)
`customUI` TSX compiled with Sucrase at runtime. Full React access, `useYumina()` hook, can read variables + call mutations + play audio + navigate. **Good for: hackers. Limits: UI layer only — can't extend simulation, can't register systems, can't touch prompts.**

**Kochuu is impressive because it pushes Model B to its breaking point.** It implements character creation, audio state machine, inventory UI, mini-map, roster tracking, kill log grouping, mobile responsive layout, multi-phase cutscene transitions — all reactively driven by variables. What it CAN'T do:

- Define typed state shapes (`Clue[]`, `RumorLedger`, `Schedule`)
- Run a tick function server-side (rumor propagation, pressure decay)
- Inject prompt fragments into NPC dialogue
- Add new event types / rule triggers / behavior actions
- Extend the editor with a "Clues" authoring panel
- Persist plugin-specific state cleanly

Those are what make Tingen-class systems authorable vs. hardcoded-in-engine.

---

## 2. What Today's Extension Surfaces Give You

From the audit, here's the "you can / you can't" matrix. Every row is a current extension surface.

| Surface | You CAN (no fork) | You CAN'T (requires fork) |
|---|---|---|
| **Custom TSX UI** | Build any React tree; read `useYumina()` vars + actions; call `api.sendMessage`, `api.setVariable`, `api.playAudio`, `api.navigate`, `api.createSession`, `api.listSessions`, `api.deleteSession`, `api.revertToMessage`, `api.setAudioVolume` | Typed access to custom state; IDE-level type hints; import external packages; sandboxed execution |
| **UIBlueprint** | Compose 10 component types (text/metric/progress/badge/list/table/image/choiceGroup/form/webPanel) with bindings + triggers + interactions | Add new component types; add new transforms; add new interaction actions |
| **Variables + Rules 2.0** | Create variables (4 types), rules (9 trigger types, 8 action types, directive positions) | Add custom trigger types, action types, directive positions |
| **Reactions + EventBus** | **Emit any event type (open string); match with wildcards; react with effects**. This is the single most extensible surface. | Editor picker won't show your events unless you register a System (see below) |
| **SystemRegistry** | Register `SystemDefinition` with events + state paths; reactions editor discovers them; `@` effect routing works | Effect dispatch is a hardcoded switch — handler for `@my-system.*` has to be added in `effect-processor.ts` |
| **Behavior actions on entities** | `behavior.triggers[].action.type` is an open string — dispatcher will silently ignore unknown types | Actually RUN a custom action: dispatcher is a switch in `behavior-evaluator.ts` |
| **Entity schema** | Use 20+ built-in fields (sprite, stats, personality, behavior, tier, scriptedLines, linkedEntryIds...) | Add custom fields — Zod schemas strip unknown keys |
| **Prompt injection** | Add lorebook entries, inject directives via reactions, toggle entries, one-shot context | Add new prompt sections; reorder sections; add custom conditional fragments; inject per-NPC prompt modifications beyond `knowsVariables`/`hiddenVariables` |
| **State model** | Store anything in `GameState.metadata` (loose Record) | Typed schema; schema validation; standard serializer hooks |
| **Persistence** | Reuse `metadata` bag; plugin-specific fields survive save/load | Custom serializer per plugin; schema versioning; typed restore |
| **Editor panels** | Nothing | Add panel: fork `studio-page-catalog.ts` + `studio-shell.tsx` + register in dockview |
| **Bridge server messages** | Send custom message types — open string at the WS layer | Actually handle them: `WorldRoom.onMessage` is a switch |
| **Assets** | Sprite library accepts `additionalVariantPaths` in constructor | Tile manifest is hardcoded; audio tracks defined per-world |

**Two insights:**

1. **The infrastructure for extensibility ALREADY EXISTS for some surfaces** (EventBus open strings, SystemRegistry, behavior trigger dispatch with open-string `on` field). It's just not wired end-to-end — you can register a system, but the effect-processor won't route to your handler without a code change.

2. **The gap is "last-mile wiring"** — turning the half-built registries into proper plugin contracts that close the loop.

---

## 3. Design: "Yumina Plugins" — a unified extension surface

### 3.1 What a Plugin IS

A **plugin** is a bundle of:

- **Manifest** (`plugin.json`) — name, version, engine compat, registered names
- **State schemas** (`schemas.ts`) — Zod schemas for typed state stores the plugin owns
- **Runtime modules** (`runtime.ts`) — tick functions, event handlers, effect handlers, prompt fragment generators, message handlers
- **UI modules** (`ui/*.tsx`) — React components that read plugin state via typed `useYumina()` extensions
- **Editor modules** (`editor/*.tsx`) — authoring sections
- **Bundled assets** (`assets/`) — optional sprites, audio, fonts

A plugin is loaded by the engine at startup (or by the user via editor). It registers itself with the engine's PluginRegistry, which routes:
- Custom events → plugin event handlers
- Custom effect `@` paths → plugin effect handlers
- Custom behavior actions → plugin action handlers
- Custom rule triggers → plugin trigger evaluators
- Custom prompt fragments → prompt builder
- Custom state stores → GameState composition + save/load
- Custom entity components → entity schema passthrough
- Custom editor sections → studio catalog
- Custom UI components → `useYumina()` extension

This is the Unity parallel: **plugin = package of MonoBehaviour-equivalents + ScriptableObjects + editor scripts.**

### 3.2 The 11 extension points a plugin can use

Each is a registry. Plugin calls `engine.registerX(definition)` at load time.

| # | Registry | Plugin declares | Engine wires to |
|---|---|---|---|
| 1 | **State stores** | Typed Zod schema + initial value | `GameState[pluginName]`, save/load, `useYumina().store.pluginName` |
| 2 | **Events** (via existing SystemDefinition) | `events[]` with field shapes | Reactions WHEN picker, event bus matching |
| 3 | **Effect `@` paths** (new) | `{ path: "@clue.discover.*", handler }` | `processSystemEffects` dispatch |
| 4 | **Rule triggers** (new) | `{ type: "clue-discovered", evaluate(ctx) }` | RulesEngine trigger evaluation |
| 5 | **Rule actions** (new) | `{ type: "advance-stage", execute(payload, ctx) }` | RulesEngine action dispatch |
| 6 | **Behavior actions** (existing open-string + new handler registry) | `{ type: "investigate_clue", execute }` | BehaviorEvaluator dispatch |
| 7 | **Entity components** (new) | `{ name: "clue-source", schema, hooks }` | Entity schema passthrough + component lifecycle |
| 8 | **Prompt fragments** (new) | `{ id, section, priority, generate(ctx) }` | `buildAiSayPrompt` / `buildAiDecidePrompt` assembly |
| 9 | **Tick functions** (new) | `{ id, cadence, run(dt, ctx) }` | Bridge tick loop / WorldRoom scheduler |
| 10 | **Server message handlers** (new) | `{ type: "investigate", handle(msg, room) }` | `WorldRoom.onMessage` dispatch |
| 11 | **Editor sections** + **runtime UI components** (unified) | `{ id, icon, component }` | Studio catalog + `useYumina()` component export |

### 3.3 Plugin lifecycle

```
┌─────────────────────────────────────────────────────────┐
│ ENGINE STARTUP                                          │
│  ├─ Load plugin manifests from /plugins/ or world.plugins│
│  ├─ For each plugin:                                    │
│  │   ├─ Validate manifest vs engine version            │
│  │   ├─ Import runtime.ts                              │
│  │   ├─ Call plugin.activate(pluginApi)                │
│  │   │   └─ Plugin calls pluginApi.register*() N times │
│  │   └─ Mark plugin as active                          │
│  └─ Run all registered onSessionStart hooks            │
│                                                         │
│ SESSION (per-room)                                      │
│  ├─ Broadcast events → plugin event handlers            │
│  ├─ Process effects → plugin effect handlers            │
│  ├─ Tick loop → plugin tick functions                   │
│  ├─ Build prompts → plugin prompt fragments included    │
│  ├─ Save/load → plugin state serialized                 │
│  └─ On shutdown: plugin.deactivate()                    │
│                                                         │
│ AUTHORING (studio editor)                               │
│  ├─ Editor sections registry includes plugin sections   │
│  ├─ Reactions editor shows plugin events + state paths  │
│  └─ Rule editor shows plugin triggers + actions         │
└─────────────────────────────────────────────────────────┘
```

---

## 4. Concrete shape — the `PluginAPI` interface

```typescript
// packages/engine/src/plugin/api.ts (NEW)

export interface PluginApi {
  /** Register a typed state store. Plugin state goes into GameState[name]. */
  registerStateStore<T>(definition: {
    name: string;                    // e.g. "clues"
    schema: z.ZodSchema<T>;
    initial: T | (() => T);
    persist?: boolean;               // default true
    version?: number;                // for migrations
    migrate?: (from: number, data: unknown) => T;
  }): void;

  /** Register a custom event type. Plugin dispatches via emitEvent(). */
  registerEvent(definition: EventDefinition): void;

  /** Register a handler for a @-path effect. */
  registerEffectHandler(definition: {
    pathPattern: string;             // e.g. "@clue.discover.*" or "@rumor.propagate"
    handler: (value: unknown, path: string, ctx: EffectContext) => EffectResult;
  }): void;

  /** Register a custom rule trigger type. */
  registerRuleTrigger(definition: {
    type: string;                    // e.g. "clue-discovered"
    label: string;                   // editor display
    configSchema: z.ZodSchema;       // what editor needs
    evaluate: (config: unknown, ctx: RuleContext) => boolean;
  }): void;

  /** Register a custom rule action type. */
  registerRuleAction(definition: {
    type: string;                    // e.g. "advance-stage"
    label: string;
    configSchema: z.ZodSchema;
    execute: (config: unknown, ctx: RuleContext) => Promise<ActionResult>;
  }): void;

  /** Register a custom entity behavior action. Dispatched from
   *  behavior.triggers[].action.type === "investigate_clue". */
  registerBehaviorAction(definition: {
    type: string;
    execute: (entity: SceneEntity, action: Record<string, unknown>, ctx: BehaviorContext) => Promise<void>;
  }): void;

  /** Register a custom entity component. Entities opt in via
   *  entity.components[componentName] = <schema> data. */
  registerEntityComponent<T>(definition: {
    name: string;                    // e.g. "clue-source"
    schema: z.ZodSchema<T>;
    onPlayerInteract?: (entity, component: T, ctx) => void;
    onProximity?: (entity, component: T, ctx) => void;
    onSchedule?: (entity, component: T, phase: string, ctx) => void;
    inspector?: React.ComponentType<{ component: T; onChange: (t: T) => void }>;
  }): void;

  /** Register a prompt fragment that runs during buildAiSayPrompt / Decide. */
  registerPromptFragment(definition: {
    id: string;
    target: "ai_say" | "ai_decide" | "scene_gen" | "director_tick";
    section: "identity" | "perception" | "knowledge" | "relationship" | "current_context" | "rules" | "custom";
    priority: number;                // lower = earlier
    generate: (ctx: PromptContext) => string | null;  // null = skip
  }): void;

  /** Register a tick function that runs at a regular cadence on the bridge. */
  registerTick(definition: {
    id: string;
    cadence: "turn" | "minute" | "phase" | { everyMs: number };
    run: (ctx: TickContext) => Promise<void>;
  }): void;

  /** Register a bridge WS message handler. */
  registerMessageHandler(definition: {
    type: string;                    // e.g. "open_investigation_board"
    handle: (msg: ClientMessage, room: WorldRoom) => Promise<void>;
  }): void;

  /** Register an editor section. */
  registerEditorSection(definition: {
    id: string;                      // e.g. "tingen.clues"
    labelKey: string;
    icon: React.ComponentType;
    component: React.ComponentType<EditorSectionProps>;
    availableIn: ("chat" | "game")[];
  }): void;

  /** Register a runtime UI component accessible from user TSX via
   *  useYumina().components[name]. Mirrors how lucide icons + Chat
   *  components already get injected into the compile scope. */
  registerUIComponent(definition: {
    name: string;                    // e.g. "ClueGallery"
    component: React.ComponentType;
  }): void;

  /** Typed access to the plugin's own store during runtime. */
  store<T>(name: string): {
    get(): T;
    set(value: T): void;
    patch(partial: Partial<T>): void;
    subscribe(fn: (value: T) => void): () => void;
  };

  /** Emit a typed event. */
  emitEvent(event: GameEvent): void;

  /** Introspect: get other registered plugins (for plugin interop). */
  getPlugin(id: string): PluginInfo | null;
}

export interface Plugin {
  id: string;                        // e.g. "tingen-mystery"
  version: string;
  engineCompat: string;              // semver range
  activate(api: PluginApi): void | Promise<void>;
  deactivate?(): void;
  metadata?: PluginMetadata;
}
```

---

## 5. Worked example — how the Tingen systems get built as plugins

Instead of adding Clue/World-Manager/Schedule to the engine core, we build a `tingen-mystery` plugin that registers all of them.

### 5.1 State stores (plugin-owned typed state)

```typescript
// plugins/tingen-mystery/schemas.ts
export const ClueSchema = z.object({
  id: z.string(),
  name: z.string(),
  description: z.string(),
  type: z.enum(["physical", "behavioral", "occult"]),
  discoveredAtTurn: z.number().optional(),
  linkedEntities: z.array(z.string()).default([]),
  linkedVariables: z.array(z.string()).default([]),
  topics: z.array(z.string()).default([]),
});

export const WorldManagerStateSchema = z.object({
  stage: z.enum(["disturbance", "awakening", "investigation", "confrontation", "ritual_night", "resolution"]),
  pressure: z.object({
    corruption: z.number().min(0).max(100),
    panic: z.number().min(0).max(100),
    cultReadiness: z.number().min(0).max(100),
    attention: z.number().min(0).max(100),
  }),
  slots: z.object({
    primaryRitualSite: z.string().optional(),
    firstCorruptedCivilian: z.string().optional(),
    decoyCourier: z.string().optional(),
  }),
  lastOffscreenTickTurn: z.number().default(0),
});

export const RumorSchema = z.object({
  id: z.string(),
  topic: z.string(),
  truthfulness: z.number().min(0).max(1),
  district: z.string(),
  spreadStrength: z.number().min(0).max(1),
  valence: z.enum(["positive", "negative", "neutral"]),
  heardBy: z.array(z.string()).default([]),  // entity IDs
});

export const ClockSchema = z.object({
  day: z.number().min(1),
  minuteOfDay: z.number().min(0).max(1440),  // 0-1440
  phase: z.enum(["early-morning", "morning", "afternoon", "dusk", "night", "late-night"]),
});
```

### 5.2 Runtime (activate hook registers everything)

```typescript
// plugins/tingen-mystery/runtime.ts
export default {
  id: "tingen-mystery",
  version: "1.0.0",
  engineCompat: "^0.5.0",
  activate(api) {
    // ── 1. State stores ────────────────────────────────
    api.registerStateStore({ name: "clues", schema: z.array(ClueSchema), initial: [] });
    api.registerStateStore({ name: "worldManager", schema: WorldManagerStateSchema, initial: { stage: "disturbance", pressure: { corruption: 0, panic: 0, cultReadiness: 0, attention: 0 }, slots: {}, lastOffscreenTickTurn: 0 } });
    api.registerStateStore({ name: "rumors", schema: z.array(RumorSchema), initial: [] });
    api.registerStateStore({ name: "clock", schema: ClockSchema, initial: { day: 1, minuteOfDay: 480, phase: "morning" } });

    // ── 2. Events ──────────────────────────────────────
    api.registerEvent({ type: "clue:discovered", dataFields: [{ name: "clueId", type: "string" }] });
    api.registerEvent({ type: "rumor:heard", dataFields: [{ name: "rumorId", type: "string" }, { name: "byEntityId", type: "string" }] });
    api.registerEvent({ type: "stage:advanced", dataFields: [{ name: "from", type: "string" }, { name: "to", type: "string" }] });
    api.registerEvent({ type: "clock:phase-changed", dataFields: [{ name: "phase", type: "string" }, { name: "day", type: "number" }] });
    api.registerEvent({ type: "pressure:threshold-crossed", dataFields: [{ name: "name", type: "string" }, { name: "value", type: "number" }] });

    // ── 3. Effect handlers ─────────────────────────────
    api.registerEffectHandler({
      pathPattern: "@clue.discover.*",
      handler: (value, path, ctx) => {
        const clueId = path.split(".")[2];
        const clues = api.store("clues").get();
        const clue = value as unknown as z.infer<typeof ClueSchema>;
        api.store("clues").set([...clues, { ...clue, discoveredAtTurn: ctx.turnCount }]);
        api.emitEvent({ type: "clue:discovered", clueId });
        return { applied: true };
      },
    });
    api.registerEffectHandler({
      pathPattern: "@pressure.*",
      handler: (value, path, ctx) => {
        const key = path.split(".")[1];  // corruption | panic | ...
        const wm = api.store("worldManager").get();
        const delta = value as number;
        const next = Math.max(0, Math.min(100, wm.pressure[key] + delta));
        api.store("worldManager").patch({ pressure: { ...wm.pressure, [key]: next } });
        if (Math.floor(wm.pressure[key] / 25) !== Math.floor(next / 25)) {
          api.emitEvent({ type: "pressure:threshold-crossed", name: key, value: next });
        }
        return { applied: true };
      },
    });

    // ── 4. Prompt fragments ────────────────────────────
    api.registerPromptFragment({
      id: "tingen.current-stage",
      target: "ai_say",
      section: "current_context",
      priority: 10,
      generate: (ctx) => {
        const wm = api.store("worldManager").get();
        return `Current stage: ${wm.stage}. City pressure: corruption ${wm.pressure.corruption}%, panic ${wm.pressure.panic}%.`;
      },
    });
    api.registerPromptFragment({
      id: "tingen.clock",
      target: "ai_say",
      section: "current_context",
      priority: 5,
      generate: (ctx) => {
        const clk = api.store("clock").get();
        return `Day ${clk.day}, ${clk.phase}.`;
      },
    });
    api.registerPromptFragment({
      id: "tingen.npc-rumors",
      target: "ai_say",
      section: "knowledge",
      priority: 20,
      generate: (ctx) => {
        const rumors = api.store("rumors").get().filter(r => r.heardBy.includes(ctx.entity.id));
        if (rumors.length === 0) return null;
        return "Rumors you've heard:\n" + rumors.slice(-3).map(r =>
          `- "${r.topic}" (truthfulness ${(r.truthfulness*100).toFixed(0)}%, ${r.valence})`
        ).join("\n");
      },
    });

    // ── 5. Tick functions ──────────────────────────────
    api.registerTick({
      id: "tingen.clock-advance",
      cadence: { everyMs: 60_000 },  // 1 real minute = 1 game minute
      run: async (ctx) => {
        const clk = api.store("clock").get();
        const nextMin = clk.minuteOfDay + 1;
        if (nextMin >= 1440) {
          api.store("clock").set({ day: clk.day + 1, minuteOfDay: 0, phase: "early-morning" });
          api.emitEvent({ type: "clock:day-rolled", day: clk.day + 1 });
        } else {
          const phase = minuteToPhase(nextMin);
          api.store("clock").set({ ...clk, minuteOfDay: nextMin, phase });
          if (phase !== clk.phase) api.emitEvent({ type: "clock:phase-changed", phase, day: clk.day });
        }
      },
    });
    api.registerTick({
      id: "tingen.rumor-propagate",
      cadence: "turn",
      run: async (ctx) => {
        // On each turn, rumors decay 1% and propagate to nearby NPCs
        const rumors = api.store("rumors").get();
        const decayed = rumors.map(r => ({ ...r, spreadStrength: Math.max(0, r.spreadStrength - 0.01) }));
        api.store("rumors").set(decayed);
      },
    });
    api.registerTick({
      id: "tingen.offscreen-resolution",
      cadence: "turn",
      run: async (ctx) => {
        // Every 10 turns, advance pressure based on stage + unspent activity
        const wm = api.store("worldManager").get();
        if (ctx.turnCount - wm.lastOffscreenTickTurn < 10) return;
        const gain = stageActivityCoefficient(wm.stage);
        api.store("worldManager").patch({
          pressure: { ...wm.pressure, cultReadiness: Math.min(100, wm.pressure.cultReadiness + gain) },
          lastOffscreenTickTurn: ctx.turnCount,
        });
      },
    });

    // ── 6. Behavior actions ────────────────────────────
    api.registerBehaviorAction({
      type: "reveal_clue",
      execute: async (entity, action, ctx) => {
        const clueData = action as { clueId: string; name: string; description: string; type: string };
        // Same as @clue.discover.{id} effect — here we provide a more
        // NPC-friendly handle for behavior.triggers[].
        api.store("clues").patch(/* ... */);
        api.emitEvent({ type: "clue:discovered", clueId: clueData.clueId });
      },
    });

    // ── 7. Entity components ───────────────────────────
    api.registerEntityComponent({
      name: "clue-source",
      schema: z.object({
        clueId: z.string(),
        discoveredByAction: z.enum(["interact", "proximity", "dialogue-topic"]),
      }),
      onPlayerInteract: (entity, component, ctx) => {
        if (component.discoveredByAction === "interact") {
          // Dispatch to clue system
          api.store("clues").patch(/* ... */);
          api.emitEvent({ type: "clue:discovered", clueId: component.clueId });
        }
      },
    });

    // ── 8. Editor sections ─────────────────────────────
    api.registerEditorSection({
      id: "tingen.clues",
      labelKey: "tingen.panels.clues",
      icon: SearchIcon,
      availableIn: ["game"],
      component: CluesEditorSection,
    });
    api.registerEditorSection({
      id: "tingen.world-manager",
      labelKey: "tingen.panels.worldManager",
      icon: CompassIcon,
      availableIn: ["game"],
      component: WorldManagerEditorSection,
    });
    api.registerEditorSection({
      id: "tingen.schedules",
      labelKey: "tingen.panels.schedules",
      icon: CalendarIcon,
      availableIn: ["game"],
      component: SchedulesEditorSection,
    });

    // ── 9. Runtime UI components ──────────────────────
    api.registerUIComponent({ name: "InvestigationBoard", component: InvestigationBoard });
    api.registerUIComponent({ name: "PressureMeter", component: PressureMeter });
    api.registerUIComponent({ name: "Clock", component: ClockHUD });
    // Now user TSX can do:
    //   var InvestigationBoard = useYumina().components.InvestigationBoard;
    //   return h(InvestigationBoard, { clues: api.store.clues });

    // ── 10. Server message handlers ───────────────────
    api.registerMessageHandler({
      type: "open_investigation_board",
      handle: async (msg, room) => {
        room.broadcast({ type: "investigation_board_opened", clues: api.store("clues").get() });
      },
    });
  },
} satisfies Plugin;
```

### 5.3 User-authored Tingen TSX becomes much shorter

Instead of the 60KB Kochuu-style monolith, Tingen's TSX becomes:

```tsx
export default function TingenGame({ variables, isStreaming }) {
  const api = useYumina();
  const { Clock, PressureMeter, InvestigationBoard } = api.components;

  const clock = api.store.clock;                // typed: ClockState
  const worldManager = api.store.worldManager;  // typed: WorldManagerState
  const clues = api.store.clues;                // typed: Clue[]

  return (
    <div className="tingen-root">
      <Clock {...clock} />
      <PressureMeter pressure={worldManager.pressure} />
      <ChatArea messages={api.messages} onSend={api.sendMessage} />
      <InvestigationBoard clues={clues} onClueInspect={(id) =>
        api.sendMessage(`I want to examine the ${id}`)
      }/>
    </div>
  );
}
```

The plugin provides the primitives; the user TSX does layout + glue.

---

## 6. Implementation roadmap — how we actually build this

### Phase A — Formalize what already works (1 week)

Turn the **latent** extensibility into **documented + typed** extensibility. No new engine features, but lock in the contracts.

- **A1**: Publish `useYumina()` API reference with typed signatures. Today it's implicit.
- **A2**: Document the EventBus open-string contract + `SystemRegistry.register()` pattern.
- **A3**: Type `GameState.metadata` as `Record<string, unknown>` with namespace convention (`metadata["pluginId.key"]`).
- **A4**: Document the behavior-action dispatch open-string contract.
- **A5**: Ship a tiny `demo-counter-plugin` that uses only existing surfaces (events + metadata + custom UI) — proves the pattern.

**Deliverable**: `docs/plugins/getting-started.md` + typed examples.

### Phase B — The PluginAPI skeleton + state stores (1-2 weeks)

Build the core plugin runtime. Minimum viable API.

- **B1**: `packages/engine/src/plugin/api.ts` — interface + `createPluginApi()` factory.
- **B2**: `packages/engine/src/plugin/state-store.ts` — typed state stores backed by `GameState.metadata` with namespace convention. Zod validation on write. Reactive subscribe.
- **B3**: `packages/engine/src/plugin/registry.ts` — central plugin registry with load/activate/deactivate.
- **B4**: Migrate `SpatialRuntime` and `TimerRuntime` to use `registerStateStore` internally (dogfood).
- **B5**: Persist state stores via WorldRoom save/load (pass-through the full `metadata` bag).

**Deliverable**: A plugin can `registerStateStore()` and see it typed, saved, and reactive.

### Phase C — Effect + event + prompt extensibility (1-2 weeks)

Close the "last-mile wiring" loop on the three existing half-built surfaces.

- **C1**: Refactor `effect-processor.ts` — replace the hardcoded switch with a registry lookup (`registerEffectHandler` wired in). Built-ins become first-registered entries.
- **C2**: Extend `SystemRegistry` so plugins register systems at runtime (not just at engine init).
- **C3**: Refactor `buildAiSayPrompt` + `buildAiDecidePrompt` to assemble from registered fragments by `section` + `priority`. Built-in sections become first-registered fragments.
- **C4**: Effect-processor gets a `registerEffectHandler` hook for `@` paths.

**Deliverable**: A plugin can add a custom `@pressure.panic +=` effect, emit a custom `stage:advanced` event, and inject a prompt fragment.

### Phase D — Rule/behavior/entity extensibility (2 weeks)

Open up the structured authoring surfaces.

- **D1**: Add `registerRuleTrigger` + `registerRuleAction`. RulesEngine dispatches via registry. Editor's rule form discovers plugin types.
- **D2**: Add `registerBehaviorAction`. BehaviorEvaluator dispatches via registry.
- **D3**: Add `registerEntityComponent`. Entity schema uses Zod `.passthrough()` for a `components?: Record<string, unknown>` bag. Lifecycle hooks wired in.
- **D4**: Rules/behaviors/entity editors discover plugin registrations at render time.

**Deliverable**: A plugin can add a "Clue source" entity component, a "discover clue" behavior action, a "clue-discovered" rule trigger — and author them in the editor.

### Phase E — Editor + UI component extensibility (1-2 weeks)

- **E1**: `studio-page-catalog.ts` becomes a registry — built-in panels + plugin panels. Panel IDs namespaced.
- **E2**: `studio-shell.tsx` renders any registered panel via the standard contract.
- **E3**: `registerUIComponent()` adds components to `useYumina().components` scope — available in user TSX.
- **E4**: Hot reload — editor can reload a plugin without restarting dev server.

**Deliverable**: A plugin can ship a fully-authored "Clues" editor section and an `<InvestigationBoard>` runtime UI component.

### Phase F — Tick functions + server message handlers (1 week)

- **F1**: `registerTick({ cadence: "turn" | "minute" | "phase" | { everyMs } })`. WorldRoom owns the tick scheduler.
- **F2**: `registerMessageHandler`. `WorldRoom.onMessage` dispatches via registry.

**Deliverable**: A plugin can run a server-side rumor-propagation tick every game minute.

### Phase G — Tingen plugin itself (2-3 weeks)

With the plugin API shipped, build the full `tingen-mystery` plugin using it.

- **G1**: Clock + day phases → `registerStateStore("clock")` + `registerTick("clock-advance")` + `registerEvent("clock:phase-changed")`
- **G2**: Schedules → `registerEntityComponent("schedule")` + `registerPromptFragment("npc-schedule")` + reaction on `clock:phase-changed`
- **G3**: World Manager → `registerStateStore("worldManager")` + `registerEffectHandler("@pressure.*")` + `registerTick("offscreen-resolution")` + `registerEditorSection("tingen.world-manager")`
- **G4**: Clues → `registerStateStore("clues")` + `registerEffectHandler("@clue.discover.*")` + `registerEntityComponent("clue-source")` + `registerEditorSection("tingen.clues")` + `registerUIComponent("InvestigationBoard")`
- **G5**: Rumors → `registerStateStore("rumors")` + `registerTick("rumor-propagate")` + `registerPromptFragment("npc-rumors")`
- **G6**: Occult tools → `registerRuleAction("divination")` + UI components + custom state
- **G7**: Cutscenes → `registerStateStore("cutscene-state")` + `registerMessageHandler("cutscene:advance")` + UI component

**Deliverable**: Tingen ships as a plugin that the Yumina engine has no first-class knowledge of. Proves the API is complete.

### Phase H — Plugin distribution + marketplace (stretch, post-slice)

- **H1**: `plugin.json` schema + CLI to package a plugin (`yumina plugin pack`)
- **H2**: Plugin install via URL / upload in editor
- **H3**: Plugin marketplace listing (curated for v1)
- **H4**: Plugin dependency + version resolution

**Deliverable**: Community can build and share plugins.

---

## 7. Comparison: Unity-parallel for each primitive

| Yumina plugin API | Unity equivalent | Purpose |
|---|---|---|
| `registerStateStore` | `ScriptableObject` | Typed persistent game data |
| `registerEntityComponent` | `MonoBehaviour` | Behavior attachable to entities |
| `registerTick` | `Update()` / coroutines | Per-frame / per-interval simulation |
| `registerEvent` + `registerEffectHandler` | `UnityEvent` / custom events | Loose coupling between systems |
| `registerPromptFragment` | (no direct parallel — unique to narrative engine) | Compose LLM context |
| `registerRuleTrigger` + `registerRuleAction` | Visual scripting graphs | Author-friendly rule wiring |
| `registerBehaviorAction` | `AnimationEvent` + `StateMachineBehaviour` | Entity-level state transitions |
| `registerEditorSection` | `EditorWindow` / `CustomInspector` | Authoring UI |
| `registerUIComponent` | Prefabs / `UIToolkit` | Runtime UI building blocks |
| `registerMessageHandler` | Networking / RPCs | Client-server communication |

Every Unity primitive has a clean Yumina parallel — the design space is well-trodden.

---

## 8. What this means for the Tingen slice

Option A — **Build Tingen systems directly into the engine** (the M1-M10 plan from yesterday).
- Pros: fastest path to a shippable Tingen
- Cons: engine becomes bloated with mystery-game-specific code; "not the Unity analog"

Option B — **Build the plugin API, then build Tingen as a plugin** (this doc).
- Pros: engine stays clean; Tingen is the first exemplar plugin; third parties can build other genres
- Cons: ~2-3 weeks of up-front API work before Tingen gets any new capability

Option C — **Hybrid: build the FIRST Tingen system (game clock) in-engine to deliver value, then extract the plugin API after** (recommended for MVP).
- Ship M1 (game clock) as a built-in system this week
- Ship M2 (NPC schedules) as a built-in system next week
- Use THOSE TWO as the proving ground for the plugin API — refactor them into plugins as part of Phase B-D of this plan
- Remaining systems (M3-M10) ship directly as plugins
- Tingen becomes the plugin that uses those plugins + plugin-specific systems

The C path gives us a shippable Tingen slice AND a real plugin architecture at the end, without blocking progress on the API work.

---

## 9. Key design principles

1. **Registries over switches.** Any place the engine does `switch (type) { case "known": ... }` is a fork-blocker. Replace with `registry.get(type).handle()`. Built-ins register first.

2. **Namespace everything.** Plugin IDs prefix state stores, event types, effect paths, editor sections, UI components. `@tingen.clue.discover` vs `@spatial.move`. Prevents collisions.

3. **Typed at the edges, loose in the middle.** Plugin state is Zod-validated on write, but stored as `Record<string, unknown>` in the metadata bag. Runtime typing via TypeScript generics on `api.store<T>()`.

4. **All plugin state survives save/load.** The engine's save format is "write `GameState` JSON; restore → replay plugin migrations." No plugin-specific persistence logic.

5. **Editor discovers plugins reflectively.** No hardcoded panel lists. Reactions picker pulls from `SystemRegistry.getAvailableEvents()`; rule action picker pulls from `registerRuleAction()` registry; etc.

6. **Prompt fragments are composable.** Never hardcode NPC prompt sections — always compose from registered fragments. Mystery games add "stage + pressure" fragments; dating sims add "affection + memory-of-date" fragments; life sims add "job + schedule" fragments.

7. **User TSX gets more capable as plugins register more UI components.** A Tingen TSX file can import `<InvestigationBoard>` because the plugin registered it. A city-builder plugin would register `<ResourceBar>`, `<BuildingPalette>`, etc.

8. **Plugins can be partial.** A plugin that only registers a UI component is valid. A plugin that only adds a single rule action is valid. No "must implement N interfaces" burden.

---

## 10. Open design questions

1. **Plugin loading order + dependencies.** Tingen-cutscene plugin may need Tingen-clock plugin. Dependency resolution: semver ranges in manifest?

2. **Plugin sandboxing.** Custom TSX is already loosely sandboxed. Server-side plugin code (tick functions, effect handlers) — do we run them in the same process or a worker? Probably same process for v1 but add a deny-list for filesystem/network.

3. **Hot reload vs. cold restart.** Editor plugin changes should hot-reload. Runtime plugin state migrations on load?

4. **Plugin versioning + backward compat.** When the engine adds a new field to an event shape, old plugins should still work. Event shapes probably need a "version" field.

5. **Multi-plugin collision.** Two plugins both register `@pressure.*` — who wins? Probably first-register wins, and second gets a warning. Could also introduce an explicit priority field.

6. **Plugin state migration.** A plugin ships v1 with `pressure: number`, ships v2 with `pressure: { corruption, panic }`. We need migration support. Plugins register a `migrate(fromVersion, data)` function.

7. **Performance.** Registry lookup on every event dispatch has O(1) cost if we use Map. Prompt fragment assembly runs on every NPC interaction — keep the fragment count small per NPC (tag fragments by applicability).

8. **Plugins vs. skills.** `/.claude/skills/` already exists as a concept in the repo's Claude Code integration. Naming: "plugin" for engine extensions, "skill" for user-invoked capabilities — keep separate.

9. **Client-side vs. server-side split.** State stores need to exist on both sides. Plugin manifests should declare which side each hook runs on. Tick functions → server. UI components → client. Effect handlers → server (with client-broadcasts). Editor sections → client.

10. **Testing story.** Plugin authors need a way to unit-test their plugins. Provide a test harness that mocks the `PluginApi` and lets them assert on emitted events + state store contents.

---

## 11. Summary — why this is the right bet

The Yumina engine has TWO authoring strengths today:
- **Data-driven authoring** (forms editor) — makes the 80th percentile author productive
- **Code-driven authoring** (TSX upload) — makes the 99th percentile author unreasonably productive

What's missing is the **connective tissue** between them — today a TSX author can't define new typed state, register server-side simulation, or extend the editor for other authors.

The plugin API fills exactly that gap. It turns Yumina from "a narrative engine with one general-purpose shape" into **"a narrative engine with a component/plugin model — like Unity, but for LLM-driven narratives."**

Every genre-specific system becomes a plugin: mystery (clues + rumors + investigation board), dating sim (relationships + affection + date planner), survival sim (resources + crafting + needs), life sim (schedules + careers + aging), tactical combat (grid + abilities + turn order). None of them belong in the engine core. All of them want the same 11 extension points.

**Recommendation: Option C from section 8** — ship M1 clock + M2 schedules as in-engine first, extract them as the first plugin examples during Phase B-E of this work, then build the rest of Tingen as plugins. Total: ~10-12 weeks for Tingen vertical slice + real plugin API.
