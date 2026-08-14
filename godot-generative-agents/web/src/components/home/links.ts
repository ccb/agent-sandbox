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

/**
 * The branch the public reads. Deploys come off `prod`, but GitHub's *default*
 * branch is `main` — so a bare repo URL lands a reader on `main`, and every link
 * to a tree or a file has to name `prod` itself. Build them with the two helpers
 * below rather than by hand, so a new link can't forget the branch;
 * `links.test.ts` fails if one does.
 *
 * The BibTeX `url` names the branch too (`repoTree`), reversing an earlier call
 * that a citation should cite the repository rather than a branch that may not
 * exist in five years. A bare repo URL sends a reader to `main`, which is not
 * the work being cited — a wrong-branch citation is a worse failure than a
 * someday-stale one, and `main` going away would break the bare URL anyway.
 */
const BRANCH = "prod";

/** The repository as a reader should browse it. */
export const repoTree = `${REPO_URL}/tree/${BRANCH}`;

/** One file, at a repo-relative path: `repoFile("godot-generative-agents/README.md")`. */
export const repoFile = (path: string) => `${REPO_URL}/blob/${BRANCH}/${path}`;
