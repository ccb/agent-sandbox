import type { ReceivedFeedEvent } from "../useLive";
import "./AgentPanel.css"; // .agent-field/.agent-field-label/.mem-empty
import "./LlmDashboard.css"; // .event-row styling

// The full detail behind a row, as the native tooltip — mirroring the Godot
// HUD's hover hint for the same records (hud add_engine_event / add_wish).
function rowTitle(e: ReceivedFeedEvent): string {
  const when = e.turn != null ? `t${e.turn}` : "-";
  if (e.kind === "wish") {
    const head = `${e.actor ?? "-"} wishes (${e.trigger}) · ${when}: ${e.desired}`;
    return e.reason ? `${head} — because ${e.reason}` : head;
  }
  return `${e.action} · ${when} · ${e.actor ?? "world"}: ${e.summary}`;
}

/**
 * The run-event feed (#644): `game_event` rows (craft/sickness/boiled/… — the
 * #467 engine records) and ActionWish demand records (#622) off the live
 * change feed. The Godot HUD already logs both; without this panel the web
 * companion silently disagreed with it about what happened. Newest first and
 * capped like LlmCallLog; live-only (a baked replay has no feed to follow).
 */
export function EventFeed({
  events,
  connected,
}: {
  events: ReceivedFeedEvent[];
  connected: boolean;
}) {
  const rows = events.slice(-30).reverse();

  return (
    <div className="agent-field event-feed">
      <span className="agent-field-label">
        Run events
        {events.length > 0 && <span className="agent-history-count">{events.length}</span>}
      </span>
      {rows.length ? (
        <ul className="event-feed-list">
          {rows.map((e) => (
            // The feed cursor is unique per record — a stable key.
            <li key={e.cursor} className="event-row" title={rowTitle(e)}>
              <span className="event-turn">{e.turn != null ? `t${e.turn}` : "–"}</span>
              <span className={`event-kind${e.kind === "wish" ? " event-kind--wish" : ""}`}>
                {e.kind === "wish" ? "💭 wish" : e.action}
              </span>
              <span className="event-text">
                {e.actor && <span className="event-actor">{e.actor}: </span>}
                {e.kind === "wish" ? e.desired : e.summary}
              </span>
            </li>
          ))}
        </ul>
      ) : (
        <p className="mem-empty">
          {connected
            ? "No game events yet — craft/sickness/wish records land here as the run logs them."
            : "Waiting for the live backend…"}
        </p>
      )}
    </div>
  );
}
