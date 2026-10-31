import { describe, expect, it } from "vitest";
import { readable } from "./diff";

// The owner reads the diff before signing it, so it names what changed, never a dump of the whole field.
describe("readable diff", () => {
  it("lists only the tags added or removed", () => {
    expect(readable({ field: "features", before: ["quiet", "wifi"], after: ["quiet", "sauna"] })).toEqual([
      { field: "features", before: "wifi" },
      { field: "features", after: "sauna" },
    ]);
  });

  it("names the room whose price changed, and nothing else", () => {
    const room = (id: string, name: string, price_chf: number) => ({ id, name, price_chf, quantity: 2 });
    expect(
      readable({
        field: "units",
        before: [room("single", "Courtyard single", 128), room("double", "Courtyard double", 172)],
        after: [room("single", "Courtyard single", 128), room("double", "Courtyard double", 165)],
      }),
    ).toEqual([{ field: "Courtyard double", before: "CHF 172", after: "CHF 165" }]);
  });

  it("shows a changed policy by its key", () => {
    expect(
      readable({
        field: "policies",
        before: { pets: "No pets", wifi: "free" },
        after: { pets: "Dogs welcome", wifi: "free" },
      }),
    ).toEqual([{ field: "pets", before: "No pets", after: "Dogs welcome" }]);
  });

  it("falls back to before and after for anything else", () => {
    expect(readable({ field: "tagline", before: "Old", after: "New" })).toEqual([
      { field: "tagline", before: "Old", after: "New" },
    ]);
  });
});
