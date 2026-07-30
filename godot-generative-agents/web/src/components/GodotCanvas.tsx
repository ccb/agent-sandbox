import { useEffect, useRef, useState } from "react";
import styles from "./GodotCanvas.module.css";

// The Godot Web export ships an `index.js` that defines a global `Engine` class.
// We load it at runtime (the file only exists after `npm run export:godot`) and
// instantiate the engine onto our own <canvas>. Embedding the canvas in a React
// component (rather than an <iframe>) keeps the future companion-app panels in the
// same DOM/CSS and leaves room for JS<->Godot messaging via JavaScriptBridge.
type GodotEngine = {
  startGame: (override?: Record<string, unknown>) => Promise<void>;
  requestQuit?: () => void;
};
type GodotEngineCtor = new (config: Record<string, unknown>) => GodotEngine;

declare global {
  interface Window {
    Engine?: GodotEngineCtor;
  }
}

// Where the export script writes the build (served by Vite from `public/`).
const GODOT_BASE = "/godot";

function loadEngineScript(): Promise<void> {
  if (window.Engine) return Promise.resolve();
  return new Promise<void>((resolve, reject) => {
    const existing = document.querySelector<HTMLScriptElement>("script[data-godot-engine]");
    if (existing) {
      existing.addEventListener("load", () => resolve());
      existing.addEventListener("error", () =>
        reject(new Error("Failed to load the Godot engine")),
      );
      return;
    }
    const script = document.createElement("script");
    script.src = `${GODOT_BASE}/index.js`;
    script.dataset.godotEngine = "true";
    script.onload = () => resolve();
    script.onerror = () =>
      reject(new Error(`Could not load ${script.src} — run "npm run export:godot" first.`));
    document.body.appendChild(script);
  });
}

/**
 * Pin `preventScroll` onto an element's own `focus()`.
 *
 * The engine focuses the canvas on every press, and while an in-game text field
 * holds focus it re-focuses a hidden `contenteditable` div it appends beside the
 * canvas. On the landing page the canvas sits inside a long scrolling article,
 * so each of those calls scrolls the reader back to the demo. `preventScroll` is
 * the platform's own opt-out and the engine never passes it — so pin it on here,
 * which covers every call site inside the engine without patching its bundle.
 */
export function focusWithoutScroll(el: { focus: (options?: FocusOptions) => void }) {
  const focus = el.focus.bind(el);
  el.focus = (options?: FocusOptions) => focus({ ...options, preventScroll: true });
}

export function GodotCanvas() {
  const canvasRef = useRef<HTMLCanvasElement>(null);
  const [status, setStatus] = useState("Loading engine…");

  useEffect(() => {
    let engine: GodotEngine | undefined;
    let cancelled = false;

    (async () => {
      try {
        await loadEngineScript();
        if (cancelled) return;
        const canvas = canvasRef.current;
        if (!canvas || !window.Engine) return;
        focusWithoutScroll(canvas);

        engine = new window.Engine({
          // Base path for the engine's sibling files (index.wasm, index.pck, …).
          executable: `${GODOT_BASE}/index`,
          mainPack: `${GODOT_BASE}/index.pck`,
          canvas,
          // 2 = adapt the framebuffer to the canvas element's CSS size.
          canvasResizePolicy: 2,
          focusCanvas: true,
          onProgress: (current: number, total: number) => {
            if (!cancelled && total > 0) {
              setStatus(`Loading… ${Math.round((current / total) * 100)}%`);
            }
          },
        });
        setStatus("Starting…");
        await engine.startGame();
        // The IME div only exists once the engine's display server is up.
        //
        // ponytail: this takes the *scroll* out of the engine's focus calls, not
        // the focus grab itself — Godot's IME shim re-focuses this div every
        // 100 ms and never clears that timer on blur, so a reader who clicks
        // into a text field inside the demo still loses selections made
        // elsewhere on the page until they click back out of it. The menu no
        // longer focuses a field on its own (main_menu.gd), which is what made
        // this reachable without asking. If it starts to matter, drop the timer
        // by patching the export shell rather than guessing from out here.
        const ime = canvas.parentElement?.querySelector<HTMLElement>("div.ime");
        if (ime) focusWithoutScroll(ime);
        if (!cancelled) setStatus("");
      } catch (err) {
        if (!cancelled) {
          console.error(err);
          setStatus(err instanceof Error ? err.message : String(err));
        }
      }
    })();

    return () => {
      cancelled = true;
      try {
        engine?.requestQuit?.();
      } catch {
        /* engine may not have started; ignore */
      }
    };
  }, []);

  return (
    <div className={styles.wrap}>
      <canvas ref={canvasRef} id="canvas" className={styles.canvas}>
        Your browser does not support the canvas element.
      </canvas>
      {status && <div className={styles.status}>{status}</div>}
    </div>
  );
}
