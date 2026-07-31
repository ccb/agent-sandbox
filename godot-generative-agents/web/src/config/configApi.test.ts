import { describe, expect, it, vi } from "vitest";
import type { ConfigSurface } from "../types/config";
import { fetchConfig, startRun } from "./configApi";

const surface = (status: "configurable" | "locked"): ConfigSurface => ({
  status,
  personas: [{ id: "maya", name: "Maya" }],
  cast: ["maya"],
  knobs: { defaults: {}, current: {} },
  brains: ["mock", "scripted"],
  plans: ["auto", "schedule", "llm"],
  efforts: ["default"],
  models: ["claude-haiku-4-5-20251001"],
  run: {
    brain: "mock",
    plan: "schedule",
    plan_request: "auto",
    effort: "default",
    model: "claude-haiku-4-5-20251001",
    steps: 1200,
    max_cost: 0,
    tick_seconds: 0.1,
  },
});

const jsonResponse = (body: unknown, status = 200): Response =>
  new Response(JSON.stringify(body), { status, headers: { "Content-Type": "application/json" } });

describe("fetchConfig", () => {
  it("maps a configurable surface", async () => {
    const f = vi.fn().mockResolvedValue(jsonResponse(surface("configurable")));
    const r = await fetchConfig("http://x", f as unknown as typeof fetch);
    expect(r.status).toBe("configurable");
    expect(r.surface?.brains).toEqual(["mock", "scripted"]);
    expect(f).toHaveBeenCalledWith("http://x/config");
  });

  it("maps a locked surface", async () => {
    const f = vi.fn().mockResolvedValue(jsonResponse(surface("locked")));
    expect((await fetchConfig("http://x", f as unknown as typeof fetch)).status).toBe("locked");
  });

  it("maps 404 to unavailable", async () => {
    const f = vi.fn().mockResolvedValue(new Response("", { status: 404 }));
    expect((await fetchConfig("http://x", f as unknown as typeof fetch)).status).toBe(
      "unavailable",
    );
  });

  it("maps a transport throw to error", async () => {
    const f = vi.fn().mockRejectedValue(new Error("down"));
    expect((await fetchConfig("http://x", f as unknown as typeof fetch)).status).toBe("error");
  });
});

describe("startRun", () => {
  it("POSTs /config then /resume and returns ok", async () => {
    const f = vi
      .fn()
      .mockResolvedValueOnce(jsonResponse({ applied: {} }))
      .mockResolvedValueOnce(new Response("", { status: 200 }));
    const r = await startRun("http://x", { cast: ["maya"] }, f as unknown as typeof fetch);
    expect(r).toEqual({ ok: true });
    expect(f.mock.calls[0][0]).toBe("http://x/config");
    expect(f.mock.calls[0][1]?.method).toBe("POST");
    expect(f.mock.calls[1][0]).toBe("http://x/resume");
  });

  it("surfaces a 400 from /config and never calls /resume", async () => {
    const f = vi.fn().mockResolvedValueOnce(jsonResponse({ detail: "cast: empty" }, 400));
    const r = await startRun("http://x", { cast: [] }, f as unknown as typeof fetch);
    expect(r).toEqual({ ok: false, stage: "config", status: 400, detail: "cast: empty" });
    expect(f).toHaveBeenCalledTimes(1);
  });

  it("surfaces a 409 from /config and never calls /resume", async () => {
    const f = vi.fn().mockResolvedValueOnce(jsonResponse({ detail: "already started" }, 409));
    const r = await startRun("http://x", { cast: ["maya"] }, f as unknown as typeof fetch);
    expect(r).toMatchObject({ ok: false, stage: "config", status: 409 });
    expect(f).toHaveBeenCalledTimes(1);
  });
});
