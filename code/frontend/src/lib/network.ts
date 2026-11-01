// The hub network as nodes, built from three endpoints that are already live. No new endpoint, no chart library.
//
// `GET /api/admin/overview`   what this hub carries, and how many introductions are open
// `GET /api/admin/neighbours` one row per configured peer, with its calibration
// `GET /api/hub/directory`    each hub's name, description and entity count — not on `main` yet (PR #71)
// `GET /api/hub/standing`     this hub's calibration of its peers, as a fallback for the two above
//
// A peer we have not asked carries no entity count and no admission policy. That is drawn as unknown, never as
// zero: "0 entities" is a claim, and we do not have it.
//
// Why `standing` is in that list. This screen is open to anyone — a federated network that only its operator
// can see the shape of is not a federated network — but the peer rows came from `/api/admin/neighbours`, an
// operator route a hub is free to lock, and the directory is not on `main` everywhere. `/api/hub/standing` is
// the one public, always-present endpoint that returns per-peer calibration, so when the other two cannot be
// read the honeycomb still has its cells instead of showing a hub alone in the world. It carries no address,
// no entity count and no blocklist, so a peer known only this way is drawn as calibration plus unknowns.

import type { AdminNeighbours, AdminOverview, Directory, Standing } from "../api";

export interface HubNode {
  hub: string;
  /** The hub's own name where we have it, otherwise its id. Never empty. */
  label: string;
  home: boolean;
  blocked: boolean;
  /** null means we have not asked, which is not the same as none. */
  entities: number | null;
  /** "" means we have not asked. */
  admission: string;
  /** Calibration: published minus realised, in tenths of a star. Lower is better; negative means undersold. */
  error: number | null;
  verdict: string;
  evidence: number;
  why: string;
}

/**
 * The home hub plus one node per peer, home first. Works with no peers at all.
 *
 * `neighbours` null means that read failed, which is not the same as a hub with no peers: then `standing` is
 * used instead, because a hub that cannot show its neighbours is worse than one that shows them with less
 * about each. A `neighbours` answer, even an empty one, is the better source and wins.
 */
export function buildNetwork(
  overview: AdminOverview | null,
  neighbours: AdminNeighbours | null,
  directory: Directory | null,
  standing: Standing | null = null,
): HubNode[] {
  const described = new Map((directory?.hubs ?? []).map((h) => [h.hub, h]));
  const home: HubNode = {
    hub: overview?.hub ?? "",
    label: overview?.name || overview?.hub || "",
    home: true,
    blocked: false,
    entities: overview?.index.entities ?? null,
    admission: described.get(overview?.hub ?? "")?.admission ?? "",
    error: null,
    verdict: "home",
    evidence: 0,
    why: "",
  };
  // Only when the operator route could not be read at all. An empty peer list from it is an answer.
  const fallback = (standing?.peers ?? []).filter((p) => p.hub && p.hub !== home.hub);
  const rows = neighbours
    ? neighbours.peers
    : fallback.map((p) => ({ ...p, url: "", blocked: false, error_stars: p.error_stars ?? null }));
  const peers = rows.map((p) => {
    const seen = described.get(p.hub);
    return {
      hub: p.hub,
      label: seen?.name || p.hub,
      home: false,
      blocked: Boolean(p.blocked) || (neighbours?.blocked_hubs ?? []).includes(p.hub),
      entities: seen?.entities ?? null,
      admission: seen?.admission ?? "",
      error: p.error,
      verdict: p.verdict,
      evidence: p.evidence,
      why: p.why,
    };
  });
  return [home, ...peers];
}

/** Introductions still waiting on somebody: the number that says the hub is actually in use. */
export const liveIntroductions = (o: AdminOverview | null): number =>
  (o?.connections.awaiting_confirmation ?? 0) + (o?.connections.awaiting_rating ?? 0);

/**
 * The points of one flat-topped hexagon, for an SVG `polygon`. The logo is a bee in an open hexagon and the
 * honeycomb cell is the shape the whole brand is built on, so the nodes are cells.
 */
export function hexPoints(cx: number, cy: number, r: number): string {
  return Array.from({ length: 6 }, (_, i) => {
    const angle = (Math.PI / 3) * i;
    return `${(cx + r * Math.cos(angle)).toFixed(1)},${(cy + r * Math.sin(angle)).toFixed(1)}`;
  }).join(" ");
}

/**
 * Where peer number `i` of `total` sits around the centre. Six to a ring, like a honeycomb's neighbours, and a
 * seventh starts a second, turned ring so nothing hides behind the first. A ring that is not full spreads its
 * peers evenly round the whole circle rather than leaving them bunched on one side: two peers sit opposite,
 * three make a triangle, four a diamond.
 */
export function ringPosition(i: number, total: number, cx: number, cy: number): { x: number; y: number; ring: number } {
  const ring = Math.floor(i / 6);
  const radius = [140, 238][ring] ?? 238 + (ring - 1) * 98;
  const onThisRing = Math.min(6, Math.max(1, total - ring * 6));
  const turn = ring % 2 ? Math.PI / 6 : 0;
  const angle = ((2 * Math.PI) / onThisRing) * (i % 6) + turn - Math.PI / 2;
  return { x: cx + radius * Math.cos(angle), y: cy + radius * Math.sin(angle), ring };
}

/** A label that will not spill out of its cell. SVG has no text wrapping worth the trouble. */
export const clip = (label: string, max: number): string =>
  label.length > max ? `${label.slice(0, max - 1).trimEnd()}\u2026` : label;

/**
 * A viewBox drawn tight around what is actually there. One hub alone in a box sized for seven looks broken; it
 * is not, it is a hub with no peers yet.
 */
export function viewBox(points: { x: number; y: number }[], cx: number, cy: number, pad: number): string {
  const xs = [cx, ...points.map((p) => p.x)];
  const ys = [cy, ...points.map((p) => p.y)];
  const minX = Math.min(...xs) - pad;
  const minY = Math.min(...ys) - pad;
  return `${minX} ${minY} ${Math.max(...xs) + pad - minX} ${Math.max(...ys) + pad - minY}`;
}
