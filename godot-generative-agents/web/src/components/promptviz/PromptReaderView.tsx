import { useEffect, useState } from "react";
import type { PromptEntry } from "../../types/promptviz";
import { PromptModal } from "./PromptModal";
import { packageLabel } from "./packageLabel";
import "./promptviz.css";

// Flat catalog written by scripts/gen_promptviz.py (pnpm gen:promptviz).
const PROMPTS_URL = `${import.meta.env.BASE_URL}promptviz/prompts.json`;

/**
 * The "Prompts" reader: a table of every .prompty template (modeled on the
 * prompt_templates README table — Prompt / Source / Used for). Clicking a row
 * opens a modal with that template's full rendered prompt + source.
 */
export function PromptReaderView() {
  const [prompts, setPrompts] = useState<PromptEntry[] | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [selected, setSelected] = useState<PromptEntry | null>(null);

  useEffect(() => {
    let cancelled = false;
    (async () => {
      try {
        const res = await fetch(PROMPTS_URL);
        if (!res.ok) throw new Error(`HTTP ${res.status} fetching prompts.json`);
        const data = (await res.json()) as { prompts: PromptEntry[] };
        if (!cancelled) setPrompts(data.prompts);
      } catch (err) {
        if (!cancelled) setError(err instanceof Error ? err.message : String(err));
      }
    })();
    return () => {
      cancelled = true;
    };
  }, []);

  return (
    <div className="pcv pcv-reader">
      <header className="pcv-topbar">
        <div className="pcv-brand">
          <span className="pcv-logo" aria-hidden="true">
            📖
          </span>
          <span className="pcv-name">Prompt Reader</span>
        </div>
        <div className="pcv-controls">{prompts && <span>{prompts.length} templates</span>}</div>
      </header>

      <div className="pcv-reader-body">
        {error && <div className="pcv-status pcv-error">{error}</div>}
        {!error && !prompts && <div className="pcv-status">Loading…</div>}
        {prompts && (
          <table className="pcv-table">
            <thead>
              <tr>
                <th>Prompt</th>
                <th>Source</th>
                <th>Used for</th>
              </tr>
            </thead>
            <tbody>
              {prompts.map((p) => (
                <tr
                  key={`${p.package}/${p.template}`}
                  tabIndex={0}
                  onClick={() => setSelected(p)}
                  onKeyDown={(e) => {
                    if (e.key === "Enter" || e.key === " ") {
                      e.preventDefault();
                      setSelected(p);
                    }
                  }}
                >
                  <td className="pcv-cell-name">{p.template}</td>
                  <td>
                    <span className="pcv-pkg-badge">{packageLabel(p.package)}</span>
                  </td>
                  <td className="pcv-cell-desc">{p.description}</td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </div>

      {selected && <PromptModal entry={selected} onClose={() => setSelected(null)} />}
    </div>
  );
}
