import { Analytics } from "@vercel/analytics/react";
import { createRoot } from "react-dom/client";
import App from "./App";
import "./index.css";

// NOTE: intentionally NOT wrapped in <StrictMode>. StrictMode double-invokes
// effects in development, which would boot the Godot engine twice onto the same
// canvas. The future companion-app UI can opt back into StrictMode around its own
// (non-Godot) components if it wants the extra checks.
const root = document.getElementById("root");
if (!root) throw new Error("Missing #root element");
// <Analytics /> only in a production build (#961): it is first-party on Vercel
// (/_vercel/insights/script.js), which is the one thing `COEP: require-corp`
// allows — but in dev the package swaps in a cross-origin debug script that COEP
// would block, so gating on PROD keeps `pnpm dev` console-clean.
createRoot(root).render(
  <>
    <App />
    {import.meta.env.PROD ? <Analytics /> : null}
  </>,
);
