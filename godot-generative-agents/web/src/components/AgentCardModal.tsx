import { useEffect } from "react";
import type { Replay } from "../types/replay";
import { type LiveState, useLiveMemories } from "../useLive";
import { AgentCard } from "./AgentCard";
import { LlmCallLog } from "./LlmCallLog";
import { MemoryRows } from "./MemoryList";
import "./AgentPanel.css";

/**
 * One agent's card as a pop-up modal (#528) — the persona card, its slice of the
 * LLM-request stream, and its full memory history over a dimmed backdrop. The web
 * twin of the Godot persona inspector (#410): opened by clicking an agent's cell
 * on the unified live dashboard, deep-linked via `?agent=`, and driven by ONE of
 * two sources:
 *
 * - Live (`?api=` given and the handshake reported a live loop with personas):
 *   the card from the feed's latest frame record, step from the feed, memories
 *   from GET /agents/{name}/memory.
 * - Replay (the default): the baked file — frames indexed by the
 *   Godot-bridge/wall-clock step, memories from `memory_streams`.
 *
 * Self-gating: an unknown `name` (a stale `?agent=`, or the roster still loading)
 * renders nothing, so App can mount this on whatever the selected name is without
 * validating it first. Closes on the backdrop, the × button, or Escape.
 */
export function AgentCardModal({
  name,
  replay,
  live,
  replayStep,
  onClose,
}: {
  name: string;
  replay: Replay | null;
  live: LiveState;
  /** The current replay step, owned by App (single useReplayStep registrant). */
  replayStep: number;
  onClose: () => void;
}) {
  // Close on Escape, like the nav dropdown and the prompt modal.
  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if (e.key === "Escape") onClose();
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [onClose]);

  const isLive = live.live && (live.meta?.personas.length ?? 0) > 0;
  const meta = isLive ? live.meta : replay?.meta;
  const personas = meta?.personas ?? [];
  // The persona index also selects the sprite tint, so it must match the map.
  const index = personas.findIndex((p) => p.name === name);
  const persona = personas[index];

  // Replay path only: the Godot-bridge / wall-clock step (owned by App). Live
  // mode ignores it — the feed's frame records carry the step instead.
  const step = isLive ? live.step : replayStep;

  // Live path only (inert otherwise): the selected persona's memory stream,
  // refetched as the live step advances. Same entry shape as the baked stream.
  const liveMemories = useLiveMemories(isLive, persona?.name ?? "", live.step, live.base);

  // Hooks are done — safe to bail on an unknown/absent agent (App mounts us on
  // whatever `?agent=` holds; the roster may not have it, or may still be loading).
  if (!meta || !persona || index < 0) return null;

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
    <div className="agent-modal-backdrop" role="presentation" onClick={onClose}>
      <aside
        className="agent-modal"
        role="dialog"
        aria-modal="true"
        aria-label={`${persona.name} details`}
        onClick={(e) => e.stopPropagation()}
      >
        {/* Title row (replaces the old page navigator): name + live state on the
            left, close on the right. */}
        <header className="agent-modal-head">
          <span className="agent-modal-title">
            <span className="agent-modal-emoji" aria-hidden="true">
              {persona.emoji}
            </span>
            {persona.name}
            {/* Live mode only: connection + run state at a glance. */}
            {isLive && (
              <span
                className={`agent-live-badge${
                  !live.connected ? " is-off" : live.paused ? " is-paused" : ""
                }`}
              >
                {!live.connected ? "reconnecting" : live.paused ? "live · paused" : "live"} · step{" "}
                {live.step}
              </span>
            )}
          </span>
          <button type="button" className="agent-modal-close" aria-label="Close" onClick={onClose}>
            ×
          </button>
        </header>

        <div className="agent-board-cols">
          <div className="agent-board-main">
            <AgentCard
              persona={persona}
              index={index}
              frame={frame}
              secPerStep={meta.sec_per_step}
              relationships={meta.relationships}
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
      </aside>
    </div>
  );
}
