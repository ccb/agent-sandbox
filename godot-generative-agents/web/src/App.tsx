import { lazy, Suspense, useEffect, useRef, useState, type ReactNode } from "react";
import { GodotCanvas } from "./components/GodotCanvas";
import { AgentCardModal } from "./components/AgentCardModal";
import { LlmDashboard } from "./components/LlmDashboard";
import { HomeView } from "./components/home/HomeView";
import { useReplay } from "./useReplay";
import { useLive, initialApiBase } from "./useLive";
import { setUrlParam } from "./url";
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

type View = "home" | "game" | "llm" | "prompts" | "reader";

// Pages selected by the URL hash (#home / #game / #llm / #prompts / #reader) so
// each is a real, shareable location and the back button works — no router
// needed. The Nerfies-style project page is the landing view; every other view is
// one explicit hop away via the menu. `#agents` (the old agent-cards page, folded
// into the live dashboard in #528) redirects here so existing links keep working.
function viewFromHash(): View {
  const hash = window.location.hash.replace("#", "");
  if (hash === "game") return "game";
  if (hash === "llm" || hash === "agents") return "llm";
  if (hash === "prompts") return "prompts";
  if (hash === "reader") return "reader";
  return "home";
}

// Monochrome line icons for the menu. Stroke is `currentColor`, so each icon
// inherits its menu item's text color — dark normally, white when active. Kept
// as inline SVG (like the hamburger trigger) rather than emoji so they render as
// flat black-and-white glyphs instead of the platform's colored emoji art.
function NavIcon({ children }: { children: ReactNode }) {
  return (
    <svg
      className="nav-icon"
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

const ICON_HOME = (
  <NavIcon>
    <path d="M3 10.5 12 3l9 7.5" />
    <path d="M5 9.5V20a1 1 0 0 0 1 1h12a1 1 0 0 0 1-1V9.5" />
    <path d="M9.5 21v-6h5v6" />
  </NavIcon>
);
const ICON_GAME = (
  <NavIcon>
    <line x1="7" y1="11" x2="11" y2="11" />
    <line x1="9" y1="9" x2="9" y2="13" />
    <line x1="15" y1="12" x2="15.01" y2="12" />
    <line x1="18" y1="10" x2="18.01" y2="10" />
    <path d="M17.32 6H6.68a4 4 0 0 0-3.98 3.59c-.08.7-.7 5.66-.7 6.41a3 3 0 0 0 3 3c1 0 1.5-.5 2-1l1.41-1.41A2 2 0 0 1 9.83 16h4.34a2 2 0 0 1 1.42.59L17 18c.5.5 1 1 2 1a3 3 0 0 0 3-3c0-.75-.62-5.71-.7-6.41A4 4 0 0 0 17.32 6z" />
  </NavIcon>
);
const ICON_LLM = (
  <NavIcon>
    <polyline points="22 12 18 12 15 21 9 3 6 12 2 12" />
  </NavIcon>
);
const ICON_CHAINS = (
  <NavIcon>
    <circle cx="18" cy="5" r="3" />
    <circle cx="6" cy="12" r="3" />
    <circle cx="18" cy="19" r="3" />
    <line x1="8.6" y1="13.5" x2="15.4" y2="17.5" />
    <line x1="15.4" y1="6.5" x2="8.6" y2="10.5" />
  </NavIcon>
);
const ICON_READER = (
  <NavIcon>
    <path d="M12 7v14" />
    <path d="M3 18a1 1 0 0 1-1-1V4a1 1 0 0 1 1-1h5a4 4 0 0 1 4 4 4 4 0 0 1 4-4h5a1 1 0 0 1 1 1v13a1 1 0 0 1-1 1h-6a3 3 0 0 0-3 3 3 3 0 0 0-3-3z" />
  </NavIcon>
);
const ICON_DOCS = (
  <NavIcon>
    <path d="M15 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V7z" />
    <path d="M14 2v4a2 2 0 0 0 2 2h4" />
    <line x1="8" y1="13" x2="16" y2="13" />
    <line x1="8" y1="17" x2="16" y2="17" />
    <line x1="8" y1="9" x2="10" y2="9" />
  </NavIcon>
);

// The navigable views, grouped into labeled sections for the dropdown menu.
interface NavItem {
  view: View;
  label: string;
  icon: ReactNode;
}
const NAV_SECTIONS: { heading: string; items: NavItem[] }[] = [
  {
    heading: "Game",
    items: [
      { view: "game", label: "Game view", icon: ICON_GAME },
      { view: "llm", label: "Live dashboard", icon: ICON_LLM },
    ],
  },
  {
    heading: "Prompts",
    items: [
      { view: "prompts", label: "Prompt chains", icon: ICON_CHAINS },
      { view: "reader", label: "Prompt reader", icon: ICON_READER },
    ],
  },
];

export default function App() {
  const { status, replay } = useReplay();
  // The live backend: one handshake + one feed poll, shared by the live dashboard
  // and the agent-card modal. The target starts from ?api= / VITE_SIM_API_URL and
  // can also be supplied at runtime by the dashboard's connect form (#519).
  const [apiUrl, setApiUrl] = useState<string | null>(initialApiBase);
  const live = useLive(apiUrl);

  // Connecting via the form is the same as arriving with ?api= — the URL is
  // updated to match (no reload), so a refresh or a shared link sticks.
  const connectApi = (url: string) => {
    const clean = url.trim().replace(/\/+$/, "");
    if (!clean) return;
    setUrlParam("api", clean);
    setApiUrl(clean);
  };

  // The open agent-card modal (#528): clicking a dashboard cell opens that
  // agent's card, deep-linked via ?agent=<name> so a refresh or a shared link
  // reopens it. The one-shot mount read mirrors initialApiBase; the writes are
  // the second caller of setUrlParam (#522). AgentCardModal self-gates on the
  // roster, so a stale name just renders nothing.
  const [selectedAgent, setSelectedAgent] = useState<string | null>(() =>
    new URLSearchParams(window.location.search).get("agent"),
  );
  const openAgent = (name: string) => {
    setSelectedAgent(name);
    setUrlParam("agent", name);
  };
  const closeAgent = () => {
    setSelectedAgent(null);
    setUrlParam("agent", null);
  };

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
    view === "home"
      ? "Home"
      : NAV_SECTIONS.flatMap((s) => s.items).find((i) => i.view === view)?.label ?? "Menu";

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
                {/* The landing page sits on its own above the grouped views. */}
                <div className="nav-group" role="group">
                  <button
                    type="button"
                    role="menuitem"
                    className={`nav-item${view === "home" ? " is-active" : ""}`}
                    onClick={() => {
                      select("home");
                      setMenuOpen(false);
                    }}
                  >
                    {ICON_HOME}
                    Home
                  </button>
                </div>
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
                        {item.icon}
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
                  {ICON_DOCS}
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

        {/* The unified live page (#519 dashboard + #528 agent cards). Mounted only
            when active — its data lives in App's shared useLive poll, so nothing is
            lost on unmount. Clicking a roster cell opens that agent's card as the
            modal below. In replay mode the dashboard shows the baked cast; while
            that file is still loading (and no backend is set) we hold a placeholder
            so the connect form doesn't flash. */}
        {view === "llm" && (
          <section className="view view-llm">
            {status === "loading" && !live.enabled ? (
              <div className="agents-placeholder">Loading agents…</div>
            ) : (
              <LlmDashboard
                replay={replay}
                live={live}
                onConnect={connectApi}
                onOpenAgent={openAgent}
              />
            )}
          </section>
        )}

        {/* The agent-card modal (#528): a full-viewport overlay, so it renders
            outside any single view section. Self-gates on the roster. */}
        {view === "llm" && selectedAgent && (
          <AgentCardModal name={selectedAgent} replay={replay} live={live} onClose={closeAgent} />
        )}

        {/* The landing page. Mounted only when active — it's a static page with
            no reason to stay alive behind the other views. */}
        {view === "home" && (
          <section className="view view-home">
            <HomeView />
          </section>
        )}

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
