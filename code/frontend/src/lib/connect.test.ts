import { beforeEach, describe, expect, it } from "vitest";
import type { Connection } from "../api";
import { connectMode, contactRows, isStale, nameFor, remember, requesterId, scoreSays } from "./connect";

const connection = (over: Partial<Connection> = {}): Connection => ({
  id: "cx-1",
  created_at: "2026-10-31T10:00:00",
  state: "open",
  requester: "traveller-ab12",
  requester_hub: "basel",
  target: "pension-limmat",
  target_hub: "zurich",
  via_hub: "zurich",
  sharing: "public",
  published_rating: 50,
  opened_at: "2026-10-31T10:00:00",
  stale_at: "2026-11-30T10:00:00",
  rated_at: null,
  rating: null,
  note: null,
  rating_stars: null,
  published_rating_stars: 5,
  ...over,
});

describe("what connecting to a result will take", () => {
  it("opens a public entry at once and asks first for a confirm one", () => {
    expect(connectMode("public", "hotel")).toBe("now");
    expect(connectMode("confirm", "hotel")).toBe("ask");
  });

  it("offers nothing for an entry only its owner may send, or one never shared", () => {
    expect(connectMode("push", "person")).toBeNull();
    expect(connectMode("never", "hotel")).toBeNull();
  });

  it("falls back to the hub's own default when a result carries no flag: a person is theirs to grant", () => {
    expect(connectMode(undefined, "person")).toBe("ask");
    expect(connectMode(undefined, "hotel")).toBe("now");
  });
});

describe("who is asking", () => {
  beforeEach(() => localStorage.clear());

  it("is one id per browser, kept across visits", () => {
    const first = requesterId();
    expect(first).toMatch(/^traveller-[0-9a-f]{8}$/);
    expect(requesterId()).toBe(first);
  });

  it("remembers the name of whoever was asked for, so the prompt can say it", () => {
    remember("pension-limmat", "Pension Limmat");
    expect(nameFor("pension-limmat")).toBe("Pension Limmat");
    expect(nameFor("someone-else")).toBe("someone-else");
  });
});

describe("the moment to score", () => {
  it("passes when the deadline does", () => {
    expect(isStale(connection(), new Date("2026-11-15T00:00:00"))).toBe(false);
    expect(isStale(connection(), new Date("2026-12-01T00:00:00"))).toBe(true);
    expect(isStale(connection({ state: "stale" }), new Date("2026-11-01T00:00:00"))).toBe(true);
  });
});

describe("what a score did", () => {
  it("says what the hub promised and what the person found", () => {
    const said = scoreSays({
      connection: connection({ state: "rated", rating: 25, rating_stars: 2.5 }),
      hub: "zurich",
      gap: 25,
      gap_stars: 2.5,
    });
    expect(said).toEqual({ key: "score.done", hub: "zurich", promised: 5, found: 2.5 });
  });

  it("says so when the hub had it exactly right", () => {
    const said = scoreSays({
      connection: connection({ state: "rated", rating: 50, rating_stars: 5 }),
      hub: "zurich",
      gap: 0,
      gap_stars: 0,
    });
    expect(said.key).toBe("score.exact");
  });

  it("only thanks the person when no hub carried the introduction", () => {
    const said = scoreSays({ connection: connection({ state: "rated", rating: 40, via_hub: "" }), hub: "" });
    expect(said.key).toBe("score.thanks");
  });
});

describe("contact, as a person may read it", () => {
  it("shows a published channel, offers a gated one on request, says not provided, and hides the rest", () => {
    const rows = contactRows({ email: "a@b.example", phone: "", mobile: "" }, { mobile: "confirm", address: "never" });
    expect(rows).toEqual([
      { channel: "email", value: "a@b.example", state: "shown" },
      { channel: "phone", value: "", state: "none" },
      { channel: "mobile", value: "", state: "onRequest" },
    ]);
  });

  it("is empty for a card that carries no contact at all", () => {
    expect(contactRows(undefined, undefined)).toEqual([]);
  });
});
