import { useEffect, useRef, useState } from "react";
import type { Replay } from "./types/replay";

// The Godot canvas plays this exact file (web/public/replay/penn_replay.json,
// written by backend/penn/generate_penn_replay.py); the companion panel reads the same
// data rather than scraping state out of the WASM. BASE_URL keeps it correct if
// the app is ever served under a sub-path.
const REPLAY_URL = `${import.meta.env.BASE_URL}replay/penn_replay.json`;

// Real seconds Godot spends per sim step (viewer.gd's `step_seconds`). Used
// only by the fallback clock below, for when Godot isn't driving the step.
const PLAYBACK_STEP_SECONDS = 0.1;

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
 * panel exactly in sync with the canvas. If those calls never arrive (e.g. the WASM
 * was exported before that bridge existed), a fallback clock drives the step at the
 * same playback rate so the panel still animates on its own.
 */
export function useReplayStep(totalSteps: number): number {
  const [step, setStep] = useState(0);
  const bridgeSeen = useRef(false);

  useEffect(() => {
    if (totalSteps <= 0) return;
    const clamp = (n: number) => Math.max(0, Math.min(totalSteps - 1, Math.floor(n)));

    window.__pennReplayStep = (n: number) => {
      bridgeSeen.current = true;
      setStep(clamp(n));
    };

    // Fallback clock. Start only after a short beat — if Godot's bridge is wired,
    // it pushes a step within the first frame and this never runs. Once any bridge
    // call has arrived, we stop ticking and let Godot stay authoritative.
    let raf = 0;
    let start: number | null = null;
    const tick = (t: number) => {
      if (bridgeSeen.current) return;
      if (start === null) start = t;
      setStep(clamp((t - start) / 1000 / PLAYBACK_STEP_SECONDS));
      raf = requestAnimationFrame(tick);
    };
    const startTimer = window.setTimeout(() => {
      if (!bridgeSeen.current) raf = requestAnimationFrame(tick);
    }, 1000);

    return () => {
      if (window.__pennReplayStep) delete window.__pennReplayStep;
      window.clearTimeout(startTimer);
      if (raf) cancelAnimationFrame(raf);
    };
  }, [totalSteps]);

  return step;
}
