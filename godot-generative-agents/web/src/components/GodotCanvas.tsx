import { useEffect, useRef, useState } from "react";

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
      existing.addEventListener("error", () => reject(new Error("Failed to load the Godot engine")));
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
    <div className="godot-canvas-wrap">
      <canvas ref={canvasRef} id="canvas" className="godot-canvas">
        Your browser does not support the canvas element.
      </canvas>
      {status && <div className="godot-status">{status}</div>}
    </div>
  );
}
