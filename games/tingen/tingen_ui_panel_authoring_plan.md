# UI Panel Authoring — First-Class Tab in Both Editors

**Reference**: the Kochuu (壶中毒) TSX example — an entire 60KB mystery game UI (character creation, inventory, SVG map, roster, kill log, audio orchestration, session management) built in one file via `useYumina()`.

**Goal**: make that authoring experience first-class, not an obscure "Components" section. Every world should have a **UI Panels** tab in both the simple editor and the studio editor, with three creation flows:

1. **Templates** — curated gallery of pre-built panels
2. **AI generation** — describe the panel, get a TSX stub
3. **Custom paste / upload** — enhanced existing flow

This is the "freedom-enabling" authoring surface that makes Yumina behave like a proper narrative-game engine (vs. a chat wrapper).

---

## 1. Why this matters

### Current state
- `packages/app/src/features/editor/sections/components.tsx` — single section, hidden-ish name
- `CustomUIComponent` schema: `{ id, name, surface: "message" | "app", tsxCode, description, order, visible }`
- Two hardcoded surfaces: `message` (chat bubble) and `app` (full game shell)
- One code editor, one compile-status indicator, one snippet menu with ~5 entries
- No preview, no templates, no AI gen

### What Kochuu proves is possible
Read `/Users/markma/Desktop/yumina/tingen_mystery_pixel_game_gdd.md` alongside the Kochuu TSX:

- **Full game shell** — own header, own chat area, own side panels, own modals
- **Character creation** — 3-column terminal-style form with archetype cards, text inputs, validation
- **Multi-phase cutscene transitions** — shake → ink-spread → dead-black → TV-line → CRT-reveal → eye-open (5 animation phases, all CSS keyframes injected into the document head)
- **Theming from variables** — `isNight = time === "夜晚"` → switches entire color palette (`C.bg`, `C.text`, `C.gold`, sky gradient with radial star field vs. warm dusk)
- **Interactive SVG map** — clickable zones, player marker with pulsing animation, map-marker drop-and-label flow
- **Roster with filters** (全部/存活/已亡) + inline note editing
- **Kill log grouped by day**
- **Inventory / allies / intel** with hover-appear action buttons (用 / 丢 / 呼叫 / verify)
- **Audio orchestration** — `api.playAudio("creation-bgm")` → `api.stopAudio` → `api.playAudio("heartbeat-sfx", { chainTo: "game-playlist" })`
- **Session management** — list sessions, new session, delete with confirm, navigate
- **Mobile responsive** — tab bar at narrow widths
- **Message action buttons** — copy, revert-to (via `api.revertToMessage`)

This is **the ceiling of the current authoring model**. It's possible because `useYumina()` exposes a rich API; but creating it today requires writing all 60KB by hand. The UI Panel Authoring feature lowers that barrier.

### The authoring gap
- Non-coder authors today have no path to Kochuu-level UI. Forms-based editor gives them variables/rules/lorebook — no visual game shell.
- Coder authors today have `components.tsx` but no preview, no templates, no AI assist — just an empty code buffer.
- LLM-generated authoring is the biggest unlock: an author says "I want a horror mystery game with a roster of 40 students and a kill log" and the AI outputs a Kochuu-shaped scaffold ready to iterate on.

---

## 2. Expanded surface types

Current: `message | app`. Proposed:

| Surface | Role | Example |
|---|---|---|
| `chat-bubble` | Renders inside each chat message (existing "message") | Per-NPC dialogue styling, XML-tag parsing |
| `game-shell` | Replaces default chat view with a full custom experience (existing "app") | Kochuu, the whole Tingen game UI |
| `hud-overlay` | Persistent widget layered on top of game-shell — screen-space | Clock, health bar, pressure meter, objective tracker |
| `modal` | Opens on event or button trigger, full-screen with close button | Investigation board, settings, character sheet, codex |
| `sidebar` | Docks left/right of the game area (author chooses side + width) | Inventory, roster, quest log, dialogue history |

**How they combine**: a world can have one `game-shell` + N `hud-overlay`s + M `modal`s + K `sidebar`s. The default shell just renders Chat + ambient elements; an author can replace that shell with their own (Kochuu) and still layer HUDs/modals on top.

**New schema field**: `triggerEvent?: string` — for `modal` / `sidebar` panels, which event opens them. E.g., `"tingen:open-investigation-board"` or user-defined.

---

## 3. Creation flows (three paths)

### Flow 1: Template gallery
When user clicks "New Panel", they see a card gallery with ~8-12 curated templates:

| Template | Surface | Vibe | Code size | Primary use |
|---|---|---|---|---|
| **Kochuu Horror Mystery (reference)** | game-shell | Arcade horror, paper texture, SVG map | 60KB | Mystery / survival / battle-royale |
| **Classic RPG HUD** | hud-overlay | SNES-style bordered panels | 2-3KB | Dungeon crawler |
| **Terminal Chat** | chat-bubble | Monospace, green-on-black | ~1KB | Sci-fi / cyberpunk |
| **Inventory Grid** | sidebar | 4-wide grid with hover tooltips | 3KB | Survival, crafting |
| **Investigation Board** | modal | Node-link or sortable gallery | 4-5KB | Mystery, detective |
| **Quest Journal** | sidebar | Day-grouped list with milestones | 2-3KB | Adventure, RPG |
| **Minimal Clock** | hud-overlay | Top-bar clock + phase indicator | 500B | Any time-based game |
| **Relationship Tracker** | sidebar | Per-NPC relationship bars | 2KB | Dating sim, social sim |
| **Combat Abilities** | hud-overlay | Hotkey bar with cooldowns | 2KB | Combat-focused games |
| **Character Creator Terminal** | game-shell (intro) | Kochuu-style multi-column form | 10KB | Any game with character creation |
| **Cutscene Overlay** | modal | Timeline-driven fade + text + image | 3KB | Intro + stage-reveal scenes |
| **Blank Game Shell** | game-shell | Minimal scaffold with useYumina hook | 200B | "I want to write it myself" |

Click → opens the editor with the template's TSX pre-loaded + description + pre-filled fields (name, surface).

### Flow 2: AI generation
User clicks "AI Generate Panel". Wizard asks:

1. **Purpose** (free text): "A horror mystery game HUD with roster, kill log, and map"
2. **Surface** (dropdown): chat-bubble / game-shell / hud-overlay / modal / sidebar
3. **Variables it binds to** (multi-select from world's variable list): `survivors`, `day-count`, `location`, `kill-log`, `inventory`, `dead-names`
4. **Actions it can call** (multi-select): `sendMessage`, `setVariable`, `playAudio`, `revertToMessage`...
5. **Reference style** (optional): "Like the Kochuu example" / "Like a minimal terminal" / "Like an RPG"

Generated prompt includes:
- Full `useYumina()` API signature
- World's variable list with types + initial values
- World's audio tracks list
- World's rules / events that can be triggered
- The chosen template as a starting-point reference (if any)
- Explicit output format: "a single default-exported React function component, uses `useYumina()` to read state and trigger actions, CSS-in-JS, handles mobile responsive"

LLM output: full TSX. User reviews → auto-compile → preview → iterate with follow-up prompts ("add an audio control in the bottom-right").

### Flow 3: Custom paste / upload
Existing flow, unchanged in function but polished:
- Monaco-style code editor (currently textarea)
- Live compile indicator (exists today — promote to always-visible)
- Always-visible preview pane (currently: preview elsewhere, not tied to panel)
- Snippet menu (exists today — expand to 15-20 entries)
- File upload button (`.tsx` / `.jsx`) — drops into the editor

---

## 4. Simple editor integration

Target: `packages/app/src/features/editor/sections/ui-panels.tsx` (new).

**Location in sidebar nav**: between `Components` (to be renamed / absorbed) and `Audio`, or replace `Components` entirely. I'd do the latter — `Components` becomes `UI Panels`.

**Layout**:
```
┌─ Sidebar ─┐  ┌─ UI Panels ───────────────────────────────┐
│ Overview  │  │                                           │
│ Characters│  │  [ + New Panel ]   (dropdown):            │
│ Entities  │  │                    ╔═══════════════════╗  │
│ Variables │  │                    ║ From Template ›   ║  │
│ Rules     │  │                    ║ AI Generate       ║  │
│ Entries   │  │                    ║ Paste TSX         ║  │
│ Audio     │  │                    ║ Upload File       ║  │
│ UI Panels │  │                    ╚═══════════════════╝  │
│ Scenes    │  │                                           │
│ ...       │  │  ┌───────────┐  ┌───────────┐  ┌────────┐│
│           │  │  │ kochuu    │  │ investiga │  │ clock  ││
│           │  │  │ [preview] │  │ tion      │  │        ││
│           │  │  │           │  │ [preview] │  │ [prev] ││
│           │  │  │ game-shell│  │ modal     │  │ hud    ││
│           │  │  └───────────┘  └───────────┘  └────────┘│
└───────────┘  └───────────────────────────────────────────┘
```

**Card per panel**:
- Thumbnail preview (captured via canvas screenshot at save time, or live-rendered micro-iframe)
- Name, description, surface badge
- Enabled toggle, reorder handle
- Click → opens editor (see below)

**Editor view** (per panel):
```
┌─ Panel: kochuu ─────────────────────────────────────────┐
│  Name: [ kochuu                             ]           │
│  Surface: [ game-shell ▼ ]  Enabled: [✓]                │
│  Description: [ Horror mystery game shell with...   ]   │
│                                                         │
│  [ Code ] [ Preview ] [ Bindings ]                      │
│                                                         │
│  ┌─ Code ──────────────────────────────────────────┐    │
│  │ export default function Kochuu({ variables }) { │    │
│  │   var h = React.createElement;                  │    │
│  │   var api = useYumina();                        │    │
│  │   ...                                           │    │
│  │                                                 │    │
│  │ [Insert Snippet ▼] [AI: Modify...] [Format]     │    │
│  └─────────────────────────────────────────────────┘    │
│                                                         │
│  Compile: ✓ OK                                          │
│  [ Save ]  [ Delete ]                                   │
└─────────────────────────────────────────────────────────┘
```

- `[ AI: Modify... ]` button — opens a modal where the user describes a change ("add an audio volume slider") and the LLM patches the TSX
- `[ Bindings ]` tab — discovered automatically from the TSX (`api.variables["foo"]` → binds to variable `foo`) — shows "This panel reads: [list]. This panel mutates: [list]"

---

## 5. Studio editor integration

Studio editor uses dockable panels. Add two panels to `packages/app/src/features/studio/studio-page-catalog.ts`:

1. **UI Panels (list)** — like the simple editor gallery, but compact card layout for the side dock
2. **UI Panel Editor (detail)** — splits code + preview + bindings side-by-side when a panel is selected

**Dock layout suggestion** (studio users work on one panel at a time while playtesting):

```
┌─ Studio ───────────────────────────────────────────────────────┐
│ ┌─ UI Panels (list) ─┐  ┌─ Code: kochuu ──────┐  ┌─ Preview ─┐│
│ │ [+New] [AI Gen]    │  │ export default...   │  │            ││
│ │                    │  │                     │  │            ││
│ │ • kochuu           │  │                     │  │            ││
│ │ • clock-hud        │  │                     │  │            ││
│ │ • settings-modal   │  │                     │  │            ││
│ │ • inventory-side   │  │                     │  │            ││
│ └────────────────────┘  └─────────────────────┘  └────────────┘│
│                                                                │
│ ┌─ Playtest ──────────────────────────────────────────────────┐│
│ │ [Chat area + custom panel rendering live]                   ││
│ └─────────────────────────────────────────────────────────────┘│
└────────────────────────────────────────────────────────────────┘
```

**Benefits over the simple editor**:
- Edit code + see preview + see in-playtest simultaneously
- Hot-reload across all three when you save
- Debug variables panel can show which state the panel is reading

**Implementation**: register panels in `studio-page-catalog.ts` under `CHAT_PANEL_MENU_GROUPS` and `GAME_PANEL_MENU_GROUPS` → `display` group.

---

## 6. Live preview architecture

The preview pane is the biggest UX leverage point. Three increasingly-sophisticated implementations:

### P1 (MVP): Stub variables
- User-editable "mock variables" table next to the preview
- Preview compiles TSX with a fake `useYumina()` that returns the mock state
- `api.sendMessage(...)` becomes console.log; `api.setVariable(...)` mutates the mock state

Current compiler (`custom-component-renderer.tsx`) already supports this pattern — needs exposure in the editor UI.

### P2: Session replay
- Pick a real session from history → preview renders the panel as it looked at turn N of that session
- Scrubber to step through turns
- Shows "what your players actually saw"

### P3: Live session
- Live-connected to a playtest session
- Panel re-renders as LLM responses stream in, variables mutate, audio plays
- Makes studio editor feel like Unity's play mode

Ship P1 with v1. P2/P3 are stretch for the studio editor specifically.

---

## 7. Template library — what ships in v1

Store templates at `packages/app/src/features/editor/ui-panel-templates/*.tsx` as raw strings (like `app-component-snippets.ts` but with full panels). Each template has:

```ts
interface UIPanelTemplate {
  id: string;               // "kochuu-horror-mystery"
  name: string;             // "Horror Mystery Shell (Kochuu)"
  description: string;      // "Full game shell with character creation, map, roster, kill log..."
  surface: Surface;
  thumbnail: string;        // URL or data-URL
  tsxCode: string;
  requiredVariables?: Array<{ id: string; type: string; reason: string }>;
  suggestedRules?: Array<{ ... }>;
  suggestedAudioTracks?: Array<{ ... }>;
  tags: string[];           // ["mystery", "horror", "battle-royale"]
  complexity: "starter" | "intermediate" | "advanced";
}
```

When a template is applied:
- TSX gets inserted into the new panel
- Required variables are auto-added to the world (with user confirmation — "This template needs `survivors: number (40)`, `day-count: number (1)`, `location: string`. Add them?")
- Suggested rules get added as disabled rules (user enables the ones they want)
- Suggested audio tracks get surfaced with upload prompts

**Initial library (10 templates)** — first-party, universal shapes only. User-created games like Kochuu live in a community marketplace later, not shipped as templates.

1. **Advanced Game Shell** (game-shell, advanced) — reference implementation for chat-only games that replace the default shell. Demonstrates: inline SVG map, multi-phase transition keyframes, audio orchestration, session management, mobile responsive, time-reactive theming. Clean scaffold with placeholder content — NOT lifted from any specific user game.
2. **Minimal Chat Terminal** (game-shell, starter) — dark terminal aesthetic, single chat pane, no extras
3. **Classic RPG HUD** (hud-overlay, starter) — HP/MP bars + gold counter + level
4. **Inventory Sidebar** (sidebar, starter) — 4×N grid with drag-to-reorder
5. **Investigation Board** (modal, intermediate) — sortable clue gallery with topic filter — MVP for the Tingen pattern
6. **Day/Time Clock HUD** (hud-overlay, starter) — single-line top bar clock + phase color
7. **Relationship Panel** (sidebar, intermediate) — NPC list with affection bars
8. **Combat Abilities Bar** (hud-overlay, intermediate) — 1-9 hotkey bar with cooldowns
9. **Character Sheet Modal** (modal, intermediate) — stats + inventory + background
10. **Cutscene Overlay** (modal, advanced) — timeline-driven with fade + dialogue + image-embed support

The "Advanced Game Shell" gets pride of place: "~20KB scaffold, demonstrates every authoring primitive. Fork and modify. If you want to see what's possible at the extreme, browse the community marketplace."

---

## 8. AI-generation prompt design

The LLM authoring flow needs a carefully crafted prompt. Here's the shape:

### System prompt
```
You author TSX components for the Yumina game engine. Your components call
useYumina() to read game state and trigger actions. You output a single
default-exported React function component. No JSX — use React.createElement
with the `h` alias shortcut for compactness and to survive AI-round-trip
token limits.

## useYumina() API signature

[injected — full TypeScript interface from custom-component-renderer.tsx]

## World context

- **World name**: {{world.name}}
- **Variables** (typed): {{variables list with types + initial values}}
- **Audio tracks**: {{world.audioTracks[].id with descriptions}}
- **Rules / events available**: {{...}}
- **Other custom panels in this world**: {{customUI[].name + surface}}

## Output format

A single TSX file:
1. Starts with `export default function {{PascalCaseName}}({ variables }) {`
2. Uses var h = React.createElement at top
3. Uses var api = useYumina() at top
4. Uses React hooks (useState, useEffect, useRef) via direct reference — React is in scope
5. Inline styles as CSS-in-JS objects (no external CSS)
6. Mobile responsive via `window.innerWidth` + useState + resize listener pattern
7. Returns a single root element
8. No imports. Everything is in scope.

## Style guidance

- Keep total size under 10KB for starter templates
- Kochuu-style is fine for advanced asks; don't replicate all 60KB unless asked
- Use semantic color variables at the top (const C = { bg: "#...", text: "#..." })
- Comment sparingly — prefer readable code over extensive comments
```

### User prompt (templated)
```
Create a {{surface}} panel for my {{game-genre}} game.

Purpose: {{free-text description}}

This panel should:
- Read these variables: {{selected vars}}
- Call these actions on user interaction: {{selected actions}}
- [Optional] Use this template as a starting point: {{template id}}

{{Additional instructions if any}}

Output ONLY the TSX code, no prose, no markdown fences.
```

### Model choice
- Claude Sonnet 4.6 for starter templates (cheap, fast)
- Claude Opus 4.6 for advanced / Kochuu-style asks (quality matters more)
- Fallback: user can regenerate with a different prompt if unhappy

### Iteration flow
- First generation: full output
- "Modify" button: user types a change request → LLM diffs against current TSX → returns new version
- LLM never deletes working code unless explicitly asked

---

## 9. Data model changes

### CustomUIComponent (backward-compatible extensions)
```typescript
export interface CustomUIComponent {
  id: string;
  name: string;
  description: string;

  // Expand surface enum
  surface: "chat-bubble" | "game-shell" | "hud-overlay" | "modal" | "sidebar"
    // backward compat — load "message" → "chat-bubble", "app" → "game-shell"
    | "message" | "app";

  tsxCode: string;

  // NEW
  /** Icon (lucide name or emoji) shown in panel picker. */
  icon?: string;
  /** Preview image captured after successful compile+render. */
  previewImageUrl?: string;
  /** If from template, track the origin for future template updates. */
  fromTemplate?: string;
  /** If AI-generated, preserve the prompt so user can "regenerate with tweaks". */
  aiPrompt?: string;
  /** For modal/sidebar: which event opens this panel. */
  triggerEvent?: string;
  /** Docking side for sidebar. */
  dockSide?: "left" | "right";
  /** Width for sidebar (default "280px"). */
  dockWidth?: string;

  order: number;
  visible: boolean;
  updatedAt: string;
}
```

### Editor store (`packages/app/src/stores/editor.ts`)
- Existing `addCustomUI`, `updateCustomUI`, `removeCustomUI` actions work unchanged
- Add `addCustomUIFromTemplate(templateId, overrides?)`
- Add `generateCustomUIWithAI(prompt, surface, bindings)` — async, streams TSX in

### Surface rendering
`packages/app/src/features/game-play/` needs to be extended with a "slot" system:
- Game page renders `<GameShell>` (default or custom)
- Overlays mount as positioned children
- Modals mount at root with backdrop
- Sidebars mount via CSS grid alongside the shell

Implementation: a `<YuminaGameRoot>` component that queries the world's `customUI` list, groups by surface, and renders each appropriately. Current `<CustomComponentRenderer>` becomes reusable inside it.

---

## 10. Implementation phases

### Phase 1 — Data + simple editor (3-4 days)
- Expand `CustomUIComponent.surface` enum, backward-compat migrations
- New section `ui-panels.tsx` in simple editor, replace `components.tsx`
- Card gallery + editor view, preserves existing code editor
- Shipped with 3 templates (Blank Game Shell, Classic RPG HUD, Minimal Clock HUD)

### Phase 2 — Template library (2-3 days)
- Author the other 7 templates
- Import Kochuu (cleanup + annotation)
- Template picker UI
- Auto-add required variables with confirmation

### Phase 3 — AI generation (2-3 days)
- Backend endpoint: `POST /api/studio/generate-panel` → calls Anthropic
- System prompt + context injection
- Frontend wizard (purpose / surface / bindings / reference)
- Iteration via "Modify" button

### Phase 4 — Studio editor integration (2 days)
- Register UI Panels list + editor + preview panels in studio-page-catalog
- Wire dockable layout
- Integrate with playtest (live session preview)

### Phase 5 — Live preview + surface rendering (3-4 days)
- P1 preview (stub variables) in the editor view
- Surface rendering refactor: overlays / modals / sidebars mount alongside game-shell
- Event-triggered modal opening (`api.openModal(panelId)` — new API method)

### Phase 6 — Polish (2 days)
- Thumbnail auto-capture
- Snippet library expansion (15-20 entries)
- Onboarding ("your first panel in 60 seconds")
- Documentation + examples

**Total: ~12-15 days of focused work.** Phases 1-3 together (~1 week) already deliver the user-facing value.

---

## 11. Kochuu as the forcing function

Every design decision in this doc should be validated against: **"Can an author recreate Kochuu via this flow?"**

| Kochuu capability | Covered by |
|---|---|
| Full game shell replacement | `game-shell` surface + template |
| SVG interactive map | Inline in TSX — doesn't need engine support |
| Typewriter intro text | Inline hook pattern, should be in snippet library |
| Audio orchestration | `api.playAudio` + `api.stopAudio` + `chainTo` (exists) |
| Variable-reactive theming | `api.variables` reading (exists) |
| Character creation overlay | Template: "Character Creator Terminal" |
| Multi-phase cutscene | Template: "Cutscene Overlay" + `setTimeout` chains |
| Session management UI | `api.listSessions / createSession / deleteSession / navigate` (exist) |
| Message actions (copy/revert) | `api.revertToMessage` (exists) |
| Mobile responsive layout | Window-size state pattern (snippet) |
| Kill log grouping, roster filters | Plain React — no engine change |
| Paper texture + keyframe animations | CSS-in-JS injected into document head (snippet pattern) |

**Conclusion**: zero engine changes required to recreate Kochuu from scratch via this flow. The plumbing already exists; this feature just makes it accessible.

This also means **the feature is testable today in isolation**: we could ship Phases 1-3 without touching the engine core, the plugin architecture, or the Unity renderer. It's a pure editor + template + AI-gen feature.

---

## 12. Open questions

1. **Monaco vs. textarea** for the code editor. Monaco is ~2MB dep but has proper JSX/TSX syntax highlighting + autocomplete. Probably worth it for this feature.
2. **Preview isolation**. Current preview is a sandboxed iframe for message surface, full-access for app surface. Modal/sidebar/hud should match app surface rules (same-origin, access to styles). This is already handled — no change needed, but confirm before shipping.
3. **Template versioning**. When we update a template, do we offer to migrate existing panels that were forked from it? Probably "no" for v1 — templates are one-shot copies.
4. **AI generation cost**. Opus calls per panel are ~$0.02-0.05. At scale this matters. Probably: free for first 3 generations per world per month, then require plan upgrade. Same mechanism as the existing Yumina Power budget.
5. **How does the TSX find React + hooks in scope?** Current compiler injects `React` into the `new Function()` closure. We need to also inject `useState`, `useEffect`, `useRef`, `useCallback`, `useMemo` as top-level names, or users have to destructure `React.useState` every time. Kochuu uses the former pattern. Standardize on injected top-level hooks.
6. **Template discoverability across worlds**. Should templates be world-scoped (per-world library) or global (shared across all worlds)? v1: global, curated. v2: world-scoped + user-published templates.
7. **Cross-panel state**. Multiple panels on the same page both read `api.variables.clock` — is there a risk of state desync? The `YuminaContext` pattern handles this — all panels read from the same context, so they always see the same state. No issue.
8. **Panel z-ordering**. Modal > hud-overlay > game-shell > sidebar (aside). Hardcode this for v1; allow author override via `zIndex` field later.
9. **Multiplayer** — do custom panels get different data per player? Today `useYumina().personalVariables` already exposes per-player state. Templates need to be designed to use it correctly. Include in the AI system prompt.
10. **Saves / state machine**. When a world includes a `game-shell` panel, should the default shell be hidden? Probably: yes, if `surface === "game-shell"` and `visible === true`, replace the default chat view entirely.

---

## 13. Quick preview of the initial experience (Phase 1 ship)

**Day 1 — Author opens simple editor, clicks "UI Panels"**:
- Empty state: "You don't have any UI panels yet. Pick a template to get started, describe one for the AI to generate, or paste your own."
- Three buttons: `Browse Templates` / `AI Generate` / `Paste Custom`

**Day 1 — Picks "Browse Templates", selects "Minimal Clock HUD"**:
- Dialog: "This template uses variables `day-count` and `time-period`. Add them to your world? [✓ Auto-add with defaults]"
- Panel is created. Editor view opens with TSX + preview showing "Day 1, morning".

**Day 2 — Clicks AI Generate, types "mystery investigation board"**:
- Wizard fills in: surface=modal, bindings=["clues", "suspects"], reference=(Investigation Board template)
- LLM generates 3KB TSX. Preview works. Author edits description. Saves.

**Day 3 — Clicks "+ Add Panel" again, picks "Paste Custom"**:
- Drops a Kochuu-shaped TSX in. Compile errors show inline. Fixes them. Saves.

All three panels are now visible in the game view — HUD on top, modal on trigger, full shell replacing the default chat view.

Compared to today (2026-04-20), this is maybe ~5% of the current visible product surface but probably the single most leveraged UX improvement we could make for authors.
