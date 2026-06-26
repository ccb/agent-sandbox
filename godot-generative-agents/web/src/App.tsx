import { GodotCanvas } from "./components/GodotCanvas";
import { AgentPanel } from "./components/AgentPanel";
import { useReplay } from "./useReplay";
import "./App.css";

export default function App() {
  const { status, replay, error } = useReplay();

  return (
    <div className="app">
      <header className="app-header">
        <h1>Penn Campus — Generative Agents</h1>
        <p className="app-sub">Godot replay, running in the browser</p>
      </header>
      <main className="app-stage">
        {/* The Godot WebAssembly canvas. penn_replay.gd pushes the current step
            out via JavaScriptBridge so the panel beside it stays in sync. */}
        <div className="stage-canvas">
          <GodotCanvas />
        </div>

        {status === "ready" && replay.meta.personas.length > 0 ? (
          <AgentPanel replay={replay} />
        ) : (
          <aside className="agent-panel agent-panel--placeholder">
            {status === "loading" && "Loading agents…"}
            {status === "error" && `Couldn't load replay: ${error}`}
            {status === "ready" && "No agents in this replay."}
          </aside>
        )}
      </main>
    </div>
  );
}
