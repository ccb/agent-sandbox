import { useEffect, useState } from "react";
import type { Replay } from "../types/replay";
import type { LiveState, ReceivedLlmCall } from "../useLive";
import { LlmCallLog } from "./LlmCallLog";
import { SpritePreview } from "./SpritePreview";
import "./AgentPanel.css"; // the llm-log row/pill styles LlmCallLog renders with
import "./LlmDashboard.css";

// Compact k-notation for token counts, matching LlmCallLog's rows.
function tok(n: number): string {
  return n >= 1000 ? `${(n / 1000).toFixed(1)}k` : String(n);
}

// One cell of the grid: a roster persona, an actor seen only on the stream, or
// the catch-all bucket for records with `actor: null`.
interface Cell {
  actor: string | null;
  label: string;
  emoji?: string;
  spriteIndex: number | null; // null = no on-map sprite (the unattributed cell)
}

// Recency thresholds, in ms since a cell's newest call reached the page: "hot"
// means called within ~2 feed polls (being consulted right now), "idle" means
// a quiet minute — the at-a-glance "who has gone quiet?" signal.
const HOT_MS = 10_000;
const IDLE_MS = 60_000;

// Aggregates over one cell's retained rows. useLive caps retention per agent,
// so past that window these describe recent behaviour; the run strip's totals
// (call_no / cum_cost_usd) stay exact regardless.
function statsFor(calls: ReceivedLlmCall[]) {
  let inTok = 0;
  let outTok = 0;
  let cacheRead = 0;
  let cost = 0;
  let latSum = 0;
  let latN = 0;
  for (const c of calls) {
    // The monitor's "in" column: bare input + cache write + cache read.
    inTok += c.input_tokens + c.cache_creation_input_tokens + c.cache_read_input_tokens;
    cacheRead += c.cache_read_input_tokens;
    outTok += c.output_tokens;
    cost += c.cost_usd;
    if (c.latency_ms != null) {
      latSum += c.latency_ms;
      latN += 1;
    }
  }
  const last = calls.length ? calls[calls.length - 1] : null;
  return {
    count: calls.length,
    inTok,
    outTok,
    cacheRead,
    cost,
    latencyLast: last?.latency_ms ?? null,
    latencyAvg: latN ? latSum / latN : null,
    last,
  };
}

/**
 * The LLM dashboard (#519): the "sit back and monitor the run" surface. One
 * cell per agent over the live request stream (#398) — client-side aggregates
 * and that agent's recent calls side by side, so attribution never means
 * reading names out of an interleaved log. A run strip on top carries the
 * exact run totals (the newest record's call_no / cum_cost_usd, authoritative
 * against GET /usage) plus the budget ceiling from the handshake's /usage read.
 *
 * Purely a consumer of useLive's existing feed poll — nothing new on the wire.
 */
export function LlmDashboard({ replay, live }: { replay: Replay | null; live: LiveState }) {
  // A slow tick so recency (hot/idle) decays while the feed is quiet — useLive
  // deliberately skips state updates when nothing changed.
  const [now, setNow] = useState(() => Date.now());
  useEffect(() => {
    const t = window.setInterval(() => setNow(Date.now()), 5000);
    return () => window.clearInterval(t);
  }, []);

  if (!live.enabled) {
    return (
      <div className="agents-placeholder">
        The LLM dashboard follows a live backend. Serve one (see backend/README.md), then
        open this page with <code>?api=&lt;its URL&gt;</code> — e.g.{" "}
        <code>/?api=http://127.0.0.1:8080#llm</code>.
      </div>
    );
  }

  // The roster: live personas when the handshake reported a loop (falling back
  // to the baked replay's cast), ∪ actors seen only on the stream, ∪ one
  // catch-all cell when unattributed records exist — so the grid works pointed
  // at any backend, replay loaded or not.
  const personas = (live.live ? live.meta?.personas : replay?.meta.personas) ?? [];
  const known = new Set(personas.map((p) => p.name));
  const extras = [
    ...new Set(
      live.calls.map((c) => c.actor).filter((a): a is string => a !== null && !known.has(a)),
    ),
  ];
  const cells: Cell[] = [
    ...personas.map((p, i) => ({ actor: p.name, label: p.name, emoji: p.emoji, spriteIndex: i })),
    ...extras.map((name, i) => ({ actor: name, label: name, spriteIndex: personas.length + i })),
  ];
  if (live.calls.some((c) => c.actor === null)) {
    cells.push({ actor: null, label: "Unattributed", spriteIndex: null });
  }

  if (!cells.length) {
    return <div className="agents-placeholder">Waiting for the live backend…</div>;
  }

  // Run totals: the monitor numbers calls and carries the cumulative cost on
  // every record, so the newest row is exact even after old rows fall off; the
  // handshake's /usage read covers the stretch before any record arrives.
  const newest = live.calls.length ? live.calls[live.calls.length - 1] : null;
  const totalCalls = newest?.call_no ?? live.usage?.calls ?? 0;
  const totalCost = newest?.cum_cost_usd ?? live.usage?.total_cost_usd ?? 0;
  const budget = live.usage?.max_cost_usd;

  return (
    <div className="llm-dash">
      <header className="llm-strip">
        <span
          className={`agent-live-badge${
            !live.connected ? " is-off" : live.paused ? " is-paused" : ""
          }`}
        >
          {!live.connected ? "reconnecting" : live.paused ? "live · paused" : "live"} · step{" "}
          {live.step}
        </span>
        <span className="llm-strip-stat">
          <strong>{totalCalls}</strong> calls
        </span>
        <span className="llm-strip-stat">
          <strong>${totalCost.toFixed(4)}</strong> spent
        </span>
        {budget != null && (
          <span className={`llm-strip-stat${totalCost >= budget ? " is-over" : ""}`}>
            <strong>${Math.max(budget - totalCost, 0).toFixed(2)}</strong> of $
            {budget.toFixed(2)} budget left
          </span>
        )}
        {live.meta?.llm && <span className="llm-strip-model">{live.meta.llm.model}</span>}
      </header>

      <div className="llm-grid">
        {cells.map((cell) => {
          const s = statsFor(live.calls.filter((c) => c.actor === cell.actor));
          const age = s.last ? now - s.last.receivedAt : null;
          const heat = age === null || age >= IDLE_MS ? "idle" : age < HOT_MS ? "hot" : "warm";
          return (
            <article className={`llm-cell is-${heat}`} key={cell.label}>
              <header className="llm-cell-head">
                {cell.spriteIndex !== null ? (
                  <SpritePreview index={cell.spriteIndex} className="llm-cell-sprite" />
                ) : (
                  <span className="llm-cell-sprite llm-cell-sprite--none" aria-hidden="true">
                    ?
                  </span>
                )}
                <div className="llm-cell-title">
                  <h3 className="llm-cell-name">
                    {cell.emoji && <span aria-hidden="true">{cell.emoji} </span>}
                    {cell.label}
                    <span
                      className={`llm-pulse is-${heat}`}
                      title={
                        s.last
                          ? `last call ${s.last.time} (${heat})`
                          : "no calls seen this session"
                      }
                    />
                  </h3>
                  <p className="llm-cell-last">
                    {s.last ? `last: ${s.last.role} · ${s.last.time}` : "no calls yet"}
                  </p>
                </div>
              </header>
              <dl className="llm-cell-stats">
                <div>
                  <dt>calls</dt>
                  <dd>{s.count}</dd>
                </div>
                <div>
                  <dt>tokens</dt>
                  <dd>
                    {tok(s.inTok)}→{tok(s.outTok)}
                  </dd>
                </div>
                <div>
                  <dt>cache hit</dt>
                  <dd>{s.inTok ? `${Math.round((s.cacheRead / s.inTok) * 100)}%` : "–"}</dd>
                </div>
                <div>
                  <dt>cost</dt>
                  <dd>${s.cost.toFixed(4)}</dd>
                </div>
                <div>
                  <dt>latency</dt>
                  <dd>
                    {s.latencyLast != null ? `${Math.round(s.latencyLast)}ms` : "–"}
                    {s.latencyAvg != null && ` (avg ${Math.round(s.latencyAvg)})`}
                  </dd>
                </div>
              </dl>
              <LlmCallLog calls={live.calls} actor={cell.actor} connected={live.connected} />
            </article>
          );
        })}
      </div>
    </div>
  );
}
