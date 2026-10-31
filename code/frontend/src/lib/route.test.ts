import { describe, expect, it } from "vitest";
import de from "../i18n/de";
import en from "../i18n/en";
import fr from "../i18n/fr";
import it_ from "../i18n/it";
import { routeFor } from "./route";

// One chat for everything: a stay goes to the booking agent, a question about any business to the Hive's cards.

describe("routing a request", () => {
  for (const [lang, d] of Object.entries({ en, de, fr, it: it_ })) {
    it(`sends the stay examples to the booking agent (${lang})`, () => {
      for (const k of ["agent.example.1", "agent.example.2", "agent.example.3"] as const)
        expect(routeFor(d[k], false), d[k]).toBe("stay");
    });
    it(`sends the business examples to the cards (${lang})`, () => {
      for (const k of ["try.pasta", "try.coffee", "try.lockout"] as const)
        expect(routeFor(d[k], false), d[k]).toBe("ask");
      for (const k of ["try.tavern", "try.garden", "try.hostel"] as const)
        expect(routeFor(d[k], false), d[k]).toBe("stay");
    });
  }

  it("keeps a reply in a running booking conversation with the booking agent", () => {
    expect(routeFor("Yes, the cheaper one please", true)).toBe("stay");
  });

  it("sends the other example businesses to the cards", () => {
    expect(routeFor("Can 4XOR help me automate a workflow?", false)).toBe("ask");
    expect(routeFor("What is Adobe doing about content credentials?", false)).toBe("ask");
  });

  it("still answers a named business in the middle of a booking", () => {
    expect(routeFor("And what is on at BaselHack?", true)).toBe("ask");
  });
});
