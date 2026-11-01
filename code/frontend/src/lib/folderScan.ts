// A folder of markdown, turned into a Card in the page. The folder is never uploaded: this reads it here, and only
// the Card the person approves is sent. The rules mirror code/backend/tools/seed_vaults.py, so a folder signed up in
// the browser and one seeded from the command line become the same Card.
//
// What a person keeps back is never read: a part marked private, shared or hidden contributes no offers, needs or
// contact. In the Card, a private part is its path and a file count; shared and hidden parts are absent entirely,
// because listing a folder in order to say it is secret announces that it exists (documentation/cards/README.md).

export type VaultFile = { path: string; bytes: Uint8Array };
export type Visibility = "public" | "public-summary" | "shared" | "private" | "hidden";
export const VISIBILITIES: Visibility[] = ["public", "public-summary", "shared", "private", "hidden"];
/** Read into the Card. The other three are the owner's to keep. */
const READ: Visibility[] = ["public", "public-summary"];

/** Per channel: public, ask first, only when I send it, never. */
export type ContactFlag = "public" | "confirm" | "push" | "never";
export const CONTACT_FLAGS: ContactFlag[] = ["public", "confirm", "push", "never"];
export type ContactChannel = { channel: string; value: string; flag: ContactFlag };

export type Listing = { id: string; title: string; summary: string; price_chf?: number };
export type Unit = { id: string; name: string; max_guests: number; price_chf: number; quantity: number };
export type StructureRow =
  | { path: string; bytes: number; visibility: "public" | "public-summary"; digest: string }
  | { path: string; files: number; visibility: "private" };

export const KINDS = ["hotel", "cafe", "person", "service"] as const;

export interface CardDraft {
  id: string;
  kind: string;
  name: string;
  description: string;
  contact: ContactChannel[];
  offers: Listing[];
  needs: Listing[];
  features: string[];
  units: Unit[];
  structure: StructureRow[];
}

// A slash cannot be a child directory's name; keep this UI key out of the published structure.
export const ROOT_FILES_GROUP = "/";

/** The parts at the top of a folder, with all loose files shared or kept back as one part. */
export function groupsOf(files: VaultFile[]): { path: string; files: number }[] {
  const counts = new Map<string, number>();
  for (const file of files) {
    const group = groupOf(file.path);
    counts.set(group, (counts.get(group) ?? 0) + 1);
  }
  return [...counts]
    .sort(([a], [b]) => (a === ROOT_FILES_GROUP ? -1 : b === ROOT_FILES_GROUP ? 1 : a.localeCompare(b)))
    .map(([path, n]) => ({ path, files: n }));
}

/** The visibility key of a file: its child directory, or the single group of loose root files. */
export const groupOf = (path: string) => (path.includes("/") ? path.split("/")[0] : ROOT_FILES_GROUP);

/** A part's visibility as the person set it; `public-summary` until they say otherwise, as in seed_vaults.py. */
const visibilityOf = (path: string, chosen: Record<string, Visibility>): Visibility =>
  chosen[groupOf(path)] ?? "public-summary";

// Words that mean something to the hub's `fit()`, lifted from the prose rather than typed twice.
const FEATURE_WORDS = [
  "quiet",
  "dog-friendly",
  "breakfast",
  "wifi",
  "accessible",
  "vegan",
  "late check-in",
  "river view",
  "terrace",
  "remote",
];
// Needs first, so "What I need" is never read as an offer.
const OFFER_HEADINGS = [
  "what i do",
  "what we do",
  "what i offer",
  "what we offer",
  "offers",
  "services",
  "rooms",
  "menu",
];
const NEED_HEADINGS = ["what i need", "what we need", "needs", "hiring", "looking for"];
const GUARANTEED = ["email", "phone"];

export const slug = (text: string) =>
  text
    .toLowerCase()
    .normalize("NFD")
    .replace(/\p{M}/gu, "")
    .replace(/[^a-z0-9]+/g, "-")
    .replace(/^-+|-+$/g, "");

function entry(text: string): Listing {
  const title = text
    .split(/\s+[—–-]\s+/)[0]
    .replace(/[.,]+$/, "")
    .slice(0, 120);
  const price = text.match(/CHF\s*([\d']+)/);
  return {
    id: slug(title).slice(0, 63) || "item",
    title,
    summary: text.slice(0, 300),
    ...(price ? { price_chf: Number(price[1].replace(/'/g, "")) } : {}),
  };
}

function readContact(text: string): ContactChannel[] {
  const out: ContactChannel[] = [];
  for (const raw of text.split(/\r?\n/)) {
    const line = raw.trim().replace(/^-+/, "").trim();
    if (!line.includes(":") || line.startsWith("#")) continue;
    const at = line.indexOf(":");
    const channel = line.slice(0, at).trim().toLowerCase();
    const value = line.slice(at + 1).trim();
    if (value.toLowerCase() === "never") out.push({ channel, value: "", flag: "never" });
    else if (value.toLowerCase().startsWith("ask")) out.push({ channel, value: "", flag: "confirm" });
    else out.push({ channel, value, flag: "public" });
  }
  return out;
}

function readOffersNeeds(texts: string[]): { offers: Listing[]; needs: Listing[] } {
  const offers: Listing[] = [];
  const needs: Listing[] = [];
  for (const text of texts) {
    let bucket: Listing[] | null = null;
    for (const raw of text.split(/\r?\n/)) {
      const line = raw.trim();
      if (line.startsWith("#")) {
        const heading = line.replace(/^#+/, "").trim().toLowerCase();
        bucket = NEED_HEADINGS.some((h) => heading.includes(h))
          ? needs
          : OFFER_HEADINGS.some((h) => heading.includes(h))
            ? offers
            : null;
      } else if (bucket && line.startsWith("-")) {
        bucket.push(entry(line.replace(/^-+/, "").trim()));
      }
    }
  }
  return { offers, needs };
}

// "- Attic single — 1 guest, CHF 110, 4 of them." The name runs up to a dash with spaces round it, so a name with
// a hyphen in it ("River-view double") is kept whole.
const ROOM = /^(?<name>.+?)\s+[—–-]+\s*(?<guests>\d+)\s*guests?,\s*CHF\s*(?<price>\d+)(?:,\s*(?<qty>\d+))?/;

function readUnits(text: string): Unit[] {
  const units: Unit[] = [];
  for (const raw of text.split(/\r?\n/)) {
    const line = raw.trim().replace(/^-+/, "").trim();
    const m = line && !line.startsWith("#") ? line.match(ROOM) : null;
    if (!m?.groups) continue;
    const name = m.groups.name.trim();
    units.push({
      id: slug(name).slice(0, 24) || `unit-${units.length + 1}`,
      name,
      max_guests: Number(m.groups.guests),
      price_chf: Number(m.groups.price),
      quantity: Number(m.groups.qty ?? 1),
    });
  }
  return units;
}

async function digest(bytes: Uint8Array): Promise<string> {
  const hash = new Uint8Array(await crypto.subtle.digest("SHA-256", bytes));
  return `sha256:${[...hash]
    .map((b) => b.toString(16).padStart(2, "0"))
    .join("")
    .slice(0, 12)}`;
}

/** Fill a Card from a folder: name and description, contact, offers and needs, rooms, and its shape. */
export async function buildDraft(
  folder: string,
  files: VaultFile[],
  visibility: Record<string, Visibility>,
): Promise<CardDraft> {
  const decoder = new TextDecoder();
  const md = files.filter((f) => f.path.endsWith(".md")).sort((a, b) => a.path.localeCompare(b.path));
  const readable = md.filter((f) => READ.includes(visibilityOf(f.path, visibility)));
  const text = (path: string) => {
    const file = readable.find((f) => f.path === path);
    return file ? decoder.decode(file.bytes) : "";
  };

  const lines = text("about.md")
    .split(/\r?\n/)
    .map((l) => l.trim())
    .filter(Boolean);
  const contact = readContact(text("contact.md"));
  for (const channel of GUARANTEED)
    if (!contact.some((c) => c.channel === channel)) contact.push({ channel, value: "", flag: "public" });
  const bodies = readable.map((f) => decoder.decode(f.bytes));
  const { offers, needs } = readOffersNeeds(bodies);
  const prose = bodies.join(" ").toLowerCase();
  const units = readUnits(text("rooms.md"));

  const structure: StructureRow[] = [];
  const kept = new Map<string, number>();
  for (const file of md) {
    const seen = visibilityOf(file.path, visibility);
    if (seen === "public" || seen === "public-summary")
      structure.push({ path: file.path, bytes: file.bytes.length, visibility: seen, digest: await digest(file.bytes) });
    else if (seen === "private") kept.set(groupOf(file.path), (kept.get(groupOf(file.path)) ?? 0) + 1);
  }
  for (const [path, n] of kept)
    structure.push({ path: path === ROOT_FILES_GROUP ? "." : path, files: n, visibility: "private" });
  structure.sort((a, b) => a.path.localeCompare(b.path));

  return {
    id: slug(folder).slice(0, 63),
    kind: units.length ? "hotel" : "person",
    name: lines[0]?.replace(/^#+\s*/, "").trim() || folder,
    description: (lines.slice(1).find((l) => !l.startsWith("#")) ?? "").slice(0, 300),
    contact,
    offers,
    needs,
    features: FEATURE_WORDS.filter((w) => prose.includes(w)),
    units,
    structure,
  };
}

/**
 * The entity as the application carries it, in the shape seed_vaults.py registers. A gated channel is an empty
 * value plus its flag; a channel only the owner sends, or never, is absent from `contact` and named only in
 * `contact_sharing`, which is where the hub looks before it fills in the guaranteed keys.
 */
export function toEntity(draft: CardDraft): Record<string, unknown> {
  const contact: Record<string, string> = {};
  const contactSharing: Record<string, string> = {};
  for (const c of draft.contact) {
    if (c.flag === "public") contact[c.channel] = c.value.trim();
    else if (c.flag === "confirm") contact[c.channel] = "";
    if (c.flag !== "public") contactSharing[c.channel] = c.flag;
  }
  const description = draft.description.trim();
  return {
    id: draft.id,
    slug: draft.id,
    kind: draft.kind,
    name: draft.name.trim(),
    description,
    tagline: description.slice(0, 90),
    // An introduction to a person is theirs to grant, the hub's own default (hub.py).
    sharing: draft.kind === "person" ? "confirm" : "public",
    contact,
    contact_sharing: contactSharing,
    features: draft.features,
    offers: draft.offers,
    needs: draft.needs,
    structure: draft.structure,
    ...(draft.units.length ? { units: draft.units } : {}),
  };
}
