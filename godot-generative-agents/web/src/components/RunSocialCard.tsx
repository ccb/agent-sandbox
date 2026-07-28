import type { RunSocial } from "../types/live";
import "./AgentPanel.css"; // .agent-field/.agent-field-label/.agent-history-count/.mem-empty
import "./LlmDashboard.css"; // .social-* rows

/**
 * This run's social opportunity (#795, carried on the live feed's `run_usage`
 * since #819): co-settled pair-steps — two agents settled within conversation
 * range at the same step — broken down by pair, plus completed conversations.
 * The zero state is the whole point: it is the "conversation was structurally
 * impossible" signature #795 opened with, surfaced while the run is still going
 * instead of in a run-end server log line — but a zero only means that when the
 * run actually counts co-settling (`counted`) and wasn't resumed (`resumed`),
 * so the card names those two non-signals distinctly (#825) rather than
 * hedging every zero with one soft sentence.
 */

// Enough pairs to show who is actually meeting without a full matrix.
const TOP_PAIRS = 5;

// Which explanatory line the zero/edge state warrants, or null to just list the
// busiest pairs. See socialView for the decision order.
export type SocialNote = "uncounted" | "resumed" | "mismatch" | "drought" | "unknown" | null;

export interface SocialView {
  pairSteps: number;
  conversations: number;
  pairs: [string, number][];
  truncated: number; // pairs beyond TOP_PAIRS, so the cap isn't silent (#823)
  note: SocialNote;
}

/**
 * Shape the wire block for rendering: busiest pairs first (with a label
 * tie-break, so equal counts render in a stable order rather than whatever the
 * server dict emitted), top 5, plus how many were dropped. `note` classifies
 * the state the counters describe:
 *
 * - `uncounted` — the run's brain never counts co-settling (the mock schedule
 *   brain, #825); its permanent 0 is "not measured".
 * - `resumed` — the run was adopted mid-day, so the accumulators restarted at 0.
 * - `mismatch` — a conversation completed yet co-settle read 0: the counter is
 *   demonstrably wrong, which the old both-zero gate hid entirely.
 * - `drought` — a counting, non-resumed run that stepped and never put two
 *   agents together: the real #795 signal.
 * - `unknown` — same zero, but from a backend too old to send `counted`, so we
 *   can't rule out mock/resumed: keep the old soft wording.
 */
export function socialView(social: RunSocial | undefined, step: number): SocialView | null {
  if (!social) return null;
  const ranked = Object.entries(social.by_pair).sort(
    ([a, na], [b, nb]) => nb - na || (a < b ? -1 : a > b ? 1 : 0),
  );
  const pairSteps = social.co_settled_pair_steps;
  const conversations = social.conversations;
  const stepped = step > 0;
  const note: SocialNote =
    social.counted === false
      ? "uncounted"
      : social.resumed
        ? "resumed"
        : stepped && pairSteps === 0 && conversations > 0
          ? "mismatch"
          : stepped && pairSteps === 0
            ? social.counted === true
              ? "drought"
              : "unknown"
            : null;
  return {
    pairSteps,
    conversations,
    pairs: ranked.slice(0, TOP_PAIRS),
    truncated: Math.max(0, ranked.length - TOP_PAIRS),
    note,
  };
}

// The one place the counter sentence + its pluralisation live — rendered both
// here and by the dashboard's strip stat, so the two can't word it differently.
export function SocialSummary({
  pairSteps,
  conversations,
}: {
  pairSteps: number;
  conversations: number;
}) {
  return (
    <>
      <strong>{pairSteps}</strong> co-settled pair-step{pairSteps === 1 ? "" : "s"} ·{" "}
      <strong>{conversations}</strong> conversation{conversations === 1 ? "" : "s"}
    </>
  );
}

const NOTE_TEXT: Record<Exclude<SocialNote, null>, string> = {
  uncounted:
    "Co-settling isn't counted under this brain — the mock schedule brain never does (#825).",
  resumed: "Resumed run — the social counters restarted at 0, so a low count isn't the whole day.",
  mismatch:
    "A conversation completed but co-settled pair-steps read 0 — the co-settle counter may be off.",
  drought:
    "No two agents were ever settled together — conversation was structurally impossible this run (#795).",
  unknown: "No co-settled moments counted yet this session.",
};

export function RunSocialCard({
  social,
  step,
  connected,
}: {
  social: RunSocial | undefined;
  step: number;
  connected: boolean;
}) {
  const v = socialView(social, step);
  if (!v) return null;
  return (
    <div className="agent-field">
      <span className="agent-field-label">
        Social {v.pairSteps > 0 && <span className="agent-history-count">{v.pairSteps}</span>}
        {/* Don't present a stale zero as live during an outage (#823): the
            card's whole job is to make a zero mean something, so flag the
            disconnect instead of asserting a drought that may be gone. */}
        {!connected && <span className="llm-log-off">backend unreachable</span>}
      </span>
      <p className="social-line">
        <SocialSummary pairSteps={v.pairSteps} conversations={v.conversations} />
      </p>
      {v.note && connected ? (
        <p className="mem-empty social-quiet" title={NOTE_TEXT[v.note]}>
          {NOTE_TEXT[v.note]}
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
            {v.truncated > 0 && (
              <li className="social-pairs-more">
                <span className="social-pair-label">+{v.truncated} more</span>
              </li>
            )}
          </ul>
        )
      )}
    </div>
  );
}
