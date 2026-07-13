// ReactNode is only used by the Icon component below, which is commented out
// together with the link buttons that use it. Re-enable this import when you
// re-enable that block.
// import type { ReactNode } from "react";
import "./home.css";

// The Paper / arXiv / Video / Code buttons in the hero are commented out for now
// (see the return below). Their inline SVG line-icons are commented out here
// along with them, since nothing else uses them. (The original Nerfies template
// pulls Font Awesome / Academicons from a CDN, which COOP/COEP would block —
// hence inlining.) Re-enable this block and the buttons together.
/*
function Icon({ children }: { children: ReactNode }) {
  return (
    <svg
      width="16"
      height="16"
      viewBox="0 0 24 24"
      fill="none"
      stroke="currentColor"
      strokeWidth="2"
      strokeLinecap="round"
      strokeLinejoin="round"
      aria-hidden="true"
    >
      {children}
    </svg>
  );
}

const PaperIcon = (
  <Icon>
    <path d="M14 3H7a2 2 0 0 0-2 2v14a2 2 0 0 0 2 2h10a2 2 0 0 0 2-2V8z" />
    <path d="M14 3v5h5" />
    <line x1="9" y1="13" x2="15" y2="13" />
    <line x1="9" y1="17" x2="15" y2="17" />
  </Icon>
);
const ArxivIcon = (
  <Icon>
    <path d="M22 10 12 5 2 10l10 5 10-5z" />
    <path d="M6 12v5c0 1 2.7 3 6 3s6-2 6-3v-5" />
  </Icon>
);
const VideoIcon = (
  <Icon>
    <circle cx="12" cy="12" r="9" />
    <polygon points="10 8 16 12 10 16" fill="currentColor" stroke="currentColor" />
  </Icon>
);
const CodeIcon = (
  <Icon>
    <path d="m9 18-6-6 6-6" />
    <path d="m15 6 6 6-6 6" />
  </Icon>
);
*/

// The repository this companion lives in — a sensible default for the Code link.
const REPO_URL = "https://github.com/ccb/agent-sandbox";

/**
 * The companion's landing page, styled after the Nerfies academic project-page
 * template (https://github.com/nerfies/nerfies.github.io). Everything below the
 * title / author list / abstract is placeholder content — swap in your own.
 */
export function HomeView() {
  return (
    <div className="nrf">
      {/* ===== Hero: title, authors, affiliations, links ===== */}
      <section className="nrf-hero">
        <div className="nrf-hero-body">
          <div className="nrf-container nrf-centered">
            {/* TODO: replace with your project title */}
            <h1 className="nrf-title nrf-title-1">
              Penn Campus: Generative Agents in a Simulated World
            </h1>
            {/* TODO: replace with your venue / program line */}
            <p className="nrf-venue">PURM 2026 · University of Pennsylvania</p>

            {/* TODO: replace with the real author names + links */}
            <div className="nrf-authors">
              <span className="nrf-author-block">
                <a href="#">Author One</a>,
              </span>{" "}
              <span className="nrf-author-block">
                <a href="#">Author Two</a>,
              </span>{" "}
              <span className="nrf-author-block">
                <a href="#">Author Three</a>,
              </span>{" "}
              <span className="nrf-author-block">
                <a href="#">Advisor Name</a>
              </span>
            </div>

            {/* Everyone shares one affiliation, so no superscripts are needed. */}
            <div className="nrf-affiliations">University of Pennsylvania</div>

            {/* Paper / arXiv / Video / Code links — commented out for now;
                re-enable (along with the Icon block at the top of this file)
                once the paper / arXiv / video URLs exist.

            <div className="nrf-links">
              <a className="nrf-button" href="#">
                {PaperIcon}
                <span>Paper</span>
              </a>
              <a className="nrf-button" href="#">
                {ArxivIcon}
                <span>arXiv</span>
              </a>
              <a className="nrf-button" href="#">
                {VideoIcon}
                <span>Video</span>
              </a>
              <a className="nrf-button" href={REPO_URL} target="_blank" rel="noreferrer">
                {CodeIcon}
                <span>Code</span>
              </a>
            </div>
            */}
          </div>
        </div>
      </section>

      {/* ===== Teaser placeholder + links into the live companion ===== */}
      <section className="nrf-teaser">
        <div className="nrf-container">
          <div className="nrf-teaser-box">Teaser figure or demo video goes here</div>
          {/* TODO: one-line description of the project */}
          <p className="nrf-subtitle nrf-centered nrf-teaser-cap">
            A one-sentence summary of the project goes here.
          </p>
          {/* These hop into the interactive views of this same companion. */}
          <div className="nrf-links">
            <a className="nrf-button" href="#llm">
              <span>Explore the agents →</span>
            </a>
            <a className="nrf-button" href="#game">
              <span>Open the live replay →</span>
            </a>
          </div>
        </div>
      </section>

      {/* ===== Abstract ===== */}
      <section className="nrf-section">
        <div className="nrf-container">
          <div className="nrf-narrow nrf-centered">
            <h2 className="nrf-title nrf-title-3">Abstract</h2>
            <div className="nrf-content nrf-justified">
              <p>
                This is a placeholder abstract. Describe the project here: the question you are
                asking, the system you built, and what makes it interesting. Keep it to a paragraph
                or two so a reader can grasp the contribution at a glance.
              </p>
              <p>
                Replace this text, the title, the author list, and the links above with your own.
                The interactive replay and agent views are one click away in the menu in the
                top-right corner.
              </p>
            </div>
          </div>
        </div>
      </section>

      {/* ===== Overview (placeholder) ===== */}
      <section className="nrf-section">
        <div className="nrf-container">
          <div className="nrf-narrow">
            <h2 className="nrf-title nrf-title-3 nrf-centered">Overview</h2>
            <div className="nrf-content nrf-justified">
              <p>
                Use sections like this one to walk through your method, show figures, or embed
                videos. Each section is just a heading and some content — add as many as you need.
              </p>
              <p>
                For implementation details and the API reference, see the{" "}
                <a href={`${import.meta.env.BASE_URL}docs/`}>project documentation</a>.
              </p>
            </div>
          </div>
        </div>
      </section>

      {/* ===== BibTeX ===== */}
      <section className="nrf-section" id="BibTeX">
        <div className="nrf-container nrf-content">
          <h2 className="nrf-title nrf-title-3">BibTeX</h2>
          {/* TODO: replace with your citation */}
          <pre className="nrf-pre">
            <code>{`@misc{placeholder2026,
  title  = {Penn Campus: Generative Agents in a Simulated World},
  author = {Author One and Author Two and Author Three and Advisor Name},
  year   = {2026},
  note   = {PURM, University of Pennsylvania},
  url    = {${REPO_URL}},
}`}</code>
          </pre>
        </div>
      </section>

      {/* ===== Footer: template attribution (as the Nerfies license asks) ===== */}
      <footer className="nrf-footer">
        <div className="nrf-container">
          <div className="nrf-content nrf-footer-content">
            <p>
              The design of this page is adapted from the{" "}
              <a href="https://github.com/nerfies/nerfies.github.io">Nerfies</a> project page. We
              thank the authors for releasing their{" "}
              <a href="https://github.com/nerfies/nerfies.github.io">source code</a>, which is
              licensed under a{" "}
              <a rel="license" href="http://creativecommons.org/licenses/by-sa/4.0/">
                Creative Commons Attribution-ShareAlike 4.0 International License
              </a>
              .
            </p>
          </div>
        </div>
      </footer>
    </div>
  );
}
