import { createRoot } from "react-dom/client";
import App from "./App";
import "./index.css";

// NOTE: intentionally NOT wrapped in <StrictMode>. StrictMode double-invokes
// effects in development, which would boot the Godot engine twice onto the same
// canvas. The future companion-app UI can opt back into StrictMode around its own
// (non-Godot) components if it wants the extra checks.
const root = document.getElementById("root");
if (!root) throw new Error("Missing #root element");
createRoot(root).render(<App />);
