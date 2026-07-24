import react from "@vitejs/plugin-react";
import { defineConfig, type Plugin } from "vite";

// Godot's threaded WASM export only runs on a *cross-origin isolated* page, which
// requires these two response headers. We set them on both the dev server and
// `vite preview`. They're harmless for a single-threaded export. Everything the
// page loads (the engine, the .pck, the replay JSON) is served from this same
// origin, so COEP `require-corp` is satisfied without extra per-asset headers.
const crossOriginIsolation = {
  "Cross-Origin-Opener-Policy": "same-origin",
  "Cross-Origin-Embedder-Policy": "require-corp",
};

// Serve the static MkDocs site (public/docs/, built by `pnpm gen:docs`) at /docs/
// in the dev server. Without this, Vite's SPA fallback answers extension-less
// URLs like /docs/ or /docs/api/agents/ with the React app's index.html, so the
// docs never show — you'd just see the app at a /docs/ URL. We rewrite those
// directory URLs to the real index.html file; registering the middleware in the
// hook body (not a returned function) runs it BEFORE Vite's internal middlewares,
// so the static-file middleware then serves the file instead of the SPA fallback.
// `vite preview` and production already resolve directory indexes, so this is
// only needed in dev.
function serveDocsInDev(): Plugin {
  return {
    name: "serve-docs-in-dev",
    configureServer(server) {
      // We only touch req.url (the path Vite routes on). This project has no
      // @types/node, so type just that field rather than pull one in.
      server.middlewares.use((req: { url?: string }, _res: unknown, next: () => void) => {
        if (req.url?.startsWith("/docs/") && req.url.endsWith("/")) {
          req.url += "index.html";
        }
        next();
      });
    },
  };
}

export default defineConfig({
  plugins: [react(), serveDocsInDev()],
  server: { headers: crossOriginIsolation },
  preview: { headers: crossOriginIsolation },
});
