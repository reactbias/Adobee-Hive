// Where a result came from. A federated directory that hides the origin of an answer is just a directory with
// extra steps, so every result row says which hub it came from, local ones included: if a local result said
// nothing, the absence of a label would mean "unknown" rather than "here".
//
// The backend's `provenance.path` is ordered **origin first, answering hub last**. A card that Zürich relayed from
// Basel reads ["basel", "zurich", "us"] with origin "basel" — the whole chain, not whoever handed it over. That
// distinction is load-bearing: a relaying hub must not be able to present someone else's card as its own.

export interface Route {
  path?: string[];
  hops?: number;
  origin?: string;
  also_reached_by?: unknown[];
}

export interface Source {
  /** True when the answering hub is the origin: nothing travelled. */
  local: boolean;
  /** The hub whose card this is. Empty only for a local result. */
  origin: string;
  hops: number;
  /** The whole chain, origin first, answering hub last. Empty for a local result. */
  path: string[];
  /** The hubs between the origin and us: the relays, which a person should be able to see. */
  relays: string[];
  /** How many other routes the same card also arrived by. A trust signal, not a ranking input. */
  alsoReachedBy: number;
}

/** Read one result's origin. Anything missing or malformed reads as local rather than as unknown. */
export function readSource(match: { hops?: number; provenance?: Route | null }): Source {
  const route = match.provenance ?? {};
  const path = Array.isArray(route.path) ? route.path.map(String) : [];
  const hops = Number(match.hops ?? route.hops ?? 0) || 0;
  const origin = String(route.origin ?? path[0] ?? "");
  if (hops <= 0 || !origin) return { local: true, origin, hops: 0, path, relays: [], alsoReachedBy: 0 };
  return {
    local: false,
    origin,
    hops,
    path,
    // Between the origin and the hub that answered. Two-hub paths have none.
    relays: path.slice(1, -1),
    alsoReachedBy: Array.isArray(route.also_reached_by) ? route.also_reached_by.length : 0,
  };
}
