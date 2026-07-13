import { useEffect, useState } from "react";
import type { Replay } from "./types/replay";

// The Godot canvas plays this exact file (web/public/replay/penn_replay.json,
// written by backend/penn/generate_penn_replay.py); the companion panel reads the same
// data rather than scraping state out of the WASM. BASE_URL keeps it correct if
// the app is ever served under a sub-path.
const REPLAY_URL = `${import.meta.env.BASE_URL}replay/penn_replay.json`;

export type ReplayState =
  | { status: "loading"; replay: null; error: null }
  | { status: "ready"; replay: Replay; error: null }
  | { status: "error"; replay: null; error: string };

/** Fetch the replay JSON once on mount. */
export function useReplay(): ReplayState {
  const [state, setState] = useState<ReplayState>({
    status: "loading",
    replay: null,
    error: null,
  });

  useEffect(() => {
    let cancelled = false;
    (async () => {
      try {
        const res = await fetch(REPLAY_URL);
        if (!res.ok) throw new Error(`HTTP ${res.status} fetching ${REPLAY_URL}`);
        const replay = (await res.json()) as Replay;
        if (!cancelled) setState({ status: "ready", replay, error: null });
      } catch (err) {
        if (!cancelled) {
          setState({
            status: "error",
            replay: null,
            error: err instanceof Error ? err.message : String(err),
          });
        }
      }
    })();
    return () => {
      cancelled = true;
    };
  }, []);

  return state;
}

declare global {
  interface Window {
    /** Registered below; viewer.gd calls it each time the step changes. */
    __pennReplayStep?: (step: number) => void;
  }
}

/**
 * The current replay step to display. Godot is the source of truth: viewer.gd
 * calls `window.__pennReplayStep(i)` whenever the integer step changes, keeping the
 * panel exactly in sync with the canvas.
 */
export function useReplayStep(totalSteps: number): number {
  const [step, setStep] = useState(0);

  useEffect(() => {
    if (totalSteps <= 0) return;
    const clamp = (n: number) => Math.max(0, Math.min(totalSteps - 1, Math.floor(n)));
    window.__pennReplayStep = (n: number) => setStep(clamp(n));
    return () => {
      if (window.__pennReplayStep) delete window.__pennReplayStep;
    };
  }, [totalSteps]);

  return step;
}
