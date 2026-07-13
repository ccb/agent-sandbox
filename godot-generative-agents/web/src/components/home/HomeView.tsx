import "./home.css";

// The repository this companion lives in — used in the citation block below.
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
