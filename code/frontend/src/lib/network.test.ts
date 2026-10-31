import { describe, expect, it } from "vitest";
import type { AdminNeighbours, AdminOverview, Directory } from "../api";
import { buildNetwork, clip, hexPoints, liveIntroductions, ringPosition, viewBox } from "./network";

// The live hub right now: 22 entities, no peers at all. That is the common case and it must not look broken.
const LIVE: AdminOverview = {
  hub: "local",
  name: "Adobee Hive (Basel)",
  index: { entities: 22 },
  neighbours: { configured: 0, blocked: 0, with_evidence: 0 },
  blocklist: { hubs: 0, entities: 0 },
  connections: { awaiting_confirmation: 1, awaiting_rating: 2, rated: 5, stale: 0, declined: 0 },
  peers: [],
};

const NEIGHBOURS: AdminNeighbours = {
  peers: [
    {
      hub: "zurich",
      url: "https://zurich.example",
      blocked: false,
      error: -4,
      error_stars: -0.4,
      evidence: 6,
      verdict: "good",
      why: "modest",
    },
    {
      hub: "spam",
      url: "https://spam.example",
      blocked: true,
      error: null,
      error_stars: null,
      evidence: 0,
      verdict: "unproven",
      why: "blocked",
    },
  ],
  blocked_hubs: ["spam"],
};

const DIRECTORY: Directory = {
  hubs: [
    {
      hub: "local",
      url: "",
      home: true,
      blocked: false,
      name: "Adobee Hive (Basel)",
      description: "",
      admission: "vetted",
      accepting: true,
      entities: 22,
      error: null,
      error_stars: null,
      evidence: 0,
      verdict: "unproven",
      why: "",
    },
    {
      hub: "zurich",
      url: "https://zurich.example",
      home: false,
      blocked: false,
      name: "Hive Zürich",
      description: "",
      admission: "open",
      accepting: true,
      entities: 9,
      error: -4,
      error_stars: -0.4,
      evidence: 6,
      verdict: "good",
      why: "modest",
    },
  ],
};

describe("building the network", () => {
  it("draws one node, honestly labelled, when there are no peers at all", () => {
    const nodes = buildNetwork(LIVE, { peers: [], blocked_hubs: [] }, null);
    expect(nodes).toHaveLength(1);
    expect(nodes[0]).toMatchObject({ home: true, label: "Adobee Hive (Basel)", entities: 22 });
  });

  it("puts the home hub first, then one node per configured peer", () => {
    const nodes = buildNetwork(LIVE, NEIGHBOURS, DIRECTORY);
    expect(nodes.map((n) => n.hub)).toEqual(["local", "zurich", "spam"]);
    expect(nodes[0].home).toBe(true);
  });

  it("takes a peer's name and entity count from the directory when it is there", () => {
    const [, zurich] = buildNetwork(LIVE, NEIGHBOURS, DIRECTORY);
    expect(zurich).toMatchObject({ label: "Hive Zürich", entities: 9, admission: "open" });
  });

  it("leaves a peer we have not asked as unknown, never as zero", () => {
    const [, zurich, spam] = buildNetwork(LIVE, NEIGHBOURS, null);
    expect(zurich).toMatchObject({ label: "zurich", entities: null, admission: "" });
    expect(spam.entities).toBeNull();
  });

  it("still shows a blocked peer, marked as blocked", () => {
    const spam = buildNetwork(LIVE, NEIGHBOURS, DIRECTORY).find((n) => n.hub === "spam");
    expect(spam).toMatchObject({ blocked: true, verdict: "unproven" });
  });

  it("carries each peer's calibration through untouched, sign and all", () => {
    const [, zurich] = buildNetwork(LIVE, NEIGHBOURS, DIRECTORY);
    expect(zurich.error).toBe(-4);
    expect(zurich.evidence).toBe(6);
  });

  it("survives every payload being missing", () => {
    expect(buildNetwork(null, null, null)).toHaveLength(1);
    expect(buildNetwork(null, null, null)[0].entities).toBeNull();
  });
});

describe("counting what is live", () => {
  it("counts the introductions still waiting on somebody, not the finished ones", () => {
    expect(liveIntroductions(LIVE)).toBe(3);
    expect(liveIntroductions(null)).toBe(0);
  });
});

describe("the honeycomb", () => {
  it("draws a hexagon as six points", () => {
    expect(hexPoints(100, 100, 50).split(" ")).toHaveLength(6);
    expect(hexPoints(0, 0, 10).split(" ")[0]).toBe("10.0,0.0");
  });

  it("puts the first six peers on one ring around the centre", () => {
    for (let i = 0; i < 6; i++) expect(ringPosition(i, 6, 300, 210).ring).toBe(0);
    const first = ringPosition(0, 6, 300, 210);
    expect(first.x).toBeCloseTo(300, 1);
    expect(first.y).toBeCloseTo(70, 1);
  });

  it("spreads a ring that is not full round the whole circle, not bunched on one side", () => {
    const [top, bottom] = [ringPosition(0, 2, 300, 210), ringPosition(1, 2, 300, 210)];
    expect(top.y).toBeCloseTo(70, 1);
    expect(bottom.y).toBeCloseTo(350, 1);
    const four = [0, 1, 2, 3].map((i) => ringPosition(i, 4, 300, 210));
    expect(four.filter((p) => p.x > 300.5)).toHaveLength(1);
    expect(four.filter((p) => p.x < 299.5)).toHaveLength(1);
  });

  it("starts a second, turned ring at the seventh, so nothing hides behind a node", () => {
    const seventh = ringPosition(6, 7, 300, 210);
    expect(seventh.ring).toBe(1);
    expect(Math.hypot(seventh.x - 300, seventh.y - 210)).toBeGreaterThan(200);
  });

  it("keeps every node of a full ring inside the drawing", () => {
    for (let i = 0; i < 6; i++) {
      const { x, y } = ringPosition(i, 6, 300, 210);
      expect(x).toBeGreaterThan(50);
      expect(x).toBeLessThan(550);
      expect(y).toBeGreaterThan(20);
      expect(y).toBeLessThan(400);
    }
  });

  it("clips a long name to its cell and leaves a short one alone", () => {
    expect(clip("Hive Bern", 12)).toBe("Hive Bern");
    expect(clip("Adobee Hive (Basel)", 12)).toBe("Adobee Hive…");
  });

  it("draws the box tight around one lone hub, so it does not sit lost in white space", () => {
    const [, , w, h] = viewBox([], 300, 210, 80).split(" ").map(Number);
    expect(w).toBe(160);
    expect(h).toBe(160);
  });

  it("grows the box to hold every peer", () => {
    const peers = [0, 1, 2, 3, 4, 5].map((i) => ringPosition(i, 6, 300, 210));
    const [, , w, h] = viewBox(peers, 300, 210, 62).split(" ").map(Number);
    expect(w).toBeGreaterThan(300);
    expect(h).toBeGreaterThan(300);
  });
});
