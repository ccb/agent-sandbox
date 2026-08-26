import { useEffect, useState } from "react";
import type { Replay } from "../types/replay";
import { type LiveState, type ReceivedLlmCall, useThinking } from "../useLive";
import { ConversationFeed } from "./ConversationFeed";
import { EventFeed } from "./EventFeed";
import { LlmCallLog } from "./LlmCallLog";
import { MostTakenActions } from "./MostTakenActions";
import { RunSocialCard, SocialSummary, socialView } from "./RunSocialCard";
import { SpritePreview } from "./SpritePreview";
import { WishFeed } from "./WishFeed";
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
 * The unified live page (#519 dashboard + #528 agent-card modal): the "sit back
 * and monitor the run" surface. One cell per agent over the live request stream
 * (#398) — client-side aggregates and that agent's recent calls side by side, so
 * attribution never means reading names out of an interleaved log. A run strip on
 * top carries the exact run totals (the newest record's call_no / cum_cost_usd,
 * authoritative against GET /usage) plus the budget ceiling from the handshake's
 * /usage read. Clicking a roster cell's header opens that agent's card as a modal
 * (App owns that state via `onOpenAgent`).
 *
 * Works pointed at any live backend AND from a baked replay with no backend at
 * all: the roster then comes from the replay's cast, the call surfaces just stay
 * empty, and the cards are still clickable (the agents view's old replay-home job,
 * folded in here). Purely a consumer of useLive's existing feed poll — the run
 * buttons POST the backend's pause/resume/reset controls; nothing else new on the
 * wire.
 */
export function LlmDashboard({
  replay,
  live,
  replayStep,
  onConnect,
  onOpenAgent,
}: {
  replay: Replay | null;
  live: LiveState;
  /** The current replay step, owned by App (single useReplayStep registrant). */
  replayStep: number;
  onConnect: (url: string) => void;
  onOpenAgent: (name: string) => void;
}) {
  // A slow tick so recency (hot/idle) decays while the feed is quiet — useLive
  // deliberately skips state updates when nothing changed.
  const [now, setNow] = useState(() => Date.now());
  useEffect(() => {
    const t = window.setInterval(() => setNow(Date.now()), 5000);
    return () => window.clearInterval(t);
  }, []);
  const [url, setUrl] = useState("http://127.0.0.1:8080");

  // The global "thinking" cue (#525): per-agent `deciding` state OR'd with the
  // stall heuristic, mirroring the Godot viewer's badge (#598). Edge-triggered
  // in the hook, so it can't strobe at mock speeds.
  const thinking = useThinking(live);

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

  // The connect form: shown as a full card when there's nothing to show yet (no
  // backend and no baked roster), and as a compact strip affordance in
  // replay-only mode so a viewer can still attach to a live backend.
  const connectForm = (inline: boolean) => (
    <form
      className={inline ? "llm-connect llm-connect--inline" : "llm-connect"}
      onSubmit={(e) => {
        e.preventDefault();
        onConnect(url);
      }}
    >
      {!inline && (
        <>
          <h2>Follow a live backend</h2>
          <p>
            Serve one —{" "}
            <code>uv run python godot-generative-agents/backend/penn/serve_penn.py</code> — then
            connect to watch its LLM calls, one cell per agent, and start/stop the run from here.
          </p>
        </>
      )}
      <div className="llm-connect-row">
        <input
          type="url"
          value={url}
          onChange={(e) => setUrl(e.target.value)}
          aria-label="Backend URL"
          required
        />
        <button type="submit">Connect</button>
      </div>
    </form>
  );

  if (!cells.length) {
    // No roster yet: a backend was given but hasn't reported personas → waiting;
    // otherwise (no backend, no baked cast) → the connect card.
    return (
      <div className="agents-placeholder">
        {live.enabled ? "Waiting for the live backend…" : connectForm(false)}
      </div>
    );
  }

  // Run controls (#519): fire-and-forget POSTs — the backend appends a status
  // record to the feed, so the badge, step, and buttons update on the next
  // poll (~1s). Reset rebuilds t0 but keeps the running/paused state.
  const ctl = (action: "pause" | "resume" | "reset") => {
    if (live.base) void fetch(`${live.base}/${action}`, { method: "POST" }).catch(() => {});
  };
  const canControl = live.connected && live.live;

  // Run totals: the monitor numbers calls and carries the cumulative cost on
  // every record, so the newest row is exact even after old rows fall off; the
  // handshake's /usage read covers the stretch before any record arrives. That
  // fallback prefers the RUN-scoped fields (#644): the lifetime `calls`/
  // `total_cost_usd` tick with the mock brain's $0 pacing records, re-inflating
  // the headline #601 fixed server-side ("27 calls over a 3-row log"). Older
  // backends without the run fields still fall through to the lifetime pair.
  const newest = live.calls.length ? live.calls[live.calls.length - 1] : null;
  const totalCalls = newest?.call_no ?? live.usage?.run_calls ?? live.usage?.calls ?? 0;
  const totalCost =
    newest?.cum_cost_usd ?? live.usage?.run_cost_usd ?? live.usage?.total_cost_usd ?? 0;
  const budget = live.usage?.max_cost_usd;

  // The run's social glance for the strip (#795/#819): shaped by the same
  // socialView the card uses, so the sentence + pluralisation live in one
  // place. Hidden when the brain never counts co-settling (#825) — a permanent
  // 0 there is noise, and the card below still explains why.
  const socialStrip = socialView(live.usage?.social, live.step);

  // The current step's frame map for the conversation feed (#534): the live feed's
  // latest frame when following a live loop, else the baked frame at the
  // Godot-bridge step. Switches on live.live (like `personas` above), not persona
  // count — a live run still shows live chat before/without persona meta.
  const feedFrame = live.live
    ? live.frame
    : replay?.frames[Math.min(replayStep, (replay?.frames.length ?? 1) - 1)];

  return (
    <div className="llm-dash">
      <header className="llm-strip">
        {live.enabled ? (
          <>
            {/* Badge precedence: disconnected (red) > paused (amber) > thinking
                (purple — a live run mid-decision, #525) > live (green). Thinking
                requires `connected`, so it can never mask "reconnecting". */}
            <span
              className={`agent-live-badge${
                !live.connected
                  ? " is-off"
                  : live.paused
                    ? " is-paused"
                    : thinking
                      ? " is-thinking"
                      : ""
              }`}
            >
              {!live.connected
                ? "reconnecting"
                : live.paused
                  ? "live · paused"
                  : thinking
                    ? "live · thinking…"
                    : "live"}{" "}
              · step {live.step}
            </span>
            <span className="llm-strip-controls">
              {live.paused ? (
                <button type="button" onClick={() => ctl("resume")} disabled={!canControl}>
                  ▶ Start
                </button>
              ) : (
                <button type="button" onClick={() => ctl("pause")} disabled={!canControl}>
                  ⏸ Stop
                </button>
              )}
              <button
                type="button"
                onClick={() => ctl("reset")}
                disabled={!canControl}
                title="Restart the sim day from the beginning"
              >
                ↺ Reset
              </button>
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
            {socialStrip && socialStrip.note !== "uncounted" && (
              <span
                className="llm-strip-stat"
                title="co-settled pair-steps · completed conversations (#795)"
              >
                <SocialSummary
                  pairSteps={socialStrip.pairSteps}
                  conversations={socialStrip.conversations}
                />
              </span>
            )}
            {live.meta?.llm && <span className="llm-strip-model">{live.meta.llm.model}</span>}
          </>
        ) : (
          // Replay-only: no run to control — show the cast is from the baked file
          // and offer a compact connect to follow a live backend instead.
          <>
            <span className="llm-strip-stat">Replay · no live backend</span>
            {connectForm(true)}
          </>
        )}
      </header>

      <ConversationFeed frame={feedFrame} personas={personas} onOpenAgent={onOpenAgent} />

      {/* The most-taken-actions tally (#701): works from both sources — the
          baked replay's events through the cursor, or the live feed's
          game_event rows — so it renders in replay mode too, unlike EventFeed. */}
      <MostTakenActions replay={replay} live={live} replayStep={replayStep} />

      {/* The wish demand feed (#873): the run's ActionWish rows (#621/#622) in
          their own panel — dual-source like the action tally above, so a baked
          replay's wishes display too (EventFeed below is live-only and buries
          wishes among game events). */}
      <WishFeed replay={replay} live={live} replayStep={replayStep} />

      {/* The run's social opportunity (#795/#819): live-only — replays carry
          no /usage, and RunSocialCard hides itself when an older backend
          serves no social block. */}
      {live.enabled && (
        <RunSocialCard social={live.usage?.social} step={live.step} connected={live.connected} />
      )}

      {/* Run events (#644): the game_event/wish rows off the live feed — the
          same records the Godot HUD logs. Live-only: a baked replay has no
          feed, and its events already live in the replay file. */}
      {live.enabled && <EventFeed events={live.events} connected={live.connected} />}

      <div className="llm-grid">
        {cells.map((cell) => {
          const s = statsFor(live.calls.filter((c) => c.actor === cell.actor));
          const age = s.last ? now - s.last.receivedAt : null;
          const heat = age === null || age >= IDLE_MS ? "idle" : age < HOT_MS ? "hot" : "warm";
          // Only roster personas have a card (persona meta + frame). Stream-only
          // "extras" and the Unattributed cell don't, so their headers aren't
          // clickable.
          const clickable = cell.actor !== null && known.has(cell.actor);
          const head = (
            <>
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
                  {/* Recency pulse + last-call line are live-only; in replay mode
                      there are no calls, so the header is just the roster tile. */}
                  {live.enabled && (
                    <span
                      className={`llm-pulse is-${heat}`}
                      title={
                        s.last ? `last call ${s.last.time} (${heat})` : "no calls seen this session"
                      }
                    />
                  )}
                  {/* Per-agent "thinking" bubble (#525): lit while this agent's
                      `deciding` begin is unmatched on the feed (#551). Within-tick
                      decides fold begin+end in one batch and never light it — the
                      #605 boundary — so this mostly marks tick-spanning decides. */}
                  {live.enabled && cell.actor !== null && cell.actor in live.deciding && (
                    <span
                      className="llm-thinking-bubble"
                      role="img"
                      aria-label="deciding"
                      title={`${cell.label} is deciding…`}
                    >
                      💭
                    </span>
                  )}
                </h3>
                {live.enabled && (
                  <p className="llm-cell-last">
                    {s.last ? `last: ${s.last.role} · ${s.last.time}` : "no calls yet"}
                  </p>
                )}
              </div>
            </>
          );
          return (
            <article className={`llm-cell${live.enabled ? ` is-${heat}` : ""}`} key={cell.label}>
              {clickable ? (
                <button
                  type="button"
                  className="llm-cell-head llm-cell-head--btn"
                  onClick={() => onOpenAgent(cell.actor as string)}
                  title={`Open ${cell.label}'s card`}
                >
                  {head}
                </button>
              ) : (
                <header className="llm-cell-head">{head}</header>
              )}
              {/* The call surfaces — aggregates + the per-agent request log — are
                  live-only. With no backend (replay) the cell is just the roster
                  tile: identity, clickable to open the card (#528). */}
              {live.enabled && (
                <>
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
                </>
              )}
            </article>
          );
        })}
      </div>
    </div>
  );
}
