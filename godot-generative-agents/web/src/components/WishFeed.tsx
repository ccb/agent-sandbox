import type { Replay, WishState } from "../types/replay";
import type { LiveState } from "../useLive";
import "./AgentPanel.css"; // .agent-field/.agent-field-label/.agent-history-count/.mem-empty
import "./LlmDashboard.css"; // .event-row/.event-kind(--wish)/.event-turn/.event-text

/**
 * The wish demand feed (#873): every ActionWish the run has logged (#621/#622),
 * in its own panel — the demand-side record #846 reads for affordance design.
 * EventFeed (#644) interleaves live wish rows among game events and is
 * live-only; this panel is wishes-only and works from both sources, like
 * MostTakenActions (#701): the live feed's `wish` rows, or the baked replay's
 * `wishes` array scoped to the cursor — so scrubbing back hides later wishes.
 */

// Wishes are rare (a busy live day logs ~10), so a modest cap keeps a
// pathological run from growing the panel unbounded, like EventFeed's 30.
const CAP = 30;

/**
 * The rows to show: `turn <= upToTurn` (null = no cursor, the live path — the
 * feed only ever carries rows up to "now"), newest first, capped. Rows pass
 * through whole so the caller keeps its own fields (e.g. the live feed's
 * unique `cursor` for React keys).
 */
export function selectWishes<T extends Pick<WishState, "turn">>(
  wishes: T[],
  upToTurn: number | null,
  cap = CAP,
): T[] {
  const scoped = upToTurn === null ? wishes : wishes.filter((w) => w.turn <= upToTurn);
  return scoped.slice(-cap).reverse();
}

// The full detail behind a row, as the native tooltip — the same fields the
// Godot HUD's add_wish hover hint carries, plus the wish's goals/scope
// snapshot, which only this panel surfaces.
function rowTitle(w: WishState): string {
  const where = w.location ? ` @ ${w.location}` : "";
  const head = `${w.actor ?? "-"} wishes (${w.trigger}) · t${w.turn}${where}: ${w.desired}`;
  const parts = [
    w.reason ? `because ${w.reason}` : "",
    w.goals.length ? `goals: ${w.goals.join("; ")}` : "",
    w.scope.length ? `in scope: ${w.scope.join(", ")}` : "",
  ].filter(Boolean);
  return parts.length ? `${head} — ${parts.join(" · ")}` : head;
}

export function WishFeed({
  replay,
  live,
  replayStep,
}: {
  replay: Replay | null;
  live: LiveState;
  /** The current replay step (App's single useReplayStep registrant). */
  replayStep: number;
}) {
  // Same source switch as MostTakenActions: the live feed's wish rows when
  // following a live loop, else the baked wishes through the cursor.
  const rows = live.live
    ? selectWishes(
        live.events.filter((e) => e.kind === "wish"),
        null,
      )
    : selectWishes(replay?.wishes ?? [], replayStep);
  const total = live.live
    ? live.events.filter((e) => e.kind === "wish").length
    : (replay?.wishes ?? []).filter((w) => w.turn <= replayStep).length;

  return (
    <div className="agent-field wish-feed">
      <span className="agent-field-label">
        Wishes
        {total > 0 && <span className="agent-history-count">{total}</span>}
      </span>
      {rows.length ? (
        <ul className="event-feed-list">
          {rows.map((w, i) => (
            // Live rows carry the feed's unique cursor; baked rows are stable
            // within a loaded replay, so their index is a safe key.
            <li
              key={"cursor" in w ? (w as { cursor: number }).cursor : `${w.turn}-${i}`}
              className="event-row"
              title={rowTitle(w)}
            >
              <span className="event-turn">t{w.turn}</span>
              <span className="event-kind event-kind--wish">💭 {w.trigger}</span>
              <span className="event-text">
                {w.actor && <span className="event-actor">{w.actor}: </span>}
                {w.desired}
              </span>
            </li>
          ))}
        </ul>
      ) : (
        <p className="mem-empty">
          {live.live
            ? "No wishes yet — an agent's unparseable or proposed action lands here (#621)."
            : "No wishes up to this step — scrub forward, or this replay predates the wish log (#622)."}
        </p>
      )}
    </div>
  );
}
