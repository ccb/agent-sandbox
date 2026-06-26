import { lazy, Suspense, useEffect, useRef, useState } from "react";
import { GodotCanvas } from "./components/GodotCanvas";
import { AgentPanel } from "./components/AgentPanel";
import { useReplay } from "./useReplay";
import "./App.css";

// Lazy-loaded: the prompt-chain view pulls in Cytoscape (~430 kB), which only
// the Prompt-chains tab needs. Splitting it keeps that weight out of the initial
// bundle until someone opens the tab.
const PromptChainView = lazy(() =>
  import("./components/promptviz/PromptChainView").then((m) => ({
    default: m.PromptChainView,
  }))
);

// The Prompts reader is its own lazy chunk — it's just a table + modal, so it
// doesn't pull in Cytoscape the way the chains view does.
const PromptReaderView = lazy(() =>
  import("./components/promptviz/PromptReaderView").then((m) => ({
    default: m.PromptReaderView,
  }))
);

type View = "game" | "agents" | "prompts" | "reader";

// Pages selected by the URL hash (#game / #agents / #prompts / #reader) so each
// is a real, shareable location and the back button works — no router needed.
// The agent cards are the landing page (the cognitive layer is the point of this
// companion); the other views are one explicit hop away.
function viewFromHash(): View {
  const hash = window.location.hash.replace("#", "");
  if (hash === "game") return "game";
  if (hash === "prompts") return "prompts";
  if (hash === "reader") return "reader";
  return "agents";
}

// The navigable views, grouped into labeled sections for the dropdown menu.
interface NavItem {
  view: View;
  label: string;
  icon: string;
}
const NAV_SECTIONS: { heading: string; items: NavItem[] }[] = [
  {
    heading: "Game",
    items: [
      { view: "agents", label: "Agent cards", icon: "👤" },
      { view: "game", label: "Game view", icon: "🎮" },
    ],
  },
  {
    heading: "Prompts",
    items: [
      { view: "prompts", label: "Prompt chains", icon: "⛓" },
      { view: "reader", label: "Prompt reader", icon: "📖" },
    ],
  },
];

export default function App() {
  const { status, replay, error } = useReplay();
  const [view, setView] = useState<View>(viewFromHash);
  const [menuOpen, setMenuOpen] = useState(false);
  const menuRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    const onHash = () => setView(viewFromHash());
    window.addEventListener("hashchange", onHash);
    return () => window.removeEventListener("hashchange", onHash);
  }, []);

  // While the nav menu is open, close it on an outside click or Escape.
  useEffect(() => {
    if (!menuOpen) return;
    const onDown = (e: MouseEvent) => {
      if (menuRef.current && !menuRef.current.contains(e.target as Node)) {
        setMenuOpen(false);
      }
    };
    const onKey = (e: KeyboardEvent) => {
      if (e.key === "Escape") setMenuOpen(false);
    };
    document.addEventListener("mousedown", onDown);
    document.addEventListener("keydown", onKey);
    return () => {
      document.removeEventListener("mousedown", onDown);
      document.removeEventListener("keydown", onKey);
    };
  }, [menuOpen]);

  const select = (v: View) => {
    window.location.hash = v;
    setView(v);
  };

  const currentLabel =
    NAV_SECTIONS.flatMap((s) => s.items).find((i) => i.view === view)?.label ?? "Menu";

  return (
    <div className="app" data-view={view}>
      <header className="app-header">
        <div className="app-title">
          <h1>Penn Campus — Generative Agents</h1>
          <p className="app-sub">Godot replay, running in the browser</p>
        </div>
        <div className="header-actions">
          {/* Collapsed nav: the trigger shows the current view and opens a
              dropdown to switch. Keeps the header uncluttered as views grow. */}
          <div className="nav-menu" ref={menuRef}>
            <button
              type="button"
              className="nav-trigger"
              aria-haspopup="menu"
              aria-expanded={menuOpen}
              aria-label={`Navigate (current: ${currentLabel})`}
              onClick={() => setMenuOpen((open) => !open)}
            >
              <svg
                className="nav-burger"
                width="18"
                height="18"
                viewBox="0 0 18 18"
                aria-hidden="true"
              >
                <rect x="1" y="3.5" width="16" height="2" rx="1" />
                <rect x="1" y="8" width="16" height="2" rx="1" />
                <rect x="1" y="12.5" width="16" height="2" rx="1" />
              </svg>
            </button>
            {menuOpen && (
              <div className="nav-dropdown" role="menu" aria-label="Navigate">
                {NAV_SECTIONS.map((section) => (
                  <div
                    className="nav-group"
                    key={section.heading}
                    role="group"
                    aria-label={section.heading}
                  >
                    <div className="nav-group-heading">{section.heading}</div>
                    {section.items.map((item) => (
                      <button
                        key={item.view}
                        type="button"
                        role="menuitem"
                        className={`nav-item${view === item.view ? " is-active" : ""}`}
                        onClick={() => {
                          select(item.view);
                          setMenuOpen(false);
                        }}
                      >
                        <span className="nav-icon" aria-hidden="true">
                          {item.icon}
                        </span>
                        {item.label}
                      </button>
                    ))}
                  </div>
                ))}
                {/* A link, not a view: it leaves the SPA for the static MkDocs
                    site at /docs/ (build it with `pnpm gen:docs`). BASE_URL keeps
                    it correct if the app's base path ever changes. */}
                <a
                  className="nav-item nav-item--link"
                  role="menuitem"
                  href={`${import.meta.env.BASE_URL}docs/`}
                >
                  <span className="nav-icon" aria-hidden="true">
                    📄
                  </span>
                  Docs ↗
                </a>
              </div>
            )}
          </div>
        </div>
      </header>

      <main className="app-stage">
        {/* The Godot canvas stays mounted and full-size at all times, so the
            engine never re-boots or resizes to zero when you switch pages. The
            agent view sits over it as an opaque page when its tab is active. */}
        <section className="view view-game" aria-hidden={view !== "game"}>
          <GodotCanvas />
        </section>

        <section className="view view-agents" aria-hidden={view !== "agents"}>
          {status === "ready" && replay.meta.personas.length > 0 ? (
            <AgentPanel replay={replay} />
          ) : (
            <div className="agents-placeholder">
              {status === "loading" && "Loading agents…"}
              {status === "error" && `Couldn't load replay: ${error}`}
              {status === "ready" && "No agents in this replay."}
            </div>
          )}
        </section>

        {/* Mounted only when active: Cytoscape needs a sized container at init,
            and (unlike the Godot canvas) this view has no reason to stay alive
            in the background. */}
        {view === "prompts" && (
          <section className="view view-prompts">
            <Suspense fallback={<div className="pcv-loading">Loading…</div>}>
              <PromptChainView />
            </Suspense>
          </section>
        )}

        {view === "reader" && (
          <section className="view view-reader">
            <Suspense fallback={<div className="pcv-loading">Loading…</div>}>
              <PromptReaderView />
            </Suspense>
          </section>
        )}
      </main>
    </div>
  );
}
