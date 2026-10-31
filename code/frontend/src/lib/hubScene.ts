// A search asks the hub first, as far as the person chose: radius 0 is this hub, above it the neighbours too.
// The folders are the fallback for when that call cannot be made.

import { api, type FederationReport } from "../api";
import { sceneFromDiscovery, type Federation, type Scene } from "./cardView";

/** The offerings the live hubs return for this request, or null when they have nothing to draw. */
export async function hubScene(query: string, radius = 0): Promise<Scene | null> {
  const found = await api.discover({ query, radius });
  if (!found.matches.length) return null;
  const cards: Record<string, unknown> = {};
  await Promise.all(
    found.matches.map(async (match) => {
      let body: Record<string, unknown> = match.card ? { ...match.card } : {};
      if (!match.card) {
        try {
          body = { ...(await api.card(match.id)) };
        } catch {
          body = {};
        }
      }
      cards[match.id] = {
        ...body,
        id: match.id,
        name: body.name ?? match.name,
        description: body.description ?? match.description,
        rating: body.rating ?? match.rating,
        rating_count: body.rating_count ?? match.rating_count,
        contact: body.contact ?? match.contact,
        contact_sharing: body.contact_sharing ?? match.contact_sharing,
      };
    }),
  );
  const scene = sceneFromDiscovery(query, found.matches, cards);
  return scene && found.federation ? { ...scene, federation: federationOf(found.federation) } : scene;
}

function federationOf(report: FederationReport): Federation {
  return {
    radius: report.radius,
    asked: (report.asked ?? []).map(({ hub, name }) => ({ hub, name })),
    dropped: (report.dropped ?? []).map(({ hub, reason }) => ({ hub, reason })),
    rejected: (report.rejected ?? []).map(({ hub, card_id, reason }) => ({ hub, card_id, reason })),
  };
}
