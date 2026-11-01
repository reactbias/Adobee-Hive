// Typed client for the FastAPI backend.
//
// The base URL is resolved per call, not baked in. VITE_API_URL is the build's default — what the Pages and
// Render deploys talk to before anybody picks anything, and empty means same origin through the dev proxy — but a
// Hive chosen in the finder overrides it for this tab. That is what makes picking Zürich actually talk to Zürich
// instead of recording a preference and carrying on with Basel.
const BUILD_BASE = (import.meta.env.VITE_API_URL ?? "").replace(/\/$/, "");

/** Thrown when the backend can't be reached; the page shows t("error.offline") for it. */
export const OFFLINE = "error.offline";

/** A status code or a lost connection is one case for the page: the backend is out of reach. */
export function shownError(message: string): string {
  if (message === OFFLINE || /^\d{3}\b/.test(message)) return OFFLINE;
  return message;
}

/**
 * A refusal from the backend, with the status, so a caller can tell a lost session (401, 403) or a lockout
 * (429, with the seconds to wait) from anything else. `message` is the backend's own detail, as before.
 */
export class ApiError extends Error {
  constructor(
    message: string,
    readonly status: number,
    readonly retryAfter: string | null = null,
  ) {
    super(message);
    this.name = "ApiError";
  }
}

/** A health check failure, kept separate from general requests so troubleshooting can explain it. */
export class HealthError extends Error {
  constructor(readonly kind: "timeout" | "network" | "response") {
    super(`Health check ${kind}`);
    this.name = "HealthError";
  }
}

// Render's free backend sleeps and takes up to a minute to wake. Past this, the chat stops "thinking" and says so.
const TIMEOUT_MS = 90_000;
const COLD = new Set([502, 503, 504]);

async function call<T>(path: string, init?: RequestInit, retry = true): Promise<T> {
  // The language switch sets <html lang>; the backend answers in it (agent replies, the second opinion).
  const lang = { "Accept-Language": document.documentElement.lang || "en" };
  // Only a read is retried after a lost connection: a POST may have arrived, and a booking must not be sent twice.
  const safe = !init?.method || init.method === "GET";
  const abort = new AbortController();
  const timer = setTimeout(() => abort.abort(), TIMEOUT_MS);
  let res: Response;
  try {
    // A peer hub's `apply_at` is a full address; everything else is a path on the Hive this tab is pointed at.
    const target = /^https?:\/\//.test(path) ? path : `${apiBase()}${path}`;
    res = await fetch(target, {
      ...init,
      signal: abort.signal,
      headers:
        init?.body instanceof FormData
          ? { ...lang, ...init?.headers }
          : { "Content-Type": "application/json", ...lang, ...init?.headers },
    });
  } catch {
    if (retry && safe && !abort.signal.aborted) return call<T>(path, init, false);
    throw new Error(OFFLINE);
  } finally {
    clearTimeout(timer);
  }
  if (!res.ok) {
    const body = await res.json().catch(() => ({}));
    // FastAPI sends a string for our errors and a list of field errors for invalid input
    const detail = Array.isArray(body.detail) ? body.detail[0]?.msg : body.detail;
    // A JSON refusal came from the app, even on 503. Retry only reads without an application detail.
    if (COLD.has(res.status) && !detail) {
      if (retry && safe) return call<T>(path, init, false);
      throw new Error(OFFLINE);
    }
    // `headers` is optional only because a stubbed Response in a test may not carry it.
    const retryAfter = res.headers?.get("Retry-After") ?? null;
    throw new ApiError(detail ?? `${res.status} ${res.statusText}`, res.status, retryAfter);
  }
  return res.json() as Promise<T>;
}

const post = <T>(path: string, body: unknown, headers?: Record<string, string>) =>
  call<T>(path, { method: "POST", body: JSON.stringify(body), headers });

// The deployed demo can require an owner token for card edits (OWNER_EDIT_TOKEN on the backend).
// It lives only in this tab's sessionStorage.
const OWNER_TOKEN_KEY = "adobee-owner-token";
export function setOwnerToken(token: string) {
  try {
    sessionStorage.setItem(OWNER_TOKEN_KEY, token);
  } catch {
    /* storage blocked: the next edit asks again */
  }
}
function ownerHeaders(): Record<string, string> {
  try {
    const token = sessionStorage.getItem(OWNER_TOKEN_KEY);
    return token ? { "X-Owner-Token": token } : {};
  } catch {
    return {};
  }
}

// The hub's administration needs a credential in X-Admin-Token: a session token from POST /api/admin/login, or
// the static ADMIN_TOKEN for curl. It lives in this tab's sessionStorage only, so closing the tab signs out.
const ADMIN_TOKEN_KEY = "adobee-admin-session";
export function setAdminToken(token: string) {
  try {
    if (token) sessionStorage.setItem(ADMIN_TOKEN_KEY, token);
    else sessionStorage.removeItem(ADMIN_TOKEN_KEY);
  } catch {
    /* storage blocked: the session lasts as long as the panel's own state */
  }
}
export function adminToken(): string {
  try {
    return sessionStorage.getItem(ADMIN_TOKEN_KEY) ?? "";
  } catch {
    return "";
  }
}
function adminHeaders(): Record<string, string> {
  const token = adminToken();
  return token ? { "X-Admin-Token": token } : {};
}

// A folder link's credential. Unlike the owner and admin tokens it is deliberately NOT stored: it is a bearer
// for somebody else's folder, handed over once in the Connect response, and it stays in the state of the screen
// that received it. A reload loses the browse, and that is the right trade for not parking another person's
// credential in a browser.
const folderAuth = (secret: string): Record<string, string> => ({ Authorization: `Bearer ${secret}` });

/**
 * One file from a peer's folder, as bytes.
 *
 * Not through `call`, which parses JSON: a granted file is a PDF or a photo as often as it is markdown. The
 * refusal shape is `call`'s, so a 404 still arrives as an `ApiError` a screen can say something about, and a
 * lost connection still arrives as OFFLINE.
 */
async function folderBytes(secret: string, path: string): Promise<Blob> {
  const query = new URLSearchParams({ path }).toString();
  let res: Response;
  try {
    res = await fetch(`${apiBase()}/api/folders/file?${query}`, { headers: folderAuth(secret) });
  } catch {
    throw new Error(OFFLINE);
  }
  if (COLD.has(res.status)) throw new Error(OFFLINE);
  if (!res.ok) {
    const body: { detail?: string } = await res.json().catch(() => ({}));
    throw new ApiError(body.detail ?? `${res.status} ${res.statusText}`, res.status);
  }
  return res.blob();
}

// The hub the app is pointed at, chosen in the instance finder: its id, and where it actually answers.
// Remembered for this tab only, so closing the tab goes back to the build's default.
const HUB_KEY = "adobee-hub";
const HUB_URL_KEY = "adobee-hub-url";

/**
 * Remember the chosen Hive. `url` is its base URL; "" means the one this build was pointed at.
 *
 * Both halves are kept together on purpose: an id alone cannot be called, and a URL alone cannot be shown.
 */
export function setChosenHub(hub: string, url = "") {
  try {
    if (hub) sessionStorage.setItem(HUB_KEY, hub);
    else sessionStorage.removeItem(HUB_KEY);
    if (hub && url) sessionStorage.setItem(HUB_URL_KEY, url.replace(/\/$/, ""));
    else sessionStorage.removeItem(HUB_URL_KEY);
  } catch {
    /* storage blocked: the finder asks again on the next load */
  }
}
export function chosenHub(): string {
  try {
    return sessionStorage.getItem(HUB_KEY) ?? "";
  } catch {
    return "";
  }
}

/** Where the chosen Hive answers, or "" for the hub this build was pointed at. */
export function chosenHubUrl(): string {
  try {
    return sessionStorage.getItem(HUB_URL_KEY) ?? "";
  } catch {
    return "";
  }
}

/** The base URL every call goes to: the Hive chosen in this tab, else the build's default. */
export const apiBase = (): string => chosenHubUrl() || BUILD_BASE;

/**
 * Where the agent runs: its own service when the build names one, else the hub's own agent. A person who picked
 * another hub gets that hub's agent, because the agent service only searches the hub it was configured with.
 */
export const agentBase = (): string => {
  const service = (import.meta.env.VITE_AGENT_URL ?? "").replace(/\/$/, "");
  const chosen = chosenHubUrl().replace(/\/$/, "");
  return service && (!chosen || chosen === BUILD_BASE) ? service : apiBase();
};

/**
 * True when this page cannot call that hub at all, whatever the hub allows.
 *
 * A page served over HTTPS may not call an `http://` address: that is mixed content, the browser blocks it
 * before any request is made, and no CORS or private-network header fixes it. The finder refuses such a choice
 * with that reason rather than appearing to switch and then failing on every call.
 */
export const blockedAsMixedContent = (url: string): boolean =>
  typeof window !== "undefined" && window.location.protocol === "https:" && /^http:\/\//i.test(url);

/** The backend the app is talking to right now: the chosen Hive, the build's default, or this very origin. */
export const apiOrigin = () => apiBase() || window.location.origin;

export const mcpUrl = () => `${apiOrigin()}/mcp/`;

// ---------- Hive ----------

export interface Unit {
  id: string;
  name: string;
  max_guests: number;
  price_chf: number;
  quantity: number;
}
export interface Trust {
  signature_valid: boolean;
  signature: string;
  public_key: string;
  algorithm: string;
  attestations: { claim: string; attested_by: string }[];
  verified_reviews: { count: number; average: number | null; recent: { rating: number; text: string }[]; rule: string };
  freshness_days: number | null;
  /** False for a card compiled from public sources: signed by the Hive as compiler, not by the business. */
  claimed: boolean;
  /** False when this hub withdrew the entity. The card and its signed history are untouched either way. */
  carried?: boolean;
  provenance?: Provenance | null;
}
export interface Provenance {
  source: string;
  url: string;
  read_on: string;
  verified_by_owner: boolean;
  note: string;
}
export interface Card {
  id: string;
  slug: string;
  kind: string;
  name: string;
  tagline?: string;
  description?: string;
  address?: string;
  contact?: Record<string, string>;
  features: string[];
  units: Unit[];
  policies?: Record<string, string>;
  opening_hours?: Record<string, string>;
  distances_m?: Record<string, number>;
  version: number;
  published_at: string;
  trust: Trust;
  [key: string]: unknown;
}
export interface Step {
  tool: string;
  input: Record<string, unknown>;
  output: Record<string, unknown>;
  ms?: number;
  /** Which MCP source answered, when the agent federates more than one. */
  source?: string;
  /** The agent's own signature check of a card, never the source's claim. */
  signature?: "valid" | "invalid" | "unchecked";
  /** Text the agent's guard withheld from this answer. */
  guard?: GuardFinding[];
}
/** One string in a tool result that gave instructions to agents, withheld before the agent read it. */
export interface GuardFinding {
  path: string;
  card_id: string | null;
  business: string | null;
  source: string | null;
  codes: string[];
  reasons: string[];
  text: string;
}
/** A listing the agent refused this run: its text addressed the agent, its copy failed the signature, or both. */
export interface Refusal {
  card_id: string | null;
  business: string | null;
  source: string;
  codes: string[];
  reasons: string[];
}
/** Demo only, rules off: the booking an unguarded agent would have sent, and the rules it broke. Never sent. */
export interface Unguarded {
  would_call: Omit<Pending, "id">; // no hold is stored, so there is nothing to approve
  total_chf: number;
  broken: { code: string; text: string; price_chf?: number; budget_chf?: number }[];
  sent: false;
}
/** Demo options for a run: plant a manipulated listing, and optionally switch the agent's rules off. */
export interface AgentOptions {
  scenario?: "injection";
  rules?: "on" | "off";
}
export interface Booking {
  status: string;
  booking_id: string;
  business: string;
  unit_name: string;
  check_in: string;
  check_out: string;
  total_chf: number;
  receipt: string;
  payment: string;
  cancellation?: string;
}
export interface Pending {
  id: string; // one-time: the server books what it held under this id, once
  tool: "hive_book";
  input: Record<string, unknown>;
}
/** A separate, independent agent checks the held booking before the human is asked; a rule check without a key. */
export interface SecondOpinion {
  verdict: "agree" | "concern";
  note: string;
  by: string;
  ms: number;
  fallback?: string;
}
/** The critic's turn: it challenges the pick with the strongest alternative, then concedes or holds. */
export interface Critic {
  challenge: string;
  answer: string;
  verdict: "agree" | "concern";
  note: string;
  rival: string | null;
}
export interface AgentResult {
  reply: string;
  steps: Step[];
  pending: Pending | null;
  mode: string;
  fallback?: string;
  second_opinion?: SecondOpinion;
  critic?: Critic;
  /** True when the critic and the verifier both agree with the pick. */
  consensus?: boolean;
  guard?: Refusal[];
  scenario?: string | null;
  rules?: "on" | "off";
  unguarded?: Unguarded | null;
}
export interface Approval {
  reply: string;
  steps: Step[];
  booking: Booking | null;
}
export interface Change {
  field: string;
  before: unknown;
  after: unknown;
}
export type SummaryItem =
  | { code: "added" | "removed"; tag: string }
  | { code: "price"; unit: string; price_chf: number };
export interface Proposal {
  card_id: string;
  proposed: Card;
  changes: Change[];
  summary: string;
  // Offline edits only: what changed, as items the studio words in the page's language.
  summary_items?: SummaryItem[] | null;
  mode: string;
}
export interface OwnerOverview {
  card: Card;
  bookings: {
    id: string;
    unit_id: string;
    guest_name: string;
    check_in: string;
    check_out: string;
    total_chf: number;
    status: string;
    agent: string;
  }[];
  /** What agents handed off to the business's own site after the person's yes: the item, never who. */
  handoffs: { item: string; created_at: string }[];
  missed_demand: { detail: string; times: number }[];
  last_7_days: Record<string, number>;
  // Standing requests this card could win by an edit: counts and budgets only, never a single traveller.
  waiting: {
    agents: number;
    budget_chf: number;
    asks: { missing: string[]; cheaper: boolean; agents: number; budget_chf: number }[];
    offers_sent: number;
  };
}
export interface DemandMap {
  days: number;
  searches: number;
  unserved_searches: number;
  features: { feature: string; asked: number; unserved: number; unserved_share: number }[];
}
export interface Health {
  status: string;
  llm: "openai" | "claude" | "mock";
  model: string;
  fast_model: string;
  /** Which similarity provider discovery ranks with. "offline" needs no key and is the default. */
  semantic: "offline" | "embeddings";
}

/** Check only this backend, once, with a short deadline and caller-controlled cancellation. */
async function health({ signal }: { signal?: AbortSignal } = {}): Promise<Health> {
  const abort = new AbortController();
  const cancel = () => abort.abort(signal?.reason);
  signal?.addEventListener("abort", cancel, { once: true });
  if (signal?.aborted) cancel();
  let timedOut = false;
  const timer = setTimeout(() => {
    timedOut = true;
    abort.abort();
  }, 5_000);
  try {
    const res = await fetch(`${apiBase()}/api/health`, {
      signal: abort.signal,
      headers: { "Accept-Language": document.documentElement.lang || "en" },
    });
    if (!res.ok) throw new ApiError(`${res.status} ${res.statusText}`, res.status);
    try {
      return (await res.json()) as Health;
    } catch {
      throw new HealthError("response");
    }
  } catch (error) {
    if (signal?.aborted) throw signal.reason;
    if (timedOut) throw new HealthError("timeout");
    if (error instanceof ApiError || error instanceof HealthError) throw error;
    throw new HealthError("network");
  } finally {
    clearTimeout(timer);
    signal?.removeEventListener("abort", cancel);
  }
}

// ---------- Ask the Hive ----------

export const MOODS = ["curious", "stressed", "planning", "celebrating"] as const;
export type Mood = (typeof MOODS)[number];
export interface Price {
  amount: number;
  currency: string;
  per: string;
  note?: string;
}
export interface AskItem {
  id: string;
  type: "offer" | "event";
  title: string;
  summary?: string | null;
  duration?: string | null;
  date?: string | null;
  price?: Price | null;
  price_chf?: number | null;
  action?: string | null;
  why: string[];
}
export interface AskReply {
  card_id: string;
  slug: string;
  name: string;
  kind: string;
  tagline?: string;
  claimed: boolean;
  source?: Provenance | null;
  signature_valid: boolean;
  items: AskItem[];
}
/** Held until the person says yes. An unclaimed card can only hand off to the business's own site. */
export interface AskPending {
  id: string;
  card_id: string;
  business: string;
  item: string;
  action: string;
  url: string;
  claimed: boolean;
}
export interface AskResult {
  question: string;
  preference: { mood: Mood | null; effects: string[]; source: string };
  replies: AskReply[];
  excluded: { card_id: string; business: string; item: string; why_not: string[] }[];
  budget_chf: number | null;
  rate: { EUR_CHF: number; note: string } | null;
  pending: AskPending | null;
  rules: string[];
  answer: string | null;
  mode: string;
  /** No card covers the request: an honest empty answer, counted as demand. */
  unserved?: boolean;
  relevance?: { by: string; reason: string | null };
  /** What the request still has to say before anyone can act, e.g. ["route", "time"] for "book me a taxi". */
  clarify?: string[];
}
/** No card answered: the scout looked on the public web. Only cards verified on their own site were added. */
export interface ScoutResult {
  question: string;
  status: "added" | "none" | "unavailable";
  added: {
    card_id: string;
    name: string;
    url: string;
    found_via: string;
    claimed: boolean;
    checks: { check: string; ok: boolean }[];
    new: boolean;
  }[];
  rejected: { name: string; url: string; why_not: string[] }[];
  result: AskResult | null;
}
export interface Handoff {
  status: "handed_off" | "requested";
  business: string;
  item: string;
  action: string;
  url: string;
  sent_to_business: boolean;
}

// ---------- Discovery, near and far (radius) ----------

/** The route a result travelled: every hub in order, ending at the Hive that answered. `hops` is its length - 1. */
export interface Route {
  path: string[];
  hops: number;
  origin: string;
  origin_url: string | null;
  /** The same card also arrived by these longer or less trusted routes. */
  also_reached_by: { path: string[]; hops: number; hub_path_trust: number }[];
}
/** One hub's trust as *this* Hive judges it: a factor in 0..1, with every factor and reason spelled out. */
export interface HubTrust {
  hub: string;
  trust: number;
  factors: Record<string, number>;
  why: string[];
}
export interface HiveMatch {
  id: string;
  slug: string;
  /** Every entity in the protocol carries a name, a description and a rating. */
  name: string;
  description: string;
  /** The verified-review average, null until a signed receipt earns one: no booking, no rating. */
  rating: number | null;
  rating_count: number;
  kind: string;
  tagline?: string | null;
  from_price_chf: number | null;
  distance_m: number | null;
  score: number;
  score_breakdown: Record<string, number>;
  why: string[];
  signature_valid: boolean;
  /** Only above radius 0: how far the result travelled and by which hubs. */
  hops?: number;
  provenance?: Route;
  /** local_relevance x hub_path_trust x hop_decay, the three factors in `score_breakdown`. */
  federated_score?: number;
  /** The signed card this Hive verified the result against, for a result from a peer. */
  card?: Card;
  /** What connecting will take: `public` opens at once, `confirm` waits for the owner's yes. */
  sharing?: Sharing;
  needs_confirmation?: boolean;
  connectable?: boolean;
  /** `email` and `phone` are always present, possibly empty; an empty one may be gated in `contact_sharing`. */
  contact?: Record<string, string>;
  contact_sharing?: Record<string, string>;
}

// ---------- Introductions: connect, then score how it went ----------

/** Who moves first, per item. `push` and `never` never appear in a search, so there is nothing to ask for. */
export type Sharing = "public" | "confirm" | "push" | "never";

/**
 * One file in a peer's folder, as one folder link may see it.
 *
 * The manifest lists more than it serves, on purpose. `readable` is the backend's own answer to "may this link
 * read the bytes", computed per path from the owner's visibility markers and grants, and a `public-summary`
 * row comes back listed and not readable: the Card already admits the file exists and hashes to this, while
 * the bytes stay the owner's to hand over. A screen that offered a button on every row would offer dead ones.
 */
export interface FolderFile {
  /** Relative to the owner's folder; what `/api/folders/file?path=` takes. */
  path: string;
  bytes: number;
  media_type: string;
  /** `sha256:` and the first twelve hex characters, the same string the file read sends as its `ETag`. */
  digest: string;
  /** How much of this path the owner admits to: `public`, `public-summary`, `shared`. */
  visibility: string;
  /** `<owner>/<path>`, the backend's own handle for the file. */
  ref: string;
  readable: boolean;
}
/** A peer's folder as one link may see it. `withheld` is a count and never a name. */
export interface FolderManifest {
  owner: string;
  viewer: string;
  /** Whether the link is established. Unlinked, a viewer sees only what the published Card already said. */
  linked: boolean;
  files: FolderFile[];
  /** How many paths the owner keeps to themselves. The names are not sent, so they cannot be shown. */
  withheld: number;
}
/**
 * The credential for one folder link. `secret` is the only time that secret exists outside a hash, so it is
 * never written to storage here: it lives in the component state of the screen that received it and is gone on
 * a reload, which is the honest cost of not keeping somebody else's bearer token in a browser.
 */
export interface FolderKey {
  id: string;
  link: string;
  handle: string;
  peer: string;
  secret: string;
  /** Always `Bearer` today; read rather than assumed. */
  scheme: string;
}

/**
 * One introduction. `requested` waits on the owner's yes, `open` waits on a person's score until `stale_at`,
 * `rated` is final, and `stale` and `declined` can never become a rating. Ratings are tenths of a star, 0–50.
 */
export interface Connection {
  id: string;
  created_at: string;
  state: "requested" | "open" | "rated" | "stale" | "declined";
  requester: string;
  requester_hub: string | null;
  target: string;
  target_hub: string | null;
  via_hub: string | null;
  sharing: string | null;
  /** What the carrying hub said the entity was worth at the introduction, frozen. */
  published_rating: number | null;
  opened_at: string | null;
  stale_at: string | null;
  rated_at: string | null;
  rating: number | null;
  note: string | null;
  rating_stars: number | null;
  published_rating_stars: number | null;
  /** The folder link this introduction opened, when the hub made one. */
  folder_link?: string;
  /**
   * The peer's folder as this link may see it, handed over with the introduction itself.
   *
   * Always present, and **empty for a remote entity**: `hub.connect` computes it from `folders.manifest`
   * against this hub's own folder root, and an entity on a peer keeps its folder on that peer's disk. So
   * browsing a folder is a local-connect feature today, and `remote` is what tells the two cases apart —
   * "nothing in it" and "not on this hub" are different sentences.
   */
  folder?: FolderManifest;
  /** The bearer for that folder, sent once and never again. `null` until a `confirm` owner says yes. */
  folder_key?: FolderKey | null;
  /** True when the entity is carried by another hub, so this hub recorded the introduction and cannot complete it. */
  remote?: boolean;
  /** Which hub carries it, when `remote`. */
  origin_hub?: string;
}
export interface Connections {
  /** Open and unscored, the one about to go stale first. */
  awaiting_rating: Connection[];
  awaiting_confirmation: Connection[];
}
export interface ConnectRequest {
  requester: string;
  entity_id: string;
  target_hub?: string;
  via_hub?: string;
  /**
   * For an entity on another hub: the signed card the federated search returned, passed through byte for
   * byte. The hub verifies it against the key that entity's own hub pinned, so a normalised or re-ordered
   * copy fails the signature check. It is ignored for an entity this hub carries.
   */
  card?: Card;
}
/** A hub's calibration as the score left it. Lower `error` is better; negative means it undersold. */
export interface HubStanding {
  hub: string;
  error: number | null;
  error_stars: number | null;
  evidence: number;
  verdict: string;
  why: string;
}
/** What a score did: the gap against what was promised, and where that leaves the hub that carried it. */
export interface ScoreOutcome {
  connection: Connection;
  hub: string;
  gap?: number;
  gap_stars?: number;
  says?: string;
  hub_standing?: HubStanding;
}
export interface Standing {
  hub: string;
  peers: HubStanding[];
}
/** What a peer Hive did with a forwarded query: who was asked, dropped, and whose card was refused here. */
export interface FederationReport {
  hub: string;
  radius: number;
  seen: string[];
  budget_ms: number;
  elapsed_ms: number;
  /** A hub is an entity too: it declares a name and a description; the rating is this Hive's own. */
  asked: { hub: string; name: string; description: string; rating: number; url: string; trust: number }[];
  dropped: { hub: string; reason: string }[];
  rejected: { hub: string; card_id: string; origin: string; reason: string }[];
  hub_trust: Record<string, HubTrust>;
}
export interface Discovery {
  matches: HiveMatch[];
  excluded: (HiveMatch & { why_not: string[] })[];
  ranking_policy: string;
  /**
   * How many entities the query actually earned something from. `matched: 0` means nothing matched,
   * which is the honest empty state: the hub filters these rows out itself now, so a nonzero score
   * with an empty `why` no longer reaches the client. Optional because a hub forwarding a peer's
   * query answers unfiltered.
   */
  matched?: number;
  /** How many entities were ranked to produce `matched`, so the count has a denominator. */
  considered?: number;
  /** Only above radius 0. */
  federated_ranking_policy?: string;
  federation?: FederationReport;
}
export interface DiscoverQuery {
  /** Ask for the unfiltered ranking, including entities the query earned nothing from. */
  include_irrelevant?: boolean;
  query?: string;
  kind?: string;
  near?: string;
  max_price_chf?: number;
  features?: string[];
  check_in?: string;
  check_out?: string;
  guests?: number;
  /** Hop limit over peer Hives. 0, the default, is this Hive only; 3 is the cap. */
  radius?: number;
  budget_ms?: number;
}

function discoverPath({ features = [], ...rest }: DiscoverQuery): string {
  const params = new URLSearchParams();
  for (const [key, value] of Object.entries(rest))
    if (value !== undefined && value !== "") params.set(key, String(value));
  for (const feature of features) params.append("features", feature);
  const query = params.toString();
  return `/api/hive/discover${query ? `?${query}` : ""}`;
}

// ---------- The hub directory, and running a hub ----------

/**
 * One Hive in the directory. `error` is this hub's calibration: published rating minus what people actually
 * found, in tenths of a star. **Lower is better**, and a negative number means the hub undersold what it
 * offered. It is null, and `verdict` is "unproven", until enough introductions have been scored to say.
 */
export interface DirectoryHub {
  hub: string;
  url: string;
  home: boolean;
  blocked: boolean;
  name: string;
  description: string;
  admission?: string;
  /** Three states: true, false, and null for "we have not asked". Null is never rendered as "not accepting". */
  accepting?: boolean | null;
  verification?: string;
  /** null means the peer has not published a count. Never shown as 0: zero is a claim we do not have. */
  entities?: number | null;
  apply_at?: string;
  /** True once the peer has answered at least once, so its name and description are its own words. */
  known?: boolean;
  /** ISO 8601 UTC of the last ask, successful or not. null means genuinely never asked. */
  last_asked?: string | null;
  /** Whether that last ask was answered. null alongside a null `last_asked`. */
  last_asked_ok?: boolean | null;
  /** When the answer being shown arrived, which differs from `last_asked` once an ask has failed. */
  last_answered?: string | null;
  /** The last ask failed, so what is shown is an older answer rather than the current one. */
  stale?: boolean;
  error: number | null;
  error_stars: number | null;
  evidence: number;
  verdict: string;
  why: string;
}
export interface Directory {
  hubs: DirectoryHub[];
  /** Seconds between rounds of asking the peers, so a row can explain why a count is two minutes old. */
  asked_every_seconds?: number;
  /** Scored introductions a verdict needs, so "unproven" can say how far off it is. */
  min_evidence?: number;
}

/** What a hub asks of someone who wants to join, published so they can read it before applying. */
export interface RegistrationPolicy {
  policy: string;
  means: string;
  checks: string[];
  proof_types: string[];
  key_custody: string;
}

export interface Proof {
  type: string;
  subject: string;
}

/**
 * The document sent to join. Every key is always present: the hub checks the signature over the body after
 * filling in its defaults, so a missing `invite` or `proofs` would change the bytes and break it.
 */
export interface JoinApplication {
  entity: Record<string, unknown>;
  public_key: string;
  proofs: Proof[];
  invite: string;
  signature?: string;
}

/** The hub's answer. A refusal is `state: "rejected"` with the checks, the reason and a next step, not an error. */
export interface ApplicationOutcome {
  id: string;
  state: "admitted" | "pending" | "rejected" | "withdrawn";
  entity_id: string;
  custody: "owner" | "hub";
  verification: string;
  checks: { check: string; ok: boolean; detail: string }[];
  reason: string;
  next: string;
}

/** A peer and how closely its published ratings matched what our people found. Lower `error` is better. */
export interface Peer {
  hub: string;
  url?: string;
  blocked?: boolean;
  error: number | null;
  error_stars: number | null;
  evidence: number;
  verdict: string;
  why: string;
}
export interface AdminOverview {
  hub: string;
  name: string;
  index: { entities: number };
  neighbours: { configured: number; blocked: number; with_evidence: number };
  blocklist: { hubs: number; entities: number };
  connections: Record<string, number>;
  peers: Peer[];
}
/** One settings field, shaped so a form can be generated from it rather than hardcoded. */
export interface SettingsField {
  key: string;
  label: string;
  value: string | number | boolean | null;
  help: string;
  options?: string[];
  editable: boolean;
}
export interface AdminSettings {
  fields: SettingsField[];
  calibration: { lower_is_better: boolean; help: string; min_evidence: number; half_life_days: number };
}
/** One row of the hub's entity list. Every field is on the public card too; the list is the operator's view. */
export interface AdminEntity {
  id: string;
  slug: string;
  name: string;
  kind: string;
  /** False for a card compiled from public information: a lead, never a business that agreed. */
  claimed: boolean;
  /** Null until a signed receipt earns one. Zero would read as a bad business, not a new one. */
  rating: number | null;
  rating_count: number;
  published_at: string | null;
  version: number | null;
  signature_valid: boolean;
  bookable: boolean;
  /** False when this hub withdrew it: out of search, not bookable, signed history kept. */
  carried: boolean;
  removal: AdminRemoval | null;
}
/** One withdrawal: this hub stopped carrying an entity, and said why. */
export interface AdminRemoval {
  entity_id: string;
  reason: string;
  removed_at: string | null;
  removed_by: string;
}
export interface AdminEntities {
  entities: AdminEntity[];
  /** What the hub carries, so a withdrawn entity is listed but not counted. */
  count: number;
  withdrawn: number;
}
/** One side of the market an entity is indexed by: what it offers, or what it needs. */
export interface AdminSide {
  title?: string;
  summary?: string;
  tags?: string[];
  sharing?: string;
  [key: string]: unknown;
}
/** One contact channel with the sharing flag that actually applies: the stricter of two. */
export interface AdminContactRow {
  channel: string;
  value: string;
  sharing: string;
  searchable: boolean;
}
/** One entity in full, as the operator deciding what to do about it needs to see it. */
export interface AdminEntityDetail {
  entity: AdminEntity;
  card: Card;
  offers: AdminSide[];
  needs: AdminSide[];
  contact: AdminContactRow[];
  contact_sharing: Record<string, string>;
  sharing_default: string;
  trust: Trust;
  signature: {
    valid: boolean;
    signature: string;
    public_key: string;
    algorithm: string;
    fresh: boolean;
    valid_until: string | null;
    version: number | null;
  };
  /** Blocked is not the same as removed: blocking refuses it wherever it comes from. */
  blocked: boolean;
  block: BlockEntry | null;
  /** Carried is this hub's side of it: a withdrawn entity is out of search here and nowhere else. */
  carried: boolean;
  removal: AdminRemoval | null;
}
/** One row of the admin ledger. `actor` is always "admin": one shared password, so no person to name. */
export interface AuditEntry {
  id: string;
  at: string | null;
  action: string;
  subject: string;
  reason: string;
  actor: string;
  credential: string;
  detail: string;
}
export interface AdminAudit {
  entries: AuditEntry[];
  who_limit: string;
}
/** One peer hub as an operator acts on it: where it is, what it is called, whether it answers, how it rates. */
export interface AdminPeer {
  url: string;
  /** The id to use: what the peer told us, or its host until anyone has asked. */
  hub: string;
  hub_id: string;
  name: string;
  note: string | null;
  /** "active" or "removed". A removed row stays, so the environment seed cannot put the peer back. */
  state: string;
  added_at: string | null;
  added_by: string | null;
  changed_at: string | null;
  removed_at: string | null;
  removed_reason: string | null;
  /** What the peer says about itself, from federation's background asking. False until it answers once. */
  known: boolean;
  description: string;
  verification: string;
  admission: string;
  /** None rather than 0 for a hub that has not published a count: unknown is never drawn as zero. */
  entities: number | null;
  /** When we last tried, and whether that try worked. Null means genuinely never asked, not refused. */
  last_asked: string | null;
  last_asked_ok: boolean | null;
  last_answered: string | null;
  /** The last ask failed, so the name and count on screen are an older answer rather than the current one. */
  stale: boolean;
  /** Blocked is not removed: a block refuses the hub in both directions. */
  blocked: boolean;
  error: number | null;
  error_stars: number | null;
  evidence: number;
  verdict: string;
  why: string;
}
export interface AdminPeers {
  peers: AdminPeer[];
  live: string[];
  seed: string[];
  /** True while nothing has been stored: HIVE_PEER_URLS is still the live list. */
  from_environment: boolean;
  blocked_hubs: string[];
}
/** One optional integration. A key is never part of this: only presence, a fingerprint and four characters. */
export interface AdminService {
  name: string;
  label: string;
  purpose: string;
  /** What the hub does without it. Empty means nothing stops working. */
  without: string;
  /** The environment variable that seeds it, so an operator can set it there instead. */
  env: string;
  configured: boolean;
  /** "stored" (set here), "environment" (the deployment's own) or "none". */
  source: string;
  stored: boolean;
  fingerprint: string;
  last_four: string;
  stored_at: string | null;
  /** Null until someone tests it: untested is not a failure. */
  working: boolean | null;
  checked_at: string | null;
  last_error: string;
  testable: boolean;
  storage_warning: string;
}
export interface AdminServices {
  services: AdminService[];
  provider: string;
  enabled: boolean;
  storage_warning: string;
}
export interface AdminNeighbours {
  peers: Peer[];
  blocked_hubs: string[];
}
export interface BlockEntry {
  kind: string;
  subject: string;
  reason: string;
  added_at: string | null;
  added_by: string;
}
export interface Blocklist {
  entries: BlockEntry[];
  kinds: string[];
}
/** One signed application to join this hub. `checks` ran in order and stopped at the first failure. */
export interface Application {
  id: string;
  created_at: string;
  state: string;
  entity_id: string;
  kind: string;
  name: string;
  custody: string;
  verification: string;
  proofs: { type: string; subject: string }[];
  checks: { check: string; ok: boolean; detail: string }[];
  decided_at: string | null;
  decided_by: string | null;
  reason: string;
  next: string;
}
export interface Applications {
  applications: Application[];
  policy: { policy: string; means: string };
}
export interface AdminSession {
  token: string;
  expires_in: number;
}

export const api = {
  health,
  /** Search the Hive. Without a radius the answer is this Hive's own cards, exactly as before. */
  discover: (query: DiscoverQuery = {}) => call<Discovery>(discoverPath(query)),
  cards: (kind?: string) => call<Card[]>(`/api/hive/cards${kind ? `?kind=${kind}` : ""}`),
  card: (id: string) => call<Card>(`/api/hive/cards/${id}`),
  review: (receipt: string, rating: number, text: string) =>
    post<{ review_id: string; card_id: string; verified_booking: boolean; verified_stay: boolean }>(
      "/api/hive/reviews",
      { receipt, rating, text },
    ),
  agent: (messages: { role: string; content: string }[], options: AgentOptions = {}) =>
    post<AgentResult>(`${agentBase()}/api/agent`, { messages, ...options }),
  approve: (pending: Pending) => post<Approval>(`${agentBase()}/api/agent/approve`, { pending }),
  owner: (id: string) => call<OwnerOverview>(`/api/owner/${id}`, { headers: ownerHeaders() }),
  propose: (id: string, instruction: string) =>
    post<Proposal>(`/api/owner/${id}/propose`, { instruction }, ownerHeaders()),
  publish: (id: string, proposed: Card) => post<Card>(`/api/owner/${id}/publish`, { proposed }, ownerHeaders()),
  verify: (card: Card) => post<{ signature_valid: boolean }>("/api/hive/verify", { card }),
  forge: (cardId: string) => post<Card>(`/api/hive/demo/forge/${encodeURIComponent(cardId)}`, {}),
  demand: () => call<DemandMap>("/api/hive/demand"),
  simulate: (n: number) => post<DemandMap>(`/api/demo/simulate?n=${n}`, {}),
  /** pick: the person named one business from the last answer, so its hand-off is held for a yes. */
  ask: (question: string, mood: Mood | null, pick = false) =>
    post<AskResult>("/api/ask", pick ? { question, mood, pick } : { question, mood }),
  scout: (question: string) => post<ScoutResult>("/api/ask/scout", { question }),
  askApprove: (id: string) => post<Handoff>("/api/ask/approve", { id }),
  activity: (after = 0) => call<ActivityFeed>(`/api/activity?after=${after}`),

  /** The Hives to choose between. Not on `main` yet (PR #71): the finder falls back to this hub on a 404. */
  directory: () => call<Directory>("/api/hub/directory"),
  /** `applyAt` is the directory row's address: a path for this hub, a full URL for a peer. */
  registrationPolicy: (applyAt = "/api/hub/register") =>
    call<RegistrationPolicy>(applyAt.replace(/\/api\/hub\/register$/, "/api/hub/registration")),
  register: (application: JoinApplication, applyAt = "/api/hub/register") =>
    call<ApplicationOutcome>(applyAt, { method: "POST", body: JSON.stringify(application) }),

  /** Ask to be introduced. A public entry comes back `open`; a `confirm` one comes back `requested`. */
  connect: (request: ConnectRequest) => post<Connection>("/api/hub/connect", request),
  /** Score an open introduction once, in tenths of a star (43 is 4.3). */
  score: (id: string, rating: number, note = "") =>
    post<ScoreOutcome>(`/api/hub/connections/${encodeURIComponent(id)}/score`, { rating, note }),
  confirmConnection: (id: string) =>
    post<Connection>(`/api/hub/connections/${encodeURIComponent(id)}/confirm`, {}, ownerHeaders()),
  declineConnection: (id: string) =>
    post<Connection>(`/api/hub/connections/${encodeURIComponent(id)}/decline`, {}, ownerHeaders()),
  connections: ({ requester = "", target = "" }: { requester?: string; target?: string } = {}) => {
    const params = new URLSearchParams();
    if (requester) params.set("requester", requester);
    if (target) params.set("target", target);
    const query = params.toString();
    return call<Connections>(`/api/hub/connections${query ? `?${query}` : ""}`);
  },
  standing: () => call<Standing>("/api/hub/standing"),

  /**
   * A peer's folder as this link may see it, asked again rather than trusted from the Connect response: the
   * owner can grant a path while somebody is looking at the list, and `readable` changes under them.
   */
  folderManifest: (secret: string) => call<FolderManifest>("/api/folders/manifest", { headers: folderAuth(secret) }),
  /**
   * One granted file, as bytes. Every refusal is the same 404 on purpose, so a caller learns nothing from
   * one: a listed-but-not-served path and a path that was never there answer identically.
   */
  folderFile: (secret: string, path: string) => folderBytes(secret, path),

  /** Trade the hub's password for a session token. A 429 carries the seconds to wait in `retryAfter`. */
  adminLogin: (password: string) => post<AdminSession>("/api/admin/login", { password }),
  adminLogout: () => post<{ signed_out: boolean }>("/api/admin/logout", {}, adminHeaders()),
  adminOverview: () => call<AdminOverview>("/api/admin/overview"),
  adminSettings: () => call<AdminSettings>("/api/admin/settings"),
  adminNeighbours: () => call<AdminNeighbours>("/api/admin/neighbours"),
  /** What this hub carries. Behind the admin token: the whole membership in one call is an operator's view. */
  adminEntities: () => call<AdminEntities>("/api/admin/entities", { headers: adminHeaders() }),
  /** One entity in full: the signed card, its offers and needs, contact flags, trust and signature. */
  adminEntity: (id: string) =>
    call<AdminEntityDetail>(`/api/admin/entities/${encodeURIComponent(id)}`, { headers: adminHeaders() }),
  /** Stop carrying an entity: out of search, not bookable, signed history kept. The reason is required. */
  adminRemoveEntity: (id: string, reason: string) =>
    post<{ entity_id: string; carried: boolean; history_kept: boolean }>(
      `/api/admin/entities/${encodeURIComponent(id)}/remove`,
      { reason },
      adminHeaders(),
    ),
  adminRestoreEntity: (id: string, reason: string) =>
    post<{ entity_id: string; carried: boolean }>(
      `/api/admin/entities/${encodeURIComponent(id)}/restore`,
      { reason },
      adminHeaders(),
    ),
  /** The admin ledger, newest first; pass a subject for one entity's or one peer's history. */
  adminAudit: (subject = "") =>
    call<AdminAudit>(`/api/admin/audit${subject ? `?subject=${encodeURIComponent(subject)}` : ""}`, {
      headers: adminHeaders(),
    }),
  /** The peers this hub asks. A database read: it never fetches from a peer, so a dead one costs nothing. */
  adminPeers: () => call<AdminPeers>("/api/admin/peers", { headers: adminHeaders() }),
  /** Add a peer. The next federated search asks it: no restart, no redeploy. */
  adminAddPeer: (url: string, reason: string, name = "") =>
    post<AdminPeer>("/api/admin/peers", { url, reason, name }, adminHeaders()),
  adminEditPeer: (url: string, reason: string, name = "", hub_id = "") =>
    call<AdminPeer>("/api/admin/peers", {
      method: "PUT",
      body: JSON.stringify({ url, reason, name, hub_id }),
      headers: adminHeaders(),
    }),
  /** Stop asking a peer. Not a block: a block refuses it in both directions (adminBlock). */
  adminRemovePeer: (url: string, reason: string) =>
    post<AdminPeer>("/api/admin/peers/remove", { url, reason }, adminHeaders()),
  /** Ask every peer whether it answers, in parallel under one deadline, and store the result. */
  adminCheckPeers: () => post<{ peers: AdminPeer[] }>("/api/admin/peers/check", {}, adminHeaders()),
  /** The optional integrations and whether a key is set. Never returns a key. */
  adminServices: () => call<AdminServices>("/api/admin/services", { headers: adminHeaders() }),
  /** Store a key. Write-only: the answer is the service's status, so the key cannot come back. */
  adminSetServiceKey: (name: string, secret: string) =>
    post<AdminService>(`/api/admin/services/${encodeURIComponent(name)}`, { secret }, adminHeaders()),
  adminClearServiceKey: (name: string) =>
    call<AdminService>(`/api/admin/services/${encodeURIComponent(name)}`, {
      method: "DELETE",
      headers: adminHeaders(),
    }),
  /** One cheap authenticated call with the key in use. A key that does not work is a 200, not an error. */
  adminCheckService: (name: string) =>
    post<AdminService>(`/api/admin/services/${encodeURIComponent(name)}/check`, {}, adminHeaders()),
  adminBlocklist: () => call<Blocklist>("/api/admin/blocklist"),
  adminBlock: (kind: string, subject: string, reason: string) =>
    post<BlockEntry>("/api/admin/blocklist", { kind, subject, reason }, adminHeaders()),
  adminUnblock: (kind: string, subject: string) =>
    call<{ lifted: boolean }>(`/api/admin/blocklist/${kind}/${encodeURIComponent(subject)}`, {
      method: "DELETE",
      headers: adminHeaders(),
    }),
  /** Not on `main` yet (PR #71): the panel shows an honest "not deployed" line on a 404. */
  adminApplications: (state = "") => call<Applications>(`/api/admin/applications${state ? `?state=${state}` : ""}`),
  adminDecide: (id: string, admit: boolean, reason: string) =>
    post<Application>(`/api/admin/applications/${encodeURIComponent(id)}`, { admit, reason }, adminHeaders()),
};

// ---------- The live activity feed (?demo) ----------

/** One step an agent took. Codes from fixed lists; `business` is a card's public name, never a person. */
export interface ActivityEvent {
  n: number;
  /** Lines from the same request share a run. */
  run: string;
  at: string;
  agent: "traveller" | "verifier" | "critic" | "concierge" | "scout" | "hive";
  step: string;
  business: string | null;
  outcome: string | null;
  /** partner: the business's own signed card. web: compiled from the public web, hand-off only. */
  source: "partner" | "web" | "model" | "rules" | null;
  count: number | null;
}
export interface ActivityFeed {
  events: ActivityEvent[];
  /** The cursor: pass it back to get only newer lines. */
  last: number;
}
