import type { LlmCallRecord } from "../types/live";

// Compact k-notation for token counts, like the Godot HUD's request log.
function tok(n: number): string {
  return n >= 1000 ? `${(n / 1000).toFixed(1)}k` : String(n);
}

// The full detail behind a row, shown on hover — the same fields the terminal
// monitor prints on its one line.
function rowTitle(c: LlmCallRecord): string {
  const cache = `${c.cache_creation_input_tokens}w/${c.cache_read_input_tokens}r cache`;
  const latency = c.latency_ms == null ? "-" : `${Math.round(c.latency_ms)} ms`;
  const turn = c.turn == null ? "-" : String(c.turn);
  return (
    `#${c.call_no} ${c.role} — ${c.actor ?? "-"} — turn ${turn} — ${c.model}\n` +
    `in ${c.input_tokens} (${cache}) → out ${c.output_tokens} — ${latency}\n` +
    `$${c.cost_usd.toFixed(6)} this call — Σ $${c.cum_cost_usd.toFixed(6)} run`
  );
}

// role is free-form on the wire; keep only word chars for the CSS tint class
// (mirrors MemoryList's kindClass).
function roleClass(role: string): string {
  return "llm-role-" + role.replace(/[^a-z]/gi, "").toLowerCase();
}

/**
 * The live LLM-request log (#398), filtered to one agent: the same
 * one-request-per-line stream the backend's terminal monitor prints and the
 * Godot HUD shows, scoped to the selected persona via each record's `actor`.
 * Newest first; hover a row for the full detail.
 */
export function LlmCallLog({
  calls,
  actor,
  connected,
}: {
  calls: LlmCallRecord[];
  actor: string;
  connected: boolean;
}) {
  const mine = calls.filter((c) => c.actor === actor);
  // The monitor numbers calls as they happen, so the newest record's call_no is
  // the run's true total — even after this list's cap trims old rows.
  const total = calls.length ? calls[calls.length - 1].call_no : 0;
  const rows = mine.slice(-30).reverse();

  return (
    <div className="agent-field llm-log">
      <span className="agent-field-label">
        LLM requests
        <span className="agent-history-count">{mine.length}</span>
        {total > 0 && <span className="llm-log-total">of {total} this run</span>}
        {!connected && <span className="llm-log-off">backend unreachable</span>}
      </span>
      {rows.length ? (
        <ul className="llm-log-list">
          {rows.map((c) => (
            <li key={c.call_no} className="llm-row" title={rowTitle(c)}>
              <span className="llm-time">{c.time}</span>
              <span className={`llm-role ${roleClass(c.role)}`}>{c.role}</span>
              <span className="llm-tokens">
                {tok(c.input_tokens)}→{tok(c.output_tokens)}
              </span>
              <span className="llm-cost">${c.cost_usd.toFixed(4)}</span>
            </li>
          ))}
        </ul>
      ) : (
        <p className="mem-empty">
          {total > 0
            ? `No calls from ${actor} yet.`
            : connected
              ? "No LLM requests yet — waiting on the live run."
              : "Waiting for the live backend…"}
        </p>
      )}
    </div>
  );
}
