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
 * Stop the engine's `focus()` calls from taking the surrounding page over.
 *
 * The engine focuses the canvas on every press, and while an in-game text field
 * holds focus, its browser IME shim re-focuses a hidden `contenteditable` div it
 * appends beside the canvas — every 100 ms, on an interval it never clears. When
 * that div blurs the shim hands focus straight back to the canvas, at which point
 * the still-focused field re-arms the shim: a loop the page cannot win.
 *
 * On the landing page the canvas sits inside a long article, where that costs the
 * reader their scroll position (the canvas gets scrolled back into view) and any
 * drag-selection, which dies the moment focus moves mid-gesture. A double-click
 * still selects, being atomic — which is exactly how the bug presented.
 *
 * So two rules for the engine's focus calls, applied to the elements it targets:
 * never scroll (`preventScroll` is the platform's own opt-out, which the engine
 * doesn't pass), and don't focus at all while `blocked()` — the reader is working
 * somewhere else on the page. Both live on elements we own or that the engine
 * appends to ours, so the engine bundle stays untouched.
 */
export function tameFocus(el: { focus: (options?: FocusOptions) => void }, blocked: () => boolean) {
  const focus = el.focus.bind(el);
  el.focus = (options?: FocusOptions) => {
    if (blocked()) return;
    focus({ ...options, preventScroll: true });
  };
}

/**
 * The drawing-buffer size for a canvas box of the given CSS size (#942).
 *
 * The engine maps pointer input linearly across the canvas element's rect
 * (GodotInput.computePosition: `(clientX - rect.x) * canvas.width / rect.width`),
 * so the buffer MUST be exactly the box's shape — an object-fit letterbox
 * between the two lands every click beside the UI it aims at. We therefore own
 * both sides: the CSS box (GodotCanvas.module.css) and this buffer, kept in
 * step by a ResizeObserver below. × devicePixelRatio so one buffer pixel is
 * one device pixel; floored to whole pixels; never 0 (a hidden box must not
 * kill the GL context).
 */
export function bufferSize(
  cssWidth: number,
  cssHeight: number,
  pixelRatio: number,
): [number, number] {
  return [
    Math.max(1, Math.floor(cssWidth * pixelRatio)),
    Math.max(1, Math.floor(cssHeight * pixelRatio)),
  ];
}

export function GodotCanvas() {
  const canvasRef = useRef<HTMLCanvasElement>(null);
  const wrapRef = useRef<HTMLDivElement>(null);
  const [status, setStatus] = useState("Loading engine…");

  useEffect(() => {
    let engine: GodotEngine | undefined;
    let cancelled = false;
    let resizeObserver: ResizeObserver | undefined;

    // Latched, not per-gesture: once the reader presses outside the demo they're
    // reading the page, and the engine has no business pulling focus back until
    // they press inside it again. Registered here rather than at module scope so
    // the click that mounted us — on the "Open the replay demo" button, which the
    // canvas replaces — isn't the press it latches on.
    let readerIsElsewhere = false;
    const onPointerDown = (e: PointerEvent) => {
      readerIsElsewhere = !wrapRef.current?.contains(e.target as Node);
    };
    document.addEventListener("pointerdown", onPointerDown, true);

    (async () => {
      try {
        await loadEngineScript();
        if (cancelled) return;
        const canvas = canvasRef.current;
        const wrap = wrapRef.current;
        if (!canvas || !wrap || !window.Engine) return;
        tameFocus(canvas, () => readerIsElsewhere);

        // Keep the buffer at exactly the box's shape (#942) — set before
        // startGame so the first frame already has the right size, then follow
        // the box through layout changes. The engine's noResize branch adopts
        // whatever buffer the page sets and never writes the canvas CSS.
        const applyBufferSize = () => {
          const rect = wrap.getBoundingClientRect();
          const [w, h] = bufferSize(rect.width, rect.height, window.devicePixelRatio || 1);
          if (canvas.width !== w) canvas.width = w;
          if (canvas.height !== h) canvas.height = h;
        };
        applyBufferSize();
        resizeObserver = new ResizeObserver(applyBufferSize);
        resizeObserver.observe(wrap);

        engine = new window.Engine({
          // Base path for the engine's sibling files (index.wasm, index.pck, …).
          executable: `${GODOT_BASE}/index`,
          mainPack: `${GODOT_BASE}/index.pck`,
          canvas,
          // 0 = the page owns the canvas size — both the CSS box and the
          // drawing buffer (applyBufferSize above). Policy 2 sized the buffer
          // to the WINDOW while the box was the stage, and the object-fit
          // letterbox that papered over the mismatch offset every click (#942).
          canvasResizePolicy: 0,
          focusCanvas: true,
          onProgress: (current: number, total: number) => {
            if (!cancelled && total > 0) {
              setStatus(`Loading… ${Math.round((current / total) * 100)}%`);
            }
          },
        });
        setStatus("Starting…");
        await engine.startGame();
        // The IME div only exists once the engine's display server is up. It's the
        // shim's 100 ms timer that targets this one, so taming it is what actually
        // breaks the loop; taming the canvas above stops the handover that re-arms it.
        const ime = canvas.parentElement?.querySelector<HTMLElement>("div.ime");
        if (ime) tameFocus(ime, () => readerIsElsewhere);
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
      document.removeEventListener("pointerdown", onPointerDown, true);
      resizeObserver?.disconnect();
      try {
        engine?.requestQuit?.();
      } catch {
        /* engine may not have started; ignore */
      }
    };
  }, []);

  return (
    <div ref={wrapRef} className={styles.wrap}>
      <canvas ref={canvasRef} id="canvas" className={styles.canvas}>
        Your browser does not support the canvas element.
      </canvas>
      {status && <div className={styles.status}>{status}</div>}
    </div>
  );
}
