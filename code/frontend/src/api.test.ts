import { afterEach, describe, expect, it, vi } from "vitest";
import { api, ApiError, HealthError, OFFLINE, setOwnerToken } from "./api";

describe("api", () => {
  it("tells the backend the app's language, so the agent answers in it", async () => {
    document.documentElement.lang = "fr";
    const fetchMock = vi.spyOn(globalThis, "fetch").mockResolvedValue(new Response("{}"));
    await api.health();
    const headers = new Headers(fetchMock.mock.calls[0][1]?.headers);
    expect(headers.get("Accept-Language")).toBe("fr");
  });
});

describe("discovery reaches as far as the person asked, and no further", () => {
  afterEach(() => vi.unstubAllGlobals());

  it("asks for this Hive only unless a radius is given", async () => {
    const fetch = vi.fn().mockResolvedValue(ok({ matches: [], excluded: [], ranking_policy: "" }));
    vi.stubGlobal("fetch", fetch);
    await api.discover({ kind: "hotel" });
    expect(fetch.mock.calls[0][0]).toBe("/api/hive/discover?kind=hotel");
  });

  it("sends the radius, the budget and every feature it was given", async () => {
    const fetch = vi.fn().mockResolvedValue(ok({ matches: [], excluded: [], ranking_policy: "" }));
    vi.stubGlobal("fetch", fetch);
    await api.discover({ features: ["quiet", "dog-friendly"], radius: 2, budget_ms: 1500 });
    const url = fetch.mock.calls[0][0] as string;
    expect(url).toContain("radius=2");
    expect(url).toContain("budget_ms=1500");
    expect(url).toContain("features=quiet&features=dog-friendly");
  });
});

describe("introductions: connect, confirm, score", () => {
  afterEach(() => vi.unstubAllGlobals());

  it("posts a connection request with who is asking and through which hub", async () => {
    const fetch = vi.fn().mockResolvedValue(ok({ id: "cx-1", state: "open" }));
    vi.stubGlobal("fetch", fetch);
    await api.connect({ requester: "traveller-ab12", entity_id: "pension-limmat", target_hub: "zurich" });
    const [url, init] = fetch.mock.calls[0];
    expect(url).toBe("/api/hub/connect");
    expect(init.method).toBe("POST");
    expect(JSON.parse(init.body)).toEqual({
      requester: "traveller-ab12",
      entity_id: "pension-limmat",
      target_hub: "zurich",
    });
  });

  it("scores in tenths of a star, never as a POST that could be retried", async () => {
    const fetch = vi.fn().mockRejectedValue(new TypeError("Failed to fetch"));
    vi.stubGlobal("fetch", fetch);
    await expect(api.score("cx-1", 43)).rejects.toThrow(OFFLINE);
    expect(fetch).toHaveBeenCalledTimes(1);
    expect(fetch.mock.calls[0][0]).toBe("/api/hub/connections/cx-1/score");
    expect(JSON.parse(fetch.mock.calls[0][1].body)).toEqual({ rating: 43, note: "" });
  });

  it("reads only this person's introductions, and the owner's yes and no go to their own paths", async () => {
    const fetch = vi.fn().mockResolvedValue(ok({ awaiting_rating: [], awaiting_confirmation: [] }));
    vi.stubGlobal("fetch", fetch);
    await api.connections({ requester: "traveller-ab12" });
    await api.connections({ target: "lena-hofmann" });
    await api.confirmConnection("cx-2");
    await api.declineConnection("cx-3");
    expect(fetch.mock.calls.map(([url]) => url)).toEqual([
      "/api/hub/connections?requester=traveller-ab12",
      "/api/hub/connections?target=lena-hofmann",
      "/api/hub/connections/cx-2/confirm",
      "/api/hub/connections/cx-3/decline",
    ]);
  });
});

// Render's free backend sleeps: the first request after a while can fail or hang. The chat retries once, then says
// so in the person's language instead of a raw "Failed to fetch".

const ok = (body: unknown) => ({ ok: true, json: async () => body }) as Response;

describe("calling the backend", () => {
  afterEach(() => vi.unstubAllGlobals());

  it("retries once when the backend is waking up", async () => {
    const fetch = vi.fn().mockRejectedValueOnce(new TypeError("Failed to fetch")).mockResolvedValueOnce(ok([]));
    vi.stubGlobal("fetch", fetch);
    await expect(api.cards()).resolves.toEqual([]);
    expect(fetch).toHaveBeenCalledTimes(2);
  });

  it("retries a gateway error from a cold start", async () => {
    const fetch = vi
      .fn()
      .mockResolvedValueOnce({ ok: false, status: 503, statusText: "", json: async () => ({}) } as Response)
      .mockResolvedValueOnce(ok([]));
    vi.stubGlobal("fetch", fetch);
    await expect(api.cards()).resolves.toEqual([]);
  });

  it("gives up with a message the page can translate", async () => {
    vi.stubGlobal("fetch", vi.fn().mockRejectedValue(new TypeError("Failed to fetch")));
    await expect(api.cards()).rejects.toThrow(OFFLINE);
  });

  it("does not retry a request the backend refused", async () => {
    const fetch = vi
      .fn()
      .mockResolvedValue({ ok: false, status: 400, statusText: "", json: async () => ({ detail: "Ask a question." }) });
    vi.stubGlobal("fetch", fetch);
    await expect(api.cards()).rejects.toThrow("Ask a question.");
    expect(fetch).toHaveBeenCalledTimes(1);
  });

  it("preserves a reachable hub's 503 refusal without retrying the sign-in", async () => {
    const fetch = vi.fn().mockResolvedValue(
      new Response(JSON.stringify({ detail: "This hub has no ADMIN_PASSWORD set." }), {
        status: 503,
        headers: { "Content-Type": "application/json" },
      }),
    );
    vi.stubGlobal("fetch", fetch);
    await expect(api.adminLogin("anything")).rejects.toMatchObject({
      name: "ApiError",
      status: 503,
      message: "This hub has no ADMIN_PASSWORD set.",
    });
    expect(fetch).toHaveBeenCalledTimes(1);
  });

  it("does not repeat a mutation when a gateway returns no application detail", async () => {
    const fetch = vi.fn().mockResolvedValue(new Response("Bad Gateway", { status: 502 }));
    vi.stubGlobal("fetch", fetch);
    await expect(api.adminLogin("anything")).rejects.toThrow(OFFLINE);
    expect(fetch).toHaveBeenCalledTimes(1);
  });
});

describe("bounded health checks", () => {
  afterEach(() => {
    vi.unstubAllGlobals();
    vi.useRealTimers();
  });

  it("reports network or browser-policy failures without retrying or calling them CORS", async () => {
    const fetch = vi.fn().mockRejectedValue(new TypeError("Failed to fetch"));
    vi.stubGlobal("fetch", fetch);
    await expect(api.health()).rejects.toMatchObject({ name: "HealthError", kind: "network" });
    expect(fetch).toHaveBeenCalledTimes(1);
  });

  it("preserves HTTP failures, including gateway failures, without retrying", async () => {
    const fetch = vi.fn().mockResolvedValue(new Response("{}", { status: 503 }));
    vi.stubGlobal("fetch", fetch);
    await expect(api.health()).rejects.toBeInstanceOf(ApiError);
    expect(fetch).toHaveBeenCalledTimes(1);
  });

  it("times out health checks in five seconds, independently of general requests", async () => {
    vi.useFakeTimers();
    let signal: AbortSignal | undefined;
    vi.stubGlobal(
      "fetch",
      vi.fn((_url: string, init: RequestInit) => {
        signal = init.signal as AbortSignal;
        return new Promise((_resolve, reject) =>
          signal!.addEventListener("abort", () => reject(signal!.reason), { once: true }),
        );
      }),
    );
    const request = expect(api.health()).rejects.toEqual(new HealthError("timeout"));
    await vi.advanceTimersByTimeAsync(5_000);
    await request;
    expect(signal?.aborted).toBe(true);
  });

  it("aborts an obsolete health check when the caller cancels it", async () => {
    const caller = new AbortController();
    let signal: AbortSignal | undefined;
    vi.stubGlobal(
      "fetch",
      vi.fn((_url: string, init: RequestInit) => {
        signal = init.signal as AbortSignal;
        return new Promise((_resolve, reject) =>
          signal!.addEventListener("abort", () => reject(signal!.reason), { once: true }),
        );
      }),
    );
    const request = expect(api.health({ signal: caller.signal })).rejects.toMatchObject({ name: "AbortError" });
    caller.abort();
    await request;
    expect(signal?.aborted).toBe(true);
  });
});

describe("the agent has its own address when the build names one", () => {
  const answer = { reply: "", steps: [], pending: null, mode: "scripted" };
  const calledUrl = (fetch: ReturnType<typeof vi.fn>) => String(fetch.mock.calls[0][0]);

  afterEach(() => {
    vi.unstubAllGlobals();
    vi.unstubAllEnvs();
    sessionStorage.clear();
  });

  it("sends agent runs and approvals to the agent service", async () => {
    vi.stubEnv("VITE_AGENT_URL", "https://agent.example/");
    const fetch = vi.fn().mockResolvedValue(ok(answer));
    vi.stubGlobal("fetch", fetch);

    await api.agent([{ role: "user", content: "a room" }]);
    expect(calledUrl(fetch)).toBe("https://agent.example/api/agent");

    fetch.mockClear();
    await api.approve({ id: "h1", tool: "hive_book", input: {} } as never);
    expect(calledUrl(fetch)).toBe("https://agent.example/api/agent/approve");
  });

  it("keeps everything else on the hub", async () => {
    vi.stubEnv("VITE_AGENT_URL", "https://agent.example");
    const fetch = vi.fn().mockResolvedValue(ok([]));
    vi.stubGlobal("fetch", fetch);

    await api.cards();

    expect(calledUrl(fetch)).not.toContain("agent.example");
  });

  it("falls back to the hub's own agent when no agent service is named", async () => {
    const fetch = vi.fn().mockResolvedValue(ok(answer));
    vi.stubGlobal("fetch", fetch);

    await api.agent([{ role: "user", content: "a room" }]);

    expect(calledUrl(fetch)).toMatch(/\/api\/agent$/);
    expect(calledUrl(fetch)).not.toContain("agent.example");
  });

  it("uses the chosen hub's own agent when a person picked another hub", async () => {
    vi.stubEnv("VITE_AGENT_URL", "https://agent.example");
    sessionStorage.setItem("adobee-hub-url", "https://zurich.example");
    const fetch = vi.fn().mockResolvedValue(ok(answer));
    vi.stubGlobal("fetch", fetch);

    await api.agent([{ role: "user", content: "a room" }]);

    expect(calledUrl(fetch)).toBe("https://zurich.example/api/agent");
  });
});

describe("the owner's yes carries the owner token", () => {
  afterEach(() => {
    vi.unstubAllGlobals();
    sessionStorage.clear();
  });

  it.each(["confirmConnection", "declineConnection"] as const)("%s sends it", async (method) => {
    setOwnerToken("fictional-token");
    const fetch = vi.fn().mockResolvedValue(ok({ id: "cx-1", state: "open" }));
    vi.stubGlobal("fetch", fetch);

    await api[method]("cx-1");

    expect(fetch.mock.calls[0][1].headers["X-Owner-Token"]).toBe("fictional-token");
  });
});
