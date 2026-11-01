import { beforeEach, describe, expect, it, vi } from "vitest";
import { forgetAsks, KEEP, pastAsks, rememberAsk } from "./asks";

describe("what you asked before", () => {
  beforeEach(() => localStorage.clear());

  it("has nothing to show before the first ask", () => {
    expect(pastAsks()).toEqual([]);
  });

  it("keeps asks newest first", () => {
    rememberAsk("a room in Basel");
    rememberAsk("an electrician in Bern");
    expect(pastAsks()).toEqual(["an electrician in Bern", "a room in Basel"]);
  });

  it("moves a repeated ask to the front instead of listing it twice", () => {
    rememberAsk("a room in Basel");
    rememberAsk("an electrician in Bern");
    rememberAsk("  A ROOM in Basel  ");
    // The person's own wording is kept, but case and surrounding space do not make a second entry.
    expect(pastAsks()).toEqual(["A ROOM in Basel", "an electrician in Bern"]);
  });

  it("stops at KEEP, so the list never becomes a profile", () => {
    for (let i = 0; i < KEEP + 5; i++) rememberAsk(`ask ${i}`);
    expect(pastAsks()).toHaveLength(KEEP);
    expect(pastAsks()[0]).toBe(`ask ${KEEP + 4}`);
  });

  it("ignores an empty ask", () => {
    rememberAsk("a room in Basel");
    expect(rememberAsk("   ")).toEqual(["a room in Basel"]);
  });

  it("forgets the lot in one call", () => {
    rememberAsk("a room in Basel");
    forgetAsks();
    expect(pastAsks()).toEqual([]);
  });

  it("is empty rather than broken when the stored value is not a list of asks", () => {
    localStorage.setItem("adobee-asks", '{"not":"a list"}');
    expect(pastAsks()).toEqual([]);
    localStorage.setItem("adobee-asks", '["a room", 7, null, "  "]');
    expect(pastAsks()).toEqual(["a room"]);
  });

  it("carries on when storage is blocked, because a private window is not an error", () => {
    const read = vi.spyOn(Storage.prototype, "getItem").mockImplementation(() => {
      throw new Error("blocked");
    });
    const write = vi.spyOn(Storage.prototype, "setItem").mockImplementation(() => {
      throw new Error("blocked");
    });
    expect(pastAsks()).toEqual([]);
    expect(rememberAsk("a room in Basel")).toEqual(["a room in Basel"]);
    read.mockRestore();
    write.mockRestore();
  });
});
