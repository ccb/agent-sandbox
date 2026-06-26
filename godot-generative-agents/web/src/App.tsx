import { lazy, Suspense, useEffect, useState } from "react";
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

export default function App() {
  const { status, replay, error } = useReplay();
  const [view, setView] = useState<View>(viewFromHash);

  useEffect(() => {
    const onHash = () => setView(viewFromHash());
    window.addEventListener("hashchange", onHash);
    return () => window.removeEventListener("hashchange", onHash);
  }, []);

  const select = (v: View) => {
    window.location.hash = v;
    setView(v);
  };

  return (
    <div className="app" data-view={view}>
      <header className="app-header">
        <div className="app-title">
          <h1>Penn Campus — Generative Agents</h1>
          <p className="app-sub">Godot replay, running in the browser</p>
        </div>
        <div className="header-actions">
          <nav className="view-tabs" role="tablist" aria-label="View">
            <button
              type="button"
              role="tab"
              aria-selected={view === "game"}
              className={`view-tab${view === "game" ? " is-active" : ""}`}
              onClick={() => select("game")}
            >
              Game view
            </button>
            <button
              type="button"
              role="tab"
              aria-selected={view === "agents"}
              className={`view-tab${view === "agents" ? " is-active" : ""}`}
              onClick={() => select("agents")}
            >
              Agent cards
            </button>
            <button
              type="button"
              role="tab"
              aria-selected={view === "prompts"}
              className={`view-tab${view === "prompts" ? " is-active" : ""}`}
              onClick={() => select("prompts")}
            >
              Prompt chains
            </button>
            <button
              type="button"
              role="tab"
              aria-selected={view === "reader"}
              className={`view-tab${view === "reader" ? " is-active" : ""}`}
              onClick={() => select("reader")}
            >
              Prompts
            </button>
          </nav>
          {/* Plain link, not a tab: it leaves the SPA for the static MkDocs site
              served at /docs/ on this same origin (build it with `pnpm gen:docs`).
              BASE_URL keeps it correct if the app's base path ever changes. */}
          <a className="view-tab docs-link" href={`${import.meta.env.BASE_URL}docs/`}>
            Docs
          </a>
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
