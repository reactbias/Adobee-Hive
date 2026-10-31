import { afterEach, describe, expect, it, vi } from "vitest";
import { api } from "../api";
import { hubScene } from "./hubScene";

describe("hub scene", () => {
  afterEach(() => vi.restoreAllMocks());

  it("draws the rooms on the card the hub returned for each match", async () => {
    vi.spyOn(api, "discover").mockResolvedValue({
      matches: [
        {
          id: "pension-limmat",
          slug: "limmat",
          name: "Pension Limmat",
          description: "A quiet room in Zürich.",
          rating: 4.2,
          rating_count: 4,
          kind: "hotel",
          from_price_chf: 110,
          distance_m: null,
          score: 70,
          score_breakdown: {},
          why: ["reached through zurich"],
          signature_valid: true,
          hops: 1,
          provenance: { path: ["zurich", "basel"], hops: 1, origin: "zurich", origin_url: null, also_reached_by: [] },
        },
      ],
      excluded: [],
      ranking_policy: "open",
    });
    vi.spyOn(api, "card").mockResolvedValue({
      id: "pension-limmat",
      name: "Pension Limmat",
      description: "A quiet room in Zürich.",
      units: [{ id: "room", name: "River room", price_chf: 110 }],
    } as never);

    const scene = await hubScene("quiet hotel");
    expect(scene?.hits[0].card.name).toBe("Pension Limmat");
    expect(scene?.hits[0].card.rating).toBe(42);
    expect(scene?.hits[0].offers[0].title).toBe("River room");
    expect(scene?.hits[0].found?.path).toEqual(["zurich", "basel"]);
  });
});
