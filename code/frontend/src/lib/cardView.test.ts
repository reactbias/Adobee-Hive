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

  it("leaves a comparison, a taxi and a jobs question to the agent", () => {
    expect(sceneFor(en["agent.example.2"])).toBeNull();
    expect(sceneFor("book me a taxi")).toBeNull();
    expect(sceneFor("Which companies offer jobs?")).toBeNull();
  });
});
