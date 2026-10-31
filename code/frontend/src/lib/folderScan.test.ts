import { describe, expect, it } from "vitest";
import { buildDraft, groupsOf, toEntity, type VaultFile } from "./folderScan";

// The same folders tools/seed_vaults.py registers, read the way a browser hands them over.
const raw = import.meta.glob<string>("../../../../testdata/vaults/*/*.md", {
  query: "?raw",
  import: "default",
  eager: true,
});

function vault(name: string): VaultFile[] {
  const encoder = new TextEncoder();
  return Object.entries(raw)
    .filter(([path]) => path.includes(`/vaults/${name}/`))
    .map(([path, text]) => ({ path: path.split(`/vaults/${name}/`)[1], bytes: encoder.encode(text) }));
}

describe("a folder, scanned in the page", () => {
  it("is grouped by what sits at its top, so each can be shared or kept back as a whole", () => {
    const files = [
      { path: "about.md", bytes: new Uint8Array(3) },
      { path: "notes/a.md", bytes: new Uint8Array(1) },
      { path: "notes/b.md", bytes: new Uint8Array(1) },
    ];
    expect(groupsOf(files)).toEqual([
      { path: "about.md", files: 1 },
      { path: "notes", files: 2 },
    ]);
  });

  it("fills a person's Card the way seed_vaults.py does", async () => {
    const draft = await buildDraft("lena-hofmann", vault("lena-hofmann"), {});
    expect(draft.id).toBe("lena-hofmann");
    expect(draft.kind).toBe("person");
    expect(draft.name).toBe("Lena Hofmann");
    expect(draft.description).toBe("Interface design for data-heavy products. Nine years, three production design");
    expect(draft.contact).toEqual([
      { channel: "email", value: "lena@lena.example", flag: "public" },
      { channel: "phone", value: "", flag: "confirm" },
      { channel: "address", value: "", flag: "never" },
    ]);
    expect(draft.offers.map((o) => [o.title, o.price_chf])).toEqual([
      ["Two-week dataviz sprint", 9600],
      ["Design system audit", 180],
    ]);
    expect(draft.needs.map((n) => n.title)).toEqual(["A Svelte contractor for overflow work, CHF 120/hour"]);
    expect(draft.features).toEqual(["remote"]);
    // Paths, sizes and digests, never contents: these are the digests seed_vaults.py computes for the same files.
    expect(draft.structure).toEqual([
      { path: "about.md", bytes: 186, visibility: "public-summary", digest: "sha256:11c31fda25cb" },
      { path: "contact.md", bytes: 74, visibility: "public-summary", digest: "sha256:79d3f2ab43ba" },
      { path: "work.md", bytes: 196, visibility: "public-summary", digest: "sha256:8a2e6df049dd" },
    ]);
  });

  it("reads a hotel's rooms as bookable units, hyphenated names included", async () => {
    const draft = await buildDraft("hotel-krafft", vault("hotel-krafft"), {});
    expect(draft.kind).toBe("hotel");
    expect(draft.features).toEqual(["quiet", "breakfast"]);
    expect(draft.units.map((u) => [u.id, u.max_guests, u.price_chf, u.quantity])).toEqual([
      ["courtyard-single", 1, 128, 3],
      ["courtyard-double", 2, 172, 4],
      ["river-view-double", 2, 238, 2],
    ]);
    expect(draft.contact.find((c) => c.channel === "mobile")).toEqual({
      channel: "mobile",
      value: "",
      flag: "confirm",
    });
  });

  it("never reads a part the person kept back, and leaves shared and hidden parts out of the Card entirely", async () => {
    const files = [
      { path: "about.md", bytes: new TextEncoder().encode("# Ada\n\nA one-line description.\n") },
      { path: "work.md", bytes: new TextEncoder().encode("# What I do\n\n- Secret consulting — CHF 900.\n") },
      { path: "diary/1.md", bytes: new TextEncoder().encode("# What I need\n\n- A hidden thing.\n") },
      { path: "clients/a.md", bytes: new TextEncoder().encode("# What I do\n\n- Shared work.\n") },
      { path: "drafts/a.md", bytes: new TextEncoder().encode("x") },
      { path: "drafts/b.md", bytes: new TextEncoder().encode("y") },
    ];
    const draft = await buildDraft("ada", files, {
      "work.md": "private",
      diary: "hidden",
      clients: "shared",
      drafts: "private",
    });
    expect(draft.offers).toEqual([]);
    expect(draft.needs).toEqual([]);
    expect(draft.structure.map((s) => s.path)).toEqual(["about.md", "drafts", "work.md"]);
    expect(draft.structure.find((s) => s.path === "drafts")).toEqual({
      path: "drafts",
      files: 2,
      visibility: "private",
    });
    expect(JSON.stringify(draft)).not.toMatch(/diary|clients/);
  });

  it("starts an empty Card when there is no folder, so typing everything by hand works", async () => {
    const draft = await buildDraft("", [], {});
    expect(draft).toMatchObject({ id: "", name: "", description: "", offers: [], needs: [], structure: [] });
    expect(draft.contact.map((c) => c.channel)).toEqual(["email", "phone"]);
  });
});

describe("the Card as it is sent", () => {
  it("has the shape seed_vaults.py registers, with gated and private channels where the hub expects them", async () => {
    const draft = await buildDraft("lena-hofmann", vault("lena-hofmann"), {});
    const entity = toEntity(draft);
    expect(entity).toMatchObject({
      id: "lena-hofmann",
      slug: "lena-hofmann",
      kind: "person",
      name: "Lena Hofmann",
      tagline: "Interface design for data-heavy products. Nine years, three production design".slice(0, 90),
      contact: { email: "lena@lena.example", phone: "" },
      contact_sharing: { phone: "confirm", address: "never" },
    });
    expect(entity).not.toHaveProperty("units");
    expect((entity.offers as { id: string }[])[0].id).toBe("two-week-dataviz-sprint");
  });

  it("sends only whole numbers, so the canonical bytes match the hub's", async () => {
    const draft = await buildDraft("hotel-krafft", vault("hotel-krafft"), {});
    const numbers: number[] = [];
    JSON.stringify(toEntity(draft), (_, value) => (typeof value === "number" && numbers.push(value), value));
    expect(numbers.length).toBeGreaterThan(0);
    expect(numbers.filter((n) => !Number.isInteger(n))).toEqual([]);
  });
});
