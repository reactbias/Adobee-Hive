import { describe, expect, it } from "vitest";
import de from "../i18n/de";
import en from "../i18n/en";
import fr from "../i18n/fr";
import it_ from "../i18n/it";
import { ratingScore, readHubCard, sceneFor, sceneFromDiscovery } from "./cardView";

describe("card view", () => {
  it("turns tenths of a star into a score, and leaves an unrated card unrated", () => {
    expect(ratingScore(43)).toBe("4.3");
    expect(ratingScore(null)).toBeNull();
  });

  it("draws the hotel, with an approval, for a stay in every language", () => {
    for (const text of [en, de, fr, it_].map((d) => d["agent.example.1"])) {
      const scene = sceneFor(text);
      expect(scene?.hits.map((h) => h.card.name)).toEqual(["Hotel Krafft Basel"]);
      expect(scene?.hits[0].card.rating).toBe(43);
      expect(scene?.hits[0].offers.map((o) => o.title)).toEqual([
        "Room reservation",
        "Small event on the Rhine terrace",
      ]);
      expect(scene?.hits[0].acting).toBe(true);
      expect(scene?.hits[0].offers[0].fields.map((f) => f.text)).toContain("Free cancellation 48h. No prepayment.");
    }
  });

  it("draws Lena unrated, and does not treat that as zero", () => {
    const scene = sceneFor("A designer for a dataviz sprint");
    expect(scene?.hits[0].card.name).toBe("Lena Hofmann");
    expect(scene?.hits[0].card.rating).toBeNull();
    expect(scene?.hits[0].offers.map((o) => o.title)).toEqual(["Two-week dataviz sprint", "Design system audit"]);
    expect(scene?.hits[0].acting).toBe(true);
  });

  it("shows a hiring need without asking to book a room", () => {
    const scene = sceneFor("Seasonal front-desk staff");
    expect(scene?.hits[0].needs.map((n) => n.title)).toEqual(["Seasonal front-desk staff"]);
    expect(scene?.hits[0].offers).toEqual([]);
    expect(scene?.hits[0].acting).toBe(false);
    expect(scene?.hits[0].needs[0].fields.map((f) => f.key)).toContain("window");
  });

  it("reads a hub card: star average, rooms as offerings, and the rest of the fields", () => {
    const card = readHubCard({
      id: "hotel-rheinblick",
      name: "Hotel Rheinblick",
      description: "Quiet courtyard rooms, dogs welcome.",
      rating: 4.6,
      rating_count: 12,
      tagline: "Quiet rooms over the Rhine",
      address: "Unterer Rheinweg 41, 4058 Basel",
      features: ["quiet", "dog-friendly"],
      policies: { cancellation: "Free until 48 h before arrival" },
      distances_m: { "basel sbb": 1900 },
      version: 1,
      published_at: "2026-10-31T08:41:44+00:00",
      valid_until: "2027-01-29T08:41:44+00:00",
      units: [
        { id: "single", name: "Courtyard single", max_guests: 1, price_chf: 128, quantity: 3 },
        { id: "double", name: "Courtyard double", max_guests: 2, price_chf: 172, quantity: 4 },
      ],
    });
    expect(card?.rating).toBe(46);
    expect(card?.offers.map((o) => o.title)).toEqual(["Courtyard single", "Courtyard double"]);
    expect(card?.offers[0].price).toEqual({ amount: 128, currency: "CHF", unit: "night" });
    expect(card?.tagline).toBe("Quiet rooms over the Rhine");
    expect(card?.place).toBe("Unterer Rheinweg 41, 4058 Basel");
    expect(card?.features).toEqual(["quiet", "dog-friendly"]);
    // Publishing metadata is for machines; the rest folds under "More about".
    expect(card?.facts.map((f) => f.key)).toEqual(["policies", "distances_m"]);
    expect(card?.facts[0].pairs).toEqual([["cancellation", "Free until 48 h before arrival"]]);
    expect(card?.facts[1].pairs).toEqual([["basel sbb", 1900]]);
  });

  it("reads a hub offer: its summary under the title, its price per person", () => {
    const card = readHubCard({
      id: "x-bekenya",
      name: "BeKenya",
      description: "Tours in Kenya.",
      offers: [
        {
          id: "kenya-21",
          title: "21 days Kenya",
          summary: "Maasai Mara, then the coast.",
          duration: "21 days",
          price: { amount: 1350, currency: "EUR", per: "person" },
        },
      ],
    });
    expect(card?.offers[0].summary).toBe("Maasai Mara, then the coast.");
    expect(card?.offers[0].price).toEqual({ amount: 1350, currency: "EUR", unit: "person" });
    expect(card?.offers[0].fields.map((f) => f.key)).toEqual(["duration"]);
  });

  it("keeps a result that arrived through the other hub", () => {
    const scene = sceneFromDiscovery(
      "quiet dog-friendly hotel",
      [
        { id: "hotel-rheinblick", why: ["has dog-friendly"], provenance: { path: ["basel"] } },
        { id: "pension-limmat", why: ["reached through zurich"], provenance: { path: ["zurich", "basel"] } },
      ],
      {
        "hotel-rheinblick": {
          id: "hotel-rheinblick",
          name: "Hotel Rheinblick",
          description: "Quiet courtyard rooms.",
          rating: null,
          units: [{ id: "single", name: "Courtyard single", price_chf: 128 }],
        },
        "pension-limmat": {
          id: "pension-limmat",
          name: "Pension Limmat",
          description: "A quiet room in Zürich.",
          rating: null,
          units: [{ id: "room", name: "River room", price_chf: 110 }],
        },
      },
    );
    expect(scene?.hits.map((h) => h.card.name)).toEqual(["Hotel Rheinblick", "Pension Limmat"]);
    expect(scene?.hits[1].found?.path).toEqual(["zurich", "basel"]);
    expect(scene?.hits[1].offers.map((o) => o.title)).toEqual(["River room"]);
  });

  it("leaves out what the hub scored zero, and never asks a yes for a card that only hands off", () => {
    const card = (id: string, name: string) => ({ id, name, description: "", rating: null, units: [] });
    const scene = sceneFromDiscovery(
      "Book me a quiet hotel. My name is Mara Keller.",
      [
        {
          id: "x-bekenya",
          score: 10,
          claimed: false,
          bookable: false,
          why: ["offers mara", "unclaimed: compiled from public information, hand-off only"],
        },
        { id: "hotel-rheinblick", score: 7, claimed: true, bookable: true, why: ["mentions quiet"] },
        {
          id: "x-pax",
          score: 0,
          claimed: false,
          bookable: false,
          why: ["unclaimed: compiled from public information"],
        },
      ],
      {
        "x-bekenya": card("x-bekenya", "BeKenya"),
        "hotel-rheinblick": card("hotel-rheinblick", "Hotel Rheinblick"),
        "x-pax": card("x-pax", "Pax"),
      },
    );
    expect(scene?.hits.map((h) => h.card.name)).toEqual(["BeKenya", "Hotel Rheinblick"]);
    expect(scene?.hits.map((h) => h.acting)).toEqual([false, true]);
    expect(scene?.hits.map((h) => h.unclaimed)).toEqual([true, false]);
    expect(scene?.hits[0].found?.why).toEqual(["offers mara"]);
  });

  it("draws nothing when the hub paid every row for its reputation alone", () => {
    // A hub of hotels, asked for an electrician: verified reviews, attestations and a valid signature
    // are paid whatever was asked, so the whole hub comes back scoring 1 or 2. Drawing those reads as
    // "found some junk" instead of "no Hive within this reach has one", which looks like a broken search.
    const reputationOnly = (attestations: number) => ({
      constraints: 0,
      text_relevance: 0,
      offers_needs: 0,
      semantic: 0,
      proximity: 0,
      attestations,
    });
    const card = (id: string, name: string) => ({ id, name, description: "", rating: null, units: [] });
    const scene = sceneFromDiscovery(
      "an electrician for a broken fuse box",
      [
        { id: "hotel-rheinblick", score: 2, score_breakdown: reputationOnly(2) },
        { id: "messe-loft", score: 1, score_breakdown: reputationOnly(1) },
      ],
      {
        "hotel-rheinblick": card("hotel-rheinblick", "Hotel Rheinblick"),
        "messe-loft": card("messe-loft", "Messe Loft"),
      },
    );
    expect(scene).toBeNull();
  });

  it("keeps what the hub paid for the request itself, and drops what it did not", () => {
    const card = (id: string, name: string) => ({ id, name, description: "", rating: null, units: [] });
    const scene = sceneFromDiscovery(
      "an electrician for a broken fuse box",
      [
        { id: "elektro-mattenhof", score: 16, score_breakdown: { semantic: 16, attestations: 0 } },
        { id: "hotel-rheinblick", score: 2, score_breakdown: { semantic: 0, offers_needs: 0, attestations: 2 } },
      ],
      {
        "elektro-mattenhof": card("elektro-mattenhof", "Elektro Mattenhof"),
        "hotel-rheinblick": card("hotel-rheinblick", "Hotel Rheinblick"),
      },
    );
    expect(scene?.hits.map((h) => h.card.name)).toEqual(["Elektro Mattenhof"]);
  });

  it("carries the signed card through untouched, beside the normalised one and never instead of it", () => {
    // #172: an introduction to an entity this hub does not carry is checked against the key that entity's
    // own hub pinned, and an Ed25519 signature covers the exact canonical JSON. readHubCard re-orders and
    // coerces, so the drawn card can never be the one that is sent.
    const signed = {
      id: "elektro-mattenhof",
      name: "Elektro Mattenhof",
      description: "Fuse boxes and house wiring.",
      rating: 4.2,
      signature: "ed25519:abc",
      published_at: "2026-10-30T09:00:00",
    };
    const scene = sceneFromDiscovery(
      "an electrician for a broken fuse box",
      [
        {
          id: "elektro-mattenhof",
          score: 16,
          score_breakdown: { semantic: 16 },
          card: signed as never,
          provenance: { path: ["bern", "basel"], origin: "bern" },
        },
      ],
      { "elektro-mattenhof": signed },
    );
    const hit = scene?.hits[0];
    // The same object, not a copy and not a normalisation of it.
    expect(hit?.signedCard).toBe(signed);
    // The drawn card is the normalised one, and the two are not the same thing.
    expect(hit?.card).not.toBe(signed);
    expect(hit?.card.rating).toBe(42);
    expect((hit?.signedCard as unknown as { rating: number }).rating).toBe(4.2);
  });

  it("carries no signed card for a row the hub did not attach one to", () => {
    const scene = sceneFromDiscovery(
      "a quiet hotel",
      [{ id: "hotel-rheinblick", score: 9, score_breakdown: { offers_needs: 9 } }],
      { "hotel-rheinblick": { id: "hotel-rheinblick", name: "Hotel Rheinblick", description: "", rating: null } },
    );
    expect(scene?.hits[0].signedCard).toBeUndefined();
  });

  it("keeps every row when the hub scored nothing, rather than showing an empty page", () => {
    const scene = sceneFromDiscovery("anything", [{ id: "a", score: 0, why: [] }], {
      a: { id: "a", name: "A", description: "", rating: null },
    });
    expect(scene?.hits.map((h) => h.card.name)).toEqual(["A"]);
  });

  it("leaves a comparison, a taxi and a jobs question to the agent", () => {
    expect(sceneFor(en["agent.example.2"])).toBeNull();
    expect(sceneFor("book me a taxi")).toBeNull();
    expect(sceneFor("Which companies offer jobs?")).toBeNull();
  });
});
