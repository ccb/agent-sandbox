import { useEffect, useState } from "react";
import { GodotCanvas } from "./components/GodotCanvas";
import { AgentPanel } from "./components/AgentPanel";
import { useReplay } from "./useReplay";
import "./App.css";

type View = "game" | "agents";

// Two "pages", selected by the URL hash (#game / #agents) so each is a real,
// shareable location and the back button works — no router dependency needed.
function viewFromHash(): View {
  return window.location.hash.replace("#", "") === "agents" ? "agents" : "game";
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
        </nav>
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
      </main>
    </div>
  );
}
