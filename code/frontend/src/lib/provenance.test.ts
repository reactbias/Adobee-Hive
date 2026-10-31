import { describe, expect, it } from "vitest";
import { readSource } from "./provenance";

// The example the running hubs actually answer with: path is origin first, answering hub last.
const RELAYED = { hops: 1, provenance: { path: ["zurich", "basel"], hops: 1, origin: "zurich", also_reached_by: [] } };

describe("reading where a result came from", () => {
  it("calls a result with no hops local", () => {
    expect(readSource({})).toMatchObject({ local: true, hops: 0 });
    expect(readSource({ hops: 0, provenance: null })).toMatchObject({ local: true, hops: 0 });
  });

  it("names the origin hub, not the hub that handed it over", () => {
    const relay = readSource({
      hops: 2,
      provenance: { path: ["basel", "zurich", "us"], hops: 2, origin: "basel" },
    });
    expect(relay.origin).toBe("basel");
    expect(relay.hops).toBe(2);
  });

  it("keeps the whole chain, so a person can see the relay", () => {
    const relay = readSource({ hops: 2, provenance: { path: ["basel", "zurich", "us"], hops: 2, origin: "basel" } });
    expect(relay.path).toEqual(["basel", "zurich", "us"]);
    expect(relay.relays).toEqual(["zurich"]);
  });

  it("reports no relay for a direct neighbour", () => {
    expect(readSource(RELAYED)).toMatchObject({ local: false, origin: "zurich", hops: 1, relays: [] });
  });

  it("counts the other routes the same card arrived by", () => {
    const many = readSource({
      hops: 1,
      provenance: { path: ["zurich", "us"], hops: 1, origin: "zurich", also_reached_by: [{}, {}] },
    });
    expect(many.alsoReachedBy).toBe(2);
  });

  it("reads a malformed provenance as local rather than as unknown", () => {
    expect(readSource({ hops: 3, provenance: {} as never })).toMatchObject({ local: true });
    expect(readSource({ hops: Number.NaN, provenance: { origin: "zurich" } })).toMatchObject({ local: true });
  });
});
