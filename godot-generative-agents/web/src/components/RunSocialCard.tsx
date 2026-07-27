import type { RunSocial } from "../types/live";
import "./AgentPanel.css"; // .agent-field/.agent-field-label/.agent-history-count/.mem-empty
import "./LlmDashboard.css"; // .social-* rows

/**
 * This run's social opportunity (#795, served inside GET /usage since #806):
 * co-settled pair-steps — two agents settled within conversation range at the
 * same step — broken down by pair, plus completed conversations. The zero
 * state is the whole point: it is the "conversation was structurally
 * impossible" signature #795 opened with, surfaced while the run is still
 * going instead of in a run-end server log line.
 */

// Enough pairs to show who is actually meeting without a full matrix.
const TOP_PAIRS = 5;

export interface SocialView {
  pairSteps: number;
  conversations: number;
  pairs: [string, number][];
  quiet: boolean;
}

/**
 * Shape the wire block for rendering: busiest pairs first (re-sorted
 * defensively; the server already orders them), top 5 only. `quiet` flags a
 * run that has stepped but never put two agents together — worded softly and
 * session-scoped by the card, because a RESUMED run restarts these counters
 * at 0 (the backend suppresses its own #795 run-end warning on resume for
 * exactly that reason) and the wire can't distinguish resumed; it also fires
 * for the whole run under the default mock brain, which never counts
 * co-settling at all (#825).
 */
export function socialView(social: RunSocial | undefined, step: number): SocialView | null {
  if (!social) return null;
  const pairs = Object.entries(social.by_pair)
    .sort(([, a], [, b]) => b - a)
    .slice(0, TOP_PAIRS);
  return {
    pairSteps: social.co_settled_pair_steps,
    conversations: social.conversations,
    pairs,
    quiet: step > 0 && social.co_settled_pair_steps === 0 && social.conversations === 0,
  };
}

export function RunSocialCard({ social, step }: { social: RunSocial | undefined; step: number }) {
  const v = socialView(social, step);
  if (!v) return null;
  return (
    <div className="agent-field social-card">
      <span className="agent-field-label">
        Social {v.pairSteps > 0 && <span className="agent-history-count">{v.pairSteps}</span>}
      </span>
      <p className="social-line">
        <strong>{v.pairSteps}</strong> co-settled pair-step{v.pairSteps === 1 ? "" : "s"} ·{" "}
        <strong>{v.conversations}</strong> conversation{v.conversations === 1 ? "" : "s"}
      </p>
      {v.quiet ? (
        <p
          className="mem-empty social-quiet"
          title="Co-settled moments are counted only when a conversation-capable brain drives the run — the mock schedule brain never counts them (#825)."
        >
          No co-settled moments counted yet this session.
        </p>
      ) : (
        v.pairs.length > 0 && (
          <ul className="social-pairs">
            {v.pairs.map(([label, steps]) => (
              <li key={label}>
                <span className="social-pair-label">{label}</span>
                <span className="social-pair-steps">{steps}</span>
              </li>
            ))}
          </ul>
        )
      )}
    </div>
  );
}
