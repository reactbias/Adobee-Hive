import { describe, expect, it } from "vitest";
import { chf, day, metres, nights, stay } from "./format";

describe("format", () => {
  it("counts nights between ISO days", () => {
    expect(nights("2026-11-13", "2026-11-15")).toBe(2);
    expect(nights("2026-12-31", "2027-01-01")).toBe(1);
    expect(nights("13.11.2026", "2026-11-15")).toBe(0); // not an ISO day: no guess
  });

  it("formats money in Swiss francs without cents", () => {
    expect(chf(360, "de-CH")).toMatch(/CHF.*360/);
    expect(chf(1250.4, "en-CH")).not.toMatch(/\.4/);
  });

  it("collapses a stay into one range per locale", () => {
    expect(stay("2026-11-13", "2026-11-15", "en-CH")).toMatch(/13.*15.*Nov.*2026/);
    expect(stay("2026-11-13", "2026-11-15", "de-CH")).toMatch(/13.*15.*Nov.*2026/);
  });

  it("passes anything that is not an ISO day through unchanged", () => {
    expect(day("soon", "en-CH")).toBe("soon");
    expect(stay(undefined, "2026-11-15", "en-CH")).toBe(" – 2026-11-15");
  });

  it("switches from metres to kilometres at 1000", () => {
    expect(metres(450, "en-CH")).toMatch(/450\s?m/);
    expect(metres(1500, "en-CH")).toMatch(/1\.5\s?km/);
  });
});
