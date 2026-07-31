// The GET/POST /config + POST /resume calls behind the setup view, as pure
// async functions with an injectable `fetch` so they test in plain Node without
// jsdom (the package's convention). The hook and component are thin wrappers.

import type { ConfigStatus, ConfigSurface, PostConfigBody } from "../types/config";

export type FetchLike = typeof fetch;

export interface FetchConfigResult {
  status: ConfigStatus; // configurable | locked | unavailable | error
  surface?: ConfigSurface;
  detail?: string;
}

// Read GET /config and classify it. A 404 means this server has no config
// surface (storeless / no controller) → the setup view never shows.
export async function fetchConfig(
  base: string,
  fetchImpl: FetchLike = fetch,
): Promise<FetchConfigResult> {
  let res: Response;
  try {
    res = await fetchImpl(`${base}/config`);
  } catch (e) {
    return { status: "error", detail: String(e) };
  }
  if (res.status === 404) return { status: "unavailable" };
  if (!res.ok) return { status: "error", detail: `HTTP ${res.status}` };
  let surface: ConfigSurface;
  try {
    surface = (await res.json()) as ConfigSurface;
  } catch {
    return { status: "error", detail: "bad JSON" };
  }
  return { status: surface.status === "configurable" ? "configurable" : "locked", surface };
}

export type StartResult =
  | { ok: true }
  | { ok: false; stage: "config" | "resume"; status?: number; detail?: string };

// Start: POST /config, then — only on success — POST /resume. A failed /config
// (400 bad input / 409 already started) short-circuits so the run never resumes
// on a rejected setup.
export async function startRun(
  base: string,
  body: PostConfigBody,
  fetchImpl: FetchLike = fetch,
): Promise<StartResult> {
  let cfg: Response;
  try {
    cfg = await fetchImpl(`${base}/config`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(body),
    });
  } catch (e) {
    return { ok: false, stage: "config", detail: String(e) };
  }
  if (!cfg.ok)
    return { ok: false, stage: "config", status: cfg.status, detail: await readDetail(cfg) };

  let res: Response;
  try {
    res = await fetchImpl(`${base}/resume`, { method: "POST" });
  } catch (e) {
    return { ok: false, stage: "resume", detail: String(e) };
  }
  if (!res.ok)
    return { ok: false, stage: "resume", status: res.status, detail: await readDetail(res) };
  return { ok: true };
}

// FastAPI puts the human message on `detail`; fall back to the status code.
async function readDetail(res: Response): Promise<string> {
  try {
    const j = (await res.json()) as { detail?: unknown };
    return typeof j.detail === "string" ? j.detail : `HTTP ${res.status}`;
  } catch {
    return `HTTP ${res.status}`;
  }
}
