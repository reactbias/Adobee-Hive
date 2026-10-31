import { afterEach, describe, expect, it } from "vitest";
import { demoMode } from "./demo";

// Presenter tools (stress test, simulated traffic, tamper test, raw MCP) stay off the public page. ?demo shows them.

describe("demo mode", () => {
  afterEach(() => window.history.replaceState(null, "", "/"));

  it("is off for visitors", () => {
    expect(demoMode()).toBe(false);
  });

  it("is on with ?demo in the address", () => {
    window.history.replaceState(null, "", "/?demo");
    expect(demoMode()).toBe(true);
  });
});
