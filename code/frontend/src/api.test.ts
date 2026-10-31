import { describe, expect, it, vi } from "vitest";
import { api } from "./api";

describe("api", () => {
  it("tells the backend the app's language, so the agent answers in it", async () => {
    document.documentElement.lang = "fr";
    const fetchMock = vi.spyOn(globalThis, "fetch").mockResolvedValue(new Response("{}"));
    await api.health();
    const headers = new Headers(fetchMock.mock.calls[0][1]?.headers);
    expect(headers.get("Accept-Language")).toBe("fr");
  });
});
