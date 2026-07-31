import { useState } from "react";
import { startRun } from "../../config/configApi";
import {
  buildPostBody,
  coercePlan,
  effectivePlan,
  mergeKnobs,
  planLocked,
} from "../../config/configBody";
import type { ConfigSurface, SetupFormState } from "../../types/config";
import "./SetupView.css";

// The 7 curated knobs, mirroring godot/scripts/simulation_setup.gd's KNOBS —
// each a label, a nested path into knobs.current, and int|float. `step`/`max`
// mirror that scene's SpinBox bounds (min is always 0 there).
const KNOBS: {
  label: string;
  path: string[];
  kind: "int" | "float";
  step: number;
  max: number;
}[] = [
  {
    label: "Temperature (llm brain)",
    path: ["game", "agent", "temperature"],
    kind: "float",
    step: 0.05,
    max: 100,
  },
  {
    label: "Recency weight",
    path: ["retrieval", "alpha_recency"],
    kind: "float",
    step: 0.05,
    max: 100,
  },
  {
    label: "Importance weight",
    path: ["retrieval", "alpha_importance"],
    kind: "float",
    step: 0.05,
    max: 100,
  },
  {
    label: "Relevance weight",
    path: ["retrieval", "alpha_relevance"],
    kind: "float",
    step: 0.05,
    max: 100,
  },
  {
    label: "Vision radius (tiles)",
    path: ["cognition", "vision_r"],
    kind: "int",
    step: 1,
    max: 10000,
  },
  {
    label: "Conversation cooldown (steps)",
    path: ["cognition", "conversation_cooldown_steps"],
    kind: "int",
    step: 1,
    max: 10000,
  },
  {
    label: "Max exchanges / conversation",
    path: ["cognition", "conversation_max_exchanges"],
    kind: "int",
    step: 1,
    max: 10000,
  },
];

// Read a nested numeric knob out of a knobs dict by path (0 if absent).
function knobAt(knobs: Record<string, unknown>, path: string[]): number {
  let cur: unknown = knobs;
  for (const seg of path) {
    if (typeof cur !== "object" || cur === null) return 0;
    cur = (cur as Record<string, unknown>)[seg];
  }
  return typeof cur === "number" ? cur : 0;
}

// Set a nested value by path into a fresh nested-dict edit ({a:{b:{c:v}}}).
function nest(path: string[], value: number): Record<string, unknown> {
  const root: Record<string, unknown> = {};
  let cur = root;
  path.forEach((seg, i) => {
    if (i === path.length - 1) cur[seg] = value;
    else {
      const next: Record<string, unknown> = {};
      cur[seg] = next;
      cur = next;
    }
  });
  return root;
}

export function SetupView({
  base,
  surface,
  onStarted,
}: {
  base: string;
  surface: ConfigSurface;
  onStarted: () => void;
}) {
  const r = surface.run;
  const [cast, setCast] = useState<string[]>(surface.cast);
  const [brain, setBrain] = useState(r.brain);
  const [plan, setPlan] = useState(r.plan_request || "auto"); // the raw ask
  const [effort, setEffort] = useState(r.effort);
  const [model, setModel] = useState(r.model);
  const [steps, setSteps] = useState(r.steps);
  const [tick, setTick] = useState(r.tick_seconds);
  const [maxCost, setMaxCost] = useState(r.max_cost);
  // knobEdits: nested dict of CHANGED knobs only, keyed by path (see nest()).
  const [knobEdits, setKnobEdits] = useState<Record<string, unknown>>({});
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  // Switching to a free brain snaps an llm planner back to auto (#791).
  const onBrain = (next: string) => {
    setBrain(next);
    setPlan((p) => coercePlan(p, next));
  };

  const start = async () => {
    setBusy(true);
    setError(null);
    const state: SetupFormState = {
      cast,
      brain,
      initialBrain: r.brain,
      steps,
      initialSteps: r.steps,
      tick,
      initialTick: r.tick_seconds,
      maxCost,
      plan,
      initialPlan: r.plan_request || "auto",
      effort,
      initialEffort: r.effort,
      model,
      initialModel: r.model,
      knobsCurrent: surface.knobs.current,
      knobEdits,
    };
    const res = await startRun(base, buildPostBody(state));
    if (res.ok) onStarted();
    else {
      setBusy(false);
      setError(res.detail ?? `Start failed (${res.stage}).`);
    }
  };

  // Each row's displayed value: the server's defaults, overlaid by its current
  // values, overlaid by any live (unsaved) edit — reusing the same mergeKnobs
  // buildPostBody merges with, so display and submit never disagree about
  // which value wins. (knobAt/nest are the brief's verbatim helpers above.)
  const knobsForDisplay = mergeKnobs(
    mergeKnobs(surface.knobs.defaults, surface.knobs.current),
    knobEdits,
  );

  const toggleCast = (id: string) => {
    setCast((c) => (c.includes(id) ? c.filter((x) => x !== id) : [...c, id]));
  };

  return (
    <form
      className="setup-view"
      onSubmit={(e) => {
        e.preventDefault();
        void start();
      }}
    >
      <h2>Simulation setup</h2>
      <p className="setup-backend">Backend: {base}</p>

      <section className="setup-section">
        <h3>Cast</h3>
        {surface.personas.length === 0 ? (
          <p className="setup-hint">No personas are available on this backend.</p>
        ) : (
          <div className="setup-cast-list">
            {surface.personas.map((p) => (
              <label className="setup-persona" key={p.id}>
                <input
                  type="checkbox"
                  checked={cast.includes(p.id)}
                  disabled={busy}
                  onChange={() => toggleCast(p.id)}
                />
                <span className="setup-persona-body">
                  <span className="setup-persona-name">
                    {p.emoji && <span aria-hidden="true">{p.emoji} </span>}
                    {p.name}
                  </span>
                  {p.description && <span className="setup-persona-desc">{p.description}</span>}
                </span>
              </label>
            ))}
          </div>
        )}
      </section>

      <section className="setup-section">
        <h3>Sim knobs</h3>
        <div className="setup-rows">
          {KNOBS.map((k) => (
            <label className="setup-row" key={k.path.join(".")}>
              <span className="setup-row-label">{k.label}</span>
              <input
                type="number"
                min={0}
                max={k.max}
                step={k.step}
                disabled={busy}
                value={knobAt(knobsForDisplay, k.path)}
                onChange={(e) => {
                  const raw = e.target.valueAsNumber;
                  if (Number.isNaN(raw)) return;
                  const v = k.kind === "int" ? Math.round(raw) : raw;
                  setKnobEdits((prev) => mergeKnobs(prev, nest(k.path, v)));
                }}
              />
            </label>
          ))}
        </div>
      </section>

      <section className="setup-section">
        <h3>Run</h3>
        <div className="setup-rows">
          <label className="setup-row">
            <span className="setup-row-label">Brain</span>
            <select value={brain} disabled={busy} onChange={(e) => onBrain(e.target.value)}>
              {surface.brains.map((b) => (
                <option key={b} value={b}>
                  {b}
                </option>
              ))}
            </select>
          </label>

          {surface.plans.length > 0 && (
            <>
              <label className="setup-row">
                <span className="setup-row-label">Planner</span>
                <select value={plan} disabled={busy} onChange={(e) => setPlan(e.target.value)}>
                  {surface.plans.map((p) => (
                    <option key={p} value={p} disabled={p === "llm" && planLocked(brain)}>
                      {p}
                    </option>
                  ))}
                </select>
              </label>
              <p className="setup-hint">Day plan: {effectivePlan(plan, brain)}</p>
            </>
          )}

          {surface.efforts.length > 0 && (
            <label className="setup-row">
              <span className="setup-row-label">Thinking depth (llm only)</span>
              <select value={effort} disabled={busy} onChange={(e) => setEffort(e.target.value)}>
                {surface.efforts.map((ef) => (
                  <option key={ef} value={ef}>
                    {ef}
                  </option>
                ))}
              </select>
            </label>
          )}

          {surface.models.length > 0 && (
            <label className="setup-row">
              <span className="setup-row-label">Model (llm only)</span>
              <select value={model} disabled={busy} onChange={(e) => setModel(e.target.value)}>
                {surface.models.map((m) => (
                  <option key={m} value={m}>
                    {m}
                  </option>
                ))}
              </select>
            </label>
          )}

          <label className="setup-row">
            <span className="setup-row-label">Steps</span>
            <input
              type="number"
              min={1}
              step={1}
              disabled={busy}
              value={steps}
              onChange={(e) => {
                const v = e.target.valueAsNumber;
                if (!Number.isNaN(v)) setSteps(Math.round(v));
              }}
            />
          </label>

          <label className="setup-row">
            <span className="setup-row-label">Tick seconds</span>
            <input
              type="number"
              min={0.05}
              max={60}
              step={0.05}
              disabled={busy}
              value={tick}
              onChange={(e) => {
                const v = e.target.valueAsNumber;
                if (!Number.isNaN(v)) setTick(v);
              }}
            />
          </label>

          <label className="setup-row">
            <span className="setup-row-label">Cost budget (USD, llm only)</span>
            <input
              type="number"
              min={0}
              max={1000}
              step={0.5}
              disabled={busy}
              value={maxCost}
              onChange={(e) => {
                const v = e.target.valueAsNumber;
                if (!Number.isNaN(v)) setMaxCost(v);
              }}
            />
          </label>
        </div>

        {r.stop_time && <p className="setup-hint">Ends about {r.stop_time} at this step budget.</p>}
      </section>

      {error && <p className="setup-error">{error}</p>}

      <button type="submit" className="setup-start" disabled={busy || cast.length === 0}>
        {busy ? "Starting…" : "▶ Start the simulation"}
      </button>
    </form>
  );
}
