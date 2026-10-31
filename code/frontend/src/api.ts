// Typed client for the FastAPI backend. VITE_API_URL is set in Amplify; empty means same origin (dev proxy).
const BASE = (import.meta.env.VITE_API_URL ?? "").replace(/\/$/, "");

async function call<T>(path: string, init?: RequestInit): Promise<T> {
  const res = await fetch(`${BASE}${path}`, {
    ...init,
    headers: init?.body instanceof FormData ? init?.headers : { "Content-Type": "application/json", ...init?.headers },
  });
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
export interface FreeUnit extends Unit {
  left: number;
  nights: number;
  total_chf: number;
}
export interface Trust {
  signature_valid: boolean;
  signature: string;
  public_key: string;
  algorithm: string;
  attestations: { claim: string; attested_by: string }[];
  verified_reviews: { count: number; average: number | null; recent: { rating: number; text: string }[]; rule: string };
  freshness_days: number | null;
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
export interface AgentResult {
  reply: string;
  steps: Step[];
  pending: Pending | null;
  mode: string;
  fallback?: string;
  second_opinion?: SecondOpinion;
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
export interface Proposal {
  card_id: string;
  proposed: Card;
  changes: Change[];
  summary: string;
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
  missed_demand: { detail: string; times: number }[];
  last_7_days: Record<string, number>;
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

export const api = {
  health: () => call<Health>("/api/health"),
  cards: (kind?: string) => call<Card[]>(`/api/hive/cards${kind ? `?kind=${kind}` : ""}`),
  card: (id: string) => call<Card>(`/api/hive/cards/${id}`),
  availability: (id: string, checkIn: string, checkOut: string, guests: number) =>
    call<{ available_units: FreeUnit[] }>(
      `/api/hive/cards/${id}/availability?check_in=${checkIn}&check_out=${checkOut}&guests=${guests}`,
    ),
  bookAsHuman: (
    id: string,
    body: { unit_id: string; check_in: string; check_out: string; guest_name: string; guests: number },
  ) => post<Booking>(`/api/hive/cards/${id}/book`, body),
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
};
