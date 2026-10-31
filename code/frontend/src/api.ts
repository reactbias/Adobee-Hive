// Typed client for the FastAPI backend. VITE_API_URL is set by the Pages build; empty means same origin (dev proxy).
const BASE = (import.meta.env.VITE_API_URL ?? "").replace(/\/$/, "");

/** Thrown when the backend can't be reached; the page shows t("error.offline") for it. */
export const OFFLINE = "error.offline";
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
    res = await fetch(`${BASE}${path}`, {
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
  // A gateway error means the request never reached the app (cold start): safe to send again.
  if (COLD.has(res.status) && retry) return call<T>(path, init, false);
  if (COLD.has(res.status)) throw new Error(OFFLINE);
  if (!res.ok) {
    const body = await res.json().catch(() => ({}));
    // FastAPI sends a string for our errors and a list of field errors for invalid input
    const detail = Array.isArray(body.detail) ? body.detail[0]?.msg : body.detail;
    throw new Error(detail ?? `${res.status} ${res.statusText}`);
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

export const mcpUrl = () => `${BASE || window.location.origin}/mcp/`;

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

export const api = {
  health: () => call<Health>("/api/health"),
  cards: (kind?: string) => call<Card[]>(`/api/hive/cards${kind ? `?kind=${kind}` : ""}`),
  card: (id: string) => call<Card>(`/api/hive/cards/${id}`),
  review: (receipt: string, rating: number, text: string) =>
    post<{ review_id: string }>("/api/hive/reviews", { receipt, rating, text }),
  agent: (messages: { role: string; content: string }[], options: AgentOptions = {}) =>
    post<AgentResult>("/api/agent", { messages, ...options }),
  approve: (pending: Pending) => post<Approval>("/api/agent/approve", { pending }),
  owner: (id: string) => call<OwnerOverview>(`/api/owner/${id}`, { headers: ownerHeaders() }),
  propose: (id: string, instruction: string) =>
    post<Proposal>(`/api/owner/${id}/propose`, { instruction }, ownerHeaders()),
  publish: (id: string, proposed: Card) => post<Card>(`/api/owner/${id}/publish`, { proposed }, ownerHeaders()),
  verify: (card: Card) => post<{ signature_valid: boolean }>("/api/hive/verify", { card }),
  forge: (cardId: string) => post<Card>(`/api/hive/demo/forge/${encodeURIComponent(cardId)}`, {}),
  demand: () => call<DemandMap>("/api/hive/demand"),
  simulate: (n: number) => post<DemandMap>(`/api/demo/simulate?n=${n}`, {}),
  ask: (question: string, mood: Mood | null) => post<AskResult>("/api/ask", { question, mood }),
  scout: (question: string) => post<ScoutResult>("/api/ask/scout", { question }),
  askApprove: (id: string) => post<Handoff>("/api/ask/approve", { id }),
  activity: (after = 0) => call<ActivityFeed>(`/api/activity?after=${after}`),
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
