import { useEffect, useState } from "react";
import type { EventsResponse, LlmCallRecord } from "./types/live";

// Live mode is opt-in: the companion stays a static page unless you point it at
// a running backend with `?api=http://127.0.0.1:8080` (or a VITE_SIM_API_URL
// env var for `pnpm dev`). The backend's CORS already allows any localhost
// origin, so the Vite dev server can poll it directly — no proxy needed.
function apiBase(): string | null {
  const param = new URLSearchParams(window.location.search).get("api");
  const env = import.meta.env.VITE_SIM_API_URL as string | undefined;
  const base = param || env || null;
  return base ? base.replace(/\/+$/, "") : null;
}

const POLL_MS = 1000; // ~the loop's pace; a missed tick just arrives next poll
const MAX_ROWS = 200; // plenty for a day (~55-60 calls); keeps re-renders cheap

export interface LlmCallsState {
  enabled: boolean; // an ?api= target was given
  connected: boolean; // the last poll succeeded
  calls: LlmCallRecord[]; // oldest → newest, capped at MAX_ROWS
}

/**
 * Follow the live backend's LLM-request stream (#398): poll `GET /events` (the
 * change feed's stateless catch-up door — see backend/README.md) and keep the
 * `engine` records whose payload is `kind: "llm_call"`. These are the same rows
 * the backend's terminal monitor prints and the Godot HUD's request log shows.
 *
 * Polling resumes from the last cursor seen, so each row arrives exactly once;
 * the first poll (`since=0`) backfills whatever the capped log still retains.
 */
export function useLlmCalls(): LlmCallsState {
  const [state, setState] = useState<LlmCallsState>({
    enabled: false,
    connected: false,
    calls: [],
  });

  useEffect(() => {
    const base = apiBase();
    if (!base) return;
    setState((s) => ({ ...s, enabled: true }));

    let cancelled = false;
    let timer = 0;
    let cursor = 0;

    const poll = async () => {
      try {
        const res = await fetch(`${base}/events?since=${cursor}`);
        if (!res.ok) throw new Error(`HTTP ${res.status}`);
        const data = (await res.json()) as EventsResponse;
        if (cancelled) return;
        cursor = Math.max(cursor, data.latest_cursor);
        const fresh = data.events
          .filter((r) => r.kind === "engine" && r.event?.kind === "llm_call")
          .map((r) => r.event as unknown as LlmCallRecord);
        // Skip the state update when nothing changed, so an idle (or paused)
        // backend doesn't re-render the panel once a second.
        setState((s) =>
          s.connected && fresh.length === 0
            ? s
            : {
                enabled: true,
                connected: true,
                calls: fresh.length ? [...s.calls, ...fresh].slice(-MAX_ROWS) : s.calls,
              },
        );
      } catch {
        if (cancelled) return;
        setState((s) => (s.connected ? { ...s, connected: false } : s));
      }
      if (!cancelled) timer = window.setTimeout(poll, POLL_MS);
    };
    void poll();

    return () => {
      cancelled = true;
      window.clearTimeout(timer);
    };
  }, []);

  return state;
}
