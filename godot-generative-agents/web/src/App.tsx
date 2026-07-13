import { Activity, BookOpen, FileText, Gamepad2, Home, Menu, Share2 } from "lucide-react";
import { lazy, type ReactNode, Suspense, useEffect, useRef, useState } from "react";
import { AgentCardModal } from "./components/AgentCardModal";
import { GodotCanvas } from "./components/GodotCanvas";
import { HomeView } from "./components/home/HomeView";
import { LlmDashboard } from "./components/LlmDashboard";
import { setUrlParam } from "./url";
import { initialApiBase, useLive } from "./useLive";
import { useReplay } from "./useReplay";
import "./App.css";

// Lazy-loaded: the prompt-chain view pulls in Cytoscape (~430 kB), which only
// the Prompt-chains tab needs. Splitting it keeps that weight out of the initial
// bundle until someone opens the tab.
const PromptChainView = lazy(() =>
  import("./components/promptviz/PromptChainView").then((m) => ({
    default: m.PromptChainView,
  })),
);

// The Prompts reader is its own lazy chunk — it's just a table + modal, so it
// doesn't pull in Cytoscape the way the chains view does.
const PromptReaderView = lazy(() =>
  import("./components/promptviz/PromptReaderView").then((m) => ({
    default: m.PromptReaderView,
  })),
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

// Menu icons: lucide line icons sized to the nav's 16px. Each is monochrome and
// strokes in `currentColor`, so it inherits its menu item's text colour — dark
// normally, white when the item is active.
const ICON_HOME = <Home className="nav-icon" size={16} aria-hidden />;
const ICON_GAME = <Gamepad2 className="nav-icon" size={16} aria-hidden />;
const ICON_LLM = <Activity className="nav-icon" size={16} aria-hidden />;
const ICON_CHAINS = <Share2 className="nav-icon" size={16} aria-hidden />;
const ICON_READER = <BookOpen className="nav-icon" size={16} aria-hidden />;
const ICON_DOCS = <FileText className="nav-icon" size={16} aria-hidden />;

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
      : (NAV_SECTIONS.flatMap((s) => s.items).find((i) => i.view === view)?.label ?? "Menu");

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
              <Menu className="nav-burger" size={18} aria-hidden />
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
