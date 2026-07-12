import { useState } from "react";
import type { Replay } from "../types/replay";
import { AgentCard } from "./AgentCard";
import { LlmCallLog } from "./LlmCallLog";
import { MemoryRows } from "./MemoryList";
import { useReplayStep } from "../useReplay";
import { useLiveMemories, type LiveState } from "../useLive";
import "./AgentPanel.css";

/**
 * The agent navigator + card + memory column, driven by ONE of two sources:
 *
 * - Live (`?api=` given and the handshake reported a live loop with personas):
 *   roster from the live meta, the card from the feed's latest frame record,
 *   step from the feed, memories from GET /agents/{name}/memory.
 * - Replay (the default): the baked file exactly as before — frames indexed by
 *   the Godot-bridge/wall-clock step, memories from `memory_streams`.
 */
export function AgentPanel({ replay, live }: { replay: Replay | null; live: LiveState }) {
  // Which agent's card you're looking at. Arrows step through the personas
  // (wrapping at the ends), like Smallville's agent navigator — switching only
  // changes WHO you see; the run keeps playing underneath.
  const [index, setIndex] = useState(0);

  const isLive = live.live && (live.meta?.personas.length ?? 0) > 0;
  const meta = isLive ? live.meta : replay?.meta;
  const personas = meta?.personas ?? [];
  const count = personas.length;
  const persona = personas[index % Math.max(count, 1)] ?? personas[0];

  // Replay path only: the Godot-bridge / wall-clock step. Passing 0 keeps it
  // inert in live mode, where the feed's frame records carry the step instead.
  const replayStep = useReplayStep(isLive ? 0 : replay?.meta.steps ?? 0);
  const step = isLive ? live.step : replayStep;

  // Live path only (inert otherwise): the selected persona's memory stream,
  // refetched as the live step advances. Same entry shape as the baked stream.
  const liveMemories = useLiveMemories(isLive, persona?.name ?? "", live.step);

  if (!meta || !persona) return null; // App gates on personas; belt for types

  const go = (delta: number) => setIndex((i) => (i + delta + count) % count);
  const frame = isLive
    ? live.frame?.[persona.name]
    : replay?.frames[Math.min(step, replay.frames.length - 1)]?.[persona.name];

  // The full memory stream accrued so far, newest-first — the expanded view,
  // distinct from the card's compact "Memories retrieved". On the replay path,
  // filtering to created_turn <= step means it grows as the replay plays; the
  // live fetch already stops at "now".
  const history = isLive
    ? liveMemories.slice().reverse()
    : (replay?.memory_streams?.[persona.name] ?? [])
        .filter((m) => m.created_turn <= step)
        .slice()
        .reverse();

  return (
    <aside className="agent-panel">
      {/* One cohesive panel: a navigator header over a two-column body (the agent's
          details on the left, its full memory history on the right), so the arrows,
          the card, and the memory list read as one piece instead of stacked boxes. */}
      <div className="agent-board">
        <header className="agent-nav">
          <button
            type="button"
            className="agent-nav-btn"
            onClick={() => go(-1)}
            disabled={count < 2}
            aria-label="Previous agent"
            title="Previous agent"
          >
            ‹
          </button>
          <span className="agent-indicator">
            <span className="agent-indicator-emoji" aria-hidden="true">
              {persona.emoji}
            </span>
            {persona.name}
            <span className="agent-indicator-count">
              {index + 1} / {count}
            </span>
          </span>
          <button
            type="button"
            className="agent-nav-btn"
            onClick={() => go(1)}
            disabled={count < 2}
            aria-label="Next agent"
            title="Next agent"
          >
            ›
          </button>
          {/* Live mode only: connection + run state at a glance. */}
          {isLive && (
            <span
              className={`agent-live-badge${
                !live.connected ? " is-off" : live.paused ? " is-paused" : ""
              }`}
            >
              {!live.connected ? "reconnecting" : live.paused ? "live · paused" : "live"} ·
              step {live.step}
            </span>
          )}
        </header>

        <div className="agent-board-cols">
          <div className="agent-board-main">
            <AgentCard
              name={persona.name}
              emoji={persona.emoji}
              index={index}
              frame={frame}
              secPerStep={meta.sec_per_step}
            />
            {/* Live mode only: this agent's slice of the LLM-request stream,
                under the card so the memory column keeps the full height. */}
            {live.enabled && (
              <LlmCallLog calls={live.calls} actor={persona.name} connected={live.connected} />
            )}
          </div>

          {/* The expanded view: every memory the agent has formed so far, beyond the
              handful the card surfaced. Its own column so the card stays compact. */}
          <section className="agent-board-side">
            <div className="agent-history-head">
              Full memory history
              <span className="agent-history-count">{history.length}</span>
            </div>
            {history.length ? (
              <MemoryRows records={history} secPerStep={meta.sec_per_step} flashTurn={step} />
            ) : (
              <p className="mem-empty">No memories yet.</p>
            )}
          </section>
        </div>
      </div>
    </aside>
  );
}
