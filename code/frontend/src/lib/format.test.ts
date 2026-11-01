import { describe, expect, it } from "vitest";
import { chf, day, metres, moment, nights, since, size, stay } from "./format";

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

// "asked 2 minutes ago" has to be true, in four languages, and must never invent a time it does not have.
describe("how long ago", () => {
  const now = new Date("2026-10-31T12:00:00Z");

  it("counts in the largest unit that fits", () => {
    expect(since("2026-10-31T11:59:30Z", "en-CH", now)).toBe("30 seconds ago");
    expect(since("2026-10-31T11:58:00Z", "en-CH", now)).toBe("2 minutes ago");
    expect(since("2026-10-31T09:00:00Z", "en-CH", now)).toBe("3 hours ago");
    expect(since("2026-10-30T12:00:00Z", "en-CH", now)).toBe("yesterday");
  });

  it("speaks the page's language", () => {
    expect(since("2026-10-31T11:58:00Z", "de-CH", now)).toBe("vor 2 Minuten");
    expect(since("2026-10-31T11:58:00Z", "fr-CH", now)).toBe("il y a 2 minutes");
    expect(since("2026-10-31T11:58:00Z", "it-CH", now)).toBe("2 minuti fa");
  });

  it("says nothing at all when there is no moment to report", () => {
    expect(since(null, "en-CH", now)).toBe("");
    expect(since(undefined, "en-CH", now)).toBe("");
    expect(since("not a date", "en-CH", now)).toBe("");
    expect(moment(null, "en-CH")).toBe("");
  });

  it("gives the exact moment for a title", () => {
    expect(moment("2026-10-31T12:00:00Z", "en-CH")).toMatch(/2026/);
  });
});

describe("file sizes", () => {
  it("shows whole bytes below a kilobyte", () => {
    expect(size(872, "en-CH")).toBe("872 B");
    expect(size(0, "en-CH")).toBe("0 B");
  });

  it("goes up a unit at a thousand, with one decimal while it is small", () => {
    expect(size(2048, "en-CH")).toBe("2.0 kB");
    expect(size(182_000, "en-CH")).toBe("182 kB");
    expect(size(26_214_400, "en-CH")).toBe("26.2 MB");
  });

  it("says nothing rather than something wrong for a size that is not one", () => {
    expect(size(null, "en-CH")).toBe("");
    expect(size(-1, "en-CH")).toBe("");
    expect(size("big", "en-CH")).toBe("");
  });
});
