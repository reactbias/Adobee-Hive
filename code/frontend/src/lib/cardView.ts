// The page draws itself from the hub folders: each entity, then its offers/ and searches/.
// Matching is local on purpose: a search should show the offerings before any model is called.
// The chat stays behind Details.

export type Price = {
  from?: number;
  to?: number;
  amount?: number;
  currency: string;
  unit?: string;
};

/**
 * One field from a file, kept so the screen can show whatever the file included. An object
 * (policies, distances) keeps its entries as pairs, so the screen can list them.
 */
export type Field = { key: string; text: string; pairs?: [string, string | number][] };

export type Offer = { id: string; title: string; summary?: string; price?: Price; fields: Field[] };
export type Need = { id: string; title: string; summary?: string; budget?: Price; fields: Field[] };

/** The three fields every entity carries, plus the lists a result can draw. */
export type HiveCard = {
  id: string;
  kind: string;
  name: string;
  description: string;
  tagline?: string;
  /** Where it is: an address, or a place name. */
  place?: string;
  features: string[];
  /** Tenths of a star, 0–50. Null means not rated yet. */
  rating: number | null;
  rating_count: number;
  offers: Offer[];
  needs: Need[];
  skills: string[];
  /** The owner's line for when a person must say yes. Card text, shown as data. */
  policy?: string;
  /** Everything else the hub sent, so a new field shows up without a layout change. */
  facts: Field[];
};

export type Hit = {
  card: HiveCard;
  /** Every offering in that entity's offers folder. The person picks one. */
  offers: Offer[];
  /** Every search in that entity's searches folder, when the request is a search. */
  needs: Need[];
  /** The request asked to act, so the picked offering can ask for a yes. */
  acting: boolean;
  /** How this hub found it, when the row came from a live search. */
  found?: { why: string[]; path: string[] };
};

export type Scene = { query: string; hits: Hit[] };

const STOP = new Set([
  "the",
  "and",
  "for",
  "with",
  "from",
  "near",
  "under",
  "over",
  "your",
  "you",
  "our",
  "just",
  "this",
  "that",
  "not",
  "but",
  "one",
  "two",
  "who",
  "what",
  "when",
  "where",
  "how",
  "can",
  "please",
  "name",
  "week",
  "close",
  "night",
  "nights",
  "book",
  "mein",
  "meine",
  "mir",
  "ein",
  "eine",
  "und",
  "mit",
  "fur",
  "von",
  "bei",
  "nach",
  "dem",
  "den",
  "der",
  "die",
  "das",
  "pour",
  "une",
  "des",
  "les",
  "dans",
  "avec",
  "pres",
  "mon",
  "moi",
  "con",
  "per",
  "una",
  "del",
  "della",
  "che",
  "non",
  "mio",
]);

// Words the cards use in English, and the way a person asks for the same thing in the four languages.
const ALIAS: Record<string, string> = {
  hotel: "hotel",
  hotels: "hotel",
  zimmer: "room",
  chambre: "room",
  chambres: "room",
  camera: "room",
  camere: "room",
  rooms: "room",
  room: "room",
  dog: "dog",
  dogs: "dog",
  hund: "dog",
  hunde: "dog",
  hundefreundlich: "dog",
  hundefreundliches: "dog",
  chien: "dog",
  chiens: "dog",
  cane: "dog",
  cani: "dog",
  quiet: "quiet",
  ruhig: "quiet",
  ruhiges: "quiet",
  calme: "quiet",
  tranquillo: "quiet",
  basel: "basel",
  bale: "basel",
  basilea: "basel",
  design: "design",
  designer: "design",
  designerin: "design",
  designeuse: "design",
  dataviz: "dataviz",
  sprint: "sprint",
  krafft: "krafft",
  lena: "lena",
  hofmann: "hofmann",
};

const NAMES = new Set(["krafft", "lena", "hofmann"]);

const ACT = /\b(book\w*|buche\w*|reserv\w*|prenot\w*|hire\w*|engag\w*|sprint)\b/;
const LOOK =
  /\b(compare|vergleich|confront|dont book|do not book|nicht buchen|nur vergleichen|ne reserve pas|compare seulement|solo confrontare|non prenotare|just compare)\b/;

function plain(text: string): string {
  return text.toLowerCase().normalize("NFD").replace(/\p{M}/gu, "");
}

function tokens(text: string): Set<string> {
  const out = new Set<string>();
  for (const raw of plain(text).split(/[^a-z0-9]+/)) {
    if (raw.length < 3) continue;
    const word = ALIAS[raw] ?? raw;
    if (STOP.has(word) || STOP.has(raw)) continue;
    out.add(word);
  }
  return out;
}

function price(raw: unknown): Price | undefined {
  if (!raw || typeof raw !== "object") return undefined;
  const p = raw as Record<string, unknown>;
  if (typeof p.currency !== "string") return undefined;
  const out: Price = { currency: p.currency };
  if (typeof p.from === "number") out.from = p.from;
  if (typeof p.to === "number") out.to = p.to;
  if (typeof p.amount === "number") out.amount = p.amount;
  if (typeof p.unit === "string") out.unit = p.unit;
  else if (typeof p.per === "string") out.unit = p.per;
  return out;
}

const text = (value: unknown): string | undefined => (typeof value === "string" && value.trim() ? value : undefined);

/** An address, or the most specific name a `location` object carries. */
function placeOf(o: Record<string, unknown>): string | undefined {
  const direct = text(o.address) ?? text(o.location);
  if (direct) return direct;
  const loc = o.location;
  if (!loc || typeof loc !== "object") return undefined;
  const l = loc as Record<string, unknown>;
  return text(l.address) ?? text(l.city) ?? text(l.name);
}

function asText(value: unknown): string {
  if (typeof value === "string" || typeof value === "number" || typeof value === "boolean") return String(value);
  if (Array.isArray(value)) return value.map(asText).filter(Boolean).join(", ");
  if (!value || typeof value !== "object" || "currency" in value) return "";
  return Object.entries(value)
    .map(([key, item]) => {
      const text = asText(item);
      return text ? `${key}: ${text}` : "";
    })
    .filter(Boolean)
    .join(" · ");
}

/** Every field except the ones the layout already uses. New keys show up without a code change. */
function fieldsOf(raw: Record<string, unknown>, skip: string[]): Field[] {
  const out: Field[] = [];
  for (const [key, value] of Object.entries(raw)) {
    if (skip.includes(key)) continue;
    const shown = asText(value);
    if (!shown) continue;
    const field: Field = { key, text: shown };
    if (value && typeof value === "object" && !Array.isArray(value) && !("currency" in value)) {
      field.pairs = Object.entries(value).flatMap(([k, v]): [string, string | number][] =>
        typeof v === "number" ? [[k, v]] : asText(v) ? [[k, asText(v)]] : [],
      );
    }
    out.push(field);
  }
  return out;
}

function listing(
  raw: unknown,
  moneyKey: "price" | "budget",
): { id: string; title: string; summary?: string; money?: Price; fields: Field[] } | null {
  if (!raw || typeof raw !== "object") return null;
  const o = raw as Record<string, unknown>;
  if (typeof o.id !== "string" || typeof o.title !== "string") return null;
  return {
    id: o.id,
    title: o.title,
    summary: text(o.summary),
    money: price(o[moneyKey]),
    fields: fieldsOf(o, ["id", "title", "summary", moneyKey, ...LISTING_SKIP]),
  };
}

// Tags and the hand-off label are for agents; the person sees the offer itself.
const LISTING_SKIP = ["tags", "action"];

/** Keep a card the UI can draw. A file that lacks the three entity fields is ignored. */
export function readCard(raw: unknown): HiveCard | null {
  if (!raw || typeof raw !== "object") return null;
  const o = raw as Record<string, unknown>;
  if (typeof o.id !== "string" || typeof o.name !== "string" || typeof o.description !== "string") return null;
  if (o.rating != null && typeof o.rating !== "number") return null;
  const offers = Array.isArray(o.offers) ? o.offers.flatMap((item) => asOffer(item)) : [];
  const needs = Array.isArray(o.needs) ? o.needs.flatMap((item) => asNeed(item)) : [];
  const skills = Array.isArray(o.skills)
    ? o.skills.flatMap((s) =>
        s && typeof s === "object" && typeof (s as { tag?: unknown }).tag === "string"
          ? [(s as { tag: string }).tag]
          : [],
      )
    : [];
  const policyRaw = o.policy;
  const policy =
    policyRaw &&
    typeof policyRaw === "object" &&
    typeof (policyRaw as { human_in_loop?: unknown }).human_in_loop === "string"
      ? (policyRaw as { human_in_loop: string }).human_in_loop
      : undefined;
  return {
    id: o.id,
    kind: typeof o.kind === "string" ? o.kind : "business",
    name: o.name,
    description: o.description,
    tagline: text(o.tagline),
    place: placeOf(o),
    features: Array.isArray(o.features) ? o.features.filter((f): f is string => typeof f === "string") : [],
    rating: typeof o.rating === "number" ? o.rating : null,
    rating_count: typeof o.rating_count === "number" ? o.rating_count : 0,
    offers,
    needs,
    skills,
    policy,
    facts: [],
  };
}

function asOffer(raw: unknown): Offer[] {
  const row = listing(raw, "price");
  return row ? [{ id: row.id, title: row.title, summary: row.summary, price: row.money, fields: row.fields }] : [];
}

function asNeed(raw: unknown): Need[] {
  const row = listing(raw, "budget");
  return row ? [{ id: row.id, title: row.title, summary: row.summary, budget: row.money, fields: row.fields }] : [];
}

const HUB_SKIP = [
  // Drawn in their own place on the card.
  "tagline",
  "address",
  "location",
  "features",
  // Publishing metadata: the signature already vouches for it.
  "version",
  "published_at",
  "valid_until",
  "aliases",
  "provenance",
  "id",
  "slug",
  "name",
  "description",
  "rating",
  "rating_count",
  "kind",
  "offers",
  "needs",
  "units",
  "skills",
  "policy",
  "trust",
  "signature",
  "public_key",
  "keys",
  "sig",
  "hive",
  "seq",
  "updated",
];

/** A star average from the hub (4.6) becomes tenths (46). An integer above 5 is already tenths. */
function toTenths(rating: number): number {
  return rating <= 5 ? Math.round(rating * 10) : Math.round(rating);
}

/**
 * A card as the hub endpoints send it. Rooms live in `units`, and the rating is a star average.
 * The folder files use `offers` and tenths, which `readCard` already understands.
 */
export function readHubCard(raw: unknown): HiveCard | null {
  if (!raw || typeof raw !== "object") return null;
  const o = { ...(raw as Record<string, unknown>) };
  const trust = o.trust as { verified_reviews?: { average?: unknown; count?: unknown } } | undefined;
  const reviews = trust?.verified_reviews;
  if (typeof o.rating !== "number" && typeof reviews?.average === "number") o.rating = reviews.average;
  if (typeof o.rating_count !== "number" && typeof reviews?.count === "number") o.rating_count = reviews.count;
  if (typeof o.rating === "number") o.rating = toTenths(o.rating);
  if (!Array.isArray(o.offers) && Array.isArray(o.units)) {
    o.offers = o.units.flatMap((unit) => {
      if (!unit || typeof unit !== "object") return [];
      const u = unit as Record<string, unknown>;
      if (typeof u.id !== "string" || typeof u.name !== "string") return [];
      const price = typeof u.price_chf === "number" ? { amount: u.price_chf, currency: "CHF", unit: "night" } : u.price;
      return [{ id: u.id, title: u.name, price, max_guests: u.max_guests, quantity: u.quantity }];
    });
  }
  const card = readCard(o);
  if (!card) return null;
  card.facts = fieldsOf(o, HUB_SKIP);
  return card;
}

/** One row per discover match, using the card the hub returned for that id. */
export function sceneFromDiscovery(
  query: string,
  matches: { id: string; why?: string[]; provenance?: { path?: string[] } }[],
  cards: Record<string, unknown>,
): Scene | null {
  const asked = plain(query);
  const acting = ACT.test(asked) && !LOOK.test(asked);
  const hits: Hit[] = [];
  for (const match of matches) {
    const card = readHubCard(cards[match.id] ?? match);
    if (!card) continue;
    const path = match.provenance?.path?.filter((hop) => typeof hop === "string") ?? [];
    hits.push({
      card,
      offers: card.offers,
      needs: card.needs,
      acting,
      found: { why: (match.why ?? []).filter((line) => typeof line === "string"), path },
    });
  }
  return hits.length ? { query, hits } : null;
}

const entityFiles = import.meta.glob<Record<string, unknown>>("../data/hubs/*/entities/*/entity.json", {
  eager: true,
  import: "default",
});
const offerFiles = import.meta.glob<Record<string, unknown>>("../data/hubs/*/entities/*/offers/*.json", {
  eager: true,
  import: "default",
});
const searchFiles = import.meta.glob<Record<string, unknown>>("../data/hubs/*/entities/*/searches/*.json", {
  eager: true,
  import: "default",
});

function entityDir(path: string): string {
  return path.replace(/\/(?:entity\.json|offers\/[^/]+\.json|searches\/[^/]+\.json)$/, "");
}

function grouped(files: Record<string, Record<string, unknown>>): Map<string, Record<string, unknown>[]> {
  const out = new Map<string, Record<string, unknown>[]>();
  for (const [path, raw] of Object.entries(files).sort(([a], [b]) => a.localeCompare(b))) {
    const dir = entityDir(path);
    out.set(dir, [...(out.get(dir) ?? []), raw]);
  }
  return out;
}

/** One card per entity folder. Offers and searches come from the files beside it. */
function loadCatalog(): HiveCard[] {
  const offers = grouped(offerFiles);
  const searches = grouped(searchFiles);
  const cards: HiveCard[] = [];
  for (const [path, raw] of Object.entries(entityFiles)) {
    const card = readCard(raw);
    if (!card) continue;
    const dir = entityDir(path);
    card.offers = (offers.get(dir) ?? []).flatMap((file) => asOffer(file));
    card.needs = (searches.get(dir) ?? []).flatMap((file) => asNeed(file));
    card.offers.sort((a, b) => a.id.localeCompare(b.id));
    card.needs.sort((a, b) => a.id.localeCompare(b.id));
    cards.push(card);
  }
  return cards.sort((a, b) => a.name.localeCompare(b.name));
}

export const CARDS: HiveCard[] = loadCatalog();

function blobOf(card: HiveCard): Set<string> {
  return tokens(
    [
      card.name,
      card.description,
      card.kind,
      ...card.skills,
      ...card.offers.map((o) => o.title),
      ...card.needs.map((n) => n.title),
    ].join(" "),
  );
}

function overlap(query: Set<string>, text: string): number {
  const words = tokens(text);
  let n = 0;
  for (const w of query) if (words.has(w)) n += 1;
  return n;
}

/**
 * What to draw for this request. Null when the cards do not cover it, so the page can
 * fall through to the agent. A rating is never invented here.
 */
export function sceneFor(text: string, cards: HiveCard[] = CARDS): Scene | null {
  const query = text.trim();
  if (!query) return null;
  const words = tokens(query);
  const asked = plain(query);
  const acting = ACT.test(asked) && !LOOK.test(asked);
  const hits: Hit[] = [];
  for (const card of cards) {
    const blob = blobOf(card);
    let score = 0;
    let named = false;
    for (const w of words) {
      if (!blob.has(w)) continue;
      score += 1;
      if (NAMES.has(w)) named = true;
    }
    if (named) score = Math.max(score, 2);
    if (score < 2) continue;
    const offersTouch = card.offers.filter((o) => overlap(words, o.title) > 0);
    const needsTouch = card.needs.filter((n) => overlap(words, n.title) > 0);
    const aboutNeeds = needsTouch.length > 0 && offersTouch.length === 0;
    hits.push({
      card,
      offers: aboutNeeds ? [] : card.offers,
      needs: aboutNeeds || needsTouch.length > 0 ? card.needs : [],
      acting: acting && !aboutNeeds,
    });
  }
  hits.sort((a, b) => b.offers.length + b.needs.length - (a.offers.length + a.needs.length));
  return hits.length ? { query, hits } : null;
}

/** `43` is 4.3. Null stays null so the screen can say "not rated yet" instead of 0. */
export function ratingScore(rating: number | null): string | null {
  if (rating === null) return null;
  return (rating / 10).toFixed(1);
}
