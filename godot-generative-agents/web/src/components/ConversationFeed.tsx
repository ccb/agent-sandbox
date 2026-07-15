import type { Frame, Persona } from "../types/replay";

/**
 * A companion-level view of the dialogue happening across all agents at the
 * current step (#534). The per-agent card's "Current Conversation" field stays
 * the detailed per-agent view; this aggregates every agent's `chat` into one
 * newest-first strip so conversations are watchable at a glance without opening
 * each modal. Container-agnostic (per #523/#528): takes the step's frame map +
 * roster, so it can live on the dashboard now and anywhere later.
 */

// Both participants of a conversation carry the same window transcript on their
// own `chat` (generate_penn_replay.py paints it onto each; live maybe_converse
// does the same), so collecting across agents double-counts every line — dedup
// by (speaker, line). Newest-last on the wire → reverse for newest-first, cap
// like LlmCallLog.
export function collectConversations(
  frame: Frame | null | undefined,
  cap = 30,
): [string, string][] {
  const seen = new Set<string>();
  const out: [string, string][] = [];
  for (const f of Object.values(frame ?? {})) {
    for (const [speaker, line] of f?.chat ?? []) {
      const key = `${speaker}\n${line}`;
      if (seen.has(key)) continue;
      seen.add(key);
      out.push([speaker, line]);
    }
  }
  return out.reverse().slice(0, cap);
}

export function ConversationFeed({
  frame,
  personas,
  onOpenAgent,
}: {
  frame: Frame | null | undefined;
  personas: Persona[];
  onOpenAgent: (name: string) => void;
}) {
  const lines = collectConversations(frame);
  const known = new Set(personas.map((p) => p.name));

  return (
    <div className="agent-field">
      <span className="agent-field-label">
        Conversations{" "}
        {lines.length > 0 && <span className="agent-history-count">{lines.length}</span>}
      </span>
      {lines.length ? (
        lines.map(([speaker, line], i) => (
          <div key={i} className="chat-line">
            {/* When the speaker is a roster persona, the name deep-links to their
                card, mirroring the dashboard's clickable cell header (#534). */}
            {known.has(speaker) ? (
              <button
                type="button"
                className="chat-speaker convo-speaker-btn"
                onClick={() => onOpenAgent(speaker)}
                title={`Open ${speaker}'s card`}
              >
                {speaker}:
              </button>
            ) : (
              <span className="chat-speaker">{speaker}:</span>
            )}{" "}
            {line}
          </div>
        ))
      ) : (
        <p className="mem-empty">No conversations yet.</p>
      )}
    </div>
  );
}
