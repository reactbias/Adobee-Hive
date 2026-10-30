// Typed client for the FastAPI backend. VITE_API_URL is set in Amplify; empty means same origin (dev proxy).
const BASE = (import.meta.env.VITE_API_URL ?? "").replace(/\/$/, "");

async function call<T>(path: string, init?: RequestInit): Promise<T> {
  const res = await fetch(`${BASE}${path}`, {
    ...init,
    headers: init?.body instanceof FormData ? init?.headers : { "Content-Type": "application/json", ...init?.headers },
  });
  if (!res.ok) {
    const body = await res.json().catch(() => ({}));
    throw new Error(body.detail ?? `${res.status} ${res.statusText}`);
  }
  return res.json() as Promise<T>;
}

const post = <T>(path: string, body: unknown) => call<T>(path, { method: "POST", body: JSON.stringify(body) });

export const mcpUrl = () => `${BASE || window.location.origin}/mcp/`;

// ---------- Hive ----------

export interface Unit { id: string; name: string; max_guests: number; price_chf: number; quantity: number }
export interface FreeUnit extends Unit { left: number; nights: number; total_chf: number }
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
export interface Step { tool: string; input: Record<string, unknown>; output: Record<string, unknown> }
export interface Booking {
  status: string; booking_id: string; business: string; unit_name: string; check_in: string; check_out: string;
  total_chf: number; receipt: string; payment: string; cancellation?: string;
}
export interface AgentResult { reply: string; steps: Step[]; booking: Booking | null; mode: string }
export interface Change { field: string; before: unknown; after: unknown }
export interface Proposal { card_id: string; proposed: Card; changes: Change[]; summary: string; mode: string }
export interface OwnerOverview {
  card: Card;
  bookings: { id: string; unit_id: string; guest_name: string; check_in: string; check_out: string; total_chf: number; status: string; agent: string }[];
  missed_demand: { detail: string; times: number }[];
  last_7_days: Record<string, number>;
}
export interface Health { status: string; llm: "claude" | "mock"; model: string; fast_model: string }

export const api = {
  health: () => call<Health>("/api/health"),
  cards: (kind?: string) => call<Card[]>(`/api/hive/cards${kind ? `?kind=${kind}` : ""}`),
  card: (id: string) => call<Card>(`/api/hive/cards/${id}`),
  availability: (id: string, checkIn: string, checkOut: string, guests: number) =>
    call<{ available_units: FreeUnit[] }>(`/api/hive/cards/${id}/availability?check_in=${checkIn}&check_out=${checkOut}&guests=${guests}`),
  bookAsHuman: (id: string, body: { unit_id: string; check_in: string; check_out: string; guest_name: string; guests: number }) =>
    post<Booking>(`/api/hive/cards/${id}/book`, body),
  review: (receipt: string, rating: number, text: string) => post<{ review_id: string }>("/api/hive/reviews", { receipt, rating, text }),
  agent: (messages: { role: string; content: string }[]) => post<AgentResult>("/api/agent", { messages }),
  owner: (id: string) => call<OwnerOverview>(`/api/owner/${id}`),
  propose: (id: string, instruction: string) => post<Proposal>(`/api/owner/${id}/propose`, { instruction }),
  publish: (id: string, proposed: Card) => post<Card>(`/api/owner/${id}/publish`, { proposed }),

};
