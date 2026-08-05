/**
 * The public repository, in one place: the hero's Code button, the BibTeX
 * `url`, and the "Run locally" pointer all have to name the same thing, and
 * HomeView can't own it without a cycle (it imports RunLocallySection).
 *
 * It is THIS repository: the plan of record (#875, updated 2026-08-04) flips
 * this one public on Aug 14 rather than exporting a standalone one, so the
 * citation points here. Private until #884 flips visibility.
 */
export const REPO_URL = "https://github.com/ccb/agent-sandbox";
