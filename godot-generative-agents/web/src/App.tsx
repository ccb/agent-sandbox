import { GodotCanvas } from "./components/GodotCanvas";
import "./App.css";

export default function App() {
  return (
    <div className="app">
      <header className="app-header">
        <h1>Penn Campus — Generative Agents</h1>
        <p className="app-sub">Godot replay, running in the browser</p>
      </header>
      <main className="app-stage">
        {/*
          The Godot WebAssembly canvas. This is the whole app for now.

          Companion-app next step: add agent-info side panels here. They can read
          the SAME public/replay/penn_replay.json this canvas plays (typed in
          src/types/replay.ts) to show each persona's current action/location —
          no need to scrape state out of Godot. Tighter sync (e.g. clicking a
          panel highlights that agent) can later use Godot's JavaScriptBridge.
        */}
        <GodotCanvas />
      </main>
    </div>
  );
}
