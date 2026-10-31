import { describe, expect, it } from "vitest";
import type { Booking, Card } from "../api";
import { icsEvent, pickNearby } from "./next";

const booking: Booking = {
  status: "confirmed",
  booking_id: "BK-1234",
  business: "Hotel Rheinblick",
  unit_name: "Courtyard single",
  check_in: "2026-11-13",
  check_out: "2026-11-15",
  total_chf: 256,
  receipt: "sig;abc,def",
  payment: "Pay at the property",
};

const cafe = (id: string, features: string[]) => ({ id, slug: id, name: id, features }) as unknown as Card;

describe("icsEvent", () => {
  const ics = icsEvent(booking, "Rheinweg 1, 4058 Basel", new Date("2026-10-31T01:02:03.456Z"));
  const lines = ics.split("\r\n");

  it("is an all-day stay from check-in to check-out", () => {
    expect(lines).toContain("DTSTART;VALUE=DATE:20261113");
    expect(lines).toContain("DTEND;VALUE=DATE:20261115");
    expect(lines).toContain("DTSTAMP:20261031T010203Z");
    expect(lines).toContain("UID:BK-1234@adobee-hive");
  });

  it("escapes text so card data cannot break the file", () => {
    expect(lines).toContain("LOCATION:Rheinweg 1\\, 4058 Basel");
    expect(ics).toContain("sig\\;abc\\,def");
    expect(lines.filter((l) => l.startsWith("BEGIN:VEVENT"))).toHaveLength(1);
  });

  it("strips line breaks an owner might put in a name", () => {
    const evil = icsEvent({ ...booking, business: "Evil\r\nEND:VEVENT" }, undefined, new Date());
    expect(evil.split("\r\n").filter((l) => l === "END:VEVENT")).toHaveLength(1);
    expect(evil).not.toContain("LOCATION:");
  });
});

describe("pickNearby", () => {
  it("prefers the place that shares what the guest asked for", () => {
    const pick = pickNearby([cafe("a", ["wifi"]), cafe("b", ["wifi", "dog-friendly"])], ["dog-friendly", "quiet"]);
    expect(pick?.card.id).toBe("b");
    expect(pick?.shared).toBe("dog-friendly");
  });

  it("still suggests something nearby when nothing matches", () => {
    const pick = pickNearby([cafe("a", ["wifi"])], ["quiet"]);
    expect(pick?.card.id).toBe("a");
    expect(pick?.shared).toBeUndefined();
  });

  it("suggests nothing when the Hive has no such place", () => {
    expect(pickNearby([], ["quiet"])).toBeNull();
  });
});
