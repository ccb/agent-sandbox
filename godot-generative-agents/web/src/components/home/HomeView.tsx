// ReactNode is only used by the Icon component below, which is commented out
// together with the link buttons that use it. Re-enable this import when you
// re-enable that block.
// import type { ReactNode } from "react";
import { lazy, type MouseEvent, Suspense, useEffect, useRef, useState } from "react";
import { GodotCanvas } from "../GodotCanvas";
import { CaseStudySection } from "./CaseStudySection";
import { CodeRef } from "./CodeRef";
import { CostSection } from "./CostSection";
import { ImplementationSection } from "./ImplementationSection";
import { ReflectionsSection } from "./ReflectionsSection";
import { TeX } from "./TeX";
import "./home.css";

// Lazy: the visualizer pulls in Cytoscape (~430 kB), and it only mounts when a
// reader asks for it (see PromptChainFigure), so that weight never lands on a
// visitor who just reads the page.
const PromptChainView = lazy(() =>
  import("../promptviz/PromptChainView").then((m) => ({ default: m.PromptChainView })),
);

/**
 * The viewer's sidebar buttons, explained under the demo — their words live in
 * Godot tooltips, which a reader watching the embed never sees.
 *
 * `icon` files are the viewer's own glyphs, exported from the panel that draws
 * them by `godot/tools/export_sidebar_icons.gd` (so they can't drift); `legend.
 * test.ts` pins each one to a file that exists. `glyph` rows are the two buttons
 * the sidebar itself draws as text, and Track's glyph is its own label, so that
 * row skips the bold repeat. Zoom/reset/home stay in the prose above — this is a
 * caption, not the manual.
 */
export const SIDEBAR_LEGEND: {
  icon?: string;
  glyph?: string;
  label?: string;
  text: string;
}[] = [
  { icon: "heatmap.png", label: "Heatmap", text: "where the agents have spent their time so far" },
  { icon: "social-graph.png", label: "Social graph", text: "who has talked to whom" },
  {
    icon: "day-plans.png",
    label: "Day plans",
    text: "each agent's plan against what actually happened",
  },
  {
    icon: "dialogue-log.png",
    label: "Dialogue log",
    text: "every line the agents have said so far, timestamped — bubbles go fast; this doesn't",
  },
  {
    glyph: "ⓘ",
    label: "State Details",
    text: "one agent's memories, current plan and relationships",
  },
  { glyph: "Track", text: "locks the camera to an agent and follows them" },
];

/**
 * The Godot replay, embedded where the "Open the replay demo" button used to
 * link out to a standalone `#game` page. Like the prompt-chain figure it stays
 * behind a click — the engine is a multi-megabyte WebAssembly download that a
 * reader hasn't asked for — and it enlarges into an overlay.
 *
 * Unlike that figure, enlarging here is a CSS class rather than a `<dialog>`
 * with a second mount: there can only ever be ONE engine instance (one `#canvas`
 * and one WASM heap), and the canvas must never unmount or collapse to zero
 * size, since `canvasResizePolicy: 2` would shrink its framebuffer with it. So
 * the same frame grows in place and the engine keeps running through it.
 *
 * The whole figure steps aside for one of the two notes beneath it (#958) when
 * the window is too narrow, or when the pointer is touch-primary — a different
 * reason and a different message each. See the gate at the foot of home.css for
 * why, and for why the swap is CSS rather than a `matchMedia` gate in here.
 */
function ReplayFigure() {
  const [shown, setShown] = useState(false);
  const [enlarged, setEnlarged] = useState(false);

  // Esc closes the overlay — what `<dialog>` gives the chain figure for free.
  useEffect(() => {
    if (!enlarged) return;
    const onKey = (e: KeyboardEvent) => {
      if (e.key === "Escape") setEnlarged(false);
    };
    document.addEventListener("keydown", onKey);
    return () => document.removeEventListener("keydown", onKey);
  }, [enlarged]);

  return (
    <>
      <figure className={`nrf-figure nrf-figure--replay${enlarged ? " is-enlarged" : ""}`}>
        {shown ? (
          <>
            {enlarged && (
              <button
                type="button"
                className="nrf-scrim"
                onClick={() => setEnlarged(false)}
                aria-label="Close the enlarged replay"
              />
            )}
            <div className="nrf-figure-frame">
              <GodotCanvas />
              <button
                type="button"
                className="nrf-figure-expand"
                onClick={() => setEnlarged((on) => !on)}
                aria-label={enlarged ? "Shrink the replay" : "Enlarge the replay"}
                title={enlarged ? "Shrink" : "Enlarge"}
              >
                {enlarged ? "✕" : "⤢"}
              </button>
            </div>
          </>
        ) : (
          <button
            type="button"
            className="nrf-figure-frame nrf-figure-idle nrf-figure-button"
            onClick={() => setShown(true)}
          >
            Open the replay demo →
          </button>
        )}
        <figcaption className="nrf-figcaption">
          A full twelve-hour run, replayed deterministically in the browser — the same Godot viewer
          that runs natively, exported to WebAssembly. Drag to pan and scroll to zoom.
          {/* <details> brings the disclosure arrow, the click/Enter/Space handling and the
              expanded/collapsed state with it — none of which is worth reimplementing in
              React. Closed by default — a reader who wants the legend can open it. */}
          <details className="nrf-legend-toggle">
            <summary>What the sidebar's buttons do</summary>
            <ul className="nrf-legend">
              {SIDEBAR_LEGEND.map((entry) => (
                <li key={entry.label ?? entry.glyph}>
                  {entry.icon ? (
                    <img
                      className="nrf-legend-icon"
                      src={`${import.meta.env.BASE_URL}sidebar-icons/${entry.icon}`}
                      alt=""
                    />
                  ) : (
                    <span className="nrf-legend-glyph">{entry.glyph}</span>
                  )}
                  <span>
                    {entry.label ? (
                      <>
                        <b>{entry.label}</b> — {entry.text}
                      </>
                    ) : (
                      entry.text
                    )}
                  </span>
                </li>
              ))}
            </ul>
          </details>
        </figcaption>
      </figure>
      {/* The two stand-ins for everything above. Both always rendered; the gate in
          home.css shows exactly one of them, or neither, never with the figure. */}
      <p className="nrf-replay-note nrf-replay-note--narrow">
        This window is too narrow to show the replay — widen it and the demo appears here.
      </p>
      <p className="nrf-replay-note nrf-replay-note--touch">
        Open this page on a desktop browser to watch the replay.
      </p>
    </>
  );
}

/**
 * The prompt-chain visualizer, framed as a figure. It used to be its own page
 * (`#prompts`); folding it in here costs nothing on load because it stays
 * behind a click — the diagram is an aside to the architecture section above,
 * not something every visitor needs fetched.
 */
function PromptChainFigure() {
  const [shown, setShown] = useState(false);
  const [expanded, setExpanded] = useState(false);
  const dialogRef = useRef<HTMLDialogElement>(null);

  // A native <dialog> brings the backdrop, Esc-to-close, focus trap and top-layer
  // stacking with it, so the only state here is whether to mount the (heavy)
  // second graph — `onClose` covers every way the dialog can be dismissed.
  const expand = () => {
    setExpanded(true);
    dialogRef.current?.showModal();
  };

  return (
    <>
      <figure className="nrf-figure nrf-figure--chain">
        {shown ? (
          <Suspense fallback={<div className="nrf-figure-frame nrf-figure-idle">Loading…</div>}>
            <div className="nrf-figure-frame">
              <PromptChainView />
              <button
                type="button"
                className="nrf-figure-expand"
                onClick={expand}
                aria-label="Enlarge the diagram"
                title="Enlarge"
              >
                ⤢
              </button>
            </div>
          </Suspense>
        ) : (
          <button
            type="button"
            className="nrf-figure-frame nrf-figure-idle nrf-figure-button"
            onClick={() => setShown(true)}
          >
            Load the interactive diagram
          </button>
        )}
        <figcaption className="nrf-figcaption">
          Each node is one step of a decision; color marks whether it calls the model or gates it
          without one. Click a node to read the prompt template behind it.
        </figcaption>
      </figure>

      {/* biome-ignore lint/a11y/useKeyWithClickEvents: the keyboard path is <dialog>'s own Esc handler, which fires onClose */}
      <dialog
        ref={dialogRef}
        className="nrf-modal"
        onClose={() => setExpanded(false)}
        // Clicking the backdrop targets the dialog itself; anything inside the
        // body stops short of it.
        onClick={(e) => {
          if (e.target === dialogRef.current) dialogRef.current?.close();
        }}
      >
        <div className="nrf-modal-body">
          {expanded && (
            <Suspense fallback={<div className="nrf-modal-loading">Loading…</div>}>
              <PromptChainView />
            </Suspense>
          )}
          <button
            type="button"
            className="nrf-modal-close"
            onClick={() => dialogRef.current?.close()}
            aria-label="Close the enlarged diagram"
            title="Close"
          >
            ✕
          </button>
        </div>
      </dialog>
    </>
  );
}

/**
 * Every formula on the page, in one place. JSX below references these by name,
 * and `formulas.test.ts` renders each one to catch a malformed literal before
 * it reaches the site.
 */
export const TEX = {
  // The world and its clock
  tileSelf: "p",
  tileOther: "p'",
  radius: "r = 8",
  perception: String.raw`\lVert p - p' \rVert_\infty = \max\bigl(|\Delta x|, |\Delta y|\bigr) \le r`,

  // Memory and retrieval
  query: "q",
  tick: "t",
  retrieval: String.raw`s(m, q, t) \;=\; \alpha_{\mathrm{rec}}\, \gamma^{\,t - a(m)} \;+\; \alpha_{\mathrm{imp}}\, \frac{i(m)}{10} \;+\; \alpha_{\mathrm{rel}}\, \mathrm{rel}(q, m)`,
  decay: String.raw`\gamma = 0.95`,
  lastAccess: "a(m)",
  importanceRange: String.raw`i(m) \in [1, 10]`,
  weights: String.raw`\alpha_{\mathrm{rec}} = \alpha_{\mathrm{imp}} = \alpha_{\mathrm{rel}} = 1`,
  unitRange: "[0, 1]",
  cosine: String.raw`\mathrm{rel}(q, m) = \tfrac{1}{2}\bigl(1 + \cos(v_q, v_m)\bigr)`,

  // Importance and reflection
  threshold: String.raw`\theta = 30`,
  reflection: String.raw`\sum_{m \,\in\, M_{\text{new}}} i(m) \;\ge\; \theta`,
  newMemories: String.raw`M_{\text{new}}`,

  // Conversations
  talkCount: "n",
  cooldown: String.raw`\min(n, 3) \times 90`,

  // Acknowledgements
  colRow: String.raw`(x, y) = (\text{col}, \text{row})`,
};

// The Paper / arXiv / Video / Code buttons in the hero are commented out until
// the video (#881) and the public repository (#884, scheduled 2026-08-14)
// exist. Their inline SVG line-icons are commented out here along with them,
// since nothing else uses them. (The original Nerfies template pulls Font
// Awesome / Academicons from a CDN, which COOP/COEP would block — hence
// inlining.) Re-enable this block and the buttons together.
/*
function Icon({ children }: { children: ReactNode }) {
  return (
    <svg
      width="16"
      height="16"
      viewBox="0 0 24 24"
      fill="none"
      stroke="currentColor"
      strokeWidth="2"
      strokeLinecap="round"
      strokeLinejoin="round"
      aria-hidden="true"
    >
      {children}
    </svg>
  );
}

const PaperIcon = (
  <Icon>
    <path d="M14 3H7a2 2 0 0 0-2 2v14a2 2 0 0 0 2 2h10a2 2 0 0 0 2-2V8z" />
    <path d="M14 3v5h5" />
    <line x1="9" y1="13" x2="15" y2="13" />
    <line x1="9" y1="17" x2="15" y2="17" />
  </Icon>
);
const ArxivIcon = (
  <Icon>
    <path d="M22 10 12 5 2 10l10 5 10-5z" />
    <path d="M6 12v5c0 1 2.7 3 6 3s6-2 6-3v-5" />
  </Icon>
);
const VideoIcon = (
  <Icon>
    <circle cx="12" cy="12" r="9" />
    <polygon points="10 8 16 12 10 16" fill="currentColor" stroke="currentColor" />
  </Icon>
);
const CodeIcon = (
  <Icon>
    <path d="m9 18-6-6 6-6" />
    <path d="m15 6 6 6-6 6" />
  </Icon>
);
*/

// The repository this companion lives in. Swap for the standalone public repo
// when it publishes (#884).
const REPO_URL = "https://github.com/ccb/agent-sandbox";

/**
 * The contents nav, in page order — `id` matches the element it points at (a
 * section for the demo, otherwise the heading itself) and `sub` marks a
 * subsection of the entry above it. `toc.test.ts` pins every id to a real target
 * in this file. Keep the order in sync with the DOM: the scroll-spy below relies
 * on it.
 */
export const TOC: { id: string; label: string; sub?: true }[] = [
  { id: "demo", label: "Demo" },
  { id: "abstract", label: "Abstract" },
  { id: "architecture", label: "How an agent works" },
  { id: "world", label: "The world and its clock", sub: true },
  { id: "memory", label: "Memory and retrieval", sub: true },
  { id: "importance", label: "Importance and reflection", sub: true },
  { id: "planning", label: "Planning", sub: true },
  { id: "conversations", label: "Conversations", sub: true },
  { id: "action-gate", label: "The action gate", sub: true },
  { id: "optional", label: "What's on by default", sub: true },
  { id: "decision", label: "Inside a decision" },
  { id: "case-study", label: "One day, up close" },
  { id: "case-cast", label: "The cast", sub: true },
  { id: "case-dialogs", label: "Three conversations", sub: true },
  { id: "case-goals", label: "Changing plans", sub: true },
  { id: "case-memory", label: "Memory at work", sub: true },
  { id: "case-verdict", label: "What holds up", sub: true },
  { id: "implementation", label: "Implementation" },
  { id: "the-gate", label: "The precondition gate", sub: true },
  { id: "verb-to-tool", label: "From verb to tool", sub: true },
  { id: "your-own-verb", label: "Adding your own verb", sub: true },
  { id: "cost", label: "What a day costs" },
  { id: "reflections", label: "Coding agents as research instruments" },
  { id: "limitations", label: "Limitations" },
  { id: "acknowledgements", label: "Acknowledgements" },
  { id: "assets", label: "Asset packs" },
  { id: "references", label: "References" },
  { id: "BibTeX", label: "BibTeX" },
];

// How long a clicked entry outranks the scroll-spy — long enough to cover the
// smooth scroll it started (browsers pick their own duration; ~500ms is typical).
const JUMP_PIN_MS = 1000;

/**
 * A sticky table of contents in the page's left margin. Clicking scrolls the
 * target into view directly instead of following the `href`, so the URL keeps no
 * `#hash`; the `href` stays for what a real link gives us (focus, Enter,
 * open-in-new-tab).
 */
function TableOfContents() {
  const [active, setActive] = useState("");
  // A clicked entry wins over the spy for a moment: the smooth scroll drags other
  // headings through the band on its way, and the last entries can never win the
  // band race at all (see below), so their highlight is the click's to set.
  const pinnedUntil = useRef(0);

  useEffect(() => {
    // Active = the last target to cross a band across the top fifth of the
    // viewport. Nothing in the band (mid-way through a long section) leaves the
    // previous entry lit, which is what a reader expects. `.view-home` fills the
    // viewport exactly, so the default root is the right one even though the
    // document itself never scrolls.
    //
    // ponytail: a target in the final viewport (References, BibTeX) can never
    // reach that band — the container runs out of scroll room first — so
    // free-scrolling to the very bottom leaves the previous entry lit. Clicking
    // them is covered by the pin; add a scrolled-to-the-end rule if the scroll
    // path starts to matter.
    const inBand = new Map<string, boolean>();
    const observer = new IntersectionObserver(
      (entries) => {
        for (const entry of entries) inBand.set(entry.target.id, entry.isIntersecting);
        if (Date.now() < pinnedUntil.current) return;
        const first = TOC.find((s) => inBand.get(s.id));
        if (first) setActive(first.id);
      },
      { rootMargin: "0px 0px -80% 0px" },
    );
    for (const { id } of TOC) {
      const el = document.getElementById(id);
      if (el) observer.observe(el);
    }
    return () => observer.disconnect();
  }, []);

  const jump = (event: MouseEvent<HTMLAnchorElement>, id: string) => {
    const target = document.getElementById(id);
    if (!target) return; // nothing to scroll to: let the href do whatever it does
    event.preventDefault();
    target.scrollIntoView({
      // Chrome honours prefers-reduced-motion for CSS smooth scrolling but not
      // for a behavior passed here, so ask for the right one.
      behavior: window.matchMedia("(prefers-reduced-motion: reduce)").matches ? "auto" : "smooth",
      block: "start",
    });
    setActive(id);
    pinnedUntil.current = Date.now() + JUMP_PIN_MS;
  };

  return (
    <nav className="nrf-toc" aria-label="Table of contents">
      <p className="nrf-toc-heading">Contents</p>
      <ul className="nrf-toc-list">
        {TOC.map((entry) => (
          <li key={entry.id}>
            <a
              href={`#${entry.id}`}
              onClick={(e) => jump(e, entry.id)}
              className={`nrf-toc-link${entry.sub ? " is-sub" : ""}${
                active === entry.id ? " is-active" : ""
              }`}
              aria-current={active === entry.id ? "true" : undefined}
            >
              {entry.label}
            </a>
          </li>
        ))}
      </ul>
    </nav>
  );
}

/**
 * The public landing page (#879), styled after the Nerfies academic
 * project-page template (https://github.com/nerfies/nerfies.github.io).
 *
 * The narrative below covers the parts of the project that are settled:
 * credits, abstract, the agent architecture and its formalizations, the
 * showcase-run case study, limitations, acknowledgements, and citations.
 * Still to land here:
 *   TODO(#881): the demo video embed in the teaser slot.
 *   TODO(#880): the "Run locally" guide and its nav entry.
 */
export function HomeView() {
  return (
    <div className="nrf">
      <TableOfContents />

      {/* ===== Hero: title, authors, affiliations, links ===== */}
      <section className="nrf-hero">
        <div className="nrf-hero-body">
          <div className="nrf-container nrf-centered">
            <h1 className="nrf-title nrf-title-1">
              Penn Campus: Generative Agents in a Simulated World
            </h1>
            <p className="nrf-venue">
              PURM 2026 · University of Pennsylvania
              {/* Decorative: the line right beside it already names the
                  university, so alt is empty rather than repeating it. */}
              <img
                className="nrf-shield"
                src={`${import.meta.env.BASE_URL}upenn-shield.svg`}
                alt=""
                width={144}
                height={161}
              />
            </p>

            <div className="nrf-authors">
              <span className="nrf-author-block">
                <a href="https://github.com/aking526">Alistair King</a>,
              </span>{" "}
              <span className="nrf-author-block">
                <a href="https://github.com/0frankie">Frankie L</a>
              </span>
            </div>

            {/* Everyone shares one affiliation, and the venue line above already
                names it — so no affiliation line and no superscripts. */}
            <div className="nrf-advisor">
              Advised by <a href="https://www.cis.upenn.edu/~ccb/">Chris Callison-Burch</a>
            </div>

            {/* Paper / arXiv / Video / Code links — re-enable (along with the
                Icon block at the top of this file) once the video (#881) and
                public repository (#884) URLs exist.

            <div className="nrf-links">
              <a className="nrf-button" href="#">
                {PaperIcon}
                <span>Paper</span>
              </a>
              <a className="nrf-button" href="#">
                {ArxivIcon}
                <span>arXiv</span>
              </a>
              <a className="nrf-button" href="#">
                {VideoIcon}
                <span>Video</span>
              </a>
              <a className="nrf-button" href={REPO_URL} target="_blank" rel="noreferrer">
                {CodeIcon}
                <span>Code</span>
              </a>
            </div>
            */}
          </div>
        </div>
      </section>

      {/* ===== Teaser: summary + the replay itself (it used to be a button linking
          out to a standalone #game page) =====
          TODO(#881): embed the captioned demo video here once it's published.
          TODO(#878): swap in a still from the selected showcase run meanwhile. */}
      <section className="nrf-teaser" id="demo">
        <div className="nrf-container">
          <p className="nrf-subtitle nrf-centered nrf-teaser-cap">
            Five LLM-driven agents plan, remember, and converse their way through a twelve-hour day
            on a faithful tile map of Penn's campus — and every run replays deterministically, right
            in your browser.
          </p>
          <ReplayFigure />
        </div>
      </section>

      {/* ===== Abstract ===== */}
      <section className="nrf-section">
        <div className="nrf-container">
          <div className="nrf-narrow nrf-centered nrf-abstract">
            <h2 className="nrf-title nrf-title-3" id="abstract">
              Abstract
            </h2>
            <div className="nrf-content nrf-justified">
              <p>
                We place five generative agents — characters driven by a large language model, with
                persistent memory, daily plans, and the ability to hold conversations — on a tile
                map of the University of Pennsylvania's campus derived from real OpenStreetMap data.
                Over a simulated twelve-hour day the agents walk between real campus places, pursue
                individually authored goals, and strike up conversations whose outcomes feed back
                into their plans and memories, following the memory–reflection–planning architecture
                of Park et al.'s <em>Generative Agents</em>. The simulation is built on a classical
                text-adventure engine: every action an agent takes — whether proposed by a language
                model or by a scripted schedule — must pass the same precondition/effect gate before
                it can change the world, so the model never mutates state directly. Each run records
                its LLM traffic and world seed, which makes any run replayable deterministically in
                a Godot viewer, natively or in the browser via WebAssembly.
              </p>
            </div>
          </div>
        </div>
      </section>

      {/* ===== Architecture ===== */}
      <section className="nrf-section">
        <div className="nrf-container">
          <div className="nrf-narrow">
            <h2 className="nrf-title nrf-title-3 nrf-centered" id="architecture">
              How an agent works
            </h2>
            <div className="nrf-content nrf-justified">
              <h3 className="nrf-title nrf-title-4" id="world">
                The world and its clock
              </h3>
              <p>
                The world advances in discrete ticks of ten in-game seconds, so an hour is 360 ticks
                and the showcase's twelve-hour day is 4,320. On each tick, every agent that is not
                mid-walk, settled into an activity, or mid-conversation makes a decision; decisions
                are then resolved in a fixed order, so two agents contending for the same resource
                settle deterministically.
                <CodeRef>
                  <code>step</code>, in <code>backend/run_simulation.py</code>
                </CodeRef>{" "}
                An agent perceives the world through a limited window: it observes a thing at tile{" "}
                <TeX>{TEX.tileOther}</TeX> from its own tile <TeX>{TEX.tileSelf}</TeX> only when the
                two are within a Chebyshev radius <TeX>{TEX.radius}</TeX>,
              </p>
              <TeX display>{TEX.perception}</TeX>
              <p>
                and anything newly entering that window — an event, or another agent's arrival —
                becomes an observation in its memory stream.
                <CodeRef>
                  <code>TiledGame.can_perceive</code>, in <code>backend/tiled_game.py</code>
                </CodeRef>
              </p>

              <h3 className="nrf-title nrf-title-4" id="memory">
                Memory and retrieval
              </h3>
              <p>
                Everything an agent experiences — observations, its own actions and failures, lines
                of dialogue, plans, reflections — is a timestamped record with an importance score.
                When the agent must decide, it cannot see the whole stream; it retrieves the records
                that score highest under a weighted sum of recency, importance, and relevance to the
                current situation <TeX>{TEX.query}</TeX> at tick <TeX>{TEX.tick}</TeX>:
                <CodeRef>
                  <code>AgentMemory.retrieve</code>, in <code>text_adventure_games/memory.py</code>
                </CodeRef>
              </p>
              <TeX display>{TEX.retrieval}</TeX>
              <p>
                with decay <TeX>{TEX.decay}</TeX> per tick since the record was last accessed (
                <TeX>{TEX.lastAccess}</TeX>), importance <TeX>{TEX.importanceRange}</TeX> normalized
                to unit range, and all weights <TeX>{TEX.weights}</TeX>. Relevance is keyword
                overlap between the query and the record by default; when an embedding backend is
                configured it becomes cosine similarity rescaled to the same{" "}
                <TeX>{TEX.unitRange}</TeX> range, <TeX>{TEX.cosine}</TeX>. The top six records
                within a budget of roughly 800 tokens are surfaced into the decision prompt.
                Retrieval refreshes a record's last-accessed time, so memories the agent keeps
                returning to stay warm while the rest fade. Every constant here — the three weights,
                the decay, the record count, the budget — is a configuration field rather than a
                hard-coded number.
                <CodeRef>
                  <code>RetrievalConfig</code>, in <code>backend/sim_config.py</code>
                </CodeRef>
              </p>
              <p>
                That retrieval happens on every decision, whether or not the agent asks for it. An
                agent may <em>additionally</em> be handed tools to query its own memory, beliefs and
                plan directly — <code>recall</code>, <code>query_knowledge</code> and{" "}
                <code>read_plan</code>.
                <CodeRef>
                  <code>cognition_toolset</code>, in <code>text_adventure_games/npc.py</code>
                </CodeRef>{" "}
                Those are a second, opt-in channel layered on top of the retrieved records, not a
                replacement for them: when they are enabled the same top-six paste still goes into
                the prompt, and the agent's own lookups are extra calls on top.
              </p>

              <h3 className="nrf-title nrf-title-4" id="importance">
                Importance and reflection
              </h3>
              <p>
                New memories are rated for poignancy by the language model on a 1 (utterly mundane)
                to 10 (momentous) scale, in one batched, temperature-zero call per agent per tick.
                <CodeRef>
                  <code>score_new_memories</code>, in <code>backend/cognition.py</code>
                </CodeRef>{" "}
                A few signals the model cannot infer from text — like falling ill, or a commitment
                made in conversation — carry fixed scores instead. Reflection is triggered by
                accumulated salience rather than by the clock: once the summed importance of the
                memories <TeX>{TEX.newMemories}</TeX> accrued since the last reflection crosses a
                threshold <TeX>{TEX.threshold}</TeX>,
              </p>
              <TeX display>{TEX.reflection}</TeX>
              <p>
                the agent asks itself up to three salient questions about its recent experience,
                answers each from retrieved evidence, and writes the inferences back into memory as
                higher-level reflections that cite the records they were drawn from — so later
                decisions can build on conclusions, not just raw observations.
                <CodeRef>
                  <code>should_reflect</code> and <code>reflect</code>, in{" "}
                  <code>text_adventure_games/reflection.py</code>
                </CodeRef>
              </p>

              <h3 className="nrf-title nrf-title-4" id="planning">
                Planning
              </h3>
              <p>
                Each agent starts its day by decomposing intentions hierarchically: a day outline,
                refined into hourly blocks, refined into minute-level stops — each stop a real
                place, an activity, and a duration — one model call per altitude.
                <CodeRef>
                  <code>LLMPlanner</code>, in <code>backend/planner.py</code>
                </CodeRef>{" "}
                Proposed stops are validated against the actual map, so a hallucinated location is
                dropped before it can reach the world.
                <CodeRef>
                  <code>validate_stops</code>, in <code>text_adventure_games/planning.py</code>
                </CodeRef>{" "}
                Plans are living documents: an agent revises when it falls behind schedule, when an
                action is rejected by the world, when a conversation changes its commitments, or
                when it reacts to something it perceives — and a revision may only rewrite the tail
                of the day, never the stops already lived.
                <CodeRef>
                  <code>maybe_revise_plan</code>, in <code>backend/cognition.py</code>
                </CodeRef>
              </p>

              <h3 className="nrf-title nrf-title-4" id="conversations">
                Conversations
              </h3>
              <p>
                When two agents are close, free, and interested, they open a conversation that
                unfolds one line per tick, up to six exchanges — dialogue takes simulated time
                rather than resolving instantly, one line at a time.
                <CodeRef>
                  <code>exchange</code>, in <code>text_adventure_games/conversation.py</code>
                </CodeRef>{" "}
                Afterwards each participant distills an outcome: what was agreed, what it means for
                their relationship, and whether their plans should change.
                <CodeRef>
                  <code>apply_conversation_outcome</code>, in <code>backend/cognition.py</code>
                </CodeRef>{" "}
                Commitments and relationship notes are written to memory with high importance so
                they survive retrieval competition. A pair that has already talked{" "}
                <TeX>{TEX.talkCount}</TeX> times waits <TeX>{TEX.cooldown}</TeX> ticks before
                starting again, which keeps two friendly agents from looping the same greeting all
                day.
              </p>

              <h3 className="nrf-title nrf-title-4" id="action-gate">
                The action gate
              </h3>
              <p>
                Every decision — whether it arrives as a typed tool call from the model or as plain
                text — is reassembled into a command and pushed through the engine's parser, where
                the action's preconditions are checked before its effects apply.
                <CodeRef>
                  <code>Parser.parse_command</code>, in <code>text_adventure_games/parsing.py</code>
                </CodeRef>{" "}
                That is the only route into the world; the model never edits world state. A rejected
                action is not silent either: it becomes a failure memory and can trigger a plan
                revision, so agents learn from what the world refuses. The five lines that enforce
                this, and a real verb passing through them, are below in <em>Implementation</em>.
              </p>

              <h3 className="nrf-title nrf-title-4" id="optional">
                What's on by default
              </h3>
              <p>
                Not all of the above is always running, and the difference matters for reading the
                costs below. <strong>Four things are unconditional:</strong> the tick loop,
                perception, the memory stream with its retrieval, and the precondition gate. They
                need no language model at all — which is what lets the bundled replay bake and the
                test suite run offline, for free, and still exercise real perception and real
                retrieval. <strong>The generative faculties are gated on a real provider:</strong>{" "}
                conversation, reflection, importance scoring, and model-written plans exist only
                when one is attached. Without it the agents walk an authored day through a
                deterministic mock brain
                <CodeRef>
                  <code>ScheduleMockClient</code>, in <code>backend/cognition.py</code>
                </CodeRef>{" "}
                and never speak to each other. <strong>The rest are knobs that default off:</strong>{" "}
                the cognition tools described above, embedding-based relevance (unset means the
                keyword overlap), and reactive interruption, which lets a perception cut into an
                activity mid-stop. Each is a field in the same configuration object as the retrieval
                constants, so a run is described by its config rather than by a code change.
              </p>
              <p>
                The showcase run enables most of them: a real provider with model tiering — a larger
                model for the deliberative roles, a cheaper one for the conversational ones —
                model-written plans, medium reasoning effort, cognition tools on, keyword relevance,
                and a fixed seed. Reactive interruption is off, so of the four revision triggers
                listed above the perception-driven one never fires; plans in this run change from
                falling behind, from a refused action, or from a conversation.
              </p>
            </div>
          </div>
        </div>
      </section>

      {/* ===== Prompt chains (folded in from the retired #prompts page) ===== */}
      <section className="nrf-section">
        <div className="nrf-container">
          <div className="nrf-narrow">
            <h2 className="nrf-title nrf-title-3 nrf-centered" id="decision">
              Inside a decision
            </h2>
            <div className="nrf-content nrf-justified">
              <p>
                None of the steps above is a single monolithic prompt. One decision is a chain: the
                agent's observation and retrieved memories are assembled into context, the model is
                asked for an action, its answer is parsed back into a command, and the world's
                precondition gate has the last word. The diagram below is generated from the
                engine's own chain specifications and prompt templates, so it stays in step with the
                code rather than being drawn by hand.
              </p>
            </div>
            <PromptChainFigure />
            <p className="nrf-figure-note">
              The interactive diagram needs a wider screen than this one.
            </p>
          </div>
        </div>
      </section>

      {/* ===== Case study: the showcase run, up close (#878) ===== */}
      <CaseStudySection />

      {/* ===== Implementation: the engine underneath ===== */}
      <ImplementationSection />

      {/* ===== Cost: the #921 cost-scaling measurements ===== */}
      <CostSection />

      {/* ===== Reflections: building this with a coding agent ===== */}
      <ReflectionsSection />

      {/* ===== Limitations ===== */}
      <section className="nrf-section">
        <div className="nrf-container">
          <div className="nrf-narrow">
            <h2 className="nrf-title nrf-title-3 nrf-centered" id="limitations">
              Limitations
            </h2>
            <div className="nrf-content nrf-justified">
              <p>
                This is a small research prototype, and it is honest about it. As described above,
                the generative machinery runs only when a real language-model provider is attached;
                the offline default is a deterministic mock brain replaying authored schedules,
                which we use for testing and byte-identical replay baking — so a free run is a
                weaker thing than the one shown here. Reproducibility comes from recording each
                run's LLM traffic and world seed and replaying both, not from seeding the model
                itself. And the scale is deliberately modest — five agents, one campus, one
                simulated day — so the behaviors you'll see are believable vignettes, not validated
                claims about human behavior.
              </p>
            </div>
          </div>
        </div>
      </section>

      {/* ===== Acknowledgements ===== */}
      <section className="nrf-section">
        <div className="nrf-container">
          <div className="nrf-narrow">
            <h2 className="nrf-title nrf-title-3 nrf-centered" id="acknowledgements">
              Acknowledgements
            </h2>
            <div className="nrf-content nrf-justified">
              <p>
                This project was carried out through the Penn Undergraduate Research Mentoring
                Program (PURM), advised by{" "}
                <a href="https://www.cis.upenn.edu/~ccb/">Chris Callison-Burch</a>. It builds on the{" "}
                <code>agent-sandbox</code> multi-agent simulation framework and the text-adventure
                engine from{" "}
                <a href="https://interactive-fiction-class.org/homeworks/text-adventure-game/text-adventure-game.html">
                  Chris Callison-Burch's CIS 7000 – <em>Interactive Fiction and Text Generation</em>{" "}
                  course materials
                </a>
                , and we thank the framework's broader contributors. We are grateful to{" "}
                <a href="https://github.com/MaEnqiMark">Mark Ma</a> for his contributions to the{" "}
                <code>text_adventure_games</code> library — the engine every agent in this
                simulation acts through. Character sprite art is from the <em>Cute Fantasy</em> pack
                by Kenmi. Campus geography is derived from{" "}
                <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a> data.
              </p>
              <p>
                Beyond the architecture it describes, this project reuses code and data formats from
                the{" "}
                <a href="https://github.com/joonspk-research/generative_agents">
                  open-source release
                </a>{" "}
                accompanying Park et al. (Apache License 2.0; author Joon Sung Park). The
                breadth-first grid path-finder that walks a sprite around walls (
                <code>backend/path_finder.py</code>) is vendored from that repository's{" "}
                <code>path_finder.py</code>, with only a raised search cap, an early exit for
                unreachable targets, and its single numpy call replaced. Our spatial layer (
                <code>backend/world_map.py</code>) follows their <code>maze.py</code>: the same
                tile-matrix CSV layers, the same <code>world:sector:arena:object</code> address
                scheme, the same <TeX>{TEX.colRow}</TeX> convention, and the same tile-radius notion
                of what an agent can see — which is why our OSM-derived campus is emitted into that
                format, and why a persona's authored spatial knowledge loads from files shaped like
                theirs. The replay files a run bakes for the viewer keep the layout their web
                frontend replayed. The cognitive machinery itself — retrieval scoring, poignancy,
                reflection, hierarchical planning — is our own implementation, written from the
                paper.
              </p>
              <p>
                Two further works shaped the design. From <em>ReAct</em> (Yao et al.) comes the
                shape of a single decision: the agent states its reasoning before naming its action,
                and a rejected action returns as an observation to reason about rather than as an
                error — the retry described above. From <em>ScienceWorld</em> (Wang et al.) comes a
                discipline about verbs. A world change an agent wants is not a verb it gets to
                invoke; it is a consequence of dumb primitives applied in the right place, which is
                why an agent toggles a stove rather than calling <em>boil</em>, and why the tool
                menu is derived from affordances in scope. That work is also our reference point for
                grading agents on task completion, an interface this prototype has designed but not
                yet built.
              </p>
            </div>
          </div>
        </div>
      </section>

      {/* ===== Asset packs ===== */}
      <section className="nrf-section">
        <div className="nrf-container">
          <div className="nrf-narrow">
            <h2 className="nrf-title nrf-title-3 nrf-centered" id="assets">
              Asset packs
            </h2>
            <div className="nrf-content nrf-justified">
              <p>
                Listed below are the asset packs we used in the game. The viewer is a Godot 4.6
                project — campus maps are authored in Tiled from{" "}
                <a href="https://www.openstreetmap.org/relation/2594845#map=15/39.94770/-75.19361">
                  OpenStreetMap data
                </a>
                , with tilesets, sprites, and UI art drawn from these packs.
              </p>
              <ul>
                <li>
                  <a href="https://kenmi-art.itch.io/cute-fantasy-ui">Cute Fantasy UI</a> by Kenmi
                </li>
                <li>
                  <a href="https://kenmi-art.itch.io/cute-fantasy-rpg">Cute Fantasy RPG</a> by Kenmi
                </li>
                <li>
                  <a href="https://kenney.nl/assets/rpg-urban-pack">RPG Urban Pack</a> by Kenney
                </li>
              </ul>
            </div>
          </div>
        </div>
      </section>

      {/* ===== References ===== */}
      <section className="nrf-section">
        <div className="nrf-container">
          <div className="nrf-narrow">
            <h2 className="nrf-title nrf-title-3 nrf-centered" id="references">
              References
            </h2>
            <div className="nrf-content">
              <p>
                Joon Sung Park, Joseph C. O'Brien, Carrie J. Cai, Meredith Ringel Morris, Percy
                Liang, and Michael S. Bernstein. 2023.{" "}
                <a href="https://dl.acm.org/doi/10.1145/3586183.3606763">
                  Generative Agents: Interactive Simulacra of Human Behavior
                </a>
                . In <em>Proceedings of UIST '23</em>. Source code:{" "}
                <a href="https://github.com/joonspk-research/generative_agents">
                  joonspk-research/generative_agents
                </a>{" "}
                (Apache License 2.0).
              </p>
              <p>
                Ruoyao Wang, Peter Jansen, Marc-Alexandre Côté, and Prithviraj Ammanabrolu. 2022.{" "}
                <a href="https://aclanthology.org/2022.emnlp-main.775/">
                  ScienceWorld: Is your Agent Smarter than a 5th Grader?
                </a>{" "}
                In <em>Proceedings of EMNLP 2022</em>.
              </p>
              <p>
                Shunyu Yao, Jeffrey Zhao, Dian Yu, Nan Du, Izhak Shafran, Karthik Narasimhan, and
                Yuan Cao. 2023.{" "}
                <a href="https://arxiv.org/abs/2210.03629">
                  ReAct: Synergizing Reasoning and Acting in Language Models
                </a>
                . In <em>Proceedings of ICLR 2023</em>.
              </p>
            </div>
          </div>
        </div>
      </section>

      {/* ===== BibTeX ===== */}
      <section className="nrf-section">
        <div className="nrf-container nrf-content">
          <h2 className="nrf-title nrf-title-3" id="BibTeX">
            BibTeX
          </h2>
          <pre className="nrf-pre">
            <code>{`@misc{king2026penncampusagents,
  title  = {Penn Campus: Generative Agents in a Simulated World},
  author = {King, Alistair and L, Frankie and Callison-Burch, Chris},
  year   = {2026},
  note   = {PURM, University of Pennsylvania},
  url    = {${REPO_URL}},
}`}</code>
          </pre>
        </div>
      </section>

      {/* ===== Footer: template attribution (as the Nerfies license asks) ===== */}
      <footer className="nrf-footer">
        <div className="nrf-container">
          <div className="nrf-content nrf-footer-content">
            <p>
              The design of this page is adapted from the{" "}
              <a href="https://github.com/nerfies/nerfies.github.io">Nerfies</a> project page. We
              thank the authors for releasing their{" "}
              <a href="https://github.com/nerfies/nerfies.github.io">source code</a>, which is
              licensed under a{" "}
              <a rel="license" href="http://creativecommons.org/licenses/by-sa/4.0/">
                Creative Commons Attribution-ShareAlike 4.0 International License
              </a>
              .
            </p>
          </div>
        </div>
      </footer>
    </div>
  );
}
