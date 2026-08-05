/**
 * The public repository, in one place: the hero's Code button, the BibTeX
 * `url`, and the "Run locally" pointer all have to name the same thing, and
 * HomeView can't own it without a cycle (it imports RunLocallySection).
 *
 * Private until the public code package publishes on 2026-08-14 (#884).
 */
export const REPO_URL = "https://github.com/ccb/agent-sandbox";
