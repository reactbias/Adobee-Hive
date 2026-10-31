import { afterEach, describe, expect, it, vi } from "vitest";
import { api, OFFLINE } from "./api";

describe("api", () => {
  it("tells the backend the app's language, so the agent answers in it", async () => {
    document.documentElement.lang = "fr";
    const fetchMock = vi.spyOn(globalThis, "fetch").mockResolvedValue(new Response("{}"));
    await api.health();
    const headers = new Headers(fetchMock.mock.calls[0][1]?.headers);
    expect(headers.get("Accept-Language")).toBe("fr");
  });
});

// Render's free backend sleeps: the first request after a while can fail or hang. The chat retries once, then says
// so in the person's language instead of a raw "Failed to fetch".

const ok = (body: unknown) => ({ ok: true, json: async () => body }) as Response;

describe("calling the backend", () => {
  afterEach(() => vi.unstubAllGlobals());

  it("retries once when the backend is waking up", async () => {
    const fetch = vi
      .fn()
      .mockRejectedValueOnce(new TypeError("Failed to fetch"))
      .mockResolvedValueOnce(ok({ status: "ok" }));
    vi.stubGlobal("fetch", fetch);
    await expect(api.health()).resolves.toEqual({ status: "ok" });
    expect(fetch).toHaveBeenCalledTimes(2);
  });

  it("retries a gateway error from a cold start", async () => {
    const fetch = vi
      .fn()
      .mockResolvedValueOnce({ ok: false, status: 503, statusText: "", json: async () => ({}) } as Response)
      .mockResolvedValueOnce(ok({ status: "ok" }));
    vi.stubGlobal("fetch", fetch);
    await expect(api.health()).resolves.toEqual({ status: "ok" });
  });

  it("gives up with a message the page can translate", async () => {
    vi.stubGlobal("fetch", vi.fn().mockRejectedValue(new TypeError("Failed to fetch")));
    await expect(api.health()).rejects.toThrow(OFFLINE);
  });

  it("does not retry a request the backend refused", async () => {
    const fetch = vi
      .fn()
      .mockResolvedValue({ ok: false, status: 400, statusText: "", json: async () => ({ detail: "Ask a question." }) });
    vi.stubGlobal("fetch", fetch);
    await expect(api.health()).rejects.toThrow("Ask a question.");
    expect(fetch).toHaveBeenCalledTimes(1);
  });
});
