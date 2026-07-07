import { useEffect, useRef } from "react";

// The agents on the campus map are all the one Cute Fantasy "Player" sheet, told
// apart by a per-persona colour (Godot `modulate`). This shows each agent's
// on-map sprite on its card: frame 0 (the front-facing idle pose, top-left of the
// sheet) tinted with that same colour, so the card portrait matches the canvas.
//
// The sheet is a 6×10 grid of 32×32 frames (web/public/sprites/player.png, a copy
// of scripts/viewer.gd's player_sheet). We draw at native 32×32 and let CSS
// scale the <canvas> up with image-rendering: pixelated, so the pixel art stays
// crisp at any size.
const SHEET_URL = `${import.meta.env.BASE_URL}sprites/player.png`;
const FRAME = 32;

// Per-persona tints, mirroring viewer.gd's TINTS array (indexed by persona
// order) so a card's portrait is the same colour as that agent on the map. Godot
// `modulate` multiplies the sprite by this colour; we reproduce that below.
export const SPRITE_TINTS = [
  "#fff2f2", // Maya  — warm white   (Godot Color(1.0, 0.95, 0.95))
  "#b3d1ff", // Ellis — blue         (Godot Color(0.70, 0.82, 1.0))
  "#ccffc7", // Diego — green        (Godot Color(0.80, 1.0, 0.78))
  "#ffdbb3", // spare — orange       (Godot Color(1.0, 0.86, 0.70))
];

// One shared, cached load of the sheet — every card draws the same image.
let sheetPromise: Promise<HTMLImageElement> | null = null;
function loadSheet(): Promise<HTMLImageElement> {
  if (!sheetPromise) {
    sheetPromise = new Promise((resolve, reject) => {
      const img = new Image();
      img.onload = () => resolve(img);
      img.onerror = () => reject(new Error(`could not load ${SHEET_URL}`));
      img.src = SHEET_URL;
    });
  }
  return sheetPromise;
}

export function SpritePreview({
  index,
  className,
}: {
  /** Persona index — picks the tint, matching the agent's colour on the map. */
  index: number;
  className?: string;
}) {
  const canvasRef = useRef<HTMLCanvasElement>(null);
  const tint = SPRITE_TINTS[index % SPRITE_TINTS.length];

  useEffect(() => {
    let cancelled = false;
    loadSheet()
      .then((img) => {
        if (cancelled) return;
        const canvas = canvasRef.current;
        if (!canvas) return;
        const ctx = canvas.getContext("2d");
        if (!ctx) return;

        ctx.clearRect(0, 0, FRAME, FRAME);
        ctx.imageSmoothingEnabled = false;
        // Frame 0 = the top-left 32×32 cell (front-facing idle, the pose Godot
        // shows a standing agent).
        ctx.drawImage(img, 0, 0, FRAME, FRAME, 0, 0, FRAME, FRAME);
        // Tint exactly like Godot's modulate: multiply the sprite by the tint,
        // then mask back to the sprite's own alpha so the surround stays clear.
        ctx.globalCompositeOperation = "multiply";
        ctx.fillStyle = tint;
        ctx.fillRect(0, 0, FRAME, FRAME);
        ctx.globalCompositeOperation = "destination-in";
        ctx.drawImage(img, 0, 0, FRAME, FRAME, 0, 0, FRAME, FRAME);
        ctx.globalCompositeOperation = "source-over";
      })
      .catch(() => {
        /* No sprite (e.g. asset missing) — the card just shows an empty frame. */
      });
    return () => {
      cancelled = true;
    };
  }, [tint]);

  return (
    <canvas
      ref={canvasRef}
      width={FRAME}
      height={FRAME}
      className={className}
      aria-hidden="true"
    />
  );
}
