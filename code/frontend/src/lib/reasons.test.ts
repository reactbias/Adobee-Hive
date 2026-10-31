import { describe, expect, it } from "vitest";
import de from "../i18n/de";
import en from "../i18n/en";
import fr from "../i18n/fr";
import it_ from "../i18n/it";
import { reasonText } from "./reasons";

// The Hive explains every pick and every exclusion in fixed English phrases (the agents read them too). The page
// shows them in the person's language.

const SAMPLES = [
  "mentions jobs",
  "fits your mood: calm, short",
  "this month",
  "recent news",
  "coming up on 2026-11-20",
  "no published price, ask for a quote",
  "EUR 1350 per person is over your budget of CHF 500",
  "set aside for your mood: long",
  "signed facts expired on 2026-10-01; the owner has to re-sign",
  "missing parking, quiet",
  "has quiet, dog-friendly",
  "takes no stay bookings",
  "no room for 2 from 2026-11-13 to 2026-11-15",
  "River room free at CHF 180/night",
  "cheapest fit CHF 240 > budget CHF 200",
  "350 m from basel sbb",
];

const fill =
  (dict: Record<string, string>) =>
  (key: string, vars: Record<string, string | number> = {}) =>
    dict[key].replace(/\{(\w+)\}/g, (_, k) => String(vars[k]));

describe("reasons", () => {
  for (const [lang, dict] of Object.entries({ de, fr, it: it_ })) {
    it(`reads every reason in ${lang}`, () => {
      for (const s of SAMPLES) {
        const out = reasonText(fill(dict as Record<string, string>), s);
        expect(out, s).not.toBe(s);
        expect(out, s).not.toMatch(/\{\w+\}/);
      }
    });
  }

  it("keeps the values from the card", () => {
    expect(reasonText(fill(de as Record<string, string>), "350 m from basel sbb")).toContain("basel sbb");
    expect(reasonText(fill(en as Record<string, string>), "mentions jobs")).toContain("jobs");
  });

  it("shows a reason it does not know as it came", () => {
    expect(reasonText(fill(de as Record<string, string>), "something new")).toBe("something new");
  });
});
