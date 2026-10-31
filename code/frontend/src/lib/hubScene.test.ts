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

  it("asks this hub only, unless the person chose to look further", async () => {
    const discover = vi.spyOn(api, "discover").mockResolvedValue({ matches: [], excluded: [], ranking_policy: "" });

    await hubScene("quiet hotel");
    await hubScene("quiet hotel", 3);

    expect(discover.mock.calls[0][0]).toEqual({ query: "quiet hotel", radius: 0 });
    expect(discover.mock.calls[1][0]).toEqual({ query: "quiet hotel", radius: 3 });
  });

  it("keeps where each result came from, and what the other hubs reported", async () => {
    vi.spyOn(api, "discover").mockResolvedValue({
      matches: [
        {
          id: "pension-limmat",
          slug: "limmat",
          name: "Pension Limmat",
          description: "A quiet room in Zürich.",
          rating: null,
          rating_count: 0,
          kind: "hotel",
          from_price_chf: 110,
          distance_m: null,
          score: 70,
          score_breakdown: {},
          why: [],
          signature_valid: true,
          hops: 1,
          provenance: { path: ["zurich", "basel"], hops: 1, origin: "zurich", origin_url: null, also_reached_by: [] },
        },
      ],
      excluded: [],
      ranking_policy: "open",
      federation: {
        hub: "basel",
        radius: 1,
        seen: ["basel"],
        budget_ms: 1500,
        elapsed_ms: 40,
        asked: [
          { hub: "zurich", name: "Hive Zürich", description: "", rating: 0.4, url: "https://z.example", trust: 0.4 },
        ],
        dropped: [{ hub: "bern", reason: "deadline exceeded: 12 ms left for this hop" }],
        rejected: [{ hub: "zurich", card_id: "hotel-liar", origin: "zurich", reason: "does not match" }],
        hub_trust: {},
      },
    });
    vi.spyOn(api, "card").mockRejectedValue(new Error("offline"));

    const scene = await hubScene("quiet hotel", 1);

    expect(scene?.hits[0].found).toMatchObject({ hops: 1, origin: "zurich" });
    // Not rated yet stays null: never a zero.
    expect(scene?.hits[0].card.rating).toBeNull();
    expect(scene?.federation).toEqual({
      radius: 1,
      asked: [{ hub: "zurich", name: "Hive Zürich" }],
      dropped: [{ hub: "bern", reason: "deadline exceeded: 12 ms left for this hop" }],
      rejected: [{ hub: "zurich", card_id: "hotel-liar", reason: "does not match" }],
    });
  });
});
