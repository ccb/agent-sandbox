// ---------------------------------------------------------------------------
// #879: for the public launch the landing page is the ONLY view. Commented out
// below (not deleted — uncomment as one piece to get the multi-view dev app
// back):
//   (1) the live dashboard (#llm) and its agent-card modal, and the live-backend
//       poll + replay-step ownership that exist only to feed them,
//   (2) the Docs link out to the static MkDocs site,
//   (3) the whole header / nav bar,
//   (4) the standalone game page (#game) — the Godot replay now sits inside the
//       landing page itself, as a figure with an enlarge button (see
//       ReplayFigure in components/home/HomeView.tsx).
// The CSS for all four is left untouched in App.css so uncommenting just works.
// The retired JSX is commented with `//` inside empty `{ }` containers, because a
// `{/* */}` wrapper would be terminated early by the JSX comments nested in it.
// ---------------------------------------------------------------------------
// import { Activity, FileText, Gamepad2, Home, Menu } from "lucide-react";
// import { type ReactNode, useEffect, useRef, useState } from "react";
// import { AgentCardModal } from "./components/AgentCardModal";
// import { GodotCanvas } from "./components/GodotCanvas";
import { HomeView } from "./components/home/HomeView";
// import { LlmDashboard } from "./components/LlmDashboard";
// import { setUrlParam } from "./url";
// import { initialApiBase, useLive } from "./useLive";
// import { useReplay, useReplayStep } from "./useReplay";
import "./App.css";

// type View = "home" | "game" | "llm";
//
// // Pages selected by the URL hash (#home / #game / #llm) so each is a real,
// // shareable location and the back button works — no router needed. The
// // Nerfies-style project page is the landing view; every other view is one
// // explicit hop away via the menu. Two retired hashes fall through to the landing
// // page: `#agents` (the old agent-cards page, folded into the live dashboard in
// // #528) and `#prompts` (the prompt-chain visualizer, now a figure on the landing
// // page itself), so existing links still land somewhere sensible.
// function viewFromHash(): View {
//   const hash = window.location.hash.replace("#", "");
//   if (hash === "game") return "game";
//   if (hash === "llm" || hash === "agents") return "llm";
//   return "home";
// }
//
// // Menu icons: lucide line icons sized to the nav's 16px. Each is monochrome and
// // strokes in `currentColor`, so it inherits its menu item's text colour — dark
// // normally, white when the item is active.
// const ICON_HOME = <Home className="nav-icon" size={16} aria-hidden />;
// const ICON_GAME = <Gamepad2 className="nav-icon" size={16} aria-hidden />;
// const ICON_LLM = <Activity className="nav-icon" size={16} aria-hidden />;
// const ICON_DOCS = <FileText className="nav-icon" size={16} aria-hidden />;
//
// // The navigable views, grouped into labeled sections for the dropdown menu.
// interface NavItem {
//   view: View;
//   label: string;
//   icon: ReactNode;
// }
// const NAV_SECTIONS: { heading: string; items: NavItem[] }[] = [
//   {
//     heading: "Game",
//     items: [
//       { view: "game", label: "Game view", icon: ICON_GAME },
//       { view: "llm", label: "Live dashboard", icon: ICON_LLM },
//     ],
//   },
// ];

export default function App() {
  // const { status, replay } = useReplay();
  // // The live backend: one handshake + one feed poll, shared by the live dashboard
  // // and the agent-card modal. The target starts from ?api= / VITE_SIM_API_URL and
  // // can also be supplied at runtime by the dashboard's connect form (#519).
  // const [apiUrl, setApiUrl] = useState<string | null>(initialApiBase);
  // const live = useLive(apiUrl);
  //
  // // Connecting via the form is the same as arriving with ?api= — the URL is
  // // updated to match (no reload), so a refresh or a shared link sticks.
  // const connectApi = (url: string) => {
  //   const clean = url.trim().replace(/\/+$/, "");
  //   if (!clean) return;
  //   setUrlParam("api", clean);
  //   setApiUrl(clean);
  // };
  //
  // // The open agent-card modal (#528): clicking a dashboard cell opens that
  // // agent's card, deep-linked via ?agent=<name> so a refresh or a shared link
  // // reopens it. The one-shot mount read mirrors initialApiBase; the writes are
  // // the second caller of setUrlParam (#522). AgentCardModal self-gates on the
  // // roster, so a stale name just renders nothing.
  // const [selectedAgent, setSelectedAgent] = useState<string | null>(() =>
  //   new URLSearchParams(window.location.search).get("agent"),
  // );
  // const openAgent = (name: string) => {
  //   setSelectedAgent(name);
  //   setUrlParam("agent", name);
  // };
  // const closeAgent = () => {
  //   setSelectedAgent(null);
  //   setUrlParam("agent", null);
  // };
  //
  // const [view, setView] = useState<View>(viewFromHash);
  // const [menuOpen, setMenuOpen] = useState(false);
  // const menuRef = useRef<HTMLDivElement>(null);
  //
  // // The replay step has a SINGLE owner: useReplayStep registers one global
  // // window.__pennReplayStep and deletes it on unmount, so App holds it and hands
  // // it to both consumers (the dashboard's conversation feed and the agent-card
  // // modal), which only render on #llm. Gated on that view so the always-mounted
  // // Godot canvas's per-step callback doesn't re-render the app on other views;
  // // passing 0 elsewhere makes useReplayStep a no-op (it needs totalSteps > 0).
  // const replayStep = useReplayStep(view === "llm" ? (replay?.meta.steps ?? 0) : 0);
  //
  // useEffect(() => {
  //   const onHash = () => setView(viewFromHash());
  //   window.addEventListener("hashchange", onHash);
  //   return () => window.removeEventListener("hashchange", onHash);
  // }, []);
  //
  // // While the nav menu is open, close it on an outside click or Escape.
  // useEffect(() => {
  //   if (!menuOpen) return;
  //   const onDown = (e: MouseEvent) => {
  //     if (menuRef.current && !menuRef.current.contains(e.target as Node)) {
  //       setMenuOpen(false);
  //     }
  //   };
  //   const onKey = (e: KeyboardEvent) => {
  //     if (e.key === "Escape") setMenuOpen(false);
  //   };
  //   document.addEventListener("mousedown", onDown);
  //   document.addEventListener("keydown", onKey);
  //   return () => {
  //     document.removeEventListener("mousedown", onDown);
  //     document.removeEventListener("keydown", onKey);
  //   };
  // }, [menuOpen]);
  //
  // const select = (v: View) => {
  //   window.location.hash = v;
  //   setView(v);
  // };
  //
  // const currentLabel =
  //   view === "home"
  //     ? "Home"
  //     : (NAV_SECTIONS.flatMap((s) => s.items).find((i) => i.view === view)?.label ?? "Menu");

  return (
    <div className="app" data-view="home">
      {
        // (2) + (3) The header and its nav menu — including the Docs link out to
        // the static MkDocs site — are retired for the public launch.
        //
        // <header className="app-header">
        //   <div className="app-title">
        //     <h1>Penn Campus — Generative Agents</h1>
        //     <p className="app-sub">Godot replay, running in the browser</p>
        //   </div>
        //   <div className="header-actions">
        //     {/* Collapsed nav: the trigger shows the current view and opens a
        //         dropdown to switch. Keeps the header uncluttered as views grow. */}
        //     <div className="nav-menu" ref={menuRef}>
        //       <button
        //         type="button"
        //         className="nav-trigger"
        //         aria-haspopup="menu"
        //         aria-expanded={menuOpen}
        //         aria-label={`Navigate (current: ${currentLabel})`}
        //         onClick={() => setMenuOpen((open) => !open)}
        //       >
        //         <Menu className="nav-burger" size={18} aria-hidden />
        //       </button>
        //       {menuOpen && (
        //         <div className="nav-dropdown" role="menu" aria-label="Navigate">
        //           {/* The landing page sits on its own above the grouped views. */}
        //           <div className="nav-group" role="group">
        //             <button
        //               type="button"
        //               role="menuitem"
        //               className={`nav-item${view === "home" ? " is-active" : ""}`}
        //               onClick={() => {
        //                 select("home");
        //                 setMenuOpen(false);
        //               }}
        //             >
        //               {ICON_HOME}
        //               Home
        //             </button>
        //           </div>
        //           {NAV_SECTIONS.map((section) => (
        //             <div
        //               className="nav-group"
        //               key={section.heading}
        //               role="group"
        //               aria-label={section.heading}
        //             >
        //               <div className="nav-group-heading">{section.heading}</div>
        //               {section.items.map((item) => (
        //                 <button
        //                   key={item.view}
        //                   type="button"
        //                   role="menuitem"
        //                   className={`nav-item${view === item.view ? " is-active" : ""}`}
        //                   onClick={() => {
        //                     select(item.view);
        //                     setMenuOpen(false);
        //                   }}
        //                 >
        //                   {item.icon}
        //                   {item.label}
        //                 </button>
        //               ))}
        //             </div>
        //           ))}
        //           {/* (2) A link, not a view: it leaves the SPA for the static
        //               MkDocs site at /docs/ (build it with `pnpm gen:docs`).
        //               BASE_URL keeps it correct if the app's base path ever
        //               changes. */}
        //           <a
        //             className="nav-item nav-item--link"
        //             role="menuitem"
        //             href={`${import.meta.env.BASE_URL}docs/`}
        //           >
        //             {ICON_DOCS}
        //             Docs ↗
        //           </a>
        //         </div>
        //       )}
        //     </div>
        //   </div>
        // </header>
      }

      <main className="app-stage">
        {
          // (4) The Godot canvas used to stay mounted here at all times so the
          // engine never re-booted when you switched pages. It now mounts inside
          // the landing page's replay figure instead — one canvas, one engine,
          // and enlarging it is a CSS class so it never leaves the DOM.
          //
          // <section className="view view-game" aria-hidden={view !== "game"}>
          //   <GodotCanvas />
          // </section>
        }

        {
          // (1) The unified live page (#519 dashboard + #528 agent cards) and its
          // agent-card modal. Not part of the public launch (#879 non-goals).
          //
          // {view === "llm" && (
          //   <section className="view view-llm">
          //     {status === "loading" && !live.enabled ? (
          //       <div className="agents-placeholder">Loading agents…</div>
          //     ) : (
          //       <LlmDashboard
          //         replay={replay}
          //         live={live}
          //         replayStep={replayStep}
          //         onConnect={connectApi}
          //         onOpenAgent={openAgent}
          //       />
          //     )}
          //   </section>
          // )}
          //
          // {view === "llm" && selectedAgent && (
          //   <AgentCardModal
          //     name={selectedAgent}
          //     replay={replay}
          //     live={live}
          //     replayStep={replayStep}
          //     onClose={closeAgent}
          //   />
          // )}
        }

        {/* The landing page — the only view now. */}
        <section className="view view-home">
          <HomeView />
        </section>
      </main>
    </div>
  );
}
