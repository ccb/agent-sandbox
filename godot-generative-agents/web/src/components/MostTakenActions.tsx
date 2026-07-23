import type { EventState, Replay } from "../types/replay";
import type { LiveState } from "../useLive";
import "./AgentPanel.css"; // .agent-field/.agent-field-label/.agent-history-count/.mem-empty
import "./LlmDashboard.css"; // .action-tally-* rows + the .event-kind verb pill

/**
 * The most-taken-actions tally (#701): which action verbs agents have executed
 * most often up to the current step — the offline most-common-actions report
 * (#699, tools/most_common_actions.py) as a live dashboard panel. Overall
 * counts (not per-actor) for v1. Works from both sources: the baked replay's
 * `events` array scoped to the cursor, or the live feed's `game_event` rows
 * (#726). Recomputed from the step every render — never accumulated — so
 * scrubbing the replay BACK lowers the counts, like ConversationFeed's
 * cursor-scoped frame.
 */

// Engine-internal GameEvent.action values that are NOT agent commands:
// EventKind.TRIGGER and EventKind.SOUND (text_adventure_games/enums.py),
// written by the trigger system and Game.emit_sound — the exact filter the
// #699 report applies (its EXCLUDED_KINDS), matched on the `action` value.
export const EXCLUDED_KINDS = new Set(["trigger", "sound"]);

// Enough rows to show the shape of a run without pushing the grid off-screen.
const TOP_N = 10;

/**
 * Fold GameEvent rows into `[verb, count]` pairs, ranked count-desc with ties
 * broken by the verb ascending (deterministic, like #699's sort key — minus
 * its distinct-actors criterion, which v1's overall counts don't surface).
 * `upToTurn` is the cursor: rows past it are out of scope (null = no cursor,
 * the live path — the feed only ever carries rows up to "now").
 */
export function tallyActions(
  events: Pick<EventState, "action" | "turn">[],
  upToTurn: number | null,
  top = TOP_N,
): [string, number][] {
  const counts = new Map<string, number>();
  for (const e of events) {
    if (upToTurn !== null && e.turn > upToTurn) continue;
    if (EXCLUDED_KINDS.has(e.action)) continue;
    counts.set(e.action, (counts.get(e.action) ?? 0) + 1);
  }
  return [...counts]
    .sort(([a, na], [b, nb]) => nb - na || (a < b ? -1 : a > b ? 1 : 0))
    .slice(0, top);
}

export function MostTakenActions({
  replay,
  live,
  replayStep,
}: {
  replay: Replay | null;
  live: LiveState;
  /** The current replay step (App's single useReplayStep registrant). */
  replayStep: number;
}) {
  // Same source switch as the dashboard's conversation frame: the live feed's
  // rows when following a live loop, else the baked events through the cursor.
  // Live rows need no turn scoping, but they do need the kind filter — the
  // feed interleaves `wish` records, which are demand, not executed actions.
  const ranked = live.live
    ? tallyActions(
        live.events.filter((e) => e.kind === "game_event"),
        null,
      )
    : tallyActions(replay?.events ?? [], replayStep);
  const total = ranked.reduce((n, [, count]) => n + count, 0);
  const max = ranked.length ? ranked[0][1] : 0;

  return (
    <div className="agent-field action-tally">
      <span className="agent-field-label">
        Most-taken actions {total > 0 && <span className="agent-history-count">{total}</span>}
      </span>
      {ranked.length ? (
        <ol className="action-tally-list">
          {ranked.map(([verb, count]) => (
            <li key={verb} className="action-tally-row" title={`${verb}: ${count}×`}>
              <span className="event-kind action-tally-verb">{verb}</span>
              <span className="action-tally-track">
                <span className="action-tally-fill" style={{ width: `${(count / max) * 100}%` }} />
              </span>
              <span className="action-tally-count">{count}</span>
            </li>
          ))}
        </ol>
      ) : (
        <p className="mem-empty">
          {!live.live && replay && !replay.events
            ? "This replay has no events record — rebake it to see the tally."
            : "No actions taken yet."}
        </p>
      )}
    </div>
  );
}
