import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

// Godot's threaded WASM export only runs on a *cross-origin isolated* page, which
// requires these two response headers. We set them on both the dev server and
// `vite preview`. They're harmless for a single-threaded export. Everything the
// page loads (the engine, the .pck, the replay JSON) is served from this same
// origin, so COEP `require-corp` is satisfied without extra per-asset headers.
const crossOriginIsolation = {
  "Cross-Origin-Opener-Policy": "same-origin",
  "Cross-Origin-Embedder-Policy": "require-corp",
};

export default defineConfig({
  plugins: [react()],
  server: { headers: crossOriginIsolation },
  preview: { headers: crossOriginIsolation },
});
